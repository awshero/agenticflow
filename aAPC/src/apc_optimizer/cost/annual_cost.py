"""Annual_Cost_Generator: annualises the NET cost of each compute.

NET cost comes from the metadata lake (already net of discounts/credits). When
the lake has no DBU vs infra split, a configured default share is used; when a
compute has no cost rows at all, a list-price estimate from node-minutes keeps
the pipeline running (and the confidence scorer marks it down).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from apc_optimizer.catalog import InstanceCatalog
from apc_optimizer.config import EngineConfig
from apc_optimizer.models import AnnualCost, ClusterMetrics, CostBasis, CostRecord

DAYS_PER_YEAR = 365.0


class AnnualCostGenerator:
    def __init__(self, config: EngineConfig, catalog: InstanceCatalog):
        self.cfg = config
        self.catalog = catalog

    def billable_days(self, m: ClusterMetrics) -> int:
        """Days of the lookback window the compute existed for."""
        days = int(m.lookback_days or self.cfg.get("global.lookback_days", 30))
        if m.create_time is not None and isinstance(m.snapshot_date, date):
            created = m.create_time.date() if isinstance(m.create_time, datetime) else m.create_time
            age = (m.snapshot_date - created).days
            if 0 < age < days:
                days = age
        return max(1, days)

    def annualize(self, m: ClusterMetrics, cost: Optional[CostRecord]) -> AnnualCost:
        days = self.billable_days(m)
        factor = DAYS_PER_YEAR / days
        if cost is not None and cost.net_cost > 0:
            if cost.dbu_cost is not None and cost.infra_cost is not None:
                dbu, infra = cost.dbu_cost, cost.infra_cost
                basis = CostBasis.NET_COST_LAKE
            else:
                share = float(self.cfg.get("cost.default_dbu_share", 0.5))
                dbu, infra = cost.net_cost * share, cost.net_cost * (1 - share)
                basis = CostBasis.NET_COST_LAKE_DEFAULT_SPLIT
            observed = cost.net_cost
        else:
            dbu, infra = self._list_estimate(m)
            observed = dbu + infra
            basis = CostBasis.LIST_PRICE_ESTIMATE
        return AnnualCost(
            observed_cost=round(observed, 2),
            observed_days=days,
            annual_cost=round((dbu + infra) * factor, 2),
            annual_dbu_cost=round(dbu * factor, 2),
            annual_infra_cost=round(infra * factor, 2),
            basis=basis,
        )

    def _list_estimate(self, m: ClusterMetrics):
        rate = float(self.cfg.get("cost.list_dbu_rate", 0.55))
        photon = float(self.cfg.get("photon.dbu_multiplier", 2.0)) if m.photon_enabled else 1.0
        dbu = infra = 0.0
        for node_type, minutes in (
            (m.driver_node_type, m.driver_node_minutes),
            (m.worker_node_type, m.worker_node_minutes),
        ):
            t = self.catalog.get(node_type)
            if t is None or not minutes:
                continue
            hours = minutes / 60.0
            dbu += hours * t.dbu_per_hour * rate * photon
            infra += hours * t.price_per_hour
        return dbu, infra
