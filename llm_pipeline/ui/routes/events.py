"""Pipeline events route module."""
from fastapi import APIRouter

router = APIRouter(prefix="/events", tags=["events"])
