# Databricks Standards — DLT Optimization Pipeline

These are static override standards for the Databricks DLT Optimization use case.
Standards Loader merges these with inferred codebase standards.
Rules defined here take precedence over inferences.

---

## Stack

```
language:              Python 3.10+
compute:               Databricks (Unity Catalog)
pipeline_framework:    Delta Live Tables (DLT)
ml_framework:          MLflow
data_format:           Delta (Parquet + transaction log)
test_framework:        pytest
spark_test_util:       pyspark.testing.assertDataFrameEqual
job_orchestrator:      Databricks Workflows (Jobs API)
api_framework:         FastAPI
```

---

## Components and Feature Types

| Component | Feature Type | Entry Point |
|---|---|---|
| Recommendation API | `api` | FastAPI app serving `/recommendations` endpoints |
| Metrics Collector | `backend` | Databricks Job — collects and writes metrics to Delta |
| ETL Pipeline | `backend` | DLT pipeline — ingest → transform → publish Delta tables |
| Recommendation Engine | `backend` | Databricks Job — trains/scores model, logs to MLflow |

---

## API Design Rules (Recommendation API)

- [ ] URL shape: `/v1/recommendations/{entity_id}` (versioned, plural nouns)
- [ ] HTTP methods: GET for recommendations, POST for feedback
- [ ] Success response shape:
  ```json
  {
    "entity_id": "...",
    "recommendations": [{"id": "...", "score": 0.95, "reason": "..."}],
    "model_version": "...",
    "generated_at": "ISO8601"
  }
  ```
- [ ] Error response shape: `{"detail": "message"}` (FastAPI default)
- [ ] Success status codes: 200 for GET, 422 for invalid input
- [ ] Health endpoint: `GET /health → {"status": "healthy", "model_version": "..."}`
- [ ] All responses: JSON, `Content-Type: application/json`
- [ ] Model version included in every response for traceability

---

## Backend / Job Rules

### Metrics Collector
- [ ] Runs as a Databricks Workflow on schedule (cron)
- [ ] Writes to Delta table using `append` mode (never overwrite raw metrics)
- [ ] Schema: `metric_name`, `value`, `entity_id`, `collected_at`, `pipeline_run_id`
- [ ] Idempotent: include `pipeline_run_id` to detect duplicate runs
- [ ] On failure: log to `metrics_errors` Delta table, raise exception to trigger retry

### ETL Pipeline (DLT)
- [ ] Use `@dlt.table` decorator for all output tables
- [ ] Use `@dlt.view` for intermediate transformations
- [ ] Use `@dlt.expect` / `@dlt.expect_or_drop` for data quality constraints
- [ ] Bronze → Silver → Gold layer naming convention
- [ ] Bronze: raw ingest, schema enforcement only
- [ ] Silver: cleansed, deduplicated, joined
- [ ] Gold: aggregated, business-ready, optimized for reads
- [ ] Never write to Delta directly inside a DLT pipeline — use `dlt.read()` and `dlt.read_stream()`
- [ ] Idempotent: DLT handles this via Delta transaction log

### Recommendation Engine
- [ ] Training and scoring are separate functions
- [ ] Log all experiments to MLflow: `mlflow.log_param`, `mlflow.log_metric`, `mlflow.log_model`
- [ ] Register best model to MLflow Model Registry with stage `Staging` → `Production`
- [ ] Recommendations written to Gold Delta table: `recommendations_gold`
- [ ] Schema: `entity_id`, `recommended_id`, `score`, `model_version`, `scored_at`
- [ ] Idempotent: partition by `scored_at` date + `model_version`, overwrite partition on re-run

---

## Test Rules

- [ ] TDD: tests written BEFORE implementation (mandatory)
- [ ] Coverage threshold: 85%
- [ ] Test file naming: `test_*.py`
- [ ] Test function naming: `test_{component}_{condition}_{expected_result}`
- [ ] Test structure: AAA (Arrange / Act / Assert)
- [ ] Unit tests: `tests/unit/` — pure Python, no SparkSession, mock all I/O
- [ ] Integration tests: `tests/integration/` — local SparkSession, in-memory Delta

