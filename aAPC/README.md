# aAPC — Databricks All-Purpose Cluster Compute Optimizer

A deterministic, rules-based framework that recommends compute optimizations for
Databricks **All-Purpose Clusters (APC)**, estimates annual savings against **NET
cost**, and scores each recommendation's confidence. It ships as one Databricks
Asset Bundle you can lift into any customer account (LOB1, LOB2, LOB3, …).

| Optimization | Rule (default thresholds in `rules.yml`) |
|---|---|
| EC2 rightsizing – driver | Required = current × P95 CPU/mem × 1.10 → cheapest catalog node that fits |
| EC2 rightsizing – workers + ASG | Same per-node requirement, **bundled** with autoscaling: each candidate shape gets min/max sized from executor concurrency P10/P95, the cheapest *fleet* wins |
| Photon off | Photon on and CPU P95 < 30% |
| Auto Stop | Smallest auto-termination value whose cold-start rate on resumed idle gaps is ≤ 20% |
| APC → Job cluster | ≥ 8 scheduled (CRON/PERIODIC) runs on ≥ 4 days and ≥ 60% of active minutes are scheduled jobs |

---

## Flow

```
 system tables (non-billing)                 metadata lake (NET cost)
 ─────────────────────────────               ────────────────────────
 compute.clusters / node_types                       │
 compute.node_timeline                               │
 lakeflow.job_(task_)run_timeline                    │
 billing.usage (photon flag + DBU qty only)          │
            │                                        │
            ▼  SQL collector (SQL warehouse)         │
 ┌──────────────────────────────┐                    │
 │ apc_metrics_table            │                    │
 │ apc_cluster_config_history   │                    │
 └──────────────┬───────────────┘                    │
                ▼  Recommendation engine (Python wheel)
   Lifecycle_APC ─► Guardrails ─► Rules ─► Annual_Cost_Generator ─► Savings ─► Confidence
                ▼
 ┌──────────────────────────────┐
 │ apc_recommendations          │  (+ apc_recommendations_latest view)
 │ apc_cluster_cost_summary     │
 └──────────────────────────────┘
```

Both stages run as one job (`apc_optimizer_pipeline`), daily at 05:00 UTC.

---

## Repository structure

```
aAPC/
├── databricks.yml                     # DAB: variables + one target per LOB/customer
├── resources/
│   └── apc_optimizer.job.yml          # collector SQL tasks -> engine wheel task
├── collector/
│   └── sql/
│       ├── apc/
│       │   ├── 00_setup.sql           # schema + all Delta tables + latest view
│       │   ├── 10_config_history.sql  # config change history  -> apc_cluster_config_history
│       │   └── 20_compute_metrics.sql # P50/P95, executors, idle gaps, schedules -> apc_metrics_table
│       └── job_cluster/               # future: same pattern for job clusters
├── src/apc_optimizer/
│   ├── conf/
│   │   ├── rules.yml                  # every threshold / guardrail (versioned)
│   │   └── instance_catalog.yml       # vCPU, memory, $/h, DBU/h per node type
│   ├── models.py                      # ClusterMetrics, RuleOutcome, Recommendation, ...
│   ├── config.py / catalog.py
│   ├── compute_types.py               # APC | JOB_CLUSTER adapters (table names)
│   ├── lifecycle/lifecycle_apc.py     # repeating configs -> ACTIVE / EXPERIMENTAL / DORMANT / DELETED
│   ├── rules/
│   │   ├── base.py                    # Rule contract + registry hook (applies_to)
│   │   ├── rightsizing.py             # driver + worker/ASG bundle
│   │   ├── photon.py
│   │   ├── auto_stop.py
│   │   ├── apc_to_job.py
│   │   └── guardrails.py              # cluster-level eligibility + cross-rule conflicts
│   ├── cost/
│   │   ├── annual_cost.py             # Annual_Cost_Generator (NET cost, annualised)
│   │   └── savings.py                 # per-rec savings + stacked (multiplicative) savings
│   ├── scoring/confidence.py          # 0-100 score + HIGH/MEDIUM/LOW band
│   ├── engine/generator.py            # orchestration (pure Python, unit-tested)
│   ├── storage/spark_io.py            # only module that touches Spark / Delta
│   └── jobs/recommend.py              # wheel entry point `apc-recommend`
├── tests/                             # 42 unit tests, no Spark needed
└── pyproject.toml
```

### Why it scales to job clusters

* Every table carries `compute_type`; recommendations key on `compute_id`.
* `compute_types.py` is the only place that maps a compute type to its tables.
* Rules declare `applies_to = {"APC"}`; opting a rule into job clusters is a
  one-line change. Rightsizing and Photon apply as-is; Auto Stop and APC→Job are
  APC-only by nature.
* The engine (`generator.py`), cost and confidence models don't know which
  compute type they are processing.
