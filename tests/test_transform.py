"""Unit tests for cleaning + validation rules (no database needed): pytest -q"""
import pandas as pd

from etl.transform import transform
from etl.validate import validate


def _raw(**over):
    row = dict(source_row=2, transaction_id="txn1", customer_name="  jOHN   smith ", product_name="USB-C Hub",
               category="electronics", unit_price="$1,234.50", quantity="3.0", rating="4/5",
               country="usa", payment_method="credit_card", order_date="15-Mar-2024")
    row.update(over)
    return pd.DataFrame([row])


def test_standardisation():
    valid, rejected = validate(transform(_raw()))
    r = valid.iloc[0]
    assert rejected.empty
    assert r.transaction_id == "TXN1"
    assert r.customer_name == "John Smith"
    assert r.unit_price == 1234.50 and r.quantity == 3 and r.rating == 4.0
    assert r.country == "United States" and r.payment_method == "Credit Card"
    assert str(r.order_date.date()) == "2024-03-15"


def test_missing_optional_values_are_filled_not_rejected():
    valid, rejected = validate(transform(_raw(customer_name="N/A", rating="", country="", payment_method="null")))
    assert rejected.empty
    r = valid.iloc[0]
    assert r.customer_name == "Unknown" and pd.isna(r.rating) and r.country == "Unknown"


def test_invalid_rows_are_rejected_with_reason():
    bad = pd.concat([_raw(unit_price="abc"), _raw(quantity="-2"), _raw(rating="9"),
                     _raw(order_date="31/02/2024"), _raw(transaction_id="")], ignore_index=True)
    bad["source_row"] = range(2, 7)
    valid, rejected = validate(transform(bad))
    assert valid.empty and len(rejected) == 5
    assert rejected["reject_reason"].str.len().gt(0).all()


def test_duplicates_removed_keep_most_complete():
    df = pd.concat([_raw(rating="", source_row=2), _raw(rating="4", transaction_id=" TXN1 ", source_row=3)],
                   ignore_index=True)
    valid, rejected = validate(transform(df))
    assert len(valid) == 1 and valid.iloc[0].rating == 4.0
    assert (rejected["reject_reason"] == "duplicate transaction_id").sum() == 1
