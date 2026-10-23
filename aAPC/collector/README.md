# APC Metrics Collector (standalone)

SQL-only collector of **non-billing** compute metrics for Databricks All-Purpose
Clusters. Every SQL file in the project lives in `sql/`, and this folder has no
dependency on the rest of `aAPC/`. You can copy it into any customer account and
run it on its own.

```
collector/
├── databricks.yml                         # standalone bundle: dev / test / prod
├── resources/apc_metrics_collector.job.yml
└── sql/
    ├── 00_setup_collector_tables.sql      # schema + apc_metrics_table + apc_cluster_config_history
    ├── 10_config_history.sql              # system.compute.clusters -> apc_cluster_config_history
    ├── 20_compute_metrics.sql             # system tables -> apc_metrics_table
    └── 90_setup_engine_tables.sql         # recommendation-engine output tables (not run by this job)
```

## Option 1: deploy as its own bundle

```bash
cd collector
databricks bundle deploy -t prod --var="lob=LOB1" --var="warehouse_id=<id>"
databricks bundle run apc_metrics_collector -t prod --var="lob=LOB1"
```

The job runs `00` → `10` + `20` on a SQL warehouse, daily at 04:00 UTC. The
schedule is paused in dev and test and live in prod.

The parent bundle (`aAPC/databricks.yml`) includes this same job and triggers it
from the full pipeline. Deploy **either** the standalone collector **or** the full
pipeline into a workspace, not both, or you'll get two copies of the job.

## Option 2: run the SQL by hand

Each file uses named parameters (`:catalog`, `:schema`, `:lob`, `:lookback_days`,
`:history_days`, `:idle_cpu_threshold`). Fill them in the SQL editor's parameter
widgets and run the files in order: `00`, `10`, `20`. Every write is an idempotent
`MERGE`, so you can rerun them safely.

## Sources

| System table | Used for |
|---|---|
| `system.compute.clusters` | current config + change history (`cluster_source IN ('UI','API')`) |
| `system.compute.node_types` | vCPU / memory / GPU per node type |
| `system.compute.node_timeline` | per-minute CPU & memory per node, executor count, idle profile |
| `system.lakeflow.job_task_run_timeline` | job tasks that ran on each APC |
| `system.lakeflow.job_run_timeline` | trigger type (`CRON`/`PERIODIC` = scheduled) |
| `system.billing.usage` | Photon flag and DBU *quantity* only, no $ |

The deploying principal needs `SELECT` on these system schemas and `CREATE TABLE`
/ `MODIFY` on the target schema.

## Extending to job clusters

Add `sql/3x_job_cluster_*.sql` following the same pattern: filter
`system.compute.clusters` on `cluster_source = 'JOB'` and key on `job_id`, because
job clusters are ephemeral. Write to `job_cluster_metrics_table` with the same
columns as `apc_metrics_table`. Then add the tasks to the job yml and run the
engine with `--compute_type JOB_CLUSTER`.
