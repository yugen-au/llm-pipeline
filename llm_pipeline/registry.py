"""
Base class for pipeline database registries.

Defines the interface for declaring which database models a pipeline manages.
"""
from abc import ABC
from typing import List, Type, ClassVar
from sqlmodel import SQLModel


class PipelineDatabaseRegistry(ABC):
    """
    Base class for pipeline database registries.
    
    Each pipeline should define its own registry class that inherits from this,
    declaring which database models it manages and their insertion order.
    
    This registry is the single source of truth for:
    1. What database tables the pipeline creates
    2. What order to insert them (FK dependencies)
    3. Which models the save() method operates on
    
    Registry must be configured at class definition time using class call syntax:
    
    Example:
        class MyPipelineRegistry(PipelineDatabaseRegistry, models=[
            Vendor,      # No dependencies
            RateCard,    # Depends on Vendor
            Lane,        # Depends on RateCard
        ]):
            pass
    """
    
    MODELS: ClassVar[List[Type[SQLModel]]] = []
    
    def __init_subclass__(cls, models=None, **kwargs):
        """
        Called when a subclass is defined. Sets MODELS from class parameter.
        
        Args:
            models: List of SQLModel classes in insertion order (required)
            **kwargs: Additional keyword arguments passed to super().__init_subclass__
        
        Raises:
            ValueError: If models not provided for concrete registry
        """
        super().__init_subclass__(**kwargs)
        
        # Only enforce models for concrete registries (not intermediate base classes)
        if models is not None:
            cls.MODELS = models
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is PipelineDatabaseRegistry:
            # This is a concrete registry without models specified
            raise ValueError(
                f"{cls.__name__} must specify models parameter when defining the class:\n"
                f"class {cls.__name__}(PipelineDatabaseRegistry, models=[Model1, Model2, ...])"
            )
    
    @classmethod
    def get_models(cls) -> List[Type[SQLModel]]:
        """
        Get all managed models in insertion order.
        
        Returns:
            List of model classes ordered by FK dependencies
        
        Raises:
            ValueError: If MODELS not defined
        """
        if not cls.MODELS:
            raise ValueError(
                f"{cls.__name__} has no models configured. "
                f"Use: class {cls.__name__}(PipelineDatabaseRegistry, models=[...])"
            )
        return cls.MODELS


__all__ = ["PipelineDatabaseRegistry"]
