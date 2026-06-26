import pandas as pd
from collections import defaultdict
from datetime import datetime
import bereon_engine as engine

PART = "5145-1-64"

BAD_QUOTE_VALUES = {
    "NB", "N/B", "NO BID", "NO QUOTE", "NQ",
    "NO STOCK", "SOLD", "SOLD ALREADY", "CANNOT LOCATE"
}

def load_csv(path):
    df = pd.read_csv(path, low_memory=False).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df.to_dict("records")

def grade(score):
    if score >= 95:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"

def is_bad_quote(row):
    text_values = [
        str(row.get("TYPE", "")).upper().strip(),
        str(row.get("COST PER UNIT", "")).upper().strip(),
        str(row.get("EXCH. FEE", "")).upper().strip(),
    ]

    if any(v in BAD_QUOTE_VALUES for v in text_values):
        return True

    for field in ["COST PER UNIT", "EXCH. FEE"]:
        price = engine.money(row.get(field, ""))
        if price is not None and price < 1:
            return True

    return False

def vendor(row):
    return engine.normalize_vendor(row.get("VENDOR", ""))

def part_number_from_quote(row):
    return str(row.get("PART #", "")).strip().upper()

def part_number_from_po(row):
    return str(row.get("PART NUMBER", "")).strip().upper()

def row_dt(row):
    return engine.parse_date(
        row.get("DATE CREATED", "")
        or row.get("CREATED/UPDATED", "")
        or row.get("DATE RECEIVED", "")
    )

def build_scores(part):
    incoming = load_csv("DATA/incoming_quotes.csv")
    po_rows = load_csv("DATA/purchase_orders.csv")

    stats = defaultdict(lambda: {
        "quotes": 0,
        "part_quotes": 0,
        "bad_quotes": 0,
        "pos": 0,
        "part_pos": 0,
        "recent_pos": 0,
        "recent_quotes": 0,
    })

    today = datetime.today()

    for row in incoming:
        v = vendor(row)
        if not v:
            continue

        stats[v]["quotes"] += 1

        if part_number_from_quote(row) == part.upper():
            stats[v]["part_quotes"] += 1

        if is_bad_quote(row):
            stats[v]["bad_quotes"] += 1

        dt = row_dt(row)
        if dt and (today - dt).days <= 730:
            stats[v]["recent_quotes"] += 1

    for row in po_rows:
        if engine.row_is_cancelled(row):
            continue

        v = vendor(row)
        if not v:
            continue

        stats[v]["pos"] += 1

        if part_number_from_po(row) == part.upper():
            stats[v]["part_pos"] += 1

        dt = row_dt(row)
        if dt and (today - dt).days <= 730:
            stats[v]["recent_pos"] += 1

    scored = []

    for v, s in stats.items():
        quotes = s["quotes"]
        pos = s["pos"]
        bad = s["bad_quotes"]

        conversion = pos / quotes if quotes else 0
        reliability = (quotes - bad) / quotes if quotes else 0

        conversion_score = min(conversion / 0.35, 1) * 35
        part_score = min(s["part_pos"] / 5, 1) * 25
        reliability_score = reliability * 15
        relationship_score = min(pos / 250, 1) * 15
        recent_score = min(s["recent_pos"] / 25, 1) * 10

        total = (
            conversion_score
            + part_score
            + reliability_score
            + relationship_score
            + recent_score
        )

        if s["part_pos"] == 0 and s["part_quotes"] == 0:
            total -= 10

        if bad >= 25:
            total -= 10
        elif bad >= 10:
            total -= 5

        total = max(0, min(100, total))

        scored.append((total, v, s, conversion, reliability))

    scored.sort(reverse=True, key=lambda x: x[0])
    return scored

def main():
    scored = build_scores(PART)

    print(f"\nVendor Score Lab for {PART}")
    print("=" * 70)

    for i, (score, v, s, conversion, reliability) in enumerate(scored[:20], start=1):
        print(f"{i}. {v} | Grade {grade(score)} | Score {score:.1f}")
        print(f"   Quote→PO: {conversion:.1%}")
        print(f"   Reliability: {reliability:.1%}")
        print(f"   Quotes: {s['quotes']} | POs: {s['pos']}")
        print(f"   Same-part quotes: {s['part_quotes']} | Same-part POs: {s['part_pos']}")
        print(f"   Bad quotes: {s['bad_quotes']}")
        print(f"   Recent POs: {s['recent_pos']}")
        print()

if __name__ == "__main__":
    main()