"""Prompt constants and seeding for the TextAnalyzer demo pipeline."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlmodel import Session, SQLModel, select

from llm_pipeline.db.prompt import Prompt

if TYPE_CHECKING:
    from sqlalchemy import Engine

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SENTIMENT_ANALYSIS_SYSTEM: dict = {
    "prompt_key": "sentiment_analysis",
    "prompt_name": "Sentiment Analysis System",
    "prompt_type": "system",
    "category": "text_analyzer",
    "step_name": "sentiment_analysis",
    "content": (
        "You are a sentiment analysis expert. Analyze the sentiment of the "
        "provided text and classify it as positive, negative, neutral, or mixed. "
        "Provide a brief explanation for your classification and a confidence score."
    ),
    "required_variables": [],
    "description": "System prompt for sentiment analysis step",
}

TOPIC_EXTRACTION_SYSTEM: dict = {
    "prompt_key": "topic_extraction",
    "prompt_name": "Topic Extraction System",
    "prompt_type": "system",
    "category": "text_analyzer",
    "step_name": "topic_extraction",
    "content": (
        "You are a topic extraction specialist. Identify the key topics discussed "
        "in the provided text. For each topic, assign a relevance score between 0 "
        "and 1. Determine the single primary topic. Consider the sentiment context "
        "when evaluating topic importance."
    ),
    "required_variables": [],
    "description": "System prompt for topic extraction step",
}

SUMMARY_SYSTEM: dict = {
    "prompt_key": "summary",
    "prompt_name": "Summary System",
    "prompt_type": "system",
    "category": "text_analyzer",
    "step_name": "summary",
    "content": (
        "You are a text summarization expert. Produce a concise summary of the "
        "provided text that incorporates the identified sentiment and primary topic. "
        "The summary should capture the key points while reflecting the overall tone."
    ),
    "required_variables": [],
    "description": "System prompt for summary step",
}

# ---------------------------------------------------------------------------
# User prompts
# ---------------------------------------------------------------------------

SENTIMENT_ANALYSIS_USER: dict = {
    "prompt_key": "sentiment_analysis",
    "prompt_name": "Sentiment Analysis User",
    "prompt_type": "user",
    "category": "text_analyzer",
    "step_name": "sentiment_analysis",
    "content": "Analyze the sentiment of the following text:\n\n{text}",
    "required_variables": ["text"],
    "description": "User prompt for sentiment analysis step",
}

TOPIC_EXTRACTION_USER: dict = {
    "prompt_key": "topic_extraction",
    "prompt_name": "Topic Extraction User",
    "prompt_type": "user",
    "category": "text_analyzer",
    "step_name": "topic_extraction",
    "content": (
        "Extract topics from the following text. The text has been analyzed as "
        "having a {sentiment} sentiment.\n\nText:\n{text}"
    ),
    "required_variables": ["text", "sentiment"],
    "description": "User prompt for topic extraction step",
}

SUMMARY_USER: dict = {
    "prompt_key": "summary",
    "prompt_name": "Summary User",
    "prompt_type": "user",
    "category": "text_analyzer",
    "step_name": "summary",
    "content": (
        "Summarize the following text. The sentiment is {sentiment} and the "
        "primary topic is {primary_topic}.\n\nText:\n{text}"
    ),
    "required_variables": ["text", "sentiment", "primary_topic"],
    "description": "User prompt for summary step",
}

# All prompts for iteration
ALL_PROMPTS: list[dict] = [
    SENTIMENT_ANALYSIS_SYSTEM,
    SENTIMENT_ANALYSIS_USER,
    TOPIC_EXTRACTION_SYSTEM,
    TOPIC_EXTRACTION_USER,
    SUMMARY_SYSTEM,
    SUMMARY_USER,
]


def seed_prompts(cls: type, engine: Engine) -> None:
    """Create demo_topics table and idempotently seed prompts.

    Args:
        cls: The pipeline class (used for logging context only).
        engine: SQLAlchemy engine for DB operations.
    """
    from llm_pipeline.demo.pipeline import Topic

    # Create demo_topics table if it doesn't exist
    SQLModel.metadata.create_all(engine, tables=[Topic.__table__])

    with Session(engine) as session:
        for prompt_data in ALL_PROMPTS:
            existing = session.exec(
                select(Prompt).where(
                    Prompt.prompt_key == prompt_data["prompt_key"],
                    Prompt.prompt_type == prompt_data["prompt_type"],
                )
            ).first()
            if existing is None:
                session.add(Prompt(**prompt_data))
        session.commit()
    logger.info("Seeded %d prompts for %s", len(ALL_PROMPTS), cls.__name__)
