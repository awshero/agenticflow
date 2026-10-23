"""Guardrails that sit around the rules.

Cluster-level guardrails decide whether a compute is eligible at all; the
recommendation-level guardrails filter what the rules propose. Per-rule
guardrails (floors, bounds) live inside each rule and are reported in
``RuleOutcome.guardrails_applied``.
"""
from __future__ import annotations

from typing import List, Optional

from apc_optimizer.config import EngineConfig
from apc_optimizer.models import (
    ClusterMetrics,
    LifecycleAssessment,
    LifecycleState,
    OptimizationType,
    RuleOutcome,
)


class Guardrails:
    def __init__(self, config: EngineConfig):
        self.cfg = config

    def skip_reason(self, m: ClusterMetrics, lifecycle: LifecycleAssessment) -> Optional[str]:
        g = self.cfg.section("global")
        key, value = g.get("exclude_tag_key"), g.get("exclude_tag_value")
        if key and (m.tags or {}).get(key) == value:
            return f"OPTED_OUT_BY_TAG({key}={value})"
        if lifecycle.state is not LifecycleState.ACTIVE:
            return f"LIFECYCLE_{lifecycle.state.value}: {lifecycle.reason}"
        if m.observed_days < int(g.get("min_observation_days", 7)):
            return f"INSUFFICIENT_OBSERVATION_DAYS({m.observed_days})"
        if m.uptime_minutes < int(g.get("min_uptime_minutes", 600)):
            return f"INSUFFICIENT_UPTIME_MINUTES({m.uptime_minutes})"
        return None

    def filter_outcomes(self, outcomes: List[RuleOutcome]) -> List[RuleOutcome]:
        """Resolve conflicts between rules on the same compute."""
        retiring = any(
            o.optimization_type is OptimizationType.APC_TO_JOB_CLUSTER
            and "APC_RETAINED_FOR_INTERACTIVE_USE" not in o.guardrails_applied
            for o in outcomes
        )
        # If the APC is being retired, tuning its auto-stop is moot.
        return [
            o
            for o in outcomes
            if not (retiring and o.optimization_type is OptimizationType.AUTO_STOP)
        ]

    def min_savings(self) -> float:
        return float(self.cfg.get("global.min_annual_savings_usd", 0))
