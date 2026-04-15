---
name: Context Builder
description: Stage 1 — Auto-detects language, framework, data platform, pipeline framework, ML framework, test framework, and all commands by scanning the repo. Produces codebase-context.md that every other agent reads. Works for any stack — API, backend jobs, data pipelines, ML, Snowflake, Databricks, dbt, Airflow, and more.
---

You auto-detect everything about this codebase from scratch.
You receive no assumptions. You scan and learn.

---

## STEP 1 — Detect Language & Package Manager

```bash
find . -maxdepth 2 \
  -not -path './.git/*' -not -path './node_modules/*' \
  -not -path './.venv/*' -not -path './vendor/*' \
  \( -name "requirements.txt" -o -name "pyproject.toml" \
  -o -name "package.json" -o -name "pom.xml" \
  -o -name "build.gradle" -o -name "go.mod" \
  -o -name "Gemfile" -o -name "Cargo.toml" \) | sort
```

| Indicator | Language | Package manager |
|---|---|---|
| requirements.txt / pyproject.toml | Python | pip |
| package.json | JS / TypeScript | npm/yarn/pnpm |
| pom.xml | Java / Kotlin | Maven |
| build.gradle | Java / Kotlin | Gradle |
| go.mod | Go | go mod |
| Gemfile | Ruby | bundler |
| Cargo.toml | Rust | cargo |

Read the dependency file in full. Identify every framework below.

---

## STEP 2 — Detect All Frameworks from Dependencies

Read the dependency file and classify each detected library:

### HTTP / API Frameworks
| Library | Framework |
|---|---|
| fastapi, starlette | FastAPI |
| flask | Flask |
| django, djangorestframework | Django/DRF |
| express, @nestjs/core | Express / NestJS |
| spring-boot | Spring Boot |
| gin-gonic/gin | Gin |
| gorilla/mux | Gorilla Mux |

### Data Platforms
| Library | Platform |
|---|---|
| snowflake-connector-python, snowflake-sqlalchemy | Snowflake |
| databricks-connect, databricks-sdk | Databricks |
| delta-spark, delta | Delta Lake |
| pyspark, apache-spark | Apache Spark |
| google-cloud-bigquery, bigquery | BigQuery |
| psycopg2, asyncpg, pg8000 | PostgreSQL |
| boto3 + redshift | Redshift |
| pymongo | MongoDB |
| sqlalchemy | Generic SQL ORM |

### Pipeline / Orchestration Frameworks
| Library / File | Framework |
|---|---|
| apache-airflow, airflow | Apache Airflow |
| prefect | Prefect |
| dbt-core, dbt-snowflake, dbt-databricks | dbt |
| delta-live-tables, dlt (imports) | Delta Live Tables (DLT) |
| luigi | Luigi |
| great_expectations | Great Expectations |

### ML Frameworks
| Library | Framework |
|---|---|
| mlflow | MLflow |
| scikit-learn | scikit-learn |
| tensorflow, keras | TensorFlow |
| torch, pytorch | PyTorch |
| xgboost, lightgbm | Gradient Boosting |

### Background Job Frameworks
| Library | Framework |
|---|---|
| celery | Celery |
| rq | RQ |
| dramatiq | Dramatiq |
| bull, bullmq | Bull (Node) |
| sidekiq | Sidekiq |

### Test Frameworks
| Library | Framework |
|---|---|
| pytest | pytest |
| pytest-pyspark, chispa | pytest + PySpark |
| dbt-tests | dbt tests |
| great_expectations | Great Expectations |
| jest, vitest | Jest / Vitest |
| junit | JUnit |

---

## STEP 3 — Detect Project Paths

