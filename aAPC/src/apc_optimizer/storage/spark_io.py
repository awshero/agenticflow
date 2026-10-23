"""Spark/Delta I/O for the engine. The only module that imports pyspark."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from apc_optimizer.compute_types import ComputeAdapter
from apc_optimizer.config import EngineConfig
from apc_optimizer.models import ClusterMetrics, ConfigSnapshot, CostRecord

# Column order must match collector/sql/90_setup_engine_tables.sql.
RECOMMENDATION_SCHEMA = """
  recommendation_id STRING, run_id STRING, generated_at TIMESTAMP, snapshot_date DATE,
  lob STRING, workspace_id STRING, compute_type STRING, compute_id STRING,
  compute_name STRING, owned_by STRING, optimization_type STRING, lifecycle_state STRING,
  current_config STRING, recommended_config STRING, rationale STRING, evidence STRING,
  guardrails_applied ARRAY<STRING>, annual_cost_current DOUBLE, annual_dbu_cost_current DOUBLE,
  annual_infra_cost_current DOUBLE, annual_savings_estimate DOUBLE, savings_pct DOUBLE,
  cost_basis STRING, confidence_score DOUBLE, confidence_band STRING,
  confidence_factors STRING, status STRING, rule_version STRING
"""

COST_SUMMARY_SCHEMA = """
  run_id STRING, generated_at TIMESTAMP, snapshot_date DATE, lob STRING,
  workspace_id STRING, compute_type STRING, compute_id STRING, compute_name STRING,
  lifecycle_state STRING, repeating_config_count INT, config_change_count INT,
  observed_cost DOUBLE, observed_days INT, annual_cost DOUBLE, annual_dbu_cost DOUBLE,
  annual_infra_cost DOUBLE, cost_basis STRING, recommendation_count INT,
  stacked_annual_savings DOUBLE, skipped_reason STRING
"""


def _columns(schema_ddl: str) -> List[str]:
    cols = []
    depth = 0
    token = ""
    for ch in schema_ddl:
        depth += ch == "<"
        depth -= ch == ">"
        if ch == "," and depth == 0:
            cols.append(token.split()[0])
            token = ""
        else:
            token += ch
    if token.strip():
        cols.append(token.split()[0])
    return cols


class SparkIO:
    def __init__(self, spark, catalog: str, schema: str, adapter: ComputeAdapter, config: EngineConfig):
        self.spark = spark
        self.ns = f"`{catalog}`.`{schema}`"
        self.adapter = adapter
        self.cfg = config

    def _t(self, name: str) -> str:
        return f"{self.ns}.`{name}`"

    # ------------------------------------------------------------ reads --
    def read_metrics(self, lob: Optional[str] = None) -> List[ClusterMetrics]:
        table = self._t(self.adapter.metrics_table)
        sql = f"SELECT * FROM {table} WHERE snapshot_date = (SELECT max(snapshot_date) FROM {table})"
        args: Dict[str, Any] = {}
        if lob:
            sql += " AND lob = :lob"
            args["lob"] = lob
        rows = self.spark.sql(sql, args=args).collect()
        return [ClusterMetrics.from_row(r.asDict(recursive=True)) for r in rows]

    def read_history(self, history_days: int) -> Dict[str, List[ConfigSnapshot]]:
        if not self.adapter.history_table:
            return {}
        rows = self.spark.sql(
            f"SELECT * FROM {self._t(self.adapter.history_table)} "
            f"WHERE change_time >= current_timestamp() - make_interval(0, 0, 0, :days)",
            args={"days": int(history_days)},
        ).collect()
        out: Dict[str, List[ConfigSnapshot]] = defaultdict(list)
        for r in rows:
            snap = ConfigSnapshot.from_row(r.asDict())
            out[snap.cluster_id].append(snap)
        return out

    def read_costs(self, cost_table: str, lookback_days: int) -> Dict[str, CostRecord]:
        """NET cost per compute over the lookback, split DBU vs infra when possible."""
        src = self.cfg.section("cost_source")
        cid, dcol, ncol = src["compute_id_col"], src["date_col"], src["net_cost_col"]
        cat = src.get("category_col")
        dbu_vals = [str(v).upper() for v in self.cfg.get("cost.dbu_categories", [])]
        infra_vals = [str(v).upper() for v in self.cfg.get("cost.infra_categories", [])]

        if cat:
            dbu_in = ", ".join(f"'{v}'" for v in dbu_vals) or "''"
            infra_in = ", ".join(f"'{v}'" for v in infra_vals) or "''"
            split = (
                f", sum(CASE WHEN upper(`{cat}`) IN ({dbu_in}) THEN `{ncol}` END) AS dbu_cost"
                f", sum(CASE WHEN upper(`{cat}`) IN ({infra_in}) THEN `{ncol}` END) AS infra_cost"
            )
        else:
            split = ", CAST(NULL AS DOUBLE) AS dbu_cost, CAST(NULL AS DOUBLE) AS infra_cost"

        rows = self.spark.sql(
            f"""
            SELECT CAST(`{cid}` AS STRING) AS compute_id,
                   sum(`{ncol}`) AS net_cost,
                   count(DISTINCT `{dcol}`) AS cost_days
                   {split}
            FROM IDENTIFIER(:cost_table)
            WHERE `{dcol}` >= date_sub(current_date(), :days)
              AND `{cid}` IS NOT NULL
            GROUP BY 1
            """,
            args={"cost_table": cost_table, "days": int(lookback_days)},
        ).collect()
        return {
            r["compute_id"]: CostRecord(
                compute_id=r["compute_id"],
                net_cost=float(r["net_cost"] or 0.0),
                dbu_cost=None if r["dbu_cost"] is None else float(r["dbu_cost"]),
                infra_cost=None if r["infra_cost"] is None else float(r["infra_cost"]),
                cost_days=int(r["cost_days"] or 0),
            )
            for r in rows
        }

    # ----------------------------------------------------------- writes --
    def _append(self, rows: Sequence[Dict[str, Any]], table: str, schema_ddl: str) -> int:
        if not rows:
            return 0
        cols = _columns(schema_ddl)
        df = self.spark.createDataFrame([tuple(r[c] for c in cols) for r in rows], schema=schema_ddl)
        df.write.format("delta").mode("append").saveAsTable(self._t(table).replace("`", ""))
        return len(rows)

    def write_recommendations(self, rows: Iterable[Dict[str, Any]]) -> int:
        return self._append(list(rows), self.adapter.recommendations_table, RECOMMENDATION_SCHEMA)

    def write_cost_summaries(self, rows: Iterable[Dict[str, Any]]) -> int:
        return self._append(list(rows), self.adapter.cost_summary_table, COST_SUMMARY_SCHEMA)
