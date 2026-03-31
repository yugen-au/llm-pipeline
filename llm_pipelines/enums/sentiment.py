"""Demo enum for auto_generate testing."""
import enum


class Sentiment(enum.Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"
