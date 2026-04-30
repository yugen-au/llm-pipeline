"""Tests for ``llm_pipeline.yaml_sync``.

Covers the small, load-bearing pieces:

- Hash determinism + Phoenix-set field exclusion
- YAML write idempotency (second-write skip)
- Prompt sync push / skip
- Dataset sync create / example-diff add+delete / metadata-only skip-with-warn
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel, Field
from pydantic_graph import End, GraphRunContext

from llm_pipeline.evals.models import Dataset, Example
from llm_pipeline.evals.phoenix_client import PhoenixDatasetError
from llm_pipeline.graph.nodes import LLMStepNode
from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.inputs import StepInputs
from llm_pipeline.prompts.models import Prompt, PromptMessage, PromptMetadata
from llm_pipeline.prompts.phoenix_client import (
    PhoenixError,
    PromptNotFoundError,
)
from llm_pipeline.prompts.variables import PromptVariables
from llm_pipeline.wiring import FromInput, Step
from llm_pipeline.yaml_sync import (
    SyncReport,
    _diff_examples,
    _hash_dataset,
    _hash_prompt,
    _hash_prompt_yaml,
    pull_phoenix_to_yaml,
    startup_sync,
    write_dataset_yaml,
    write_prompt_yaml,
)


# ---------------------------------------------------------------------------
# Fixtures + fakes
# ---------------------------------------------------------------------------


def _make_prompt(name: str, *, system: str, user: str) -> Prompt:
    return Prompt(
        name=name,
        description=None,
        metadata=PromptMetadata(category="test"),
        messages=[
            PromptMessage(role="system", content=system),
            PromptMessage(role="user", content=user),
        ],
    )


def _make_dataset(
    name: str,
    *,
    target_name: str = "Step",
    inputs: list[dict[str, Any]] | None = None,
    description: str | None = None,
) -> Dataset:
    return Dataset(
        name=name,
        description=description,
        metadata={"target_type": "step", "target_name": target_name},
        examples=[
            Example(input=ip, output={}, metadata={})
            for ip in (inputs or [{"q": "hi"}])
        ],
    )


class _FakePromptClient:
    """Minimal PhoenixPromptClient surface used by yaml_sync."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.versions: dict[str, list[dict[str, Any]]] = {}
        self.tags: list[tuple[str, str]] = []
        self._next = 0

    def seed(self, prompt: Prompt) -> None:
        record = {
            "name": prompt.name,
            "metadata": prompt.metadata.model_dump(exclude_none=True),
        }
        if prompt.description is not None:
            record["description"] = prompt.description
        self.records[prompt.name] = record
        messages = [{"role": m.role, "content": m.content} for m in prompt.messages]
        version = self._make_version(messages, model=prompt.model)
        if prompt.response_format is not None:
            version["response_format"] = prompt.response_format
        if prompt.tools is not None:
            version["tools"] = prompt.tools
        self.versions.setdefault(prompt.name, []).append(version)

    def _make_version(
        self, messages: list[dict[str, str]], *, model: str | None = None,
    ) -> dict[str, Any]:
        from llm_pipeline.prompts.models import pai_model_to_phoenix

        self._next += 1
        version: dict[str, Any] = {
            "id": f"v_{self._next:03d}",
            "template": {"type": "chat", "messages": messages},
            "template_type": "CHAT",
            "template_format": "F_STRING",
            "invocation_parameters": {"type": "openai", "openai": {}},
        }
        if model:
            provider, name = pai_model_to_phoenix(model)
            version["model_provider"] = provider
            version["model_name"] = name
        return version

    # ---- PhoenixPromptClient surface ----

    def list_prompts(self, *, limit: int = 100, cursor: Any | None = None):
        del limit, cursor
        return {"data": list(self.records.values()), "next_cursor": None}

    def get_latest(self, name: str) -> dict[str, Any]:
        if name not in self.versions or not self.versions[name]:
            raise PromptNotFoundError(name)
        return self.versions[name][-1]

    def create(self, *, prompt: dict[str, Any], version: dict[str, Any]):
        name = prompt["name"]
        if name not in self.records:
            self.records[name] = {
                "name": name,
                "metadata": prompt.get("metadata") or {},
            }
            if "description" in prompt:
                self.records[name]["description"] = prompt["description"]
        new_v = self._make_version(version["template"]["messages"])
        # Carry over the optional version fields so tests can assert
        # what the route/yaml_sync sent through.
        for k in (
            "description", "response_format", "tools",
            "model_provider", "model_name",
        ):
            if k in version:
                new_v[k] = version[k]
        self.versions.setdefault(name, []).append(new_v)
        return new_v

    def add_tag(self, version_id: str, tag: str, *, description: str | None = None):
        del description
        self.tags.append((version_id, tag))


