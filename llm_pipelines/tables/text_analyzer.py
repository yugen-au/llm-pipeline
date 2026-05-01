"""TextAnalyzer database tables (SQLModel, table=True)."""
from typing import Optional

from sqlmodel import Field, SQLModel


class Topic(SQLModel, table=True):
    """Persisted topic record extracted by the topic extraction step."""
    __tablename__ = "demo_topics"
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    relevance: float
    run_id: str
