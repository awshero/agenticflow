-- =============================================================================
-- APC Compute Optimizer :: 90_setup_engine_tables.sql
-- Output tables of the recommendation engine. NOT part of the standalone
-- collector job; the full pipeline (aAPC/resources) runs it before the engine.
-- Idempotent. Parameters: :catalog, :schema
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS IDENTIFIER(:catalog || '.' || :schema);

USE CATALOG IDENTIFIER(:catalog);
USE SCHEMA IDENTIFIER(:schema);

-- -----------------------------------------------------------------------------
-- 1. apc_recommendations : output of the recommendation engine (append-only,
--    one batch per run_id).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS apc_recommendations (
  recommendation_id           STRING      NOT NULL,
  run_id                      STRING      NOT NULL,
  generated_at                TIMESTAMP   NOT NULL,
  snapshot_date               DATE,
  lob                         STRING,
  workspace_id                STRING,
  compute_type                STRING,
  compute_id                  STRING,
  compute_name                STRING,
  owned_by                    STRING,
  optimization_type           STRING      COMMENT 'EC2_RIGHTSIZING_DRIVER | EC2_RIGHTSIZING_WORKER_ASG | PHOTON_OFF | AUTO_STOP | APC_TO_JOB_CLUSTER',
  lifecycle_state             STRING,
  current_config              STRING      COMMENT 'JSON',
  recommended_config          STRING      COMMENT 'JSON',
  rationale                   STRING,
  evidence                    STRING      COMMENT 'JSON metrics that triggered the rule',
  guardrails_applied          ARRAY<STRING>,
  annual_cost_current         DOUBLE,
  annual_dbu_cost_current     DOUBLE,
  annual_infra_cost_current   DOUBLE,
  annual_savings_estimate     DOUBLE,
  savings_pct                 DOUBLE,
  cost_basis                  STRING      COMMENT 'NET_COST_LAKE | NET_COST_LAKE_DEFAULT_SPLIT | LIST_PRICE_ESTIMATE',
  confidence_score            DOUBLE,
  confidence_band             STRING,
  confidence_factors          STRING      COMMENT 'JSON',
  status                      STRING,
  rule_version                STRING
)
USING DELTA
CLUSTER BY (run_id, compute_id)
COMMENT 'Deterministic compute optimization recommendations';

-- -----------------------------------------------------------------------------
-- 2. apc_cluster_cost_summary : Annual_Cost_Generator output + stacked savings.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS apc_cluster_cost_summary (
  run_id                      STRING      NOT NULL,
  generated_at                TIMESTAMP   NOT NULL,
  snapshot_date               DATE,
  lob                         STRING,
  workspace_id                STRING,
  compute_type                STRING,
  compute_id                  STRING,
  compute_name                STRING,
  lifecycle_state             STRING,
  repeating_config_count      INT,
  config_change_count         INT,
  observed_cost               DOUBLE,
  observed_days               INT,
  annual_cost                 DOUBLE,
  annual_dbu_cost             DOUBLE,
  annual_infra_cost           DOUBLE,
  cost_basis                  STRING,
  recommendation_count        INT,
  stacked_annual_savings      DOUBLE      COMMENT 'Savings if all recommendations applied (multiplicative, not additive)',
  skipped_reason              STRING
)
USING DELTA
CLUSTER BY (run_id, compute_id);

CREATE OR REPLACE VIEW apc_recommendations_latest AS
SELECT *
FROM apc_recommendations
WHERE run_id = (SELECT max_by(run_id, generated_at) FROM apc_recommendations);