class _FakeDatasetClient:
    """Minimal PhoenixDatasetClient surface used by yaml_sync."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}  # id -> record
        self.examples: dict[str, list[dict[str, Any]]] = {}  # id -> [example]
        self._next = 0

    def seed(self, dataset: Dataset, *, dataset_id: str | None = None) -> str:
        new_id = dataset_id or self._next_id()
        self.records[new_id] = {
            "id": new_id,
            "name": dataset.name,
            "description": dataset.description,
            "metadata": dataset.metadata.model_dump(exclude_none=True),
        }
        self.examples[new_id] = []
        for ex in dataset.examples:
            self.examples[new_id].append({
                "id": self._next_id(),
                "input": ex.input,
                "output": ex.output,
                "metadata": ex.metadata,
            })
        return new_id

    def _next_id(self) -> str:
        self._next += 1
        return f"id_{self._next:03d}"

    # ---- PhoenixDatasetClient surface ----

    def list_datasets(self, *, limit: int = 100, cursor: Any | None = None):
        del limit, cursor
        return {"data": list(self.records.values()), "next_cursor": None}

    def list_examples(self, dataset_id: str, *, version_id: Any | None = None):
        del version_id
        return {"data": {"examples": list(self.examples.get(dataset_id, []))}}

    def upload_dataset(
        self, *, name, examples, description=None, metadata=None, action="create",
    ):
        del action
        new_id = self._next_id()
        self.records[new_id] = {
            "id": new_id,
            "name": name,
            "description": description,
            "metadata": metadata or {},
        }
        self.examples[new_id] = []
        for ex in examples:
            self.examples[new_id].append({
                "id": self._next_id(),
                "input": ex.get("input", {}),
                "output": ex.get("output", {}),
                "metadata": ex.get("metadata", {}),
            })
        return self.records[new_id]

    def add_examples(self, dataset_id: str, examples: list[dict[str, Any]]):
        for ex in examples:
            self.examples.setdefault(dataset_id, []).append({
                "id": self._next_id(),
                "input": ex.get("input", {}),
                "output": ex.get("output", {}),
                "metadata": ex.get("metadata", {}),
            })
        return {}

    def delete_example(self, dataset_id: str, example_id: str) -> None:
        items = self.examples.get(dataset_id, [])
        self.examples[dataset_id] = [e for e in items if e.get("id") != example_id]

    def patch_dataset(self, dataset_id, *, name=None, description=None, metadata=None):
        rec = self.records.get(dataset_id)
        if rec is None:
            return {}
        if name is not None:
            rec["name"] = name
        if description is not None:
            rec["description"] = description
        if metadata is not None:
            rec["metadata"] = metadata
        return rec


# ---------------------------------------------------------------------------
# Hash + write idempotency
# ---------------------------------------------------------------------------


class TestHashes:
    def test_same_prompt_hashes_equal(self):
        a = _make_prompt("p", system="s", user="u")
        b = _make_prompt("p", system="s", user="u")
        assert _hash_prompt(a) == _hash_prompt(b)

    def test_phoenix_set_fields_excluded_from_hash(self):
        a = _make_prompt("p", system="s", user="u")
        b = a.model_copy(update={"version_id": "v_abc"})
        assert _hash_prompt(a) == _hash_prompt(b)

    def test_dataset_phoenix_fields_excluded(self):
        a = _make_dataset("d", inputs=[{"q": "hi"}])
        b = a.model_copy(update={"id": "id_1", "created_at": "2025-01-01", "example_count": 1})
        # per-example id changes also excluded
        b = b.model_copy(update={
            "examples": [Example(id="ex_1", input={"q": "hi"}, output={}, metadata={})],
        })
        assert _hash_dataset(a) == _hash_dataset(b)


class TestWriteIdempotency:
    def test_second_write_skips(self, tmp_path: Path):
        p = _make_prompt("foo", system="s", user="u")
        assert write_prompt_yaml(p, tmp_path) is True
        assert write_prompt_yaml(p, tmp_path) is False

    def test_changed_content_rewrites(self, tmp_path: Path):
        p1 = _make_prompt("foo", system="s", user="u")
        p2 = _make_prompt("foo", system="s2", user="u")
        write_prompt_yaml(p1, tmp_path)
        assert write_prompt_yaml(p2, tmp_path) is True

    def test_yaml_round_trips(self, tmp_path: Path):
        p = _make_prompt("foo", system="s", user="u")
        write_prompt_yaml(p, tmp_path)
        loaded = Prompt.model_validate(
            yaml.safe_load((tmp_path / "foo.yaml").read_text()),
        )
        assert _hash_prompt(loaded) == _hash_prompt(p)


# ---------------------------------------------------------------------------
# Example-diff
# ---------------------------------------------------------------------------


class TestExampleDiff:
    def test_add_when_in_yaml_only(self):
        yaml_exs = [Example(input={"q": "a"}, output={}, metadata={})]
        phoenix_exs: list[Example] = []
        to_add, to_delete = _diff_examples(yaml_exs, phoenix_exs)
        assert len(to_add) == 1 and to_add[0].input == {"q": "a"}
        assert to_delete == []

    def test_delete_when_in_phoenix_only(self):
        yaml_exs: list[Example] = []
        phoenix_exs = [Example(id="ex_1", input={"q": "a"}, output={}, metadata={})]
        to_add, to_delete = _diff_examples(yaml_exs, phoenix_exs)
        assert to_add == []
        assert to_delete == ["ex_1"]

    def test_skip_when_both_match_by_input(self):
        yaml_exs = [Example(input={"q": "a"}, output={"label": "x"}, metadata={})]
        phoenix_exs = [
            Example(id="ex_1", input={"q": "a"}, output={"label": "y"}, metadata={}),
        ]
        # match is by input only — output drift is not a diff
        to_add, to_delete = _diff_examples(yaml_exs, phoenix_exs)
        assert to_add == []
        assert to_delete == []


# ---------------------------------------------------------------------------
# Prompt sync
# ---------------------------------------------------------------------------


class TestPromptSync:
    def test_pushes_when_phoenix_absent(self, tmp_path: Path):
        client = _FakePromptClient()
        write_prompt_yaml(
            _make_prompt("hello", system="s", user="u"), tmp_path,
        )
        report = startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=client, dataset_client=None,
            introspection_registry=_registry_with("HelloStep"),
        )
        assert report.prompts_pushed == ["hello"]
        assert "hello" in client.records
        # tagged production
        assert any(t == "production" for _, t in client.tags)

    def test_skips_when_hash_matches(self, tmp_path: Path):
        # Build a Prompt + Phoenix copy that match including the
        # step-derived response_format / tools.
        client = _FakePromptClient()
        registry = _registry_with("SameStep")
        write_prompt_yaml(_make_prompt("same", system="s", user="u"), tmp_path)
        # Seed Phoenix with the same content the sync will compute.
        from llm_pipeline.prompts.registration import derive_step_extras
        rf, tools = derive_step_extras(registry["test_pipeline"].nodes[0].cls)
        client.seed(
            _make_prompt("same", system="s", user="u").model_copy(update={
                "response_format": rf, "tools": tools,
            }),
        )
        report = startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=client, dataset_client=None,
            introspection_registry=registry,
        )
        assert report.prompts_skipped == ["same"]
        assert report.prompts_pushed == []

    def test_pushes_when_messages_differ(self, tmp_path: Path):
        client = _FakePromptClient()
        client.seed(_make_prompt("drifted", system="OLD", user="u"))
        write_prompt_yaml(
            _make_prompt("drifted", system="NEW", user="u"), tmp_path,
        )
        report = startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=client, dataset_client=None,
            introspection_registry=_registry_with("DriftedStep"),
        )
        assert report.prompts_pushed == ["drifted"]
        # Latest version contains NEW system message
        latest = client.get_latest("drifted")
        sys_msg = next(
            m for m in latest["template"]["messages"] if m["role"] == "system"
        )
        assert sys_msg["content"] == "NEW"

    def test_step_without_yaml_skipped(self, tmp_path: Path):
        """Steps registered without a matching YAML file aren't synced."""
        client = _FakePromptClient()
        report = startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=client, dataset_client=None,
            introspection_registry=_registry_with("OrphanStep"),
        )
        assert report.prompts_pushed == []
        assert report.prompts_skipped == []
        assert report.prompts_failed == []
        assert "orphan" not in client.records

    def test_orphan_yaml_without_step_skipped(self, tmp_path: Path):
        """YAML files without a registered step don't sync to Phoenix."""
        write_prompt_yaml(
            _make_prompt("orphan", system="s", user="u"), tmp_path,
        )
        client = _FakePromptClient()
        report = startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=client, dataset_client=None,
            introspection_registry={},
        )
        assert report.prompts_pushed == []
        assert "orphan" not in client.records


