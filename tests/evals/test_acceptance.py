"""Tests for ``accept_experiment`` — the variant -> production walker.

Covers each accept path in isolation:

- ``model``     -> ``StepModelConfig`` upserted
- ``prompts``   -> Phoenix prompt POST + production tag swap
- ``instructions`` -> source file AST rewrite

Plus the audit row insertion. Phoenix is stubbed via in-memory
fakes mirroring :class:`PhoenixDatasetClient` /
:class:`PhoenixPromptClient`.
"""
from __future__ import annotations

import inspect
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic_graph import End, GraphRunContext
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.db.step_config import StepModelConfig
from llm_pipeline.evals.acceptance import AcceptanceError, accept_experiment
from llm_pipeline.evals.variants import Variant
from llm_pipeline.graph import (
    FromInput,
    LLMResultMixin,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineState,
    StepInputs,
)
from llm_pipeline.state import EvaluationAcceptance


# ---------------------------------------------------------------------------
# A pipeline whose INSTRUCTIONS class lives in a real file (so the AST
# helper has something to read + rewrite). The file is created per-test
# so writes don't pollute the repo.
# ---------------------------------------------------------------------------


_INSTRUCTIONS_SRC = textwrap.dedent("""
    from typing import ClassVar
    from llm_pipeline.graph import LLMResultMixin


    class AcceptInstructions(LLMResultMixin):
        label: str = ""

        example: ClassVar[dict] = {"label": "x", "confidence_score": 0.9}
""").strip() + "\n"


