# Jira Requirements

Ticket: PROJ-1
Summary: Create a GET API endpoint to parse country name and return the capital
Type: Story
Priority: Medium
Status: In Progress

## Description

Build a REST API endpoint that accepts a country name as input and returns the corresponding capital city.

## Acceptance Criteria

- [ ] **AC1**: `GET /countries/{country_name}/capital` endpoint exists and is accessible
- [ ] **AC2**: Returns HTTP 200 with `{"country": "{name}", "capital": "{capital}"}` for valid countries
- [ ] **AC3**: Returns HTTP 404 with `{"detail": "Country not found: {name}"}` when country is not in the dataset
- [ ] **AC4**: Returns HTTP 400 with `{"detail": "Invalid country name"}` for empty or invalid input
- [ ] **AC5**: Country name lookup is case-insensitive (`france` returns same as `France`)
- [ ] **AC6**: Supports multi-word country names (e.g., `United States`, `New Zealand`)
- [ ] **AC7**: Response Content-Type is `application/json`
- [ ] **AC8**: `GET /health` endpoint returns `{"status": "healthy"}`

## Example Usage

```
GET /countries/France/capital
→ 200 {"country": "France", "capital": "Paris"}

GET /countries/france/capital
→ 200 {"country": "france", "capital": "Paris"}

GET /countries/Japan/capital
→ 200 {"country": "Japan", "capital": "Tokyo"}

GET /countries/Wakanda/capital
→ 404 {"detail": "Country not found: Wakanda"}

GET /countries/ /capital
→ 400 {"detail": "Invalid country name"}
```

## Technical Notes

- Python + FastAPI preferred
- Must have 90%+ test coverage
- Unit tests for service layer, integration tests for HTTP layer
- Dataset must include at minimum: G20 countries + common countries

## Out of Scope

- Authentication/authorization
- Pagination
- Country search/fuzzy matching
- Caching layer
- Database (static in-memory data is acceptable)
