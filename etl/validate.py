"""VALIDATE: enforce business constraints, split into (valid, rejected), then de-duplicate."""
import logging
from datetime import date

import pandas as pd

log = logging.getLogger("etl")

MIN_DATE = pd.Timestamp("2000-01-01")


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (valid_unique_rows, rejected_rows). Rejected rows carry a `reject_reason`."""
    df = df.copy()
    today = pd.Timestamp(date.today())

    def flag(mask: pd.Series, msg: str) -> None:
        for idx in df.index[mask.fillna(False)]:
            df.at[idx, "_issues"].append(msg)

    flag(df["transaction_id"].isna(), "missing transaction_id")
    flag(df["unit_price"].isna(), "unit_price missing or unparseable")
    flag(df["unit_price"] <= 0, "unit_price must be > 0")
    flag(df["quantity"].isna(), "quantity missing or unparseable")
    flag(df["quantity"] <= 0, "quantity must be > 0")
    flag(df["rating"].notna() & ((df["rating"] < 1) | (df["rating"] > 5)), "rating outside 1-5")
    flag(df["order_date"].isna(), "order_date missing or unparseable")
    flag(df["order_date"] > today, "order_date is in the future")
    flag(df["order_date"] < MIN_DATE, "order_date before 2000-01-01")

    bad = df["_issues"].map(len) > 0
    df["reject_reason"] = df["_issues"].map("; ".join)
    rejected = df[bad].drop(columns="_issues")
    valid = df[~bad].drop(columns=["_issues", "reject_reason"])
    log.info("VALIDATE | %s valid, %s rejected (constraint violations)", f"{len(valid):,}", f"{len(rejected):,}")

    # --- de-duplicate on the business key, keeping the most complete record -----------
    optional = ["customer_name", "category", "rating", "payment_method", "country"]
    placeholder = {"customer_name": "Unknown", "category": "Uncategorized",
                   "payment_method": "Unknown", "country": "Unknown"}
    completeness = sum(
        (valid[c].notna() & (valid[c] != placeholder.get(c))).astype(int) for c in optional)
    valid = (valid.assign(_score=completeness)
                  .sort_values(["_score", "source_row"], ascending=[False, True]))
    is_dup = valid.duplicated(subset="transaction_id", keep="first")
    dups = valid[is_dup].drop(columns="_score").assign(reject_reason="duplicate transaction_id")
    valid = valid[~is_dup].drop(columns="_score").sort_values("source_row")
    log.info("DEDUPE   | removed %s duplicate rows, %s unique rows remain", f"{len(dups):,}", f"{len(valid):,}")

    rejected = pd.concat([rejected, dups]).sort_values("source_row")
    return valid, rejected
