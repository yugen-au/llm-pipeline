"""Pipeline runs route module."""
from fastapi import APIRouter

router = APIRouter(prefix="/runs", tags=["runs"])
