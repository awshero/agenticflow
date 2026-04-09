# API Design Standards

## REST Conventions

### URL Structure
- Use nouns, not verbs: `/countries/{name}/capital` NOT `/getCapital`
- Lowercase with hyphens for multi-word paths: `/country-regions` NOT `/countryRegions`
- Use path params for resource identity: `/countries/{name}/capital`
- Use query params for filtering/pagination: `/countries?region=europe`

### HTTP Methods
- GET: Read-only, no side effects
- POST: Create new resource
- PUT: Full replacement update
- PATCH: Partial update
- DELETE: Remove resource

### Status Codes (mandatory)
| Scenario | Code |
|----------|------|
| Success (GET/PATCH) | 200 |
| Created (POST) | 201 |
| No content (DELETE) | 204 |
| Bad request / validation error | 400 |
| Unauthorized | 401 |
| Forbidden | 403 |
| Not found | 404 |
| Method not allowed | 405 |
| Conflict | 409 |
| Unprocessable entity | 422 |
| Server error | 500 |

### Response Format (mandatory)

**Success response:**
```json
{
  "country": "France",
  "capital": "Paris"
}
```

**Error response:**
```json
{
  "detail": "Human-readable error message"
}
```

**Never** return bare strings or arrays as top-level responses.

### Headers (mandatory)
- `Content-Type: application/json` on all responses
- `X-Request-ID` on all responses (trace ID)

### Validation Rules
- Validate all path parameters at router level
- Return 400 for empty, whitespace-only, or special-char-only inputs
- Return 422 for type mismatches (FastAPI default)

### Naming Conventions
- JSON keys: `snake_case`
- No abbreviations in field names (`country_name` not `cntry_nm`)
- Dates: ISO 8601 format (`2024-01-15T10:30:00Z`)

### Documentation
- Every endpoint must have a docstring description
- Include example request/response in docstring
- OpenAPI spec auto-generated (FastAPI does this by default)

### Health Check (mandatory)
Every service must expose:
```
GET /health
Response 200: {"status": "healthy", "version": "1.0.0"}
```

### Performance
- Response time target: < 200ms for simple lookups
- Response time target: < 1000ms for complex operations
