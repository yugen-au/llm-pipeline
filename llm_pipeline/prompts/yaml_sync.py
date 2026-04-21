"""YAML-based prompt discovery and bidirectional sync.

Prompts stored as YAML files in a configurable directory are synced
with the database on startup (YAML -> DB) and on UI save (DB -> YAML).
Version-based conflict resolution: newer version always wins.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from llm_pipeline.prompts.utils import extract_variables_from_content
from llm_pipeline.utils.versioning import compare_versions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom YAML representer for literal block style on multiline strings
# ---------------------------------------------------------------------------

class _LiteralStr(str):
    """Wrapper to force literal block style (|) in YAML output."""


def _literal_representer(dumper: yaml.Dumper, data: _LiteralStr) -> Any:
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(_LiteralStr, _literal_representer)



# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------

_VARIANT_TYPES = ("system", "user")


def parse_prompt_yaml(path: Path) -> list[dict]:
    """Parse a prompt YAML file into a list of variant dicts.

    Each dict is shaped to match Prompt model fields. Returns 1-2 dicts
    (one per variant present in the file).

    Raises:
        ValueError: If prompt_key is missing or no variants defined.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML dict, got {type(data).__name__} in {path}")

    prompt_key = data.get("prompt_key")
    if not prompt_key:
        raise ValueError(f"Missing prompt_key in {path}")

    # Shared top-level fields
    shared = {
        "prompt_key": prompt_key,
        "prompt_name": data.get("prompt_name", prompt_key),
        "category": data.get("category"),
        "step_name": data.get("step_name"),
    }

    variants: list[dict] = []
    for vtype in _VARIANT_TYPES:
        section = data.get(vtype)
        if section is None:
            continue
        if not isinstance(section, dict):
            logger.warning("Skipping non-dict '%s' section in %s", vtype, path)
            continue

        content = section.get("content", "")
        var_defs = section.get("variable_definitions")
        required = extract_variables_from_content(content) if content else []

        variants.append({
            **shared,
            "prompt_type": vtype,
            "content": content,
            "description": section.get("description"),
            "version": str(section.get("version", "1.0")),
            "variable_definitions": var_defs,
            "required_variables": required or None,
            "created_by": "yaml",
        })

    if not variants:
        raise ValueError(f"No system or user section in {path}")

    return variants


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_yaml_prompts(prompts_dir: Path) -> list[dict]:
    """Scan directory for *.yaml files and parse each into variant dicts."""
    results: list[dict] = []
    for yaml_path in sorted(prompts_dir.glob("*.yaml")):
        try:
            results.extend(parse_prompt_yaml(yaml_path))
        except Exception:
            logger.warning("Failed to parse %s, skipping", yaml_path, exc_info=True)
    return results


# ---------------------------------------------------------------------------
# Startup sync: YAML -> DB
# ---------------------------------------------------------------------------


def sync_yaml_to_db(engine: "Engine", prompts_dirs: "Path | list[Path]") -> None:  # noqa: F821
    """Sync YAML prompt files into the database.

    Accepts a single Path or list of Paths. For each variant: insert if
    missing, insert new version if YAML version is newer, skip with WARNING
    if same or older.
    """
    from sqlmodel import Session
    from llm_pipeline.db.prompt import Prompt
    from llm_pipeline.db.versioning import get_latest, save_new_version
    from llm_pipeline.prompts.variables import rebuild_from_db

    if isinstance(prompts_dirs, Path):
        prompts_dirs = [prompts_dirs]

    variants: list[dict] = []
    for d in prompts_dirs:
        if d.is_dir():
            variants.extend(discover_yaml_prompts(d))
    if not variants:
        return

    inserted = 0
    updated = 0

    with Session(engine) as session:
        for v in variants:
            key_filters = {
                "prompt_key": v["prompt_key"],
                "prompt_type": v["prompt_type"],
            }
            existing = get_latest(session, Prompt, **key_filters)

            # Fields that go into new_fields (exclude key_filters and version)
            new_fields = {
                k: v[k] for k in (
                    "prompt_name", "content", "description",
                    "variable_definitions", "required_variables",
                    "category", "step_name", "created_by",
                ) if k in v
            }

            if existing is None:
                # First-time insert
                save_new_version(
                    session, Prompt, key_filters, new_fields,
                    version=v.get("version"),
                )
                inserted += 1
                if v.get("variable_definitions"):
                    rebuild_from_db(
                        v["prompt_key"], v["prompt_type"], v["variable_definitions"],
                    )
            else:
                cmp = compare_versions(v["version"], existing.version)
                if cmp > 0:
                    # YAML is newer — insert new version row
                    save_new_version(
                        session, Prompt, key_filters, new_fields,
                        version=v["version"],
                    )
                    updated += 1
                    if v.get("variable_definitions"):
                        rebuild_from_db(
                            v["prompt_key"], v["prompt_type"],
                            v["variable_definitions"],
                        )
                else:
                    # Same or older — no-op with WARNING per A8
                    logger.warning(
                        "YAML prompt %s/%s version %s <= DB version %s, skipping",
                        v["prompt_key"], v["prompt_type"],
                        v["version"], existing.version,
                    )

        session.commit()

    if inserted or updated:
        logger.info(
            "YAML prompt sync: %d inserted, %d updated from %d dir(s)",
            inserted, updated, len(prompts_dirs),
        )


# ---------------------------------------------------------------------------
# Write-back: DB -> YAML
# ---------------------------------------------------------------------------


def _to_literal(value: str) -> str:
    """Wrap multiline strings for literal block style in YAML output."""
    if "\n" in value:
        return _LiteralStr(value)
    return value


def write_prompt_to_yaml(
    prompts_dir: Path,
    prompt_key: str,
    prompt_type: str,
    data: dict,
) -> bool:
    """Write updated prompt data back to its YAML file.

    Creates new files if they don't exist. Creates the directory if needed.
    Uses atomic temp-file + Path.replace to avoid partial-write corruption.
    Returns True if file was written.
    """
    import tempfile

    prompts_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = prompts_dir / f"{prompt_key}.yaml"

    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    else:
        doc = {"prompt_key": prompt_key}

    # Update shared top-level fields
    if "prompt_name" in data and data["prompt_name"]:
        doc["prompt_name"] = data["prompt_name"]
    if "category" in data:
        doc["category"] = data["category"]
    if "step_name" in data:
        doc["step_name"] = data["step_name"]

    # Update the variant section
    section = doc.get(prompt_type) or {}
    if "content" in data and data["content"] is not None:
        section["content"] = _to_literal(data["content"])
    if "description" in data:
        section["description"] = data["description"]
    if "version" in data:
        section["version"] = data["version"]
    if "variable_definitions" in data:
        section["variable_definitions"] = data["variable_definitions"]

    doc[prompt_type] = section

    # Atomic write: temp file in same dir then replace
    fd, tmp_path = tempfile.mkstemp(
        dir=str(prompts_dir), suffix=".yaml.tmp",
    )
    try:
        with open(fd, "w", encoding="utf-8") as f:
            yaml.dump(
                doc, f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        Path(tmp_path).replace(yaml_path)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    logger.debug("Wrote back %s/%s to %s", prompt_key, prompt_type, yaml_path)
    return True


__all__ = [
    "parse_prompt_yaml",
    "discover_yaml_prompts",
    "sync_yaml_to_db",
    "write_prompt_to_yaml",
]
