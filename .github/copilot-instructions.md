# GitHub Copilot — TDD Pipeline Instructions

This repository follows a strict **Test-Driven Development (TDD)** pipeline.
Copilot must follow these rules in every suggestion, edit, and agent task.

---

## TDD Workflow (mandatory)

Always follow RED → GREEN → REFACTOR:
1. **RED**: Write failing tests first. Never write implementation before tests.
2. **GREEN**: Write the minimal code to make tests pass.
3. **REFACTOR**: Clean up without breaking tests.

---

## Project Structure

```
src/
├── main.py              # FastAPI app entry point
├── routers/             # HTTP route handlers only (no business logic)
├── services/            # Business logic and validation
└── data/                # Static data and constants

tests/
├── conftest.py          # Shared pytest fixtures
├── unit/                # Unit tests (test service layer in isolation)
└── integration/         # Integration tests (test full HTTP cycle via TestClient)

.github/
├── prompts/             # Copilot agent prompt files (one per TDD stage)
├── standards/           # Coding, API, testing, and git standards
├── context/             # Jira requirements and pipeline state
└── workflows/           # GitHub Actions CI/CD pipelines
```

---

## Standards (always apply)

### API Design
- Use nouns in URLs: `/countries/{name}/capital` not `/getCapital`
- Status codes: 200 success, 400 bad input, 404 not found, 500 server error
- All responses must be JSON: `{"field": value}` — no bare strings
- Error responses: `{"detail": "human-readable message"}`

### Python / FastAPI
- All function signatures must have type hints
- Routers handle HTTP only — no business logic
- Services handle business logic — return domain values, not HTTP responses
- Use `Optional[str]` for Python 3.9, `str | None` for 3.10+
- Imports order: stdlib → third-party → local

### Testing
- Minimum 90% code coverage (enforced by pytest.ini)
- Test naming: `test_{subject}_{condition}_{expected_result}`
- AAA pattern: Arrange / Act / Assert
- Use `@pytest.mark.parametrize` for multiple data variants
- `conftest.py` for shared fixtures only

### Git
- Branch format: `{JIRA-ID}-{short-description}` (lowercase, hyphens)
- Commit format: `{type}({scope}): {description}` (Conventional Commits)
- PR base branch: `develop`

---

## Copilot Agent Prompts

The following prompt files are available in `.github/prompts/`. Invoke them in
Copilot Chat using `@workspace` and referencing the prompt file:

| Prompt File | Stage | Purpose |
|-------------|-------|---------|
| `tdd-orchestrator.prompt.md` | Entry | Run the full pipeline |
| `context-builder.prompt.md` | 1 | Scan codebase and build context |
| `standards-loader.prompt.md` | 2 | Compile active standards |
| `test-generator.prompt.md` | 3 | Write all tests (RED phase) |
| `test-runner-fixer.prompt.md` | 4 | Run and fix test issues |
| `feature-developer.prompt.md` | 5 | Implement feature (GREEN phase) |
| `doc-generator.prompt.md` | 6 | Generate README-TEST-SCENARIOS.md |
| `git-manager.prompt.md` | 7 | Branch, commit, push |
| `pr-manager.prompt.md` | 8 | Create pull request |
| `pr-reviewer.prompt.md` | 9 | Review and merge PR |
| `e2e-validator.prompt.md` | 10 | End-to-end API validation |
