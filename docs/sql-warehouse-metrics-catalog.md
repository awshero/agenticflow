# Databricks SQL Warehouse — Full Metric & Signal Catalog

Complete signal inventory for Classic + Serverless SQL Warehouse cost
optimization. Every signal carries a stable ID so it can be traced from
this catalog → extraction SQL → rule engine → recommendation output.

**Companion docs**
- [`sql-warehouse-signals.md`](./sql-warehouse-signals.md) — why each signal matters and how recommendations degrade without it
- [`../notebooks/sql_warehouse_optimizer.ipynb`](../notebooks/sql_warehouse_optimizer.ipynb) — reference implementation

**Legend**
| Mark | Meaning |
|---|---|
| ✅ | Directly selectable from a system table |
| ⚠️ | Derived — computed from ✅ sources, not a column |
| ❌ | Requires an external source (REST API, AWS CUR, `DESCRIBE`) |

> Schemas evolve and some tables are preview/region-gated. Column names in
> `system.query.history` have shifted across releases — resolve them at runtime
> rather than hardcoding. Verify before building.

---

## Coverage summary

| Layer | Prefix | Signals | ✅ | ⚠️ | ❌ |
|---|---|---:|---:|---:|---:|
| Configuration | `C` | 16 | 9 | 2 | 5 |
| Billing & cost | `B` | 13 | 8 | 1 | 4 |
| Lifecycle & capacity | `L` | 16 | 5 | 8 | 3 |
| Query execution | `Q` | 32 | 26 | 0 | 6 |
| Derived decision metrics | `D` | 26 | 0 | 26 | 0 |
| Table / data layout | `T` | 10 | 3 | 0 | 7 |
| Governance | `G` | 10 | 6 | 2 | 2 |
| **Total** | | **123** | **57** | **39** | **27** |

**~78% of signals are obtainable from system tables alone** (✅ + ⚠️). The
27 external signals are concentrated in table layout (`T`) and Classic infra
cost (`B`), and only one of them — `B08` — is blocking.

---

## Layer C · Configuration & Inventory

**Source:** `system.compute.warehouses` (SCD2) unless noted. Take the latest
row per `warehouse_id` where `delete_time IS NULL`.

| ID | Signal | Source | ST | Drives |
|---|---|---|:--:|---|
| C01 | `warehouse_id` | `compute.warehouses` | ✅ | Primary key for all joins |
| C02 | `workspace_id` | `compute.warehouses` | ✅ | Multi-workspace scoping |
| C03 | `warehouse_name` | `compute.warehouses` | ✅ | Reporting, consolidation matching |
| C04 | `warehouse_type` | `compute.warehouses` | ✅ | **Classic↔Serverless decision** |
| C05 | `warehouse_size` | `compute.warehouses` | ✅ | DBU/hr rate; size up/down |
| C06 | `min_clusters` | `compute.warehouses` | ✅ | **Warm-floor 24/7 cost** |
| C07 | `max_clusters` | `compute.warehouses` | ✅ | Concurrency ceiling + cost cap |
| C08 | `auto_stop_minutes` | `compute.warehouses` | ✅ | Idle tax vs cold-start tax |
| C09 | `warehouse_channel` | `compute.warehouses` | ✅ | CURRENT vs PREVIEW |
| C10 | `tags` / custom tags | `compute.warehouses` | ✅ | Chargeback, grouping |
| C11 | Config change history | `compute.warehouses` SCD2 | ⚠️ | Drift detection (see D24) |
| C12 | Owner / creator | `compute.warehouses` or audit | ⚠️ | Accountability; verify column exists |
| C13 | `spot_instance_policy` | **SQL Warehouses API** | ❌ | Classic reliability vs cost |
| C14 | `enable_photon` | **API** | ❌ | Inferable: always on Serverless/Pro |
| C15 | Warehouse ACLs / permissions | **Permissions API** | ❌ | Who can resize; governance |
| C16 | Statement timeout | **Workspace settings API** | ❌ | Runaway-query guardrail |

> If `system.compute.warehouses` is unavailable in your region, poll the SQL
> Warehouses API into your own SCD2 table. **Do not settle for a current-state
> snapshot** — C11 drift detection needs history, and "temporary" resizes that
> were never reverted are a common and invisible leak.

---

## Layer B · Billing & Cost

