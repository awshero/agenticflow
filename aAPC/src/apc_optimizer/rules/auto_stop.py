"""Auto Stop (auto-termination) tuned to the cluster's real idle pattern.

The collector splits idle streaks into
  * intra-session gaps - idle, then the user came back (a lower auto-stop
    would have caused a cold start), and
  * terminal tails     - idle until the cluster auto-terminated (pure waste
    beyond the new setting).
The recommended value is the smallest candidate whose cold-start rate over
the intra-session gaps stays within ``max_restart_rate``.
"""
from __future__ import annotations

from typing import List, Optional

from apc_optimizer.models import OptimizationType, RuleOutcome
from apc_optimizer.rules.base import Rule, RuleContext, clamp


def restart_rate(gaps: List[int], minutes: int) -> float:
    return sum(1 for g in gaps if g > minutes) / len(gaps) if gaps else 0.0


class AutoStopRule(Rule):
    optimization_type = OptimizationType.AUTO_STOP
    config_section = "auto_stop"

    def choose(self, gaps: List[int]) -> int:
        lo = int(self.params.get("min_minutes", 10))
        hi = int(self.params.get("max_minutes", 120))
        max_rate = float(self.params.get("max_restart_rate", 0.2))
        candidates = sorted(c for c in self.params.get("candidate_minutes", []) if lo <= c <= hi) or [hi]
        for c in candidates:
            if restart_rate(gaps, c) <= max_rate:
                return c
        return candidates[-1]

    def evaluate(self, ctx: RuleContext) -> Optional[RuleOutcome]:
        m = ctx.metrics
        if m.uptime_minutes <= 0:
            return None
        current = m.auto_termination_minutes or 0  # 0 => auto-stop disabled
        gaps = [int(g) for g in m.intra_session_idle_gaps if g is not None]
        tails = [int(t) for t in m.terminal_idle_tails if t is not None]
        target = self.choose(gaps)
        if current and target >= current:
            return None

        penalty = int(self.params.get("restart_penalty_minutes", 5))
        saved_gap = sum(max(0, g - target - penalty) for g in gaps if g > target)
        saved_tail = sum(max(0, t - target) for t in tails)
        saved = saved_gap + saved_tail
        if saved <= 0:
            return None
        frac = clamp(saved / m.uptime_minutes, 0.0, 1.0)
        rate = restart_rate(gaps, target)
        sample = min(1.0, (len(gaps) + len(tails)) / 20.0)
        guardrails = []
        if not current:
            guardrails.append("AUTO_STOP_WAS_DISABLED")
        if target == int(self.params.get("min_minutes", 10)):
            guardrails.append(f"AUTO_STOP_MIN_BOUND({target})")
        return RuleOutcome(
            optimization_type=self.optimization_type,
            current_config={"auto_termination_minutes": current},
            recommended_config={"auto_termination_minutes": target},
            rationale=(
                f"Idle {m.idle_minutes} of {m.uptime_minutes} uptime minutes. "
                f"Auto-stop {current or 'disabled'} -> {target} min saves ~{saved} idle "
                f"minutes over {m.observed_days}d with a {rate:.0%} cold-start rate on resumed sessions."
            ),
            evidence={
                "idle_minutes": m.idle_minutes,
                "uptime_minutes": m.uptime_minutes,
                "intra_session_gap_count": len(gaps),
                "terminal_tail_count": len(tails),
                "idle_gap_p50": m.idle_gap_p50,
                "idle_gap_p80": m.idle_gap_p80,
                "idle_gap_p90": m.idle_gap_p90,
                "saved_idle_minutes": saved,
                "cold_start_rate": round(rate, 4),
            },
            dbu_reduction_frac=frac,
            infra_reduction_frac=frac,
            signal_strength=clamp((1 - rate) * (0.5 + 0.5 * sample), 0.0, 1.0),
            guardrails_applied=guardrails,
        )
