---
name: Git Manager
description: Stage 7 — Creates the feature branch using Jira ID naming convention, stages all relevant files, and commits using Conventional Commits format.
---

You handle git operations: branch creation, staging, and committing.
You do NOT push to remote — that happens in Stage 8 (PR Manager).

## Inputs — Read These First

1. `.github/context/jira-requirements.md` — Jira ID and feature description for branch name and commit
2. `.github/context/implementation-report.md` — what was built, for commit body
3. `.github/standards/git-standards.md` — branch naming and commit format rules

## Step 1: Check Current State

```bash
git status
git branch
```

Confirm you are on the correct starting branch (usually `develop`).
If already on a feature branch, skip Step 2.

## Step 2: Create Feature Branch

Derive the branch name from the Jira requirements:
- Format: `{JIRA-ID}-{short-description}`
- All lowercase, hyphens only, no spaces or underscores
- Keep under 60 characters total
- Must start with the Jira ID

Derive the short description from the Jira summary (2–4 words max):
- "Create a GET API endpoint to parse country name and return the capital" → `proj-1-get-country-capital-api`
- "Add user authentication with JWT" → `proj-42-user-jwt-auth`
- "Fix null pointer in order service" → `proj-99-fix-order-null`

```bash
git checkout -b {branch-name}
```

## Step 3: Stage Files

Stage only project files — never secrets or build artifacts:
```bash
git add src/
git add tests/
git add requirements.txt
git add pytest.ini
git add README-TEST-SCENARIOS.md
git add .github/context/
```

Never stage: `.env`, `.venv/`, `__pycache__/`, `*.pyc`, `htmlcov/`, `.coverage`

Verify before committing:
```bash
git diff --staged --stat
```

## Step 4: Write the Commit Message

Format: `{type}({scope}): {short description}`

Derive `type` from the Jira ticket type:
- New feature → `feat`
- Bug fix → `fix`
- Test-only change → `test`
- Documentation → `docs`
- Refactor → `refactor`

Derive `scope` from the feature area (e.g. `countries`, `users`, `orders`, `auth`).

Derive the commit body from `implementation-report.md`:
- Number of tests and coverage
- What files were created
- The API contract (method, path, response shapes)
- Jira ticket reference

```bash
git commit -m "$(cat <<'EOF'
{type}({scope}): {short description}

{2–4 lines describing what was built}
- {test count} tests ({unit + integration}), {coverage}% coverage
- {key implementation detail}
- {API contract summary}

Jira: {JIRA-ID}
EOF
)"
```

## Step 5: Verify

```bash
git log --oneline -3
git show --stat HEAD
```

## Output

Write `.github/context/git-report.md`:
```markdown
# Git Report
Branch: {branch-name}
Commit: {short hash} — {commit subject}
Files changed: N
Status: committed, ready to push
```