# ---------------------------------------------------------------------------
# Pull direction (Phoenix -> YAML), step-driven
# ---------------------------------------------------------------------------


class TestPromptPull:
    def test_pulls_when_phoenix_has_prompt_no_yaml(self, tmp_path: Path):
        """First-time pull: Phoenix has the prompt; YAML doesn't exist yet."""
        client = _FakePromptClient()
        client.seed(_make_prompt("hello", system="S", user="U"))
        registry = _registry_with("HelloStep")

        report = pull_phoenix_to_yaml(
            prompts_dir=tmp_path,
            prompt_client=client,
            introspection_registry=registry,
        )
        assert report.prompts_pulled == ["hello"]
        # YAML file written on disk
        assert (tmp_path / "hello.yaml").exists()

    def test_pulls_when_phoenix_diverged_from_yaml(self, tmp_path: Path):
        """Phoenix has changes YAML doesn't — pull overwrites YAML."""
        # Existing YAML reflects old content
        write_prompt_yaml(
            _make_prompt("drifted", system="OLD", user="u"), tmp_path,
        )
        # Phoenix has newer content (e.g. someone edited via Playground)
        client = _FakePromptClient()
        client.seed(_make_prompt("drifted", system="NEW", user="u"))
        registry = _registry_with("DriftedStep")

        report = pull_phoenix_to_yaml(
            prompts_dir=tmp_path,
            prompt_client=client,
            introspection_registry=registry,
        )
        assert report.prompts_pulled == ["drifted"]
        # YAML now reflects Phoenix's NEW system message
        loaded = Prompt.model_validate(
            yaml.safe_load((tmp_path / "drifted.yaml").read_text()),
        )
        sys_msg = next(m for m in loaded.messages if m.role == "system")
        assert sys_msg.content == "NEW"

    def test_skips_when_yaml_already_matches_phoenix(self, tmp_path: Path):
        """Idempotent pull: matching content → no write, no mtime bump."""
        prompt = _make_prompt("aligned", system="s", user="u")
        write_prompt_yaml(prompt, tmp_path)
        original_mtime = (tmp_path / "aligned.yaml").stat().st_mtime_ns
        client = _FakePromptClient()
        client.seed(prompt)
        registry = _registry_with("AlignedStep")

        report = pull_phoenix_to_yaml(
            prompts_dir=tmp_path,
            prompt_client=client,
            introspection_registry=registry,
        )
        assert report.prompts_pulled == []
        assert report.prompts_pull_skipped == ["aligned"]
        # mtime unchanged — write_prompt_yaml's hash check held
        assert (tmp_path / "aligned.yaml").stat().st_mtime_ns == original_mtime

    def test_skips_when_phoenix_has_no_prompt(self, tmp_path: Path):
        """Step exists but Phoenix has nothing — leave YAML alone for bootstrap path."""
        client = _FakePromptClient()  # no seed; Phoenix is empty
        registry = _registry_with("NewStep")

        report = pull_phoenix_to_yaml(
            prompts_dir=tmp_path,
            prompt_client=client,
            introspection_registry=registry,
        )
        assert report.prompts_pulled == []
        assert report.prompts_pull_skipped == ["new"]
        assert not (tmp_path / "new.yaml").exists()

    def test_step_driven_phoenix_orphans_ignored(self, tmp_path: Path):
        """Phoenix prompts without a matching step are ignored entirely."""
        client = _FakePromptClient()
        # Phoenix has prompts the framework doesn't know about
        client.seed(_make_prompt("phoenix_only", system="s", user="u"))
        client.seed(_make_prompt("another_orphan", system="s", user="u"))
        # Empty registry: no steps
        registry: dict = {}

        report = pull_phoenix_to_yaml(
            prompts_dir=tmp_path,
            prompt_client=client,
            introspection_registry=registry,
        )
        # Nothing pulled — no step references these prompts
        assert report.prompts_pulled == []
        assert report.prompts_pull_skipped == []
        # No YAML files written for the orphans
        assert not (tmp_path / "phoenix_only.yaml").exists()
        assert not (tmp_path / "another_orphan.yaml").exists()

    def test_phoenix_transport_failure_recorded(self, tmp_path: Path):
        """Phoenix lookup failures bucket into prompts_pull_failed."""
        registry = _registry_with("BoomStep")

        class _ExplodingClient(_FakePromptClient):
            def get_latest(self, name):
                raise PhoenixError("simulated outage")

        report = pull_phoenix_to_yaml(
            prompts_dir=tmp_path,
            prompt_client=_ExplodingClient(),
            introspection_registry=registry,
        )
        assert report.prompts_pulled == []
        assert len(report.prompts_pull_failed) == 1
        assert report.prompts_pull_failed[0][0] == "boom"
        assert "phoenix" in report.prompts_pull_failed[0][1]

    def test_step_seen_only_once_when_shared_across_pipelines(
        self, tmp_path: Path,
    ):
        """Same step referenced by multiple pipelines is deduped."""
        prompt = _make_prompt("shared", system="s", user="u")
        client = _FakePromptClient()
        client.seed(prompt)

        # Two pipelines that share the same SharedStep class.
        PipelineCls, _ = _make_test_pipeline("SharedStep")
        registry = {"p1": PipelineCls, "p2": PipelineCls}

        report = pull_phoenix_to_yaml(
            prompts_dir=tmp_path,
            prompt_client=client,
            introspection_registry=registry,
        )
        # Pulled exactly once, not duplicated.
        assert report.prompts_pulled == ["shared"]


