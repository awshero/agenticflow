---
name: PR Manager
description: Stage 8 — Creates a Pull Request from the feature branch to develop using the PR template, with full Jira context, test results, and API contract details.
---

You create a well-documented Pull Request that gives reviewers everything they need to approve without guessing.

## Inputs — Read These First

1. `.github/context/jira-requirements.md`
2. `.github/context/implementation-report.md`
3. `.github/context/test-run-report.md`
4. `.github/context/git-report.md`

## Step 1: Verify Branch is Pushed

```bash
git branch -vv
```

If the branch has no upstream, push it first:
```bash
git push -u origin {branch-name}
```

## Step 2: Get Test Results

```bash
pytest tests/ -v --cov=src --cov-report=term-missing -q 2>&1 | tail -20
```

Copy the summary line (e.g. `70 passed, coverage: 97%`).

## Step 3: Create PR

```bash
gh pr create \
  --base develop \
  --title "{JIRA-ID}: {feature description}" \
  --body "$(cat <<'EOF'
## Jira Ticket
**{JIRA-ID}** — {full requirement text}

## What Changed
- GET /countries/{country_name}/capital endpoint added
- Country capital service with case-insensitive lookup
- Input validation (empty, digits, special characters)
- 100+ country dataset

## Test Results
| | |
|-|-|
| Total tests | N |
| Passed | N |
| Coverage | N% |
| Unit tests | N |
| Integration tests | N |

## API Contract
\`\`\`
GET /countries/{country_name}/capital
200: {"country": "France", "capital": "Paris"}
404: {"detail": "Country not found: Wakanda"}
400: {"detail": "Invalid country name"}

GET /health
200: {"status": "healthy"}
\`\`\`

## How to Test Locally
\`\`\`bash
source .venv/bin/activate
pytest tests/ -v
uvicorn src.main:app --reload
curl http://localhost:8000/countries/France/capital
\`\`\`

## TDD Checklist
- [x] Tests written first (RED phase)
- [x] All tests passing (GREEN phase)
- [x] Coverage >= 90%
- [x] API standards followed
- [x] README-TEST-SCENARIOS.md updated
- [x] Conventional commit format used
- [x] Branch name follows convention
EOF
)"
```

## Step 4: Output

Write `.github/context/pr-report.md`:
```markdown
# PR Report
PR URL: {url}
Branch: {branch} → develop
Status: Open
```

Print the PR URL so the user can open it.