**Source:** `system.billing.usage` joined to `system.billing.list_prices`.

| ID | Signal | Source | ST | Drives |
|---|---|---|:--:|---|
| B01 | `usage_quantity` (DBUs) | `billing.usage` | ✅ | Consumption baseline |
| B02 | `sku_name` | `billing.usage` | ✅ | Classic vs Serverless SKU split |
| B03 | `billing_origin_product` | `billing.usage` | ✅ | Filter to `SQL` |
| B04 | `usage_start_time` / `end_time` | `billing.usage` | ✅ | Hourly cost time series |
| B05 | `usage_metadata.warehouse_id` | `billing.usage` | ✅ | Join key to C01 |
| B06 | `custom_tags` | `billing.usage` | ✅ | Chargeback |
| B07 | `identity_metadata.run_as` | `billing.usage` | ✅ | Attribution |
| B08 | **EC2 / EBS cost (Classic)** | **AWS CUR** | ❌ | 🔴 **Blocking for Classic** |
| B09 | Data transfer / NAT cost | **AWS CUR** | ❌ | Cross-AZ shuffle cost |
| B10 | `list_prices.pricing.default` | `billing.list_prices` | ✅ | $/DBU by SKU + date range |
| B11 | Negotiated / discounted rate | Contract | ❌ | List price overstates savings |
| B12 | Effective $/DBU by type | derived from B01+B10 | ⚠️ | Cost model input |
| B13 | Budget / spend alerts | `billing.budgets` | ✅ | Verify availability |

> 🔴 **B08 is the single most consequential gap.** System tables give DBUs only;
> for Classic warehouses the EC2/EBS half of the bill lives in AWS CUR. Joining
> requires matching Databricks-propagated resource tags — verify what actually
> lands in your CUR. **A Classic-vs-Serverless comparison built without B08 is
> biased toward Classic by 40–60% and will recommend changes that lose money.**
> Serverless has no equivalent gap.

---

## Layer L · Lifecycle & Capacity

**Source:** `system.compute.warehouse_events`.

| ID | Signal | Source | ST | Drives |
|---|---|---|:--:|---|
| L01 | `event_type` | `warehouse_events` | ✅ | STARTING/RUNNING/STOPPING/STOPPED |
| L02 | `event_type` scale events | `warehouse_events` | ✅ | SCALED_UP / SCALED_DOWN |
| L03 | `cluster_count` at event | `warehouse_events` | ✅ | 🟢 **The billable unit driver** |
| L04 | `event_time` | `warehouse_events` | ✅ | Step-function reconstruction |
| L05 | `warehouse_id` | `warehouse_events` | ✅ | Join key |
| L06 | Uptime intervals | L01+L04 | ⚠️ | Non-STOPPED spans |
| L07 | `uptime_hours` | L06 | ⚠️ | Idle calc denominator |
| L08 | **`cluster_hours`** = ∫ cluster_count dt | L03+L04 | ⚠️ | 🟢 **True cost basis** |
| L09 | `max_cluster_count` observed | L03 | ⚠️ | Peak capacity used |
| L10 | `p50` / `p95` cluster count | L03+L04, duration-weighted | ⚠️ | max_clusters right-sizing |
| L11 | `cold_start_count` | count STARTING | ⚠️ | Cold-start tax |
| L12 | Cold-start duration | STARTING→RUNNING gap | ⚠️ | Startup cost per restart |
| L13 | `scale_event_count` | count L02 | ⚠️ | Thrash detection |
| L14 | Node CPU % | `compute.node_timeline` | ❌ | ⚠️ Unreliable for SQL WH |
| L15 | Node memory % | `compute.node_timeline` | ❌ | ⚠️ Unreliable for SQL WH |
| L16 | Serverless IWM decisions | — | ❌ | Not exposed; black box |

> **L14/L15 caveat.** `node_timeline` reliably covers all-purpose and job
> clusters, but SQL Warehouse compute — especially Serverless — is generally not
> represented. **Do not design a utilization-based sizing model for SQL
> warehouses.** Sizing must be driven by spill (Q14), not CPU/memory. This is the
> key structural difference from job-cluster optimization.

---

## Layer Q · Query Execution

**Source:** `system.query.history`. Grain = one statement.

### Q-a · Identity & attribution

