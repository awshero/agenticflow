import pytest

from apc_optimizer.models import OptimizationType
from apc_optimizer.rules import build_rules
from apc_optimizer.rules.apc_to_job import ApcToJobClusterRule
from apc_optimizer.rules.auto_stop import AutoStopRule, restart_rate
from apc_optimizer.rules.photon import PhotonOffRule
from apc_optimizer.rules.rightsizing import DriverRightsizingRule, WorkerRightsizingAsgRule
from conftest import make_ctx, make_metrics


# --------------------------------------------------------------- driver --
def test_driver_downsized_with_headroom(cfg, catalog):
    m = make_metrics(driver_cpu_p95=15.0, driver_mem_p95=20.0)
    out = DriverRightsizingRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    assert out is not None
    rec = catalog.get(out.recommended_config["driver_node_type"])
    # 16 vCPU * 15% * 1.1 = 2.64 -> 4 vCPU floor (25% downsize ratio)
    # 128GB * 20% * 1.1 = 28.2GB -> 32GB floor (25% downsize ratio)
    assert rec.vcpu >= 4 and rec.memory_gb >= 32
    assert out.evidence["required_memory_gb"] == pytest.approx(32)
    assert any("MIN_VCPU_FLOOR" in g for g in out.guardrails_applied)
    assert any("MIN_MEMORY_FLOOR" in g for g in out.guardrails_applied)
    assert 0 < out.infra_reduction_frac < 1 and 0 < out.dbu_reduction_frac < 1


def test_driver_busy_not_downsized(cfg, catalog):
    m = make_metrics(driver_cpu_p95=85.0, driver_mem_p95=85.0)
    assert DriverRightsizingRule(cfg).evaluate(make_ctx(cfg, catalog, m)) is None


def test_driver_unknown_type_or_gpu_skipped(cfg, catalog):
    assert DriverRightsizingRule(cfg).evaluate(
        make_ctx(cfg, catalog, make_metrics(driver_node_type="x9.huge", driver_cpu_p95=5.0))
    ) is None
    assert DriverRightsizingRule(cfg).evaluate(
        make_ctx(cfg, catalog, make_metrics(driver_gpu_count=1, driver_cpu_p95=5.0, driver_mem_p95=5.0))
    ) is None


def test_driver_max_downsize_ratio(cfg, catalog):
    m = make_metrics(driver_node_type="r5.16xlarge", driver_cpu_p95=1.0, driver_mem_p95=1.0)
    out = DriverRightsizingRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    rec = catalog.get(out.recommended_config["driver_node_type"])
    assert rec.vcpu >= 16 and rec.memory_gb >= 128  # 25% of 64 vCPU / 512 GB


# --------------------------------------------------------- worker + ASG --
def test_worker_fleet_shrinks_and_asg_resized(cfg, catalog):
    m = make_metrics(worker_cpu_p95=25.0, worker_mem_p95=30.0)
    out = WorkerRightsizingAsgRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    assert out is not None
    rc = out.recommended_config
    assert rc["min_autoscale_workers"] >= 1
    assert rc["min_autoscale_workers"] <= rc["max_autoscale_workers"]
    new = catalog.get(rc["worker_node_type"])
    # capacity at P95 must still be covered: max workers * new node >= p95 * requirement
    req_vcpu = 16 * 0.25 * 1.1
    req_mem = 64 * 0.30 * 1.1
    assert rc["max_autoscale_workers"] * new.vcpu >= 8 * req_vcpu
    assert rc["max_autoscale_workers"] * new.memory_gb >= 8 * req_mem
    assert out.evidence["fleet_cost_reduction_pct"] >= 5
    assert out.current_config["max_autoscale_workers"] == 10


def test_worker_fixed_size_cluster(cfg, catalog):
    m = make_metrics(min_autoscale_workers=None, max_autoscale_workers=None, worker_count=8,
                     worker_count_p10=8, worker_count_p50=8, worker_count_p95=8,
                     worker_cpu_p95=20.0, worker_mem_p95=25.0)
    out = WorkerRightsizingAsgRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    assert out is not None
    assert "worker_count" in out.recommended_config
    assert out.recommended_config["worker_count"] < 8 or \
        catalog.get(out.recommended_config["worker_node_type"]).vcpu < 16


def test_worker_rules_skip(cfg, catalog):
    rule = WorkerRightsizingAsgRule(cfg)
    single = make_metrics(min_autoscale_workers=None, max_autoscale_workers=None, worker_count=0)
    assert rule.evaluate(make_ctx(cfg, catalog, single)) is None
    busy = make_metrics(worker_cpu_p95=90.0, worker_mem_p95=90.0)
    assert rule.evaluate(make_ctx(cfg, catalog, busy)) is None
    no_data = make_metrics(worker_cpu_p95=None)
    assert rule.evaluate(make_ctx(cfg, catalog, no_data)) is None
    gpu = make_metrics(worker_gpu_count=4, worker_cpu_p95=5.0, worker_mem_p95=5.0)
    assert rule.evaluate(make_ctx(cfg, catalog, gpu)) is None


