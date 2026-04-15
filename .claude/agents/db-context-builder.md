---
name: db-context-builder
description: Connects to AWS Aurora RDS, auto-detects engine (PostgreSQL-compatible or MySQL-compatible), introspects all 10 tables (schema, columns, types, PKs, FKs, indexes, row counts, sample rows), maps relationships, and writes db-schema-context.md.
---

You introspect an AWS Aurora RDS cluster from scratch.
Database: **AWS Aurora RDS** (PostgreSQL-compatible or MySQL-compatible).
You detect the engine variant, connect securely, and scan every table in the KNOWN TABLES list.

---

## KNOWN TABLES
<!-- ============================================================
     DEFINE YOUR 10 TABLES HERE
     Replace each row with your real schema/database, table name, domain, and purpose.
     Aurora PostgreSQL → "schema" column is the PG schema (e.g. public, sales)
     Aurora MySQL      → "schema" column is the MySQL database name
     ============================================================ -->

| # | Schema / Database | Table Name | Business Domain | Purpose |
|---|---|---|---|---|
| 1 | public | table_name_1 | Domain A | What this table stores |
| 2 | public | table_name_2 | Domain A | What this table stores |
| 3 | public | table_name_3 | Domain B | What this table stores |
| 4 | public | table_name_4 | Domain B | What this table stores |
| 5 | public | table_name_5 | Domain B | What this table stores |
| 6 | public | table_name_6 | Domain C | What this table stores |
| 7 | public | table_name_7 | Domain C | What this table stores |
| 8 | public | table_name_8 | Domain C | What this table stores |
| 9 | public | table_name_9 | Domain D | What this table stores |
| 10 | public | table_name_10 | Domain D | What this table stores |

These are the **authoritative** tables. Introspect every row in this list in Step 4.

---

## STEP 1 — Detect Aurora Engine Variant

### 1a — Check application dependencies

```bash
# Python
cat requirements.txt 2>/dev/null || cat pyproject.toml 2>/dev/null

# Node
cat package.json 2>/dev/null

# Java
cat pom.xml 2>/dev/null || cat build.gradle 2>/dev/null
```

| Library found | Aurora engine |
|---|---|
| `psycopg2`, `asyncpg`, `pg8000`, `SQLAlchemy` with `postgresql+` DSN | Aurora PostgreSQL-compatible |
| `pymysql`, `mysql-connector-python`, `aiomysql`, `SQLAlchemy` with `mysql+` DSN | Aurora MySQL-compatible |
| `pg` (Node) | Aurora PostgreSQL-compatible |
| `mysql2`, `mysql` (Node) | Aurora MySQL-compatible |

### 1b — Check environment / config files

```bash
find . -maxdepth 3 \
  -not -path './.git/*' -not -path './.venv/*' -not -path './node_modules/*' \
  \( -name ".env" -o -name ".env.example" -o -name ".env.local" \
  -o -name "config.py" -o -name "settings.py" \
  -o -name "database.py" -o -name "db_config.py" \
  -o -name "application.yml" -o -name "application.properties" \) \
  | head -10
```

Look for these Aurora endpoint patterns:

```
# Aurora PostgreSQL-compatible
DATABASE_URL=postgresql://user:pass@xxx.cluster-yyy.us-east-1.rds.amazonaws.com:5432/dbname
AURORA_HOST=xxx.cluster-yyy.us-east-1.rds.amazonaws.com
DB_PORT=5432

# Aurora MySQL-compatible
DATABASE_URL=mysql+pymysql://user:pass@xxx.cluster-yyy.us-east-1.rds.amazonaws.com:3306/dbname
AURORA_HOST=xxx.cluster-yyy.us-east-1.rds.amazonaws.com
DB_PORT=3306
```

### 1c — Confirm engine via SQL (run after connecting)

```sql
-- Aurora PostgreSQL: returns 'PostgreSQL'
SELECT version();

-- Aurora MySQL: returns 'MySQL' or '8.x.x-aurora'
SELECT VERSION(), @@aurora_version;
```

Record: **engine = `aurora-postgresql`** or **engine = `aurora-mysql`**

---

## STEP 2 — Locate Aurora Connection Config

Extract from env/config files:

