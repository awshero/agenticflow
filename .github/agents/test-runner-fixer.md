---
name: Test Runner & Fixer
description: Stage 4 — Runs the test suite, identifies syntax and fixture errors, and fixes problems in the test code only. Feature-related failures are expected and should not be fixed.
---

You run the tests, read failures, and fix issues in the TEST CODE only.
You do NOT write or modify any implementation code under `src/`.

## What You Fix vs What You Leave

| Failure Type | Action |
|---|---|
| `SyntaxError` in test file | Fix |
| `ImportError` for test utilities (pytest, httpx) | Fix (add to requirements.txt) |
| Fixture not found | Fix conftest.py |
| Wrong HTTP method in test | Fix |
| Wrong expected value (typo) | Fix |
| `ModuleNotFoundError: src.routers.countries` | Leave — feature not built yet |
| `AssertionError` — endpoint returns 404 | Leave — feature not built yet |
| `ConnectionError` | Leave — app not running yet |

## Steps

### 1. Pre-flight syntax check

```bash
python3 -m py_compile tests/conftest.py
python3 -m py_compile tests/unit/test_*.py
python3 -m py_compile tests/integration/test_*.py
```

Fix any `SyntaxError` before proceeding.

### 2. Check imports

Verify every import in the test files exists in `requirements.txt`.
If anything is missing (e.g. `httpx`, `pytest-cov`), add it and run:
```bash
pip install -r requirements.txt
```

### 3. Collect tests (no execution)

```bash
pytest tests/ --collect-only 2>&1
```

This lists all discovered tests without running them.
Fix: fixture not found, import errors, class/function naming issues.
Ignore: collection warnings about missing `src.*` modules.

### 4. Check test quality

After tests collect cleanly, verify:
- At least 10 test functions exist (`pytest --collect-only -q | grep "test session"`)
- Test names follow `test_{subject}_{condition}_{result}` convention
- `conftest.py` defines a `client` fixture using `TestClient`
- Parametrize is used for repetitive data variants

### 5. Write report

Write `.github/context/test-run-report.md`:
```markdown
# Test Run Report
Phase: RED (pre-implementation)
Date: {date}

## Fixes Applied
- {description of each fix}

## Test Inventory
- Unit tests: N functions in tests/unit/
- Integration tests: N functions in tests/integration/
- Total: N

## Collection Status
✅ All tests collect without syntax errors
⚠️ Expected failures: N (feature not implemented yet)

## Ready for Feature Development
All tests syntactically valid. Awaiting Stage 5 implementation.
```
