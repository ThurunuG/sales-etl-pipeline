"""Run every analytical query in sql/03_analytics_queries.sql and print results + timing.

    python scripts/run_queries.py              # results
    python scripts/run_queries.py --explain    # EXPLAIN ANALYZE plans too
"""
import argparse
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from etl.config import get_settings  # noqa: E402
from etl.load import connect  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--explain", action="store_true")
    args = ap.parse_args()
    cfg = get_settings()
    text = (cfg.sql_dir / "03_analytics_queries.sql").read_text(encoding="utf-8")
    # split on blank-line-separated blocks that start with the "-- Qn." title comment
    blocks = [b.strip() for b in re.split(r"(?m)^-- (?=Q\d+\.)", text)[1:]]
    conn = connect(cfg.dsn())
    pd.set_option("display.width", 200, "display.max_rows", 60)
    with conn.cursor() as cur:
        for block in blocks:
            title = block.splitlines()[0].rstrip("- ")
            sql = "\n".join(l for l in block.splitlines()[1:] if not l.strip().startswith("--")).strip().rstrip(";")
            print(f"\n=== {title} ===")
            t = time.perf_counter()
            cur.execute(sql)
            rows, cols = cur.fetchall(), [d[0] for d in cur.description]
            ms = (time.perf_counter() - t) * 1000
            print(pd.DataFrame(rows, columns=cols).to_string(index=False))
            print(f"-- {len(rows)} rows in {ms:.1f} ms")
            if args.explain:
                cur.execute("EXPLAIN (ANALYZE, BUFFERS) " + sql)
                print("\n".join(r[0] for r in cur.fetchall()))
    conn.close()


if __name__ == "__main__":
    main()
