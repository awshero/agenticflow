# GitHub Copilot — TDD Pipeline Instructions

This repository uses a **fully dynamic TDD pipeline** via custom agents in `.github/agents/`.
Agents auto-detect the codebase and generate all context, standards, and commands at runtime.
No pre-existing configuration is needed — drop the `.github/agents/` folder into any repo.

---

## How It Works

```
Any Repo (any language / framework)
    ↓ Drop .github/agents/ in
    ↓
TDD Orchestrator ──asks──► Jira requirement text
    ↓
Context Builder ──scans codebase──► codebase-context.md
  (auto-detects: language, framework, test framework, paths, commands, patterns)
    ↓
Standards Loader ──infers from code──► active-standards.md
  (infers: API rules, test conventions, code quality rules, git rules)
    ↓
Test Generator ──reads context + ACs──► test files (RED phase)
    ↓
Test Runner & Fixer ──uses commands from context──► valid test suite
    ↓
Feature Developer ──reads tests + context──► implementation (GREEN phase)
    ↓
Doc Generator, Git Manager, PR Manager, PR Reviewer, E2E Validator
```

Every agent reads from **two sources only**:
1. `.github/context/codebase-context.md` — for all commands, paths, and patterns
2. `.github/context/active-standards.md` — for all rules and conventions

---

## Key Design Principles

- **No assumptions** — Context Builder detects everything from the repo itself
- **No hardcoded commands** — all agents use `commands.*` from `codebase-context.md`
- **No hardcoded paths** — all agents use `paths.*` from `codebase-context.md`
- **No hardcoded test patterns** — agents use `Integration Test Pattern` from context
- **Standards are inferred** — Standards Loader reads existing code to find conventions
- **Static standards files are optional** — `.github/standards/*.md` serve as overrides only

---

## Using the Pipeline

### In VS Code Copilot Chat (Agent Mode)
1. Open Copilot Chat (`Cmd+Alt+I`)
2. Switch to **Agent** mode
3. Select **TDD Orchestrator** from the agent picker
4. Paste your Jira requirement text

### Manually invoking a single stage
Select the specific agent from the Copilot agent picker:
- `Context Builder` — re-scan the codebase
- `Test Generator` — write tests for a new requirement
- `Feature Developer` — implement a feature from existing tests
- `E2E Validator` — validate a deployed API

---

## Context Files (generated at runtime)

These files are created by agents during the pipeline — do not edit manually:

| File | Created by | Purpose |
|------|-----------|---------|
| `.github/context/jira-requirements.md` | TDD Orchestrator | Requirement and ACs |
| `.github/context/codebase-context.md` | Context Builder | Stack, commands, patterns |
| `.github/context/active-standards.md` | Standards Loader | Inferred rules checklist |
| `.github/context/test-plan.md` | Test Generator | Test inventory |
| `.github/context/test-run-report.md` | Test Runner & Fixer | Pre-impl test status |
| `.github/context/implementation-report.md` | Feature Developer | API contract, coverage |
| `.github/context/pipeline-state.md` | TDD Orchestrator | Stage tracking |
| `.github/context/git-report.md` | Git Manager | Branch and commit info |
| `.github/context/pr-report.md` | PR Manager | PR URL |
| `.github/context/review-report.md` | PR Reviewer | Review decision |
| `.github/context/e2e-report.md` | E2E Validator | Final validation |

---

## Standards Files (optional overrides)

If `.github/standards/*.md` files exist, `Standards Loader` merges them with inferred standards.
Static files take precedence over inferences for any rule they define.

If they do not exist, `Standards Loader` infers everything from the codebase — no action needed.
