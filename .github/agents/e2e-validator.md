---
name: E2E Validator
description: Stage 10 — Hits the deployed API and validates every Jira acceptance criterion is met. This is the final gate before the feature is considered done.
---

You validate the deployed API against every acceptance criterion in the Jira ticket.
This runs AFTER the user has deployed the feature to their target environment (local or AWS).

## Step 1: Get API Base URL

Ask the user: "What is the base URL of the deployed API?"
Examples: `http://localhost:8000` or `https://api.example.com`

Set `BASE_URL` to the provided value.

## Step 2: Health Check (abort if fails)

```bash
STATUS=$(curl -s -o /dev/null -w "%{http_code}" {BASE_URL}/health)
echo "Health: $STATUS"
```

If not 200, stop and report: "API is not reachable at {BASE_URL}. Confirm the service is running."

## Step 3: Run All E2E Scenarios

Test every acceptance criterion from `.github/context/jira-requirements.md`.

### Happy Path Tests
```bash
# France → Paris
echo "--- France ---"
curl -s -w "\nStatus: %{http_code}\n" {BASE_URL}/countries/France/capital

# Japan → Tokyo
echo "--- Japan ---"
curl -s -w "\nStatus: %{http_code}\n" {BASE_URL}/countries/Japan/capital

# Multi-word country
echo "--- United States ---"
curl -s -w "\nStatus: %{http_code}\n" "{BASE_URL}/countries/United%20States/capital"
```

### Case Insensitivity Tests
```bash
echo "--- france (lowercase) ---"
curl -s -w "\nStatus: %{http_code}\n" {BASE_URL}/countries/france/capital

echo "--- GERMANY (uppercase) ---"
curl -s -w "\nStatus: %{http_code}\n" {BASE_URL}/countries/GERMANY/capital
```

### Not Found Tests
```bash
echo "--- Wakanda (unknown) ---"
curl -s -w "\nStatus: %{http_code}\n" {BASE_URL}/countries/Wakanda/capital
# Must be 404 with {"detail": "..."}
```

### Invalid Input Tests
```bash
echo "--- 123 (digits) ---"
curl -s -w "\nStatus: %{http_code}\n" {BASE_URL}/countries/123/capital
# Must be 400

echo "--- space only ---"
curl -s -w "\nStatus: %{http_code}\n" "{BASE_URL}/countries/%20/capital"
# Must be 400
```

### Response Format Test
```bash
echo "--- Content-Type header ---"
curl -sI {BASE_URL}/countries/France/capital | grep -i content-type
# Must contain: application/json
```

### Performance Test
```bash
echo "--- Response time ---"
TIME=$(curl -s -o /dev/null -w "%{time_total}" {BASE_URL}/countries/France/capital)
echo "Response time: ${TIME}s"
# Target: < 0.5s
```

## Step 4: Map Results to Acceptance Criteria

Read `.github/context/jira-requirements.md` and map each AC to its test result:

| AC | Requirement | HTTP Test | Result |
|----|-------------|-----------|--------|
| AC1 | Endpoint exists | GET /countries/France/capital → 200 | PASS/FAIL |
| AC2 | Returns capital | body.capital == "Paris" | PASS/FAIL |
| AC3 | 404 for unknown | GET /countries/Wakanda/capital → 404 | PASS/FAIL |
| AC4 | 400 for invalid | GET /countries/123/capital → 400 | PASS/FAIL |
| AC5 | Case insensitive | GET /countries/france/capital → 200 | PASS/FAIL |
| AC6 | Multi-word country | GET /countries/United%20States/capital → 200 | PASS/FAIL |
| AC7 | JSON Content-Type | Header present | PASS/FAIL |
| AC8 | Health check | GET /health → 200 | PASS/FAIL |

## Step 5: Final Report

Write `.github/context/e2e-report.md`:
```markdown
# E2E Validation Report
Date: {date}
API URL: {BASE_URL}
Jira: {JIRA_ID}

## Results
- Total scenarios: N
- Passed: N
- Failed: N

## Acceptance Criteria
{table from Step 4}

## FINAL STATUS: REQUIREMENTS MET / REQUIREMENTS NOT MET
```

If ALL pass: print "TDD Pipeline Complete — All requirements validated end-to-end."
If ANY fail: print the failures clearly and suggest fixes.
