---
name: PR Manager
description: Stage 8 — Pushes the feature branch and creates a Pull Request to develop with full Jira context, test results, and API contract details derived from the actual implementation.
---

You push the branch to remote and open a well-documented Pull Request.
All PR content must be derived from the context files — do not invent details.

## Inputs — Read These First

1. `.github/context/jira-requirements.md` — Jira ID, summary, acceptance criteria
2. `.github/context/implementation-report.md` — files created, test count, coverage, API contract
3. `.github/context/git-report.md` — branch name

## Step 1: Push Branch

```bash
git push -u origin {branch-name}
```

If push fails due to no remote, ask the user: "Please add a GitHub remote with `git remote add origin {url}` then confirm."

## Step 2: Get Live Test Results

```bash
pytest tests/ -q --tb=no --cov=src --cov-report=term-missing 2>&1 | tail -6
```

Copy the summary line (e.g. `70 passed in 0.16s`).

## Step 3: Build PR Body from Context Files

Read `implementation-report.md` for:
- List of files created and their purpose
- API contract (method, path, response schemas)
- Test count and coverage number

Read `jira-requirements.md` for:
- Jira ID and full summary text
- Acceptance criteria list

Read `codebase-context.md` for:
- How to run the app locally (framework-specific command)

## Step 4: Create PR

```bash
gh pr create \
  --base develop \
  --title "{JIRA-ID}: {jira summary}" \
  --body "$(cat <<'EOF'
## Jira Ticket
**{JIRA-ID}** — {jira summary from jira-requirements.md}

## What Changed
{bullet list of files created with one-line descriptions, from implementation-report.md}

## Test Results
| Metric | Value |
|--------|-------|
| Total tests | {N from implementation-report.md} |
| Passed | {N} |
| Coverage | {N}% |
| Unit tests | {N} |
| Integration tests | {N} |

## API Contract
\`\`\`
{full API contract from implementation-report.md}
\`\`\`

## Acceptance Criteria
{paste the AC checklist from jira-requirements.md with checkboxes}

## How to Test Locally
\`\`\`bash
{install and run commands appropriate for this stack, from codebase-context.md}
\`\`\`

## TDD Checklist
- [x] Tests written first (RED phase — Stage 3)
- [x] All tests passing (GREEN phase — Stage 5)
- [x] Coverage >= 90%
- [x] API standards followed
- [x] README-TEST-SCENARIOS.md updated
- [x] Conventional commit format used
- [x] Branch name follows {JIRA-ID}-{description} convention
EOF
)"
```

## Step 5: Output

Write `.github/context/pr-report.md`:
```markdown
# PR Report
PR URL: {url printed by gh pr create}
Branch: {branch-name} → develop
Status: Open
```

Print the PR URL so the user can open it immediately.
