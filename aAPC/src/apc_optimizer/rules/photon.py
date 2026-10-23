"""Photon off when the cluster is not CPU-bound enough to benefit from it."""
from __future__ import annotations

from typing import Optional

from apc_optimizer.models import OptimizationType, RuleOutcome
from apc_optimizer.rules.base import Rule, RuleContext, clamp


class PhotonOffRule(Rule):
    optimization_type = OptimizationType.PHOTON_OFF
    config_section = "photon"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleOutcome]:
        m = ctx.metrics
        if not m.photon_enabled:
            return None
        # Photon accelerates executors; on single-node clusters the driver does the work.
        cpu_p95 = m.driver_cpu_p95 if m.is_single_node else m.worker_cpu_p95
        if cpu_p95 is None:
            return None
        threshold = float(self.params.get("cpu_p95_threshold", 30))
        if cpu_p95 >= threshold:
            return None
        multiplier = float(self.params.get("dbu_multiplier", 2.0))
        dbu_frac = 1 - 1 / multiplier if multiplier > 1 else 0.0
        return RuleOutcome(
            optimization_type=self.optimization_type,
            current_config={"runtime_engine": "PHOTON"},
            recommended_config={"runtime_engine": "STANDARD"},
            rationale=(
                f"{'Driver' if m.is_single_node else 'Worker'} CPU P95 is {cpu_p95:.1f}% "
                f"(< {threshold:g}%): workload is not compute-bound, Photon's "
                f"{multiplier:g}x DBU rate is not paying off."
            ),
            evidence={"cpu_p95": cpu_p95, "threshold": threshold, "photon_dbu_multiplier": multiplier},
            dbu_reduction_frac=dbu_frac,
            infra_reduction_frac=0.0,
            signal_strength=clamp((threshold - cpu_p95) / threshold, 0.0, 1.0),
            guardrails_applied=["PHOTON_RUNTIME_MAY_INCREASE"],
        )