| ID | Signal | ST | Drives |
|---|---|:--:|---|
| Q01 | `statement_id` | ✅ | Grain |
| Q02 | `session_id` | ✅ | Session grouping |
| Q03 | `compute.warehouse_id` | ✅ | Join key (struct field) |
| Q04 | `executed_by` | ✅ | User attribution |
| Q05 | `executed_as` | ✅ | Service principal detection |
| Q06 | `start_time` | ✅ | 🟢 Concurrency sweep-line |
| Q07 | `end_time` | ✅ | 🟢 Concurrency sweep-line |
| Q08 | `execution_status` | ✅ | FAILED/CANCELED still cost money |
| Q09 | `error_message` | ✅ | Failure clustering |

### Q-b · Timing breakdown — the diagnostic core

| ID | Signal | ST | Drives |
|---|---|:--:|---|
| Q10 | `total_duration_ms` | ✅ | Wall clock |
| Q11 | `waiting_for_compute_duration_ms` | ✅ | 🟢 Cold start → Serverless case |
| Q12 | `waiting_at_capacity_duration_ms` | ✅ | 🟢 **Queuing → scale OUT** |
| Q13 | `compilation_duration_ms` | ✅ | Planning / stale stats |
| Q14 | `execution_duration_ms` | ✅ | Duty-cycle numerator |
| Q15 | `result_fetch_duration_ms` | ✅ | Client-side bottleneck |
| Q16 | `total_task_duration_ms` | ✅ | ÷ Q14 ≈ effective parallelism |

### Q-c · Resource pressure

| ID | Signal | ST | Drives |
|---|---|:--:|---|
| Q17 | **`spilled_local_bytes`** | ✅ | 🔴 **Safety metric → scale UP** |
| Q18 | `shuffle_read_bytes` | ✅ | Wide ops, skew |
| Q19 | `read_bytes` | ✅ | Scan volume |
| Q20 | `written_bytes` | ✅ | Write amplification |

### Q-d · Efficiency & caching

| ID | Signal | ST | Drives |
|---|---|:--:|---|
| Q21 | `from_result_cache` | ✅ | Near-zero-cost queries |
| Q22 | `read_io_cache_percent` | ✅ | Disk cache warmth |
| Q23 | `read_files` | ✅ | Small-file symptom |
| Q24 | `pruned_files` | ✅ | Pruning effectiveness |
| Q25 | `read_partitions` | ✅ | Partition pruning |
| Q26 | `read_rows` | ✅ | Selectivity (may be `rows_read_count`) |
| Q27 | `produced_rows` | ✅ | Selectivity (may be `rows_produced_count`) |

### Q-e · Workload character

| ID | Signal | ST | Drives |
|---|---|:--:|---|
| Q28 | `statement_type` | ✅ | ETL-on-warehouse anti-pattern |
| Q29 | `statement_text` | ✅ | MV candidates, LLM analysis |
| Q30 | `client_application` | ✅ | Tableau / Power BI / dbt |
| Q31 | `client_driver` | ✅ | Connection path |
| Q32 | `query_source` | ✅ | dashboard / alert / job |

### Q-f · Not in query history

| Signal | Source | Note |
|---|---|---|
| Physical / logical plan | Query Profile API | Deep dives only |
| Per-operator time | Query Profile API | Does not scale estate-wide |
| Per-stage / task metrics | Query Profile API | — |
| Photon coverage % | Query Profile API | — |
| Join strategy (BHJ/SMJ) | Query Profile API | — |
| Task-level skew | Query Profile API | — |

> The Query Profile gap matters less than it appears. Q17, Q23/Q24 and Q16 cover
> ~80% of tuning decisions. Reserve profile pulls for the top-N costliest queries.

> **Column-name drift.** Q26/Q27 and Q23/Q24 have appeared under both bare and
> `_count`-suffixed names. Resolve at runtime by introspecting the schema.

---

## Layer D · Derived Decision Metrics

All ⚠️. These are the metrics the rule engine actually reads.

