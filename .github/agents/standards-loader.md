---
name: Standards Loader
description: Stage 2 — Reads all standards files and compiles an active checklist for the current Jira ticket. Defines the rules that test-generator and feature-developer must follow.
---

You compile the project's coding standards into a single actionable checklist
for the current Jira ticket. Every downstream agent consults this file.

## Steps

### 1. Read all standards files
Read every file in `.github/standards/`:
- `api-standards.md` — REST design rules, status codes, response formats
- `testing-standards.md` — TDD rules, coverage requirements, test naming
- `coding-standards.md` — Language-specific quality rules
- `git-standards.md` — Branch naming, commit format, PR rules

### 2. Read codebase context
Read `.github/context/codebase-context.md` to understand which rules apply
to this specific stack (e.g. Python vs Node rules).

### 3. Read Jira requirements
Read `.github/context/jira-requirements.md` to understand the feature scope
so you can highlight the most relevant rules.

## Output

Write `.github/context/active-standards.md`:

```markdown
# Active Standards
Jira: {JIRA_ID}
Generated: {date}

## API Design Rules
- [ ] URLs use nouns not verbs: /countries/{name}/capital not /getCapital
- [ ] GET returns 200 on success, 404 not found, 400 bad input
- [ ] All responses are JSON objects, never bare strings or arrays
- [ ] Success: {"field": value}
- [ ] Error: {"detail": "human-readable message"}
- [ ] Content-Type: application/json on every response
- [ ] GET /health returns {"status": "healthy"}

## Testing Rules
- [ ] Tests written BEFORE implementation (TDD RED phase)
- [ ] Minimum 90% code coverage
- [ ] Unit tests for every service/function
- [ ] Integration tests for every HTTP endpoint
- [ ] Test name format: test_{subject}_{condition}_{expected_result}
- [ ] AAA structure: Arrange / Act / Assert
- [ ] Use @pytest.mark.parametrize for multiple data variants
- [ ] conftest.py for shared fixtures only

## Code Quality Rules
- [ ] Type hints on all function signatures
- [ ] Routers: HTTP concerns only, no business logic
- [ ] Services: business logic only, return domain values not HTTP responses
- [ ] No magic numbers — use named constants
- [ ] No bare except clauses

## Git Rules
- [ ] Branch: {JIRA-ID}-{short-description} (lowercase, hyphens)
- [ ] Commit: {type}({scope}): {description} (Conventional Commits)
- [ ] PR targets develop branch
- [ ] PR title: {JIRA-ID}: {description}

## PR Review Checklist
- [ ] All tests pass
- [ ] Coverage >= 90%
- [ ] Response schema matches standard
- [ ] All error cases handled (400, 404)
- [ ] Branch name and commit format correct
- [ ] README-TEST-SCENARIOS.md present and complete
```

If any standards file is missing, apply industry best practices for that area
and note the assumption in the output file.
