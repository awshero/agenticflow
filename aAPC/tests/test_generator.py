import json
from datetime import timedelta

import pytest

from apc_optimizer.compute_types import get_adapter
from apc_optimizer.engine.generator import RecommendationGenerator
from apc_optimizer.models import ClusterMetrics, OptimizationType
from conftest import NOW, cost, make_metrics, snap


def wasteful(**overrides):
    """An over-provisioned, Photon-on, idle-heavy APC: every rule but APC->Job fires."""
    base = dict(
        photon_enabled=True,
        driver_cpu_p95=12.0, driver_mem_p95=18.0,
        worker_cpu_p95=22.0, worker_mem_p95=30.0,
        intra_session_idle_gaps=[6, 9, 12, 15, 18, 22, 25, 28, 50, 70],
        terminal_idle_tails=[120] * 20,
    )
    base.update(overrides)
    return make_metrics(**base)


def test_end_to_end_recommendations(cfg, catalog):
    gen = RecommendationGenerator(cfg, catalog)
    res = gen.run([wasteful()], {"c1": [snap(90)]}, {"c1": cost()}, run_id="r1", generated_at=NOW)
    types = {r.optimization_type for r in res.recommendations}
    assert types == {
        OptimizationType.EC2_RIGHTSIZING_DRIVER.value,
        OptimizationType.EC2_RIGHTSIZING_WORKER_ASG.value,
        OptimizationType.PHOTON_OFF.value,
        OptimizationType.AUTO_STOP.value,
    }
    for r in res.recommendations:
        assert r.annual_savings_estimate >= 500
        assert 0 <= r.confidence_score <= 100
        assert r.cost_basis == "NET_COST_LAKE"
        assert r.lifecycle_state == "ACTIVE"
        json.loads(r.current_config), json.loads(r.recommended_config), json.loads(r.evidence)
        assert len(r.recommendation_id) == 32
    (summary,) = res.summaries
    assert summary.recommendation_count == 4
    assert summary.skipped_reason is None
    additive = sum(r.annual_savings_estimate for r in res.recommendations)
    assert 0 < summary.stacked_annual_savings < additive
    assert summary.stacked_annual_savings < summary.annual_cost
    assert set(res.recommendations[0].as_dict()) >= {"recommendation_id", "confidence_band"}
    assert summary.as_dict()["compute_id"] == "c1"


def test_ids_deterministic(cfg, catalog):
    gen = RecommendationGenerator(cfg, catalog)
    a = gen.run([wasteful()], {}, {"c1": cost()}, run_id="r1", generated_at=NOW)
    b = gen.run([wasteful()], {}, {"c1": cost()}, run_id="r1", generated_at=NOW)
    assert [r.recommendation_id for r in a.recommendations] == [r.recommendation_id for r in b.recommendations]


def test_retire_suppresses_auto_stop(cfg, catalog):
    m = wasteful(scheduled_job_runs=90, scheduled_job_days=30, distinct_scheduled_jobs=3,
                 scheduled_job_minutes=3950, active_minutes=4000)
    res = RecommendationGenerator(cfg, catalog).run([m], {}, {"c1": cost()}, run_id="r", generated_at=NOW)
    types = {r.optimization_type for r in res.recommendations}
    assert OptimizationType.APC_TO_JOB_CLUSTER.value in types
    assert OptimizationType.AUTO_STOP.value not in types


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"tags": {"apc_optimizer": "exclude"}}, "OPTED_OUT_BY_TAG"),
        ({"last_active_time": NOW - timedelta(days=30)}, "LIFECYCLE_DORMANT"),
        ({"observed_days": 3}, "INSUFFICIENT_OBSERVATION_DAYS"),
        ({"uptime_minutes": 100}, "INSUFFICIENT_UPTIME_MINUTES"),
    ],
)
def test_cluster_level_guardrails(cfg, catalog, overrides, reason):
    res = RecommendationGenerator(cfg, catalog).run(
        [wasteful(**overrides)], {}, {"c1": cost()}, run_id="r", generated_at=NOW
    )
    assert res.recommendations == []
    assert res.summaries[0].skipped_reason.startswith(reason)
    assert res.summaries[0].annual_cost > 0  # cost still reported for skipped clusters


def test_min_savings_guardrail(cfg, catalog):
    tiny = cost(net=30.0, dbu=15.0, infra=15.0)
    res = RecommendationGenerator(cfg, catalog).run([wasteful()], {}, {"c1": tiny}, run_id="r")
    assert res.recommendations == []
    assert res.summaries[0].stacked_annual_savings == 0


def test_from_row_and_adapter():
    m = ClusterMetrics.from_row({"workspace_id": "w", "cluster_id": "c", "intra_session_idle_gaps": None,
                                 "tags": None, "unknown_column": 1})
    assert m.intra_session_idle_gaps == [] and m.tags == {} and m.compute_id == "c"
    assert get_adapter("APC").metrics_table == "apc_metrics_table"
    with pytest.raises(ValueError):
        get_adapter("SQL_WAREHOUSE")
