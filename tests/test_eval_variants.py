"""Tests for evals v2 variants.

Suites:
- Step 1 (TestFreshDbCreation / TestMigrationOnExistingDb): schema + migrations.
- Step 2 (TestApplyInstructionDelta): delta application + ACE hardening.
"""
from datetime import datetime, timezone
from typing import ClassVar

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine, inspect, text
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals import apply_instruction_delta
from llm_pipeline.evals.delta import (
    _MAX_DELTA_ITEMS,
    _MAX_STRING_LEN,
    _resolve_type,
    _validate_default,
)
from llm_pipeline.evals.models import (
    EvaluationDataset,
    EvaluationVariant,
    EvaluationRun,
)
from llm_pipeline.step import LLMResultMixin


class TestFreshDbCreation:
    """init_pipeline_db() creates eval_variants and updated eval_runs schema."""

    def test_eval_variants_table_created(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            assert "eval_variants" in inspector.get_table_names()
        finally:
            engine.dispose()

    def test_eval_variants_columns(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            cols = {c["name"] for c in inspector.get_columns("eval_variants")}
            expected = {
                "id",
                "dataset_id",
                "name",
                "description",
                "delta",
                "created_at",
                "updated_at",
            }
            assert expected.issubset(cols), f"missing: {expected - cols}"
        finally:
            engine.dispose()

    def test_eval_variants_fk_to_dataset(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            fks = inspector.get_foreign_keys("eval_variants")
            # expect one FK: dataset_id -> eval_datasets.id
            assert any(
                fk["referred_table"] == "eval_datasets"
                and "dataset_id" in fk["constrained_columns"]
                and "id" in fk["referred_columns"]
                for fk in fks
            ), f"dataset_id FK not found in {fks}"
        finally:
            engine.dispose()

    def test_eval_variants_dataset_index(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            indexes = inspector.get_indexes("eval_variants")
            names = {idx["name"] for idx in indexes}
            assert "ix_eval_variants_dataset" in names
        finally:
            engine.dispose()

    def test_eval_runs_has_variant_columns(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            inspector = inspect(engine)
            cols = {c["name"] for c in inspector.get_columns("eval_runs")}
            assert "variant_id" in cols
            assert "delta_snapshot" in cols
        finally:
            engine.dispose()

    def test_variant_round_trip_insert(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            with Session(engine) as session:
                ds = EvaluationDataset(
                    name="test_ds",
                    target_type="step",
                    target_name="my_step",
                )
                session.add(ds)
                session.commit()
                session.refresh(ds)
                ds_id = ds.id

                variant = EvaluationVariant(
                    dataset_id=ds_id,
                    name="variant-a",
                    description="first variant",
                    delta={
                        "model": "claude-3.5-sonnet",
                        "system_prompt": "override sys",
                        "user_prompt": "override user",
                        "instructions_delta": [
                            {"op": "add", "field": "foo", "type_str": "str"}
                        ],
                    },
                )
                session.add(variant)
                session.commit()
                session.refresh(variant)

            with Session(engine) as session:
                retrieved = session.exec(
                    select(EvaluationVariant).where(
                        EvaluationVariant.name == "variant-a"
                    )
                ).one()
                assert retrieved.dataset_id == ds_id
                assert retrieved.delta["model"] == "claude-3.5-sonnet"
                assert retrieved.delta["instructions_delta"][0]["field"] == "foo"
        finally:
            engine.dispose()

    def test_run_delta_snapshot_round_trip(self):
        engine = create_engine("sqlite://")
        try:
            init_pipeline_db(engine=engine)
            with Session(engine) as session:
                ds = EvaluationDataset(
                    name="ds_for_run",
                    target_type="step",
                    target_name="my_step",
                )
                session.add(ds)
                session.commit()
                session.refresh(ds)
                ds_id = ds.id

                variant = EvaluationVariant(
                    dataset_id=ds_id,
                    name="v1",
                    delta={"model": "m", "system_prompt": None,
                           "user_prompt": None, "instructions_delta": []},
                )
                session.add(variant)
                session.commit()
                session.refresh(variant)
                variant_id = variant.id

                run = EvaluationRun(
                    dataset_id=ds_id,
                    variant_id=variant_id,
                    delta_snapshot={"model": "m", "system_prompt": None,
                                    "user_prompt": None,
                                    "instructions_delta": []},
                )
                session.add(run)
                session.commit()
                session.refresh(run)
                run_id = run.id

            with Session(engine) as session:
                retrieved = session.exec(
                    select(EvaluationRun).where(EvaluationRun.id == run_id)
                ).one()
                assert retrieved.variant_id == variant_id
                assert retrieved.delta_snapshot["model"] == "m"
        finally:
            engine.dispose()


class TestMigrationOnExistingDb:
    """_migrate_add_columns adds variant_id + delta_snapshot to legacy eval_runs."""

    def test_migration_adds_columns_to_existing_eval_runs(self, tmp_path):
        db_path = tmp_path / "legacy.db"
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            # Create a pre-migration eval_runs table without the new columns.
            with engine.connect() as conn:
                conn.execute(text(
                    "CREATE TABLE eval_datasets ("
                    "id INTEGER PRIMARY KEY, name VARCHAR(200), "
                    "target_type VARCHAR(20), target_name VARCHAR(200), "
                    "description TEXT, created_at DATETIME, updated_at DATETIME)"
                ))
                conn.execute(text(
                    "CREATE TABLE eval_runs ("
                    "id INTEGER PRIMARY KEY, dataset_id INTEGER, "
                    "status VARCHAR(20), total_cases INTEGER, passed INTEGER, "
                    "failed INTEGER, errored INTEGER, report_data TEXT, "
                    "error_message TEXT, started_at DATETIME, "
                    "completed_at DATETIME)"
                ))
                conn.commit()

            # Sanity: new columns not present yet.
            inspector = inspect(engine)
            pre_cols = {c["name"] for c in inspector.get_columns("eval_runs")}
            assert "variant_id" not in pre_cols
            assert "delta_snapshot" not in pre_cols
        finally:
            engine.dispose()

        # Now run init_pipeline_db against the same file — should migrate.
        engine2 = create_engine(f"sqlite:///{db_path}")
        try:
            init_pipeline_db(engine=engine2)
            inspector = inspect(engine2)
            post_cols = {c["name"] for c in inspector.get_columns("eval_runs")}
            assert "variant_id" in post_cols
            assert "delta_snapshot" in post_cols
            # eval_variants table now created by create_all.
            assert "eval_variants" in inspector.get_table_names()
        finally:
            engine2.dispose()

    def test_migration_idempotent(self, tmp_path):
        db_path = tmp_path / "idem.db"
        engine = create_engine(f"sqlite:///{db_path}")
        try:
            init_pipeline_db(engine=engine)
        finally:
            engine.dispose()

        engine2 = create_engine(f"sqlite:///{db_path}")
        try:
            # Second run must not raise.
            init_pipeline_db(engine=engine2)
            inspector = inspect(engine2)
            cols = {c["name"] for c in inspector.get_columns("eval_runs")}
            assert "variant_id" in cols
            assert "delta_snapshot" in cols
        finally:
            engine2.dispose()


# ---------------------------------------------------------------------------
# Step 2 — apply_instruction_delta + security boundaries.
# ---------------------------------------------------------------------------
class _DemoInstructions(LLMResultMixin):
    """Concrete LLMResultMixin subclass used across delta tests."""

    category: str = "unknown"
    score: int = 0

    example: ClassVar[dict] = {
        "category": "unknown",
        "score": 0,
        "confidence_score": 0.95,
        "notes": None,
    }


class TestApplyInstructionDelta:
    """Delta application correctness + ACE hygiene enforcement."""

    # --- correctness -------------------------------------------------------

    def test_add_field(self):
        delta = [
            {
                "op": "add",
                "field": "new_field",
                "type_str": "str",
                "default": "hello",
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)

        assert issubclass(cls, _DemoInstructions)
        assert "new_field" in cls.model_fields
        assert cls.model_fields["new_field"].annotation is str
        instance = cls()
        assert instance.new_field == "hello"

    def test_add_optional_field(self):
        delta = [
            {
                "op": "add",
                "field": "maybe_int",
                "type_str": "Optional[int]",
                "default": None,
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        instance = cls()
        assert instance.maybe_int is None

    def test_modify_field(self):
        delta = [
            {
                "op": "modify",
                "field": "category",
                "type_str": "str",
                "default": "billing",
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)

        assert cls.model_fields["category"].default == "billing"
        assert cls().category == "billing"

    def test_modify_field_without_type_str_preserves_annotation(self):
        delta = [
            {
                "op": "modify",
                "field": "score",
                "default": 42,
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)

        assert cls.model_fields["score"].annotation is int
        assert cls().score == 42

    def test_empty_delta_returns_unchanged(self):
        assert apply_instruction_delta(_DemoInstructions, []) is _DemoInstructions
        assert apply_instruction_delta(_DemoInstructions, None) is _DemoInstructions  # type: ignore[arg-type]

    # --- security: op validation ------------------------------------------

    @pytest.mark.parametrize(
        "bad_op", ["remove", "eval", "exec", "delete", "", None]
    )
    def test_unknown_op_raises(self, bad_op):
        delta = [
            {
                "op": bad_op,
                "field": "x",
                "type_str": "str",
                "default": "",
            }
        ]
        with pytest.raises(ValueError, match="op must be"):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_remove_op_explicitly_rejected(self):
        """remove is not supported in v2; must raise ValueError."""
        delta = [{"op": "remove", "field": "category"}]
        with pytest.raises(ValueError, match="op must be"):
            apply_instruction_delta(_DemoInstructions, delta)

    # --- security: type_str whitelist -------------------------------------

    def test_unknown_type_str_raises(self):
        delta = [
            {
                "op": "add",
                "field": "x",
                "type_str": "__import__('os').system('ls')",
                "default": "",
            }
        ]
        with pytest.raises(
            ValueError, match="not in whitelist|exceeds max length"
        ):
            apply_instruction_delta(_DemoInstructions, delta)

    @pytest.mark.parametrize(
        "bad_type",
        [
            "object",
            "type",
            "eval",
            "Any",
            "List[str]",
            "tuple",
            "set",
            "bytes",
            "pathlib.Path",
        ],
    )
    def test_non_whitelisted_types_rejected(self, bad_type):
        with pytest.raises(ValueError, match="not in whitelist"):
            _resolve_type(bad_type)

    def test_resolve_type_rejects_non_string(self):
        with pytest.raises(ValueError, match="must be a string"):
            _resolve_type(int)  # type: ignore[arg-type]

    # --- security: field name regex ---------------------------------------

    @pytest.mark.parametrize(
        "bad_field",
        [
            "__class__",
            "__init__",
            "__dict__",
            "items.append",
            "../x",
            "x.y",
            "x-y",
            "x y",
            "1field",
            "X",  # uppercase start disallowed by regex
            "",
        ],
    )
    def test_malicious_field_name_raises(self, bad_field):
        delta = [
            {
                "op": "add",
                "field": bad_field,
                "type_str": "str",
                "default": "",
            }
        ]
        with pytest.raises(
            ValueError, match="valid identifier|must be a string"
        ):
            apply_instruction_delta(_DemoInstructions, delta)

    # --- security: default validation -------------------------------------

    def test_callable_default_rejected(self):
        delta = [
            {
                "op": "add",
                "field": "x",
                "type_str": "int",
                "default": lambda: 1,
            }
        ]
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_class_ref_default_rejected(self):
        delta = [
            {
                "op": "add",
                "field": "x",
                "type_str": "str",
                "default": BaseModel,
            }
        ]
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_nested_dict_default_rejected(self):
        """Nested structures beyond flat dict/list of scalars are rejected."""
        delta = [
            {
                "op": "add",
                "field": "x",
                "type_str": "dict",
                "default": {"nested": {"inner": 1}},
            }
        ]
        with pytest.raises(ValueError, match="must be scalars"):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_list_of_dicts_default_rejected(self):
        delta = [
            {
                "op": "add",
                "field": "x",
                "type_str": "list",
                "default": [{"a": 1}],
            }
        ]
        with pytest.raises(ValueError, match="may only contain scalars"):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_flat_list_default_accepted(self):
        delta = [
            {
                "op": "add",
                "field": "tags",
                "type_str": "list",
                "default": ["a", "b", "c"],
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        assert cls().tags == ["a", "b", "c"]

    def test_flat_dict_default_accepted(self):
        delta = [
            {
                "op": "add",
                "field": "meta",
                "type_str": "dict",
                "default": {"k": "v"},
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        assert cls().meta == {"k": "v"}

    def test_validate_default_direct_callable(self):
        with pytest.raises(ValueError):
            _validate_default(lambda: 1)

    # --- security: size caps ----------------------------------------------

    def test_oversized_delta_rejected(self):
        delta = [
            {
                "op": "add",
                "field": f"f_{i}",
                "type_str": "int",
                "default": i,
            }
            for i in range(_MAX_DELTA_ITEMS + 1)  # 51 items
        ]
        with pytest.raises(ValueError, match="exceeds max"):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_delta_at_cap_accepted(self):
        """Boundary: 50 items must still work."""
        delta = [
            {
                "op": "add",
                "field": f"f_{i}",
                "type_str": "int",
                "default": 0,
            }
            for i in range(_MAX_DELTA_ITEMS)
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        assert f"f_{_MAX_DELTA_ITEMS - 1}" in cls.model_fields

    def test_oversized_string_rejected(self):
        big = "a" * (_MAX_STRING_LEN + 1)
        delta = [
            {
                "op": "add",
                "field": "x",
                "type_str": big,
                "default": "",
            }
        ]
        with pytest.raises(
            ValueError, match="exceeds max length|not in whitelist"
        ):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_oversized_field_name_rejected(self):
        big = "a" + ("b" * _MAX_STRING_LEN)  # 1001 chars, valid identifier chars
        delta = [
            {
                "op": "add",
                "field": big,
                "type_str": "str",
                "default": "",
            }
        ]
        with pytest.raises(ValueError, match="exceeds max length"):
            apply_instruction_delta(_DemoInstructions, delta)

    # --- inheritance preservation -----------------------------------------

    def test_preserves_create_failure(self):
        """create_failure() inherited from LLMResultMixin must survive delta."""
        delta = [
            {
                "op": "add",
                "field": "extra",
                "type_str": "str",
                "default": "",
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)

        assert hasattr(cls, "create_failure")
        failure = cls.create_failure(
            "boom", category="err", score=0, extra=""
        )
        assert failure.confidence_score == 0.0
        assert "Failed: boom" in failure.notes

    def test_preserves_base_fields(self):
        delta = [
            {
                "op": "add",
                "field": "extra",
                "type_str": "int",
                "default": 1,
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        assert "confidence_score" in cls.model_fields
        assert "notes" in cls.model_fields
        assert "category" in cls.model_fields
        assert "score" in cls.model_fields

    # --- pydantic / pydantic-ai compatibility -----------------------------

    def test_result_is_pydantic_basemodel_subclass(self):
        delta = [
            {
                "op": "add",
                "field": "extra",
                "type_str": "str",
                "default": "",
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        assert issubclass(cls, BaseModel)
        # Pydantic schema generation must not error.
        schema = cls.model_json_schema()
        assert "extra" in schema["properties"]

    def test_pydantic_ai_output_type_compatible(self):
        """Result class must be usable as a pydantic-ai Agent output_type.

        Skips if pydantic-ai is unavailable; otherwise constructs an Agent
        with the delta-modified class as output_type. No model call is made —
        construction alone exercises pydantic-ai's output-validation code.
        """
        pydantic_ai = pytest.importorskip("pydantic_ai")

        delta = [
            {
                "op": "add",
                "field": "extra",
                "type_str": "str",
                "default": "",
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)

        try:
            from pydantic_ai.models.test import TestModel
        except ImportError:
            pytest.skip("pydantic_ai.models.test.TestModel unavailable")

        agent = pydantic_ai.Agent(TestModel(), output_type=cls)
        assert agent is not None

    # --- misc edge cases --------------------------------------------------

    def test_missing_field_in_item_raises(self):
        delta = [{"op": "add", "type_str": "str", "default": ""}]
        with pytest.raises(ValueError, match="must be a string"):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_non_list_delta_raises(self):
        with pytest.raises(ValueError, match="must be a list"):
            apply_instruction_delta(
                _DemoInstructions, {"op": "add"}  # type: ignore[arg-type]
            )

    def test_non_dict_item_raises(self):
        with pytest.raises(ValueError, match="must be a dict"):
            apply_instruction_delta(
                _DemoInstructions, ["not-a-dict"]  # type: ignore[list-item]
            )

    def test_add_without_default_rejected(self):
        delta = [{"op": "add", "field": "x", "type_str": "str"}]
        with pytest.raises(ValueError, match="requires a default"):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_modify_without_default_rejected(self):
        delta = [{"op": "modify", "field": "category"}]
        with pytest.raises(ValueError, match="requires a default"):
            apply_instruction_delta(_DemoInstructions, delta)

    def test_modify_unknown_field_without_type_rejected(self):
        delta = [{"op": "modify", "field": "no_such_field", "default": 1}]
        with pytest.raises(ValueError, match="not present on base class"):
            apply_instruction_delta(_DemoInstructions, delta)
