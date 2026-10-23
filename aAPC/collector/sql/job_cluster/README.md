# Job cluster collector (future)

Mirror `collector/sql/apc/` here to extend the optimizer to job clusters:

1. `00_setup.sql` – create `job_cluster_metrics_table` with the same columns as
   `apc_metrics_table` (the engine's `ClusterMetrics` model reads either).
2. `20_compute_metrics.sql` – same CTEs, but filter `system.compute.clusters`
   on `cluster_source = 'JOB'` and aggregate per **job** (job clusters are
   ephemeral, so key on `job_id` + task rather than `cluster_id`).
3. Register the task in `resources/` and run the engine with
   `--compute_type JOB_CLUSTER`.

Rules opt in by adding `"JOB_CLUSTER"` to their `applies_to` set
(rightsizing, Photon off apply as-is; Auto Stop and APC→Job do not).
