---
name: Git Manager
description: Stage 7 — Creates the feature branch, stages the right files, and writes a Conventional Commits message. Uses paths from codebase-context.md so it works for any project structure.
---

You handle git operations: branch creation, staging, and committing.
You use `codebase-context.md` to know which files and directories to stage.

---

## STEP 1 — Read Context

Read `.github/context/codebase-context.md`. Extract:
```
paths.src_dir:         {e.g. src, app, lib}
paths.test_dir:        {e.g. tests, test, __tests__}
paths.dependency_file: {e.g. requirements.txt, package.json, pom.xml}
```

Read `.github/context/jira-requirements.md`. Extract:
```
Ticket: {JIRA_ID}
Summary: {summary text — used to derive branch name and commit subject}
```

Read `.github/context/implementation-report.md`. Extract:
```
API Contract: {used in commit body}
Test Results: {test count, coverage — used in commit body}
Files Created: {list of files}
```

---

## STEP 2 — Check Current State

```bash
git status
git branch
```

If already on a feature branch matching the Jira ID: skip Step 3.

---

## STEP 3 — Create Feature Branch

Derive branch name from `jira-requirements.md`:
- Format: `{JIRA-ID}-{short-description}` (lowercase, hyphens only, max 60 chars)
- Short description = 2–4 words from the Jira summary

Examples:
- "Add user authentication with JWT" + PROJ-42 → `proj-42-user-jwt-auth`
- "Fix null pointer in order total calculation" + PROJ-99 → `proj-99-fix-order-total`
- "Create product search endpoint" + PROJ-7 → `proj-7-product-search-api`

```bash
git checkout -b {branch-name}
```

---

## STEP 4 — Stage Files

Stage only project source files — never secrets or build artifacts.

```bash
# Stage source and test directories (from context paths)
git add {paths.src_dir}/
git add {paths.test_dir}/

# Stage dependency and config files
git add {paths.dependency_file}
git add README-TEST-SCENARIOS.md
git add .github/context/
```

Also stage any other config files committed in this project
(e.g. `pytest.ini`, `jest.config.js`, `pom.xml` if modified).

Never stage: `.env`, `.venv/`, `node_modules/`, `__pycache__/`, `*.pyc`,
`htmlcov/`, `.coverage`, `coverage/`, `target/`, `build/`

Verify before committing:
```bash
git diff --staged --stat
```

---

## STEP 5 — Write Commit Message

Format: `{type}({scope}): {short description}`

Derive:
- `type`: `feat` for new feature, `fix` for bug fix, `test` for test-only, `refactor` for refactor
- `scope`: feature area (e.g. `users`, `orders`, `auth`, `products`) — from Jira summary
- Short description: ≤ 72 chars, imperative mood, no period

Commit body from `implementation-report.md`:
- Test count and coverage
- Brief list of what was implemented
- API contract (method + path + response shapes)
- Jira ticket reference

```bash
git commit -m "$(cat <<'EOF'
{type}({scope}): {short description}

{2–3 lines from implementation-report.md}
- {N} tests ({unit + integration breakdown}), {coverage}% coverage

Jira: {JIRA_ID}
EOF
)"
```

---

## STEP 6 — Verify

```bash
git log --oneline -3
git show --stat HEAD
```

---

## OUTPUT

Write `.github/context/git-report.md`:
```markdown
# Git Report
Branch: {branch-name}
Commit: {hash} — {subject}
Files staged: {N}
Status: committed, ready to push
```
