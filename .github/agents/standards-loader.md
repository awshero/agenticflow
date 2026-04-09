---
name: Standards Loader
description: Stage 2 — Reads all standards files and compiles an active checklist tailored to the current Jira ticket. Defines the rules that all downstream agents must follow.
---

You compile the project's coding standards into a single actionable checklist
for the current Jira ticket. Every downstream agent consults this file.

## Inputs — Read These First

1. All files in `.github/standards/` — the rule sources
2. `.github/context/codebase-context.md` — to apply stack-specific rules
3. `.github/context/jira-requirements.md` — to highlight rules most relevant to this feature

## Steps

### 1. Read all standards files
Read every file in `.github/standards/`:
- `api-standards.md` — REST design, status codes, response format
- `testing-standards.md` — TDD rules, coverage requirements, naming
- `coding-standards.md` — language-specific quality rules
- `git-standards.md` — branch naming, commit format, PR rules

### 2. Identify stack-specific rules
From `codebase-context.md`, determine:
- Language (Python/Node/etc.) → apply the matching coding rules
- Framework (FastAPI/Express/etc.) → apply the matching API rules
- Test framework (pytest/jest/etc.) → apply the matching test rules

### 3. Highlight feature-relevant rules
From `jira-requirements.md`, identify the feature type:
- New endpoint → highlight URL structure, status codes, response schema rules
- Bug fix → highlight error handling, test coverage for error paths
- Enhancement → highlight backward compatibility, regression testing

## Output

Write `.github/context/active-standards.md`:

```markdown
# Active Standards
Jira: {JIRA_ID} — {summary}
Stack: {language} + {framework}
Generated: {date}

## API Design Rules
- [ ] URLs use nouns not verbs (e.g. /resources/{id} not /getResource)
- [ ] Use correct HTTP status codes: 200 success, 201 created, 400 bad input, 404 not found, 500 server error
- [ ] All responses must be JSON objects — never bare strings or arrays
- [ ] Success response: {field names derived from Jira requirements}
- [ ] Error response: {"detail": "human-readable message"}
- [ ] Content-Type: application/json on every response
- [ ] GET /health returns {"status": "healthy"}

## Testing Rules
- [ ] Tests written BEFORE implementation (TDD RED phase mandatory)
- [ ] Minimum 90% code coverage
- [ ] Unit tests for every service function
- [ ] Integration tests for every HTTP endpoint
- [ ] Test name format: test_{subject}_{condition}_{expected_result}
- [ ] AAA structure: Arrange / Act / Assert
- [ ] Use parametrize for multiple data variants
- [ ] conftest.py for shared fixtures only — no business logic

## Code Quality Rules
- [ ] Type hints on all function signatures
- [ ] Router layer: HTTP handling only — no business logic
- [ ] Service layer: business logic only — no HTTP responses
- [ ] No magic strings or numbers — use named constants
- [ ] No bare except clauses

## Git Rules
- [ ] Branch name: {JIRA-ID}-{short-description} (lowercase, hyphens only)
- [ ] Commit format: {type}({scope}): {description} — Conventional Commits
- [ ] PR targets develop branch
- [ ] PR title: {JIRA-ID}: {description}

## PR Review Gate (all must pass before merge)
- [ ] All tests pass (0 failures)
- [ ] Coverage >= 90%
- [ ] API response schema matches standards
- [ ] All error cases have tests (400, 404)
- [ ] Branch name and commit message comply with git standards
- [ ] README-TEST-SCENARIOS.md is present and accurate
```

If any standards file is missing, note it and apply industry best practices for that domain.