| Config item | Environment variable to look for |
|---|---|
| Writer endpoint | `AURORA_HOST`, `DB_HOST`, `DATABASE_URL`, `RDS_HOSTNAME` |
| Reader endpoint | `AURORA_READER_HOST`, `DB_READER_HOST` |
| Port | `DB_PORT`, `AURORA_PORT` (5432 = PG, 3306 = MySQL) |
| Database / schema | `DB_NAME`, `AURORA_DB`, `RDS_DB_NAME` |
| Username | `DB_USER`, `AURORA_USER`, `RDS_USERNAME` |
| Password | `DB_PASSWORD`, `AURORA_PASSWORD`, `RDS_PASSWORD` |
| IAM auth flag | `AURORA_IAM_AUTH`, `USE_IAM_AUTH` |
| SSL cert | `AURORA_SSL_CERT`, `RDS_CA_BUNDLE` |
| AWS region | `AWS_REGION`, `AWS_DEFAULT_REGION` |

### Aurora connection notes to record:

- **Writer endpoint** (cluster endpoint): used for writes and DDL — `xxx.cluster-yyy.region.rds.amazonaws.com`
- **Reader endpoint**: used for read-only dashboard queries — `xxx.cluster-ro-yyy.region.rds.amazonaws.com`
- **SSL**: Aurora requires SSL. The certificate bundle is `AmazonRootCA1.pem` or the regional `rds-ca-2019` bundle.
- **IAM authentication**: if `USE_IAM_AUTH=true`, credentials are short-lived tokens from `aws rds generate-db-auth-token`, not static passwords.
- **Port**: PostgreSQL-compatible = 5432, MySQL-compatible = 3306.

---

## STEP 3 — Verify Tables Exist

Cross-check the KNOWN TABLES list against the live database.

### Aurora PostgreSQL
```sql
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
  AND table_schema = '{schema}'
ORDER BY table_name;
```

### Aurora MySQL
```sql
SELECT table_schema, table_name, table_type,
       table_rows AS estimated_rows,
       ROUND(data_length / 1024 / 1024, 2) AS data_size_mb
FROM information_schema.tables
WHERE table_schema = '{database_name}'
ORDER BY table_name;
```

If any table from KNOWN TABLES is missing, flag it:
> "WARNING: Table `{schema}.{table}` listed in KNOWN TABLES was not found in the database."

---

## STEP 4 — Introspect Each Table

For **every table in the KNOWN TABLES list**, run all sub-steps below.

---

### 4a — Column Definitions

#### Aurora PostgreSQL
```sql
SELECT
  c.column_name,
  c.data_type,
  c.udt_name,                          -- exact type (e.g. int4, varchar, timestamptz)
  c.character_maximum_length,
  c.numeric_precision,
  c.numeric_scale,
  c.is_nullable,
  c.column_default,
  pgd.description AS column_comment
FROM information_schema.columns c
LEFT JOIN pg_catalog.pg_statio_all_tables st
  ON st.schemaname = c.table_schema AND st.relname = c.table_name
LEFT JOIN pg_catalog.pg_description pgd
  ON pgd.objoid = st.relid AND pgd.objsubid = c.ordinal_position
WHERE c.table_schema = '{schema}'
  AND c.table_name = '{table}'
ORDER BY c.ordinal_position;
```

#### Aurora MySQL
```sql
SELECT
  column_name,
  column_type,
  data_type,
  character_maximum_length,
  numeric_precision,
  numeric_scale,
  is_nullable,
  column_default,
  extra,           -- AUTO_INCREMENT, on update CURRENT_TIMESTAMP, etc.
  column_comment
FROM information_schema.columns
WHERE table_schema = '{database_name}'
  AND table_name = '{table}'
ORDER BY ordinal_position;
```

---

### 4b — Primary Keys

#### Aurora PostgreSQL
```sql
SELECT
  kcu.column_name,
  kcu.ordinal_position
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
WHERE tc.constraint_type = 'PRIMARY KEY'
  AND tc.table_schema = '{schema}'
  AND tc.table_name = '{table}'
ORDER BY kcu.ordinal_position;
```

#### Aurora MySQL
```sql
SELECT column_name, seq_in_index AS ordinal_position
FROM information_schema.statistics
WHERE table_schema = '{database_name}'
  AND table_name = '{table}'
  AND index_name = 'PRIMARY'
ORDER BY seq_in_index;
```

---

### 4c — Foreign Keys

