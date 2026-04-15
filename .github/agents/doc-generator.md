---
name: Doc Generator
description: Stage 6 — Generates README-TEST-SCENARIOS.md from actual test files and implementation. Adapts documentation to feature_type (api / backend / combined). Uses commands from codebase-context.md. Works for any language or framework.
---

You generate documentation from what is actually in the code.
All examples, commands, and contracts come from real files — never invented.

---

## STEP 1 — Read Context

Read `.github/context/codebase-context.md`. Extract:
```
commands.test:           {run tests}
commands.test_coverage:  {run with coverage}
commands.run_api:        {start the API — N/A if no HTTP layer}
commands.run_worker:     {start the worker — N/A if no background layer}
commands.install:        {install dependencies}
stack.language, stack.framework
paths.test_dir, paths.src_dir
```

Read:
- `.github/context/jira-requirements.md` — Jira ID, summary, feature_type, ACs, User Story, NFRs
- `.github/context/active-standards.md` — feature_type, NFR constraints covered
- `.github/context/implementation-report.md` — files created, test results, contracts
- All test files in `{paths.test_dir}/`
- Source files in `{paths.src_dir}/` — for exact endpoint paths, job definitions

---

## OUTPUT: `README-TEST-SCENARIOS.md`

---

### Section 1: Feature Overview
- Jira/Story ticket and user story (from `jira-requirements.md`)
- Feature type: api / backend / combined
- Stack: `{language}` + `{framework}`
- What was built (1–3 sentences from `## What Is Being Built` in requirements)

---

### Section 2: API Contract
*(Include only if feature_type is api or combined)*

Read router/controller source files. Write the real contract:

```
{METHOD} {exact path from source code}

Parameters:
  {param} ({type}, required/optional): {description}

Success {code}:
  {exact response shape from Pydantic model / DTO / interface}

Error {code}:
  {exact error shape from source code}
```

---

### Section 3: Background Job Contract
*(Include only if feature_type is backend or combined)*

Read job/task/worker source files. Document:

```
Job: {job_name}
Trigger: {HTTP call | schedule/cron | event | message | manual}
Input: {parameters or payload shape}
Processing: {what it does — transform, send, write, publish}
Output / side effects: {what changes when this job runs}
Retry policy: {N retries, backoff strategy}
Idempotent: {yes — describe key | no}
```

---

### Section 4: Unit Test Scenarios
Read `{test_dir}/unit/` test files. Build one row per test function:

| # | Test Name | Input | Expected | Category |
|---|-----------|-------|----------|----------|
(derive from actual test assertions — do not invent)

---

### Section 5: Integration Test Scenarios
*(For API/combined: HTTP tests. For backend/combined: job execution tests)*

**HTTP Integration Tests** (api or combined):

| # | Test Name | Request | Expected Status | Expected Body |
|---|-----------|---------|-----------------|---------------|

**Backend Integration Tests** (backend or combined):

| # | Test Name | Job Input | Expected Side Effect | Pass/Fail |
|---|-----------|-----------|----------------------|-----------|

**End-to-End Flow Tests** (combined only):

| # | Test Name | API Call | Job Triggered | Side Effect Verified |
|---|-----------|----------|---------------|----------------------|

---

### Section 6: NFR Test Coverage
*(Include only if BMAD NFRs were present)*

| # | NFR | Test Name | Type | Threshold/Assertion |
|---|-----|-----------|------|---------------------|
(from `active-standards.md → Performance/Security Constraints`)

---

### Section 7: Acceptance Criteria Coverage
Map every AC from `jira-requirements.md` to tests:

| AC | Requirement | Unit Tests | Integration Tests | E2E Tests | Status |
|----|-------------|------------|-------------------|-----------|--------|

---

### Section 8: Coverage Report
Run the coverage command and paste the actual output:
```bash
{commands.test_coverage from codebase-context.md}
```

---

### Section 9: Edge Cases
List every edge case tested and one sentence on why it matters.

---

### Section 10: How to Run Tests
Use the exact commands from `codebase-context.md`:

```bash
# Install dependencies
{commands.install}

# Run all tests
{commands.test}

# Run with coverage report
{commands.test_coverage}
```

---

### Section 11: How to Run the Application

*(Adapt based on feature_type)*

**Start the API** (api or combined):
```bash
{commands.run_api}
# Interactive docs (if FastAPI/Swagger available): http://localhost:8000/docs
```

**Start the Worker** (backend or combined):
```bash
{commands.run_worker}
```

---

### Section 12: Sample Calls
*(Adapt based on feature_type)*

**API calls** (api or combined) — derive from integration test parametrized data:
```bash
# One curl per major scenario — use real inputs from tests
# Show expected output as a comment
```

**Trigger a background job manually** (backend or combined — if applicable):
```bash
# Command or script to manually enqueue the job for testing
# Expected side effect as a comment
```