def _make_instructions_module(tmp_path: Path) -> tuple[Path, type]:
    """Write a temp file holding ``AcceptInstructions`` and import it."""
    pkg_dir = tmp_path / "accept_pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    schema_path = pkg_dir / "schema.py"
    schema_path.write_text(_INSTRUCTIONS_SRC, encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    try:
        import importlib

        # Drop any cached version; tests reuse the module name.
        sys.modules.pop("accept_pkg", None)
        sys.modules.pop("accept_pkg.schema", None)
        mod = importlib.import_module("accept_pkg.schema")
        cls = mod.AcceptInstructions
    finally:
        # Leave sys.path alone for the duration of the test; cleanup in fixture.
        pass
    return schema_path, cls


@pytest.fixture
def _accept_pipeline(tmp_path: Path):
    """Build a one-step pipeline with INSTRUCTIONS sourced from a temp file."""
    schema_path, instructions_cls = _make_instructions_module(tmp_path)

    class AcceptInput(PipelineInputData):
        text: str

    class AcceptInputs(StepInputs):
        text: str

    class AcceptStep(LLMStepNode):
        INPUTS = AcceptInputs
        INSTRUCTIONS = instructions_cls
        inputs_spec = AcceptInputs.sources(text=FromInput("text"))

        async def run(
            self, ctx: GraphRunContext[PipelineState, PipelineDeps],
        ) -> End[None]:
            return End(None)

    class AcceptPipeline(Pipeline):
        INPUT_DATA = AcceptInput
        nodes = [AcceptStep]

    yield AcceptPipeline, AcceptStep, schema_path

    # Cleanup: remove the path we prepended in _make_instructions_module
    sys_path_entry = str(tmp_path)
    while sys_path_entry in sys.path:
        sys.path.remove(sys_path_entry)
    for name in list(sys.modules):
        if name.startswith("accept_pkg"):
            sys.modules.pop(name, None)


@pytest.fixture
def _engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(eng)
    SQLModel.metadata.create_all(eng)
    return eng


# ---------------------------------------------------------------------------
# Phoenix stubs
# ---------------------------------------------------------------------------


class _DatasetStub:
    """Minimal facade matching the methods ``acceptance.accept_experiment`` calls."""

    def __init__(self, *, experiment: dict, dataset: dict | None = None):
        self._experiment = experiment
        self._dataset = dataset or {
            "id": experiment.get("dataset_id", "ds-1"),
            "metadata": {},
        }

    def get_experiment(self, experiment_id: str) -> dict:
        return self._experiment

    def get_dataset(self, dataset_id: str) -> dict:
        return self._dataset


class _PromptStub:
    """Records every call so prompt-accept tests can assert end-to-end behaviour."""

    def __init__(self):
        self.versions: dict[str, dict] = {}
        self.created: list[dict] = []
        self.tags_added: list[dict] = []
        self.tags_deleted: list[dict] = []

    def register_version(
        self, *, name: str, version_id: str, system: str, user: str,
    ) -> None:
        self.versions[name] = {
            "id": version_id,
            "name": name,
            "template": {
                "type": "chat",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            "template_format": "F_STRING",
            "model_provider": "OPENAI",
            "model_name": "gpt-4o-mini",
        }

    def get_by_tag(self, name: str, tag: str) -> dict:
        if tag != "production":
            from llm_pipeline.prompts.phoenix_client import PromptNotFoundError
            raise PromptNotFoundError(name)
        if name in self.versions:
            return self.versions[name]
        from llm_pipeline.prompts.phoenix_client import PromptNotFoundError
        raise PromptNotFoundError(name)

    def get_latest(self, name: str) -> dict:
        if name in self.versions:
            return self.versions[name]
        from llm_pipeline.prompts.phoenix_client import PromptNotFoundError
        raise PromptNotFoundError(name)

    def create(self, *, prompt: dict, version: dict) -> dict:
        new_id = f"v-{len(self.created) + 1}"
        record = {
            "id": new_id,
            "name": prompt["name"],
            "template": version.get("template"),
            "template_format": version.get("template_format"),
        }
        self.created.append({"prompt": prompt, "version": version, "id": new_id})
        self.versions[prompt["name"]] = record
        return record

    def add_tag(self, version_id: str, tag_name: str, **kwargs) -> None:
        self.tags_added.append({"version_id": version_id, "tag": tag_name})

    def delete_tag(self, version_id: str, tag_name: str) -> None:
        self.tags_deleted.append({"version_id": version_id, "tag": tag_name})


def _experiment_payload(*, variant: dict) -> dict:
    return {
        "id": "exp-1",
        "dataset_id": "ds-1",
        "metadata": {
            "variant": variant,
            "target_type": "step",
            "target_name": "AcceptStep",
        },
    }


# ---------------------------------------------------------------------------
# Model accept path
# ---------------------------------------------------------------------------


class TestAcceptModel:
    def test_upserts_step_model_config(self, _accept_pipeline, _engine):
        pipeline_cls, _, _ = _accept_pipeline
        variant = {"model": "google-gla:gemini-2.0-flash"}

        row = accept_experiment(
            "exp-1",
            pipeline_registry={pipeline_cls.pipeline_name(): pipeline_cls},
            engine=_engine,
            dataset_client=_DatasetStub(
                experiment=_experiment_payload(variant=variant),
            ),
            prompt_client=_PromptStub(),
        )
        assert row.delta_summary["model"] == "google-gla:gemini-2.0-flash"
        # StepModelConfig row exists.
        with Session(_engine) as session:
            cfg = session.exec(
                select(StepModelConfig).where(
                    StepModelConfig.pipeline_name == pipeline_cls.pipeline_name(),
                    StepModelConfig.step_name == "accept",
                ),
            ).first()
        assert cfg is not None
        assert cfg.model == "google-gla:gemini-2.0-flash"

    def test_overwrites_existing_step_model_config(
        self, _accept_pipeline, _engine,
    ):
        pipeline_cls, _, _ = _accept_pipeline
        # Pre-seed a row.
        with Session(_engine) as session:
            session.add(StepModelConfig(
                pipeline_name=pipeline_cls.pipeline_name(),
                step_name="accept",
                model="old-model",
            ))
            session.commit()

        accept_experiment(
            "exp-1",
            pipeline_registry={pipeline_cls.pipeline_name(): pipeline_cls},
            engine=_engine,
            dataset_client=_DatasetStub(
                experiment=_experiment_payload(variant={"model": "new-model"}),
            ),
            prompt_client=_PromptStub(),
        )
        with Session(_engine) as session:
            cfg = session.exec(
                select(StepModelConfig).where(
                    StepModelConfig.pipeline_name == pipeline_cls.pipeline_name(),
                ),
            ).first()
        assert cfg.model == "new-model"


# ---------------------------------------------------------------------------
# Prompt accept path
# ---------------------------------------------------------------------------


class TestAcceptPrompt:
    def test_creates_new_phoenix_version_and_swaps_tag(
        self, _accept_pipeline, _engine,
    ):
        pipeline_cls, step_cls, _ = _accept_pipeline
        prompt_name = step_cls.resolved_prompt_name()

        prompt_stub = _PromptStub()
        prompt_stub.register_version(
            name=prompt_name,
            version_id="v-prior",
            system="System.",
            user="OLD: {text}",
        )

        accept_experiment(
            "exp-1",
            pipeline_registry={pipeline_cls.pipeline_name(): pipeline_cls},
            engine=_engine,
            dataset_client=_DatasetStub(
                experiment=_experiment_payload(
                    variant={"prompt_overrides": {step_cls.step_name(): "NEW: {text}"}},
                ),
            ),
            prompt_client=prompt_stub,
        )

        # New version POSTed; user message reflects the override; system preserved.
        assert len(prompt_stub.created) == 1
        new = prompt_stub.created[0]
        msgs = new["version"]["template"]["messages"]
        roles = {m["role"]: m["content"] for m in msgs}
        assert roles["system"] == "System."
        assert roles["user"] == "NEW: {text}"

        # New version tagged production; old demoted.
        assert any(t["tag"] == "production" for t in prompt_stub.tags_added)
        assert any(
            t["tag"] == "production" and t["version_id"] == "v-prior"
            for t in prompt_stub.tags_deleted
        )


# ---------------------------------------------------------------------------
# Instructions accept path
# ---------------------------------------------------------------------------


class TestAcceptInstructions:
    def test_rewrites_source_file(
        self, _accept_pipeline, _engine,
    ):
        pipeline_cls, step_cls, schema_path = _accept_pipeline

        accept_experiment(
            "exp-1",
            pipeline_registry={pipeline_cls.pipeline_name(): pipeline_cls},
            engine=_engine,
            dataset_client=_DatasetStub(
                experiment=_experiment_payload(
                    variant={
                        "instructions_delta": [
                            {
                                "op": "add",
                                "field": "intensity",
                                "type_str": "float",
                                "default": 0.5,
                            },
                        ],
                    },
                ),
            ),
            prompt_client=_PromptStub(),
        )

        text = schema_path.read_text()
        assert "intensity: float = 0.5" in text
        # Backup written.
        assert schema_path.with_suffix(".py.bak").exists()


# ---------------------------------------------------------------------------
# Audit row + multi-surface accept
# ---------------------------------------------------------------------------


class TestAcceptanceAudit:
    def test_records_evaluation_acceptance_row(
        self, _accept_pipeline, _engine,
    ):
        pipeline_cls, step_cls, _ = _accept_pipeline
        row = accept_experiment(
            "exp-1",
            pipeline_registry={pipeline_cls.pipeline_name(): pipeline_cls},
            engine=_engine,
            dataset_client=_DatasetStub(
                experiment=_experiment_payload(
                    variant={"model": "m"},
                ),
            ),
            prompt_client=_PromptStub(),
            accepted_by="alice",
            notes="ship it",
        )
        assert row.experiment_id == "exp-1"
        assert row.accepted_by == "alice"
        assert row.notes == "ship it"
        # accept_paths records what changed.
        assert "model" in row.accept_paths

    def test_three_surfaces_in_one_call(
        self, _accept_pipeline, _engine,
    ):
        pipeline_cls, step_cls, schema_path = _accept_pipeline
        prompt_stub = _PromptStub()
        prompt_stub.register_version(
            name=step_cls.resolved_prompt_name(),
            version_id="v-prior",
            system="Sys.",
            user="OLD: {text}",
        )

        row = accept_experiment(
            "exp-1",
            pipeline_registry={pipeline_cls.pipeline_name(): pipeline_cls},
            engine=_engine,
            dataset_client=_DatasetStub(
                experiment=_experiment_payload(
                    variant={
                        "model": "m-x",
                        "prompt_overrides": {
                            step_cls.step_name(): "NEW: {text}",
                        },
                        "instructions_delta": [
                            {
                                "op": "add",
                                "field": "extra",
                                "type_str": "str",
                                "default": "x",
                            },
                        ],
                    },
                ),
            ),
            prompt_client=prompt_stub,
        )
        assert "model" in row.accept_paths
        assert "prompts" in row.accept_paths
        assert "instructions" in row.accept_paths


# ---------------------------------------------------------------------------
# Failure surface
# ---------------------------------------------------------------------------


class TestAcceptanceFailures:
    def test_pipeline_target_with_instructions_delta_rejected(
        self, _accept_pipeline, _engine,
    ):
        pipeline_cls, _, _ = _accept_pipeline
        experiment = {
            "id": "exp-pipe",
            "dataset_id": "ds-pipe",
            "metadata": {
                "variant": {
                    "instructions_delta": [
                        {
                            "op": "add",
                            "field": "x",
                            "type_str": "str",
                            "default": "y",
                        },
                    ],
                },
                "target_type": "pipeline",
                "target_name": pipeline_cls.__name__,
            },
        }
        with pytest.raises(AcceptanceError, match="instructions_delta"):
            accept_experiment(
                "exp-pipe",
                pipeline_registry={pipeline_cls.__name__: pipeline_cls},
                engine=_engine,
                dataset_client=_DatasetStub(experiment=experiment),
                prompt_client=_PromptStub(),
            )

    def test_unknown_step_target_raises(self, _accept_pipeline, _engine):
        pipeline_cls, _, _ = _accept_pipeline
        experiment = {
            "id": "exp-x",
            "dataset_id": "ds-x",
            "metadata": {
                "variant": {"model": "m"},
                "target_type": "step",
                "target_name": "MissingStep",
            },
        }
        with pytest.raises(AcceptanceError, match="not found"):
            accept_experiment(
                "exp-x",
                pipeline_registry={pipeline_cls.pipeline_name(): pipeline_cls},
                engine=_engine,
                dataset_client=_DatasetStub(experiment=experiment),
                prompt_client=_PromptStub(),
            )
