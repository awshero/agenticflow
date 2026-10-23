"""APC -> Job cluster migration for APCs that mostly serve scheduled jobs."""
from __future__ import annotations

from typing import Optional

from apc_optimizer.models import OptimizationType, RuleOutcome
from apc_optimizer.rules.base import Rule, RuleContext, clamp


class ApcToJobClusterRule(Rule):
    optimization_type = OptimizationType.APC_TO_JOB_CLUSTER
    config_section = "apc_to_job"

    def evaluate(self, ctx: RuleContext) -> Optional[RuleOutcome]:
        m = ctx.metrics
        p = self.params
        min_runs = int(p.get("min_scheduled_runs", 8))
        if m.scheduled_job_runs < min_runs or m.scheduled_job_days < int(p.get("min_scheduled_days", 4)):
            return None
        if m.uptime_minutes <= 0:
            return None
        share = clamp(m.scheduled_job_minutes / max(m.active_minutes, 1), 0.0, 1.0)
        if share < float(p.get("min_scheduled_share", 0.6)):
            return None

        ratio = float(p.get("jobs_dbu_rate", 0.15)) / float(p.get("apc_dbu_rate", 0.55))
        job_frac = clamp(m.scheduled_job_minutes / m.uptime_minutes, 0.0, 1.0)
        guardrails = []
        if share >= 0.9:
            # Purely scheduled: the APC can be retired, idle uptime disappears too.
            dbu_frac = 1 - job_frac * ratio
            infra_frac = 1 - job_frac
            mode = "retire APC; run the jobs on job clusters"
        else:
            # Mixed: move the scheduled share, keep the APC for interactive work.
            dbu_frac = job_frac * (1 - ratio)
            infra_frac = 0.0
            mode = "move scheduled jobs to job clusters; keep APC for interactive use"
            guardrails.append("APC_RETAINED_FOR_INTERACTIVE_USE")

        return RuleOutcome(
            optimization_type=self.optimization_type,
            current_config={"compute": "ALL_PURPOSE", "scheduled_job_ids": m.scheduled_job_ids},
            recommended_config={"compute": "JOB_CLUSTER", "action": mode,
                                "job_cluster_template": {
                                    "node_type_id": m.worker_node_type,
                                    "driver_node_type_id": m.driver_node_type,
                                    "spark_version": m.dbr_version}},
            rationale=(
                f"{m.scheduled_job_runs} scheduled runs of {m.distinct_scheduled_jobs} job(s) on "
                f"{m.scheduled_job_days} days use {share:.0%} of active compute; Jobs Compute "
                f"is billed at {ratio:.0%} of the All-Purpose DBU rate -> {mode}."
            ),
            evidence={
                "scheduled_job_runs": m.scheduled_job_runs,
                "scheduled_job_days": m.scheduled_job_days,
                "distinct_scheduled_jobs": m.distinct_scheduled_jobs,
                "scheduled_job_minutes": m.scheduled_job_minutes,
                "active_minutes": m.active_minutes,
                "scheduled_share_of_active": round(share, 4),
                "jobs_to_apc_dbu_rate_ratio": round(ratio, 4),
            },
            dbu_reduction_frac=clamp(dbu_frac, 0.0, 1.0),
            infra_reduction_frac=clamp(infra_frac, 0.0, 1.0),
            signal_strength=clamp(share * min(1.0, m.scheduled_job_runs / (2 * min_runs)), 0.0, 1.0),
            guardrails_applied=guardrails,
        )
