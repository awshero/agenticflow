"""Rule registry. Add a rule class here and it runs for every compute type it
declares in ``applies_to`` - this is how job clusters get rules later."""
from __future__ import annotations

from typing import List, Type

from apc_optimizer.config import EngineConfig
from apc_optimizer.rules.apc_to_job import ApcToJobClusterRule
from apc_optimizer.rules.auto_stop import AutoStopRule
from apc_optimizer.rules.base import Rule, RuleContext
from apc_optimizer.rules.guardrails import Guardrails
from apc_optimizer.rules.photon import PhotonOffRule
from apc_optimizer.rules.rightsizing import DriverRightsizingRule, WorkerRightsizingAsgRule

RULES: List[Type[Rule]] = [
    DriverRightsizingRule,
    WorkerRightsizingAsgRule,
    PhotonOffRule,
    AutoStopRule,
    ApcToJobClusterRule,
]


def build_rules(config: EngineConfig, compute_type: str) -> List[Rule]:
    rules = [cls(config) for cls in RULES]
    return [r for r in rules if r.enabled and r.supports(compute_type)]


__all__ = ["RULES", "Rule", "RuleContext", "Guardrails", "build_rules"]
