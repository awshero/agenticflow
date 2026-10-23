from datetime import timedelta

import pytest

from apc_optimizer.config import EngineConfig
from apc_optimizer.cost.annual_cost import AnnualCostGenerator
from apc_optimizer.cost.savings import SavingsEstimator
from apc_optimizer.lifecycle.lifecycle_apc import LifecycleAPC, build_spans
from apc_optimizer.models import CostBasis, CostRecord, LifecycleState, OptimizationType, RuleOutcome
from apc_optimizer.scoring.confidence import ConfidenceScorer
from conftest import NOW, cost, make_metrics, snap


# ------------------------------------------------------------- lifecycle --
def test_spans_collapse_identical_configs():
    hist = [snap(50), snap(45), snap(30, driver_node_type="r5.8xlarge"), snap(20)]
    spans = build_spans(hist, NOW)
    assert len(spans) == 3
    assert spans[0].fingerprint == spans[2].fingerprint
    assert spans[0].days == pytest.approx(20)


def test_repeating_config_is_active(cfg):
    hist = [snap(60), snap(40, driver_node_type="r5.8xlarge"), snap(35)]
    a = LifecycleAPC(cfg).assess(make_metrics(), hist)
    assert a.state is LifecycleState.ACTIVE
    assert a.current_config_is_repeating
    assert len(a.repeating_configs) == 1
    assert a.distinct_config_count == 2
    assert a.stability == pytest.approx(1.0 - 0.03 * 0)  # changes before window don't count


def test_churning_new_config_is_experimental(cfg):
    hist = [snap(9.5 - i, worker_count=i) for i in range(10)]  # 9 changes, newest 0.5d old
    a = LifecycleAPC(cfg).assess(make_metrics(), hist)
    assert a.state is LifecycleState.EXPERIMENTAL
    assert a.config_change_count == 9
    assert a.stability == 0.3


def test_dormant_and_deleted(cfg):
    lc = LifecycleAPC(cfg)
    dormant = make_metrics(last_active_time=NOW - timedelta(days=20))
    assert lc.assess(dormant, [snap(100)]).state is LifecycleState.DORMANT
    assert lc.assess(make_metrics(uptime_minutes=0), []).state is LifecycleState.DORMANT
    deleted = make_metrics(delete_time=NOW - timedelta(days=2))
    assert lc.assess(deleted, []).state is LifecycleState.DELETED


def test_no_history_uses_last_change_time(cfg):
    a = LifecycleAPC(cfg).assess(make_metrics(last_config_change_time=NOW - timedelta(days=3)), [])
    assert a.state is LifecycleState.ACTIVE
    assert a.current_config_age_days == pytest.approx(3)
    assert a.stability == 0.6
    b = LifecycleAPC(cfg).assess(make_metrics(last_config_change_time=None), [])
    assert b.stability == 0.8
    c = LifecycleAPC(cfg).assess(make_metrics(), [snap(10)])
    assert c.stability == 0.85


# ------------------------------------------------------------ annual cost --
def test_annualize_with_lake_split(cfg, catalog):
    a = AnnualCostGenerator(cfg, catalog).annualize(make_metrics(), cost())
    assert a.basis is CostBasis.NET_COST_LAKE
    assert a.annual_cost == pytest.approx(30_000 * 365 / 30)
    assert a.annual_dbu_cost == pytest.approx(15_000 * 365 / 30)


def test_annualize_default_split_and_young_cluster(cfg, catalog):
    m = make_metrics(create_time=NOW - timedelta(days=10))
    a = AnnualCostGenerator(cfg, catalog).annualize(m, CostRecord("c1", net_cost=1000.0))
    assert a.basis is CostBasis.NET_COST_LAKE_DEFAULT_SPLIT
    assert a.observed_days == 10
    assert a.annual_cost == pytest.approx(1000 * 36.5)
    assert a.annual_dbu_cost == pytest.approx(a.annual_infra_cost)


def test_annualize_list_price_fallback(cfg, catalog):
    m = make_metrics(photon_enabled=True)
    a = AnnualCostGenerator(cfg, catalog).annualize(m, None)
    assert a.basis is CostBasis.LIST_PRICE_ESTIMATE
    driver_infra = 6000 / 60 * 1.008
    worker_infra = 30000 / 60 * 0.768
    assert a.observed_cost > driver_infra + worker_infra
    assert a.annual_infra_cost == pytest.approx((driver_infra + worker_infra) * 365 / 30, rel=1e-3)


# ---------------------------------------------------------------- savings --
def _outcome(dbu, infra, signal=0.5):
    return RuleOutcome(OptimizationType.PHOTON_OFF, {}, {}, "", {}, dbu, infra, signal)


def test_savings_and_stacking(cfg, catalog):
    annual = AnnualCostGenerator(cfg, catalog).annualize(make_metrics(), cost(net=2000, dbu=1000, infra=1000))
    a, b = _outcome(0.5, 0.0), _outcome(0.2, 0.2)
    assert SavingsEstimator.estimate(annual, a) == pytest.approx(annual.annual_dbu_cost * 0.5, abs=0.01)
    stacked = SavingsEstimator.stacked(annual, [a, b])
    additive = SavingsEstimator.estimate(annual, a) + SavingsEstimator.estimate(annual, b)
    assert stacked < additive
    assert stacked == pytest.approx(annual.annual_dbu_cost * 0.6 + annual.annual_infra_cost * 0.2, abs=0.01)


# ------------------------------------------------------------- confidence --
def test_confidence_bands(cfg, catalog):
    gen, scorer = AnnualCostGenerator(cfg, catalog), ConfidenceScorer(cfg)
    m = make_metrics(observed_days=30, uptime_minutes=5000)
    lc = LifecycleAPC(cfg).assess(m, [snap(60)])
    high = scorer.score(m, lc, gen.annualize(m, cost()), _outcome(0.1, 0.1, signal=1.0))
    assert high.score == 100.0 and high.band == "HIGH"

    weak = make_metrics(observed_days=7, uptime_minutes=600)
    lc2 = LifecycleAPC(cfg).assess(weak, [snap(2)])
    low = scorer.score(weak, lc2, gen.annualize(weak, None), _outcome(0.1, 0.1, signal=0.05))
    assert low.band == "LOW"
    assert set(low.factors) == {"coverage", "sample", "stability", "signal", "cost"}

    mid = scorer.score(m, lc, gen.annualize(m, cost()), _outcome(0.1, 0.1, signal=0.1))
    assert mid.band in {"HIGH", "MEDIUM"} and mid.score < high.score


def test_config_overrides(tmp_path):
    p = tmp_path / "r.yml"
    p.write_text("photon:\n  cpu_p95_threshold: 40\n")
    cfg = EngineConfig.load(str(p), {"global": {"lookback_days": 14}})
    assert cfg.get("photon.cpu_p95_threshold") == 40
    assert cfg.get("photon.dbu_multiplier") == 2.0
    assert cfg.get("global.lookback_days") == 14
    assert cfg.get("nope.missing", "d") == "d"
    assert cfg.rule_version == "1.0.0"
