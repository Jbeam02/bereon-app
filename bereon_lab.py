import pandas as pd
import bereon_engine as engine
from collections import defaultdict
from statistics import median

PARTS = ["5145-1-64", "5145-1-77"]

def load_csv(path):
    df = pd.read_csv(path, low_memory=False).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df.to_dict("records")

def is_round_price(price):
    return price is not None and price == round(price) and price % 50 == 0

def classify_transaction(row, side):
    text = engine.row_text(row)
    price = engine.row_price(row, side)

    if "REPAIR" in text:
        return "Repair"

    if "EXCH" in text or "EXCHANGE" in text:
        return "Exchange" if is_round_price(price) else "Repair/Exchange"

    if price and price >= 10000:
        return "Outright"

    if price and is_round_price(price):
        return "Exchange"

    return "Repair/Other"

def summarize_price_buckets(rows, side):
    buckets = defaultdict(list)

    for row in rows:
        if engine.row_is_cancelled(row):
            continue

        price = engine.row_price(row, side)
        if not price or price <= 1:
            continue

        cond = engine.row_condition(row) or "UNK"
        bucket = classify_transaction(row, side)
        dt = engine.row_date(row)
        buckets[(cond, bucket)].append((price, dt))

    for (cond, bucket), records in sorted(buckets.items()):
        prices = sorted([p for p, d in records])
        dates = [d for p, d in records if d]
        latest = max(dates).strftime("%b %Y") if dates else "No date"

        print(f"{cond} | {bucket}")
        print(f"  Count: {len(prices)}")
        print(f"  Range: {engine.fmt_money(min(prices))} - {engine.fmt_money(max(prices))}")
        print(f"  Median: {engine.fmt_money(median(prices))}")
        print(f"  Latest: {latest}")
        print()

def main():
    incoming = load_csv("DATA/incoming_quotes.csv")
    outgoing = load_csv("DATA/outgoing_quotes.csv")
    po = load_csv("DATA/purchase_orders.csv")
    sales = load_csv("DATA/sales_orders.csv")

    incoming_index = engine.build_part_index(incoming, ["PART #", "Part #", "Part Number", "PART NUMBER", "P/N", "PN"])
    outgoing_index = engine.build_part_index(outgoing, ["Part #", "PART #", "Part Number", "PART NUMBER", "P/N", "PN"])
    po_index = engine.build_part_index(po, engine.PART_FIELD_NAMES)
    sales_index = engine.build_part_index(sales, engine.PART_FIELD_NAMES)

    for part in PARTS:
        print("=" * 70)
        print(f"PART: {part}")
        print("=" * 70)

        print("\nBUY / PO PRICE BUCKETS")
        summarize_price_buckets(engine.get_purchase_history_matches(po_index, part), "buy")

        print("\nSELL / SALES PRICE BUCKETS")
        summarize_price_buckets(engine.get_sales_history_matches(sales_index, part), "sell")

        print("\nINCOMING QUOTE PRICE BUCKETS")
        summarize_price_buckets(engine.get_incoming_matches(incoming_index, part), "buy")

        print("\nOUTGOING QUOTE PRICE BUCKETS")
        summarize_price_buckets(engine.get_outgoing_matches(outgoing_index, part), "sell")

if __name__ == "__main__":
    main()