# --------------------------------------------------------------- photon --
@pytest.mark.parametrize("photon,cpu,fires", [(True, 20.0, True), (True, 30.0, False), (False, 5.0, False)])
def test_photon_off(cfg, catalog, photon, cpu, fires):
    m = make_metrics(photon_enabled=photon, worker_cpu_p95=cpu)
    out = PhotonOffRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    assert (out is not None) is fires
    if fires:
        assert out.dbu_reduction_frac == pytest.approx(0.5)
        assert out.infra_reduction_frac == 0
        assert out.signal_strength == pytest.approx(10 / 30)


def test_photon_single_node_uses_driver_cpu(cfg, catalog):
    m = make_metrics(photon_enabled=True, min_autoscale_workers=None, max_autoscale_workers=None,
                     worker_count=0, worker_cpu_p95=None, driver_cpu_p95=12.0)
    out = PhotonOffRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    assert out.evidence["cpu_p95"] == 12.0


# ------------------------------------------------------------ auto stop --
def test_auto_stop_reduced(cfg, catalog):
    gaps = [6, 8, 10, 12, 14, 18, 20, 25, 40, 90]
    tails = [120] * 15
    m = make_metrics(intra_session_idle_gaps=gaps, terminal_idle_tails=tails)
    out = AutoStopRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    assert out is not None
    target = out.recommended_config["auto_termination_minutes"]
    assert target == 30  # smallest candidate with <=20% of gaps longer than it
    assert restart_rate(gaps, target) <= 0.2
    saved = (40 - 30 - 5) + (90 - 30 - 5) + 15 * (120 - 30)
    assert out.evidence["saved_idle_minutes"] == saved
    assert out.dbu_reduction_frac == pytest.approx(saved / 6000)


def test_auto_stop_already_tight(cfg, catalog):
    m = make_metrics(auto_termination_minutes=10, terminal_idle_tails=[10, 10])
    assert AutoStopRule(cfg).evaluate(make_ctx(cfg, catalog, m)) is None


def test_auto_stop_disabled_cluster(cfg, catalog):
    m = make_metrics(auto_termination_minutes=0, terminal_idle_tails=[300, 400])
    out = AutoStopRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    assert out.recommended_config["auto_termination_minutes"] == 10
    assert "AUTO_STOP_WAS_DISABLED" in out.guardrails_applied


def test_auto_stop_long_gaps_use_max(cfg, catalog):
    rule = AutoStopRule(cfg)
    assert rule.choose([500] * 10) == 120
    assert AutoStopRule(cfg).evaluate(make_ctx(cfg, catalog, make_metrics(uptime_minutes=0))) is None


# ----------------------------------------------------------- APC -> Job --
def test_apc_to_job_retire(cfg, catalog):
    m = make_metrics(scheduled_job_runs=60, scheduled_job_days=30, distinct_scheduled_jobs=2,
                     scheduled_job_minutes=3900, active_minutes=4000, scheduled_job_ids=["11", "12"])
    out = ApcToJobClusterRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    assert out is not None
    job_frac = 3900 / 6000
    assert out.dbu_reduction_frac == pytest.approx(1 - job_frac * 0.15 / 0.55)
    assert out.infra_reduction_frac == pytest.approx(1 - job_frac)
    assert "APC_RETAINED_FOR_INTERACTIVE_USE" not in out.guardrails_applied


def test_apc_to_job_mixed(cfg, catalog):
    m = make_metrics(scheduled_job_runs=20, scheduled_job_days=10, scheduled_job_minutes=2800,
                     active_minutes=4000)
    out = ApcToJobClusterRule(cfg).evaluate(make_ctx(cfg, catalog, m))
    assert out.infra_reduction_frac == 0
    assert "APC_RETAINED_FOR_INTERACTIVE_USE" in out.guardrails_applied


@pytest.mark.parametrize("runs,days,minutes", [(3, 10, 3000), (20, 2, 3000), (20, 10, 1000)])
def test_apc_to_job_thresholds(cfg, catalog, runs, days, minutes):
    m = make_metrics(scheduled_job_runs=runs, scheduled_job_days=days, scheduled_job_minutes=minutes)
    assert ApcToJobClusterRule(cfg).evaluate(make_ctx(cfg, catalog, m)) is None


# ------------------------------------------------------------- registry --
def test_registry_respects_enabled_and_compute_type(cfg):
    assert {r.optimization_type for r in build_rules(cfg, "APC")} == set(OptimizationType)
    assert build_rules(cfg, "JOB_CLUSTER") == []
    cfg.rules["photon"]["enabled"] = False
    assert OptimizationType.PHOTON_OFF not in {r.optimization_type for r in build_rules(cfg, "APC")}


def test_role_share(cfg, catalog):
    ctx = make_ctx(cfg, catalog, make_metrics())
    assert ctx.role_share("driver", "infra") + ctx.role_share("worker", "infra") == pytest.approx(1)
    empty = make_ctx(cfg, catalog, make_metrics(driver_node_minutes=0, worker_node_minutes=0))
    assert empty.role_share("driver", "dbu") == 1.0
    assert empty.role_share("worker", "dbu") == 0.0
