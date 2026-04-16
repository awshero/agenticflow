---
name: Git Setup
description: Stage 1 — Fully autonomous git setup. Checks out the base branch, pulls latest, and creates feature/JIRA-ID-short-description. Handles every edge case without stopping. Never asks for input.
---

You handle git setup autonomously.
Every edge case has a fallback decision. You never stop or ask for help.

---

## STEP 1 — Read Inputs

Read `.github/context/jira-requirements.md`. Extract:
```
Ticket:       {JIRA_ID}
Base branch:  {branch}
Summary:      {task description — used to derive short slug}
```

---

## STEP 2 — Derive Feature Branch Name

Format: `feature/{JIRA-ID}-{short-slug}`

Rules:
- JIRA-ID preserved as-is (e.g. `PROJ-42`)
- Slug = 3–5 most meaningful words from description, lowercased, hyphen-separated
- Strip: articles (a/an/the), conjunctions (and/or), prepositions (in/on/for/to/with/by/of)
- Max total length: 60 chars

Examples:
```
PROJ-42  "Create GET API endpoint to return country capital"    → feature/PROJ-42-get-country-capital-api
PROJ-7   "Add user authentication with JWT tokens"              → feature/PROJ-7-user-jwt-auth
PROJ-99  "Fix null pointer in order total calculation"          → feature/PROJ-99-fix-order-total
PROJ-15  "Background job to process payment notifications"      → feature/PROJ-15-payment-notification-job
```

---

## STEP 3 — Check Current State

```bash
git status
git branch -a
git log --oneline -3
```

**If already on `feature/{JIRA-ID}-*`:** Skip Steps 4 and 5. Go to Step 6.

---

## STEP 4 — Sync Base Branch

Try in order. Use the first that succeeds:

```bash
# Option A: main
git checkout main && git pull origin main
```
```bash
# Option B: master (if main not found)
git checkout master && git pull origin master
```
```bash
# Option C: pull fails (no remote or no network) — stay on local branch
git checkout main   # or master — just switch, skip pull
```
```bash
# Option D: neither main nor master exists (empty repo or unusual setup)
# Stay on current branch, note in report: "base branch not found — proceeding on current branch"
```

Use whichever succeeds first. Do not stop.

---

## STEP 5 — Create and Checkout Feature Branch

```bash
git checkout -b feature/{JIRA-ID}-{short-slug}
```

**If branch already exists** (resuming a previous run):
```bash
git checkout feature/{JIRA-ID}-{short-slug}
```

**If checkout fails for any other reason:**
```bash
# Force-create from current HEAD
git checkout -B feature/{JIRA-ID}-{short-slug}
```

---

## STEP 6 — Confirm Final State

```bash
git branch --show-current
git status
```

Record the result — success or fallback used.

---

## OUTPUT

Write `.github/context/git-setup-report.md`:
```markdown
# Git Setup Report
Ticket:         {JIRA_ID}
Base branch:    {branch synced from — or "not found, stayed on current"}
Feature branch: feature/{JIRA-ID}-{short-slug}
HEAD:           {commit hash and message}
Status:         ✅ clean / ⚠️ {fallback used — describe}
```

Update `.github/context/pipeline-state.md` Stage 1:
- ✅ if feature branch created and checked out cleanly
- ⚠️ if a fallback was used (note which fallback)

Proceed immediately to Stage 2: Context Builder.
