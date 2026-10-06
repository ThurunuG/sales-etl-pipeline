# Sales ETL Pipeline — Python + PostgreSQL (100% local)

A small end-to-end data-engineering project: a **deliberately dirty sales-transactions dataset**
(12,480 raw rows) is extracted, cleaned, validated, de-duplicated and loaded into **PostgreSQL**,
then analysed with optimised SQL. Everything runs locally — no cloud account needed.

```
 scripts/generate_dataset.py          run_pipeline.py                          PostgreSQL
 ┌────────────────────────┐   ┌─────────────────────────────────────────┐   ┌───────────────────────┐
 │ data/raw/sales_raw.csv │──▶│ EXTRACT → TRANSFORM → VALIDATE → LOAD    │──▶│ sales_transactions    │
 │ (dirty, 12,480 rows)   │   │            │            │               │   │ categories, countries │
 └────────────────────────┘   │            ▼            ▼               │   │ etl_runs (audit)      │
                              │  data/processed/    logs/rejected_      │   │ rejected_records      │
                              │  sales_clean.csv    records.csv + DB    │   └───────────────────────┘
                              └─────────────────────────────────────────┘
```

## 1. The dataset (business domain: sales transactions)

`python scripts/generate_dataset.py` writes `data/raw/sales_raw.csv` (seeded, so reproducible).
10 columns, mixed types (string / numeric / date), **12,000 base rows + 480 duplicates**.

| Column | Type | Example |
|---|---|---|
| transaction_id | string | `TXN108243` |
| customer_name, product_name, category | string | `Aiden Perera`, `Air Fryer`, `Home & Kitchen` |
| unit_price, quantity | numeric | `105.27`, `3` |
| rating | numeric (1–5) | `3.8` |
| country, payment_method | string | `United States`, `PayPal` |
| order_date | date | `2024-11-26` |

Injected dirt: missing values (`""`, `N/A`, `null`), exact + near duplicates, mixed casing/whitespace,
country aliases (`US`, `U.S.`, `USA`), prices like `$1,234.50` / `45.00 USD`, quantities like `3.0` / `2 units`,
ratings like `4/5` / `4,5`, **5 date formats**, and unrecoverable values (negative price, rating 9, `31/02/2024`, year 2099).

> **Using a real dataset instead?** Point `RAW_DATA_PATH` at any CSV with these columns, or adapt
> `etl/transform.py`. Good public options: *UCI Online Retail II* (~1M rows, sales transactions, naturally dirty),
> *Superstore Sales* (~10k rows) and *Olist Brazilian E-commerce* (~100k orders) from Kaggle/UCI.

## 2. Project structure

```
sales-etl-pipeline/
├── run_pipeline.py            # ETL entry point
├── etl/                       # config, logger, extract, transform, validate, load
├── sql/
│   ├── 01_schema.sql          # tables, PKs, FKs, CHECK constraints
│   ├── 02_indexes.sql         # indexes
│   └── 03_analytics_queries.sql
├── scripts/
│   ├── generate_dataset.py    # creates the dirty raw CSV
│   ├── run_queries.py         # runs the analytical queries (+ --explain)
│   └── benchmark_indexes.py   # before/after index benchmark on 1M rows
├── tests/test_transform.py    # unit tests for cleaning rules
├── data/raw  data/processed   # input / cleaned output
├── logs/                      # pipeline.log, rejected_records.csv
├── docker-compose.yml         # PostgreSQL 16 (optional)
├── requirements.txt  .env.example
```

## 3. Setup & run

```bash
# 1. Python deps
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. PostgreSQL - option A: Docker
cp .env.example .env            # edit the password
docker compose up -d
#    option B: your own local Postgres
#    CREATE USER etl_user WITH PASSWORD '...';  CREATE DATABASE sales_dw OWNER etl_user;

# 3. Create raw dataset, then run the pipeline
python scripts/generate_dataset.py
python run_pipeline.py --reset          # --reset truncates tables for a clean demo run

# 4. Analytics + optimisation
python scripts/run_queries.py           # add --explain for query plans
python scripts/benchmark_indexes.py     # 1,000,000-row before/after index benchmark
pytest -q                               # unit tests
```

Credentials are read **only from environment variables / `.env`** (git-ignored). Nothing is hard-coded.
`run_pipeline.py` options: `--reset`, `--dry-run` (no DB), `--input path.csv`.

## 4. What the pipeline does

