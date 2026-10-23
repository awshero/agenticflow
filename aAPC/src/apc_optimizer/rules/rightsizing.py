"""EC2 rightsizing for driver and workers.

Requirement per node = current capacity x P95 utilisation x (1 + headroom).
The driver gets the cheapest node that covers its requirement. Workers are
bundled with the autoscaler (ASG): every candidate node shape gets its own
min/max worker count sized to the observed executor concurrency, and the
cheapest *fleet* wins - so moving to smaller nodes and adding workers (or the
reverse) is evaluated as one decision rather than two conflicting ones.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from apc_optimizer.catalog import InstanceType
from apc_optimizer.models import OptimizationType, RuleOutcome
from apc_optimizer.rules.base import Rule, RuleContext, clamp


class _RightsizingBase(Rule):
    config_section = "rightsizing"

    @property
    def headroom(self) -> float:
        return float(self.params.get("headroom_pct", 10)) / 100.0

    @property
    def list_dbu_rate(self) -> float:
        return float(self.cfg.get("cost.list_dbu_rate", 0.55))

    def requirement(
        self, node: InstanceType, cpu_p95: float, mem_p95: float, role: str, node_floors: bool
    ) -> Tuple[float, float, List[str]]:
        """(required vCPU, required GiB, guardrails applied) for one node.

        Driver floors apply to the requirement itself; worker floors apply to
        the candidate node instead, because the fleet size absorbs the rest.
        """
        floors = self.params.get(role, {}) if node_floors else {}
        ratio = float(self.params.get("max_downsize_ratio", 0.25))
        req_vcpu = node.vcpu * cpu_p95 / 100.0 * (1 + self.headroom)
        req_mem = node.memory_gb * mem_p95 / 100.0 * (1 + self.headroom)
        applied: List[str] = []
        min_vcpu = max(float(floors.get("min_vcpu", 0)), node.vcpu * ratio)
        min_mem = max(float(floors.get("min_memory_gb", 0)), node.memory_gb * ratio)
        if req_vcpu < min_vcpu:
            req_vcpu = min_vcpu
            applied.append(f"{role.upper()}_MIN_VCPU_FLOOR({min_vcpu:g})")
        if req_mem < min_mem:
            req_mem = min_mem
            applied.append(f"{role.upper()}_MIN_MEMORY_FLOOR({min_mem:g}GB)")
        return req_vcpu, req_mem, applied

    def candidates(self, ctx: RuleContext, current: InstanceType) -> List[InstanceType]:
        return ctx.catalog.candidates(
            current,
            self.params.get("allowed_families", []),
            bool(self.params.get("allow_family_change", True)),
        )

    def _rank_key(self, t: InstanceType, current: InstanceType, cost: float):
        # cheapest first; on ties prefer staying in the same family, then fewer vCPU
        return (round(cost, 6), t.family != current.family, t.vcpu, t.name)


class DriverRightsizingRule(_RightsizingBase):
    optimization_type = OptimizationType.EC2_RIGHTSIZING_DRIVER

    def evaluate(self, ctx: RuleContext) -> Optional[RuleOutcome]:
        m = ctx.metrics
        current = ctx.driver_type
        if current is None or m.driver_cpu_p95 is None or m.driver_mem_p95 is None:
            return None
        if self.params.get("skip_gpu", True) and (m.driver_gpu_count or 0) > 0:
            return None

        req_vcpu, req_mem, applied = self.requirement(
            current, m.driver_cpu_p95, m.driver_mem_p95, "driver", node_floors=True
        )
        rate = self.list_dbu_rate
        fits = [
            t
            for t in self.candidates(ctx, current)
            if t.vcpu >= req_vcpu and t.memory_gb >= req_mem
        ]
        if not fits:
            return None
        best = min(fits, key=lambda t: self._rank_key(t, current, t.hourly_cost(rate)))
        reduction = 1 - best.hourly_cost(rate) / current.hourly_cost(rate)
        if best.name == current.name or reduction * 100 < float(self.params.get("min_cost_reduction_pct", 5)):
            return None

        dbu_frac = ctx.role_share("driver", "dbu") * (1 - best.dbu_per_hour / current.dbu_per_hour)
        infra_frac = ctx.role_share("driver", "infra") * (1 - best.price_per_hour / current.price_per_hour)
        signal = clamp(1 - max(req_vcpu / current.vcpu, req_mem / current.memory_gb), 0.0, 1.0)
        return RuleOutcome(
            optimization_type=self.optimization_type,
            current_config={
                "driver_node_type": current.name,
                "vcpu": current.vcpu,
                "memory_gb": current.memory_gb,
            },
            recommended_config={
                "driver_node_type": best.name,
                "vcpu": best.vcpu,
                "memory_gb": best.memory_gb,
            },
            rationale=(
                f"Driver P95 CPU {m.driver_cpu_p95:.1f}% / memory {m.driver_mem_p95:.1f}% on "
                f"{current.name}; with {self.headroom:.0%} headroom it needs "
                f"{req_vcpu:.1f} vCPU / {req_mem:.1f} GiB -> {best.name}."
            ),
            evidence={
                "driver_cpu_p95": m.driver_cpu_p95,
                "driver_mem_p95": m.driver_mem_p95,
                "required_vcpu": round(req_vcpu, 2),
                "required_memory_gb": round(req_mem, 2),
                "headroom_pct": self.headroom * 100,
            },
            dbu_reduction_frac=max(0.0, dbu_frac),
            infra_reduction_frac=max(0.0, infra_frac),
            signal_strength=signal,
            guardrails_applied=applied,
        )


class WorkerRightsizingAsgRule(_RightsizingBase):
    """Worker node shape + autoscaling min/max, decided together."""

    optimization_type = OptimizationType.EC2_RIGHTSIZING_WORKER_ASG

    def _current_counts(self, ctx: RuleContext) -> Tuple[Optional[int], Optional[int]]:
        m = ctx.metrics
        if m.is_autoscaling:
            return m.min_autoscale_workers, m.max_autoscale_workers
        return m.worker_count, m.worker_count

    def _fleet(
        self,
        cand: InstanceType,
        req_vcpu: float,
        req_mem: float,
        p10: float,
        p50: float,
        p95: float,
        autoscaling: bool,
    ) -> Dict[str, Any]:
        asg = self.cfg.section("asg")
        floor_n = int(asg.get("min_workers_floor", 1))
        ceil_n = int(asg.get("max_workers_ceiling", 100))
        asg_headroom = float(asg.get("headroom_pct", 10)) / 100.0
        # how many candidate nodes replace one current node at P95 load
        scale = max(req_vcpu / cand.vcpu, req_mem / cand.memory_gb)
        new_max = int(clamp(math.ceil(p95 * scale * (1 + asg_headroom) - 1e-9), floor_n, ceil_n))
        if autoscaling:
            new_min = int(clamp(math.floor(p10 * scale), floor_n, new_max))
        else:
            new_min = new_max
        expected = clamp(p50 * scale, new_min, new_max)
        return {"scale": scale, "min": new_min, "max": new_max, "expected_workers": expected}

    def evaluate(self, ctx: RuleContext) -> Optional[RuleOutcome]:
        m = ctx.metrics
        current = ctx.worker_type
        if m.is_single_node or current is None:
            return None
        if m.worker_cpu_p95 is None or m.worker_mem_p95 is None or m.worker_count_p95 is None:
            return None
        if self.params.get("skip_gpu", True) and (m.worker_gpu_count or 0) > 0:
            return None

        cur_min, cur_max = self._current_counts(ctx)
        p95 = float(m.worker_count_p95 or 0) or float(cur_max or 0)
        p50 = float(m.worker_count_p50 if m.worker_count_p50 is not None else p95)
        p10 = float(m.worker_count_p10 if m.worker_count_p10 is not None else p50)
        if p95 <= 0:
            return None

        req_vcpu, req_mem, applied = self.requirement(
            current, m.worker_cpu_p95, m.worker_mem_p95, "worker", node_floors=False
        )
        rate = self.list_dbu_rate
        current_fleet_cost = p50 * current.hourly_cost(rate)
        floors = self.params.get("worker", {})
        best: Optional[Tuple[InstanceType, Dict[str, Any], float]] = None
        for cand in self.candidates(ctx, current):
            if cand.vcpu < float(floors.get("min_vcpu", 0)) or cand.memory_gb < float(floors.get("min_memory_gb", 0)):
                continue
            if cand.vcpu < current.vcpu * float(self.params.get("max_downsize_ratio", 0.25)):
                continue
            fleet = self._fleet(cand, req_vcpu, req_mem, p10, p50, p95, m.is_autoscaling)
            cost = fleet["expected_workers"] * cand.hourly_cost(rate)
            if best is None or self._rank_key(cand, current, cost) < self._rank_key(best[0], current, best[2]):
                best = (cand, fleet, cost)
        if best is None:
            return None
        cand, fleet, new_cost = best

        reduction = 1 - new_cost / current_fleet_cost if current_fleet_cost > 0 else 0.0
        min_pct = float(self.params.get("min_cost_reduction_pct", 5))
        if reduction * 100 < min_pct:
            return None
        if m.is_autoscaling:
            asg_rec = {"min_autoscale_workers": fleet["min"], "max_autoscale_workers": fleet["max"]}
            asg_cur = {"min_autoscale_workers": cur_min, "max_autoscale_workers": cur_max}
        else:
            asg_rec = {"worker_count": fleet["max"]}
            asg_cur = {"worker_count": cur_max}

        dbu_ratio = (fleet["expected_workers"] * cand.dbu_per_hour) / (p50 * current.dbu_per_hour)
        infra_ratio = (fleet["expected_workers"] * cand.price_per_hour) / (p50 * current.price_per_hour)
        dbu_frac = ctx.role_share("worker", "dbu") * (1 - dbu_ratio)
        infra_frac = ctx.role_share("worker", "infra") * (1 - infra_ratio)
        signal = clamp(reduction * 2, 0.0, 1.0)
        return RuleOutcome(
            optimization_type=self.optimization_type,
            current_config={"worker_node_type": current.name, "vcpu": current.vcpu,
                            "memory_gb": current.memory_gb, **asg_cur},
            recommended_config={"worker_node_type": cand.name, "vcpu": cand.vcpu,
                                "memory_gb": cand.memory_gb, **asg_rec},
            rationale=(
                f"Worker P95 CPU {m.worker_cpu_p95:.1f}% / memory {m.worker_mem_p95:.1f}% on "
                f"{current.name}; executors P10/P50/P95 = {p10:g}/{p50:g}/{p95:g}. "
                f"Cheapest fleet meeting P95 + headroom is {cand.name} x "
                f"{fleet['min']}-{fleet['max']} (expected {fleet['expected_workers']:.1f} workers)."
            ),
            evidence={
                "worker_cpu_p95": m.worker_cpu_p95,
                "worker_mem_p95": m.worker_mem_p95,
                "worker_count_p10": p10,
                "worker_count_p50": p50,
                "worker_count_p95": p95,
                "required_vcpu_per_current_node": round(req_vcpu, 2),
                "required_memory_gb_per_current_node": round(req_mem, 2),
                "node_scale_factor": round(fleet["scale"], 4),
                "fleet_cost_reduction_pct": round(reduction * 100, 2),
            },
            dbu_reduction_frac=max(0.0, dbu_frac),
            infra_reduction_frac=max(0.0, infra_frac),
            signal_strength=signal,
            guardrails_applied=applied,
        )