# ---------------------------------------------------------------------------
# Dataset sync
# ---------------------------------------------------------------------------


class TestDatasetSync:
    def test_creates_when_phoenix_absent(self, tmp_path: Path):
        client = _FakeDatasetClient()
        write_dataset_yaml(
            _make_dataset("d1", inputs=[{"q": "a"}, {"q": "b"}]), tmp_path,
        )
        report = startup_sync(
            prompts_dir=None, datasets_dir=tmp_path,
            prompt_client=None, dataset_client=client,
        )
        assert report.datasets_created == ["d1"]
        assert any(r["name"] == "d1" for r in client.records.values())

    def test_diffs_examples_add_and_delete(self, tmp_path: Path):
        client = _FakeDatasetClient()
        seeded_id = client.seed(
            _make_dataset("d2", inputs=[{"q": "keep"}, {"q": "drop"}]),
        )
        # YAML keeps "keep" and adds "new"; "drop" should be deleted
        write_dataset_yaml(
            _make_dataset("d2", inputs=[{"q": "keep"}, {"q": "new"}]), tmp_path,
        )
        report = startup_sync(
            prompts_dir=None, datasets_dir=tmp_path,
            prompt_client=None, dataset_client=client,
        )
        assert report.datasets_diffed == ["d2"]
        remaining_inputs = {
            tuple(sorted(e["input"].items())) for e in client.examples[seeded_id]
        }
        assert (("q", "keep"),) in remaining_inputs
        assert (("q", "new"),) in remaining_inputs
        assert (("q", "drop"),) not in remaining_inputs

    def test_metadata_only_drift_patched(self, tmp_path: Path):
        """Description / metadata diff with matching examples → patchDataset.

        Replaces the old "skip with warning" behaviour now that GraphQL's
        ``patchDataset`` gives us a real update path.
        """
        client = _FakeDatasetClient()
        seeded_id = client.seed(
            _make_dataset("d3", inputs=[{"q": "a"}]),
        )
        # Same examples; description changes
        drifted = _make_dataset(
            "d3", inputs=[{"q": "a"}], description="new description",
        )
        write_dataset_yaml(drifted, tmp_path)
        report = startup_sync(
            prompts_dir=None, datasets_dir=tmp_path,
            prompt_client=None, dataset_client=client,
        )
        assert report.datasets_diffed == ["d3"]
        # Phoenix copy now reflects the YAML's description.
        assert client.records[seeded_id]["description"] == "new description"

    def test_hash_match_skipped(self, tmp_path: Path):
        ds = _make_dataset("d4", inputs=[{"q": "a"}])
        write_dataset_yaml(ds, tmp_path)
        client = _FakeDatasetClient()
        client.seed(ds)
        report = startup_sync(
            prompts_dir=None, datasets_dir=tmp_path,
            prompt_client=None, dataset_client=client,
        )
        assert report.datasets_skipped == ["d4"]
        assert report.datasets_created == []
        assert report.datasets_diffed == []


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


