# GitHub Copilot — Jira-Driven TDD Agentic Workflow

This is a **fully autonomous 7-stage TDD pipeline**.
Give it a Jira ID and task description. It runs to completion without asking for anything else.

---

## Single Invocation — Fully Hands-Off

```
You: "@TDD Orchestrator  PROJ-42 — Create a GET /products/{id} endpoint
      that returns product details. Returns 200 with {id, name, price} on
      success, 404 if product not found, 400 if id is not a valid integer."
```

The pipeline runs all 7 stages and commits the result. No follow-up questions.

---

## The Pipeline

```
One message from you
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  TDD Orchestrator  — extracts Jira ID + ACs, classifies type    │
│  Writes: jira-requirements.md, pipeline-state.md                │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1  Git Setup                                             │
│                                                                 │
│  git checkout main && git pull origin main                      │
│  git checkout -b feature/{JIRA-ID}-{short-slug}                 │
│  Fallback: tries master → stays on current if neither exists    │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2  Context Builder                                       │
│                                                                 │
│  Scans codebase → detects language, framework, test framework   │
│  Derives all commands (install, test, coverage, collect)        │
│  Reads existing tests → infers patterns, conventions            │
│  Writes: codebase-context.md  +  active-standards.md           │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3  Test Generator  (RED Phase)                           │
│                                                                 │
│  Writes failing tests for every AC — no implementation yet      │
│  api:      ≥10 HTTP integration  +  ≥10 unit tests             │
│  backend:  ≥10 unit  +  ≥5 integration tests                   │
│  combined: ≥10 HTTP  +  ≥10 unit  +  ≥5 E2E flow tests        │
│  Writes: test files  +  test-plan.md                           │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 4  Test Executor  (Retry Loop — max 4 attempts)          │
│                                                                 │
│  Attempt 1 → run → fix test-code errors → continue?            │
│  Attempt 2 → run → fix test-code errors → continue?            │
│  Attempt 3 → run → fix test-code errors → continue?            │
│  Attempt 4 → run → log remaining issues → proceed regardless   │
│                                                                 │
│  Fixes:  syntax, bad imports, fixture issues, naming            │
│  Never:  source modules (expected RED — implementation missing) │
│  After 4: logs ⚠️ and moves on — never stops                   │
│  Writes: test-run-report.md                                     │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 5  Feature Developer  (GREEN Phase)                      │
│                                                                 │
│  Implements layer by layer: Data → Service → Router → Entry     │
│  Runs tests after each layer                                    │
│  Fix loop: up to 10 autonomous fix cycles if tests still fail  │
│  After 10: logs ⚠️ and moves on — never stops                  │
│  Writes: implementation-report.md                              │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 6  Code Validator                                        │
│                                                                 │
│  Runs full test suite + coverage check                          │
│  Maps every AC → passing test  (✅/⚠️/❌)                       │
│  Code quality spot-check (separation of concerns, type hints)   │
│  Produces clear status — never blocks the pipeline              │
│  Writes: validation-report.md                                  │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 7  Git Committer                                         │
│                                                                 │
│  Auto-fixes branch state if needed                              │
│  git add {src}/ {tests}/ {deps} context/                       │
│  git commit -m "{JIRA-ID}: {description} [✅ | ⚠️]"            │
│  Writes: git-report.md  +  pipeline-report.md (final)          │
└─────────────────────────────────────────────────────────────────┘
        │
        ▼
   Feature branch committed. Review pipeline-report.md.
   Push + open PR when ready.
```

---

## How to Start

1. Open Copilot Chat — `Cmd+Alt+I` (Mac) / `Ctrl+Alt+I` (Windows)
2. Switch to **Agent** mode
3. Select **TDD Orchestrator**
4. Send **one message** with your Jira ID and task description

That's it. The pipeline runs to completion on its own.

---

## What Happens When Things Go Wrong

The pipeline never stops mid-run. Instead:

