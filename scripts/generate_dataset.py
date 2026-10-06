"""Generate a realistic but intentionally DIRTY sales-transactions dataset.

Usage:
    python scripts/generate_dataset.py                # 12,000 base rows
    python scripts/generate_dataset.py --rows 50000

Dirty-data issues injected (so the ETL has real work to do):
    * missing values (customer, category, rating, payment method, country, price, qty, date)
    * exact and "near" duplicates (case / whitespace differences, same transaction_id)
    * inconsistent casing and stray whitespace
    * country aliases (USA, U.S., united states, UK, ...)
    * prices with currency symbols / thousands separators / junk text
    * quantities as floats or text, zero / negative values
    * 5 different date formats
    * ratings as "4/5", out of range values, text
"""
import argparse
import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

SEED = 42

# product -> (category, base price)
CATALOG = {
    "Wireless Mouse": ("Electronics", 24.99),
    "Mechanical Keyboard": ("Electronics", 89.50),
    "USB-C Hub": ("Electronics", 45.00),
    "Noise Cancelling Headphones": ("Electronics", 199.99),
    "4K Monitor": ("Electronics", 329.00),
    "Smartphone Case": ("Accessories", 14.99),
    "Laptop Sleeve": ("Accessories", 29.90),
    "Leather Wallet": ("Accessories", 49.00),
    "Sunglasses": ("Accessories", 79.00),
    "Running Shoes": ("Sports", 119.00),
    "Yoga Mat": ("Sports", 32.00),
    "Dumbbell Set": ("Sports", 149.00),
    "Water Bottle": ("Sports", 18.50),
    "Office Chair": ("Furniture", 249.00),
    "Standing Desk": ("Furniture", 489.00),
    "Bookshelf": ("Furniture", 129.00),
    "Desk Lamp": ("Furniture", 39.99),
    "Coffee Maker": ("Home & Kitchen", 79.99),
    "Air Fryer": ("Home & Kitchen", 99.00),
    "Blender": ("Home & Kitchen", 59.00),
    "Knife Set": ("Home & Kitchen", 69.50),
    "Novel Bundle": ("Books", 34.00),
    "Cookbook": ("Books", 27.50),
    "Python Handbook": ("Books", 44.00),
    "Face Serum": ("Beauty", 38.00),
    "Perfume": ("Beauty", 95.00),
    "Hair Dryer": ("Beauty", 64.00),
}

COUNTRIES = {
    "United States": ["United States", "USA", "U.S.", "united states", "US"],
    "United Kingdom": ["United Kingdom", "UK", "U.K.", "united kingdom", "Great Britain"],
    "Germany": ["Germany", "germany", "DE", "GERMANY"],
    "France": ["France", "france", "FR"],
    "India": ["India", "india", "IN", "INDIA"],
    "Sri Lanka": ["Sri Lanka", "sri lanka", "LK", "SRI LANKA"],
    "Australia": ["Australia", "australia", "AU"],
    "Canada": ["Canada", "canada", "CA", "CANADA"],
    "Japan": ["Japan", "japan", "JP"],
    "Singapore": ["Singapore", "singapore", "SG"],
}
COUNTRY_WEIGHTS = [28, 14, 11, 9, 12, 5, 7, 6, 4, 4]

PAYMENTS = ["Credit Card", "Debit Card", "PayPal", "Cash", "Bank Transfer"]
PAYMENT_VARIANTS = {
    "Credit Card": ["Credit Card", "credit card", "CREDIT CARD", "Credit  Card", "credit_card"],
    "Debit Card": ["Debit Card", "debit card", "DEBIT CARD", "debit_card"],
    "PayPal": ["PayPal", "paypal", "PAYPAL", "Paypal"],
    "Cash": ["Cash", "cash", "CASH"],
    "Bank Transfer": ["Bank Transfer", "bank transfer", "BANK TRANSFER", "bank_transfer"],
}

FIRST = ["James", "Mary", "Liam", "Olivia", "Noah", "Emma", "Arjun", "Priya", "Kasun", "Nimali",
         "Hans", "Sophie", "Pierre", "Chloe", "Yuki", "Hiro", "Wei", "Mei", "Oliver", "Amelia",
         "Lucas", "Isabella", "Ethan", "Mia", "Aiden", "Zoe", "Rahul", "Anita", "Tharindu", "Sanduni"]
LAST = ["Smith", "Johnson", "Brown", "Taylor", "Wilson", "Patel", "Sharma", "Perera", "Fernando",
        "Silva", "Muller", "Schmidt", "Dubois", "Martin", "Tanaka", "Sato", "Chen", "Wang", "Jones",
        "Davis", "Garcia", "Miller", "Lee", "Walker", "Kumar", "Singh", "Jayasinghe", "Wickramasinghe"]


def fmt_date(d: date, rng: random.Random) -> str:
    style = rng.choices(range(5), weights=[50, 20, 12, 10, 8])[0]
    if style == 0:
        return d.strftime("%Y-%m-%d")
    if style == 1:
        return d.strftime("%d/%m/%Y")
    if style == 2:
        return d.strftime("%b %d, %Y")
    if style == 3:
        return d.strftime("%d-%b-%Y")
    return d.strftime("%Y/%m/%d")


