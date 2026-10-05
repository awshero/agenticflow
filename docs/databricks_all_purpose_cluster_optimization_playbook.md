# Databricks All-Purpose Compute (APC) Cost Optimization Playbook

**Scope:** Classic all-purpose clusters (interactive / "APC") across all workspaces
**Baseline:** ~$40M annual spend on all-purpose compute
**Audience:** Platform engineering, FinOps, Data/ML platform leads, workspace admins
**Data source:** Databricks system tables (`system.billing`, `system.compute`, `system.lakeflow`, `system.access`, `system.query`)
**Status of facts:** Schemas and behaviors reflect Databricks documentation as of September–October 2026. Several compute tables are Public Preview, so re-check column names before productionizing any query.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [How All-Purpose Compute Works (Internals)](#2-how-all-purpose-compute-works-internals)
3. [The APC Cost Model](#3-the-apc-cost-model)
4. [Use-Case Pattern Catalog (17 patterns)](#4-use-case-pattern-catalog)
5. [Optimization Lever Catalog (55+ levers)](#5-optimization-lever-catalog)
6. [System Tables Deep Reference](#6-system-tables-deep-reference)
7. [Metrics & KPI Catalog (what to measure, from where, thresholds)](#7-metrics--kpi-catalog)
8. [SQL Query Library](#8-sql-query-library)
9. [Savings Model for the $40M Baseline](#9-savings-model-for-the-40m-baseline)
10. [Governance: Policies, Tags, Chargeback](#10-governance-policies-tags-chargeback)
11. [Automation: Detection → Action Loop](#11-automation-detection--action-loop)
12. [AI/ML & Data Science Specific Playbook](#12-aiml--data-science-specific-playbook)
13. [Implementation Roadmap (30/60/90/180 days)](#13-implementation-roadmap)
14. [Known Limitations & Gotchas](#14-known-limitations--gotchas)
15. [Appendix: Policy JSON templates, Dashboard spec](#15-appendix)

---

## 1. Executive Summary

All-purpose compute is the most expensive way to run classic Spark on Databricks per unit of work. It exists for **interactive** use (notebooks, exploration, debugging, model development), but in most large organizations it accumulates four classes of waste:

| Waste class | What it looks like | Typical root cause |
|---|---|---|
| **Wrong SKU** | Scheduled pipelines, ADF/Airflow-triggered notebooks, and ML training running on APC | "It worked in dev, so we pointed the job at the same cluster" |
| **Idle burn** | Clusters RUNNING with near-zero CPU for hours; long or disabled auto-termination | Users avoid startup wait; autotermination 0/120/240+ min |
| **Over-provisioning** | Large workers, high min-autoscale, driver-heavy pandas code on 20-node clusters | Copy-paste configs, no right-sizing feedback |
| **Wrong price for the capacity** | 100% on-demand, old instance generations, Photon on non-Photon-friendly code | No policy defaults; no spot/fleet strategy |

**The core strategy has five pillars:**

1. **Move non-interactive work off APC** (Jobs compute, serverless jobs, SQL warehouses, Lakeflow pipelines, AI Runtime for GPU).
2. **Kill idle time** (policy-enforced auto-termination, idle detection automation, serverless notebooks for bursty users).
3. **Right-size what remains** (node family, worker counts, autoscaling bounds, single-node for driver-bound work).
4. **Buy capacity cheaper** (spot/fleet for workers, newer instance generations, reserved capacity for baseline, Photon only where ROI-positive).
5. **Govern & make cost visible** (compute policies, mandatory tags, chargeback/showback dashboards, budget alerts).

**Realistic outcome:** For an APC estate of this size, a sustained 20–35% reduction is a conservative, defensible target; 40%+ is achievable where a large share of APC turns out to be scheduled/orchestrated work. Section 9 shows how to size this with your own data rather than benchmarks.

---

## 2. How All-Purpose Compute Works (Internals)

### 2.1 Architecture

- **Control plane** (Databricks-managed): workspace UI, cluster manager, notebook service, job scheduler, REPL management.
- **Classic compute plane** (your cloud account/subscription): the VMs for the driver and workers run in *your* VPC/VNet. You pay the **cloud provider** for VMs/disks/networking **and** pay **Databricks** DBUs.
- **Serverless compute plane** (Databricks account): serverless notebooks/jobs/SQL — VM cost is bundled into the DBU price.

### 2.2 Anatomy of an all-purpose cluster

| Component | Role | Cost implication |
|---|---|---|
| **Driver node** | Runs the Spark driver, notebook REPLs (Python/Scala/R/SQL contexts), the `SparkContext`, `toPandas()`/`collect()` results, single-machine libraries (pandas, sklearn, xgboost non-distributed) | Driver is billed whether or not workers are busy. Driver-bound code on a big cluster wastes all worker spend. |
| **Worker nodes** | Run Spark executors (tasks) | Billed per node-hour (DBU + VM) |
| **Execution contexts (REPLs)** | One per attached notebook per language; multiple users share one cluster in Standard access mode | Consolidation lever: one well-sized shared cluster can replace many personal ones |
| **Local disk / elastic disk** | Shuffle spill, Delta/disk cache | Autoscaling local storage adds cloud disk cost |
| **Init scripts & libraries** | Run on every (re)start on every node | Startup time is paid time; heavy init scripts discourage auto-termination |

### 2.3 Cluster lifecycle states

`PENDING → RUNNING ↔ RESIZING → TERMINATING → TERMINATED` (also `RESTARTING`, `ERROR`, `UNKNOWN`).

- An APC cluster definition **persists** after termination (same `cluster_id`) and can be restarted; libraries are reinstalled and notebooks reattached on restart.
- Terminated APC configs are pruned after 30 days unless **pinned** by an admin.
- If a scheduled job targets an existing terminated APC, the cluster **autostarts** (a hidden source of APC spend).
- JDBC/ODBC connections can also autostart an APC.

### 2.4 Auto-termination — exactly what "idle" means

Per Databricks docs, a cluster is **inactive** only when *all* commands have finished: Spark jobs, Structured Streaming, JDBC calls, and web-terminal activity. Termination happens when `now − last_command_time > autotermination_minutes`.

Implications:

- **Idle cost = autotermination window × cluster size**, every time a user walks away. A 20-node cluster with a 120-min window burns 40 node-hours per abandoned session.
- An **open streaming query**, a **BI tool polling via JDBC**, or a **`while True` loop** keeps the cluster "active" forever — CPU may be ~0% but auto-termination never fires. System tables (CPU ~idle but uptime continuous) are the only way to catch this.
- `autotermination_minutes = 0` disables it entirely.
- Older runtimes can report stale activity times for JDBC/R/streaming — another reason to keep DBR current.

### 2.5 Autoscaling internals

- **Standard autoscaling:** adds nodes stepwise; scales down only when nodes are fully idle.
- **Optimized autoscaling** (Premium+ tiers): scales up in fewer steps, and can scale down even when the cluster isn't idle by evaluating shuffle-file state. Per docs, on all-purpose compute it scales down after the cluster is underutilized for a longer window (≈150 seconds) than on job compute (≈40 seconds) — interactive clusters are deliberately "stickier."
- **Key insight:** For interactive clusters, `min_autoscale_workers` is a **cost floor that is paid for every running minute**. A min of 8 on an exploratory cluster is usually waste.
- Autoscaling does not help driver-bound workloads at all.

### 2.6 Access modes (`data_security_mode`)

| Value | UI name | Who | Consolidation potential |
|---|---|---|---|
| `USER_ISOLATION` | Standard (formerly Shared) | Many users, UC-enforced isolation | **High** — one cluster serves a team |
| `SINGLE_USER` | Dedicated (formerly Single user) | One user or one group | Low per cluster; needed for some ML/RDD/GPU workloads |
| `LEGACY_*`, `NONE` | Legacy (passthrough, table ACL, no isolation) | — | Migrate: blocks UC features and often serverless migration |

### 2.7 Instance pools

- Pools keep idle VMs warm to cut start time.
- **Databricks does not charge DBUs for idle instances sitting in a pool**, but the **cloud provider does bill the VMs**. `min_idle_instances` is therefore a 24×7 VM cost.
- Pools are a lever to make *aggressive auto-termination tolerable* (fast restarts), not a free lunch.

### 2.8 Spot / preemptible capacity

- AWS: `aws_attributes.availability` = `SPOT`, `SPOT_WITH_FALLBACK`, `ON_DEMAND`; `first_on_demand` = number of nodes (starting with driver) kept on-demand.
- Azure: `azure_attributes.availability` = `SPOT_AZURE`, `SPOT_WITH_FALLBACK_AZURE`, `ON_DEMAND_AZURE`; `spot_bid_max_price` (−1 = up to on-demand price).
- GCP: preemptible / spot via `gcp_attributes`.
- **Spot reduces only the cloud VM portion**, not DBUs. Keep the **driver on-demand** (`first_on_demand ≥ 1`) for interactive clusters — losing the driver loses the notebook state.
- Flexible node types (`worker_node_type_flexibility`) let the cluster fall back across compatible instance types, which improves spot acquisition.

### 2.9 Photon

- Photon is a vectorized C++ engine for SQL/DataFrame operations. It carries a **higher DBU rate** (separate Photon SKUs; `product_features.is_photon = true`).
- Photon reduces cost **only if** the speedup exceeds the DBU multiplier. Interactive notebooks dominated by Python UDFs, pandas, ML training, or idle time get **no benefit** but still pay the Photon rate for every running minute — including idle minutes.
- Rule: Photon on APC should be opt-in per use case, not a default.

### 2.10 How jobs on APC are billed and attributed

- A job that runs on an existing all-purpose cluster is billed at the **all-purpose SKU**, not Jobs.
- In `system.billing.usage`, `usage_metadata.job_id` / `job_run_id` are **not populated** for jobs run on all-purpose compute — the cost only appears under `usage_metadata.cluster_id`. You must detect these via `system.lakeflow.job_task_run_timeline.compute_ids`.
- Notebook workflows (`dbutils.notebook.run`, `WORKFLOW_RUN`) inherit the parent's compute and billing.
- External orchestrators (Azure Data Factory, Airflow `DatabricksSubmitRunOperator` with `existing_cluster_id`, etc.) typically appear as `SUBMIT_RUN` runs in the timeline tables.

---

## 3. The APC Cost Model

### 3.1 Formula

```
APC total cost = Databricks DBU cost + Cloud infrastructure cost

DBU cost       = Σ (node-hours × DBU/hr for that node type × $/DBU for the APC SKU [× Photon uplift])
Cloud cost     = Σ (VM-hours × VM $/hr [spot/on-demand/reserved]) + managed disks + elastic disk + egress
```

Every term is a lever:

| Term | Lever |
|---|---|
| node-hours | auto-termination, idle detection, autoscaling bounds, fewer/smaller nodes, consolidation |
| DBU/hr per node | instance family & size, newer generations, GPU vs CPU choice |
| $/DBU | SKU (All-Purpose → Jobs/Serverless/SQL), Photon on/off, commit discounts |
| VM $/hr | spot/fleet, reserved instances/savings plans, newer generations, ARM (Graviton/Ampere where supported) |
| disks | elastic disk, EBS/managed disk sizing |

### 3.2 Clarify what the $40M contains (do this first)

`system.billing.usage` × `system.billing.list_prices` gives **list-price DBU cost only**. It does **not** include:

- your **negotiated discount** (list prices table is published list; apply your contract rate separately),
- **cloud VM/disk cost** for classic compute (comes from AWS CUR / Azure Cost Management / GCP Billing export; Databricks tags VMs with `ClusterId`, `ClusterName`, `Creator`, and your custom tags).

If the $40M is the Databricks invoice, VM spend is likely a large additional amount; if it is total cost of ownership, then split it. Many levers (idle, right-sizing) cut **both**; spot/RI cut only VM; SKU moves cut only DBU rate.

### 3.3 Why APC is the expensive SKU

Pull your actual rates (they vary by cloud, region, tier, contract):

```sql
SELECT sku_name, pricing.effective_list.default AS usd_per_dbu, price_start_time
FROM system.billing.list_prices
WHERE price_end_time IS NULL
  AND currency_code = 'USD'
  AND (sku_name LIKE '%ALL_PURPOSE%' OR sku_name LIKE '%JOBS%' OR sku_name LIKE '%SERVERLESS%' OR sku_name LIKE '%INTERACTIVE%')
ORDER BY sku_name;
```

Commonly cited AWS Premium list rates put all-purpose around ~3.5–4× classic Jobs compute per DBU for the same node — verify with the query above for your account. That ratio is the single biggest number in the savings model.

---

## 4. Use-Case Pattern Catalog

Each pattern lists: **description → detection signature in system tables → right target → levers**.

### P1. Scheduled production jobs on APC *(highest-value anti-pattern)*
- **Signature:** cluster appears in `lakeflow.job_task_run_timeline.compute_ids` with `run_type = 'JOB_RUN'` and `trigger_type` in (`CRON`, `PERIODIC`, `FILE_ARRIVAL`, `TABLE`, `CONTINUOUS`); `clusters.cluster_source IN ('UI','API')`.
- **Target:** Jobs compute (job clusters, shared across tasks) or serverless jobs.
- **Levers:** L1, L2, L50 (policy to forbid `existing_cluster_id` for scheduled jobs).

### P2. Externally orchestrated runs on APC (ADF, Airflow, Control-M, custom API)
- **Signature:** `run_type = 'SUBMIT_RUN'` in timeline tables with an APC cluster in `compute_ids`; regular cadence of runs; often a cluster that is up 24×7 with spiky CPU.
- **Target:** Jobs compute via `new_cluster` spec in the submit payload, or serverless jobs; for ADF use job-cluster linked service.
- **Levers:** L1, L3, L4.

### P3. Always-on "team" cluster (24×7, nobody owns turning it off)
- **Signature:** `auto_termination_minutes = 0` or very large; driver present in `node_timeline` > 20 h/day, including weekends; low average CPU.
- **Target:** Standard-mode shared cluster with 30–60 min auto-termination + pool for fast restart, or serverless notebooks.
- **Levers:** L10–L15, L20.

### P4. Personal "pet" clusters (one per user, oversized, rarely used)
- **Signature:** `data_security_mode = 'SINGLE_USER'`, distinct `owned_by` per cluster, low users-per-cluster from audit `attachNotebook`, many clusters with few active minutes.
- **Target:** Personal Compute policy (single node, small), serverless notebooks, or shared Standard cluster per team.
- **Levers:** L12, L20, L21, L52.

### P5. Ad-hoc exploration / EDA on small data
- **Signature:** low worker CPU, short bursts, driver CPU > workers, sessions with long gaps; data volume small.
- **Target:** Serverless notebooks (no idle burn, no startup wait) or single-node cluster.
- **Levers:** L5, L22, L11.

### P6. Driver-bound data science (pandas, sklearn, statsmodels, `toPandas()`)
- **Signature:** in `node_timeline`, driver CPU/memory high while worker CPU < 5–10%; `mem_used_percent` on driver near 90%+, `mem_swap_percent` > 0.
- **Target:** Single-node cluster with a large memory-optimized driver; or rewrite to pandas API on Spark / Spark ML / pandas UDFs.
- **Levers:** L22, L23, L60–L63.

### P7. Distributed ML training (CPU: XGBoost/LightGBM/Spark ML/Hyperopt/Optuna)
- **Signature:** ML runtime (`dbr_version LIKE '%-ml-%'`), sustained high worker CPU for long periods, often run manually from notebooks.
- **Target:** Develop on small APC; run full training as a job on Jobs compute; tune parallelism.
- **Levers:** L1, L30–L34, L64.

### P8. GPU deep learning / LLM fine-tuning on classic GPU clusters
- **Signature:** `dbr_version LIKE '%gpu%'`, node types with `node_types.gpu_count > 0`; GPU clusters idle between experiments (very expensive idle).
- **Target:** AI Runtime (serverless GPU, A10/H100) for interactive and training; Foundation Model fine-tuning / Model Serving where applicable; jobs for long runs.
- **Levers:** L6, L13 (short auto-termination on GPU), L35.
- **Note:** `node_timeline` does **not** expose GPU utilization; use cluster metrics UI / `nvidia-smi` sampling or MLflow system metrics.

### P9. GenAI experimentation (LLM API calls, RAG prototyping, embedding generation)
- **Signature:** low CPU, long sessions waiting on network I/O; high `network_sent/received_bytes` relative to CPU.
- **Target:** Serverless notebooks; batch embedding via `ai_query` / batch inference jobs; vector search pipelines.
- **Levers:** L5, L7.

### P10. BI / SQL tools hitting APC via JDBC/ODBC (Power BI, Tableau, Excel, dbt)
- **Signature:** continuous uptime, periodic small CPU spikes, few/no notebook `attachNotebook` or `runCommand` events from humans, `user_agent` of BI drivers in audit logs.
- **Target:** SQL warehouses (serverless preferred) — built for this, scale to zero, Photon included.
- **Levers:** L8.

### P11. Streaming on APC
- **Signature:** cluster never auto-terminates; steady moderate CPU 24×7; long-running notebook command.
- **Target:** Jobs compute (continuous trigger) or Lakeflow Declarative Pipelines; consider `availableNow` triggers on a schedule if latency allows.
- **Levers:** L1, L9.

### P12. Notebook workflows (`dbutils.notebook.run`) orchestration on APC
- **Signature:** `WORKFLOW_RUN` rows in `job_run_timeline`; cost charged to parent notebook's cluster.
- **Target:** Convert to multi-task Lakeflow Jobs on job compute.
- **Levers:** L1, L2.

### P13. Dev/test of pipelines (legit interactive) with oversized prod-like clusters
- **Signature:** same node types/counts as production jobs, low utilization, business-hours usage.
- **Target:** Smaller dev policy (capped `dbus_per_hour`), data sampling, serverless notebooks.
- **Levers:** L20, L21, L52.

### P14. Training / onboarding / hackathon clusters
- **Signature:** burst of cluster creations by many new users, then abandonment.
- **Target:** Single shared Standard cluster per class with strict auto-termination, or serverless.
- **Levers:** L12, L51.

### P15. IDE / Databricks Connect / VS Code / RStudio sessions
- **Signature:** activity via API, `user_agent` contains IDE/connect identifiers; long attached sessions with sparse compute.
- **Target:** Databricks Connect against serverless; short auto-termination.
- **Levers:** L5, L11.

### P16. Library-heavy / init-script-heavy clusters ("I never turn it off because startup takes 20 min")
- **Signature:** `init_scripts` populated; long `INSTANCE_LAUNCHING → INSTANCE_PLACED` gaps in `instance_events`; auto-termination disabled.
- **Target:** Pools with `preloaded_spark_version`, container images (DCS), workspace/UC volume–hosted wheels, serverless environments; then shorten auto-termination.
- **Levers:** L14, L15, L16.

### P17. Zombie / orphan clusters
- **Signature:** owner deprovisioned or departed; cluster restarts by schedule/JDBC autostart; no human attaches in 30+ days.
- **Target:** delete / unpin; transfer ownership.
- **Levers:** L17, L53.

---

## 5. Optimization Lever Catalog

Impact: ★★★ high / ★★ medium / ★ low. Effort: L/M/H. "Cuts" = which cost term it reduces.

### A. Workload placement (change the SKU) — biggest lever

| ID | Lever | Cuts | Impact | Effort | Notes |
|---|---|---|---|---|---|
| L1 | Move scheduled jobs from APC to **Jobs compute** (job clusters) | $/DBU | ★★★ | M | Same Spark code; change compute spec. Reuse one job cluster across tasks to amortize startup. |
| L2 | Move scheduled jobs to **serverless jobs** | $/DBU + VM + idle | ★★★ | M | No VM bill, no idle; check feature limits (init scripts, RDD APIs, some Spark confs). Use Standard performance mode for non-urgent work. |
| L3 | Change ADF/Airflow/external submits from `existing_cluster_id` to `new_cluster` / job definition | $/DBU | ★★★ | L | Usually a config change in the orchestrator. |
| L4 | Convert `runs/submit` one-offs into defined Lakeflow Jobs | $/DBU, visibility | ★★ | M | Also gains `job_id` attribution in billing. |
| L5 | Move bursty interactive users to **serverless notebooks** | idle, VM, startup | ★★★ | M | Billed as `INTERACTIVE`; eliminates idle windows & oversized personal clusters. Verify language/API support for each team. |
| L6 | Move GPU interactive/training to **AI Runtime (serverless GPU)** | idle GPU | ★★★ | M | A10/H100; single-node accelerators; connection auto-terminates after 60 min idle. |
| L7 | Move batch inference / embeddings to batch inference jobs or `ai_query` | $/DBU | ★★ | M | |
| L8 | Move BI/JDBC/SQL users to **serverless SQL warehouses** | $/DBU, idle | ★★★ | L–M | Photon included, scale to zero. |
| L9 | Move streaming to Jobs compute / Lakeflow pipelines; use `availableNow` scheduled triggers when latency allows | $/DBU, 24×7 uptime | ★★ | M | |

### B. Idle elimination

| ID | Lever | Impact | Effort | Notes |
|---|---|---|---|---|
| L10 | Policy-enforce `autotermination_minutes` (e.g., fixed 30–60; max 60) | ★★★ | L | Most universal lever. |
| L11 | Shorter windows for expensive clusters (≤ 20–30 min for >X DBU/hr) | ★★ | L | Tier the window by cluster cost. |
| L12 | Forbid `autotermination_minutes = 0` except allow-listed streaming | ★★★ | L | |
| L13 | GPU clusters: 10–20 min auto-termination | ★★★ | L | GPU idle is the most expensive idle. |
| L14 | Instance pools with `preloaded_spark_version` to make restarts fast | ★★ | M | Watch `min_idle_instances` (VM cost). Set `idle_instance_autotermination_minutes`. |
| L15 | Replace heavy init scripts with prebuilt images / wheels in UC volumes / environments | ★★ | M | Shortens startup → users accept auto-termination. |
| L16 | Pin `dbr_version` to current LTS for reliable activity tracking | ★ | L | Old runtimes misreport activity for JDBC/R/streaming. |
| L17 | **Idle-killer automation**: terminate clusters with CPU ≈ 0 for N minutes even if "active" (open stream/JDBC poll) | ★★★ | M | Catches what auto-termination can't. See §11. |
| L18 | Off-hours schedule: auto-terminate all non-allowlisted APC at night/weekends | ★★ | L | |
| L19 | Disable JDBC autostart on APC where BI users should be on SQL warehouses | ★ | L | |

### C. Right-sizing

| ID | Lever | Impact | Effort | Notes |
|---|---|---|---|---|
| L20 | Cap size via policy `dbus_per_hour` (range with `maxValue`) | ★★★ | L | Direct per-cluster cost ceiling. |
| L21 | Restrict `node_type_id` / `driver_node_type_id` allowlists per persona | ★★ | L | |
| L22 | **Single-node** clusters for driver-bound work | ★★★ | L | Detect via driver-vs-worker CPU skew. |
| L23 | Size driver to the workload (large driver only when needed) | ★★ | L | |
| L24 | Lower `min_autoscale_workers` (0–2 for interactive) | ★★★ | L | Min workers are paid every running minute. |
| L25 | Tighten `max_autoscale_workers` based on observed p95 node count | ★★ | L | |
| L26 | Prefer autoscaling over fixed `worker_count` for interactive | ★★ | L | |
| L27 | Match instance family to bottleneck: memory-optimized (high mem%), compute-optimized (high CPU), storage-optimized (high `cpu_wait_percent` / disk cache) | ★★ | M | |
| L28 | Migrate to newest instance generations (better price-performance) | ★★ | L | Detect old gens in `node_type`. |
| L29 | Fewer, larger workers vs many small ones (shuffle efficiency, fewer DBU overheads) — test per workload | ★ | M | |

### D. Price of capacity

| ID | Lever | Cuts | Impact | Effort | Notes |
|---|---|---|---|---|---|
| L30 | Spot/spot-with-fallback for **workers**; driver on-demand (`first_on_demand=1`) | VM | ★★★ | L | Policy-default it. |
| L31 | Flexible node types / fleet instances to improve spot availability | VM | ★★ | L | |
| L32 | Reserved instances / savings plans for the always-on baseline that remains after cleanup | VM | ★★ | M | Do **after** idle cleanup, not before. |
| L33 | Databricks commit (DBCU) negotiation sized on post-optimization run-rate | $/DBU | ★★ | M | |
| L34 | **Photon only where ROI-positive** (disable by default on APC) | $/DBU | ★★ | L | Measure speedup vs multiplier. |
| L35 | ARM instances where supported (e.g., Graviton on AWS) | VM, DBU/hr | ★ | M | Check runtime/library support. |
| L36 | Right-size EBS/managed disks; turn off elastic disk where unnecessary | disk | ★ | L | |

### E. Consolidation

| ID | Lever | Impact | Effort | Notes |
|---|---|---|---|---|
| L40 | Replace N personal clusters with 1 Standard-mode team cluster (autoscale 1–N) | ★★★ | M | Use audit users-per-cluster and overlapping-usage analysis. |
| L41 | Limit clusters per user via policy `max_clusters_per_user` | ★★ | L | |
| L42 | Remove "unrestricted cluster creation" entitlement; users create only from policies | ★★★ | L | Core governance control. |

### F. Runtime, engine & data layout

| ID | Lever | Impact | Effort |
|---|---|---|---|
| L45 | Current LTS DBR (AQE, better scheduler, bug fixes) | ★ | L |
| L46 | Disk cache on storage-optimized nodes for repeated reads | ★ | L |
| L47 | Predictive optimization / liquid clustering / compaction to cut scan time | ★★ | L |
| L48 | Migrate legacy access modes to UC Standard/Dedicated (unblocks serverless) | ★★ | M |

### G. Governance & behavior

| ID | Lever | Impact | Effort |
|---|---|---|---|
| L50 | Policy: forbid jobs on APC (block `existing_cluster_id` in CI/CD checks; policy `cluster_type` restrictions) | ★★★ | L |
| L51 | Mandatory tags (cost_center, team, env, use_case) enforced by policy | ★★ | L |
| L52 | Persona-based policies (Analyst, DE-dev, DS-CPU, DS-GPU, Streaming-exception) | ★★★ | M |
| L53 | Monthly cluster hygiene: delete unused, unpin stale, transfer orphan ownership | ★ | L |
| L54 | Showback/chargeback dashboards per team & owner | ★★ | M |
| L55 | Budget alerts / anomaly alerts on APC spend | ★ | L |
| L56 | "Top 20 wasteful clusters" weekly nudges to owners | ★★ | L |

### H. Code-level (data science heavy)

| ID | Lever | Impact | Notes |
|---|---|---|---|
| L60 | Avoid `toPandas()` / `collect()` on large data; use pandas API on Spark | ★★ | Stops driver bloat that forces huge drivers. |
| L61 | Replace row-at-a-time Python UDFs with pandas UDFs or native functions | ★★ | |
| L62 | Cache/persist reused DataFrames; unpersist after | ★ | |
| L63 | Sample during exploration (`TABLESAMPLE`, `limit`) | ★★ | |
| L64 | Right-size HPO parallelism (Hyperopt/Optuna/Ray) to cluster cores; early stopping | ★★ | |
| L65 | Stop streams / `spark.stop()` patterns at notebook end; avoid `while True` polling cells | ★★ | Directly prevents "active but idle" clusters. |

---

## 6. System Tables Deep Reference

> Enable schemas (`compute`, `billing`, `lakeflow`, `access`, `query`) per metastore. Grant `USE` + `SELECT` to the FinOps group. **Billing tables are global** (cross-region); **compute, lakeflow and most audit tables are regional** — run compute-table queries in a workspace in each region and union results.

### 6.1 `system.billing.usage` — the money table

| Column | Type | Use for APC |
|---|---|---|
| `record_id` | string | dedup key |
| `account_id`, `workspace_id` | string | |
| `sku_name` | string | e.g. `PREMIUM_ALL_PURPOSE_COMPUTE`, Photon variants |
| `cloud` | string | AWS / AZURE / GCP |
| `usage_start_time`, `usage_end_time` | timestamp | hourly granularity for classic compute |
| `usage_date` | date | partition-friendly filter |
| `custom_tags` | map | cluster tags → chargeback |
| `usage_unit` | string | `DBU` |
| `usage_quantity` | decimal | DBUs (can be negative for retractions — always SUM) |
| `usage_metadata` | struct | `cluster_id`, `instance_pool_id`, `node_type`, `job_id`, `job_run_id`, `notebook_id`, `warehouse_id`, … |
| `identity_metadata` | struct | `run_as` (for APC = identity that **created** the cluster, not necessarily owner), `owned_by`, `created_by` |
| `record_type` | string | `ORIGINAL`, `RETRACTION`, `RESTATEMENT` |
| `ingestion_date` | date | |
| `billing_origin_product` | string | **`ALL_PURPOSE`** = classic APC; `INTERACTIVE` = serverless notebooks; `JOBS`, `SQL`, `DLT`, `AI_RUNTIME`, … |
| `product_features` | struct | `is_photon`, `is_serverless`, `jobs_tier`, `performance_target`, … |
| `usage_type` | string | `COMPUTE_TIME`, `GPU_TIME`, … |

Critical facts:
- Filter APC with `billing_origin_product = 'ALL_PURPOSE'`.
- `usage_metadata.job_id` is **null** for jobs run on APC — attribute via lakeflow timeline tables.
- If driver and worker node types differ, usage splits into separate records per `node_type`.
- For owner attribution, join `usage_metadata.cluster_id` → `system.compute.clusters.owned_by` (point-in-time).
- Records typically land within ~12 hours.

### 6.2 `system.billing.list_prices`

| Column | Use |
|---|---|
| `sku_name`, `cloud`, `currency_code`, `usage_unit` | join keys |
| `price_start_time`, `price_end_time` | time-valid join (`price_end_time IS NULL` = current) |
| `pricing.default` | list price |
| `pricing.promotional.default` | temporary promo |
| `pricing.effective_list.default` | **use this** — list price resolved with promotions |

Join on `sku_name` **and** the time window, or you will double-count. List ≠ your contract price — apply your discount factor.

### 6.3 `system.compute.clusters` (SCD2 — full config history)

| Column | Optimization use |
|---|---|
| `cluster_id`, `cluster_name`, `workspace_id` | keys |
| `owned_by` | owner for nudges/chargeback |
| `create_time`, `delete_time` | lifecycle; orphan detection |
| `driver_node_type`, `worker_node_type` | right-sizing, generation checks, GPU detection |
| `worker_count` | fixed-size clusters (0 + no autoscale → single node) |
| `min_autoscale_workers`, `max_autoscale_workers` | autoscale floor/ceiling |
| `auto_termination_minutes` | idle policy compliance |
| `enable_elastic_disk` | disk cost |
| `tags` | chargeback; `ResourceClass=SingleNode` |
| `cluster_source` | **`UI`/`API` = all-purpose**; `JOB`, `PIPELINE`, `PIPELINE_MAINTENANCE` |
| `init_scripts` | startup-cost signal |
| `aws_attributes` / `azure_attributes` / `gcp_attributes` | spot vs on-demand, `first_on_demand` |
| `driver_instance_pool_id`, `worker_instance_pool_id` | pool usage |
| `dbr_version` | ML/GPU runtime, runtime currency |
| `data_security_mode` | access mode (`USER_ISOLATION`, `SINGLE_USER`, legacy) |
| `policy_id` | policy coverage (null = unpoliced) |
| `change_time`, `change_date` | SCD2 ordering |

Get current state with `QUALIFY ROW_NUMBER() OVER (PARTITION BY workspace_id, cluster_id ORDER BY change_time DESC) = 1`. Clusters deleted before Oct 23, 2023 are absent.

### 6.4 `system.compute.node_types`

`node_type`, `core_count`, `memory_mb`, `gpu_count` — normalize utilization to cores/GB, detect GPU nodes, compute "allocated cores × hours".

### 6.5 `system.compute.node_timeline` — the utilization table (per instance per minute)

| Column | Meaning | Derived signal |
|---|---|---|
| `cluster_id`, `instance_id`, `driver` | identity & role | driver vs worker skew |
| `start_time`, `end_time` | minute bucket (UTC) | uptime, time-of-day patterns |
| `cpu_user_percent` + `cpu_system_percent` | CPU busy | idle, over-provisioning |
| `cpu_wait_percent` | I/O wait | storage/IO-bound → storage-optimized, caching, layout fixes |
| `mem_used_percent` | memory used (incl. background) | memory over/under-provision |
| `mem_swap_percent` | swap | memory pressure → bigger/memory-optimized |
| `network_sent_bytes`, `network_received_bytes` | network | shuffle-heavy or API-wait workloads |
| `disk_free_bytes_per_mount_point` | ephemeral disk free | spill pressure, disk over-provision |
| `node_type`, `private_ip` | | |

Limits: no serverless/SQL warehouse rows; nodes running < 10 minutes may be missing; **no GPU metrics**; driver has background CPU of a few percent even when idle.

### 6.6 `system.compute.instance_events` (Public Preview)

`instance_id`, `event_time`, `event_type` (`INSTANCE_LAUNCHING`, `STATE_TRANSITION`), `state` (`INSTANCE_LAUNCHING`, `INSTANCE_READY`, `INSTANCE_PLACED`, `INSTANCE_TERMINATED`), `cluster_id` (only when `INSTANCE_PLACED`), `instance_pool_id`, `node_type`, `availability_type` (`ON_DEMAND`/`SPOT`/`PREEMPTIBLE`).

Use for: **spot coverage %**, **startup latency** (launching → placed), **pool idle minutes** (`INSTANCE_READY` time = warm VM you pay the cloud for).

### 6.7 `system.compute.instance_pools` (SCD2, Public Preview)

`instance_pool_id`, `instance_pool_name`, `node_type`, `min_idle_instances`, `max_capacity`, `idle_instance_autotermination_minutes`, `preloaded_spark_version`, `preloaded_docker_images`, cloud attributes, `tags`. Use to audit pools whose `min_idle_instances` create 24×7 VM cost.

### 6.8 `system.lakeflow.*` (jobs)

| Table | Key columns for APC |
|---|---|
| `jobs` (SCD2) | `job_id`, `name`, `creator_id`, `run_as`, `trigger`, `trigger_type`, `tags`, `paused` |
| `job_tasks` (SCD2) | `task_key`, `depends_on_keys` |
| `job_run_timeline` | `run_id`, `run_type` (`JOB_RUN`/`SUBMIT_RUN`/`WORKFLOW_RUN`), `trigger_type`, `compute_ids`, `result_state`, `period_start_time/end_time` (hourly slices) |
| `job_task_run_timeline` | `run_id`, `job_run_id`, `task_key`, **`compute_ids`** (job clusters, **interactive clusters**, warehouses), `compute` details, `setup/execution/cleanup_duration_seconds` (rows after early Dec 2025), `result_state`, `termination_code` |

Timeline rows are sliced hourly (clock-hour-aligned since Jan 19, 2026); sum slices per run.

### 6.9 `system.access.audit`

Columns: `event_time`, `event_date`, `workspace_id`, `service_name`, `action_name`, `user_identity.email`, `request_params` (map), `response`, `user_agent`, `source_ip_address`, `audit_level`.

APC-relevant events:
- `service_name='clusters'`: `create`, `edit`, `start`, `restart`, `delete` (terminate), `permanentDelete`, `resize`, `changeClusterOwner`, `changeClusterAcl` — who creates/edits/restarts what.
- `service_name='notebook'`: `attachNotebook` / `detachNotebook` (notebook ↔ cluster ↔ user mapping), `runCommand` (**verbose audit logs only** — includes `executionTime`, `status`, `commandText`).
- `service_name='jobs'`: `runCommand` (verbose), `runNow`, `submitRun`.

Use for: users-per-cluster, human activity vs. machine activity, last human touch, command durations.

> Request-param key names vary by event; run the discovery query in §8.13 before relying on them.

### 6.10 `system.query.history`

Covers SQL warehouses and **serverless** notebooks/jobs only — **not classic APC**. Useful *after* migration to compare cost/performance and for BI workloads moved to warehouses.

### 6.11 Data you still need outside system tables

| Need | Source |
|---|---|
| Cloud VM/disk cost | AWS CUR / Azure Cost Management / GCP billing export, joined via Databricks VM tags (`ClusterId`) |
| Contract $/DBU | Your Databricks contract |
| Cluster events (autoscale resize, spot loss) | Clusters API `events` endpoint / cluster event log |
| GPU utilization | Cluster metrics UI, `nvidia-smi`, MLflow system metrics |
| Spark stage-level detail | Spark UI / event logs (cluster log delivery) |

---

## 7. Metrics & KPI Catalog

Thresholds are starting points — calibrate on your distribution (e.g., flag worst decile).

### 7.1 Spend & attribution

| KPI | Definition | Source | Use |
|---|---|---|---|
| APC list cost | Σ DBU × effective_list | usage × list_prices | baseline |
| APC net cost | APC list × (1 − contract discount) + VM cost | + cloud billing | true baseline |
| APC share of compute | APC $ / all compute $ | usage | strategic north-star (target ↓) |
| Cost by team/owner/cluster | group by `custom_tags`, `owned_by` | usage + clusters | chargeback |
| Untagged APC % | $ where cost_center tag null | usage | governance |
| Unpoliced APC % | $ on clusters with `policy_id IS NULL` | usage + clusters | governance |
| Photon APC % | $ with `is_photon = true` | usage | Photon review |
| Weekend/off-hours % | $ outside business hours | usage (hourly) | idle/schedule lever |

### 7.2 Idle & uptime

| KPI | Definition | Threshold | Lever |
|---|---|---|---|
| Uptime hours / day | driver minutes / 60 | > 20 h → always-on | L10, L17 |
| **Idle node-minute ratio** | node-minutes in minutes where driver CPU < 10% and avg worker CPU < 5% ÷ total node-minutes | > 40% | L10–L18 |
| **Idle cost $** | cluster cost × idle ratio | rank top-N | nudges/automation |
| Auto-termination distribution | % clusters with 0 / >60 / >120 min | 0 → violation | L10, L12 |
| "Active-but-idle" sessions | contiguous idle runs > autotermination window | any | L17 (stream/JDBC holds) |
| Days since last human attach | from audit `attachNotebook` | > 30 | L53 |

### 7.3 Right-sizing

| KPI | Definition | Threshold | Lever |
|---|---|---|---|
| Avg / p95 worker CPU | busy % on workers (active minutes only) | p95 < 30% | L24, L25, L27 |
| Avg / p95 worker memory | `mem_used_percent` | p95 < 40% | smaller / compute-optimized |
| Driver-bound score | driver CPU p95 high (> 60%) **and** worker CPU p95 < 10% | true | L22 |
| Driver memory pressure | driver `mem_used_percent` p95 > 90% or swap > 0 | true | L23, L60 |
| Autoscale utilization | avg active workers / `max_autoscale_workers` | < 0.3 | L25 |
| Min-worker burden | `min_autoscale_workers` × uptime hours | high | L24 |
| IO-wait ratio | `cpu_wait_percent` p95 | > 15% | L27 storage-optimized, L46/L47 |
| Swap events | `mem_swap_percent` > 0 | any sustained | memory-optimized |
| Disk headroom | min `disk_free` on `/local_disk0` | very high constantly → shrink disks | L36 |
| Instance generation lag | % node-hours on old generations | > 20% | L28 |

### 7.4 Pricing efficiency

| KPI | Definition | Target |
|---|---|---|
| Spot coverage (workers) | spot instance-minutes / total worker instance-minutes | > 60–80% on non-critical interactive |
| Pool idle VM-hours | `INSTANCE_READY` minutes in pools | minimize |
| Startup latency p50/p95 | launching → placed | track; justify pools |
| Photon ROI | runtime(non-Photon)/runtime(Photon) vs DBU multiplier | > multiplier |

### 7.5 Workload placement

| KPI | Definition | Target |
|---|---|---|
| **Jobs-on-APC cost** | APC $ on clusters used by job task runs (allocated) | → 0 |
| Jobs-on-APC count | distinct jobs/submit runs on APC | → 0 |
| Scheduled-trigger runs on APC | `trigger_type` CRON/PERIODIC/etc. on APC | → 0 |
| BI/JDBC APC clusters | clusters with machine activity & no human attach | → 0 |
| GPU APC idle $ | GPU cluster cost × idle ratio | → 0 (AI Runtime) |
| Serverless adoption | INTERACTIVE $ / (INTERACTIVE + ALL_PURPOSE) $ | ↑ |

### 7.6 Consolidation & hygiene

| KPI | Definition | Target |
|---|---|---|
| Users per active cluster | distinct users attaching per cluster per week | ↑ |
| Clusters per user | active clusters per owner | ≤ 1–2 |
| Legacy access mode % | clusters/$ on `LEGACY_*`/`NONE` | → 0 |
| Old DBR % | clusters on non-supported runtimes | → 0 |
| Cost per active user | APC $ / distinct active users | ↓ |

---

## 8. SQL Query Library

Conventions:
- Run in a Databricks SQL warehouse (or serverless notebook) per region for `compute`/`lakeflow`/`audit` tables; billing is global.
- Create a `finops` schema (e.g., `main.finops`) and **materialize** the base views as tables refreshed daily by a job — `node_timeline` is large.
- Thresholds are parameters: `IDLE_DRIVER_CPU = 10`, `IDLE_WORKER_CPU = 5`. Tune after eyeballing distributions.
- Replace tag keys (`cost_center`, `team`) with your organization's keys.
- Apply your contract discount to `list_usd` for net figures.

### 8.1 Base: current config of all-purpose clusters

```sql
CREATE OR REPLACE VIEW finops.v_apc_clusters_latest AS
SELECT
  c.*,
  (c.worker_count = 0 AND c.max_autoscale_workers IS NULL)
    OR c.tags['ResourceClass'] = 'SingleNode'                 AS is_single_node,
  c.dbr_version LIKE '%ml%'                                    AS is_ml_runtime,
  c.dbr_version LIKE '%gpu%'                                   AS is_gpu_runtime,
  COALESCE(c.aws_attributes.availability, c.azure_attributes.availability) AS availability,
  COALESCE(CAST(c.aws_attributes.first_on_demand AS INT),
           CAST(c.azure_attributes.first_on_demand AS INT))    AS first_on_demand
FROM system.compute.clusters c
WHERE c.cluster_source IN ('UI', 'API')          -- all-purpose only
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.workspace_id, c.cluster_id ORDER BY c.change_time DESC) = 1;
```

> If a cloud-attribute field doesn't resolve on your cloud, drop that branch of the `COALESCE`.

### 8.2 Base: hourly APC cost per cluster (list price)

```sql
CREATE OR REPLACE VIEW finops.v_apc_cost_hourly AS
WITH prices AS (
  SELECT sku_name, price_start_time, price_end_time,
         CAST(pricing.effective_list.default AS DECIMAL(30,10)) AS usd_per_unit
  FROM system.billing.list_prices
  WHERE currency_code = 'USD'
)
SELECT
  u.workspace_id,
  u.usage_metadata.cluster_id                AS cluster_id,
  date_trunc('HOUR', u.usage_start_time)     AS hour_ts,
  u.usage_date,
  u.sku_name,
  u.product_features.is_photon               AS is_photon,
  u.usage_metadata.node_type                 AS node_type,
  u.custom_tags['cost_center']               AS cost_center,   -- adapt tag keys
  u.custom_tags['team']                      AS team,
  u.identity_metadata.run_as                 AS created_by_identity,
  SUM(u.usage_quantity)                      AS dbus,          -- SUM nets out corrections
  SUM(u.usage_quantity * p.usd_per_unit)     AS list_usd
FROM system.billing.usage u
JOIN prices p
  ON u.sku_name = p.sku_name
 AND u.usage_end_time >= p.price_start_time
 AND (p.price_end_time IS NULL OR u.usage_end_time < p.price_end_time)
WHERE u.billing_origin_product = 'ALL_PURPOSE'
GROUP BY ALL;
```

### 8.3 Baseline: APC spend by month, workspace, team

```sql
SELECT date_trunc('MONTH', usage_date) AS month, workspace_id, team, cost_center,
       SUM(dbus) AS dbus, ROUND(SUM(list_usd), 0) AS list_usd
FROM finops.v_apc_cost_hourly
WHERE usage_date >= add_months(current_date(), -12)
GROUP BY ALL
ORDER BY month DESC, list_usd DESC;
```

APC share of all compute (strategic KPI):

```sql
WITH prices AS (
  SELECT sku_name, price_start_time, price_end_time, pricing.effective_list.default AS p
  FROM system.billing.list_prices WHERE currency_code = 'USD'
)
SELECT date_trunc('MONTH', u.usage_date) AS month, u.billing_origin_product,
       ROUND(SUM(u.usage_quantity * p.p), 0) AS list_usd,
       ROUND(100 * SUM(u.usage_quantity * p.p) / SUM(SUM(u.usage_quantity * p.p)) OVER (PARTITION BY date_trunc('MONTH', u.usage_date)), 1) AS pct
FROM system.billing.usage u
JOIN prices p ON u.sku_name = p.sku_name
  AND u.usage_end_time >= p.price_start_time
  AND (p.price_end_time IS NULL OR u.usage_end_time < p.price_end_time)
WHERE u.usage_date >= add_months(current_date(), -6)
GROUP BY ALL
ORDER BY month DESC, list_usd DESC;
```

### 8.4 Top 50 most expensive APC clusters with their config

```sql
SELECT k.workspace_id, k.cluster_id, c.cluster_name, c.owned_by, c.policy_id,
       c.driver_node_type, c.worker_node_type, c.worker_count,
       c.min_autoscale_workers, c.max_autoscale_workers, c.auto_termination_minutes,
       c.data_security_mode, c.dbr_version, c.availability, c.is_gpu_runtime,
       ROUND(SUM(k.list_usd), 0) AS list_usd_30d,
       ROUND(SUM(k.list_usd) * 365 / 30, 0) AS annualized_usd
FROM finops.v_apc_cost_hourly k
LEFT JOIN finops.v_apc_clusters_latest c
  ON k.workspace_id = c.workspace_id AND k.cluster_id = c.cluster_id
WHERE k.usage_date >= current_date() - INTERVAL 30 DAYS
GROUP BY ALL
ORDER BY list_usd_30d DESC
LIMIT 50;
```

### 8.5 Base: per-cluster per-minute utilization (materialize this)

```sql
CREATE OR REPLACE TABLE finops.apc_cluster_minute AS
SELECT
  n.workspace_id, n.cluster_id, n.start_time AS minute_ts,
  COUNT(*)                                                                         AS nodes,
  COUNT_IF(NOT n.driver)                                                           AS workers,
  MAX(CASE WHEN n.driver THEN n.cpu_user_percent + n.cpu_system_percent END)       AS driver_cpu,
  MAX(CASE WHEN n.driver THEN n.mem_used_percent END)                              AS driver_mem,
  MAX(CASE WHEN n.driver THEN n.mem_swap_percent END)                              AS driver_swap,
  AVG(CASE WHEN NOT n.driver THEN n.cpu_user_percent + n.cpu_system_percent END)   AS worker_cpu_avg,
  MAX(CASE WHEN NOT n.driver THEN n.cpu_user_percent + n.cpu_system_percent END)   AS worker_cpu_max,
  AVG(CASE WHEN NOT n.driver THEN n.mem_used_percent END)                          AS worker_mem_avg,
  AVG(n.cpu_wait_percent)                                                          AS cpu_wait_avg,
  MAX(n.mem_swap_percent)                                                          AS swap_max,
  SUM(n.network_sent_bytes + n.network_received_bytes)                             AS net_bytes
FROM system.compute.node_timeline n
JOIN finops.v_apc_clusters_latest c
  ON n.workspace_id = c.workspace_id AND n.cluster_id = c.cluster_id
WHERE n.start_time >= current_date() - INTERVAL 90 DAYS
GROUP BY n.workspace_id, n.cluster_id, n.start_time;
```

Add an idle flag view:

```sql
CREATE OR REPLACE VIEW finops.v_apc_cluster_minute AS
SELECT *,
  (COALESCE(driver_cpu, 0) < 10 AND COALESCE(worker_cpu_avg, 0) < 5) AS is_idle
FROM finops.apc_cluster_minute;
```

### 8.6 ⭐ Idle cost per cluster (hour-level allocation)

```sql
WITH m AS (
  SELECT workspace_id, cluster_id, date_trunc('HOUR', minute_ts) AS hour_ts,
         SUM(nodes)                              AS node_min,
         SUM(CASE WHEN is_idle THEN nodes END)   AS idle_node_min
  FROM finops.v_apc_cluster_minute
  WHERE minute_ts >= current_date() - INTERVAL 30 DAYS
  GROUP BY ALL
),
k AS (
  SELECT workspace_id, cluster_id, hour_ts, SUM(list_usd) AS list_usd
  FROM finops.v_apc_cost_hourly
  WHERE usage_date >= current_date() - INTERVAL 30 DAYS
  GROUP BY ALL
)
SELECT k.workspace_id, k.cluster_id, c.cluster_name, c.owned_by, c.auto_termination_minutes,
       ROUND(SUM(k.list_usd), 0)                                                   AS cost_30d,
       ROUND(SUM(k.list_usd * COALESCE(m.idle_node_min, 0) / NULLIF(m.node_min, 0)), 0) AS idle_cost_30d,
       ROUND(100 * SUM(COALESCE(m.idle_node_min, 0)) / NULLIF(SUM(m.node_min), 0), 1)  AS idle_pct,
       ROUND(SUM(m.node_min) / 60, 0)                                              AS node_hours
FROM k
LEFT JOIN m ON k.workspace_id = m.workspace_id AND k.cluster_id = m.cluster_id AND k.hour_ts = m.hour_ts
LEFT JOIN finops.v_apc_clusters_latest c ON k.workspace_id = c.workspace_id AND k.cluster_id = c.cluster_id
GROUP BY ALL
ORDER BY idle_cost_30d DESC
LIMIT 100;
```

### 8.7 "Active-but-idle" streaks (auto-termination never fired)

Finds contiguous idle runs longer than the cluster's own auto-termination window — evidence of open streams, JDBC polling, or loops holding the cluster.

```sql
WITH flagged AS (
  SELECT m.*, c.auto_termination_minutes,
         minute_ts - make_dt_interval(0, 0,
           CAST(ROW_NUMBER() OVER (PARTITION BY m.workspace_id, m.cluster_id, m.is_idle ORDER BY minute_ts) AS INT), 0) AS grp
  FROM finops.v_apc_cluster_minute m
  JOIN finops.v_apc_clusters_latest c ON m.workspace_id = c.workspace_id AND m.cluster_id = c.cluster_id
  WHERE m.minute_ts >= current_date() - INTERVAL 14 DAYS
)
SELECT workspace_id, cluster_id, auto_termination_minutes,
       MIN(minute_ts) AS idle_start, MAX(minute_ts) AS idle_end,
       COUNT(*) AS idle_minutes, ROUND(AVG(nodes), 1) AS avg_nodes
FROM flagged
WHERE is_idle
GROUP BY workspace_id, cluster_id, auto_termination_minutes, grp
HAVING COUNT(*) > GREATEST(COALESCE(NULLIF(auto_termination_minutes, 0), 0), 60)
ORDER BY idle_minutes * avg_nodes DESC
LIMIT 200;
```

> Gaps in `node_timeline` (missing minutes) will split streaks; that keeps the estimate conservative.

### 8.8 ⭐ Right-sizing profile (active minutes only)

```sql
SELECT m.workspace_id, m.cluster_id, c.cluster_name, c.owned_by,
       c.worker_node_type, c.min_autoscale_workers, c.max_autoscale_workers, c.worker_count,
       COUNT(*) FILTER (WHERE NOT is_idle)                                  AS active_minutes,
       percentile_approx(worker_cpu_avg, 0.95) FILTER (WHERE NOT is_idle)   AS p95_worker_cpu,
       percentile_approx(worker_mem_avg, 0.95) FILTER (WHERE NOT is_idle)   AS p95_worker_mem,
       percentile_approx(driver_cpu, 0.95)     FILTER (WHERE NOT is_idle)   AS p95_driver_cpu,
       percentile_approx(driver_mem, 0.95)                                  AS p95_driver_mem,
       MAX(driver_swap)                                                     AS max_driver_swap,
       percentile_approx(cpu_wait_avg, 0.95)                                AS p95_io_wait,
       AVG(workers)                                                         AS avg_workers,
       percentile_approx(workers, 0.95)                                     AS p95_workers,
       CASE
         WHEN percentile_approx(driver_cpu, 0.95) FILTER (WHERE NOT is_idle) > 60
          AND percentile_approx(worker_cpu_avg, 0.95) FILTER (WHERE NOT is_idle) < 10
          AND MAX(workers) > 0                                       THEN 'DRIVER_BOUND -> single node'
         WHEN percentile_approx(worker_cpu_avg, 0.95) FILTER (WHERE NOT is_idle) < 30
          AND percentile_approx(worker_mem_avg, 0.95) FILTER (WHERE NOT is_idle) < 40 THEN 'OVERSIZED -> fewer/smaller workers'
         WHEN percentile_approx(cpu_wait_avg, 0.95) > 15             THEN 'IO_BOUND -> storage-optimized / caching / layout'
         WHEN MAX(swap_max) > 1 OR percentile_approx(worker_mem_avg, 0.95) > 90 THEN 'MEMORY_PRESSURE -> memory-optimized'
         ELSE 'OK'
       END AS sizing_verdict
FROM finops.v_apc_cluster_minute m
JOIN finops.v_apc_clusters_latest c ON m.workspace_id = c.workspace_id AND m.cluster_id = c.cluster_id
WHERE m.minute_ts >= current_date() - INTERVAL 30 DAYS
GROUP BY ALL
HAVING active_minutes > 120
ORDER BY active_minutes DESC;
```

Autoscale floor burden (min workers paid while idle):

```sql
SELECT c.workspace_id, c.cluster_id, c.cluster_name, c.min_autoscale_workers, c.max_autoscale_workers,
       SUM(CASE WHEN m.is_idle THEN m.workers END) / 60 AS idle_worker_hours,
       AVG(m.workers) / NULLIF(c.max_autoscale_workers, 0) AS autoscale_utilization
FROM finops.v_apc_cluster_minute m
JOIN finops.v_apc_clusters_latest c ON m.workspace_id = c.workspace_id AND m.cluster_id = c.cluster_id
WHERE m.minute_ts >= current_date() - INTERVAL 30 DAYS AND c.min_autoscale_workers >= 2
GROUP BY ALL
ORDER BY idle_worker_hours DESC;
```

### 8.9 ⭐ Jobs running on APC (with cost allocation)

```sql
WITH task_exploded AS (
  SELECT t.workspace_id, t.job_id, t.job_run_id, t.task_key,
         explode(t.compute_ids) AS cluster_id,
         TIMESTAMPDIFF(SECOND, t.period_start_time, t.period_end_time) AS secs
  FROM system.lakeflow.job_task_run_timeline t
  WHERE t.period_start_time >= current_date() - INTERVAL 30 DAYS
    AND size(t.compute_ids) > 0
),
task_on_apc AS (
  SELECT e.*
  FROM task_exploded e
  JOIN finops.v_apc_clusters_latest c ON e.workspace_id = c.workspace_id AND e.cluster_id = c.cluster_id
),
run_meta AS (
  SELECT workspace_id, run_id, FIRST(run_type, TRUE) AS run_type, FIRST(trigger_type, TRUE) AS trigger_type
  FROM system.lakeflow.job_run_timeline
  WHERE period_start_time >= current_date() - INTERVAL 31 DAYS
  GROUP BY ALL
),
jobs_latest AS (
  SELECT workspace_id, job_id, name
  FROM system.lakeflow.jobs
  QUALIFY ROW_NUMBER() OVER (PARTITION BY workspace_id, job_id ORDER BY change_time DESC) = 1
),
job_hours AS (
  SELECT a.workspace_id, a.cluster_id, a.job_id, r.run_type, r.trigger_type,
         COUNT(DISTINCT a.job_run_id) AS runs, SUM(a.secs) / 3600 AS task_hours
  FROM task_on_apc a
  LEFT JOIN run_meta r ON a.workspace_id = r.workspace_id AND a.job_run_id = r.run_id
  GROUP BY ALL
),
cluster_totals AS (
  SELECT workspace_id, cluster_id, SUM(task_hours) AS all_task_hours FROM job_hours GROUP BY ALL
),
uptime AS (
  SELECT workspace_id, cluster_id, COUNT(*) / 60 AS uptime_hours
  FROM finops.v_apc_cluster_minute WHERE minute_ts >= current_date() - INTERVAL 30 DAYS GROUP BY ALL
),
cost AS (
  SELECT workspace_id, cluster_id, SUM(list_usd) AS cost_30d
  FROM finops.v_apc_cost_hourly WHERE usage_date >= current_date() - INTERVAL 30 DAYS GROUP BY ALL
)
SELECT j.workspace_id, j.cluster_id, j.job_id, jl.name AS job_name, j.run_type, j.trigger_type, j.runs,
       ROUND(j.task_hours, 1) AS task_hours, ROUND(u.uptime_hours, 1) AS cluster_uptime_hours,
       ROUND(co.cost_30d, 0) AS cluster_cost_30d,
       ROUND(co.cost_30d * j.task_hours / GREATEST(u.uptime_hours, ct.all_task_hours), 0) AS est_job_cost_30d,
       ROUND(ct.all_task_hours / NULLIF(u.uptime_hours, 0), 2) AS cluster_job_share
FROM job_hours j
JOIN cluster_totals ct ON j.workspace_id = ct.workspace_id AND j.cluster_id = ct.cluster_id
LEFT JOIN uptime u ON j.workspace_id = u.workspace_id AND j.cluster_id = u.cluster_id
LEFT JOIN cost co ON j.workspace_id = co.workspace_id AND j.cluster_id = co.cluster_id
LEFT JOIN jobs_latest jl ON j.workspace_id = jl.workspace_id AND j.job_id = jl.job_id
ORDER BY est_job_cost_30d DESC NULLS LAST;
```

Interpretation:
- `run_type = 'SUBMIT_RUN'` → external orchestrator (ADF/Airflow/API) → fix in the orchestrator (L3).
- `trigger_type` in CRON/PERIODIC/FILE_ARRIVAL/TABLE → scheduled production work (L1/L2).
- `cluster_job_share > 0.5` → the cluster is effectively a job cluster: **move all of it** and potentially delete the APC.
- Overlapping tasks can push `all_task_hours` above uptime; the `GREATEST` keeps allocation ≤ 100%.
- Savings estimate for a moved job ≈ `est_job_cost × (1 − jobs_price / apc_price)` (plus idle eliminated).

### 8.10 Configuration hygiene & policy compliance

```sql
SELECT workspace_id,
  COUNT(*)                                                          AS apc_clusters,
  COUNT_IF(delete_time IS NULL)                                     AS not_deleted,
  COUNT_IF(policy_id IS NULL)                                       AS no_policy,
  COUNT_IF(auto_termination_minutes = 0)                            AS autoterm_disabled,
  COUNT_IF(auto_termination_minutes > 60)                           AS autoterm_gt_60,
  COUNT_IF(data_security_mode IN ('LEGACY_PASSTHROUGH','LEGACY_SINGLE_USER','LEGACY_TABLE_ACL','NONE')) AS legacy_access,
  COUNT_IF(min_autoscale_workers >= 4)                              AS high_min_workers,
  COUNT_IF(worker_count >= 8 AND max_autoscale_workers IS NULL)     AS large_fixed_size,
  COUNT_IF(availability IN ('ON_DEMAND','ON_DEMAND_AZURE'))         AS on_demand_only,
  COUNT_IF(size(init_scripts) > 0)                                  AS with_init_scripts,
  COUNT_IF(is_gpu_runtime)                                          AS gpu_runtime,
  COUNT_IF(tags['cost_center'] IS NULL)                             AS untagged
FROM finops.v_apc_clusters_latest
WHERE delete_time IS NULL
GROUP BY workspace_id
ORDER BY apc_clusters DESC;
```

Weight it by money (non-compliant $):

```sql
SELECT
  CASE WHEN c.auto_termination_minutes = 0 THEN 'autoterm_disabled'
       WHEN c.auto_termination_minutes > 60 THEN 'autoterm_gt_60'
       ELSE 'autoterm_ok' END AS autoterm_bucket,
  c.policy_id IS NULL AS no_policy,
  ROUND(SUM(k.list_usd), 0) AS cost_30d
FROM finops.v_apc_cost_hourly k
JOIN finops.v_apc_clusters_latest c ON k.workspace_id = c.workspace_id AND k.cluster_id = c.cluster_id
WHERE k.usage_date >= current_date() - INTERVAL 30 DAYS
GROUP BY ALL ORDER BY cost_30d DESC;
```

### 8.11 Spot coverage (instance-minutes by availability)

```sql
WITH ev AS (
  SELECT workspace_id, instance_id, state, cluster_id, availability_type, node_type, event_time,
         LEAD(event_time) OVER (PARTITION BY workspace_id, instance_id ORDER BY event_time) AS next_time
  FROM system.compute.instance_events
  WHERE event_time >= current_date() - INTERVAL 30 DAYS
)
SELECT e.workspace_id, e.cluster_id, c.cluster_name,
       ROUND(SUM(TIMESTAMPDIFF(SECOND, e.event_time, COALESCE(e.next_time, current_timestamp()))) / 3600, 1) AS placed_hours,
       ROUND(100 * SUM(CASE WHEN e.availability_type IN ('SPOT','PREEMPTIBLE')
                            THEN TIMESTAMPDIFF(SECOND, e.event_time, COALESCE(e.next_time, current_timestamp())) END)
             / SUM(TIMESTAMPDIFF(SECOND, e.event_time, COALESCE(e.next_time, current_timestamp()))), 1) AS spot_pct
FROM ev e
JOIN finops.v_apc_clusters_latest c ON e.workspace_id = c.workspace_id AND e.cluster_id = c.cluster_id
WHERE e.state = 'INSTANCE_PLACED'
GROUP BY ALL
ORDER BY placed_hours DESC;
```

> Includes the driver. With `first_on_demand = 1`, a fully-spot-worker cluster of N nodes tops out at `(N−1)/N`.

### 8.12 Startup latency & pool idle VM time

```sql
-- Startup latency per instance (launch -> first placement)
WITH ev AS (
  SELECT workspace_id, instance_id, instance_pool_id,
         MIN(CASE WHEN state = 'INSTANCE_LAUNCHING' THEN event_time END) AS launched,
         MIN(CASE WHEN state = 'INSTANCE_PLACED'    THEN event_time END) AS placed,
         MAX(CASE WHEN state = 'INSTANCE_PLACED'    THEN cluster_id END) AS cluster_id
  FROM system.compute.instance_events
  WHERE event_time >= current_date() - INTERVAL 30 DAYS
  GROUP BY ALL
)
SELECT instance_pool_id IS NOT NULL AS from_pool,
       percentile_approx(TIMESTAMPDIFF(SECOND, launched, placed), 0.5)  AS p50_secs,
       percentile_approx(TIMESTAMPDIFF(SECOND, launched, placed), 0.95) AS p95_secs,
       COUNT(*) AS instances
FROM ev WHERE launched IS NOT NULL AND placed IS NOT NULL
GROUP BY ALL;
```

```sql
-- Idle (READY, unplaced) VM hours in pools = cloud cost with no work
WITH ev AS (
  SELECT workspace_id, instance_id, instance_pool_id, state, event_time,
         LEAD(event_time) OVER (PARTITION BY workspace_id, instance_id ORDER BY event_time) AS next_time
  FROM system.compute.instance_events
  WHERE event_time >= current_date() - INTERVAL 30 DAYS AND instance_pool_id IS NOT NULL
)
SELECT workspace_id, instance_pool_id,
       ROUND(SUM(TIMESTAMPDIFF(SECOND, event_time, COALESCE(next_time, current_timestamp()))) / 3600, 1) AS idle_ready_vm_hours
FROM ev WHERE state = 'INSTANCE_READY'
GROUP BY ALL ORDER BY idle_ready_vm_hours DESC;
```

### 8.13 Audit-log analytics (users, human vs machine activity)

Discovery first (confirms param key names in your account):

```sql
SELECT service_name, action_name, map_keys(request_params) AS param_keys, COUNT(*) AS n
FROM system.access.audit
WHERE event_date >= current_date() - INTERVAL 7 DAYS
  AND service_name IN ('clusters', 'notebook', 'jobs')
GROUP BY ALL
ORDER BY n DESC;
```

Users per cluster and last human attach:

```sql
SELECT CAST(workspace_id AS STRING) AS workspace_id,
       request_params['clusterId']        AS cluster_id,
       COUNT(DISTINCT user_identity.email) AS distinct_users_90d,
       MAX(event_time)                     AS last_attach_time,
       DATEDIFF(current_date(), MAX(event_date)) AS days_since_last_attach
FROM system.access.audit
WHERE service_name = 'notebook' AND action_name = 'attachNotebook'
  AND event_date >= current_date() - INTERVAL 90 DAYS
GROUP BY ALL;
```

Clusters that are spending money but have **no human attach** (BI/JDBC/orchestrator/zombie candidates):

```sql
WITH attaches AS (
  SELECT CAST(workspace_id AS STRING) AS workspace_id, request_params['clusterId'] AS cluster_id
  FROM system.access.audit
  WHERE service_name = 'notebook' AND action_name = 'attachNotebook'
    AND event_date >= current_date() - INTERVAL 30 DAYS
  GROUP BY ALL
)
SELECT k.workspace_id, k.cluster_id, ROUND(SUM(k.list_usd), 0) AS cost_30d
FROM finops.v_apc_cost_hourly k
LEFT ANTI JOIN attaches a ON k.workspace_id = a.workspace_id AND k.cluster_id = a.cluster_id
WHERE k.usage_date >= current_date() - INTERVAL 30 DAYS
GROUP BY ALL
ORDER BY cost_30d DESC;
```

Cluster restarts/creates by actor (find automation restarting clusters):

```sql
SELECT action_name, user_identity.email AS actor, user_agent, COUNT(*) AS n
FROM system.access.audit
WHERE service_name = 'clusters' AND action_name IN ('create', 'start', 'restart', 'edit', 'resize', 'delete')
  AND event_date >= current_date() - INTERVAL 30 DAYS
GROUP BY ALL
ORDER BY n DESC;
```

With verbose audit logs on — command volume and runtime per user (human activity intensity):

```sql
SELECT user_identity.email AS user, event_date,
       COUNT(*) AS commands,
       ROUND(SUM(CAST(request_params['executionTime'] AS DOUBLE)) / 3600, 2) AS exec_hours  -- verify unit (seconds) via a sample
FROM system.access.audit
WHERE service_name = 'notebook' AND action_name = 'runCommand'
  AND event_date >= current_date() - INTERVAL 30 DAYS
GROUP BY ALL;
```

### 8.14 Off-hours & weekend spend

```sql
SELECT
  CASE WHEN dayofweek(from_utc_timestamp(hour_ts, 'America/New_York')) IN (1, 7) THEN 'weekend'
       WHEN hour(from_utc_timestamp(hour_ts, 'America/New_York')) NOT BETWEEN 7 AND 19 THEN 'weeknight'
       ELSE 'business_hours' END AS period,
  ROUND(SUM(list_usd), 0) AS cost_30d
FROM finops.v_apc_cost_hourly
WHERE usage_date >= current_date() - INTERVAL 30 DAYS
GROUP BY ALL;
```

(Set the time zone per region/team.)

### 8.15 Photon on APC — candidates to switch off

```sql
WITH photon AS (
  SELECT workspace_id, cluster_id, SUM(list_usd) AS photon_cost_30d
  FROM finops.v_apc_cost_hourly
  WHERE is_photon AND usage_date >= current_date() - INTERVAL 30 DAYS
  GROUP BY ALL
),
util AS (
  SELECT workspace_id, cluster_id,
         AVG(CASE WHEN is_idle THEN 1 ELSE 0 END) AS idle_ratio,
         percentile_approx(worker_cpu_avg, 0.5) FILTER (WHERE NOT is_idle) AS median_active_worker_cpu
  FROM finops.v_apc_cluster_minute
  WHERE minute_ts >= current_date() - INTERVAL 30 DAYS
  GROUP BY ALL
)
SELECT p.*, u.idle_ratio, u.median_active_worker_cpu, c.is_ml_runtime, c.owned_by
FROM photon p
LEFT JOIN util u USING (workspace_id, cluster_id)
LEFT JOIN finops.v_apc_clusters_latest c USING (workspace_id, cluster_id)
ORDER BY photon_cost_30d DESC;
```

High idle ratio or ML runtime + Photon = likely paying the Photon premium for no speedup. A/B test before/after.

### 8.16 GPU clusters on APC

```sql
SELECT c.workspace_id, c.cluster_id, c.cluster_name, c.owned_by, c.worker_node_type,
       GREATEST(COALESCE(nw.gpu_count, 0), COALESCE(nd.gpu_count, 0)) AS gpus_per_node,
       c.auto_termination_minutes,
       ROUND(SUM(k.list_usd), 0) AS cost_30d
FROM finops.v_apc_clusters_latest c
LEFT JOIN system.compute.node_types nw ON nw.node_type = c.worker_node_type
LEFT JOIN system.compute.node_types nd ON nd.node_type = c.driver_node_type
JOIN finops.v_apc_cost_hourly k ON k.workspace_id = c.workspace_id AND k.cluster_id = c.cluster_id
WHERE GREATEST(COALESCE(nw.gpu_count, 0), COALESCE(nd.gpu_count, 0)) > 0
  AND k.usage_date >= current_date() - INTERVAL 30 DAYS
GROUP BY ALL
ORDER BY cost_30d DESC;
```

Combine with 8.6 idle (CPU-idle is a reasonable proxy: a GPU cluster with idle CPUs is almost always an idle GPU). Candidates → AI Runtime, ≤ 20 min auto-termination.

### 8.17 Consolidation candidates (personal clusters per team overlapping in time)

```sql
WITH m AS (
  SELECT c.tags['team'] AS team, m.minute_ts,
         COUNT(DISTINCT m.cluster_id) AS concurrent_clusters,
         SUM(m.nodes) AS provisioned_nodes,
         SUM(CASE WHEN NOT m.is_idle THEN m.nodes ELSE 0 END) AS busy_nodes
  FROM finops.v_apc_cluster_minute m
  JOIN finops.v_apc_clusters_latest c ON m.workspace_id = c.workspace_id AND m.cluster_id = c.cluster_id
  WHERE c.data_security_mode = 'SINGLE_USER' AND m.minute_ts >= current_date() - INTERVAL 30 DAYS
  GROUP BY ALL
)
SELECT team,
       percentile_approx(concurrent_clusters, 0.95) AS p95_concurrent_clusters,
       percentile_approx(provisioned_nodes, 0.95)   AS p95_provisioned_nodes,
       percentile_approx(busy_nodes, 0.95)          AS p95_busy_nodes,
       ROUND(percentile_approx(busy_nodes, 0.95) / NULLIF(percentile_approx(provisioned_nodes, 0.95), 0), 2) AS busy_ratio
FROM m GROUP BY team ORDER BY p95_provisioned_nodes DESC;
```

A low `busy_ratio` with many concurrent personal clusters → one Standard-mode team cluster autoscaling to ≈ `p95_busy_nodes` (or serverless notebooks).

### 8.18 Instance generation & runtime currency

```sql
SELECT worker_node_type, dbr_version, COUNT(*) AS clusters
FROM finops.v_apc_clusters_latest
WHERE delete_time IS NULL
GROUP BY ALL ORDER BY clusters DESC;
```

Maintain a small reference table `finops.ref_node_generation(node_type, generation, recommended_replacement)` and join to quantify node-hours on old generations.

### 8.19 ⭐ Opportunity roll-up (single prioritized list)

```sql
-- Build each opportunity as a view first (outputs of 8.6, 8.8, 8.9, 8.15, 8.16), then:
SELECT 'jobs_on_apc' AS lever, SUM(est_job_cost_30d) * 12 AS addressable_annual,
       0.65 AS assumed_reduction  -- replace with 1 - jobs_price/apc_price from §3.3
FROM finops.opp_jobs_on_apc
UNION ALL
SELECT 'idle', SUM(idle_cost_30d) * 12, 0.60 FROM finops.opp_idle
UNION ALL
SELECT 'oversized', SUM(cost_30d) * 12, 0.30 FROM finops.opp_rightsizing WHERE sizing_verdict LIKE 'OVERSIZED%'
UNION ALL
SELECT 'driver_bound', SUM(cost_30d) * 12, 0.50 FROM finops.opp_rightsizing WHERE sizing_verdict LIKE 'DRIVER_BOUND%'
UNION ALL
SELECT 'photon_off', SUM(photon_cost_30d) * 12, 0.30 FROM finops.opp_photon WHERE idle_ratio > 0.5;
-- Note: levers overlap; apply in sequence (placement -> idle -> sizing -> pricing), not additively.
```

---

## 9. Savings Model for the $40M Baseline

### 9.1 Method (replace assumptions with your query outputs)

Apply levers **sequentially**, because they overlap (a job moved off APC no longer has idle time to remove):

```
Step 1  Placement   : S1 = JobsOnAPC$ × (1 − P_jobs/P_apc)          [+ BI→SQL, GPU→AI Runtime]
Step 2  Idle        : S2 = (Remaining APC$ × IdleShare) × CaptureRate
Step 3  Right-size  : S3 = (Remaining APC$ after S2) × SizingReduction
Step 4  Pricing     : S4 = Photon-off + spot (VM) + generation upgrades + commits
Total               = S1 + S2 + S3 + S4
```

Inputs come from: §3.3 (price ratio), §8.9 (JobsOnAPC$), §8.6 (IdleShare), §8.8 (sizing verdicts), §8.15 (Photon), §8.11 (spot coverage).

### 9.2 Illustrative scenarios (DBU spend only — assumptions, not measurements)

| Step | Conservative | Moderate | Aggressive |
|---|---|---|---|
| Jobs/orchestrated share of APC | 15% ($6.0M) | 25% ($10.0M) | 35% ($14.0M) |
| Net reduction on moved work | 55% → **$3.3M** | 60% → **$6.0M** | 65% → **$9.1M** |
| Remaining interactive APC | $34.0M | $30.0M | $26.0M |
| Idle share of remaining | 25% | 35% | 40% |
| Idle captured | 50% → **$4.25M** | 60% → **$6.3M** | 70% → **$7.28M** |
| Right-sizing on remainder | 8% → **$2.38M** | 15% → **$3.56M** | 20% → **$3.74M** |
| Photon/generation/misc | 1% → **$0.27M** | 5% → **$1.0M** | 8% → **$1.2M** |
| **Total annual savings** | **≈ $10.2M (25%)** | **≈ $16.9M (42%)** | **≈ $21.3M (53%)** |

Notes:
- "Net reduction on moved work" already nets out the new Jobs/serverless cost that replaces APC.
- Idle captured via serverless notebooks nets out the higher serverless DBU rate (serverless bundles VM cost, so compare against APC DBU **+** VM).
- If the $40M excludes cloud VMs, idle elimination, right-sizing and spot produce **additional** VM savings on top of this table.
- Re-baseline monthly; report realized savings as *(baseline cost per unit of work − current)*, not just absolute spend, so growth doesn't mask savings.

### 9.3 Realized-savings tracking

| Metric | Formula |
|---|---|
| APC run-rate | trailing-30-day APC $ × 12 |
| Migrated workload savings | Σ (pre-migration 30-day cost − post-migration 30-day cost on new SKU) per moved job |
| Idle $ trend | §8.6 weekly |
| Policy coverage | % APC $ under policies |
| Unit cost | APC $ per active user, per notebook-hour (verbose audit) |

---

## 10. Governance: Policies, Tags, Chargeback

### 10.1 Persona-based compute policies

| Persona policy | Who | Key constraints |
|---|---|---|
| **Personal / Explore (Single node)** | Everyone by default | Single node, small/medium node allowlist, autoterm fixed 30, Photon off, tags required |
| **Team Shared (Standard mode)** | Analysts, DE dev | `USER_ISOLATION`, autoscale min 1 / max ≤ 10, autoterm 30–60, spot workers, `dbus_per_hour` cap |
| **DS-CPU** | Data scientists | ML runtime, memory-optimized allowlist, autoscale max ≤ 8, autoterm ≤ 45, `dbus_per_hour` cap |
| **DS-GPU (exception)** | Approved DS/ML engineers | GPU allowlist, single node or small, autoterm ≤ 20, mandatory project tag; prefer AI Runtime |
| **Large Interactive (exception)** | Approved, time-boxed | Higher cap, mandatory justification tag, expiry review |
| **Streaming exception** | Rare | autoterm 0 allowed only here; owner + review date tag |

Supporting controls:
- Remove the **unrestricted cluster creation** entitlement from users/groups; grant **CAN_USE** on persona policies only.
- Set `max_clusters_per_user` on personal policies (e.g., 1–2).
- Use policy **families** + overrides for consistency; manage with Terraform (`databricks_cluster_policy`) or Asset Bundles.
- Prevent jobs from targeting APC: CI checks on bundles/job JSON rejecting `existing_cluster_id`; review `SUBMIT_RUN` sources monthly (§8.9).

### 10.2 Tagging standard

Mandatory custom tags (enforced via policy `custom_tags.<key>`):
`cost_center`, `team`, `env` (dev/test/prod), `use_case` (explore / ds-train / de-dev / bi / streaming), `owner_email` (if `owned_by` is a service principal), `expiry` (for exceptions).

Tags flow to `system.billing.usage.custom_tags` and to cloud VM tags → join both cost streams.

### 10.3 Chargeback / showback

- Monthly statement per cost center: APC $ (list → net), idle $, jobs-on-APC $, top clusters, compliance score.
- Owner-level "waste receipts": each week, top idle clusters with $ and a one-click fix link.
- Budget alerts per workspace/team on APC run-rate.

---

## 11. Automation: Detection → Action Loop

### 11.1 Daily pipeline (run as a **job on Jobs or serverless compute**, never on APC)

1. Refresh `finops.apc_cluster_minute` incrementally (last 2 days, merge).
2. Recompute opportunity tables (`opp_idle`, `opp_jobs_on_apc`, `opp_rightsizing`, `opp_photon`, `opp_gpu`).
3. Publish an AI/BI dashboard (§15.3) and email/Slack owner digests.
4. Open tickets for the top-N items (job migrations need human change).

### 11.2 Idle-killer (catches what auto-termination misses)

Logic: if a RUNNING all-purpose cluster has been idle (per §8.5 definition) for ≥ `GRACE_MIN` in the latest available `node_timeline` data, is not tagged `idle_kill=exempt`, then notify the owner and terminate on the next pass.

```python
# Run per workspace as a scheduled job (serverless or small job cluster).
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.compute import State

GRACE_MIN = 90          # minutes of continuous idle in node_timeline before action
DRY_RUN = True          # start in report-only mode

w = WorkspaceClient()
ws_id = str(w.get_workspace_id())

idle = spark.sql(f"""
  WITH recent AS (
    SELECT cluster_id, minute_ts, is_idle
    FROM finops.v_apc_cluster_minute
    WHERE workspace_id = '{ws_id}'
      AND minute_ts >= current_timestamp() - INTERVAL 6 HOURS
  ),
  last_busy AS (
    SELECT cluster_id,
           MAX(CASE WHEN NOT is_idle THEN minute_ts END) AS last_busy_ts,
           MAX(minute_ts) AS last_seen_ts
    FROM recent GROUP BY cluster_id
  )
  SELECT cluster_id,
         TIMESTAMPDIFF(MINUTE, COALESCE(last_busy_ts, current_timestamp() - INTERVAL 6 HOURS), last_seen_ts) AS idle_min
  FROM last_busy
""").toPandas()
idle_map = dict(zip(idle.cluster_id, idle.idle_min))

for c in w.clusters.list():
    if c.state != State.RUNNING or c.cluster_source is None or c.cluster_source.value not in ("UI", "API"):
        continue
    tags = c.custom_tags or {}
    if tags.get("idle_kill") == "exempt":
        continue
    idle_min = idle_map.get(c.cluster_id, 0)
    if idle_min >= GRACE_MIN:
        print(f"{'[DRY]' if DRY_RUN else ''} terminate {c.cluster_id} {c.cluster_name} owner={c.creator_user_name} idle={idle_min}m")
        if not DRY_RUN:
            w.clusters.delete(cluster_id=c.cluster_id)   # 'delete' = terminate; config is retained
```

Notes: `node_timeline` is not real-time — choose a grace window comfortably above its delivery delay; notify before enforcing; exempt streaming clusters explicitly (and migrate them, §4 P11).

### 11.3 Other automations

- **Policy drift**: weekly list of clusters with `policy_id IS NULL` or legacy access mode → owner tickets.
- **Zombie sweeper**: clusters with no human attach for 60 days and not pinned → notify, then permanently delete after 14 days.
- **Jobs-on-APC detector**: new entries in §8.9 trigger a PR/issue against the job's repo.
- **Pool right-sizer**: pools with high `idle_ready_vm_hours` → lower `min_idle_instances`.

---

## 12. AI/ML & Data Science Specific Playbook

Data scientists are usually the largest APC consumers after misplaced jobs. Target behaviors:

| Stage | Recommended compute | Why |
|---|---|---|
| Exploration / EDA on samples | Serverless notebook or small single-node | No idle burn, instant start |
| Feature engineering at scale | Standard-mode shared cluster (autoscale 1–N) or job | Spark work, shareable |
| pandas/sklearn on < ~100 GB | Single-node, memory-optimized driver | Workers would sit idle |
| Distributed CPU training / HPO | Develop small; **run as job** on Jobs compute | All-purpose rate only for interactive part |
| Deep learning / fine-tuning | **AI Runtime** (serverless A10/H100) interactively; jobs for long runs | No idle GPU cluster |
| Batch scoring / embeddings | Jobs / batch inference / `ai_query` | Non-interactive |
| Online serving | Model Serving | Never an always-on APC |

Practices to coach:
- Detach and terminate when done; don't leave training loops or streams running in a notebook.
- Use `TABLESAMPLE`/`limit` in exploration; avoid `toPandas()` on full tables.
- Size Hyperopt/Optuna/Ray parallelism to cores; use early stopping.
- Track experiments with MLflow (enable system metrics logging to capture GPU utilization, which system tables don't provide).
- Use the ML runtime only when needed (heavier image, slower start); pin library versions in environments instead of init scripts.
- Do CPU-only work (cloning repos, data prep, EDA) on CPU compute, not GPU sessions.

Change management: publish a one-page "which compute should I use?" decision tree; make cost visible per user weekly; offer office hours; migrate with templates (job YAML / bundles) so teams can self-serve.

---

## 13. Implementation Roadmap

| Phase | Timeline | Actions | Exit criteria |
|---|---|---|---|
| **0. Instrument** | Weeks 0–2 | Enable system schemas in all regions; grant FinOps access; build `finops` views/tables (§8.1–8.5); turn on verbose audit logs; agree tag standard; confirm $40M composition (DBU vs VM, list vs net) | Baseline dashboard live; top-100 clusters known |
| **1. Quick wins** | Weeks 2–6 | Policy-enforce auto-termination ≤ 60 (≤ 20 GPU); forbid autoterm 0 except exceptions; nudge top idle owners; kill zombies; Photon off on idle-heavy APC; lower min workers; spot workers with on-demand driver | Idle $ ↓ 30%+; policy coverage > 80% of APC $ |
| **2. Placement** | Weeks 4–12 | Migrate jobs-on-APC (start with highest $); fix ADF/Airflow submit configs; move BI/JDBC to SQL warehouses; streaming → jobs/pipelines | Jobs-on-APC $ ↓ 80% |
| **3. Re-platform interactive** | Months 2–4 | Persona policies; remove unrestricted creation; serverless notebooks for bursty users; AI Runtime for GPU; team shared clusters replace personal ones | APC share of compute trending down; users/cluster ↑ |
| **4. Optimize & lock in** | Months 3–6 | Right-size from §8.8; instance generation upgrades; reserved capacity for remaining baseline; DBCU negotiation; idle-killer enforcing | Target savings realized; monthly governance review |
| **5. Sustain** | Ongoing | Weekly owner digests, monthly chargeback, quarterly policy review, regression alerts | Savings retained under growth |

---

## 14. Known Limitations & Gotchas

1. **Jobs on APC have no `job_id` in billing** — attribution requires lakeflow timeline joins and is an estimate when workloads share a cluster.
2. **`node_timeline`** excludes serverless/SQL warehouses, may miss nodes alive < 10 minutes, has no GPU metrics, and is not real-time.
3. **Regional vs global**: billing is global; compute, lakeflow and most audit records are regional — run per region and union.
4. **Billing corrections**: always `SUM(usage_quantity)`; don't filter to `ORIGINAL` only.
5. **List vs contract price**: `list_prices` is list; use `pricing.effective_list.default` and apply your discount.
6. **Time-valid price join** is mandatory or you'll multiply rows.
7. **`identity_metadata.run_as` for APC = creator**, not owner; use `clusters.owned_by` at the time of usage.
8. **Clusters deleted before Oct 23, 2023** are missing from `system.compute.clusters`.
9. **Public Preview tables** (`compute.*` instance tables, `query.history`) can change schema — pin queries in version control and test after releases.
10. **Driver background CPU** is non-zero when idle — don't use 0% as the idle threshold.
11. **`query.history` does not cover classic APC** — APC SQL performance must come from Spark UI/event logs.
12. **Timeline slicing** changed to clock-hour alignment on Jan 19, 2026 — sum slices per run, never count rows as runs.
13. **Serverless isn't automatically cheaper**: for steady, fully-utilized, all-day work, a well-sized classic job cluster with spot/RI can be cheaper. Serverless wins on bursty/idle-prone work.
14. **Audit `request_params` keys** differ per event — use the discovery query (§8.13).

---

## 15. Appendix

### 15.1 Policy template — Team Shared (AWS)

```json
{
  "cluster_type":               { "type": "fixed", "value": "all-purpose" },
  "data_security_mode":         { "type": "fixed", "value": "USER_ISOLATION" },
  "spark_version":              { "type": "unlimited", "defaultValue": "auto:latest-lts" },
  "runtime_engine":             { "type": "fixed", "value": "STANDARD" },
  "autotermination_minutes":    { "type": "range", "minValue": 10, "maxValue": 60, "defaultValue": 30 },
  "dbus_per_hour":              { "type": "range", "maxValue": 40 },
  "autoscale.min_workers":      { "type": "range", "maxValue": 2, "defaultValue": 1 },
  "autoscale.max_workers":      { "type": "range", "maxValue": 10, "defaultValue": 4 },
  "node_type_id":               { "type": "allowlist", "values": ["<m-family-xlarge>", "<r-family-xlarge>", "<r-family-2xlarge>"], "defaultValue": "<r-family-xlarge>" },
  "driver_node_type_id":        { "type": "allowlist", "values": ["<m-family-xlarge>", "<r-family-xlarge>", "<r-family-2xlarge>"] },
  "aws_attributes.availability":    { "type": "fixed", "value": "SPOT_WITH_FALLBACK" },
  "aws_attributes.first_on_demand": { "type": "fixed", "value": 1 },
  "enable_elastic_disk":        { "type": "fixed", "value": true },
  "custom_tags.cost_center":    { "type": "unlimited", "isOptional": false },
  "custom_tags.team":           { "type": "unlimited", "isOptional": false },
  "custom_tags.use_case":       { "type": "allowlist", "values": ["explore", "de-dev", "ds-feature", "bi"] }
}
```

Azure equivalents: `azure_attributes.availability` = `SPOT_WITH_FALLBACK_AZURE`, `azure_attributes.first_on_demand` = 1, `azure_attributes.spot_bid_max_price` = -1. Replace `<…>` placeholders with your approved current-generation instance types.

### 15.2 Policy template — Personal single node

```json
{
  "cluster_type":                              { "type": "fixed", "value": "all-purpose" },
  "data_security_mode":                        { "type": "fixed", "value": "SINGLE_USER" },
  "num_workers":                               { "type": "fixed", "value": 0, "hidden": true },
  "spark_conf.spark.databricks.cluster.profile": { "type": "fixed", "value": "singleNode", "hidden": true },
  "spark_conf.spark.master":                   { "type": "fixed", "value": "local[*]", "hidden": true },
  "custom_tags.ResourceClass":                 { "type": "fixed", "value": "SingleNode", "hidden": true },
  "autotermination_minutes":                   { "type": "range", "minValue": 10, "maxValue": 45, "defaultValue": 30 },
  "runtime_engine":                            { "type": "fixed", "value": "STANDARD" },
  "node_type_id":                              { "type": "allowlist", "values": ["<m-family-xlarge>", "<r-family-2xlarge>", "<r-family-4xlarge>"], "defaultValue": "<m-family-xlarge>" },
  "custom_tags.cost_center":                   { "type": "unlimited", "isOptional": false }
}
```

Set `max_clusters_per_user` = 1 on this policy. (Newer cluster APIs also express single node via `is_single_node`; keep whichever form your workspace's policy UI generates.)

### 15.3 Dashboard specification (AI/BI dashboard on system tables)

| Page | Visuals | Source queries |
|---|---|---|
| Executive | APC run-rate, APC share of compute, realized savings, compliance score | 8.3, 9.3 |
| Waste | Idle $ by team, top idle clusters, active-but-idle streaks, off-hours $ | 8.6, 8.7, 8.14 |
| Placement | Jobs-on-APC by job/team, SUBMIT_RUN sources, no-human-attach clusters | 8.9, 8.13 |
| Sizing | Sizing verdicts, driver-bound list, autoscale floor burden | 8.8 |
| Pricing | Spot coverage, Photon on APC, GPU clusters, pool idle VM hours | 8.11, 8.12, 8.15, 8.16 |
| Governance | Policy coverage, autoterm distribution, legacy access, untagged $ | 8.10 |
| Owner view (filter by `owned_by`) | Personal waste receipt | all |

### 15.4 Reference documentation

- Compute system tables: `docs.databricks.com/admin/system-tables/compute`
- Billable usage table: `docs.databricks.com/admin/system-tables/billing`
- Pricing table: `docs.databricks.com/admin/system-tables/pricing`
- Jobs (lakeflow) tables: `docs.databricks.com/admin/system-tables/jobs`
- Audit log table & verbose audit logs: `docs.databricks.com/admin/system-tables/audit-logs`, `.../account-settings/verbose-logs`
- Query history: `docs.databricks.com/admin/system-tables/query-history`
- Manage compute / auto-termination: `docs.databricks.com/compute/clusters-manage`
- Compute policy reference: `docs.databricks.com/admin/clusters/policy-definition`
- Cost optimization best practices: `docs.databricks.com/lakehouse-architecture/cost-optimization/best-practices`
- AI Runtime (serverless GPU): `docs.databricks.com/machine-learning/ai-runtime/`