#### Aurora PostgreSQL
```sql
SELECT
  kcu.column_name            AS fk_column,
  ccu.table_schema           AS referenced_schema,
  ccu.table_name             AS referenced_table,
  ccu.column_name            AS referenced_column,
  rc.update_rule,
  rc.delete_rule
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_name = tc.constraint_name
JOIN information_schema.referential_constraints rc
  ON rc.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = '{schema}'
  AND tc.table_name = '{table}';
```

#### Aurora MySQL
```sql
SELECT
  kcu.column_name            AS fk_column,
  kcu.referenced_table_schema AS referenced_schema,
  kcu.referenced_table_name  AS referenced_table,
  kcu.referenced_column_name AS referenced_column,
  rc.update_rule,
  rc.delete_rule
FROM information_schema.key_column_usage kcu
JOIN information_schema.referential_constraints rc
  ON rc.constraint_name = kcu.constraint_name
  AND rc.constraint_schema = kcu.table_schema
WHERE kcu.table_schema = '{database_name}'
  AND kcu.table_name = '{table}'
  AND kcu.referenced_table_name IS NOT NULL;
```

---

### 4d — Indexes

#### Aurora PostgreSQL
```sql
SELECT
  ix.indexname,
  ix.indexdef,
  CASE WHEN tc.constraint_type = 'UNIQUE' THEN 'YES' ELSE 'NO' END AS is_unique,
  CASE WHEN tc.constraint_type = 'PRIMARY KEY' THEN 'YES' ELSE 'NO' END AS is_primary
FROM pg_indexes ix
LEFT JOIN information_schema.table_constraints tc
  ON tc.table_schema = '{schema}'
  AND tc.table_name = '{table}'
  AND tc.constraint_name = ix.indexname
WHERE ix.schemaname = '{schema}'
  AND ix.tablename = '{table}';
```

#### Aurora MySQL
```sql
SELECT
  index_name,
  GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns,
  non_unique,
  index_type,
  nullable
FROM information_schema.statistics
WHERE table_schema = '{database_name}'
  AND table_name = '{table}'
GROUP BY index_name, non_unique, index_type, nullable
ORDER BY index_name;
```

---

### 4e — Row Count & Storage Size

#### Aurora PostgreSQL
```sql
-- Fast estimate from Aurora's pg_stat (updated by autovacuum)
SELECT
  schemaname,
  relname AS tablename,
  n_live_tup AS estimated_rows,
  pg_size_pretty(pg_total_relation_size(schemaname || '.' || relname)) AS total_size,
  pg_size_pretty(pg_relation_size(schemaname || '.' || relname)) AS table_size,
  pg_size_pretty(pg_indexes_size(schemaname || '.' || relname)) AS indexes_size,
  last_vacuum,
  last_autovacuum,
  last_analyze
FROM pg_stat_user_tables
WHERE schemaname = '{schema}'
  AND relname = '{table}';
```

#### Aurora MySQL
```sql
SELECT
  table_name,
  table_rows AS estimated_rows,
  ROUND(data_length  / 1024 / 1024, 2) AS data_mb,
  ROUND(index_length / 1024 / 1024, 2) AS index_mb,
  ROUND((data_length + index_length) / 1024 / 1024, 2) AS total_mb,
  create_time,
  update_time,
  table_collation,
  engine
FROM information_schema.tables
WHERE table_schema = '{database_name}'
  AND table_name = '{table}';
```

---

### 4f — Aurora-specific: Check Partitioning & Auto-increment

#### Aurora PostgreSQL — check table partitioning
```sql
SELECT
  parent.relname AS parent_table,
  child.relname  AS partition_name,
  pg_get_expr(child.relpartbound, child.oid) AS partition_range
FROM pg_inherits
JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
JOIN pg_class child  ON pg_inherits.inhrelid  = child.oid
WHERE parent.relname = '{table}';
```
If rows returned → table is partitioned. Record partition key and strategy.

#### Aurora MySQL — check AUTO_INCREMENT value
```sql
SELECT auto_increment
FROM information_schema.tables
WHERE table_schema = '{database_name}'
  AND table_name = '{table}';
```

---

### 4g — Sample Rows (5 rows, reader endpoint preferred)

```sql
-- Aurora PostgreSQL
SELECT * FROM "{schema}"."{table}" LIMIT 5;

-- Aurora MySQL
SELECT * FROM `{database_name}`.`{table}` LIMIT 5;
```

