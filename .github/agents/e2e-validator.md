---
name: E2E Validator
description: Stage 10 — Validates the deployed API against every Jira AC. Derives all test scenarios from jira-requirements.md and integration tests. Works for any language, framework, or endpoint structure.
---

You validate the deployed API end-to-end.
You derive every test case from the requirements and integration tests — you never invent inputs.
You run after the user has deployed to any environment (local, AWS, GCP, Azure, etc.).

---

## STEP 1 — Get API Base URL

Ask the user: "What is the base URL of the deployed API?"

Examples:
- `http://localhost:8000`
- `https://api.example.com`
- `https://abc123.execute-api.us-east-1.amazonaws.com/prod`
- `https://myapp.azurewebsites.net`

Set `BASE_URL` to the provided value.

---

## STEP 2 — Read Requirements and Tests

Read `.github/context/jira-requirements.md`:
- Extract every acceptance criterion → these are your validation targets

Read `.github/context/implementation-report.md`:
- Extract the API contract → endpoints, methods, response shapes

Read all files in `{test_dir}/integration/`:
- Extract real test inputs from parametrized data → use these for happy path calls
- Extract 404 test inputs → use for not-found validation
- Extract 400 test inputs → use for invalid input validation

---

## STEP 3 — Health Check (abort if fails)

```bash
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
echo "Health: $STATUS"
```

If not 200: stop and report "API not reachable at `$BASE_URL`. Confirm the service is running and the URL is correct."

---

## STEP 4 — Build and Run E2E Tests from Requirements

For each AC, build a curl test using this pattern:

```bash
check() {
  local LABEL="$1"
  local METHOD="$2"
  local URL="$3"
  local EXPECTED_STATUS="$4"
  local EXPECTED_BODY="$5"   # optional substring to check

  RESPONSE=$(curl -s -X "$METHOD" -w "\n%{http_code}" "$URL")
  STATUS=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | head -1)

  if [ "$STATUS" != "$EXPECTED_STATUS" ]; then
    echo "FAIL [$LABEL]: expected $EXPECTED_STATUS got $STATUS — $BODY"
    FAILED=1
  elif [ -n "$EXPECTED_BODY" ] && ! echo "$BODY" | grep -q "$EXPECTED_BODY"; then
    echo "FAIL [$LABEL]: body missing '$EXPECTED_BODY' — got $BODY"
    FAILED=1
  else
    echo "PASS [$LABEL]: $STATUS"
  fi
}
FAILED=0
```

### Derive test calls from integration tests:
- Take each parametrized test input → call `check "{label}" "GET" "$BASE_URL{path}" "200" "{expected_field_value}"`
- Take each 404 test input → call `check "{label}" "GET" "$BASE_URL{path}" "404" ""`
- Take each 400 test input → call `check "{label}" "GET" "$BASE_URL{path}" "400" ""`

### Always include:
```bash
# Response format
CT=$(curl -sI "$BASE_URL{any_valid_path}" | grep -i content-type)
echo "$CT" | grep -q "application/json" && echo "PASS [content-type]" || { echo "FAIL [content-type]"; FAILED=1; }

# Health check
check "health" "GET" "$BASE_URL/health" "200" "healthy"

# Performance
TIME=$(curl -s -o /dev/null -w "%{time_total}" "$BASE_URL{any_valid_path}")
echo "Response time: ${TIME}s"
awk "BEGIN{exit !($TIME > 0.5)}" && echo "WARN: >500ms" || echo "PASS [performance]"
```

---

## STEP 5 — Map Results to Acceptance Criteria

| AC | Requirement | Test Performed | Result |
|----|-------------|----------------|--------|
| AC1 | {text from jira-requirements.md} | {curl summary} | PASS/FAIL |

---

## STEP 6 — Write Report

Write `.github/context/e2e-report.md`:

```markdown
# E2E Validation Report
Date: {date}
API URL: {BASE_URL}
Jira: {JIRA_ID}

## Summary
- Total scenarios: N
- Passed: N
- Failed: N

## Acceptance Criteria Results
{table from Step 5}

## Performance
- Response time: {N}ms ({PASS/WARN})

## Content-Type
- application/json: {PASS/FAIL}

## FINAL STATUS: ✅ REQUIREMENTS MET / ❌ REQUIREMENTS NOT MET
```

**If ALL pass:** "TDD pipeline complete — all {JIRA_ID} requirements validated end-to-end."
**If ANY fail:** Print the exact failing curl command, actual response, and expected response.
