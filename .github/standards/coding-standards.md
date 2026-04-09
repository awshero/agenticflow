# Coding Standards — Python/FastAPI

## Project Structure

```
src/
├── __init__.py
├── main.py              # App factory, router registration, middleware
├── routers/             # HTTP route handlers only (no business logic)
│   ├── __init__.py
│   └── {feature}.py
├── services/            # Business logic (pure functions preferred)
│   ├── __init__.py
│   └── {feature}_service.py
└── data/                # Static data, constants, seed data
    └── {feature}.py
```

## Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Files | snake_case | `country_service.py` |
| Functions | snake_case | `get_capital()` |
| Variables | snake_case | `country_name` |
| Classes | PascalCase | `CountryService` |
| Constants | SCREAMING_SNAKE | `MAX_COUNTRY_NAME_LENGTH` |
| Type hints | Always required | `def get_capital(name: str) -> str \| None:` |

## Python Specifics

### Type Hints (mandatory)
```python
# All function signatures must have type hints
def get_capital(country_name: str) -> str | None:
    ...
```

### Imports Order
```python
# 1. Standard library
import os
from typing import Optional

# 2. Third-party
from fastapi import FastAPI, HTTPException

# 3. Local
from src.services.country_service import get_capital
```

### String Formatting
Use f-strings: `f"Country {name} not found"` NOT `"Country " + name + " not found"`

### Error Handling
```python
# Raise HTTPException in routers
raise HTTPException(status_code=404, detail=f"Country not found: {country_name}")

# Return None in services (let router decide HTTP response)
def get_capital(name: str) -> str | None:
    return CAPITALS.get(name.strip().title())
```

## Separation of Concerns

### Router responsibilities (ONLY):
- Parse path/query parameters
- Validate input format
- Call service layer
- Convert service result to HTTP response
- Raise HTTPException for errors

### Service responsibilities (ONLY):
- Business logic
- Data lookups
- Data transformations
- Return domain objects (not HTTP responses)

### Data layer responsibilities (ONLY):
- Static data definitions
- Constants
- No logic

## FastAPI Specifics

### Route definitions
```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/countries", tags=["countries"])

class CapitalResponse(BaseModel):
    country: str
    capital: str

@router.get("/{country_name}/capital", response_model=CapitalResponse)
def get_country_capital(country_name: str) -> CapitalResponse:
    """
    Get the capital city for a given country.

    - **country_name**: Name of the country (case-insensitive)
    """
    ...
```

### Pydantic Models
- Use Pydantic models for all request/response bodies
- Field names: snake_case
- Add descriptions to fields

## Code Quality

### Line Length: 88 characters (black default)
### No Magic Numbers
```python
# BAD
if len(name) > 100:

# GOOD
MAX_COUNTRY_NAME_LENGTH = 100
if len(name) > MAX_COUNTRY_NAME_LENGTH:
```

### No Bare Excepts
```python
# BAD
try:
    ...
except:
    pass

# GOOD
try:
    ...
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

## Linting Configuration

`.flake8` or `pyproject.toml`:
```ini
[flake8]
max-line-length = 88
extend-ignore = E203, W503
```

Run before commit: `flake8 src/ tests/`
Auto-format: `black src/ tests/`