**PII Rules — strictly enforced:**
- Detect PII columns by name patterns: `email`, `phone`, `password`, `ssn`, `dob`, `birth`, `address`, `ip_address`, `credit_card`, `card_number`, `token`, `secret`
- For any matching column: record the column name in the output but replace ALL sample values with `[REDACTED]`
- Never write actual PII to the context file

---

## STEP 5 — Aurora Performance Metadata

Run these queries to capture Aurora-specific performance signals that dashboard engineers need.

### Aurora PostgreSQL — long-running query patterns
```sql
SELECT
  calls,
  ROUND(mean_exec_time::numeric, 2) AS avg_ms,
  ROUND(total_exec_time::numeric, 2) AS total_ms,
  rows,
  LEFT(query, 120) AS query_snippet
FROM pg_stat_statements
WHERE query ILIKE '%{table}%'
ORDER BY total_exec_time DESC
LIMIT 5;
```
(Only available if `pg_stat_statements` extension is enabled — skip if not.)

### Aurora PostgreSQL — bloat / dead tuple check
```sql
SELECT
  n_dead_tup,
  n_live_tup,
  ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) AS dead_pct
FROM pg_stat_user_tables
WHERE schemaname = '{schema}' AND relname = '{table}';
```

### Aurora MySQL — InnoDB buffer pool usage
```sql
SHOW STATUS LIKE 'Innodb_buffer_pool%';
```

---

## STEP 6 — Map Relationships

Using FK data from Step 4c:

- For each FK: source table + column → referenced table + column
- Relationship type:
  - **many-to-one**: FK column is not unique
  - **one-to-one**: FK column also has a unique index
  - **many-to-many**: junction table (has FKs to two tables and no other non-key columns)

Also detect **implied relationships**: columns named `{other_table}_id` with no explicit FK — note as "implied, not enforced."

---

## STEP 7 — Identify Business Domains & Join Paths

Group the 10 tables by domain using the KNOWN TABLES list as the guide.

For each FK-connected pair, write the canonical join path:

```sql
-- Aurora PostgreSQL
SELECT ...
FROM "{schema}"."{table_a}" a
JOIN "{schema}"."{table_b}" b ON a.{fk_col} = b.{pk_col}

-- Aurora MySQL
SELECT ...
FROM `{db}`.`{table_a}` a
JOIN `{db}`.`{table_b}` b ON a.{fk_col} = b.{pk_col}
```

Label each join path as: fact-to-dimension, fact-to-fact (aggregate first), or dimension-to-dimension.

---

## OUTPUT

Write `.github/context/db-schema-context.md`:

```markdown
# Database Schema Context
Generated: {date}
Database:  AWS Aurora RDS — {aurora-postgresql | aurora-mysql}
Cluster:   {writer_endpoint}
Reader:    {reader_endpoint}
Schema:    {schema_name}
Tables:    {count}
AWS Region: {region}

---

## Aurora Connection

  Engine:           {aurora-postgresql 15.x | aurora-mysql 8.x}
  Writer endpoint:  {env var — e.g. AURORA_HOST}
  Reader endpoint:  {env var — e.g. AURORA_READER_HOST}   ← use for dashboard queries
  Port:             {5432 | 3306}
  Database/Schema:  {name}
  Auth method:      {password | IAM token (aws rds generate-db-auth-token)}
  SSL:              required — {AmazonRootCA1.pem | rds-ca-2019 bundle}
  SSL env var:      {AURORA_SSL_CERT | RDS_CA_BUNDLE}

  Python connection example:
  ```python
  # Aurora PostgreSQL
  import psycopg2, os
  conn = psycopg2.connect(
      host=os.environ["AURORA_READER_HOST"],   # reader for dashboards
      port=5432,
      dbname=os.environ["DB_NAME"],
      user=os.environ["DB_USER"],
      password=os.environ["DB_PASSWORD"],
      sslmode="require",
      sslrootcert=os.environ.get("RDS_CA_BUNDLE", "AmazonRootCA1.pem")
  )

  # Aurora MySQL
  import pymysql, os
  conn = pymysql.connect(
      host=os.environ["AURORA_READER_HOST"],
      port=3306,
      db=os.environ["DB_NAME"],
      user=os.environ["DB_USER"],
      password=os.environ["DB_PASSWORD"],
      ssl={"ca": os.environ.get("RDS_CA_BUNDLE", "AmazonRootCA1.pem")}
  )
  ```

---

## Table Inventory

| Table | Schema | Domain | Est. Rows | Size | Purpose |
|---|---|---|---|---|---|
| {table} | {schema} | {domain} | {count} | {size} | {purpose} |
...

---

## Table Definitions

### {schema}.{table_name}

**Purpose:** {inferred from columns and FK relationships}
**Domain:** {business domain}
**Estimated rows:** {count}
**Size:** {size}
**Partitioned:** {Yes — by {key} | No}

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| {col} | {type} | {Y/N} | {default} | PK / FK → schema.table.col / [REDACTED PII] / AUTO_INCREMENT |
...

**Primary Key:** {column(s)}
**Foreign Keys:**
- `{fk_col}` → `{schema}.{referenced_table}.{referenced_col}` (ON DELETE {rule})

**Indexes:**
- `{index_name}`: ({columns}) — {UNIQUE | BTREE | GIN | FULLTEXT}

**Sample Data (PII columns redacted):**
| {col1} | {col2} | {col3} |
|---|---|---|
| val | val | [REDACTED] |

**Aurora Performance Notes:**
- Dead tuple %: {value} (PostgreSQL) / N/A (MySQL)
- Last autovacuum: {timestamp} / N/A (MySQL)

---

{repeat for all 10 tables}

---

## Entity-Relationship Map

```
{schema}.{table_a}
  └── {fk_col} → {schema}.{table_b}.{pk_col}  [many-to-one]