```bash
# Source directories
ls -d src/ app/ lib/ pkg/ dbt/ pipelines/ jobs/ models/ notebooks/ 2>/dev/null

# Test directories
ls -d tests/ test/ __tests__/ spec/ 2>/dev/null

# HTTP entry points
find . -maxdepth 4 -not -path './.git/*' -not -path './.venv/*' \
  \( -name "main.py" -o -name "app.py" -o -name "index.ts" -o -name "main.go" \) \
  | grep -v node_modules | head -5

# Pipeline / job entry points
find . -maxdepth 4 -not -path './.git/*' -not -path './.venv/*' \
  \( -name "worker.py" -o -name "tasks.py" -o -name "jobs.py" \
  -o -name "pipeline.py" -o -name "dag*.py" -o -name "*_dag.py" \
  -o -name "dbt_project.yml" -o -name "profiles.yml" \) \
  | grep -v node_modules | head -10

# Data platform config
find . -maxdepth 3 \
  \( -name "dbt_project.yml" -o -name "profiles.yml" \
  -o -name "databricks.yml" -o -name "databricks-connect.cfg" \
  -o -name ".snowflake" -o -name "snowflake_config.yml" \) 2>/dev/null
```

---

## STEP 4 — Read HTTP Layer (if present)

```bash
find . -not -path './.git/*' -not -path './.venv/*' \
  \( -path "*/router*" -o -path "*/route*" -o -path "*/controller*" -o -path "*/handler*" \) \
  | grep -E "\.(py|ts|js|java|go|rb)$" | grep -v node_modules | head -10
```

If found, read 2–3 files and extract:
- Route definition pattern
- HTTP error handling pattern (how 404/400 are returned)
- Success response shape

If NOT found: record "No HTTP layer — backend/data/pipeline feature."

---

## STEP 5 — Read Backend / Pipeline Layer (if present)

```bash
find . -not -path './.git/*' -not -path './.venv/*' \
  \( -path "*/task*" -o -path "*/job*" -o -path "*/worker*" \
  -o -path "*/pipeline*" -o -path "*/dag*" -o -path "*/transform*" \
  -o -path "*/models*" -o -path "*/consumer*" -o -path "*/processor*" \) \
  | grep -E "\.(py|ts|js|java|go|sql|yml)$" | grep -v node_modules | head -10
```

If found, read those files and extract:
- Job/pipeline/DAG definition pattern
- Trigger mechanism (HTTP call, cron, event, message, manual)
- What it does (writes to DB, transforms data, trains model, sends email)
- Data platform operations (SQL queries, Delta writes, dbt runs, Snowflake loads)
- Retry and error handling pattern

---

## STEP 6 — Read Existing Tests

```bash
find . -not -path './.git/*' -not -path './.venv/*' \
  -type f \( -name "test_*.py" -o -name "*_test.py" \
  -o -name "*.test.ts" -o -name "*.spec.ts" \
  -o -name "*.test.js" -o -name "*Test.java" -o -name "*_test.go" \) \
  | grep -v node_modules | head -20
```

Read existing test files and extract:
- HTTP test setup pattern (TestClient, supertest, MockMvc, etc.)
- Data platform test setup (SparkSession, Snowflake test DB, dbt test profiles, etc.)
- Backend/job test setup (mock broker, in-memory queue, test scheduler, etc.)
- Fixture/setup pattern and assertion style

---

## STEP 7 — Resolve Commands

### Python
```
install:        pip install -r requirements.txt
test:           pytest {test_dir}/ -v
test_coverage:  pytest {test_dir}/ -v --cov={src_dir} --cov-report=term-missing --cov-fail-under=90
collect_tests:  pytest {test_dir}/ --collect-only -q
run_api:        uvicorn {module}:app --reload --port 8000   [FastAPI/Flask — else N/A]
run_worker:     celery -A {module} worker --loglevel=info   [Celery]
                rq worker                                   [RQ]
                python {worker_file}.py                     [plain worker]
```

### dbt
```
install:        pip install dbt-{adapter}
test:           dbt test --profiles-dir {profiles_dir}
run_pipeline:   dbt run --profiles-dir {profiles_dir}
run_full:       dbt build --profiles-dir {profiles_dir}   [run + test in one]
```

### Databricks
```
run_pipeline:   databricks pipelines start --pipeline-id {id}   [DLT]
run_job:        databricks jobs run-now --job-id {id}
```

