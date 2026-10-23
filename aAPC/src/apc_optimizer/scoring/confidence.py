"""Confidence score generator (0-100) for each recommendation.

Deterministic weighted sum of five factors, each in 0..1:
  coverage   observed days vs. a full observation window
  sample     telemetry volume (uptime minutes) behind the percentiles
  stability  Lifecycle_APC stability of the current configuration
  signal     how far past its threshold the rule fired (rule-specific)
  cost       quality of the cost basis (lake split > default split > list)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from apc_optimizer.config import EngineConfig
from apc_optimizer.models import (
    AnnualCost,
    ClusterMetrics,
    CostBasis,
    LifecycleAssessment,
    RuleOutcome,
)

COST_QUALITY = {
    CostBasis.NET_COST_LAKE: 1.0,
    CostBasis.NET_COST_LAKE_DEFAULT_SPLIT: 0.8,
    CostBasis.LIST_PRICE_ESTIMATE: 0.5,
}


@dataclass
class Confidence:
    score: float
    band: str
    factors: Dict[str, float]


class ConfidenceScorer:
    def __init__(self, config: EngineConfig):
        c = config.section("confidence")
        self.weights = c.get("weights", {})
        self.bands = c.get("bands", {"high": 75, "medium": 50})
        self.full_days = float(c.get("full_coverage_days", 30))
        self.full_sample = float(c.get("full_sample_uptime_minutes", 2400))

    def score(
        self,
        m: ClusterMetrics,
        lifecycle: LifecycleAssessment,
        annual: AnnualCost,
        outcome: RuleOutcome,
    ) -> Confidence:
        factors = {
            "coverage": min(1.0, m.observed_days / self.full_days) if self.full_days else 1.0,
            "sample": min(1.0, m.uptime_minutes / self.full_sample) if self.full_sample else 1.0,
            "stability": lifecycle.stability,
            "signal": max(0.0, min(1.0, outcome.signal_strength)),
            "cost": COST_QUALITY[annual.basis],
        }
        total_w = sum(self.weights.get(k, 0.0) for k in factors) or 1.0
        score = 100.0 * sum(factors[k] * self.weights.get(k, 0.0) for k in factors) / total_w
        score = round(score, 1)
        if score >= self.bands.get("high", 75):
            band = "HIGH"
        elif score >= self.bands.get("medium", 50):
            band = "MEDIUM"
        else:
            band = "LOW"
        return Confidence(score=score, band=band, factors={k: round(v, 4) for k, v in factors.items()})
