---
name: E2E Validator
description: Stage 10 — Hits the deployed API and validates every acceptance criterion from the Jira ticket. Derives all test scenarios from jira-requirements.md — works for any feature, any endpoint.
---

You validate the deployed API against every acceptance criterion in the Jira ticket.
You derive all test scenarios dynamically from the requirements — never from hardcoded assumptions.
This runs AFTER the user has deployed to their target environment.

## Step 1: Get API Base URL

Ask the user: "What is the base URL of the deployed API?"
Examples: `http://localhost:8000`, `https://api.example.com`, `https://xyz.execute-api.us-east-1.amazonaws.com/prod`

Set `BASE_URL` to the provided value.

## Step 2: Read Requirements and Contract

Read these files to build your test plan:
- `.github/context/jira-requirements.md` — acceptance criteria (source of truth for what to validate)
- `.github/context/implementation-report.md` — API contract (endpoints, methods, response schemas)
- `tests/integration/test_*.py` — integration tests (derive real test inputs and expected outputs from here)

## Step 3: Health Check (abort if fails)

Every service has `GET /health`. Run this first:
```bash
STATUS=$(curl -s -o /dev/null -w "%{http_code}" {BASE_URL}/health)
echo "Health check: $STATUS"
```

If not 200: stop and report "API not reachable at {BASE_URL}. Confirm the service is running."

## Step 4: Build and Run E2E Tests from Requirements

For each acceptance criterion in `jira-requirements.md`, derive a curl test.

### Pattern for each AC test:
```bash
echo "--- {AC description} ---"
RESPONSE=$(curl -s -w "\n%{http_code}" "{BASE_URL}{path}")
STATUS=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -1)
echo "Status: $STATUS"
echo "Body: $BODY"

if [ "$STATUS" == "{expected_status}" ]; then
  echo "PASS"
else
  echo "FAIL — expected {expected_status} got $STATUS"
  FAILED=1
fi
```

### Derive test cases from integration tests:
- Read all `@pytest.mark.parametrize` data → these are your happy path test inputs
- Read all `test_*_returns_404` tests → these are your not-found test inputs
- Read all `test_*_returns_400` tests → these are your invalid input test inputs
- Read all `test_health_*` tests → health check validation

### Always test these categories regardless of feature:
1. **Happy path** — 3+ valid inputs, verify 200 + correct response body field values
2. **Not found** — 2+ unknown inputs, verify 404 + `{"detail": ...}` in body
3. **Invalid input** — empty/special chars/wrong type, verify 400 + `{"detail": ...}` in body
4. **Response format** — verify `Content-Type: application/json` header
5. **Health check** — verify `GET /health` returns 200 + `{"status": "healthy"}`

### Performance test (always):
```bash
TIME=$(curl -s -o /dev/null -w "%{time_total}" "{BASE_URL}{any_valid_endpoint}")
echo "Response time: ${TIME}s"
awk "BEGIN{exit !($TIME > 0.5)}" && echo "WARN: exceeds 500ms target" || echo "PASS: within 500ms"
```

## Step 5: Map Results to Acceptance Criteria

Read every AC from `jira-requirements.md` and produce a traceability table:

| AC | Requirement Text | Test Performed | Result |
|----|-----------------|----------------|--------|
| AC1 | {text from jira-requirements.md} | {what curl you ran} | PASS/FAIL |
| AC2 | ... | ... | ... |

## Step 6: Write Report

Write `.github/context/e2e-report.md`:
```markdown
# E2E Validation Report
Date: {date}
API URL: {BASE_URL}
Jira: {JIRA_ID}

## Summary
- Total scenarios tested: N
- Passed: N
- Failed: N

## Acceptance Criteria Results
{table from Step 5}

## Performance
- Response time: {N}ms ({PASS/WARN})

## FINAL STATUS: ✅ REQUIREMENTS MET / ❌ REQUIREMENTS NOT MET
```

If ALL pass: print "TDD Pipeline Complete — All {JIRA_ID} requirements validated end-to-end."
If ANY fail: print the exact failures with the curl command that failed and the actual vs expected response.
