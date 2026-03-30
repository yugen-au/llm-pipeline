"""Unit tests for _load_pipeline_modules in llm_pipeline.ui.app."""
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.ui.app import _load_pipeline_modules


@pytest.fixture
def engine():
    """In-memory SQLite engine for _seed_prompts calls."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(eng)
    return eng


# ---------------------------------------------------------------------------
# Successful import + scan
# ---------------------------------------------------------------------------

class TestSuccessfulScan:
    def test_registers_local_subclass(self, engine):
        """good_module.AlphaPipeline is registered under 'alpha' key."""
        pipeline_reg, intro_reg = _load_pipeline_modules(
            ["tests.ui._fixtures.good_module"], None, engine
        )
        assert "alpha" in pipeline_reg
        assert "alpha" in intro_reg

    def test_factory_is_callable(self, engine):
        """Registered factory is callable."""
        pipeline_reg, _ = _load_pipeline_modules(
            ["tests.ui._fixtures.good_module"], None, engine
        )
        assert callable(pipeline_reg["alpha"])

    def test_introspection_is_class(self, engine):
        """Introspection registry stores the class itself."""
        from tests.ui._fixtures.good_module import AlphaPipeline
        _, intro_reg = _load_pipeline_modules(
            ["tests.ui._fixtures.good_module"], None, engine
        )
        assert intro_reg["alpha"] is AlphaPipeline

    def test_seed_prompts_called(self, engine):
        """_seed_prompts is called for registered class."""
        with patch(
            "tests.ui._fixtures.good_module.AlphaPipeline._seed_prompts"
        ) as mock_seed:
            _load_pipeline_modules(
                ["tests.ui._fixtures.good_module"], None, engine
            )
        mock_seed.assert_called_once_with(engine)

    def test_seed_prompts_failure_does_not_unregister(self, engine):
        """Pipeline stays registered even when _seed_prompts raises."""
        with patch(
            "tests.ui._fixtures.good_module.AlphaPipeline._seed_prompts",
            side_effect=RuntimeError("boom"),
        ):
            pipeline_reg, _ = _load_pipeline_modules(
                ["tests.ui._fixtures.good_module"], None, engine
            )
        assert "alpha" in pipeline_reg

    def test_multiple_modules(self, engine):
        """Loading two modules merges their registries."""
        pipeline_reg, _ = _load_pipeline_modules(
            [
                "tests.ui._fixtures.good_module",
                "tests.ui._fixtures.mixed_module",
            ],
            None,
            engine,
        )
        assert "alpha" in pipeline_reg
        assert "beta" in pipeline_reg


# ---------------------------------------------------------------------------
# ValueError on bad module
# ---------------------------------------------------------------------------

class TestImportFailure:
    def test_raises_value_error_on_bad_module(self, engine):
        """ValueError raised when module path cannot be imported."""
        with pytest.raises(ValueError, match="Failed to import"):
            _load_pipeline_modules(
                ["totally.bogus.module"], None, engine
            )

    def test_chained_from_import_error(self, engine):
        """ValueError chains the original ImportError."""
        with pytest.raises(ValueError) as exc_info:
            _load_pipeline_modules(
                ["totally.bogus.module"], None, engine
            )
        assert isinstance(exc_info.value.__cause__, ImportError)


# ---------------------------------------------------------------------------
# ValueError on no subclasses
# ---------------------------------------------------------------------------

class TestNoSubclasses:
    def test_raises_value_error_when_no_subclasses(self, engine):
        """ValueError raised when module has no PipelineConfig subclasses."""
        with pytest.raises(ValueError, match="No PipelineConfig subclasses"):
            _load_pipeline_modules(
                ["tests.ui._fixtures.no_pipelines"], None, engine
            )


# ---------------------------------------------------------------------------
# Re-export guard filtering
# ---------------------------------------------------------------------------

class TestReexportGuard:
    def test_reexport_only_module_raises(self, engine):
        """Module that only re-exports (no local subclass) raises ValueError."""
        with pytest.raises(ValueError, match="No PipelineConfig subclasses"):
            _load_pipeline_modules(
                ["tests.ui._fixtures.reexport_module"], None, engine
            )

    def test_mixed_module_registers_only_local(self, engine):
        """mixed_module defines BetaPipeline locally and re-exports AlphaPipeline;
        only BetaPipeline should be registered."""
        pipeline_reg, intro_reg = _load_pipeline_modules(
            ["tests.ui._fixtures.mixed_module"], None, engine
        )
        assert "beta" in pipeline_reg
        assert "alpha" not in pipeline_reg
        assert "beta" in intro_reg
        assert "alpha" not in intro_reg
