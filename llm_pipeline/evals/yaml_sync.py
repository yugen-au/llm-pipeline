"""YAML-based eval dataset sync: YAML -> DB on startup, DB -> YAML on save.

DB is source of truth. Version-based conflict resolution: newer version wins.
"""
import logging
import tempfile
from pathlib import Path
from typing import Any

import yaml

from llm_pipeline.db.versioning import get_latest, save_new_version
from llm_pipeline.evals.models import EvaluationDataset, EvaluationCase
from llm_pipeline.utils.versioning import compare_versions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# YAML parsing
# ---------------------------------------------------------------------------


def _parse_eval_yaml(path: Path) -> dict[str, Any]:
    """Parse an eval dataset YAML file into a dict.

    Expected format:
        name: ...
        target_type: step|pipeline
        target_name: ...
        description: ...
        cases:
          - name: ...
            inputs: {...}
            expected_output: {...}
            metadata: {...}
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Expected YAML dict, got {type(data).__name__} in {path}")

    name = data.get("name")
    if not name:
        raise ValueError(f"Missing 'name' in {path}")

    return data


# ---------------------------------------------------------------------------
# Startup sync: YAML -> DB (insert-if-not-exists)
# ---------------------------------------------------------------------------


def sync_evals_yaml_to_db(engine: "Engine", scan_dirs: list[Path]) -> None:  # noqa: F821
    """Scan directories for *.yaml eval datasets and seed DB.

    For each YAML file: insert EvaluationDataset if name not in DB,
    then insert each case if (dataset_id, case_name) not in DB.
    """
    from sqlmodel import Session, select

    yaml_files: list[Path] = []
    for d in scan_dirs:
        if d.is_dir():
            yaml_files.extend(sorted(d.glob("*.yaml")))

    if not yaml_files:
        return

    inserted_ds = 0
    inserted_cases = 0

    with Session(engine) as session:
        for path in yaml_files:
            try:
                data = _parse_eval_yaml(path)
            except Exception:
                logger.warning("Failed to parse eval YAML %s, skipping", path, exc_info=True)
                continue

            name = data["name"]
            target_type = data.get("target_type", "step")
            target_name = data.get("target_name", name)
            description = data.get("description")
            cases = data.get("cases", [])

            # Insert dataset if not exists
            existing = session.exec(
                select(EvaluationDataset).where(EvaluationDataset.name == name)
            ).first()

            if existing is None:
                dataset = EvaluationDataset(
                    name=name,
                    target_type=target_type,
                    target_name=target_name,
                    description=description,
                )
                session.add(dataset)
                session.flush()  # get id
                inserted_ds += 1
            else:
                dataset = existing

            # Insert/update cases via versioning helpers
            for case_data in cases:
                case_name = case_data.get("name")
                if not case_name:
                    continue

                yaml_version = str(case_data.get("version", "1.0"))
                existing_case = get_latest(
                    session, EvaluationCase,
                    dataset_id=dataset.id, name=case_name,
                )

                if existing_case is None:
                    # First-time insert
                    save_new_version(
                        session, EvaluationCase,
                        key_filters={"dataset_id": dataset.id, "name": case_name},
                        new_fields={
                            "inputs": case_data.get("inputs", {}),
                            "expected_output": case_data.get("expected_output"),
                            "metadata_": case_data.get("metadata"),
                        },
                        version=yaml_version,
                    )
                    inserted_cases += 1
                else:
                    cmp = compare_versions(yaml_version, existing_case.version)
                    if cmp > 0:
                        # YAML is newer — insert new version
                        save_new_version(
                            session, EvaluationCase,
                            key_filters={"dataset_id": dataset.id, "name": case_name},
                            new_fields={
                                "inputs": case_data.get("inputs", {}),
                                "expected_output": case_data.get("expected_output"),
                                "metadata_": case_data.get("metadata"),
                            },
                            version=yaml_version,
                        )
                        inserted_cases += 1
                    else:
                        logger.warning(
                            "Eval case '%s' in dataset '%s': YAML version %s "
                            "<= DB version %s, skipping",
                            case_name, name, yaml_version, existing_case.version,
                        )

        session.commit()

    if inserted_ds or inserted_cases:
        logger.info(
            "Eval YAML sync: %d dataset(s) inserted, %d case(s) inserted from %d file(s)",
            inserted_ds, inserted_cases, len(yaml_files),
        )


# ---------------------------------------------------------------------------
# Write-back: DB -> YAML (atomic via temp file + rename)
# ---------------------------------------------------------------------------


def write_dataset_to_yaml(engine: "Engine", dataset_id: int, target_dir: Path) -> None:  # noqa: F821
    """Load dataset + cases from DB, serialize to YAML, write atomically."""
    from sqlmodel import Session, select

    with Session(engine) as session:
        dataset = session.exec(
            select(EvaluationDataset).where(EvaluationDataset.id == dataset_id)
        ).first()
        if dataset is None:
            raise ValueError(f"Dataset {dataset_id} not found")

        cases = session.exec(
            select(EvaluationCase)
            .where(
                EvaluationCase.dataset_id == dataset_id,
                EvaluationCase.is_active == True,  # noqa: E712
                EvaluationCase.is_latest == True,  # noqa: E712
            )
            .order_by(EvaluationCase.id)
        ).all()

    doc: dict[str, Any] = {
        "name": dataset.name,
        "target_type": dataset.target_type,
        "target_name": dataset.target_name,
    }
    if dataset.description:
        doc["description"] = dataset.description

    doc["cases"] = []
    for c in cases:
        entry: dict[str, Any] = {
            "name": c.name,
            "version": c.version,
            "inputs": c.inputs,
        }
        if c.expected_output is not None:
            entry["expected_output"] = c.expected_output
        if c.metadata_ is not None:
            entry["metadata"] = c.metadata_
        doc["cases"].append(entry)

    # Atomic write: write to temp, then rename
    target_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = target_dir / f"{dataset.name}.yaml"

    fd, tmp_path = tempfile.mkstemp(
        dir=str(target_dir), suffix=".yaml.tmp", prefix=".eval_"
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
    except Exception:
        # Clean up temp file on failure
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise

    logger.debug("Wrote eval dataset '%s' to %s", dataset.name, yaml_path)


__all__ = ["sync_evals_yaml_to_db", "write_dataset_to_yaml"]