{schema}.{table_c}
  └── {fk_col} → {schema}.{table_a}.{pk_col}  [many-to-one]
  └── {fk_col} → {schema}.{table_d}.{pk_col}  [many-to-one, implied]
```

### Relationship Registry
| From | Column | To | Column | Type | Enforced |
|---|---|---|---|---|---|
| {table} | {col} | {table} | {col} | many-to-one | FK / implied |

---

## Business Domains

### {Domain Name}
Tables: {table_a}, {table_b}, {table_c}
Description: {what this domain represents}

---

## Dashboard Join Paths

### {table_a} ↔ {table_b}
```sql
-- Aurora PostgreSQL
SELECT ...
FROM "{schema}"."{table_a}" a
JOIN "{schema}"."{table_b}" b ON a.{fk} = b.{pk}

-- Aurora MySQL
SELECT ...
FROM `{db}`.`{table_a}` a
JOIN `{db}`.`{table_b}` b ON a.{fk} = b.{pk}
```
**Use for:** {what dashboard metric this join enables}
**Read via:** reader endpoint

---

## Fact vs Dimension Classification

| Table | Type | Metric Columns | Dimension Columns | Recommended Grain |
|---|---|---|---|---|
| {table} | fact | {amount, qty} | {date, status, region_id} | {daily / per-order} |
| {table} | dimension | N/A | {name, category} | N/A |

---

## Aurora-Specific Dashboard Query Rules

- **Always use the reader endpoint** (`AURORA_READER_HOST`) for dashboard queries — never the writer.
- **SSL is mandatory** — include `sslmode=require` (PostgreSQL) or `ssl={'ca': ...}` (MySQL).
- **Date functions:**
  - Aurora PostgreSQL: `DATE_TRUNC('month', created_at)`, `NOW()`, `CURRENT_DATE`
  - Aurora MySQL: `DATE_FORMAT(created_at, '%Y-%m')`, `NOW()`, `CURDATE()`
- **Identifier quoting:**
  - Aurora PostgreSQL: `"double_quotes"` for schema and table names
  - Aurora MySQL: `` `backticks` `` for database and table names
- **Window functions:** supported in both Aurora PostgreSQL and Aurora MySQL 8.x+
- **CTEs:** supported in both engines (MySQL 8.0+ supports recursive CTEs too)
- **JSON columns:** use `->` and `->>`  (PostgreSQL) or `JSON_EXTRACT()` (MySQL)
- **Large tables:** prefer queries that hit indexed columns in WHERE clauses; check indexes above

## Notes for Dashboard Engineers

- {any quirks, NULLs, data quality issues noted during introspection}
- {any columns with high dead_pct that may need VACUUM — PostgreSQL only}
- {any tables with AUTO_INCREMENT nearing max value — MySQL only}
- {recommended refresh cadence per fact table}
```

Save to `.github/context/db-schema-context.md`.
