# Databricks SQL Warehouse Optimization — Required Signals

**Purpose:** Define the minimum signal set for Classic + Serverless SQL Warehouse
cost optimization, and state precisely how the recommendation degrades when each
signal is missing.

**Legend:** ✅ system table · ⚠️ derived · ❌ external source required

---

## Tier 0 — Configuration (blocking: no recommendation is possible without these)

| # | Signal | Source | ST? | Without it, the recommendation becomes… |
|---|---|---|---|---|
| 1 | `warehouse_type` (CLASSIC/PRO/SERVERLESS) | `system.compute.warehouses` | ✅ | **Dead.** The Classic↔Serverless migration is the single highest-value recommendation. Without the current type you cannot even state a direction, and you may "recommend" a warehouse migrate to what it already is. |
| 2 | `warehouse_size` | `system.compute.warehouses` | ✅ | **No cost baseline.** Size determines DBU/hr. Without it you cannot price the current state, so no savings figure exists — only vague advice. |
| 3 | `min_clusters` / `max_clusters` | `system.compute.warehouses` | ✅ | **Blind to the #1 silent waste.** `min_clusters > 1` bills 24/7 regardless of query volume. You will miss it entirely and report a warehouse as "already optimal" while it burns a permanent floor cost. |
| 4 | `auto_stop_minutes` | `system.compute.warehouses` | ✅ | **Cannot quantify idle.** Idle is typically 30–60% of Classic spend. You would see high cost with low query volume and have no lever to explain or fix it. |

---

## Tier 1 — Cost (blocking: recommendations exist but are unactionable)

| # | Signal | Source | ST? | Without it, the recommendation becomes… |
|---|---|---|---|---|
| 5 | DBUs consumed (hourly) | `system.billing.usage` | ✅ | **Unranked.** You can identify *what* is misconfigured but not *which* misconfiguration matters. Every finding looks equally urgent; engineers fix the cheap ones first. |
| 6 | `$/DBU` | `system.billing.list_prices` | ✅ | **Unapprovable.** Savings expressed in DBUs do not clear a finance review. "Save 35,000 DBUs" gets ignored; "save $8,200/mo" gets funded. |
| 7 | **EC2 / EBS cost (Classic only)** | **AWS CUR** | ❌ | **Actively harmful — worse than no recommendation.** DBUs are only ~40–60% of true Classic cost. Classic appears far cheaper than it is, so the tool systematically recommends *staying* on Classic when Serverless would be cheaper. This loses money while claiming to save it. Serverless-only estates have no such gap. |

---

## Tier 2 — Capacity & Lifecycle (recommendations become imprecise)

| # | Signal | Source | ST? | Without it, the recommendation becomes… |
|---|---|---|---|---|
| 8 | `cluster_count` time series | `system.compute.warehouse_events` | ✅ | **Wrong by a multiplier.** Cost scales with *cluster-hours*, not uptime. Costing a 4-cluster warehouse as if it ran one cluster understates spend ~4×, and you cannot tune `max_clusters` at all. |
| 9 | Uptime intervals (RUNNING→STOPPED) | `warehouse_events` | ⚠️ | **No duty cycle.** Duty cycle is the deciding input for Classic vs Serverless. Without it that recommendation collapses to guesswork. |
| 10 | Cold-start count / duration | `warehouse_events` | ⚠️ | **One-sided auto-stop advice.** You will recommend aggressive auto-stop without seeing the startup cost it creates — on Classic each restart bills 2–5 min of idle compute *and* drops the disk cache. Net effect can be a cost increase. |

---

## Tier 3 — Query Signals (recommendations become unsafe)

All from `system.query.history`.