| Stage | Module | Behaviour |
|---|---|---|
| Extract | `etl/extract.py` | Reads CSV as text (no silent coercion), checks columns, records the source line number |
| Clean / standardise | `etl/transform.py` | Trims/collapses whitespace; null tokens → NULL; consistent casing (most-common spelling per case-insensitive value, so `USB-C Hub` stays correct); country alias map; strips `$`, `,`, `USD`; `"4/5"`/`"4,5"` ratings; `"2 units"` quantities; 5 date formats → ISO dates |
| Missing values | transform | `customer_name`, `payment_method`, `country` → `'Unknown'`; missing `category` is **imputed from the product** (most common category for that product) else `'Uncategorized'`; missing `rating` stays NULL (a missing rating is not an invalid order) |
| Validate | `etl/validate.py` | Rejects rows that break rules: price/quantity missing or ≤ 0, rating outside 1–5, date missing/unparseable/future/pre-2000, missing `transaction_id` |
| De-duplicate | validate | On `transaction_id` **after** standardisation (so `" txn1 "` and `TXN1` match); keeps the most complete record |
| Reject log | `logs/rejected_records.csv` + `rejected_records` table | Every dropped row with its source line number, reason(s) and raw values |
| Load | `etl/load.py` | Bulk `COPY` into a temp staging table → `INSERT … ON CONFLICT DO NOTHING` (re-runs are idempotent); lookup tables upserted; run audited in `etl_runs` |

Typical result: **12,480 extracted → 295 rejected → 471 duplicates removed → 11,714 loaded**.

## 5. Database design

* `sales_transactions` (fact) — PK `transaction_id`; FKs to `categories` and `countries` (normalised lookup tables);
  `CHECK`s on price > 0, quantity > 0, rating 1–5, sane date range; `NOT NULL`s; `total_amount` is a
  **generated stored column** (`unit_price * quantity`) so it can never drift.
* `etl_runs` — audit trail (status, counts, error). `rejected_records` — queryable rejects (JSONB raw row).

## 6. Analytical queries & optimisation (`sql/03_analytics_queries.sql`)

1. **Top categories by revenue** (+ % of total window function)
2. **Monthly revenue and month-over-month growth** (CTE + `LAG`)
3. **Average rating by country** (partial index, `HAVING` to drop tiny groups)
4. **Top 3 products per category in 2025** (`ROW_NUMBER`, sargable date range)
5. Revenue by country × payment method

Optimisation decisions: aggregate **before** joining lookup tables; sargable date predicates
(`order_date >= … AND < …`, never `EXTRACT(year …)`); a **partial** index for rating; a **covering** index
(`INCLUDE`) for index-only scans; a tiny **BRIN** index for time-ordered data; `ANALYZE` after bulk loads.

### Does indexing help? Measured (`python scripts/benchmark_indexes.py`, 1,000,000 rows, local PostgreSQL 16)

| Query | No index | Indexed | Speed-up | Plan after |
|---|---|---|---|---|
| Single transaction lookup | ~38 ms | ~0.02 ms | ~2000× | Index Scan (PK) |
| One month of revenue | ~47 ms | ~4 ms | ~12× | Index Scan on `order_date` |
| Revenue of one category | ~42 ms | ~15 ms | ~2.7× | Parallel Index Only Scan (covering) |
| Avg rating for one country | ~43 ms | ~11 ms | ~4× | Index Only Scan (partial) |
| Revenue of **all** categories | ~97 ms | ~98 ms | **1×** | Seq Scan (unchanged) |

(Timings vary by machine; re-run for your numbers.) **The last row is intentional:** a query that reads every
row gains nothing from an index and the planner correctly ignores it — indexes help *selective* queries.
On the 11.7k-row demo table, sequential scans are fastest for everything, which is why the benchmark scales up.
Each index also costs write time and disk, so only indexes that serve real queries are created.

## 7. Scalability & architecture thinking (1M+ records)

**Pipeline.** Today pandas loads the whole file into memory (fine to a few million rows). For 1M–50M+ rows:
read the CSV in **chunks** (`pd.read_csv(chunksize=…)`) or switch to **Polars/DuckDB**; keep `COPY` for loading
(it already loads ~100k+ rows/s); drop secondary indexes before the bulk load and rebuild after; de-duplicate
in the database (`ON CONFLICT`) instead of in memory. Beyond ~100M rows move to **Spark / a warehouse**.

**Scheduling.** Now: `cron`, e.g. `0 2 * * * cd /app && .venv/bin/python run_pipeline.py >> logs/cron.log 2>&1`.
Production: an **Airflow** DAG — `extract → transform → validate → load → quality_checks → notify` as separate tasks
with retries, SLAs and backfills; new files arrive partitioned by date and each run processes one partition.

**Partitioning / indexing evolution.** Use **declarative range partitioning by month** on `order_date`
(partition pruning, cheap retention via `DROP PARTITION`, parallel scans, smaller per-partition indexes); keep a
BRIN index per partition; add composite indexes only when query patterns demand it; use **materialised views**
(or pre-aggregated daily tables) for dashboard queries; consider read replicas.

**Failure handling.** Already implemented: single transaction per load (all-or-nothing), idempotent upsert
(safe to re-run after a crash), `etl_runs` audit with `FAILED` + error message, structured logs, rejected-row file/table.
Next: retries with exponential backoff, a dead-letter location for bad files, row-count / null-rate quality gates that
fail the run, alerting (email/Slack) from the orchestrator, and checkpointing per chunk.

