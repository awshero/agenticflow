from datetime import date, datetime, timedelta

import pytest

from apc_optimizer.catalog import InstanceCatalog
from apc_optimizer.config import EngineConfig, load_instance_catalog
from apc_optimizer.lifecycle.lifecycle_apc import LifecycleAPC
from apc_optimizer.models import ClusterMetrics, ConfigSnapshot, CostRecord
from apc_optimizer.rules.base import RuleContext

SNAPSHOT = date(2026, 10, 1)
NOW = datetime(2026, 10, 1)


@pytest.fixture
def cfg():
    return EngineConfig.load()


@pytest.fixture
def catalog():
    return InstanceCatalog(load_instance_catalog())


def make_metrics(**overrides) -> ClusterMetrics:
    base = dict(
        workspace_id="ws1",
        cluster_id="c1",
        cluster_name="ds-team-apc",
        owned_by="ds@example.com",
        lob="LOB1",
        snapshot_date=SNAPSHOT,
        create_time=NOW - timedelta(days=200),
        last_config_change_time=NOW - timedelta(days=40),
        driver_node_type="r5.4xlarge",
        worker_node_type="m5.4xlarge",
        driver_vcpu=16,
        driver_memory_gb=128,
        worker_vcpu=16,
        worker_memory_gb=64,
        min_autoscale_workers=2,
        max_autoscale_workers=10,
        auto_termination_minutes=120,
        photon_enabled=False,
        lookback_days=30,
        observed_days=25,
        telemetry_minutes=50_000,
        last_active_time=NOW - timedelta(days=1),
        driver_cpu_p95=60.0,
        driver_mem_p95=70.0,
        worker_cpu_p95=70.0,
        worker_mem_p95=70.0,
        worker_count_p10=2,
        worker_count_p50=5,
        worker_count_p95=8,
        worker_count_max=10,
        driver_node_minutes=6000,
        worker_node_minutes=30000,
        uptime_minutes=6000,
        active_minutes=4000,
        idle_minutes=2000,
        session_count=20,
        intra_session_idle_gaps=[],
        terminal_idle_tails=[],
    )
    base.update(overrides)
    return ClusterMetrics(**base)


def make_ctx(cfg, catalog, metrics, history=()):
    lifecycle = LifecycleAPC(cfg).assess(metrics, list(history))
    return RuleContext(metrics=metrics, lifecycle=lifecycle, catalog=catalog, config=cfg)


def snap(days_ago: float, **cfg_overrides) -> ConfigSnapshot:
    base = dict(
        cluster_id="c1",
        change_time=NOW - timedelta(days=days_ago),
        driver_node_type="r5.4xlarge",
        worker_node_type="m5.4xlarge",
        min_autoscale_workers=2,
        max_autoscale_workers=10,
        auto_termination_minutes=120,
        dbr_version="15.4.x-scala2.12",
    )
    base.update(cfg_overrides)
    return ConfigSnapshot(**base)


def cost(net=30_000.0, dbu=15_000.0, infra=15_000.0) -> CostRecord:
    return CostRecord(compute_id="c1", net_cost=net, dbu_cost=dbu, infra_cost=infra, cost_days=30)
