"""TRANSFORM: clean + standardise. Produces typed columns plus a per-row list of problems.

Nothing is dropped here; validate.py decides what is rejected.
"""
import logging
import re

import pandas as pd

log = logging.getLogger("etl")

NULL_TOKENS = {"", "n/a", "na", "null", "none", "nan", "-", "--", "?", "unknown"}

COUNTRY_ALIASES = {
    "us": "United States", "usa": "United States", "u.s.": "United States",
    "u.s.a.": "United States", "united states": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "united kingdom": "United Kingdom",
    "great britain": "United Kingdom", "gb": "United Kingdom",
    "de": "Germany", "germany": "Germany",
    "fr": "France", "france": "France",
    "in": "India", "india": "India",
    "lk": "Sri Lanka", "sri lanka": "Sri Lanka",
    "au": "Australia", "australia": "Australia",
    "ca": "Canada", "canada": "Canada",
    "jp": "Japan", "japan": "Japan",
    "sg": "Singapore", "singapore": "Singapore",
}

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%b %d, %Y", "%d-%b-%Y", "%Y/%m/%d"]


# ----------------------------------------------------------------------------- helpers
def _clean_text(s: pd.Series) -> pd.Series:
    """Trim, collapse inner whitespace, turn null-like tokens into <NA>."""
    s = s.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    return s.mask(s.str.lower().isin(NULL_TOKENS))


def _canonical_case(s: pd.Series) -> pd.Series:
    """Make casing consistent without hard-coding rules.

    For each case-insensitive value, pick the MOST COMMON spelling in the data
    (e.g. 'usb-c hub' / 'USB-C Hub' / 'USB-C Hub' -> 'USB-C Hub').
    """
    key = s.str.lower()
    mode_by_key = (
        pd.DataFrame({"key": key, "val": s}).dropna()
        .groupby("key")["val"].agg(lambda v: v.value_counts().index[0])
    )
    return key.map(mode_by_key).astype("string")


def _parse_dates(s: pd.Series) -> pd.Series:
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for fmt in DATE_FORMATS:
        todo = out.isna() & s.notna()
        if not todo.any():
            break
        out[todo] = pd.to_datetime(s[todo], format=fmt, errors="coerce")
    return out


# ----------------------------------------------------------------------------- main
def transform(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    for col in df.columns.drop("source_row"):
        df[col] = _clean_text(df[col])

    df["_issues"] = [[] for _ in range(len(df))]

    def flag(mask: pd.Series, msg: str) -> None:
        for idx in df.index[mask.fillna(False)]:
            df.at[idx, "_issues"].append(msg)

    # --- transaction_id ---------------------------------------------------------------
    df["transaction_id"] = df["transaction_id"].str.upper()

    # --- text columns: consistent casing ----------------------------------------------
    df["customer_name"] = df["customer_name"].str.title().fillna("Unknown")
    df["product_name"] = _canonical_case(df["product_name"])
    df["category"] = _canonical_case(df["category"])

    # category imputation: product -> most common known category
    known = df.dropna(subset=["product_name", "category"])
    prod_to_cat = known.groupby("product_name")["category"].agg(lambda v: v.value_counts().index[0])
    missing_cat = df["category"].isna()
    df.loc[missing_cat, "category"] = df.loc[missing_cat, "product_name"].map(prod_to_cat)
    df["category"] = df["category"].fillna("Uncategorized")

    # payment: 'credit_card' / 'CREDIT  CARD' -> 'Credit Card'
    df["payment_method"] = (df["payment_method"].str.replace("_", " ").str.title().fillna("Unknown"))

    # country: alias map, otherwise Title Case; missing -> 'Unknown'
    c_low = df["country"].str.lower()
    df["country"] = c_low.map(COUNTRY_ALIASES).fillna(df["country"].str.title()).fillna("Unknown")

    # --- numerics -----------------------------------------------------------------------
    price_txt = df["unit_price"].str.replace(r"[^0-9.\-]", "", regex=True).replace("", pd.NA)
    df["unit_price"] = pd.to_numeric(price_txt, errors="coerce").round(2)

    qty_txt = df["quantity"].str.extract(r"^\s*(-?\d+(?:\.\d+)?)\s*(?:units?)?\s*$")[0]
    qty_num = pd.to_numeric(qty_txt, errors="coerce")
    flag(qty_num.notna() & (qty_num % 1 != 0), "quantity is not a whole number")
    df["quantity"] = qty_num.round().astype("Int64")

    rating_raw_present = df["rating"].notna()
    rating_txt = (df["rating"].str.split("/").str[0].str.replace(",", ".", regex=False))
    df["rating"] = pd.to_numeric(rating_txt, errors="coerce").round(1)
    flag(rating_raw_present & df["rating"].isna(), "rating is not numeric")

    # --- dates --------------------------------------------------------------------------
    df["order_date"] = _parse_dates(df["order_date"])

    log.info("TRANSFORM| standardised casing, numerics, dates; imputed %s categories",
             f"{int(missing_cat.sum() - (df['category'] == 'Uncategorized').sum()):,}")
    return df
