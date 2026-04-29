"""Tests for evals v2 variants.

Suites:
- Step 1 (TestFreshDbCreation / TestMigrationOnExistingDb): schema + migrations.
- Step 2 (TestApplyInstructionDelta): delta application + ACE hardening.
"""
import json
from datetime import datetime, timezone
from typing import ClassVar

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine, inspect, text
from sqlmodel import Session, select

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.evals import apply_instruction_delta
from llm_pipeline.evals.delta import (
    _MAX_DEFAULT_LEN,
    _MAX_DEFAULT_NODES,
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

    def test_empty_dict_delta_rejected(self):
        """Empty dict ``{}`` has len==0 but is not a list — must raise, not no-op."""
        with pytest.raises(ValueError, match="must be a list"):
            apply_instruction_delta(_DemoInstructions, {})  # type: ignore[arg-type]

    def test_string_delta_rejected(self):
        """Non-list input (string) must raise ValueError, not be coerced."""
        with pytest.raises(ValueError, match="must be a list"):
            apply_instruction_delta(_DemoInstructions, "foo")  # type: ignore[arg-type]

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


class TestDefaultValidatorNested:
    """Arbitrary nested JSON defaults accepted; ACE rejections preserved."""

    # --- happy path: nested structures ------------------------------------

    def test_list_of_dicts_accepted(self):
        _validate_default([{"name": "foo", "count": 1}])

    def test_dict_with_list_value_accepted(self):
        _validate_default({"outer": [1, 2, 3]})

    def test_three_level_nesting_accepted(self):
        _validate_default({"a": {"b": {"c": "deep"}}})

    def test_list_of_lists_accepted(self):
        _validate_default([[1, 2], [3, 4]])

    def test_empty_list_accepted(self):
        _validate_default([])

    def test_empty_dict_accepted(self):
        _validate_default({})

    def test_nested_default_flows_through_apply_instruction_delta(self):
        delta = [
            {
                "op": "add",
                "field": "items",
                "type_str": "list",
                "default": [{"name": "foo", "count": 1},
                            {"name": "bar", "count": 2}],
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        instance = cls()
        assert instance.items == [
            {"name": "foo", "count": 1},
            {"name": "bar", "count": 2},
        ]

    def test_mixed_nested_default_via_delta(self):
        delta = [
            {
                "op": "add",
                "field": "topics",
                "type_str": "dict",
                "default": {
                    "primary": ["a", "b"],
                    "metadata": {"source": "test", "tags": [1, 2, 3]},
                },
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        assert cls().topics == {
            "primary": ["a", "b"],
            "metadata": {"source": "test", "tags": [1, 2, 3]},
        }

    # --- ACE rejections still in force ------------------------------------

    def test_callable_rejected(self):
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            _validate_default(lambda: 1)

    def test_set_rejected(self):
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            _validate_default({1, 2, 3})

    def test_arbitrary_object_instance_rejected(self):
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            _validate_default(object())

    def test_pydantic_basemodel_instance_rejected(self):
        class _Thing(BaseModel):
            x: int = 1

        with pytest.raises(ValueError, match="not JSON-serialisable"):
            _validate_default(_Thing())

    def test_dict_with_non_string_key_rejected(self):
        # json.dumps silently coerces int keys to strings, so the explicit
        # walker guard is what rejects this case.
        with pytest.raises(ValueError, match="dict keys must be strings"):
            _validate_default({1: "a"})

    def test_dict_with_tuple_key_rejected(self):
        # Tuple keys: json.dumps raises TypeError.
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            _validate_default({(1, 2): "a"})

    def test_nested_callable_rejected(self):
        """Callable nested inside a valid container still rejected."""
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            _validate_default({"a": [lambda: 1]})

    def test_nested_set_rejected(self):
        with pytest.raises(ValueError, match="not JSON-serialisable"):
            _validate_default([{"x": {1, 2}}])

    # --- size caps --------------------------------------------------------

    def test_encoded_length_exceeds_cap_rejected(self):
        # Build a string whose json.dumps encoding exceeds _MAX_DEFAULT_LEN.
        # A raw string of length 2001 becomes a JSON string of 2003 chars
        # (wrapping quotes), so this comfortably trips the cap.
        oversized = "a" * (_MAX_DEFAULT_LEN + 1)
        with pytest.raises(ValueError, match="exceeds max"):
            _validate_default(oversized)

    def test_node_count_exceeds_cap_rejected(self):
        """Overly large structure rejected by either cap — both are defences.

        Oversized payloads trip whichever cap fires first (encoded-length
        runs before the walker). We just verify the rejection happens with a
        meaningful error — not which specific cap caught it.
        """
        payload = [0] * (_MAX_DEFAULT_NODES + 1)
        with pytest.raises(ValueError, match="exceeds max|nested node count"):
            _validate_default(payload)

    def test_encoded_length_exactly_at_cap_accepted(self):
        # Construct a default whose json.dumps encoding is EXACTLY 2000
        # chars. `"x...x"` with n x's encodes to n+2 chars.
        payload = "x" * (_MAX_DEFAULT_LEN - 2)
        encoded = json.dumps(payload)
        assert len(encoded) == _MAX_DEFAULT_LEN
        _validate_default(payload)  # must not raise

    def test_node_count_boundary_accepted_when_under_size_cap(self):
        """Near-boundary node count + under size cap = accepted.

        With _MAX_DEFAULT_LEN=2000, fitting _MAX_DEFAULT_NODES=1000 distinct
        JSON nodes in under 2000 encoded chars isn't possible (min ~1 char
        per node + delimiters). We instead verify that a payload with many
        nodes but well under both caps is accepted cleanly.
        """
        # 500 zeros: node_count=500, encoded ~= 1501 chars. Well within caps.
        payload = [0] * 500
        encoded = json.dumps(payload)
        assert len(encoded) <= _MAX_DEFAULT_LEN
        _validate_default(payload)  # must not raise


# ---------------------------------------------------------------------------
# Step 3 — merge_variable_definitions + runner integration.
# ---------------------------------------------------------------------------
from unittest.mock import patch  # noqa: E402

from sqlalchemy.pool import StaticPool  # noqa: E402

from llm_pipeline.db.step_config import StepModelConfig  # noqa: E402
from llm_pipeline.evals import merge_variable_definitions  # noqa: E402
from llm_pipeline.evals.models import EvaluationCase  # noqa: E402
from llm_pipeline.evals.runner import EvalRunner, _apply_variant_to_sandbox  # noqa: E402


class TestMergeVariableDefinitions:
    """Union-by-name merge; variant wins on conflict; None handled."""

    def test_both_none_returns_empty_list(self):
        assert merge_variable_definitions(None, None) == []

    def test_prod_none_returns_variant_copy(self):
        variant = [{"name": "x", "type": "str"}]
        result = merge_variable_definitions(None, variant)
        assert result == variant
        # Must be a copy so downstream mutation doesn't corrupt caller's list.
        result.append({"name": "extra"})
        assert len(variant) == 1

    def test_variant_none_returns_prod_copy(self):
        prod = [{"name": "y", "type": "int"}]
        result = merge_variable_definitions(prod, None)
        assert result == prod
        result.append({"name": "extra"})
        assert len(prod) == 1

    def test_disjoint_union(self):
        prod = [{"name": "a", "type": "str"}]
        variant = [{"name": "b", "type": "int"}]
        merged = merge_variable_definitions(prod, variant)
        names = {item["name"] for item in merged}
        assert names == {"a", "b"}

    def test_variant_wins_on_name_collision(self):
        prod = [{"name": "a", "type": "str", "auto_generate": "orig_expr"}]
        variant = [{"name": "a", "type": "int", "auto_generate": "new_expr"}]
        merged = merge_variable_definitions(prod, variant)
        assert len(merged) == 1
        assert merged[0]["type"] == "int"
        assert merged[0]["auto_generate"] == "new_expr"

    def test_auto_generate_expressions_passed_through_unevaluated(self):
        """MUST NOT evaluate auto_generate expressions during merge."""
        # Arbitrary non-registered expression — if this were eval'd, it'd raise.
        prod = [
            {"name": "a", "type": "list", "auto_generate": "enum_values(Nope)"}
        ]
        variant = [
            {"name": "b", "type": "list", "auto_generate": "enum_values(AlsoNope)"}
        ]
        merged = merge_variable_definitions(prod, variant)
        # Both expressions survive as strings — no attempt at resolution.
        by_name = {i["name"]: i for i in merged}
        assert by_name["a"]["auto_generate"] == "enum_values(Nope)"
        assert by_name["b"]["auto_generate"] == "enum_values(AlsoNope)"

    def test_items_without_name_skipped(self):
        prod = [{"name": "a"}, {"type": "str"}]  # second has no name
        variant = [{"no_name_here": True}]
        merged = merge_variable_definitions(prod, variant)
        names = {i.get("name") for i in merged}
        assert names == {"a"}


# ---- shared fixtures -------------------------------------------------------


@pytest.fixture()
def shared_engine():
    e = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(e)
    return e


# ---- _apply_variant_to_sandbox direct tests --------------------------------


class TestApplyVariantToSandbox:
    """Phase E: prompt + variable_definitions variant overrides log a
    warning and skip (Phoenix owns prompt content). The model override
    still upserts a sandbox ``StepModelConfig`` row."""

    def _make_step_def(self, *, prompt_name="my_step", step_name="my_step"):
        class _SD:
            pass
        sd = _SD()
        sd.prompt_name = prompt_name
        sd.resolved_prompt_name = prompt_name
        sd.step_name = step_name
        return sd

    def test_system_prompt_override_logs_warning(self, shared_engine, caplog):
        import logging
        step_def = self._make_step_def()
        with caplog.at_level(logging.WARNING):
            _apply_variant_to_sandbox(
                sandbox_engine=shared_engine,
                step_def=step_def,
                variant_delta={"system_prompt": "VARIANT_SYS"},
            )
        assert any("system_prompt" in rec.message for rec in caplog.records)

    def test_user_prompt_override_logs_warning(self, shared_engine, caplog):
        import logging
        step_def = self._make_step_def()
        with caplog.at_level(logging.WARNING):
            _apply_variant_to_sandbox(
                sandbox_engine=shared_engine,
                step_def=step_def,
                variant_delta={"user_prompt": "VARIANT_USR"},
            )
        assert any("user_prompt" in rec.message for rec in caplog.records)

    def test_variable_definitions_override_logs_warning(self, shared_engine, caplog):
        import logging
        step_def = self._make_step_def()
        with caplog.at_level(logging.WARNING):
            _apply_variant_to_sandbox(
                sandbox_engine=shared_engine,
                step_def=step_def,
                variant_delta={
                    "variable_definitions": [
                        {"name": "shared", "type": "int"},
                    ],
                },
            )
        assert any(
            "variable_definitions" in rec.message for rec in caplog.records
        )

    def test_model_upserts_step_model_config(self, shared_engine):
        step_def = self._make_step_def()
        _apply_variant_to_sandbox(
            sandbox_engine=shared_engine,
            step_def=step_def,
            variant_delta={"model": "gpt-5-test"},
        )
        with Session(shared_engine) as session:
            cfg = session.exec(
                select(StepModelConfig).where(
                    StepModelConfig.pipeline_name == "sandbox",
                    StepModelConfig.step_name == "my_step",
                )
            ).first()
            assert cfg is not None
            assert cfg.model == "gpt-5-test"

    def test_model_upsert_updates_existing_row(self, shared_engine):
        step_def = self._make_step_def()
        with Session(shared_engine) as session:
            session.add(StepModelConfig(
                pipeline_name="sandbox",
                step_name="my_step",
                model="old-model",
            ))
            session.commit()

        _apply_variant_to_sandbox(
            sandbox_engine=shared_engine,
            step_def=step_def,
            variant_delta={"model": "new-model"},
        )
        with Session(shared_engine) as session:
            rows = session.exec(
                select(StepModelConfig).where(
                    StepModelConfig.pipeline_name == "sandbox",
                    StepModelConfig.step_name == "my_step",
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].model == "new-model"


# ---- End-to-end: runner with variant ---------------------------------------


class _CustomerQuery(LLMResultMixin):
    """Base instructions class for runner integration test."""
    category: str = "unknown"
    sentiment: str = "neutral"

    example: ClassVar[dict] = {
        "category": "unknown",
        "sentiment": "neutral",
        "confidence_score": 0.95,
        "notes": None,
    }


@pytest.fixture()
def dataset_with_variant(shared_engine):
    """Create dataset + cases + variant with all 4 delta types."""
    with Session(shared_engine) as session:
        ds = EvaluationDataset(
            name="variant_ds",
            target_type="step",
            target_name="my_step",
        )
        session.add(ds)
        session.flush()
        session.add(EvaluationCase(
            dataset_id=ds.id,
            name="case_a",
            inputs={"text": "hello"},
            expected_output={"category": "billing"},
        ))
        session.commit()
        ds_id = ds.id

        variant = EvaluationVariant(
            dataset_id=ds_id,
            name="full_variant",
            description="all four delta types",
            delta={
                "model": "variant-model-x",
                "system_prompt": "VARIANT_SYSTEM",
                "user_prompt": "VARIANT_USER",
                "variable_definitions": [
                    {"name": "shared", "type": "int", "auto_generate": "var_expr"},
                ],
                "instructions_delta": [
                    {"op": "add", "field": "urgency",
                     "type_str": "str", "default": "normal"},
                    {"op": "modify", "field": "category",
                     "type_str": "str", "default": "updated"},
                ],
            },
        )
        session.add(variant)
        session.commit()
        session.refresh(variant)
        return ds_id, variant.id


class TestRunnerVariantIntegration:
    """End-to-end: run_dataset(variant_id=...) applies delta + persists snapshot."""

    def _make_step_def(self):
        """Duck-typed StepDefinition-like object for _find_step_def stub."""
        from dataclasses import dataclass, field
        from typing import Optional as _Opt

        @dataclass
        class _SD:
            step_class: type = type("MyStep", (), {"__name__": "MyStep"})
            prompt_name: _Opt[str] = "my_step"
            instructions: type = _CustomerQuery
            evaluators: list = field(default_factory=list)

            @property
            def step_name(self) -> str:
                return "my_step"

            @property
            def resolved_prompt_name(self) -> str:
                return self.prompt_name or self.step_name

        return _SD()

    def test_run_with_variant_persists_variant_id_and_snapshot(
        self, shared_engine, dataset_with_variant
    ):
        ds_id, variant_id = dataset_with_variant
        runner = EvalRunner(engine=shared_engine)

        def stub_find(step_name):
            return self._make_step_def(), None, "default-model", "sandbox"

        # Replace sandbox-running task with a no-op so we never hit LLMs.
        # The real value under test is: delta snapshot + variant_id persisted,
        # sandbox patched (verified via applied prompt/config rows).
        captured: dict = {}

        def stub_build(step_def, input_data_cls, step_model, variant_delta=None):
            captured["step_def"] = step_def
            captured["step_model"] = step_model
            captured["variant_delta"] = variant_delta

            def task(inputs):
                # Exercise the sandbox patching path end-to-end so the side
                # effects (Prompt rows, StepModelConfig) are observable.
                from llm_pipeline.sandbox import create_sandbox_engine
                sandbox_engine = create_sandbox_engine(shared_engine)
                if variant_delta:
                    _apply_variant_to_sandbox(
                        sandbox_engine=sandbox_engine,
                        step_def=step_def,
                        variant_delta=variant_delta,
                    )
                # Phase E: prompts live in Phoenix; only StepModelConfig
                # is observable in the sandbox DB.
                with Session(sandbox_engine) as s:
                    cfg = s.exec(
                        select(StepModelConfig).where(
                            StepModelConfig.pipeline_name == "sandbox",
                            StepModelConfig.step_name == "my_step",
                        )
                    ).first()
                    captured.setdefault("sandbox_states", []).append({
                        "cfg_model": cfg.model if cfg else None,
                    })
                return {"category": "updated", "sentiment": "neutral",
                        "urgency": "normal"}
            return task

        with patch.object(runner, "_find_step_def", side_effect=stub_find), \
             patch.object(runner, "_build_step_task_fn", side_effect=stub_build):
            run_id = runner.run_dataset(ds_id, variant_id=variant_id)

        # 1. Run row populated with variant_id + delta_snapshot.
        with Session(shared_engine) as session:
            run = session.exec(
                select(EvaluationRun).where(EvaluationRun.id == run_id)
            ).one()
            assert run.variant_id == variant_id
            assert run.status == "completed"
            # delta_snapshot must match the variant delta exactly (deep copy).
            assert run.delta_snapshot["model"] == "variant-model-x"
            assert run.delta_snapshot["system_prompt"] == "VARIANT_SYSTEM"
            assert run.delta_snapshot["user_prompt"] == "VARIANT_USER"
            assert run.delta_snapshot["instructions_delta"] == [
                {"op": "add", "field": "urgency",
                 "type_str": "str", "default": "normal"},
                {"op": "modify", "field": "category",
                 "type_str": "str", "default": "updated"},
            ]

        # 2. Runner picked up the variant model in preference to kwargs/default.
        assert captured["step_model"] == "variant-model-x"

        # 3. Variant delta was passed through to _build_step_task_fn.
        assert captured["variant_delta"]["model"] == "variant-model-x"
        assert captured["variant_delta"]["instructions_delta"][0]["field"] == "urgency"

        # 4. Sandbox engine got the model override (the only piece of
        # the variant Phase E still applies; prompt-content overrides
        # are skipped because Phoenix owns prompts now).
        sandbox_states = captured["sandbox_states"]
        assert sandbox_states, "task_fn must have executed at least once"
        for state in sandbox_states:
            assert state["cfg_model"] == "variant-model-x"

    def test_evaluator_resolution_uses_modified_instructions_class(
        self, shared_engine, dataset_with_variant
    ):
        """Variant-added `urgency` field must appear in auto-evaluator set.

        _resolve_step_task must call apply_instruction_delta BEFORE
        _resolve_evaluators so build_auto_evaluators sees the new field.
        """
        runner = EvalRunner(engine=shared_engine)

        def stub_find(step_name):
            return self._make_step_def(), None, "default-model", "sandbox"

        with patch.object(runner, "_find_step_def", side_effect=stub_find):
            task_fn, evaluators = runner._resolve_step_task(
                "my_step",
                model=None,
                variant_delta={
                    "model": "some-model",
                    "instructions_delta": [
                        {"op": "add", "field": "urgency",
                         "type_str": "str", "default": "normal"},
                    ],
                },
            )
        # The auto-generated evaluators should include the new urgency field.
        from llm_pipeline.evals.evaluators import FieldMatchEvaluator
        assert evaluators is not None
        names = {e.field_name for e in evaluators
                 if isinstance(e, FieldMatchEvaluator)}
        assert "urgency" in names, (
            "auto-evaluator must include variant-added field "
            f"— got {names}"
        )
        # Sanity: base fields still present.
        assert "category" in names
        assert "sentiment" in names

    def test_variant_not_belonging_to_dataset_raises(
        self, shared_engine
    ):
        """Variant must belong to the requested dataset."""
        with Session(shared_engine) as session:
            ds1 = EvaluationDataset(
                name="ds_one", target_type="step", target_name="s")
            ds2 = EvaluationDataset(
                name="ds_two", target_type="step", target_name="s")
            session.add(ds1)
            session.add(ds2)
            session.flush()
            # Give ds1 a case so we progress past the "no cases" check on ds1
            session.add(EvaluationCase(
                dataset_id=ds1.id, name="c", inputs={}))
            v = EvaluationVariant(
                dataset_id=ds2.id, name="v", delta={})
            session.add(v)
            session.commit()
            ds1_id = ds1.id
            v_id = v.id

        runner = EvalRunner(engine=shared_engine)
        with pytest.raises(ValueError, match="does not belong"):
            runner.run_dataset(ds1_id, variant_id=v_id)

    def test_missing_variant_id_raises(self, shared_engine):
        with Session(shared_engine) as session:
            ds = EvaluationDataset(
                name="only_ds", target_type="step", target_name="s")
            session.add(ds)
            session.flush()
            session.add(EvaluationCase(
                dataset_id=ds.id, name="c", inputs={}))
            session.commit()
            ds_id = ds.id

        runner = EvalRunner(engine=shared_engine)
        with pytest.raises(ValueError, match="Variant .* not found"):
            runner.run_dataset(ds_id, variant_id=99999)

    def test_run_dataset_by_name_passes_variant_id_through(
        self, shared_engine, dataset_with_variant
    ):
        """Signature extension: run_dataset_by_name forwards variant_id."""
        ds_id, variant_id = dataset_with_variant
        runner = EvalRunner(engine=shared_engine)

        with patch.object(runner, "run_dataset") as run_mock:
            run_mock.return_value = 123
            result = runner.run_dataset_by_name(
                "variant_ds", model="m", variant_id=variant_id
            )
        assert result == 123
        run_mock.assert_called_once_with(
            ds_id, model="m", variant_id=variant_id
        )

    def test_no_variant_id_baseline_run_snapshot_null(
        self, shared_engine
    ):
        """Baseline runs (no variant) must leave variant_id + delta_snapshot None."""
        with Session(shared_engine) as session:
            ds = EvaluationDataset(
                name="baseline_ds", target_type="step", target_name="my_step")
            session.add(ds)
            session.flush()
            session.add(EvaluationCase(
                dataset_id=ds.id, name="c", inputs={}))
            session.commit()
            ds_id = ds.id

        runner = EvalRunner(engine=shared_engine)

        def mock_task_fn(inputs):
            return {"category": "x"}

        with patch.object(
            runner, "_resolve_task", return_value=(mock_task_fn, None)
        ):
            run_id = runner.run_dataset(ds_id)

        with Session(shared_engine) as session:
            run = session.exec(
                select(EvaluationRun).where(EvaluationRun.id == run_id)
            ).one()
            assert run.variant_id is None
            assert run.delta_snapshot is None


# ---------------------------------------------------------------------------
# Step 4 — enum type resolution via _AUTO_GENERATE_REGISTRY.
# ---------------------------------------------------------------------------
from enum import Enum  # noqa: E402
from typing import Optional as _Optional  # noqa: E402
from typing import get_args as _get_args  # noqa: E402
from typing import get_origin as _get_origin  # noqa: E402
from typing import Union as _Union  # noqa: E402

from llm_pipeline.prompts.variables import (  # noqa: E402
    _AUTO_GENERATE_REGISTRY,
    register_auto_generate,
)


class _TestEnum(str, Enum):
    """Sample enum used by TestEnumTypeResolution."""
    FOO = "foo"
    BAR = "bar"


class _NonEnumConstant:
    """Arbitrary non-enum object registered to exercise the 'not an enum' guard."""
    value = 42


class TestEnumTypeResolution:
    """enum:<Name> + Optional[enum:<Name>] resolution via the auto_generate registry.

    Registry-only lookup — never imports modules. Must reject unknown names,
    non-identifier names, and registered-but-non-enum objects. Defaults for
    enum fields are validated by pydantic at class creation.
    """

    @pytest.fixture(autouse=True)
    def _registry_setup(self):
        # Stash any pre-existing entries so we restore them after the test.
        # Tests across this class share names "TestEnum" / "TheConstant".
        names = ("TestEnum", "TheConstant")
        saved = {n: _AUTO_GENERATE_REGISTRY.get(n) for n in names}
        try:
            register_auto_generate("TestEnum", _TestEnum)
            register_auto_generate("TheConstant", _NonEnumConstant)
            yield
        finally:
            for name, prev in saved.items():
                if prev is None:
                    _AUTO_GENERATE_REGISTRY.pop(name, None)
                else:
                    _AUTO_GENERATE_REGISTRY[name] = prev

    # --- happy path: _resolve_type -----------------------------------------

    def test_resolve_enum_returns_registered_class(self):
        assert _resolve_type("enum:TestEnum") is _TestEnum

    def test_resolve_optional_enum_returns_optional_wrapper(self):
        resolved = _resolve_type("Optional[enum:TestEnum]")
        # Optional[X] is Union[X, None].
        assert _get_origin(resolved) is _Union
        args = _get_args(resolved)
        assert _TestEnum in args
        assert type(None) in args

    # --- happy path: apply_instruction_delta -------------------------------

    def test_add_enum_field_default_coerces_to_member(self):
        delta = [
            {
                "op": "add",
                "field": "sentiment",
                "type_str": "enum:TestEnum",
                "default": "foo",
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        assert "sentiment" in cls.model_fields
        assert cls.model_fields["sentiment"].annotation is _TestEnum
        # validate_default=True wrap coerces raw string to enum member.
        instance = cls()
        assert instance.sentiment is _TestEnum.FOO

    def test_add_enum_field_instance_roundtrip(self):
        delta = [
            {
                "op": "add",
                "field": "sentiment",
                "type_str": "enum:TestEnum",
                "default": "foo",
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        # Explicit instantiation with the member value still yields the
        # enum member — standard pydantic coercion.
        assert cls(sentiment="bar").sentiment is _TestEnum.BAR
        assert cls(sentiment="foo").sentiment is _TestEnum.FOO

    def test_add_optional_enum_field_default_none(self):
        delta = [
            {
                "op": "add",
                "field": "maybe_sent",
                "type_str": "Optional[enum:TestEnum]",
                "default": None,
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        assert cls().maybe_sent is None

    def test_add_optional_enum_field_default_member_value(self):
        delta = [
            {
                "op": "add",
                "field": "maybe_sent",
                "type_str": "Optional[enum:TestEnum]",
                "default": "bar",
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        assert cls().maybe_sent is _TestEnum.BAR

    # --- rejection: registry lookup ---------------------------------------

    def test_unknown_enum_name_raises(self):
        with pytest.raises(ValueError, match="not registered"):
            _resolve_type("enum:UnknownEnum")

    def test_identifier_like_malicious_name_still_fails_registry_lookup(self):
        # __class__ is a valid identifier but is NEVER in the trusted registry.
        with pytest.raises(ValueError, match="not registered"):
            _resolve_type("enum:__class__")

    def test_dunder_import_name_rejected_by_registry(self):
        # __import__ passes the identifier regex but will not be registered —
        # this asserts the ACE-surface property: even identifier-looking
        # builtins can't reach any dynamic resolution because there's none.
        with pytest.raises(ValueError, match="not registered"):
            _resolve_type("enum:__import__")

    def test_non_identifier_enum_name_rejected(self):
        with pytest.raises(ValueError, match="valid identifier"):
            _resolve_type("enum:bad-name-with-dash")

    def test_non_identifier_enum_name_with_dots_rejected(self):
        with pytest.raises(ValueError, match="valid identifier"):
            _resolve_type("enum:some.module.Name")

    def test_non_enum_registered_object_rejected(self):
        with pytest.raises(ValueError, match="not an enum"):
            _resolve_type("enum:TheConstant")

    # --- rejection: default mismatches ------------------------------------

    def test_enum_default_not_a_member_raises(self):
        """Invalid enum default surfaces as ValueError on instantiation.

        Pydantic's validate_default check fires at model instantiation (not at
        create_model time), so we trigger it by constructing the class.
        ValidationError is a ValueError subclass, so tests using
        pytest.raises(ValueError) catch it — matching the module-level
        contract that all failure modes raise ValueError.
        """
        delta = [
            {
                "op": "add",
                "field": "sentiment",
                "type_str": "enum:TestEnum",
                "default": "nonexistent",
            }
        ]
        cls = apply_instruction_delta(_DemoInstructions, delta)
        with pytest.raises(ValueError, match="enum|foo|bar"):
            cls()

    # --- security: no importlib in the enum resolution path ---------------

    def test_no_importlib_in_enum_resolution_codepath(self):
        """The resolver must not call importlib at any point in enum handling.

        Code-inspection via AST: parse llm_pipeline/evals/delta.py and confirm
        no `import importlib` / `importlib.import_module(...)` appears. The
        positive-lookup path is already covered by the happy-path tests; this
        protects against future regressions that might re-introduce dynamic
        module loading.
        """
        import ast
        from pathlib import Path

        src = Path(
            "llm_pipeline/evals/delta.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "importlib", (
                        "delta.py must not import importlib"
                    )
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "importlib", (
                    "delta.py must not import from importlib"
                )
            elif isinstance(node, ast.Attribute):
                # Catches `importlib.import_module(...)` written without an
                # explicit import (e.g. via an aliased stdlib namespace).
                if (
                    isinstance(node.value, ast.Name)
                    and node.value.id == "importlib"
                ):
                    raise AssertionError(
                        "delta.py references importlib attribute access"
                    )

    # --- modify path preserves annotation on enum fields ------------------

    def test_modify_existing_enum_field_preserves_annotation(self):
        """Omitting type_str on modify preserves the base's enum annotation."""

        class _BaseWithEnum(LLMResultMixin):
            existing: _TestEnum = _TestEnum.FOO
            example: ClassVar[dict] = {
                "existing": "foo",
                "confidence_score": 0.95,
                "notes": None,
            }

        delta = [
            {"op": "modify", "field": "existing", "default": "bar"}
        ]
        cls = apply_instruction_delta(_BaseWithEnum, delta)

        # Annotation carried over from base class.
        assert cls.model_fields["existing"].annotation is _TestEnum
        # validate_default wrap coerces the new default to the member.
        assert cls().existing is _TestEnum.BAR
        # Roundtrip.
        assert cls(existing="foo").existing is _TestEnum.FOO
