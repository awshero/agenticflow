# GitHub Copilot — TDD Pipeline Instructions

This repository uses a **Jira-driven TDD pipeline** via custom agents in `.github/agents/`.
Agents auto-detect the codebase and generate all context, standards, and commands at runtime.
Drop `.github/agents/` into any repo — no pre-existing configuration needed.

---

## The Pipeline

```
Jira Ticket (paste requirement)
    ↓
TDD Orchestrator — classifies feature type (api / backend / combined), writes jira-requirements.md
    ↓
Context Builder — scans codebase, detects stack/commands/patterns → codebase-context.md
    ↓
Standards Loader — infers rules from existing code → active-standards.md
    ↓
Test Generator — writes failing tests from Jira ACs (RED phase)
    ↓
Test Runner & Fixer — collects tests, fixes syntax errors (stays RED)
    ↓
Feature Developer — implements to make tests pass (GREEN phase)
    ↓
Doc Generator — generates README-TEST-SCENARIOS.md from actual code
    ↓
Git Manager — creates branch, conventional commit
    ↓
PR Manager — opens pull request
    ↓
PR Reviewer — reviews against standards, approves and merges
    ↓
E2E Validator — validates deployed app against all Jira ACs
```

---

## How to Start

1. Open Copilot Chat (`Cmd+Alt+I`)
2. Switch to **Agent** mode
3. Select **TDD Orchestrator** from the agent picker
4. Paste your Jira ticket ID, summary, and acceptance criteria

---

## Feature Types

Agents automatically adapt based on what is being built:

| Type | What it means | Test strategy |
|------|--------------|---------------|
| `api` | HTTP endpoint(s) only | Unit tests + HTTP integration tests |
| `backend` | Background job / worker / pipeline only | Unit tests + job execution tests |
| `combined` | API that triggers backend processing | Unit + HTTP + job + end-to-end flow tests |

---

## Context Files (generated at runtime — do not edit manually)

| File | Created by | Purpose |
|------|-----------|---------|
| `.github/context/jira-requirements.md` | TDD Orchestrator | Ticket, ACs, feature type |
| `.github/context/codebase-context.md` | Context Builder | Stack, commands, test patterns |
| `.github/context/active-standards.md` | Standards Loader | Inferred rules and conventions |
| `.github/context/test-plan.md` | Test Generator | Test inventory and AC coverage |
| `.github/context/test-run-report.md` | Test Runner & Fixer | Pre-implementation test status |
| `.github/context/implementation-report.md` | Feature Developer | API/job contract, coverage |
| `.github/context/pipeline-state.md` | TDD Orchestrator | Stage tracking |
| `.github/context/git-report.md` | Git Manager | Branch and commit info |
| `.github/context/pr-report.md` | PR Manager | PR URL |
| `.github/context/review-report.md` | PR Reviewer | Review decision |
| `.github/context/e2e-report.md` | E2E Validator | Final AC validation |

---

## Standards Files (optional overrides)

If `.github/standards/*.md` files exist, Standards Loader merges them with inferred standards.
Static files take precedence over inferences for any rule they define.
If they do not exist, Standards Loader infers everything from the codebase automatically.

---

## Key Design Principles

- **No hardcoded commands** — all agents read `commands.*` from `codebase-context.md`
- **No hardcoded paths** — all agents read `paths.*` from `codebase-context.md`
- **No hardcoded test patterns** — agents use patterns detected from the existing codebase
- **Standards are inferred** — Standards Loader reads existing code to find conventions
- **Feature-type aware** — every agent branches on `api / backend / combined`