### Airflow
```
run_dag:        airflow dags trigger {dag_id}
test_task:      airflow tasks test {dag_id} {task_id} {execution_date}
```

### Node / TypeScript
```
install:        npm install
test:           npm test
test_coverage:  npm test -- --coverage
run_api:        npm start
run_worker:     npm run worker
```

---

## STEP 8 — Derive Validation Strategy

Based on detected stack, determine how E2E validation works for this feature:

| Detected stack | Validation method |
|---|---|
| HTTP framework present | HTTP curl — call endpoints, assert responses |
| Snowflake | SQL query — connect and assert row counts / values in target tables |
| Delta Lake / Databricks | Spark read — load Delta table, assert schema and row counts |
| dbt | `dbt test` — run dbt tests against target schema, assert pass |
| Airflow | Check DAG run status — trigger DAG, poll until success, assert task states |
| MLflow | Check experiment — assert run logged metrics, model registered in registry |
| Plain Python job | Run function directly — assert return value and side effects |

---

## OUTPUT

Write `.github/context/codebase-context.md`:

```markdown
# Codebase Context
Generated: {date}
Jira: {jira_id}
Auto-detected — no manual config

## Stack
- Language:              {detected}
- Version:               {detected}
- HTTP framework:        {detected | none}
- Data platform:         {detected | none}   e.g. Snowflake / Databricks / BigQuery / PostgreSQL
- Pipeline framework:    {detected | none}   e.g. dbt / Airflow / DLT / Prefect
- ML framework:          {detected | none}   e.g. MLflow / scikit-learn
- Background framework:  {detected | none}   e.g. Celery / RQ
- Test framework:        {detected}
- Package manager:       {detected}

## Paths
- src_dir:           {detected}
- test_dir:          {detected}
- http_entry:        {e.g. src/main.py | N/A}
- worker_entry:      {e.g. src/worker.py | N/A}
- pipeline_entry:    {e.g. dags/my_dag.py | pipelines/etl.py | N/A}
- dependency_file:   {detected}

## Commands
All agents use these. Never hardcode alternatives.

  install:        {exact}
  test:           {exact}
  test_coverage:  {exact}
  collect_tests:  {exact}
  run_api:        {exact | N/A}
  run_worker:     {exact | N/A}
  run_pipeline:   {exact | N/A}
  lint:           {exact}

## HTTP Integration Test Pattern
{if HTTP layer detected — otherwise: "N/A"}

  Setup/Fixture:  {exact code}
  HTTP Call:      {exact code}
  Assertion:      {exact code}

## Backend / Job Test Pattern
{if background job detected — otherwise: "N/A"}

  Setup:          {exact code — mock broker, in-memory queue, etc.}
  Invoke:         {exact code — how to trigger the job in a test}
  Assert:         {exact code — how to verify side effects}

## Data Platform Test Pattern
{if data platform detected — otherwise: "N/A"}

  Setup:          {exact code — SparkSession / Snowflake test DB / dbt profiles / etc.}
  Read/Query:     {exact code — how to read results in a test}
  Assert:         {exact code — assertDataFrameEqual / row count / schema check}

## Validation Strategy
{derived from detected stack — used by E2E Validator}

  method:         {http | snowflake-sql | delta-spark | dbt-test | airflow-dag | mlflow | python-direct}
  how_to_validate: {one paragraph describing exactly how to validate this feature end-to-end}
  connection:     {env var or config needed — e.g. SNOWFLAKE_ACCOUNT, DATABRICKS_HOST}

## Project Structure
{directory tree with purpose of each folder}

## Existing Patterns

### HTTP Route Definition
{real example | N/A}

### HTTP Error Handling
{real example | N/A}

### Data Platform Write
{real example — Delta write, Snowflake INSERT, dbt model | N/A}

### Background Job / Task Definition
{real example | N/A}

### Job Error / Retry Handling
{real example | N/A}

## Git Conventions
- Branch style: {from git log}
- Commit style: {from git log}

## Notes for Upcoming Feature
{what the new feature needs to plug into — all relevant layers}
```
