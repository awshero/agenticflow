"""Compute-type adapters: the single place that knows which tables a compute
type reads/writes. The engine, rules and cost model are compute-type agnostic,
so adding job clusters = a collector SQL folder + one adapter entry + rules
that declare ``applies_to = {"JOB_CLUSTER", ...}``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from apc_optimizer.models import ComputeType


@dataclass(frozen=True)
class ComputeAdapter:
    compute_type: str
    metrics_table: str
    history_table: Optional[str]
    recommendations_table: str
    cost_summary_table: str


ADAPTERS: Dict[str, ComputeAdapter] = {
    ComputeType.APC.value: ComputeAdapter(
        compute_type=ComputeType.APC.value,
        metrics_table="apc_metrics_table",
        history_table="apc_cluster_config_history",
        recommendations_table="apc_recommendations",
        cost_summary_table="apc_cluster_cost_summary",
    ),
    # Future: collector/sql/job_cluster/*.sql populates these tables.
    ComputeType.JOB_CLUSTER.value: ComputeAdapter(
        compute_type=ComputeType.JOB_CLUSTER.value,
        metrics_table="job_cluster_metrics_table",
        history_table=None,
        recommendations_table="apc_recommendations",
        cost_summary_table="apc_cluster_cost_summary",
    ),
}


def get_adapter(compute_type: str) -> ComputeAdapter:
    try:
        return ADAPTERS[compute_type]
    except KeyError:
        raise ValueError(f"Unsupported compute_type {compute_type!r}; known: {sorted(ADAPTERS)}")
