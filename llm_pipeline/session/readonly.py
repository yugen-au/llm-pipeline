"""
Read-only session wrapper for pipeline steps.

Prevents accidental database writes during step execution by wrapping
the SQLModel session and blocking all write operations.
"""
from typing import Any
from sqlmodel import Session


class ReadOnlySession:
    """
    Read-only wrapper for SQLModel Session.
    
    Allows all read operations (query, exec, get) but blocks write operations
    (add, delete, flush, commit) to prevent accidental database modifications
    during step execution.
    
    The pipeline will use this wrapper for self.session during step execution,
    then switch to the real session during save() operations.
    """
    
    def __init__(self, session: Session):
        """
        Initialize read-only session wrapper.
        
        Args:
            session: The underlying SQLModel/SQLAlchemy session to wrap
        """
        self._session = session
    
    # Allow read operations
    def query(self, *args, **kwargs):
        """Allow queries (read operation)."""
        return self._session.query(*args, **kwargs)
    
    def exec(self, *args, **kwargs):
        """Allow exec (read operation for SQLModel)."""
        return self._session.exec(*args, **kwargs)
    
    def get(self, *args, **kwargs):
        """Allow get by primary key (read operation)."""
        return self._session.get(*args, **kwargs)
    
    def execute(self, *args, **kwargs):
        """Allow execute (read operation)."""
        return self._session.execute(*args, **kwargs)
    
    def scalar(self, *args, **kwargs):
        """Allow scalar (read operation)."""
        return self._session.scalar(*args, **kwargs)
    
    def scalars(self, *args, **kwargs):
        """Allow scalars (read operation)."""
        return self._session.scalars(*args, **kwargs)
    
    # Block write operations
    def add(self, *args, **kwargs):
        """Block add operation."""
        raise RuntimeError(
            "Cannot write to database during step execution. "
            "Database writes are only allowed in pipeline.save(). "
            "If you need to create database records during extraction, "
            "create the model instances and return them - the pipeline "
            "will handle insertion in the correct order."
        )
    
    def add_all(self, *args, **kwargs):
        """Block add_all operation."""
        raise RuntimeError(
            "Cannot write to database during step execution. "
            "Database writes are only allowed in pipeline.save()."
        )
    
    def delete(self, *args, **kwargs):
        """Block delete operation."""
        raise RuntimeError(
            "Cannot delete from database during step execution. "
            "Database writes are only allowed in pipeline.save()."
        )
    
    def flush(self, *args, **kwargs):
        """Block flush operation."""
        raise RuntimeError(
            "Cannot flush to database during step execution. "
            "Database writes are only allowed in pipeline.save()."
        )
    
    def commit(self, *args, **kwargs):
        """Block commit operation."""
        raise RuntimeError(
            "Cannot commit to database during step execution. "
            "Database writes are only allowed in pipeline.save()."
        )
    
    def merge(self, *args, **kwargs):
        """Block merge operation."""
        raise RuntimeError(
            "Cannot merge to database during step execution. "
            "Database writes are only allowed in pipeline.save()."
        )
    
    def refresh(self, *args, **kwargs):
        """Block refresh operation (can trigger writes)."""
        raise RuntimeError(
            "Cannot refresh from database during step execution. "
            "Use queries instead."
        )
    
    def expire(self, *args, **kwargs):
        """Block expire operation."""
        raise RuntimeError(
            "Cannot expire objects during step execution."
        )
    
    def expire_all(self, *args, **kwargs):
        """Block expire_all operation."""
        raise RuntimeError(
            "Cannot expire objects during step execution."
        )
    
    def expunge(self, *args, **kwargs):
        """Block expunge operation."""
        raise RuntimeError(
            "Cannot expunge objects during step execution."
        )
    
    def expunge_all(self, *args, **kwargs):
        """Block expunge_all operation."""
        raise RuntimeError(
            "Cannot expunge objects during step execution."
        )
    
    # Allow some metadata/utility operations
    @property
    def bind(self):
        """Allow access to bind (needed for some operations)."""
        return self._session.bind
    
    @property
    def info(self):
        """Allow access to info dict."""
        return self._session.info
    
    def is_active(self):
        """Allow checking if session is active."""
        return self._session.is_active
    
    def __repr__(self):
        return f"<ReadOnlySession wrapping {self._session!r}>"


__all__ = ["ReadOnlySession"]
