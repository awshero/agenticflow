# Git Standards

## Branch Naming

Format: `{JIRA-ID}-{short-description}`

Rules:
- All lowercase
- Hyphens only (no underscores, no spaces)
- Max 60 characters total
- Must start with Jira ticket ID

Examples:
- `proj-1-get-country-capital-api`
- `proj-42-fix-null-country-response`
- `proj-100-add-country-search-endpoint`

BAD examples:
- `feature/get-capital` (no Jira ID)
- `PROJ-1_get_capital` (uppercase, underscores)
- `proj1getCapital` (no hyphens, camelCase)

## Commit Message Format (Conventional Commits)

```
{type}({scope}): {short description}

{optional body}

{optional footer}
Jira: {JIRA-ID}
```

### Types
| Type | When to Use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `test` | Adding/fixing tests |
| `docs` | Documentation only |
| `refactor` | Code change, no feature/fix |
| `chore` | Build tools, deps, config |
| `perf` | Performance improvement |
| `ci` | CI/CD changes |

### Examples
```
feat(countries): add GET /countries/{name}/capital endpoint

Implements capital lookup by country name with case-insensitive
matching. Returns 404 for unknown countries, 400 for invalid input.

- 15 tests (unit + integration), 95% coverage
- Response: {"country": str, "capital": str}

Jira: PROJ-1-get-country-capital-api
```

```
test(countries): add TDD test suite for capital lookup

RED phase: 8 unit tests, 7 integration tests written before implementation.
All tests fail as expected (feature not yet implemented).

Jira: PROJ-1-get-country-capital-api
```

## Branch Protection (develop/main)

- Require PR for all merges
- Require at least 1 review (pr-reviewer agent counts)
- Require all CI checks to pass
- Delete branch after merge
- No force pushes to develop/main

## PR Rules

- Title: `{JIRA-ID}: {description}` (max 72 chars)
- Base branch: `develop` (never directly to `main`)
- Must include test results in description
- Must link to Jira ticket
- Use PR template (`.github/PULL_REQUEST_TEMPLATE.md`)

## Tag Format (releases)

Semantic versioning: `v{MAJOR}.{MINOR}.{PATCH}`
- MAJOR: Breaking API changes
- MINOR: New backwards-compatible features
- PATCH: Bug fixes

## Git Flow

```
main (production)
  └── develop (integration)
        └── {JIRA-ID}-{feature} (feature branches)
```

Feature branches are cut from `develop` and merge back to `develop`.
`develop` → `main` via release PR only.