### SparkSession Fixture (shared conftest.py)
```python
import pytest
from pyspark.sql import SparkSession

@pytest.fixture(scope="session")
def spark() -> SparkSession:
    return (
        SparkSession.builder
        .master("local[2]")
        .appName("test")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .config("spark.databricks.delta.retentionDurationCheck.enabled", "false")
        .getOrCreate()
    )

@pytest.fixture(scope="function")
def tmp_delta_path(tmp_path):
    return str(tmp_path / "delta_table")
```

### DLT Pipeline Test Pattern
```python
# DLT functions are plain Python functions — import and test directly
# Do NOT use dlt.read() in tests — pass DataFrames as arguments instead

from src.pipelines.etl import transform_silver  # the @dlt.table function body

def test_transform_silver_deduplicates_records(spark):
    # Arrange
    raw = spark.createDataFrame([
        ("id1", "val", "2024-01-01"),
        ("id1", "val", "2024-01-01"),  # duplicate
    ], ["id", "value", "date"])

    # Act
    result = transform_silver(raw)

    # Assert
    assert result.count() == 1
```

### Delta Table Assertion Pattern
```python
from pyspark.testing import assertDataFrameEqual
from delta import DeltaTable

def test_metrics_collector_writes_to_delta(spark, tmp_delta_path):
    # Arrange
    input_data = [("cpu_usage", 0.75, "node-1", "2024-01-01T00:00:00")]

    # Act
    collect_metrics(spark, input_data, output_path=tmp_delta_path)

    # Assert
    result = spark.read.format("delta").load(tmp_delta_path)
    assert result.count() == 1
    assert "metric_name" in result.columns
```

### MLflow Test Pattern
```python
import mlflow
from unittest.mock import patch, MagicMock

def test_recommendation_engine_logs_metrics_to_mlflow(spark):
    with mlflow.start_run():
        # Act
        train_model(spark, experiment_name="test")

        # Assert
        run = mlflow.active_run()
        client = mlflow.tracking.MlflowClient()
        metrics = client.get_run(run.info.run_id).data.metrics
        assert "rmse" in metrics
        assert "precision_at_10" in metrics
```

### API + Model Test Pattern
```python
from fastapi.testclient import TestClient
from unittest.mock import patch

@pytest.fixture(scope="module")
def client():
    from src.api.main import app
    return TestClient(app)

def test_recommendations_endpoint_returns_scored_results(client):
    with patch("src.api.services.recommendation_service.load_model") as mock_model:
        mock_model.return_value.predict.return_value = [("item-1", 0.95), ("item-2", 0.87)]
        response = client.get("/v1/recommendations/user-123")
        assert response.status_code == 200
        body = response.json()
        assert "recommendations" in body
        assert len(body["recommendations"]) > 0
        assert "model_version" in body
```

---

## Code Quality Rules

- [ ] Separation of concerns:
  - `src/api/` — FastAPI routers and request/response models only
  - `src/services/` — business logic, model loading, recommendation scoring
  - `src/pipelines/` — DLT table definitions (`@dlt.table`, `@dlt.view`)
  - `src/jobs/` — Databricks job entry points (metrics collector, engine runner)
  - `src/data/` — Delta table readers/writers, schema definitions
  - `src/models/` — MLflow model wrappers and feature engineering
- [ ] No Spark logic in API layer — API calls service functions only
- [ ] No MLflow calls in DLT pipeline — pipelines are for data, not model training
- [ ] Type hints required on all public functions
- [ ] No hardcoded table paths — use config or environment variables
- [ ] Delta table paths and catalog names from environment config, never hardcoded

---

## Git Rules

- [ ] Branch: `{JIRA-ID}-{component}-{short-description}` (e.g. `DLT-42-etl-silver-transform`)
- [ ] Commit: `{type}({scope}): {description}` — scope = `api` / `etl` / `metrics` / `engine`
- [ ] PR targets: `main`

---

## Pre-Merge Gate

- [ ] All tests pass (unit + integration)
- [ ] Coverage ≥ 85%
- [ ] All AC checkboxes covered by at least one test
- [ ] DLT expectations (`@dlt.expect`) defined for all nullable/quality-sensitive columns
- [ ] MLflow experiment name and model name follow naming convention
- [ ] No hardcoded Delta paths or catalog names
- [ ] README-TEST-SCENARIOS.md present and complete
