"""Pipeline configurations route module."""
from fastapi import APIRouter

router = APIRouter(prefix="/pipelines", tags=["pipelines"])
