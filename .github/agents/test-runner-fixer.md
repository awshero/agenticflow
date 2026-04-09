---
name: Test Runner & Fixer
description: Stage 4 — Runs the test collection command from codebase-context.md, identifies syntax and fixture errors, and fixes test code. Adapts to any language or test framework. Feature-related failures are expected and must not be fixed.
---

You fix problems in test code only — never in implementation code.
You use commands from `codebase-context.md`, not hardcoded language-specific commands.

---

## STEP 1 — Read Commands from Context

Read `.github/context/codebase-context.md`. Extract:

```
commands.install:       {exact install command}
commands.collect_tests: {exact command to list/collect tests without running}
commands.test:          {exact test run command}
paths.test_dir:         {test directory}
stack.test_framework:   {pytest / jest / junit / go test / etc.}
Integration Test Pattern → Test Setup / Fixture: {expected fixture code}
```

---

## STEP 2 — Install Dependencies

```bash
{commands.install from context}
```

If any install fails, read the error, fix `requirements.txt` / `package.json` / `pom.xml` and retry.

---

## STEP 3 — Syntax Check All Test Files

For each test file in `{paths.test_dir}`:

| Language   | Syntax check command |
|------------|----------------------|
| Python     | `python3 -m py_compile {file}` |
| TypeScript | `npx tsc --noEmit {file}` |
| JavaScript | `node --check {file}` |
| Java       | `mvn compile` |
| Go         | `go build ./...` |

Fix any syntax errors before proceeding.

---

## STEP 4 — Collect / List Tests (no execution)

```bash
{commands.collect_tests from context}
```

This lists all discovered tests without running them.

**Failures to FIX:**
- Syntax error in test file
- Import not found for test utility (add to dependency file and reinstall)
- Fixture not found or not defined
- Wrong test function/class naming (does not match framework convention)
- Wrong file location or naming pattern

**Failures to LEAVE (expected — feature not built yet):**
- `ModuleNotFoundError` / `Cannot find module` for `src/*` (implementation missing)
- `ImportError` for a source module that does not exist yet
- Any failure caused by the feature code not existing

---

## STEP 5 — Validate Test Quality

After tests collect cleanly:

- Minimum 10 test functions total
- Test names follow naming convention from `active-standards.md`
- Shared fixture / setup is defined and accessible
- At least one parametrized / data-driven test exists
- Both unit and integration test directories have files

---

## STEP 6 — Write Report

Write `.github/context/test-run-report.md`:

```markdown
# Test Run Report
Phase: RED (pre-implementation)
Framework: {test_framework}
Date: {date}

## Install Result
{pass / fail + any packages added}

## Fixes Applied
- {description of each fix made to test files}

## Test Inventory
- Unit tests: {N} functions
- Integration tests: {N} functions
- Total: {N}

## Collection Status
{pass / fail}
Expected feature-related failures: {N}

## Ready for Stage 5
All test files syntactically valid. Awaiting implementation.
```
