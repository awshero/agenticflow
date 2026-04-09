"""
HTTP route handlers for country capital endpoints.
Router layer: HTTP concerns only, no business logic.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services.country_service import get_capital, validate_country_name

router = APIRouter(prefix="/countries", tags=["countries"])


class CapitalResponse(BaseModel):
    country: str
    capital: str


@router.get("/{country_name}/capital", response_model=CapitalResponse)
def get_country_capital(country_name: str) -> CapitalResponse:
    """
    Get the capital city for a given country name.

    - **country_name**: Name of the country (case-insensitive, e.g. "France", "france")

    Returns the capital city or an appropriate error.

    Example:
        GET /countries/France/capital
        → {"country": "France", "capital": "Paris"}
    """
    if not validate_country_name(country_name):
        raise HTTPException(status_code=400, detail="Invalid country name")

    capital = get_capital(country_name)

    if capital is None:
        raise HTTPException(
            status_code=404,
            detail=f"Country not found: {country_name}",
        )

    return CapitalResponse(country=country_name, capital=capital)
