# Testing Standards

## TDD Workflow (mandatory)

Follow strict RED → GREEN → REFACTOR:
1. **RED**: Write failing test first. Run it. See it fail. Commit "test: add failing test for X"
2. **GREEN**: Write minimal implementation to make test pass. Commit "feat: implement X"
3. **REFACTOR**: Clean up code without changing behavior. Tests must still pass.

## Coverage Requirements

| Level | Minimum Coverage |
|-------|-----------------|
| Overall project | 90% |
| Service/business logic | 95% |
| Router/controllers | 85% |
| Data layer | 80% |
| Utility functions | 90% |

Run coverage: `pytest --cov=src --cov-report=term-missing --cov-fail-under=90`

## Test Organization

```
tests/
├── conftest.py          # Shared fixtures only
├── unit/
│   ├── __init__.py
│   └── test_{module}.py # One file per src module
└── integration/
    ├── __init__.py
    └── test_{feature}.py # One file per feature/endpoint
```

## Test Naming Convention

```python
def test_{unit_under_test}_{condition}_{expected_result}():
```

Examples:
- `test_get_capital_valid_country_returns_capital_string`
- `test_get_capital_unknown_country_returns_none`
- `test_country_endpoint_valid_name_returns_200`
- `test_country_endpoint_unknown_country_returns_404`
- `test_country_endpoint_empty_name_returns_400`

## Test Structure (AAA Pattern)

```python
def test_example():
    # Arrange — set up test data
    country_name = "France"

    # Act — call the thing being tested
    result = get_capital(country_name)

    # Assert — verify the result
    assert result == "Paris"
```

## What to Test

### Unit Tests
- Every public method of every service class
- Input validation logic
- Data transformation logic
- Edge cases: None, empty string, whitespace, special characters
- Boundary values

### Integration Tests
- Every HTTP endpoint (happy path)
- Every HTTP endpoint (error paths: 400, 404)
- Response body schema (exact field names and types)
- Response headers (Content-Type)
- HTTP status codes

### Do NOT Test
- Third-party library internals (FastAPI, pytest, etc.)
- Python built-in types
- Framework routing (FastAPI handles this)

## Fixtures (conftest.py)

```python
@pytest.fixture
def client():
    """FastAPI test client — use for all integration tests."""
    from fastapi.testclient import TestClient
    from src.main import app
    return TestClient(app)
```

All shared fixtures go in `conftest.py`. Never define the same fixture twice.

## Parametrize Repetitive Tests

```python
@pytest.mark.parametrize("country,expected_capital", [
    ("France", "Paris"),
    ("Germany", "Berlin"),
    ("Japan", "Tokyo"),
    ("Brazil", "Brasília"),
])
def test_get_capital_known_countries(country, expected_capital):
    assert get_capital(country) == expected_capital
```

## Assertions

- Use specific assertions: `assert result == "Paris"` not `assert result`
- For dicts: assert specific keys and values, not entire dict equality (brittle)
- For HTTP: assert status code first, then body
- Error message: `assert result == "Paris", f"Expected Paris but got {result}"`

## Test Independence

- No test should depend on execution order
- No test should share mutable state
- Use fixtures for setup, not module-level variables
- Clean up after tests that create files/data

## Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage (required before PR)
pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=90

# Specific category
pytest tests/unit/ -v
pytest tests/integration/ -v

# One test file
pytest tests/unit/test_country_service.py -v

# One test
pytest tests/unit/test_country_service.py::test_get_capital_france_returns_paris -v
```
