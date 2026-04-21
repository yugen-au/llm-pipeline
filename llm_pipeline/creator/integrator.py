"""
StepIntegrator -- one-shot file + DB writer for generated pipeline steps.

Accepts a GeneratedStep adapter model, writes generated Python files to a
target directory, registers prompts in the DB via idempotent check-then-insert,
AST-splices the target pipeline file, updates DraftStep status, and commits.
On any failure: deletes written files, restores .bak backups, rolls back the
DB session, and re-raises.
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from llm_pipeline.creator import ast_modifier
from llm_pipeline.creator.models import GeneratedStep, IntegrationResult
from llm_pipeline.creator.sandbox import CodeSecurityValidator
from llm_pipeline.db.prompt import Prompt

if TYPE_CHECKING:
    from sqlmodel import Session

    from llm_pipeline.state import DraftStep

logger = logging.getLogger(__name__)


class StepIntegrator:
    """Orchestrates integration of a GeneratedStep into a pipeline project.

    Phases (all-or-nothing):
        1. Dir setup (mkdir + __init__.py)
        2. File writes (all artifacts from GeneratedStep)
        3. Prompt DB registration (AST security scan + controlled exec)
        4. AST modifications via ast_modifier.modify_pipeline_file()
        5. DraftStep status update to "accepted"
        6. Session commit
        7. Full rollback on any failure
    """

    def __init__(
        self,
        session: Session,
        pipeline_file: Path | None = None,
    ) -> None:
        """
        Args:
            session: Writable SQLModel Session from caller. Integrator owns
                     commit/rollback -- caller must NOT commit.
            pipeline_file: Target pipeline.py for AST modifications.
                           If None, AST step is skipped.
        """
        self.session = session
        self.pipeline_file = pipeline_file

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def integrate(
        self,
        generated: GeneratedStep,
        target_dir: Path,
        draft: DraftStep | None = None,
    ) -> IntegrationResult:
        """Write files, register prompts, AST-modify pipeline, commit.

        Returns IntegrationResult on success. On any failure: rolls back
        DB, deletes written files, restores .bak, and re-raises.
        """
        files_written: list[str] = []
        newly_created_dir = False
        ast_started = False

        try:
            # Phase 1 -- Dir setup
            newly_created_dir = self._ensure_target_dir(target_dir)

            # Phase 2 -- File writes
            files_written = self._write_files(generated, target_dir)

            # Phase 3 -- Prompt DB registration
            prompts_registered = self._register_prompts(generated)

            # Phase 4 -- AST modifications
            pipeline_updated = False
            if self.pipeline_file is not None:
                ast_started = True
                self._apply_ast_modifications(generated, target_dir)
                pipeline_updated = True

            # Phase 5 -- DraftStep status update
            if draft is not None:
                from llm_pipeline.state import utc_now

                draft.status = "accepted"
                draft.updated_at = utc_now()
                self.session.add(draft)

            # Phase 6 -- Commit
            self.session.commit()

        except Exception:
            self._rollback_files(files_written, target_dir, newly_created_dir)
            if ast_started and self.pipeline_file is not None:
                self._restore_pipeline_bak()
            self.session.rollback()
            raise

        return IntegrationResult(
            files_written=files_written,
            prompts_registered=prompts_registered,
            pipeline_file_updated=pipeline_updated,
            target_dir=str(target_dir),
        )

    # ------------------------------------------------------------------
    # Phase 1 -- Directory setup
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_target_dir(target_dir: Path) -> bool:
        """Create target_dir and __init__.py if missing. Returns True if newly created."""
        newly_created = not target_dir.exists()
        target_dir.mkdir(parents=True, exist_ok=True)

        init_file = target_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("", encoding="utf-8")

        return newly_created

    # ------------------------------------------------------------------
    # Phase 2 -- File writes
    # ------------------------------------------------------------------

    @staticmethod
    def _write_files(generated: GeneratedStep, target_dir: Path) -> list[str]:
        """Write all artifacts to target_dir. Returns list of absolute paths."""
        written: list[str] = []
        for filename, content in generated.all_artifacts.items():
            filepath = target_dir / filename
            filepath.write_text(content, encoding="utf-8")
            written.append(str(filepath.resolve()))
        return written

    # ------------------------------------------------------------------
    # Phase 3 -- Prompt registration
    # ------------------------------------------------------------------

    def _register_prompts(self, generated: GeneratedStep) -> int:
        """AST-scan prompts_code, extract ALL_PROMPTS, idempotent insert.

        Falls back to _reconstruct_prompts if security scan fails or
        exec raises.
        """
        validator = CodeSecurityValidator()
        issues = validator.validate(generated.prompts_code)

        if issues:
            logger.warning(
                "Security issues in prompts_code for %s, using fallback: %s",
                generated.step_name,
                issues,
            )
            prompt_list = self._reconstruct_prompts(generated)
            return self._insert_prompts(prompt_list)

        # Controlled exec with restricted builtins
        namespace: dict = {"__builtins__": {}}
        try:
            exec(generated.prompts_code, namespace)  # noqa: S102
        except Exception as exc:
            logger.warning(
                "exec failed for prompts_code of %s (%s), using fallback",
                generated.step_name,
                exc,
            )
            prompt_list = self._reconstruct_prompts(generated)
            return self._insert_prompts(prompt_list)

        all_prompts = namespace.get("ALL_PROMPTS")
        if not isinstance(all_prompts, list):
            logger.warning(
                "ALL_PROMPTS not found or not a list for %s, using fallback",
                generated.step_name,
            )
            prompt_list = self._reconstruct_prompts(generated)
            return self._insert_prompts(prompt_list)

        return self._insert_prompts(all_prompts)

    def _insert_prompts(self, prompt_list: list[dict]) -> int:
        """Idempotent insert via save_new_version: skip if latest already exists."""
        from llm_pipeline.db.versioning import get_latest, save_new_version

        inserted = 0
        for prompt_data in prompt_list:
            key = prompt_data.get("prompt_key", "")
            ptype = prompt_data.get("prompt_type", "")
            key_filters = {"prompt_key": key, "prompt_type": ptype}

            existing = get_latest(self.session, Prompt, **key_filters)
            if existing is None:
                new_fields = {
                    k: v for k, v in prompt_data.items()
                    if k not in ("prompt_key", "prompt_type", "version",
                                 "is_active", "is_latest", "created_at", "updated_at")
                }
                save_new_version(
                    self.session, Prompt, key_filters, new_fields,
                    version=prompt_data.get("version", "1.0"),
                )
                inserted += 1
        return inserted

    @staticmethod
    def _reconstruct_prompts(generated: GeneratedStep) -> list[dict]:
        """Build minimal system + user prompt dicts from step metadata.

        Used as fallback when exec-based extraction fails. Extracts
        content from prompts_code via basic string matching if possible,
        otherwise uses placeholder content.
        """
        name = generated.step_name
        category = name

        # Attempt to extract content blocks from prompts_code
        system_content = _extract_prompt_content(
            generated.prompts_code, f"{name.upper()}_SYSTEM", "system"
        )
        user_content = _extract_prompt_content(
            generated.prompts_code, f"{name.upper()}_USER", "user"
        )

        prompts: list[dict] = [
            {
                "prompt_key": name,
                "prompt_name": f"{generated.step_class_name} System",
                "prompt_type": "system",
                "category": category,
                "step_name": name,
                "content": system_content or f"System prompt for {name} step.",
                "required_variables": [],
                "description": f"System prompt for {name} step",
            },
            {
                "prompt_key": name,
                "prompt_name": f"{generated.step_class_name} User",
                "prompt_type": "user",
                "category": category,
                "step_name": name,
                "content": user_content or f"User prompt for {name} step.",
                "required_variables": [],
                "description": f"User prompt for {name} step",
            },
        ]
        return prompts

    # ------------------------------------------------------------------
    # Phase 4 -- AST modifications
    # ------------------------------------------------------------------

    def _apply_ast_modifications(
        self,
        generated: GeneratedStep,
        target_dir: Path,
    ) -> None:
        """Derive module paths and call ast_modifier.modify_pipeline_file."""
        # Derive dotted module path from target_dir relative to project root.
        # e.g. /project/llm_pipeline/steps/sentiment -> llm_pipeline.steps.sentiment
        step_module = _dir_to_module_path(target_dir, generated.step_name + "_step")

        extraction_model: str | None = None
        extraction_module: str | None = None
        if generated.extraction_code is not None:
            extraction_model = _derive_extraction_model_name(generated)
            extraction_module = _dir_to_module_path(
                target_dir, generated.step_name + "_extraction"
            )

        ast_modifier.modify_pipeline_file(
            pipeline_file=self.pipeline_file,
            step_class=generated.step_class_name,
            step_module=step_module,
            step_name=generated.step_name,
            extraction_model=extraction_model,
            extraction_module=extraction_module,
        )

    # ------------------------------------------------------------------
    # Rollback helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rollback_files(
        files_written: list[str],
        target_dir: Path,
        newly_created: bool,
    ) -> None:
        """Delete written files. If dir was newly created, remove entirely."""
        for fpath in files_written:
            try:
                Path(fpath).unlink(missing_ok=True)
            except OSError:
                pass

        if newly_created and target_dir.exists():
            shutil.rmtree(str(target_dir), ignore_errors=True)

    def _restore_pipeline_bak(self) -> None:
        """Restore pipeline file from .bak if it exists."""
        if self.pipeline_file is None:
            return
        bak_path = self.pipeline_file.with_suffix(".py.bak")
        if bak_path.exists():
            try:
                bak_content = bak_path.read_text(encoding="utf-8")
                self.pipeline_file.write_text(bak_content, encoding="utf-8")
            except OSError:
                pass  # best effort


# ---------------------------------------------------------------------------
# Module-level utilities
# ---------------------------------------------------------------------------


def _dir_to_module_path(target_dir: Path, module_name: str) -> str:
    """Convert a directory path + module name to a dotted import path.

    Walks up from target_dir looking for the first directory that does NOT
    contain __init__.py (i.e. the project root or site-packages boundary).
    Falls back to using 'llm_pipeline' as the root package name.

    e.g. /project/llm_pipeline/steps/sentiment + "sentiment_step"
         -> "llm_pipeline.steps.sentiment.sentiment_step"
    """
    parts: list[str] = [module_name]
    current = target_dir.resolve()

    while True:
        parts.insert(0, current.name)
        parent = current.parent
        if parent == current:
            break  # filesystem root
        init_file = parent / "__init__.py"
        if not init_file.exists():
            break
        current = parent

    return ".".join(parts)


def _derive_extraction_model_name(generated: GeneratedStep) -> str:
    """Derive the extraction SQLModel class name from extraction_code.

    Scans for `class <Name>(SQLModel` or `class <Name>(PipelineExtraction` pattern.
    Falls back to PascalCase(step_name) + "Extraction".
    """
    if generated.extraction_code:
        match = re.search(
            r"class\s+(\w+)\s*\(",
            generated.extraction_code,
        )
        if match:
            return match.group(1)
    from llm_pipeline.creator.models import _to_pascal_case

    return f"{_to_pascal_case(generated.step_name)}Extraction"


def _extract_prompt_content(
    prompts_code: str,
    var_name: str,
    prompt_type: str,
) -> str | None:
    """Best-effort extraction of a prompt content string from source code.

    Looks for patterns like:
        VAR_NAME: dict = { ... "content": ("...", "..."), ... }
    or
        VAR_NAME: dict = { ... "content": "...", ... }

    Returns the content string or None if not found.
    """
    # Pattern: "content": (\n "..."\n) or "content": "..."
    # Search near the variable name section
    idx = prompts_code.find(var_name)
    if idx == -1:
        return None

    # Get the section after the variable name (up to next top-level variable or end)
    section = prompts_code[idx:]
    # Look for "content" key
    content_match = re.search(
        r'"content"\s*:\s*\(\s*([\s\S]*?)\s*\)',
        section,
    )
    if content_match:
        # Multi-line parenthesized string
        raw = content_match.group(1)
        # Join string literals
        parts = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
        if parts:
            return "".join(parts)

    # Single string
    content_match = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', section)
    if content_match:
        return content_match.group(1)

    return None


__all__ = ["StepIntegrator"]
