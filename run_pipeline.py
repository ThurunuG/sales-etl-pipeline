#!/usr/bin/env python3
"""ETL entry point.

    python run_pipeline.py                 # full run: extract -> transform -> validate -> load
    python run_pipeline.py --reset         # truncate target tables first (clean demo run)
    python run_pipeline.py --dry-run       # everything except the database load
"""
import argparse
import sys
import time

from etl.config import get_settings
from etl.extract import extract
from etl.load import (connect, finish_run, load_clean, reset_tables, run_sql_file,
                      save_rejects_to_db, start_run)
from etl.logger import setup_logging
from etl.transform import transform
from etl.validate import validate


def main() -> int:
    ap = argparse.ArgumentParser(description="Sales ETL pipeline")
    ap.add_argument("--input", help="override RAW_DATA_PATH")
    ap.add_argument("--reset", action="store_true", help="truncate target tables before loading")
    ap.add_argument("--dry-run", action="store_true", help="skip the PostgreSQL load")
    args = ap.parse_args()

    cfg = get_settings()
    log = setup_logging(cfg.log_path)
    t0 = time.time()
    log.info("=" * 70)
    log.info("PIPELINE | start")

    stats: dict = {}
    conn = run_id = None
    try:
        if not args.dry_run:
            conn = connect(cfg.dsn())
            run_sql_file(conn, cfg.sql_dir / "01_schema.sql")
            run_id = start_run(conn)
            if args.reset:
                reset_tables(conn)

        # ---- E ----
        from pathlib import Path
        raw = extract(Path(args.input) if args.input else cfg.raw_path)
        stats["extracted"] = len(raw)

        # ---- T ----
        transformed = transform(raw)
        valid, rejected = validate(transformed)
        stats["rejected"] = int((rejected["reject_reason"] != "duplicate transaction_id").sum())
        stats["duplicates"] = int((rejected["reject_reason"] == "duplicate transaction_id").sum())

        # ---- write files (clean output + rejected log) ----
        cfg.processed_path.parent.mkdir(parents=True, exist_ok=True)
        cfg.rejected_path.parent.mkdir(parents=True, exist_ok=True)
        valid.drop(columns="source_row").to_csv(cfg.processed_path, index=False)
        rejected.to_csv(cfg.rejected_path, index=False)
        log.info("OUTPUT   | clean -> %s | rejected -> %s", cfg.processed_path, cfg.rejected_path)
        if not rejected.empty:
            for reason, n in rejected["reject_reason"].str.split("; ").explode().value_counts().items():
                log.info("REJECTED | %5d  %s", n, reason)

        # ---- L ----
        if args.dry_run:
            stats["loaded"] = 0
            log.info("LOAD     | skipped (--dry-run)")
        else:
            stats["loaded"] = load_clean(conn, valid)
            save_rejects_to_db(conn, run_id, rejected)
            run_sql_file(conn, cfg.sql_dir / "02_indexes.sql")
            finish_run(conn, run_id, "SUCCESS", stats)
            log.info("LOAD     | inserted %s new rows into sales_transactions", f"{stats['loaded']:,}")

        log.info("SUMMARY  | extracted=%(extracted)s rejected=%(rejected)s duplicates=%(duplicates)s loaded=%(loaded)s", stats)
        log.info("PIPELINE | finished in %.1fs", time.time() - t0)
        return 0
    except Exception as exc:  # noqa: BLE001 - top-level handler records failure then re-raises exit code
        log.exception("PIPELINE | FAILED: %s", exc)
        if conn is not None and run_id is not None:
            conn.rollback()
            finish_run(conn, run_id, "FAILED", stats, str(exc))
        return 1
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
