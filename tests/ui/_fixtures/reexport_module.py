"""Fixture module: re-exports AlphaPipeline from good_module but defines no local subclass."""
from tests.ui._fixtures.good_module import AlphaPipeline  # noqa: F401 - re-export
