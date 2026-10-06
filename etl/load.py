"""LOAD: write clean data into PostgreSQL (bulk COPY into staging, then idempotent upsert)."""
import io
import logging
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import Json, execute_values

log = logging.getLogger("etl")


def connect(dsn: dict):
    try:
        return psycopg2.connect(**dsn)
    except psycopg2.OperationalError as exc:
        raise SystemExit(
            f"Cannot connect to PostgreSQL ({dsn['host']}:{dsn['port']}/{dsn['dbname']} as {dsn['user']}).\n"
            f"Is the database running and is .env configured?\nDetails: {exc}")


def run_sql_file(conn, path: Path) -> None:
    with conn.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))
    conn.commit()


def start_run(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO etl_runs DEFAULT VALUES RETURNING run_id")
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_run(conn, run_id: int, status: str, stats: dict, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE etl_runs SET finished_at = now(), status = %s, rows_extracted = %s,
                      rows_duplicates = %s, rows_rejected = %s, rows_loaded = %s, error_message = %s
               WHERE run_id = %s""",
            (status, stats.get("extracted"), stats.get("duplicates"), stats.get("rejected"),
             stats.get("loaded"), error, run_id))
    conn.commit()


def reset_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE sales_transactions, rejected_records RESTART IDENTITY")
    conn.commit()
    log.info("RESET    | truncated sales_transactions and rejected_records")


def load_clean(conn, df: pd.DataFrame) -> int:
    """Bulk-load rows. Returns number of NEW rows inserted (existing keys are skipped)."""
    with conn.cursor() as cur:
        # 1) lookup tables (insert only new names)
        for table, col, values in (("categories", "category_name", df["category"].unique()),
                                   ("countries", "country_name", df["country"].unique())):
            execute_values(cur, f"INSERT INTO {table} ({col}) VALUES %s ON CONFLICT ({col}) DO NOTHING",
                           [(v,) for v in values])

        # 2) unlogged-style temp staging table filled with one COPY (fast)
        cur.execute("""CREATE TEMP TABLE stg_sales (
                           transaction_id text, customer_name text, product_name text, category text,
                           unit_price numeric, quantity int, rating numeric, country text,
                           payment_method text, order_date date) ON COMMIT DROP""")
        buf = io.StringIO()
        cols = ["transaction_id", "customer_name", "product_name", "category", "unit_price",
                "quantity", "rating", "country", "payment_method", "order_date"]
        out = df[cols].copy()
        out["order_date"] = out["order_date"].dt.strftime("%Y-%m-%d")
        out.to_csv(buf, index=False, header=False, na_rep="\\N")
        buf.seek(0)
        cur.copy_expert("COPY stg_sales FROM STDIN WITH (FORMAT csv, NULL '\\N')", buf)

        # 3) move to the real table, resolving foreign keys; re-runs are idempotent
        cur.execute("""
            INSERT INTO sales_transactions
                (transaction_id, customer_name, product_name, category_id, country_id,
                 unit_price, quantity, rating, payment_method, order_date)
            SELECT s.transaction_id, s.customer_name, s.product_name, c.category_id, co.country_id,
                   s.unit_price, s.quantity, s.rating, s.payment_method, s.order_date
            FROM stg_sales s
            JOIN categories c  ON c.category_name = s.category
            JOIN countries  co ON co.country_name = s.country
            ON CONFLICT (transaction_id) DO NOTHING""")
        inserted = cur.rowcount
    conn.commit()
    return inserted


def save_rejects_to_db(conn, run_id: int, rejected: pd.DataFrame) -> None:
    if rejected.empty:
        return
    rows = []
    for rec in rejected.to_dict("records"):
        reason = rec.pop("reject_reason")
        src = rec.pop("source_row")
        clean = {k: (None if pd.isna(v) else str(v)) for k, v in rec.items()}
        rows.append((run_id, int(src), reason, Json(clean)))
    with conn.cursor() as cur:
        execute_values(cur, "INSERT INTO rejected_records (run_id, source_row, reason, raw_record) VALUES %s", rows)
    conn.commit()
