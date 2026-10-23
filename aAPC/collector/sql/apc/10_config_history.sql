-- =============================================================================
-- APC Compute Optimizer :: 10_config_history.sql
-- Captures the configuration-change history of All-Purpose Clusters from
-- system.compute.clusters (one row per change) for Lifecycle_APC.
-- Parameters: :catalog, :schema, :lob, :history_days
-- =============================================================================

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

MERGE INTO apc_cluster_config_history AS t
USING (
  SELECT
    :lob                                   AS lob,
    c.account_id,
    c.workspace_id,
    'APC'                                  AS compute_type,
    c.cluster_id,
    c.cluster_name,
    c.change_time,
    c.driver_node_type,
    c.worker_node_type,
    CAST(c.worker_count AS INT)            AS worker_count,
    CAST(c.min_autoscale_workers AS INT)   AS min_autoscale_workers,
    CAST(c.max_autoscale_workers AS INT)   AS max_autoscale_workers,
    CAST(c.auto_termination_minutes AS INT) AS auto_termination_minutes,
    c.dbr_version,
    c.policy_id,
    c.data_security_mode,
    c.delete_time,
    current_timestamp()                    AS collected_at
  FROM system.compute.clusters c
  WHERE c.cluster_source IN ('UI', 'API')                -- All-Purpose only
    AND c.change_date >= date_sub(current_date(), CAST(:history_days AS INT))
) AS s
ON  t.workspace_id = s.workspace_id
AND t.cluster_id   = s.cluster_id
AND t.change_time  = s.change_time
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
