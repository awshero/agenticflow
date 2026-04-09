"""
FastAPI application entry point.
Registers routers and exposes health check.
"""
from typing import Dict

from fastapi import FastAPI

from src.routers.countries import router as countries_router

app = FastAPI(
    title="Country Capital API",
    description="REST API to look up the capital city of any country.",
    version="1.0.0",
)

app.include_router(countries_router)


@app.get("/health", tags=["health"])
def health_check() -> Dict[str, str]:
    """Service health check."""
    return {"status": "healthy"}