| ID | Metric | Formula | Drives |
|---|---|---|---|
| D01 | **`duty_cycle`** | `Σ Q14 / L08` | 🟢 Classic ↔ Serverless |
| D02 | `idle_hours` | `L07 − Σ Q10` | Auto-stop tuning |
| D03 | `idle_ratio` | `D02 / L07` | > 40% → tighten auto-stop |
| D04 | `idle_cost_usd` | `D03 × B01 × B10` | Savings from C08 change |
| D05 | `cold_start_tax_usd` | `L11 × L12 × size_dbu × $/DBU` | Counterweight to D03 |
| D06 | `queue_rate` | `count(Q12 > 0) / count(*)` | > 5% → **scale out** |
| D07 | `p95_queue_ms` | `percentile(Q12, .95)` | SLA impact |
| D08 | `spill_rate` | `count(Q17 > 0) / count(*)` | > 10% → **scale up** |
| D09 | `coldstart_rate` | `count(Q11 > 0) / count(*)` | Serverless case |
| D10 | `cache_hit_rate` | `count(Q21) / count(*)` | Cache-loss risk |
| D11 | `peak_concurrency` | sweep-line max over Q06/Q07 | Absolute ceiling |
| D12 | **`p95_concurrency`** | duration-weighted p95 | 🟢 max_clusters sizing |
| D13 | **`required_clusters`** | `⌈D12 / 10⌉` | Target cluster count |
| D14 | `concurrency_headroom_pct` | `1 − L10.p95 / C07` | > 50% → shrink max |
| D15 | `time_at_max_clusters_pct` | `∫(L03 = C07) / L07` | > 10% → raise max |
| D16 | `time_at_min_clusters_pct` | `∫(L03 = C06) / L07` | ~100% + no queue → lower min |
| D17 | `min_cluster_floor_cost` | `(C06−1) × L07 × size_dbu × $` | Warm-floor waste |
| D18 | `scale_thrash_rate` | `L13 / L07` | > 2/hr → widen bounds |
| D19 | `cost_per_query` | `(B01×B10 + B08) / count(*)` | Cross-warehouse ranking |
| D20 | `cost_per_tb_scanned` | `total_cost / Σ Q19` | Efficiency benchmark |
| D21 | `failed_query_waste_usd` | `count(Q08≠FINISHED)/count(*) × cost` | Typically 5–15% |
| D22 | `prune_ratio` | `Q24 / Q23` | Low → layout problem |
| D23 | `zombie_score` | `count(*) = 0 AND cost > 0` | Delete candidate |
| D24 | `config_drift_events` | consecutive C11 diffs | Unreverted resizes |
| D25 | `write_stmt_rate` | `count(Q28 ∈ writes)/count(*)` | ETL-on-warehouse |
| D26 | `peak_to_trough_ratio` | `p95 hourly qps / p50` | Spiky → Serverless |

### The two-axis rule

A single query **never spans clusters**. Adding clusters cannot make one query
faster. This makes the axes strictly non-overlapping:

| Symptom | Correct axis | Wrong move |
|---|---|---|
| D06 high (queuing) | **Scale OUT** — raise C07 | Size up → 2× cost, queue persists |
| D08 high (spill) | **Scale UP** — raise C05 | Add clusters → cost up, still spills |
| Both high | Size up first, re-measure 7d | Both at once → no attribution |

---

## Layer T · Table & Data Layout

Upstream root causes. Often the cheapest wins — no warehouse config change.

| ID | Signal | Source | ST | Drives |
|---|---|---|:--:|---|
| T01 | Predictive optimization history | `storage.predictive_optimization_operations_history` | ✅ | OPTIMIZE/VACUUM coverage |
| T02 | Table lineage | `access.table_lineage` | ✅ | Which tables drive which WH |
| T03 | Column lineage | `access.column_lineage` | ✅ | Clustering-column candidates |
| T04 | Catalog metadata | `information_schema.*` | ✅ | Table/column inventory |
| T05 | File count / avg file size | `DESCRIBE DETAIL` | ❌ | 🔴 Small-file detection |
| T06 | Table size on disk | `DESCRIBE DETAIL` | ❌ | `sizeInBytes`, `numFiles` |
| T07 | Z-order / liquid clustering cols | `DESCRIBE DETAIL` / DDL | ❌ | Verify vs Q29 predicates |
| T08 | Statistics freshness | `DESCRIBE EXTENDED` | ❌ | Explains high Q13 |
| T09 | Partition cardinality | `SHOW PARTITIONS` | ❌ | Over-partitioning |
| T10 | Deletion vector adoption | `DESCRIBE DETAIL` props | ❌ | Rewrite cost |

> Layer T is the most system-table-poor layer and holds the cheapest wins. Build
> a metadata crawler, but **rank tables by Q19 (`read_bytes`) from query history
> first** — crawl the hot tables, not the whole catalog.

