-- =============================================================================
-- APC Metrics Collector :: 00_setup_collector_tables.sql
-- Creates the schema and the tables the collector writes:
--   apc_metrics_table, apc_cluster_config_history
-- Idempotent. Parameters (SQL file task named parameters):
--   :catalog  target catalog
--   :schema   target schema
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema)
  COMMENT 'APC compute optimizer: metrics, lifecycle and recommendations';

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

-- -----------------------------------------------------------------------------
-- 1. apc_metrics_table : one row per cluster per collection snapshot.
--    Non-billing compute telemetry only (no $ values live here).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS apc_metrics_table (
  snapshot_date               DATE        NOT NULL,
  collected_at                TIMESTAMP   NOT NULL,
  lob                         STRING,
  account_id                  STRING,
  workspace_id                STRING      NOT NULL,
  compute_type                STRING      NOT NULL COMMENT 'APC today; JOB_CLUSTER in future',
  cluster_id                  STRING      NOT NULL,
  cluster_name                STRING,
  owned_by                    STRING,
  cluster_source              STRING,
  dbr_version                 STRING,
  policy_id                   STRING,
  tags                        MAP<STRING, STRING>,
  create_time                 TIMESTAMP,
  delete_time                 TIMESTAMP,
  last_config_change_time     TIMESTAMP,

  -- current configuration
  driver_node_type            STRING,
  worker_node_type            STRING,
  driver_vcpu                 INT,
  driver_memory_gb            DOUBLE,
  driver_gpu_count            INT,
  worker_vcpu                 INT,
  worker_memory_gb            DOUBLE,
  worker_gpu_count            INT,
  worker_count                INT         COMMENT 'Fixed-size clusters only',
  min_autoscale_workers       INT,
  max_autoscale_workers       INT,
  auto_termination_minutes    INT,
  photon_enabled              BOOLEAN,

  -- observation window
  lookback_days               INT,
  observed_days               INT,
  telemetry_minutes           BIGINT,
  last_active_time            TIMESTAMP,

  -- driver utilisation (%)
  driver_cpu_p50              DOUBLE,
  driver_cpu_p95              DOUBLE,
  driver_cpu_max              DOUBLE,
  driver_mem_p50              DOUBLE,
  driver_mem_p95              DOUBLE,
  driver_mem_max              DOUBLE,

  -- worker utilisation (%)
  worker_cpu_p50              DOUBLE,
  worker_cpu_p95              DOUBLE,
  worker_cpu_max              DOUBLE,
  worker_mem_p50              DOUBLE,
  worker_mem_p95              DOUBLE,
  worker_mem_max              DOUBLE,

  -- executor (worker) concurrency, for ASG min/max
  worker_count_p10            DOUBLE,
  worker_count_p50            DOUBLE,
  worker_count_p95            DOUBLE,
  worker_count_max            INT,
  driver_node_minutes         BIGINT,
  worker_node_minutes         BIGINT,

  -- uptime / idle profile, for Auto Stop
  uptime_minutes              BIGINT,
  active_minutes              BIGINT,
  idle_minutes                BIGINT,
  session_count               INT,
  intra_session_idle_gaps     ARRAY<INT>  COMMENT 'Idle streaks (min) that ended with renewed activity',
  terminal_idle_tails         ARRAY<INT>  COMMENT 'Idle streaks (min) that ended with termination',
  idle_gap_p50                DOUBLE,
  idle_gap_p80                DOUBLE,
  idle_gap_p90                DOUBLE,

  -- scheduled workload profile, for APC -> Job cluster migration
  total_job_runs              BIGINT,
  scheduled_job_runs          BIGINT,
  distinct_scheduled_jobs     INT,
  scheduled_job_days          INT,
  job_task_minutes            DOUBLE,
  scheduled_job_minutes       DOUBLE,
  scheduled_job_ids           ARRAY<STRING>,

  dbus_consumed               DOUBLE      COMMENT 'DBU quantity (not cost) - informational'
)
USING DELTA
CLUSTER BY (snapshot_date, cluster_id)
COMMENT 'APC non-billing compute metrics collected from Databricks system tables';

-- -----------------------------------------------------------------------------
-- 2. apc_cluster_config_history : every configuration change of every APC.
--    Feeds Lifecycle_APC (repeating configs / active-ness).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS apc_cluster_config_history (
  lob                         STRING,
  account_id                  STRING,
  workspace_id                STRING      NOT NULL,
  compute_type                STRING      NOT NULL,
  cluster_id                  STRING      NOT NULL,
  cluster_name                STRING,
  change_time                 TIMESTAMP   NOT NULL,
  driver_node_type            STRING,
  worker_node_type            STRING,
  worker_count                INT,
  min_autoscale_workers       INT,
  max_autoscale_workers       INT,
  auto_termination_minutes    INT,
  dbr_version                 STRING,
  policy_id                   STRING,
  data_security_mode          STRING,
  delete_time                 TIMESTAMP,
  collected_at                TIMESTAMP
)
USING DELTA
CLUSTER BY (cluster_id, change_time)
COMMENT 'Configuration change history for All-Purpose Clusters';
