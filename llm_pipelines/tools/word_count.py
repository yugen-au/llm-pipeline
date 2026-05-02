"""Demo tool: count words in a string.

Showcases the :class:`AgentTool` shape — module-level ``Inputs`` /
``Args`` classes pinned via UPPER_CASE ClassVars, prefix-paired
naming, and a ``run`` classmethod returning the result.
"""
from __future__ import annotations

from pydantic import BaseModel

from llm_pipeline.agent_tool import AgentTool
from llm_pipeline.inputs import StepInputs


class WordCountInputs(StepInputs):
    """No pipeline-side data needed."""


class WordCountArgs(BaseModel):
    """LLM-supplied arguments."""

    text: str


class WordCountTool(AgentTool):
    """Count whitespace-separated words in a string."""

    INPUTS = WordCountInputs
    ARGS = WordCountArgs

    @classmethod
    def run(cls, inputs: WordCountInputs, args: WordCountArgs, ctx) -> int:
        return len(args.text.split())
