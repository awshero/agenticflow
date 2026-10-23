"""Cost saving estimator: turns a rule's cost-reduction fractions into dollars."""
from __future__ import annotations

from typing import Iterable

from apc_optimizer.models import AnnualCost, RuleOutcome


class SavingsEstimator:
    @staticmethod
    def estimate(annual: AnnualCost, outcome: RuleOutcome) -> float:
        return round(
            annual.annual_dbu_cost * outcome.dbu_reduction_frac
            + annual.annual_infra_cost * outcome.infra_reduction_frac,
            2,
        )

    @staticmethod
    def stacked(annual: AnnualCost, outcomes: Iterable[RuleOutcome]) -> float:
        """Savings if every recommendation is applied together.

        Reductions compound on what is left (Photon off on an already
        right-sized fleet saves less than on the original), so the fractions
        multiply instead of adding.
        """
        dbu_left = infra_left = 1.0
        for o in outcomes:
            dbu_left *= 1 - o.dbu_reduction_frac
            infra_left *= 1 - o.infra_reduction_frac
        return round(
            annual.annual_dbu_cost * (1 - dbu_left) + annual.annual_infra_cost * (1 - infra_left),
            2,
        )
