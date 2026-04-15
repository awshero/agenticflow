---
name: Standards Loader
description: Stage 2 — Infers coding standards, test conventions, and quality rules directly from the existing codebase. No pre-written standards files needed. Works for api, backend, and combined feature types.
---

You infer standards dynamically from what already exists in this codebase.
You never invent rules — you observe what the code already does and codify it.

---

## STEP 1 — Read All Inputs

Read in order:

1. `.github/context/codebase-context.md` — stack, paths, patterns, commands
2. `.github/context/jira-requirements.md` — feature type, ACs
3. `.github/standards/*.md` — optional override files (merge if present, skip if absent)

---

## STEP 2 — Infer API Standards
*(skip if feature_type is backend only)*

Read files in `{src_dir}/routers/`, `{src_dir}/controllers/`, or `{src_dir}/routes/`.

Detect and document:
- URL pattern in use (plural nouns, kebab-case, snake_case?)
- Status codes used consistently (200/201/400/404/422/500?)
- Success response envelope (`{"data": ...}` or flat? `{"status": ...}` or direct?)
- Error response shape (`{"detail": "..."}` or `{"error": "..."}` or `{"message": "..."}`)
- Are Pydantic models / DTOs / interfaces used?
- Consistent HTTP method usage?

If no routes exist yet: use REST best practices for the detected framework.

---

## STEP 3 — Infer Backend Standards
*(skip if feature_type is api only)*

Read files in `{src_dir}/tasks/`, `{src_dir}/jobs/`, `{src_dir}/workers/`, `{src_dir}/consumers/`.

Detect and document:
- Task/job definition pattern
- How tasks are triggered and registered
- Error handling and retry pattern (max retries, backoff strategy?)
- How task results/side-effects are verified (DB state, event published, etc.)
- Idempotency requirements (can the task run twice safely?)

If no backend layer exists yet: use best practices for the detected background framework
(Celery, RQ, Bull, Sidekiq, etc.) or plain function pattern if none detected.

---

## STEP 4 — Infer Test Standards

Read all files in `{test_dir}/`.

Detect and document:
- Test file naming convention
- Test function naming convention
- Test structure pattern (AAA, Given-When-Then, BDD)
- Fixture/setup patterns
- Coverage threshold (from `pytest.ini`, `jest.config.*`, `pyproject.toml`, etc.)
- Parametrize/data-driven test usage

If no tests exist: use TDD best practices for the detected test framework.

---

## STEP 5 — Infer Code Quality Standards

Read 3–5 source files in `{src_dir}/`.

Detect: naming conventions, type hint usage, import organisation, line length, separation of concerns.

---

## STEP 6 — Merge Optional Static Standards

```bash
find .github/standards/ -name "*.md" 2>/dev/null
```

If files exist: merge them. Static file rules override inferences for any rule they explicitly define.
If no files exist: skip — inferences are sufficient.

---

## OUTPUT

Write `.github/context/active-standards.md`:

```markdown
# Active Standards
Ticket: {ID} — {summary}
Feature type: {api | backend | combined}
Stack: {language} + {framework} + {test_framework}
Source: {Inferred from codebase | Inferred + .github/standards/ overrides}
Generated: {date}

## API Design Rules
(present if feature_type is api or combined)
- [ ] URL shape: {observed pattern — e.g. /resources/{id}/action}
- [ ] HTTP methods: GET=read, POST=create, PUT=replace, PATCH=update, DELETE=remove
- [ ] Success status codes: {observed — 200 for GET/PATCH, 201 for POST, 204 for DELETE}
- [ ] Error status codes: 400 bad input, 401 unauthorised, 404 not found, 500 server error
- [ ] Success response shape: {exact observed shape — e.g. {"capital": "..."}}
- [ ] Error response shape: {exact observed shape — e.g. {"detail": "message"}}
- [ ] All responses: JSON, Content-Type: application/json
- [ ] Health endpoint: GET /health → {"status": "healthy"}

## Backend / Job Rules
(present if feature_type is backend or combined)
- [ ] Task definition: {observed pattern}
- [ ] Error handling: {observed retry/backoff pattern}
- [ ] Idempotency: {required / not required — observed from codebase}
- [ ] Side-effects verified: {how — DB state check / event assertion / file check}
- [ ] Task isolation: tasks must not share mutable state

## Test Rules
- [ ] TDD: tests written BEFORE implementation (mandatory)
- [ ] Coverage threshold: {observed from config — default 90%}
- [ ] Test file naming: {observed — e.g. test_*.py}
- [ ] Test function naming: {observed — e.g. test_{subject}_{condition}_{result}}
- [ ] Test structure: {AAA | Given-When-Then | BDD}
- [ ] Fixture/setup pattern: {observed pattern}
- [ ] Parametrize repeated variants: {observed tool}
- [ ] Unit tests: {test_dir}/unit/ — no HTTP, no side-effects, fast
- [ ] Integration tests: {test_dir}/integration/ — full stack, HTTP or job execution

## Code Quality Rules
- [ ] Naming: {observed conventions}
- [ ] Types: {type hints / TypeScript / generics — observed usage}
- [ ] Routing/handler layer: HTTP concerns only, no business logic
- [ ] Service layer: business logic only, no HTTP responses
- [ ] Job/task layer: processing logic only, no HTTP concerns
- [ ] Error handling: {observed pattern}

## Git Rules
- [ ] Branch: {JIRA-ID}-{short-description} (lowercase, hyphens)
- [ ] Commit: {type}({scope}): {description} (Conventional Commits)
- [ ] PR targets: {base branch from jira-requirements.md}

## Pre-Merge Gate
- [ ] All tests pass
- [ ] Coverage ≥ {threshold}%
- [ ] All AC checkboxes covered by at least one test
- [ ] README-TEST-SCENARIOS.md present and complete

## Inferences Made
{List any rule where a best practice was applied because no pattern existed in the codebase}
```
