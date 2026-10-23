"""Domain models shared by every component. Pure Python - no Spark."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional


class ComputeType(str, Enum):
    APC = "APC"
    JOB_CLUSTER = "JOB_CLUSTER"


class OptimizationType(str, Enum):
    EC2_RIGHTSIZING_DRIVER = "EC2_RIGHTSIZING_DRIVER"
    EC2_RIGHTSIZING_WORKER_ASG = "EC2_RIGHTSIZING_WORKER_ASG"
    PHOTON_OFF = "PHOTON_OFF"
    AUTO_STOP = "AUTO_STOP"
    APC_TO_JOB_CLUSTER = "APC_TO_JOB_CLUSTER"


class LifecycleState(str, Enum):
    ACTIVE = "ACTIVE"              # in use, config settled -> recommend
    EXPERIMENTAL = "EXPERIMENTAL"  # in use, config still churning -> hold
    DORMANT = "DORMANT"            # exists, no runtime in active window
    DELETED = "DELETED"


class CostBasis(str, Enum):
    NET_COST_LAKE = "NET_COST_LAKE"
    NET_COST_LAKE_DEFAULT_SPLIT = "NET_COST_LAKE_DEFAULT_SPLIT"
    LIST_PRICE_ESTIMATE = "LIST_PRICE_ESTIMATE"


def _from_mapping(cls, row: Mapping[str, Any]):
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in dict(row).items() if k in names})


@dataclass
class ClusterMetrics:
    """One row of apc_metrics_table (or, in future, job_cluster_metrics_table)."""

    workspace_id: str
    cluster_id: str
    compute_type: str = ComputeType.APC.value
    snapshot_date: Optional[date] = None
    lob: Optional[str] = None
    cluster_name: Optional[str] = None
    owned_by: Optional[str] = None
    dbr_version: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    create_time: Optional[datetime] = None
    delete_time: Optional[datetime] = None
    last_config_change_time: Optional[datetime] = None

    driver_node_type: Optional[str] = None
    worker_node_type: Optional[str] = None
    driver_vcpu: Optional[int] = None
    driver_memory_gb: Optional[float] = None
    driver_gpu_count: Optional[int] = None
    worker_vcpu: Optional[int] = None
    worker_memory_gb: Optional[float] = None
    worker_gpu_count: Optional[int] = None
    worker_count: Optional[int] = None
    min_autoscale_workers: Optional[int] = None
    max_autoscale_workers: Optional[int] = None
    auto_termination_minutes: Optional[int] = None
    photon_enabled: Optional[bool] = None

    lookback_days: int = 30
    observed_days: int = 0
    telemetry_minutes: int = 0
    last_active_time: Optional[datetime] = None

    driver_cpu_p50: Optional[float] = None
    driver_cpu_p95: Optional[float] = None
    driver_cpu_max: Optional[float] = None
    driver_mem_p50: Optional[float] = None
    driver_mem_p95: Optional[float] = None
    driver_mem_max: Optional[float] = None
    worker_cpu_p50: Optional[float] = None
    worker_cpu_p95: Optional[float] = None
    worker_cpu_max: Optional[float] = None
    worker_mem_p50: Optional[float] = None
    worker_mem_p95: Optional[float] = None
    worker_mem_max: Optional[float] = None

    worker_count_p10: Optional[float] = None
    worker_count_p50: Optional[float] = None
    worker_count_p95: Optional[float] = None
    worker_count_max: Optional[int] = None
    driver_node_minutes: int = 0
    worker_node_minutes: int = 0

    uptime_minutes: int = 0
    active_minutes: int = 0
    idle_minutes: int = 0
    session_count: int = 0
    intra_session_idle_gaps: List[int] = field(default_factory=list)
    terminal_idle_tails: List[int] = field(default_factory=list)
    idle_gap_p50: Optional[float] = None
    idle_gap_p80: Optional[float] = None
    idle_gap_p90: Optional[float] = None

    total_job_runs: int = 0
    scheduled_job_runs: int = 0
    distinct_scheduled_jobs: int = 0
    scheduled_job_days: int = 0
    job_task_minutes: float = 0.0
    scheduled_job_minutes: float = 0.0
    scheduled_job_ids: List[str] = field(default_factory=list)
    dbus_consumed: Optional[float] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ClusterMetrics":
        m = _from_mapping(cls, row)
        m.intra_session_idle_gaps = list(m.intra_session_idle_gaps or [])
        m.terminal_idle_tails = list(m.terminal_idle_tails or [])
        m.scheduled_job_ids = list(m.scheduled_job_ids or [])
        m.tags = dict(m.tags or {})
        return m

    @property
    def is_autoscaling(self) -> bool:
        return self.min_autoscale_workers is not None and self.max_autoscale_workers is not None

    @property
    def is_single_node(self) -> bool:
        return not self.is_autoscaling and not self.worker_count

    @property
    def compute_id(self) -> str:
        return self.cluster_id


@dataclass
class ConfigSnapshot:
    """One row of apc_cluster_config_history."""

    cluster_id: str
    change_time: datetime
    workspace_id: Optional[str] = None
    driver_node_type: Optional[str] = None
    worker_node_type: Optional[str] = None
    worker_count: Optional[int] = None
    min_autoscale_workers: Optional[int] = None
    max_autoscale_workers: Optional[int] = None
    auto_termination_minutes: Optional[int] = None
    dbr_version: Optional[str] = None
    delete_time: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "ConfigSnapshot":
        return _from_mapping(cls, row)

    def fingerprint(self) -> str:
        """Identity of a configuration, independent of when it was applied."""
        return "|".join(
            str(v)
            for v in (
                self.driver_node_type,
                self.worker_node_type,
                self.worker_count,
                self.min_autoscale_workers,
                self.max_autoscale_workers,
                self.auto_termination_minutes,
                self.dbr_version,
            )
        )


@dataclass
class CostRecord:
    """NET cost for one compute over the lookback, from the metadata lake."""

    compute_id: str
    net_cost: float
    dbu_cost: Optional[float] = None
    infra_cost: Optional[float] = None
    cost_days: int = 0


@dataclass
class AnnualCost:
    observed_cost: float
    observed_days: int
    annual_cost: float
    annual_dbu_cost: float
    annual_infra_cost: float
    basis: CostBasis


@dataclass
class LifecycleAssessment:
    state: LifecycleState
    config_change_count: int
    distinct_config_count: int
    repeating_configs: List[str]
    current_config_age_days: Optional[float]
    current_config_is_repeating: bool
    dominant_config: Optional[str]
    dominant_config_share: float
    stability: float  # 0..1, consumed by the confidence scorer
    reason: str


@dataclass
class RuleOutcome:
    """What a rule proposes, before cost and confidence are attached."""

    optimization_type: OptimizationType
    current_config: Dict[str, Any]
    recommended_config: Dict[str, Any]
    rationale: str
    evidence: Dict[str, Any]
    # fraction of the cluster's annual DBU / infra cost this change removes
    dbu_reduction_frac: float
    infra_reduction_frac: float
    # 0..1 - how far the metric sits past the rule's threshold
    signal_strength: float
    guardrails_applied: List[str] = field(default_factory=list)


@dataclass
class Recommendation:
    recommendation_id: str
    run_id: str
    generated_at: datetime
    snapshot_date: Optional[date]
    lob: Optional[str]
    workspace_id: str
    compute_type: str
    compute_id: str
    compute_name: Optional[str]
    owned_by: Optional[str]
    optimization_type: str
    lifecycle_state: str
    current_config: str
    recommended_config: str
    rationale: str
    evidence: str
    guardrails_applied: List[str]
    annual_cost_current: float
    annual_dbu_cost_current: float
    annual_infra_cost_current: float
    annual_savings_estimate: float
    savings_pct: float
    cost_basis: str
    confidence_score: float
    confidence_band: str
    confidence_factors: str
    status: str
    rule_version: str

    def as_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class ClusterCostSummary:
    run_id: str
    generated_at: datetime
    snapshot_date: Optional[date]
    lob: Optional[str]
    workspace_id: str
    compute_type: str
    compute_id: str
    compute_name: Optional[str]
    lifecycle_state: str
    repeating_config_count: int
    config_change_count: int
    observed_cost: float
    observed_days: int
    annual_cost: float
    annual_dbu_cost: float
    annual_infra_cost: float
    cost_basis: str
    recommendation_count: int
    stacked_annual_savings: float
    skipped_reason: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)
