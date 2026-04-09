"""
Unit tests for CountryService.
TDD RED phase: Written before implementation.
Jira: PROJ-1 — GET country capital API

Tests cover:
- Happy path: known countries return correct capitals
- Case insensitivity
- Multi-word country names
- Unknown countries return None
- Invalid inputs return None or raise ValueError
"""
import pytest

from src.services.country_service import get_capital, validate_country_name


class TestGetCapital:
    """Tests for get_capital(country_name: str) -> str | None"""

    def test_get_capital_france_returns_paris(self):
        # Arrange
        country_name = "France"
        # Act
        result = get_capital(country_name)
        # Assert
        assert result == "Paris"

    def test_get_capital_germany_returns_berlin(self):
        result = get_capital("Germany")
        assert result == "Berlin"

    def test_get_capital_japan_returns_tokyo(self):
        result = get_capital("Japan")
        assert result == "Tokyo"

    def test_get_capital_united_states_returns_washington(self):
        result = get_capital("United States")
        assert result == "Washington, D.C."

    def test_get_capital_united_kingdom_returns_london(self):
        result = get_capital("United Kingdom")
        assert result == "London"

    @pytest.mark.parametrize("country,expected_capital", [
        ("France", "Paris"),
        ("Germany", "Berlin"),
        ("Japan", "Tokyo"),
        ("Brazil", "Brasília"),
        ("India", "New Delhi"),
        ("Australia", "Canberra"),
        ("Canada", "Ottawa"),
        ("Mexico", "Mexico City"),
        ("Italy", "Rome"),
        ("Spain", "Madrid"),
        ("China", "Beijing"),
        ("Russia", "Moscow"),
        ("South Africa", "Pretoria"),
        ("Argentina", "Buenos Aires"),
        ("Nigeria", "Abuja"),
    ])
    def test_get_capital_known_countries_parametrized(self, country, expected_capital):
        result = get_capital(country)
        assert result == expected_capital, f"Expected {expected_capital} for {country}, got {result}"

    def test_get_capital_unknown_country_returns_none(self):
        result = get_capital("Wakanda")
        assert result is None

    def test_get_capital_nonexistent_country_returns_none(self):
        result = get_capital("Neverland")
        assert result is None


class TestGetCapitalCaseInsensitivity:
    """Case-insensitive lookup tests."""

    def test_get_capital_lowercase_country_returns_capital(self):
        result = get_capital("france")
        assert result == "Paris"

    def test_get_capital_uppercase_country_returns_capital(self):
        result = get_capital("FRANCE")
        assert result == "Paris"

    def test_get_capital_mixed_case_country_returns_capital(self):
        result = get_capital("fRaNcE")
        assert result == "Paris"

    def test_get_capital_lowercase_multiword_returns_capital(self):
        result = get_capital("united states")
        assert result == "Washington, D.C."

    def test_get_capital_leading_trailing_whitespace_stripped(self):
        result = get_capital("  France  ")
        assert result == "Paris"


class TestValidateCountryName:
    """Tests for validate_country_name(name: str) -> bool"""

    def test_validate_valid_name_returns_true(self):
        assert validate_country_name("France") is True

    def test_validate_multiword_name_returns_true(self):
        assert validate_country_name("United States") is True

    def test_validate_empty_string_returns_false(self):
        assert validate_country_name("") is False

    def test_validate_whitespace_only_returns_false(self):
        assert validate_country_name("   ") is False

    def test_validate_digits_only_returns_false(self):
        assert validate_country_name("123") is False

    def test_validate_special_chars_only_returns_false(self):
        assert validate_country_name("@#$%") is False

    def test_validate_name_with_hyphen_returns_true(self):
        # e.g. Guinea-Bissau, Timor-Leste
        assert validate_country_name("Guinea-Bissau") is True

    def test_validate_name_with_apostrophe_returns_true(self):
        # e.g. Côte d'Ivoire
        assert validate_country_name("Cote d'Ivoire") is True
