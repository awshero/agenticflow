-- =============================================================================
-- APC Compute Optimizer :: 20_compute_metrics.sql
-- Non-billing compute metrics collector for All-Purpose Clusters.
--
-- Sources (system tables only, no $ values):
--   system.compute.clusters               current config (latest change row)
--   system.compute.node_types             vCPU / memory per node type
--   system.compute.node_timeline          per-minute CPU / memory per node
--   system.lakeflow.job_task_run_timeline job tasks that ran on the APC
--   system.lakeflow.job_run_timeline      trigger type (CRON / PERIODIC => scheduled)
--   system.billing.usage                  photon flag + DBU *quantity* only
--
-- Writes: apc_metrics_table (MERGE on snapshot_date, workspace_id, cluster_id)
-- Parameters: :catalog, :schema, :lob, :lookback_days, :idle_cpu_threshold
-- =============================================================================

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

MERGE INTO apc_metrics_table AS t
USING (
  WITH
  params AS (
    SELECT
      current_date()                                                    AS snapshot_date,
      CAST(:lookback_days AS INT)                                       AS lookback_days,
      CAST(date_sub(current_date(), CAST(:lookback_days AS INT)) AS TIMESTAMP) AS window_start,
      CAST(:idle_cpu_threshold AS DOUBLE)                               AS idle_cpu
  ),

  -- ---------------------------------------------------------------- config --
  apc_clusters AS (
    SELECT c.*
    FROM system.compute.clusters c
    CROSS JOIN params p
    WHERE c.cluster_source IN ('UI', 'API')
      AND (c.delete_time IS NULL OR c.delete_time >= p.window_start)
    QUALIFY row_number() OVER (PARTITION BY c.workspace_id, c.cluster_id ORDER BY c.change_time DESC) = 1
  ),

  -- ------------------------------------------------------------- telemetry --
  nt AS (
    SELECT
      n.workspace_id,
      n.cluster_id,
      n.instance_id,
      n.driver,
      date_trunc('MINUTE', n.start_time)                      AS minute_ts,
      n.cpu_user_percent + n.cpu_system_percent               AS cpu_pct,
      n.mem_used_percent                                      AS mem_pct
    FROM system.compute.node_timeline n
    JOIN apc_clusters c
      ON n.workspace_id = c.workspace_id AND n.cluster_id = c.cluster_id
    CROSS JOIN params p
    WHERE n.start_time >= p.window_start
  ),

  driver_stats AS (
    SELECT workspace_id, cluster_id,
      percentile_approx(cpu_pct, 0.50) AS driver_cpu_p50,
      percentile_approx(cpu_pct, 0.95) AS driver_cpu_p95,
      max(cpu_pct)                     AS driver_cpu_max,
      percentile_approx(mem_pct, 0.50) AS driver_mem_p50,
      percentile_approx(mem_pct, 0.95) AS driver_mem_p95,
      max(mem_pct)                     AS driver_mem_max,
      count(*)                         AS driver_node_minutes
    FROM nt WHERE driver
    GROUP BY workspace_id, cluster_id
  ),

  worker_stats AS (
    SELECT workspace_id, cluster_id,
      percentile_approx(cpu_pct, 0.50) AS worker_cpu_p50,
      percentile_approx(cpu_pct, 0.95) AS worker_cpu_p95,
      max(cpu_pct)                     AS worker_cpu_max,
      percentile_approx(mem_pct, 0.50) AS worker_mem_p50,
      percentile_approx(mem_pct, 0.95) AS worker_mem_p95,
      max(mem_pct)                     AS worker_mem_max,
      count(*)                         AS worker_node_minutes
    FROM nt WHERE NOT driver
    GROUP BY workspace_id, cluster_id
  ),

  -- one row per cluster-minute the cluster was up
  cluster_minutes AS (
    SELECT workspace_id, cluster_id, minute_ts,
      max(cpu_pct)                                         AS max_cpu,
      count(DISTINCT CASE WHEN NOT driver THEN instance_id END) AS workers_up
    FROM nt
    GROUP BY workspace_id, cluster_id, minute_ts
  ),

  worker_concurrency AS (
    SELECT workspace_id, cluster_id,
      percentile_approx(workers_up, 0.10) AS worker_count_p10,
      percentile_approx(workers_up, 0.50) AS worker_count_p50,
      percentile_approx(workers_up, 0.95) AS worker_count_p95,
      max(workers_up)                     AS worker_count_max
    FROM cluster_minutes
    GROUP BY workspace_id, cluster_id
  ),

  -- ------------------------------------------- idle profile (gaps & islands) --
  cm_flag AS (
    SELECT m.*,
      CASE WHEN m.max_cpu < p.idle_cpu THEN 1 ELSE 0 END AS is_idle,
      CASE WHEN lag(m.minute_ts) OVER w IS NULL
             OR m.minute_ts > lag(m.minute_ts) OVER w + INTERVAL 2 MINUTES
           THEN 1 ELSE 0 END                             AS new_session
    FROM cluster_minutes m CROSS JOIN params p
    WINDOW w AS (PARTITION BY m.workspace_id, m.cluster_id ORDER BY m.minute_ts)
  ),

  cm_session AS (
    SELECT *,
      sum(new_session) OVER (PARTITION BY workspace_id, cluster_id ORDER BY minute_ts
                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS session_id
    FROM cm_flag
  ),

  cm_streak AS (
    SELECT *,
      row_number() OVER (PARTITION BY workspace_id, cluster_id, session_id ORDER BY minute_ts)
      - row_number() OVER (PARTITION BY workspace_id, cluster_id, session_id, is_idle ORDER BY minute_ts) AS streak_grp
    FROM cm_session
  ),

  session_bounds AS (
    SELECT workspace_id, cluster_id, session_id, max(minute_ts) AS session_end
    FROM cm_session
    GROUP BY workspace_id, cluster_id, session_id
  ),

  idle_streaks AS (
    SELECT s.workspace_id, s.cluster_id, s.session_id, s.streak_grp,
      CAST(count(*) AS INT) AS idle_len,
      max(s.minute_ts)      AS streak_end
    FROM cm_streak s
    WHERE s.is_idle = 1
    GROUP BY s.workspace_id, s.cluster_id, s.session_id, s.streak_grp
  ),

  idle_classified AS (
    SELECT i.*, (i.streak_end = b.session_end) AS is_terminal
    FROM idle_streaks i
    JOIN session_bounds b USING (workspace_id, cluster_id, session_id)
  ),

  idle_stats AS (
    SELECT workspace_id, cluster_id,
      -- streaks < 5 min are just think-time noise, not auto-stop candidates
      collect_list(CASE WHEN NOT is_terminal AND idle_len >= 5 THEN idle_len END) AS intra_session_idle_gaps,
      collect_list(CASE WHEN is_terminal THEN idle_len END)                        AS terminal_idle_tails,
      percentile_approx(CASE WHEN NOT is_terminal AND idle_len >= 5 THEN idle_len END, 0.50) AS idle_gap_p50,
      percentile_approx(CASE WHEN NOT is_terminal AND idle_len >= 5 THEN idle_len END, 0.80) AS idle_gap_p80,
      percentile_approx(CASE WHEN NOT is_terminal AND idle_len >= 5 THEN idle_len END, 0.90) AS idle_gap_p90
    FROM idle_classified
    GROUP BY workspace_id, cluster_id
  ),

  uptime_stats AS (
    SELECT workspace_id, cluster_id,
      count(*)                                         AS uptime_minutes,
      sum(1 - is_idle)                                 AS active_minutes,
      sum(is_idle)                                     AS idle_minutes,
      CAST(max(session_id) AS INT)                     AS session_count,
      CAST(count(DISTINCT to_date(minute_ts)) AS INT)  AS observed_days,
      max(CASE WHEN is_idle = 0 THEN minute_ts END)    AS last_active_time
    FROM cm_session
    GROUP BY workspace_id, cluster_id
  ),

  -- ------------------------------------------------ scheduled job workload --
  task_runs AS (
    SELECT
      tr.workspace_id,
      compute_id                                       AS cluster_id,
      tr.job_id,
      tr.job_run_id,
      tr.period_start_time,
      (unix_timestamp(tr.period_end_time) - unix_timestamp(tr.period_start_time)) / 60.0 AS task_minutes
    FROM system.lakeflow.job_task_run_timeline tr
    CROSS JOIN params p
    LATERAL VIEW explode(tr.compute_ids) x AS compute_id
    WHERE tr.period_start_time >= p.window_start
  ),

  run_triggers AS (
    SELECT workspace_id, job_id, run_id, max(trigger_type) AS trigger_type
    FROM system.lakeflow.job_run_timeline r
    CROSS JOIN params p
    WHERE r.period_start_time >= p.window_start
    GROUP BY workspace_id, job_id, run_id
  ),

  job_stats AS (
    SELECT t.workspace_id, t.cluster_id,
      count(DISTINCT t.job_run_id)                                                   AS total_job_runs,
      count(DISTINCT CASE WHEN r.trigger_type IN ('CRON', 'PERIODIC') THEN t.job_run_id END) AS scheduled_job_runs,
      CAST(count(DISTINCT CASE WHEN r.trigger_type IN ('CRON', 'PERIODIC') THEN t.job_id END) AS INT) AS distinct_scheduled_jobs,
      CAST(count(DISTINCT CASE WHEN r.trigger_type IN ('CRON', 'PERIODIC') THEN to_date(t.period_start_time) END) AS INT) AS scheduled_job_days,
      sum(t.task_minutes)                                                            AS job_task_minutes,
      coalesce(sum(CASE WHEN r.trigger_type IN ('CRON', 'PERIODIC') THEN t.task_minutes END), 0) AS scheduled_job_minutes,
      collect_set(CASE WHEN r.trigger_type IN ('CRON', 'PERIODIC') THEN CAST(t.job_id AS STRING) END) AS scheduled_job_ids
    FROM task_runs t
    JOIN apc_clusters c
      ON t.workspace_id = c.workspace_id AND t.cluster_id = c.cluster_id
    LEFT JOIN run_triggers r
      ON t.workspace_id = r.workspace_id AND t.job_id = r.job_id AND t.job_run_id = r.run_id
    GROUP BY t.workspace_id, t.cluster_id
  ),

  -- ---------------------------------------- photon flag & DBU quantity only --
  usage_stats AS (
    SELECT u.workspace_id, u.usage_metadata.cluster_id AS cluster_id,
      max(coalesce(u.product_features.is_photon, false)) AS photon_enabled,
      sum(CASE WHEN u.usage_unit = 'DBU' THEN u.usage_quantity END) AS dbus_consumed
    FROM system.billing.usage u
    CROSS JOIN params p
    WHERE u.usage_date >= to_date(p.window_start)
      AND u.usage_metadata.cluster_id IS NOT NULL
    GROUP BY u.workspace_id, u.usage_metadata.cluster_id
  )

  -- ------------------------------------------------------------- final row --
  SELECT
    p.snapshot_date,
    current_timestamp()                                AS collected_at,
    :lob                                               AS lob,
    c.account_id,
    c.workspace_id,
    'APC'                                              AS compute_type,
    c.cluster_id,
    c.cluster_name,
    c.owned_by,
    c.cluster_source,
    c.dbr_version,
    c.policy_id,
    c.tags,
    c.create_time,
    c.delete_time,
    c.change_time                                      AS last_config_change_time,

    c.driver_node_type,
    c.worker_node_type,
    CAST(dn.core_count AS INT)                         AS driver_vcpu,
    dn.memory_mb / 1024.0                              AS driver_memory_gb,
    CAST(dn.gpu_count AS INT)                          AS driver_gpu_count,
    CAST(wn.core_count AS INT)                         AS worker_vcpu,
    wn.memory_mb / 1024.0                              AS worker_memory_gb,
    CAST(wn.gpu_count AS INT)                          AS worker_gpu_count,
    CAST(c.worker_count AS INT)                        AS worker_count,
    CAST(c.min_autoscale_workers AS INT)               AS min_autoscale_workers,
    CAST(c.max_autoscale_workers AS INT)               AS max_autoscale_workers,
    CAST(c.auto_termination_minutes AS INT)            AS auto_termination_minutes,
    coalesce(us.photon_enabled, lower(c.dbr_version) LIKE '%photon%') AS photon_enabled,

    p.lookback_days,
    coalesce(up.observed_days, 0)                      AS observed_days,
    coalesce(ds.driver_node_minutes, 0) + coalesce(ws.worker_node_minutes, 0) AS telemetry_minutes,
    up.last_active_time,

    ds.driver_cpu_p50, ds.driver_cpu_p95, ds.driver_cpu_max,
    ds.driver_mem_p50, ds.driver_mem_p95, ds.driver_mem_max,
    ws.worker_cpu_p50, ws.worker_cpu_p95, ws.worker_cpu_max,
    ws.worker_mem_p50, ws.worker_mem_p95, ws.worker_mem_max,

    CAST(wc.worker_count_p10 AS DOUBLE)                AS worker_count_p10,
    CAST(wc.worker_count_p50 AS DOUBLE)                AS worker_count_p50,
    CAST(wc.worker_count_p95 AS DOUBLE)                AS worker_count_p95,
    CAST(wc.worker_count_max AS INT)                   AS worker_count_max,
    coalesce(ds.driver_node_minutes, 0)                AS driver_node_minutes,
    coalesce(ws.worker_node_minutes, 0)                AS worker_node_minutes,

    coalesce(up.uptime_minutes, 0)                     AS uptime_minutes,
    coalesce(up.active_minutes, 0)                     AS active_minutes,
    coalesce(up.idle_minutes, 0)                       AS idle_minutes,
    coalesce(up.session_count, 0)                      AS session_count,
    coalesce(ist.intra_session_idle_gaps, CAST(array() AS ARRAY<INT>))     AS intra_session_idle_gaps,
    coalesce(ist.terminal_idle_tails, CAST(array() AS ARRAY<INT>))         AS terminal_idle_tails,
    CAST(ist.idle_gap_p50 AS DOUBLE)                   AS idle_gap_p50,
    CAST(ist.idle_gap_p80 AS DOUBLE)                   AS idle_gap_p80,
    CAST(ist.idle_gap_p90 AS DOUBLE)                   AS idle_gap_p90,

    coalesce(js.total_job_runs, 0)                     AS total_job_runs,
    coalesce(js.scheduled_job_runs, 0)                 AS scheduled_job_runs,
    coalesce(js.distinct_scheduled_jobs, 0)            AS distinct_scheduled_jobs,
    coalesce(js.scheduled_job_days, 0)                 AS scheduled_job_days,
    coalesce(js.job_task_minutes, 0)                   AS job_task_minutes,
    coalesce(js.scheduled_job_minutes, 0)              AS scheduled_job_minutes,
    coalesce(js.scheduled_job_ids, CAST(array() AS ARRAY<STRING>))            AS scheduled_job_ids,

    us.dbus_consumed
  FROM apc_clusters c
  CROSS JOIN params p
  LEFT JOIN system.compute.node_types dn ON dn.node_type = c.driver_node_type
  LEFT JOIN system.compute.node_types wn ON wn.node_type = c.worker_node_type
  LEFT JOIN driver_stats       ds  ON ds.workspace_id  = c.workspace_id AND ds.cluster_id  = c.cluster_id
  LEFT JOIN worker_stats       ws  ON ws.workspace_id  = c.workspace_id AND ws.cluster_id  = c.cluster_id
  LEFT JOIN worker_concurrency wc  ON wc.workspace_id  = c.workspace_id AND wc.cluster_id  = c.cluster_id
  LEFT JOIN uptime_stats       up  ON up.workspace_id  = c.workspace_id AND up.cluster_id  = c.cluster_id
  LEFT JOIN idle_stats         ist ON ist.workspace_id = c.workspace_id AND ist.cluster_id = c.cluster_id
  LEFT JOIN job_stats          js  ON js.workspace_id  = c.workspace_id AND js.cluster_id  = c.cluster_id
  LEFT JOIN usage_stats        us  ON us.workspace_id  = c.workspace_id AND us.cluster_id  = c.cluster_id
) AS s
ON  t.snapshot_date = s.snapshot_date
AND t.workspace_id  = s.workspace_id
AND t.cluster_id    = s.cluster_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
