"""Entry point for the ``generate_recommendations`` task (python_wheel_task).

    apc-recommend --catalog finops --schema apc_optimizer --lob LOB1 \
                  --cost_table finops.cost_lake.databricks_net_cost
"""
from __future__ import annotations

import argparse
import logging
import uuid
from collections import Counter
from datetime import datetime
from typing import List, Optional

from apc_optimizer.catalog import InstanceCatalog
from apc_optimizer.compute_types import get_adapter
from apc_optimizer.config import EngineConfig, load_instance_catalog
from apc_optimizer.engine.generator import RecommendationGenerator

log = logging.getLogger("apc_optimizer")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="APC compute optimization recommendation engine")
    p.add_argument("--catalog", required=True)
    p.add_argument("--schema", required=True)
    p.add_argument("--cost_table", required=True)
    p.add_argument("--lob", default=None)
    p.add_argument("--compute_type", default="APC")
    p.add_argument("--lookback_days", type=int, default=None)
    p.add_argument("--history_days", type=int, default=180)
    p.add_argument("--rules_path", default=None, help="Optional YAML overriding packaged rules.yml")
    p.add_argument("--catalog_path", default=None, help="Optional instance catalog YAML")
    p.add_argument("--run_id", default=None)
    p.add_argument("--dry_run", action="store_true", help="Generate but do not write")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)

    from pyspark.sql import SparkSession  # imported lazily: tests run without Spark

    from apc_optimizer.storage.spark_io import SparkIO

    overrides = {"global": {"lookback_days": args.lookback_days}} if args.lookback_days else None
    cfg = EngineConfig.load(args.rules_path, overrides)
    catalog = InstanceCatalog(load_instance_catalog(args.catalog_path))
    adapter = get_adapter(args.compute_type)
    spark = SparkSession.builder.getOrCreate()
    io = SparkIO(spark, args.catalog, args.schema, adapter, cfg)

    lookback = int(cfg.get("global.lookback_days", 30))
    metrics = io.read_metrics(args.lob)
    history = io.read_history(args.history_days)
    costs = io.read_costs(args.cost_table, lookback)
    log.info("loaded %d computes, %d histories, %d cost records", len(metrics), len(history), len(costs))

    run_id = args.run_id or f"{datetime.utcnow():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
    result = RecommendationGenerator(cfg, catalog).run(metrics, history, costs, run_id)

    by_type = Counter(r.optimization_type for r in result.recommendations)
    total = sum(s.stacked_annual_savings for s in result.summaries)
    log.info("run %s: %d recommendations %s, stacked annual savings $%.0f",
             run_id, len(result.recommendations), dict(by_type), total)

    if args.dry_run:
        return
    io.write_recommendations(r.as_dict() for r in result.recommendations)
    io.write_cost_summaries(s.as_dict() for s in result.summaries)


if __name__ == "__main__":
    main()
