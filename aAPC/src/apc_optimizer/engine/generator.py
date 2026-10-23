"""Recommendation generator: metrics -> lifecycle -> guardrails -> rules ->
annual cost -> savings -> confidence -> Recommendation rows.

Pure Python over domain objects, so the whole decision path is unit-testable
without Spark; ``storage.spark_io`` does the reading and writing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence

from apc_optimizer.catalog import InstanceCatalog
from apc_optimizer.config import EngineConfig
from apc_optimizer.cost.annual_cost import AnnualCostGenerator
from apc_optimizer.cost.savings import SavingsEstimator
from apc_optimizer.lifecycle.lifecycle_apc import LifecycleAPC
from apc_optimizer.models import (
    ClusterCostSummary,
    ClusterMetrics,
    ConfigSnapshot,
    CostRecord,
    Recommendation,
    RuleOutcome,
)
from apc_optimizer.rules import Guardrails, RuleContext, build_rules
from apc_optimizer.scoring.confidence import ConfidenceScorer


def _json(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)


def recommendation_id(run_id: str, workspace_id: str, compute_id: str, opt_type: str) -> str:
    raw = f"{run_id}|{workspace_id}|{compute_id}|{opt_type}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@dataclass
class GenerationResult:
    recommendations: List[Recommendation] = field(default_factory=list)
    summaries: List[ClusterCostSummary] = field(default_factory=list)


class RecommendationGenerator:
    def __init__(self, config: EngineConfig, catalog: InstanceCatalog):
        self.cfg = config
        self.catalog = catalog
        self.lifecycle = LifecycleAPC(config)
        self.guardrails = Guardrails(config)
        self.annual = AnnualCostGenerator(config, catalog)
        self.scorer = ConfidenceScorer(config)

    def run(
        self,
        metrics: Iterable[ClusterMetrics],
        history: Dict[str, Sequence[ConfigSnapshot]],
        costs: Dict[str, CostRecord],
        run_id: str,
        generated_at: Optional[datetime] = None,
    ) -> GenerationResult:
        generated_at = generated_at or datetime.utcnow()
        result = GenerationResult()
        for m in metrics:
            recs, summary = self.for_compute(
                m, history.get(m.compute_id, []), costs.get(m.compute_id), run_id, generated_at
            )
            result.recommendations.extend(recs)
            result.summaries.append(summary)
        return result

    def for_compute(
        self,
        m: ClusterMetrics,
        history: Sequence[ConfigSnapshot],
        cost: Optional[CostRecord],
        run_id: str,
        generated_at: datetime,
    ):
        lifecycle = self.lifecycle.assess(m, history)
        annual = self.annual.annualize(m, cost)
        skip = self.guardrails.skip_reason(m, lifecycle)

        kept: List[RuleOutcome] = []
        recs: List[Recommendation] = []
        if skip is None:
            ctx = RuleContext(metrics=m, lifecycle=lifecycle, catalog=self.catalog, config=self.cfg)
            outcomes = [o for o in (r.evaluate(ctx) for r in build_rules(self.cfg, m.compute_type)) if o]
            min_savings = self.guardrails.min_savings()
            for o in self.guardrails.filter_outcomes(outcomes):
                savings = SavingsEstimator.estimate(annual, o)
                if savings < min_savings:
                    continue
                kept.append(o)
                conf = self.scorer.score(m, lifecycle, annual, o)
                recs.append(
                    Recommendation(
                        recommendation_id=recommendation_id(
                            run_id, m.workspace_id, m.compute_id, o.optimization_type.value
                        ),
                        run_id=run_id,
                        generated_at=generated_at,
                        snapshot_date=m.snapshot_date,
                        lob=m.lob,
                        workspace_id=m.workspace_id,
                        compute_type=m.compute_type,
                        compute_id=m.compute_id,
                        compute_name=m.cluster_name,
                        owned_by=m.owned_by,
                        optimization_type=o.optimization_type.value,
                        lifecycle_state=lifecycle.state.value,
                        current_config=_json(o.current_config),
                        recommended_config=_json(o.recommended_config),
                        rationale=o.rationale,
                        evidence=_json(o.evidence),
                        guardrails_applied=list(o.guardrails_applied),
                        annual_cost_current=annual.annual_cost,
                        annual_dbu_cost_current=annual.annual_dbu_cost,
                        annual_infra_cost_current=annual.annual_infra_cost,
                        annual_savings_estimate=savings,
                        savings_pct=round(100.0 * savings / annual.annual_cost, 2) if annual.annual_cost else 0.0,
                        cost_basis=annual.basis.value,
                        confidence_score=conf.score,
                        confidence_band=conf.band,
                        confidence_factors=_json(conf.factors),
                        status="OPEN",
                        rule_version=self.cfg.rule_version,
                    )
                )

        summary = ClusterCostSummary(
            run_id=run_id,
            generated_at=generated_at,
            snapshot_date=m.snapshot_date,
            lob=m.lob,
            workspace_id=m.workspace_id,
            compute_type=m.compute_type,
            compute_id=m.compute_id,
            compute_name=m.cluster_name,
            lifecycle_state=lifecycle.state.value,
            repeating_config_count=len(lifecycle.repeating_configs),
            config_change_count=lifecycle.config_change_count,
            observed_cost=annual.observed_cost,
            observed_days=annual.observed_days,
            annual_cost=annual.annual_cost,
            annual_dbu_cost=annual.annual_dbu_cost,
            annual_infra_cost=annual.annual_infra_cost,
            cost_basis=annual.basis.value,
            recommendation_count=len(recs),
            stacked_annual_savings=SavingsEstimator.stacked(annual, kept),
            skipped_reason=skip,
        )
        return recs, summary