| # | Signal | ST? | Without it, the recommendation becomes… |
|---|---|---|---|
| 11 | `spilled_local_bytes` | ✅ | **Dangerous. This is the safety metric.** Spill is the only reliable memory-pressure signal for SQL WH (node CPU/mem is not exposed). Without it, a warehouse that looks idle by duty cycle gets downsized into constant spill — queries slow sharply, and cost can rise as runtimes stretch. **Never ship a downsize recommendation without this.** |
| 12 | `waiting_at_capacity_duration_ms` | ✅ | **Wrong-axis fix.** Queuing and slowness look identical without it, so the tool sizes up (2× DBU/hr) when it should add clusters. Cost doubles, queue persists, trust in the tool is gone after the first such recommendation. |
| 13 | `execution_duration_ms` | ✅ | **No duty cycle numerator.** Same collapse as #9 — the Classic/Serverless decision loses its primary input. |
| 14 | `start_time` / `end_time` | ✅ | **Cannot size `max_clusters`.** True concurrency comes from interval overlap across queries. Without it, cluster-count advice is unfounded and you either throttle real workloads or leave an unbounded cost ceiling. |
| 15 | `waiting_for_compute_duration_ms` | ✅ | **Misses the strongest Serverless case.** Cold-start pain is the clearest migration trigger. Without it, spiky interactive warehouses stay on Classic paying startup tax indefinitely. |
| 16 | `from_result_cache`, `read_io_cache_percent` | ✅ | **Cache-destroying advice.** Cache-dependent BI warehouses get aggressive auto-stop or a Serverless move that discards warm disk cache. Latency regresses, users escalate, and the recommendation gets reverted. |
| 17 | `execution_status` | ✅ | **Inflated legitimate load.** FAILED/CANCELED queries consume DBUs and appear as real demand — typically 5–15%. You size for waste and recommend *more* capacity than needed. |
| 18 | `statement_type`, `query_source`, `client_application` | ✅ | **Wrong problem solved.** Cannot detect ETL/MERGE running on a SQL Warehouse. You tune the warehouse when the correct recommendation is "move this to a Job cluster." |
| 19 | `read_files` / `pruned_files`, `read_bytes` | ✅ | **Compute fix for a data problem.** Poor file layout looks like insufficient compute. You recommend a size increase where OPTIMIZE or liquid clustering would have cut cost with zero config change. |

---

## Tier 4 — Data Layout (misses the cheapest wins)

| # | Signal | Source | ST? | Without it, the recommendation becomes… |
|---|---|---|---|---|
| 20 | File count / avg file size | `DESCRIBE DETAIL` | ❌ | **Compute-only.** Every recommendation is "change the warehouse." The free wins — compaction, clustering on real predicate columns — never surface. Ceiling on achievable savings drops noticeably. |
| 21 | Clustering / Z-order columns | `DESCRIBE DETAIL` | ❌ | Cannot verify layout matches actual filter predicates. Pruning findings from #19 have no prescribed fix. |
| 22 | Statistics freshness | `DESCRIBE EXTENDED` | ❌ | High `compilation_duration_ms` has no explanation; planning-bound queries get misattributed to compute. |

---

## Confidence model

Bind reported confidence to the signals actually present:

| Confidence | Requires |
|---|---|
| **high** | Tiers 0–3 complete, ≥ 21 days of history, ≥ 100 queries, spill data present |
| **medium** | Tiers 0–2 complete, Tier 3 partial |
| **low** | Tier 0–1 only, < 7 days history, or < 20 queries |
| **suppress** | Missing #11 (spill) on any *downsize* recommendation, or missing #7 (CUR) on any *Classic→stay-Classic* recommendation |

The two suppression rules matter most: those are the cases where a missing signal
does not merely weaken the recommendation, it inverts it.

---

## Minimum viable signal set

Five system tables cover Tiers 0–3 and every derived metric:

```
system.compute.warehouses         -- config + SCD2 drift        (#1–4)
system.billing.usage              -- DBU consumption            (#5)
system.billing.list_prices        -- $/DBU                      (#6)
system.compute.warehouse_events   -- cluster_count + uptime     (#8–10)
system.query.history              -- all query signals          (#11–19)
```

Plus, **only if the estate contains Classic warehouses**:

```
AWS CUR                           -- EC2/EBS cost               (#7)
```

**Serverless-only estates need zero external sources** — the entire model is pure SQL.

---

## Not available anywhere in system tables

Design around these; do not block on them.

| Missing | Consequence | Mitigation |
|---|---|---|
| Node CPU / memory % for SQL WH | No utilization-based sizing | Use `spilled_local_bytes` (#11) as the sizing signal instead |
| Query profile (operators, stages, joins, Photon %) | No deep per-query tuning | Pull profiles on top-N costly queries only; does not scale estate-wide |
| Serverless IWM scaling decisions | Cannot explain Serverless scaling behaviour | Treat as a black box; tune bounds only |
| Negotiated DBU rate | Savings are list-price estimates | Overlay contract rate as a config parameter |
| BI tool refresh schedules | Spiky arrival patterns unexplained | Infer from `query_source` + `client_application` (#18) |

---

## Key modelling notes

1. **Cost driver is `cluster_hours`, not uptime.** `∫ cluster_count dt` from
   `warehouse_events`. Using uptime alone misprices every multi-cluster warehouse.

2. **Two independent axes.** Queuing (#12) → scale **out**. Spill (#11) → scale
   **up**. Never conflate; a single query never spans clusters, so adding
   clusters cannot make one query faster.

3. **Attribute savings separately** across type change, size change, and cluster
   change. They compound multiplicatively — summing them double-counts and
   overstates the total, which fails the first reconciliation against the invoice.

4. **Classic and Serverless need different thresholds.** Serverless IWM
   pre-empts queuing, so the same `max_clusters` yields far less
   `waiting_at_capacity`. Applying Classic thresholds to Serverless
   under-provisions it.