def random_order_date(rng: random.Random) -> date:
    """Dates between 2023-01-01 and 2025-12-31 with growth + Q4 seasonality."""
    start, end = date(2023, 1, 1), date(2025, 12, 31)
    span = (end - start).days
    while True:
        offset = int(span * (rng.random() ** 0.8))  # skew towards recent dates (growth)
        d = start + timedelta(days=offset)
        weight = 1.5 if d.month in (11, 12) else 1.0
        if rng.random() < weight / 1.5:
            return d


def build_clean_row(i: int, rng: random.Random) -> dict:
    product = rng.choice(list(CATALOG))
    category, base = CATALOG[product]
    country = rng.choices(list(COUNTRIES), weights=COUNTRY_WEIGHTS)[0]
    price = round(base * rng.uniform(0.9, 1.15), 2)
    return {
        "transaction_id": f"TXN{100000 + i}",
        "customer_name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
        "product_name": product,
        "category": category,
        "unit_price": price,
        "quantity": rng.choices([1, 2, 3, 4, 5, 6], weights=[45, 25, 12, 8, 6, 4])[0],
        "rating": round(min(5, max(1, rng.gauss(4.0, 0.9))), 1),
        "country": country,
        "payment_method": rng.choice(PAYMENTS),
        "order_date": random_order_date(rng),
    }


def dirty_row(row: dict, rng: random.Random) -> dict:
    r = dict(row)

    # --- formatting / casing noise -------------------------------------------------
    r["order_date"] = fmt_date(r["order_date"], rng)
    r["country"] = rng.choice(COUNTRIES[r["country"]])
    r["payment_method"] = rng.choice(PAYMENT_VARIANTS[r["payment_method"]])

    name = r["customer_name"]
    roll = rng.random()
    if roll < 0.10:
        name = name.upper()
    elif roll < 0.20:
        name = name.lower()
    elif roll < 0.25:
        name = f"  {name}  "
    r["customer_name"] = name

    cat = r["category"]
    roll = rng.random()
    if roll < 0.08:
        cat = cat.lower()
    elif roll < 0.12:
        cat = cat.upper()
    elif roll < 0.15:
        cat = f" {cat} "
    r["category"] = cat

    if rng.random() < 0.05:
        r["product_name"] = r["product_name"].lower()

    # price formats
    p = r["unit_price"]
    roll = rng.random()
    if roll < 0.07:
        r["unit_price"] = f"${p:,.2f}"
    elif roll < 0.10:
        r["unit_price"] = f"{p:,.2f} USD"
    elif roll < 0.12:
        r["unit_price"] = f" {p} "
    else:
        r["unit_price"] = p

    # quantity formats
    q = r["quantity"]
    roll = rng.random()
    if roll < 0.04:
        r["quantity"] = f"{q}.0"
    elif roll < 0.06:
        r["quantity"] = f"{q} units"
    elif roll < 0.07:
        r["quantity"] = str(q)

    # rating formats
    rt = r["rating"]
    roll = rng.random()
    if roll < 0.03:
        r["rating"] = f"{rt}/5"
    elif roll < 0.04:
        r["rating"] = f"{rt}".replace(".", ",")  # european decimal comma

    # --- missing values ---------------------------------------------------------------
    for col, prob in [("customer_name", 0.03), ("category", 0.04), ("rating", 0.10),
                      ("payment_method", 0.03), ("country", 0.02)]:
        if rng.random() < prob:
            r[col] = rng.choice([None, "", "N/A", "null"])

    # --- invalid / unrecoverable values (these should be REJECTED) -------------------
    roll = rng.random()
    if roll < 0.006:
        r["unit_price"] = rng.choice([None, "", "N/A", "abc", "-15.00", "0"])
    roll = rng.random()
    if roll < 0.005:
        r["quantity"] = rng.choice([None, "", "0", "-2", "many"])
    if rng.random() < 0.004:
        r["rating"] = rng.choice(["9.5", "0", "-1", "excellent", "7"])
    if rng.random() < 0.005:
        r["order_date"] = rng.choice([None, "", "31/02/2024", "not a date", "2099-01-01"])
    if rng.random() < 0.002:
        r["transaction_id"] = rng.choice([None, ""])

    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=12000, help="number of base transactions")
    ap.add_argument("--out", default="data/raw/sales_raw.csv")
    ap.add_argument("--dup-rate", type=float, default=0.04, help="fraction of rows duplicated")
    args = ap.parse_args()

    rng = random.Random(SEED)
    rows = [dirty_row(build_clean_row(i, rng), rng) for i in range(args.rows)]

    # --- duplicates: exact copies and "near" copies (case/whitespace variations) -----
    n_dups = int(args.rows * args.dup_rate)
    for src in rng.sample(rows, n_dups):
        dup = dict(src)
        if rng.random() < 0.5:  # near duplicate
            if isinstance(dup["customer_name"], str):
                dup["customer_name"] = dup["customer_name"].upper()
            if isinstance(dup["transaction_id"], str):
                dup["transaction_id"] = f" {dup['transaction_id'].lower()} "
        rows.append(dup)

    rng.shuffle(rows)
    df = pd.DataFrame(rows)
    df = df[["transaction_id", "customer_name", "product_name", "category", "unit_price",
             "quantity", "rating", "country", "payment_method", "order_date"]]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Wrote {len(df):,} raw rows ({args.rows:,} base + {n_dups:,} duplicates) -> {out}")


if __name__ == "__main__":
    main()
