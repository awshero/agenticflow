"""
Business logic for country capital lookups.
Service layer: pure functions, no HTTP concerns.
"""
import re
from typing import Optional

from src.data.countries import COUNTRY_CAPITALS

# Matches strings containing at least one letter, optionally with spaces, hyphens, apostrophes
_VALID_NAME_PATTERN = re.compile(r"^[a-zA-ZÀ-ÿ'\-]+([ \-'][a-zA-ZÀ-ÿ']+)*$")


def validate_country_name(name: str) -> bool:
    """
    Return True if name is a plausible country name, False otherwise.

    Valid: letters, spaces, hyphens, apostrophes (e.g. "Guinea-Bissau", "Cote d'Ivoire")
    Invalid: empty string, whitespace-only, digits-only, special characters
    """
    if not name or not name.strip():
        return False
    return bool(_VALID_NAME_PATTERN.match(name.strip()))


def get_capital(country_name: str) -> Optional[str]:
    """
    Return the capital city for the given country name, or None if not found.

    Lookup is case-insensitive and strips leading/trailing whitespace.

    Args:
        country_name: Name of the country (e.g. "France", "france", "FRANCE")

    Returns:
        Capital city string if found, None otherwise.
    """
    if not country_name or not country_name.strip():
        return None

    normalized = country_name.strip().title()
    return COUNTRY_CAPITALS.get(normalized)
