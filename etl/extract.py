"""EXTRACT: read the raw CSV exactly as-is (everything as text, nothing silently coerced)."""
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger("etl")

EXPECTED_COLUMNS = [
    "transaction_id", "customer_name", "product_name", "category", "unit_price",
    "quantity", "rating", "country", "payment_method", "order_date",
]


def extract(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Raw dataset not found: {path}. Run: python scripts/generate_dataset.py")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Raw file is missing expected columns: {missing}")
    # line number in the CSV file (header = line 1) so rejected rows can be traced back
    df.insert(0, "source_row", range(2, len(df) + 2))
    log.info("EXTRACT  | read %s rows, %s columns from %s", f"{len(df):,}", len(df.columns) - 1, path)
    return df
