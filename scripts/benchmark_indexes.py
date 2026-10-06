"""Show how indexes improve performance, on a scaled-up copy of the schema.

Creates a throw-away table `sales_bench` (default 1,000,000 rows, generated inside PostgreSQL),
runs EXPLAIN (ANALYZE) on typical queries WITHOUT indexes, adds the indexes, then runs again.

    python scripts/benchmark_indexes.py --rows 1000000
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from etl.config import get_settings  # noqa: E402
from etl.load import connect  # noqa: E402

QUERIES = {
    "Q-A  single transaction lookup (PK)": (
        "SELECT * FROM sales_bench WHERE transaction_id = 'TXN{mid}'"),
    "Q-B  one month of revenue (date range)": (
        "SELECT COUNT(*), SUM(total_amount) FROM sales_bench "
        "WHERE order_date >= DATE '2025-03-01' AND order_date < DATE '2025-04-01'"),
    "Q-C  revenue of ONE category (filter)": (
        "SELECT SUM(total_amount) FROM sales_bench WHERE category_id = 2"),
    "Q-E  revenue ALL categories (full scan)": (
        "SELECT category_id, SUM(total_amount) FROM sales_bench GROUP BY category_id"),
    "Q-D  avg rating, one country": (
        "SELECT AVG(rating) FROM sales_bench WHERE country_id = 3 AND rating IS NOT NULL"),
}

INDEXES = [
    "ALTER TABLE sales_bench ADD PRIMARY KEY (transaction_id)",
    "CREATE INDEX ON sales_bench (order_date)",
    "CREATE INDEX ON sales_bench (category_id) INCLUDE (total_amount)",
    "CREATE INDEX ON sales_bench (country_id, rating) WHERE rating IS NOT NULL",
]


def explain(cur, sql: str) -> tuple[float, str]:
    cur.execute("EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF) " + sql)
    lines = [r[0] for r in cur.fetchall()]
    ms = float(re.search(r"Execution Time: ([\d.]+) ms", "\n".join(lines)).group(1))
    scan = next((l.strip() for l in lines if "Scan" in l), lines[0].strip())
    return ms, re.sub(r"\s+on\s+sales_bench.*|\s+using.*", "", scan, flags=re.I).strip() + (
        " (" + re.search(r"using (\S+)", scan).group(1) + ")" if "using" in scan else "")


def run_all(cur, rows: int) -> dict:
    out = {}
    for name, sql in QUERIES.items():
        sql = sql.format(mid=100000 + rows // 2)
        explain(cur, sql)  # warm-up
        out[name] = min((explain(cur, sql) for _ in range(3)), key=lambda t: t[0])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1_000_000)
    args = ap.parse_args()
    conn = connect(get_settings().dsn())
    conn.autocommit = True
    cur = conn.cursor()

    print(f"Building sales_bench with {args.rows:,} rows inside PostgreSQL ...")
    cur.execute("DROP TABLE IF EXISTS sales_bench")
    cur.execute(f"""
        CREATE TABLE sales_bench AS
        SELECT 'TXN' || (100000 + g)                              AS transaction_id,
               (1 + (random()*6)::int)::smallint                   AS category_id,
               (1 + (random()*10)::int)::smallint                  AS country_id,
               CASE WHEN random() < 0.1 THEN NULL
                    ELSE round((1 + random()*4)::numeric, 1) END   AS rating,
               round((10 + random()*490)::numeric, 2)              AS total_amount,
               DATE '2023-01-01' + ((g::numeric / {args.rows}) * 1095)::int AS order_date
        FROM generate_series(1, {args.rows}) g""")
    cur.execute("ANALYZE sales_bench")

    before = run_all(cur, args.rows)
    for ddl in INDEXES:
        cur.execute(ddl)
    cur.execute("VACUUM ANALYZE sales_bench")  # builds visibility map -> index-only scans
    after = run_all(cur, args.rows)

    print(f"\n{'Query':<42}{'No index':>12}{'Indexed':>12}{'Speed-up':>10}")
    print("-" * 76)
    for name in QUERIES:
        b, a = before[name], after[name]
        print(f"{name:<42}{b[0]:>9.2f} ms{a[0]:>9.2f} ms{b[0] / a[0]:>9.1f}x")
        print(f"{'':<4}plan before: {b[1]}\n{'':<4}plan after : {a[1]}")
    cur.execute("DROP TABLE sales_bench")
    conn.close()


if __name__ == "__main__":
    main()
