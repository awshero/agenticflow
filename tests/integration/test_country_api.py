"""
Integration tests for GET /countries/{country_name}/capital endpoint.
TDD RED phase: Written before implementation.
Jira: PROJ-1 — GET country capital API

Tests cover:
- HTTP 200 happy path responses
- Correct JSON response schema
- HTTP 404 for unknown countries
- HTTP 400 for invalid inputs
- Content-Type headers
- Health check endpoint
"""
import pytest


class TestGetCountryCapitalHappyPath:
    """HTTP 200 happy path tests."""

    def test_get_capital_france_returns_200(self, client):
        response = client.get("/countries/France/capital")
        assert response.status_code == 200

    def test_get_capital_france_returns_correct_body(self, client):
        response = client.get("/countries/France/capital")
        body = response.json()
        assert body["capital"] == "Paris"

    def test_get_capital_response_includes_country_field(self, client):
        response = client.get("/countries/France/capital")
        body = response.json()
        assert "country" in body
        assert "capital" in body

    def test_get_capital_response_schema_only_expected_fields(self, client):
        response = client.get("/countries/France/capital")
        body = response.json()
        assert set(body.keys()) == {"country", "capital"}

    def test_get_capital_germany_returns_berlin(self, client):
        response = client.get("/countries/Germany/capital")
        assert response.status_code == 200
        assert response.json()["capital"] == "Berlin"

    def test_get_capital_japan_returns_tokyo(self, client):
        response = client.get("/countries/Japan/capital")
        assert response.status_code == 200
        assert response.json()["capital"] == "Tokyo"

    @pytest.mark.parametrize("country,expected_capital", [
        ("France", "Paris"),
        ("Germany", "Berlin"),
        ("Japan", "Tokyo"),
        ("Brazil", "Bras%C3%ADlia"),   # URL-encoded Brasília
        ("India", "New Delhi"),
        ("Australia", "Canberra"),
        ("Canada", "Ottawa"),
        ("Italy", "Rome"),
        ("Spain", "Madrid"),
        ("China", "Beijing"),
    ])
    def test_get_capital_multiple_countries_return_200(self, client, country, expected_capital):
        response = client.get(f"/countries/{country}/capital")
        assert response.status_code == 200, f"Expected 200 for {country}, got {response.status_code}"

    def test_get_capital_multiword_country_united_states(self, client):
        response = client.get("/countries/United States/capital")
        assert response.status_code == 200
        assert response.json()["capital"] == "Washington, D.C."

    def test_get_capital_multiword_country_united_kingdom(self, client):
        response = client.get("/countries/United Kingdom/capital")
        assert response.status_code == 200
        assert response.json()["capital"] == "London"


class TestGetCountryCapitalCaseInsensitivity:
    """Case-insensitive lookup tests via HTTP."""

    def test_get_capital_lowercase_country_returns_200(self, client):
        response = client.get("/countries/france/capital")
        assert response.status_code == 200
        assert response.json()["capital"] == "Paris"

    def test_get_capital_uppercase_country_returns_200(self, client):
        response = client.get("/countries/FRANCE/capital")
        assert response.status_code == 200
        assert response.json()["capital"] == "Paris"

    def test_get_capital_mixed_case_returns_200(self, client):
        response = client.get("/countries/fRaNcE/capital")
        assert response.status_code == 200
        assert response.json()["capital"] == "Paris"


class TestGetCountryCapitalNotFound:
    """HTTP 404 tests for unknown countries."""

    def test_get_capital_unknown_country_returns_404(self, client):
        response = client.get("/countries/Wakanda/capital")
        assert response.status_code == 404

    def test_get_capital_unknown_country_returns_detail_field(self, client):
        response = client.get("/countries/Wakanda/capital")
        body = response.json()
        assert "detail" in body

    def test_get_capital_unknown_country_detail_mentions_country_name(self, client):
        response = client.get("/countries/Wakanda/capital")
        body = response.json()
        assert "Wakanda" in body["detail"]

    def test_get_capital_fictional_country_returns_404(self, client):
        response = client.get("/countries/Neverland/capital")
        assert response.status_code == 404

    def test_get_capital_random_string_returns_404(self, client):
        response = client.get("/countries/xyzzy/capital")
        assert response.status_code == 404


class TestGetCountryCapitalInvalidInput:
    """HTTP 400 tests for invalid inputs."""

    def test_get_capital_whitespace_name_returns_400(self, client):
        response = client.get("/countries/%20/capital")
        assert response.status_code == 400

    def test_get_capital_digits_only_returns_400(self, client):
        response = client.get("/countries/123/capital")
        assert response.status_code == 400

    def test_get_capital_special_chars_returns_400(self, client):
        response = client.get("/countries/%40%23%24/capital")  # @#$
        assert response.status_code == 400

    def test_get_capital_invalid_input_returns_detail_field(self, client):
        response = client.get("/countries/123/capital")
        body = response.json()
        assert "detail" in body


class TestResponseHeaders:
    """Response header validation."""

    def test_get_capital_returns_json_content_type(self, client):
        response = client.get("/countries/France/capital")
        assert "application/json" in response.headers["content-type"]

    def test_get_capital_404_returns_json_content_type(self, client):
        response = client.get("/countries/Wakanda/capital")
        assert "application/json" in response.headers["content-type"]


class TestHealthCheck:
    """Health check endpoint tests."""

    def test_health_endpoint_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_endpoint_returns_status_healthy(self, client):
        response = client.get("/health")
        body = response.json()
        assert body["status"] == "healthy"

    def test_health_endpoint_returns_json(self, client):
        response = client.get("/health")
        assert "application/json" in response.headers["content-type"]
