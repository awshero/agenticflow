"""Rule contract. A rule looks at one compute's metrics and either proposes a
change (RuleOutcome) or returns None. Rules never touch money directly: they
state what *fraction* of DBU / infra cost the change removes, and the savings
estimator turns that into dollars against the NET cost."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import ClassVar, FrozenSet, Optional

from apc_optimizer.catalog import InstanceCatalog, InstanceType
from apc_optimizer.config import EngineConfig
from apc_optimizer.models import (
    ClusterMetrics,
    ComputeType,
    LifecycleAssessment,
    OptimizationType,
    RuleOutcome,
)


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass
class RuleContext:
    metrics: ClusterMetrics
    lifecycle: LifecycleAssessment
    catalog: InstanceCatalog
    config: EngineConfig

    @property
    def driver_type(self) -> Optional[InstanceType]:
        return self.catalog.get(self.metrics.driver_node_type)

    @property
    def worker_type(self) -> Optional[InstanceType]:
        return self.catalog.get(self.metrics.worker_node_type)

    def role_share(self, role: str, component: str) -> float:
        """Share of the cluster's DBU (component='dbu') or infra ('infra') cost
        attributable to the driver or the workers, from node-minutes x rate."""
        m = self.metrics
        d, w = self.driver_type, self.worker_type

        def rate(t: Optional[InstanceType]) -> float:
            if t is None:
                return 0.0
            return t.dbu_per_hour if component == "dbu" else t.price_per_hour

        driver_part = m.driver_node_minutes * rate(d)
        worker_part = m.worker_node_minutes * rate(w)
        total = driver_part + worker_part
        if total <= 0:
            return 1.0 if role == "driver" and m.worker_node_minutes == 0 else 0.0
        return (driver_part if role == "driver" else worker_part) / total


class Rule(abc.ABC):
    optimization_type: ClassVar[OptimizationType]
    config_section: ClassVar[str]
    applies_to: ClassVar[FrozenSet[str]] = frozenset({ComputeType.APC.value})

    def __init__(self, config: EngineConfig):
        self.cfg = config
        self.params = config.section(self.config_section)

    @property
    def enabled(self) -> bool:
        return bool(self.params.get("enabled", True))

    def supports(self, compute_type: str) -> bool:
        return compute_type in self.applies_to

    @abc.abstractmethod
    def evaluate(self, ctx: RuleContext) -> Optional[RuleOutcome]:
        ...