class TestErrorPaths:
    def test_invalid_yaml_bucketed(self, tmp_path: Path):
        (tmp_path / "broken.yaml").write_text(
            "not_a_prompt: true\nrandom_keys: yes",
            encoding="utf-8",
        )
        client = _FakePromptClient()
        report = startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=client, dataset_client=None,
            introspection_registry=_registry_with("BrokenStep"),
        )
        assert report.prompts_pushed == []
        assert len(report.prompts_failed) == 1
        assert report.prompts_failed[0][0] == "broken.yaml"

    def test_phoenix_failure_bucketed(self, tmp_path: Path):
        write_prompt_yaml(
            _make_prompt("boom", system="s", user="u"), tmp_path,
        )

        class _ExplodingClient(_FakePromptClient):
            def get_latest(self, name):
                raise PhoenixError("simulated outage")

        report = startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=_ExplodingClient(), dataset_client=None,
            introspection_registry=_registry_with("BoomStep"),
        )
        assert report.prompts_pushed == []
        assert len(report.prompts_failed) == 1
        assert "phoenix" in report.prompts_failed[0][1]

    def test_dataset_create_failure_bucketed(self, tmp_path: Path):
        write_dataset_yaml(
            _make_dataset("dboom", inputs=[{"q": "a"}]), tmp_path,
        )

        class _ExplodingClient(_FakeDatasetClient):
            def upload_dataset(self, **kwargs):
                raise PhoenixDatasetError("simulated outage")

        report = startup_sync(
            prompts_dir=None, datasets_dir=tmp_path,
            prompt_client=None, dataset_client=_ExplodingClient(),
        )
        assert report.datasets_created == []
        assert len(report.datasets_failed) == 1