| Problem | What the pipeline does |
|---------|----------------------|
| Base branch not found | Falls back: `main` → `master` → current branch |
| Branch already exists | Checks it out and continues |
| Test syntax errors (after 4 retries) | Logs remaining issues with ⚠️, continues |
| Implementation still failing (after 10 fix cycles) | Logs gaps with ⚠️, continues |
| Coverage below threshold | Notes gap in validation report, commits with ⚠️ |
| AC not covered by a test | Marks ❌ in validation report, commits with ⚠️ |
| Commit hook rejects | Retries with `--no-verify`, logs the bypass |

Everything is captured in the final `pipeline-report.md`. Review it and the `validation-report.md` before merging.

---

## Feature Types

| Type       | Signals in description                                          | Test strategy                              |
|------------|-----------------------------------------------------------------|--------------------------------------------|
| `api`      | endpoint, GET/POST/PUT/DELETE, REST, HTTP, URL                  | Unit + HTTP integration tests              |
| `backend`  | job, worker, queue, cron, pipeline, async, event, process       | Unit + job execution tests                 |
| `combined` | both API and backend signals                                    | Unit + HTTP + job + end-to-end flow tests  |

If the type is ambiguous, the pipeline defaults to `api`.

---

## Agent Files

| Agent                  | Stage | Role                                                       |
|------------------------|-------|------------------------------------------------------------|
| `tdd-orchestrator.md`  | Entry | Extract input, classify, run all 7 stages, final report    |
| `git-setup.md`         | 1     | Checkout base branch, create feature branch                |
| `context-builder.md`   | 2     | Auto-detect stack, commands, patterns                      |
| `standards-loader.md`  | 2b    | Infer coding and testing conventions                       |
| `test-generator.md`    | 3     | Write failing tests (RED phase)                            |
| `test-executor.md`     | 4     | Run tests, fix test-code errors, 4-attempt retry           |
| `feature-developer.md` | 5     | Implement to pass tests, 10-cycle fix loop (GREEN phase)   |
| `code-validator.md`    | 6     | Validate tests, coverage, ACs — report only, never blocks  |
| `git-committer.md`     | 7     | Auto-fix branch, stage files, commit with Jira ID + status |

---

## Context Files (generated at runtime — do not edit)

| File                                        | Created by      | Purpose                                      |
|---------------------------------------------|-----------------|----------------------------------------------|
| `.github/context/jira-requirements.md`      | Orchestrator    | Ticket, ACs, feature type                    |
| `.github/context/codebase-context.md`       | Context Builder | Stack, commands, paths, test patterns        |
| `.github/context/active-standards.md`       | Context Builder | Inferred coding/testing conventions          |
| `.github/context/test-plan.md`              | Test Generator  | Test inventory, AC → test mapping            |
| `.github/context/test-run-report.md`        | Test Executor   | Retry log, attempt history, RED confirmation |
| `.github/context/implementation-report.md`  | Feature Dev     | Files created, contracts, fix cycles used    |
| `.github/context/validation-report.md`      | Code Validator  | Test results, coverage, AC status            |
| `.github/context/pipeline-state.md`         | Orchestrator    | Stage-by-stage ✅/⚠️/❌ status               |
| `.github/context/git-setup-report.md`       | Git Setup       | Branch name, fallbacks used                  |
| `.github/context/git-report.md`             | Git Committer   | Commit hash, files, next steps               |
| `.github/context/pipeline-report.md`        | Orchestrator    | Final consolidated run report                |

---

## Key Design Principles

- **Single invocation** — one message starts the entire pipeline, nothing else needed
- **Git-first** — feature branch created before any code is read or written
- **Never blocks** — every failure has an autonomous fallback; issues are logged with ⚠️
- **Status in the commit** — `[✅]` or `[⚠️]` in the commit subject signals quality at a glance
- **Full audit trail** — every decision, fix, and retry is logged in the context files
- **Stack-agnostic** — works with Python, Node.js, Java, Go, or any detectable framework
- **Resume-safe** — `pipeline-state.md` lets a failed run restart from where it stopped
- **No hardcoded commands or paths** — everything derived from `codebase-context.md`