---

## Layer G · Governance & Behavioral

| ID | Signal | Source | ST | Drives |
|---|---|---|:--:|---|
| G01 | Warehouse create/edit/delete events | `access.audit` | ✅ | Who resized what, when |
| G02 | SQL config overrides (`SET`) | `access.audit` | ⚠️ | Unsanctioned tuning |
| G03 | Distinct users per warehouse | `query.history` Q04 | ✅ | 1-user Large WH = misuse |
| G04 | Warehouse count per workspace | `compute.warehouses` | ✅ | Sprawl |
| G05 | Overlapping warehouses | Q03+Q04+T02 | ⚠️ | Consolidation candidates |
| G06 | Job → warehouse usage | `system.lakeflow.*` | ✅ | ETL detection |
| G07 | Off-hours spend % | B04 + calendar | ✅ | Scheduling opportunity |
| G08 | Days since last query | `max(Q06)` | ✅ | Zombie detection (D23) |
| G09 | Dashboard / alert schedules | **API** | ❌ | Explains arrival spikes |
| G10 | BI tool metadata | **BI tool APIs** | ❌ | Extract refresh schedules |

---

## Signal → recommendation matrix

| Recommendation | Required signals | Suppress if missing |
|---|---|---|
| Classic → Serverless | C04, C05, D01, D03, D09, B01, B10, **B08** | B08 → confidence `low` |
| Serverless → Classic | C04, D01, B01, B10, **B08** | **B08 → suppress entirely** |
| Size up | C05, D08, Q17 | Q17 → suppress |
| Size down | C05, D03, **Q17**, D08 | **Q17 → suppress entirely** |
| Raise `max_clusters` | C07, D06, D07, D15, D13 | D12 → suppress |
| Lower `max_clusters` | C07, D12, D13, D14 | D12 → suppress |
| Lower `min_clusters` | C06, D06, D16, D17 | D06 → suppress |
| Tighten `auto_stop` | C08, D03, D04, D05, D10 | D10 → flag cache risk |
| Delete warehouse | D23, G08, B01 | — |
| Consolidate warehouses | G03, G05, T02, D01 | — |
| Move ETL to Job cluster | Q28, D25, Q32, Q30 | — |
| Fix data layout | Q23, Q24, D22, T05, T07 | T05 → advisory only |

The two **suppress entirely** rules are the cases where a missing signal
*inverts* the answer rather than blurring it. A low-confidence label does not
stop someone acting on a recommendation pointed the wrong way.

---

## Minimum viable extraction set

Five system tables cover layers C, B, L, Q and every derived metric in D:

```sql
system.compute.warehouses         -- C01–C12, D24
system.compute.warehouse_events   -- L01–L13, D14–D18
system.billing.usage              -- B01–B07
system.billing.list_prices        -- B10, B12
system.query.history              -- Q01–Q32, D01–D13, D19–D26
```

Plus, **only if the estate contains Classic warehouses**:

```
AWS CUR                           -- B08, B09
```

**A Serverless-only estate needs zero external sources** — the entire model is
pure SQL against system tables.

---

## Modelling notes

1. **Cost basis is `cluster_hours` (L08), not uptime (L07).** Costing a
   4-cluster warehouse on uptime alone understates spend ~4×.

2. **Duration-weight all percentiles.** An unweighted p95 over concurrency
   treats a 50 ms spike the same as a 5-minute plateau and over-provisions.

3. **Size changes are near cost-neutral for throughput-bound work.** Busy
   cluster-hours roughly halve when size doubles, so DBU cost is flat. Idle
   hours scale linearly with size. **Downsizing therefore only saves money on
   idle-dominated warehouses** — on a throughput-bound one it just adds latency.

4. **Do not decompose total savings per lever.** Type, size and cluster changes
   compound multiplicatively; price the whole config as one unit. Summing
   per-lever savings double-counts and fails invoice reconciliation.

5. **Classic and Serverless need different thresholds.** Serverless IWM
   pre-empts queuing, so identical `max_clusters` yields far less Q12. Applying
   Classic thresholds to Serverless under-provisions it.

6. **The config space is ~9,450 points and fully enumerable.** Score every valid
   config and take the cheapest feasible one. No heuristic search or model is
   needed — this is discrete optimization, not inference.