* Add `collector/sql/job_cluster/*.sql`, register the tasks, and run the engine
  with `--compute_type JOB_CLUSTER` (see `collector/sql/job_cluster/README.md`).

---

## Components

### 1. SQL metrics collector (non-billing)
Runs on a SQL warehouse as SQL file tasks with named parameters
(`:catalog`, `:schema`, `:lob`, `:lookback_days`, `:idle_cpu_threshold`).
Idempotent `MERGE` keyed on `(snapshot_date, workspace_id, cluster_id)`, so a
rerun on the same day overwrites rather than duplicates.

What `20_compute_metrics.sql` derives per APC:
* **Driver / worker CPU & memory** P50 / P95 / max from `node_timeline` (CPU = user + system).
* **Executor concurrency** P10 / P50 / P95 / max workers up per minute (drives ASG min/max).
* **Idle profile** via gaps-and-islands over cluster-minutes: a minute is idle when the
  busiest node is below `idle_cpu_threshold`. Idle streaks are split into
  *intra-session gaps* (user came back) and *terminal tails* (ran until auto-stop).
* **Scheduled workload**: job task runs whose `compute_ids` include the APC, joined to
  `job_run_timeline.trigger_type IN ('CRON','PERIODIC')`.
* **Photon flag** from `billing.usage.product_features.is_photon` (no $ used).

### 2. Lifecycle_APC
Collapses config history into spans of identical configuration (driver/worker type,
worker counts, autoscale bounds, auto-stop, DBR) and counts how often each comes back.

| State | Meaning | Engine behaviour |
|---|---|---|
| `ACTIVE` | used in the last 14 d, config settled or repeating | recommendations generated |
| `EXPERIMENTAL` | > 6 changes in the window, current config < 7 d old and never seen before | held back: owner still tuning |
| `DORMANT` | no activity in the last 14 d | skipped (cost still reported) |
| `DELETED` | cluster deleted | skipped |

Stability (repeating config, age, churn) feeds the confidence score.

### 3. Rules & guardrails
Cluster-level: opt-out tag `apc_optimizer=exclude`, lifecycle must be `ACTIVE`,
≥ 7 observed days, ≥ 600 uptime minutes. Per-rule: driver floor 4 vCPU / 16 GB,
max 4× downsize per step, allowed families, GPU nodes skipped, auto-stop bounded to
10–120 min, minimum 5% cost reduction. Cross-rule: when an APC is retired in favour
of job clusters, Auto Stop is suppressed. Recommendations under $500/yr are dropped.

### 4. Annual_Cost_Generator & savings estimator
* NET cost from the metadata lake over the lookback, annualised as
  `cost × 365 / billable_days` (billable days shorten for clusters created mid-window).
* DBU vs infra split from the lake's category column; else `default_dbu_share`;
  if a cluster has no cost rows, a list-price estimate from node-minutes
  (`cost_basis` tells you which).
* Each rule returns the *fraction* of DBU and infra cost it removes; savings =
  `annual_dbu × dbu_frac + annual_infra × infra_frac`.
* `stacked_annual_savings` in the summary compounds all recommendations
  multiplicatively, so it never double-counts.

### 5. Confidence score (0–100)

| Factor | Weight | 1.0 when |
|---|---|---|
| coverage | 0.25 | ≥ 30 observed days |
| sample | 0.15 | ≥ 2 400 uptime minutes |
| stability | 0.20 | repeating / long-lived config, little churn |
| signal | 0.30 | metric far past the rule threshold (rule-specific) |
| cost | 0.10 | NET cost with DBU/infra split (0.8 default split, 0.5 list estimate) |

Bands: `HIGH` ≥ 75, `MEDIUM` ≥ 50, else `LOW`.

---

## Deploy

Prerequisites: Databricks CLI ≥ 0.218, Unity Catalog with access to `system.compute`,
`system.lakeflow` and `system.billing`, a SQL warehouse, and read access to the
cost-lake table.

1. Set each target's `workspace.host` and `catalog` in `databricks.yml`.
2. Map your cost-lake columns in `src/apc_optimizer/conf/rules.yml → cost_source`.
3. Deploy and run:

```bash
pip install build
databricks bundle validate -t lob1 --var="warehouse_id=<id>"
databricks bundle deploy   -t lob1 --var="warehouse_id=<id>" --var="cost_table=<cat.schema.table>"
databricks bundle run apc_optimizer_pipeline -t lob1
```

Query the output:

```sql
SELECT compute_name, optimization_type, annual_savings_estimate, confidence_band, rationale
FROM   <catalog>.apc_optimizer.apc_recommendations_latest
ORDER  BY annual_savings_estimate DESC;
```

## Local development

```bash
cd aAPC
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Tune thresholds without code changes by passing `--rules_path` to an override YAML
(deep-merged over the packaged `rules.yml`); bump `rule_version` when you do.