def test_sync_report_independent_domains(tmp_path: Path):
    """One domain's failures don't poison the other."""
    write_prompt_yaml(_make_prompt("alpha", system="s", user="u"), tmp_path / "p")
    write_dataset_yaml(_make_dataset("d1", inputs=[{"q": "a"}]), tmp_path / "d")
    pc = _FakePromptClient()
    dc = _FakeDatasetClient()
    report = startup_sync(
        prompts_dir=tmp_path / "p", datasets_dir=tmp_path / "d",
        prompt_client=pc, dataset_client=dc,
        introspection_registry=_registry_with("AlphaStep"),
    )
    assert report.prompts_pushed == ["alpha"]
    assert report.datasets_created == ["d1"]
    assert isinstance(report, SyncReport)


# ---------------------------------------------------------------------------
# Step-derivation: response_format + tools attached at push time
# ---------------------------------------------------------------------------


class _FakeInstructions(BaseModel):
    """A minimal pydantic model used as INSTRUCTIONS in the test pipeline."""

    sentiment: str
    confidence: float


class _FakeInputs(StepInputs):
    text: str


class _FakePrompt(PromptVariables):
    text: str = Field(description="text")


class _FakeStepBase(LLMStepNode):
    """Base for dynamically-named test step classes.

    Concrete subclasses are constructed in ``_make_test_pipeline`` with
    distinct ``__name__``s so each test gets its own snake-cased prompt
    name. The whole class body lives at module scope so ``prepare``'s
    return-type annotation resolves cleanly under
    ``typing.get_type_hints``.
    """

    INPUTS = _FakeInputs
    INSTRUCTIONS = _FakeInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _FakeInputs) -> list[_FakePrompt]:
        return [_FakePrompt(
            text=inputs.text)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


def _make_test_pipeline(*step_names: str):
    """Build a synthetic pipeline-like object with ``Step``-binding ``nodes``.

    Each name is the step class name (must end in ``Step``); its
    snake_case name becomes the prompt name yaml_sync looks for.
    The synthetic ``Pipeline`` skips the real ``Pipeline.__init_subclass__``
    machinery (it doesn't inherit from ``Pipeline``) — yaml_sync only
    needs ``cls.nodes`` to be a list of bindings, so this is sufficient.
    """
    if not step_names:
        step_names = ("FakeStep",)
    step_classes = [
        type(name, (_FakeStepBase,), {})
        for name in step_names
    ]
    bindings = [
        Step(cls, inputs_spec=_FakeInputs.sources(text=FromInput("text")))
        for cls in step_classes
    ]
    PipelineCls = type("Pipeline", (), {"nodes": bindings})
    return PipelineCls, step_classes


def _registry_with(*step_names: str) -> dict:
    """Return an introspection_registry with one pipeline carrying these steps."""
    PipelineCls, _ = _make_test_pipeline(*step_names)
    return {"test_pipeline": PipelineCls}


class TestStepDerivation:
    def test_response_format_attached_on_first_create(self, tmp_path: Path):
        """yaml_sync resolves the step and pushes prompt with response_format."""
        from pydantic import BaseModel  # noqa: F401 — used by _FakeInstructions

        PipelineCls, _ = _make_test_pipeline("FakeStep")
        registry = {"fake_pipeline": PipelineCls}

        write_prompt_yaml(
            _make_prompt("fake", system="s", user="u"), tmp_path,
        )
        client = _FakePromptClient()
        startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=client, dataset_client=None,
            introspection_registry=registry,
        )

        latest = client.get_latest("fake")
        assert latest.get("response_format") is not None
        assert latest["response_format"]["type"] == "json_schema"
        # Schema should reflect _FakeInstructions's pydantic shape.
        json_schema = latest["response_format"]["json_schema"]
        assert json_schema["name"] == "_FakeInstructions"
        assert "sentiment" in json_schema["schema"]["properties"]

    def test_orphan_yaml_without_step_skipped(self, tmp_path: Path):
        """YAML files without a registered step don't sync — the LLMStep
        is the canonical entity, and an orphan YAML has nothing to bind to."""
        write_prompt_yaml(
            _make_prompt("orphan", system="s", user="u"), tmp_path,
        )
        client = _FakePromptClient()
        report = startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=client, dataset_client=None,
            introspection_registry={},
        )
        assert report.prompts_pushed == []
        assert "orphan" not in client.records

    def test_code_change_to_instructions_triggers_push(self, tmp_path: Path):
        """Hash includes response_format so changing INSTRUCTIONS forces a push."""
        # Seed Phoenix with a prompt that has the OLD (no schema) version.
        prompt = _make_prompt("evolving", system="s", user="u")
        write_prompt_yaml(prompt, tmp_path)
        client = _FakePromptClient()
        client.seed(prompt)  # seeded with no response_format

        # Now sync with a registered step that contributes a response_format.
        PipelineCls, _ = _make_test_pipeline("EvolvingStep")
        registry = {"p": PipelineCls}
        report = startup_sync(
            prompts_dir=tmp_path, datasets_dir=None,
            prompt_client=client, dataset_client=None,
            introspection_registry=registry,
        )
        assert report.prompts_pushed == ["evolving"]
        latest = client.get_latest("evolving")
        assert latest.get("response_format") is not None

    def test_yaml_idempotency_ignores_code_derived_fields(self, tmp_path: Path):
        """write_prompt_yaml's idempotency uses the YAML hash (excludes
        response_format/tools), so two prompts that only differ on those
        fields don't churn the file."""
        bare = _make_prompt("idem", system="s", user="u")
        with_schema = bare.model_copy(update={
            "response_format": {"type": "json_schema", "json_schema": {"name": "X"}},
        })
        # First write goes to disk.
        assert write_prompt_yaml(bare, tmp_path) is True
        # Second write with response_format set should be a no-op since
        # YAML doesn't carry that field.
        assert write_prompt_yaml(with_schema, tmp_path) is False
        # Hashes match for YAML idempotency, but differ for sync diff.
        assert _hash_prompt_yaml(bare) == _hash_prompt_yaml(with_schema)
        assert _hash_prompt(bare) != _hash_prompt(with_schema)
