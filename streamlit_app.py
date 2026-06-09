import streamlit as st
import pandas as pd
from pathlib import Path
from statistics import median
from collections import defaultdict

st.set_page_config(page_title="Bereon Aviation Intelligence", layout="wide")

DATA_DIR = Path("DATA")

VISIBLE_CONDITIONS = ["OH", "RP", "IN", "SV", "NE"]

COND_MAP = {
    "overhauled": "OH",
    "overhaul": "OH",
    "oh": "OH",
    "repaired": "RP",
    "repair": "RP",
    "rp": "RP",
    "inspected": "IN",
    "inspected/tested": "IN",
    "in": "IN",
    "serviceable": "SV",
    "sv": "SV",
    "new_item": "NE",
    "new item": "NE",
    "new": "NE",
    "ne": "NE",
    "factory new": "NE",
    "as removed": "AR",
    "as_removed": "AR",
    "ar": "AR",
}

CONDITION_RANK = {
    "NE": 6,
    "OH": 5,
    "RP": 4,
    "SV": 3,
    "IN": 2,
    "AR": 1,
    "": 0,
}

PART_COLUMNS = [
    "PART #", "Part #", "Part Number", "PART NUMBER", "P/N", "PN",
    "Part No", "PART NO", "Part", "Item", "Item Number"
]

COND_COLUMNS = [
    "Condition", "CONDITION", "Cond", "COND", "CD", "Code"
]

BUY_PRICE_COLUMNS = [
    "EXCH FEE / COST EA",
    "EXCH. FEE",
    "COST PER UNIT",
    "Cost Per Unit",
    "Unit Cost",
    "Cost",
    "Purchase Price",
    "PO Price",
    "Price Paid",
    "Unit Price",
    "OUTRIGHT VALUE",
    "Outright Value",
    "Price",
    "Amount",
]

SELL_PRICE_COLUMNS = [
    "EXCH FEE / SALES EA",
    "Exchange Fee / Sales EA",
    "Price Per Unit",
    "PRICE PER UNIT",
    "Unit Price",
    "Unit Amount",
    "Sell Price",
    "Sale Price",
    "Sales Price",
    "SO Price",
    "Invoice Price",
    "Sold Price",
    "Sold For",
    "OUTRIGHT VALUE",
    "Outright Value",
    "Price",
    "Amount",
    "Revenue",
    "Line Total",
    "Total",
    "Net",
]

VENDOR_COLUMNS = [
    "Vendor", "VENDOR", "Vendor Name", "Company", "Supplier",
    "Purchased From", "PURCHASED FROM"
]

CUSTOMER_COLUMNS = [
    "Customer", "CUSTOMER", "Customer Name", "Company"
]

DATE_COLUMNS = [
    "Date", "DATE", "Quote Date", "QUOTE DATE", "CREATED/UPDATED",
    "Created/Updated", "Created Date", "Date Created", "PO Date",
    "Order Date", "SO Date", "Sales Date", "Invoice Date"
]

TAG_DATE_COLUMNS = [
    "TAG DATE", "Tag Date", "Tag", "Cert Date", "Certification Date"
]

TAGGED_BY_COLUMNS = [
    "TAGGED BY", "Tagged By", "Tag By"
]


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def money(value):
    try:
        text = clean(value)
        text = text.replace("$", "").replace(",", "").strip()
        if text == "":
            return None
        return float(text)
    except:
        return None


def fmt_money(value):
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def compact(value):
    return str(value).lower().replace(" ", "").replace("/", "").replace("#", "").replace(".", "").replace("_", "")


def find_column(df, possible_names):
    if df.empty:
        return None

    for col in df.columns:
        for name in possible_names:
            if clean(col).lower() == name.lower():
                return col

    compact_map = {compact(col): col for col in df.columns}

    for name in possible_names:
        key = compact(name)
        if key in compact_map:
            return compact_map[key]

    for col in df.columns:
        col_key = compact(col)
        for name in possible_names:
            name_key = compact(name)
            if name_key and (name_key in col_key or col_key in name_key):
                return col

    return None


@st.cache_data
def read_csv_file(filename):
    path = DATA_DIR / filename

    if not path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, low_memory=False, encoding="utf-8")
    except:
        try:
            df = pd.read_csv(path, low_memory=False, encoding="latin1")
        except Exception as e:
            st.error(f"Could not read DATA/{filename}: {e}")
            return pd.DataFrame()

    df = df.fillna("")
    df.columns = [clean(c) for c in df.columns]
    return df


def load_backend_file(filename):
    df = read_csv_file(filename)

    if df.empty:
        st.warning(f"No saved DATA/{filename} found or file could not be read.")
    else:
        st.success(f"Using saved file: DATA/{filename} — {len(df):,} rows")

    return df


def get_value(row, possible_columns):
    for col in possible_columns:
        if col in row:
            return clean(row[col])

    row_keys = list(row.index)

    for key in row_keys:
        for col in possible_columns:
            if clean(key).lower() == col.lower():
                return clean(row[key])

    for key in row_keys:
        key_compact = compact(key)
        for col in possible_columns:
            col_compact = compact(col)
            if col_compact and (col_compact in key_compact or key_compact in col_compact):
                return clean(row[key])

    return ""


def get_condition(row):
    raw = get_value(row, COND_COLUMNS)
    raw_clean = raw.lower().strip()
    return COND_MAP.get(raw_clean, raw.upper())


def get_price(row, side="buy"):
    columns = BUY_PRICE_COLUMNS if side == "buy" else SELL_PRICE_COLUMNS

    for col in columns:
        value = get_value(row, [col])
        price = money(value)
        if price and price > 1:
            return price

    return None


def get_vendor(row):
    return get_value(row, VENDOR_COLUMNS)


def get_customer(row):
    return get_value(row, CUSTOMER_COLUMNS)


def filter_part(df, part_number):
    if df.empty or not part_number:
        return pd.DataFrame()

    part_col = find_column(df, PART_COLUMNS)

    if part_col is None:
        st.error("No part-number column found in this file.")
        return pd.DataFrame()

    search = part_number.strip().upper()
    mask = df[part_col].astype(str).str.strip().str.upper() == search

    return df.loc[mask].copy()


def pricing_guidance(matches, side="buy"):
    by_condition = defaultdict(list)

    for _, row in matches.iterrows():
        cond = get_condition(row)
        price = get_price(row, side=side)

        if cond in VISIBLE_CONDITIONS and price:
            by_condition[cond].append(price)

    rows = []

    for cond in VISIBLE_CONDITIONS:
        prices = by_condition.get(cond, [])

        if not prices:
            continue

        prices = sorted(prices)

        if len(prices) >= 4:
            med = median(prices)
            prices = [p for p in prices if med * 0.50 <= p <= med * 1.50]

        if not prices:
            continue

        med = median(prices)

        if side == "buy":
            rows.append({
                "Condition": cond,
                "Target Buy": fmt_money(med * 0.90),
                "Max Buy": fmt_money(med * 1.10),
                "Median": fmt_money(med),
                "Records": len(prices),
            })
        else:
            rows.append({
                "Condition": cond,
                "Low Quote": fmt_money(med * 0.90),
                "Suggested Quote": fmt_money(med),
                "High Quote": fmt_money(med * 1.10),
                "Records": len(prices),
            })

    return pd.DataFrame(rows)


def ranked_buy_options(matches):
    rows = []

    for _, row in matches.iterrows():
        cond = get_condition(row)
        price = get_price(row, side="buy")
        vendor = get_vendor(row)

        if cond not in VISIBLE_CONDITIONS or not price:
            continue

        score = 0
        score += CONDITION_RANK.get(cond, 0) * 25
        score -= price / 1000

        tag_date = get_value(row, TAG_DATE_COLUMNS)
        tagged_by = get_value(row, TAGGED_BY_COLUMNS)

        rows.append({
            "Vendor": vendor,
            "Condition": cond,
            "Price": fmt_money(price),
            "Tag Date": tag_date,
            "Tagged By": tagged_by,
            "Bereon Score": round(score, 2),
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Bereon Score", ascending=False)


def quote_stats(matches):
    prices = []

    for _, row in matches.iterrows():
        price = get_price(row, side="sell")
        if price:
            prices.append(price)

    if not prices:
        return None

    return {
        "average": sum(prices) / len(prices),
        "median": median(prices),
        "low": min(prices),
        "high": max(prices),
        "count": len(prices),
    }


def show_raw(matches):
    with st.expander("Raw matching records"):
        st.dataframe(matches.head(100), use_container_width=True)


def dashboard():
    st.title("Bereon Aviation Intelligence Platform")
    st.write("Search Support Air backend CSV data by part number.")
    st.info("Current mode: CSV backend files in DATA folder.")


def procurement():
    st.title("Procurement Intelligence")
    st.caption("What To Buy For")

    source = st.radio(
        "Data source",
        ["Incoming Quotes", "Purchase Orders"],
        horizontal=True,
    )

    if source == "Incoming Quotes":
        df = load_backend_file("incoming_quotes.csv")
        side = "buy"
    else:
        df = load_backend_file("purchase_orders.csv")
        side = "buy"

    if df.empty:
        return

    part = st.text_input("Search Part Number")

    if not part:
        return

    matches = filter_part(df, part)

    if matches.empty:
        st.warning("No matching records found.")
        return

    st.success(f"Found {len(matches):,} record(s) for {part.upper()}")

    guidance = pricing_guidance(matches, side=side)

    st.subheader("Buy Range Recommendations")

    if guidance.empty:
        st.info("No usable pricing found.")
    else:
        st.dataframe(guidance, use_container_width=True)

    st.subheader("Best Value Options")

    ranked = ranked_buy_options(matches)

    if ranked.empty:
        st.info("No ranked buy options found.")
    else:
        st.dataframe(ranked.head(20), use_container_width=True)

        best = ranked.iloc[0]
        st.success(
            f"Best Value: {best['Vendor']} | {best['Condition']} | {best['Price']}"
        )

    show_raw(matches)


def quote():
    st.title("Quote Intelligence")
    st.caption("What To Quote")

    df = load_backend_file("outgoing_quotes.csv")

    if df.empty:
        return

    part = st.text_input("Search Part Number", key="quote_part")

    if not part:
        return

    matches = filter_part(df, part)

    if matches.empty:
        st.warning("No matching quote records found.")
        return

    st.success(f"Found {len(matches):,} quote record(s) for {part.upper()}")

    st.subheader("Quote Range Recommendations")

    guidance = pricing_guidance(matches, side="sell")

    if guidance.empty:
        st.info("No usable quote pricing found.")
    else:
        st.dataframe(guidance, use_container_width=True)

    stats = quote_stats(matches)

    if stats:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Records", stats["count"])
        c2.metric("Average", fmt_money(stats["average"]))
        c3.metric("Median", fmt_money(stats["median"]))
        c4.metric("Low", fmt_money(stats["low"]))
        c5.metric("High", fmt_money(stats["high"]))

    show_raw(matches)


def market():
    st.title("Market Intelligence")
    st.caption("Sales history lookup for now")

    df = load_backend_file("sales_orders.csv")

    if df.empty:
        return

    part = st.text_input("Search Part Number", key="market_part")

    if not part:
        st.dataframe(df.head(100), use_container_width=True)
        return

    matches = filter_part(df, part)

    if matches.empty:
        st.warning("No matching sales records found.")
        return

    st.success(f"Found {len(matches):,} sales record(s) for {part.upper()}")

    guidance = pricing_guidance(matches, side="sell")

    if not guidance.empty:
        st.subheader("Sales-Based Quote Intelligence")
        st.dataframe(guidance, use_container_width=True)

    show_raw(matches)


def settings():
    st.title("Settings")
    st.write("Bereon CSV backend mode")
    st.write("Expected files:")
    st.code(
        "DATA/incoming_quotes.csv\n"
        "DATA/outgoing_quotes.csv\n"
        "DATA/purchase_orders.csv\n"
        "DATA/sales_orders.csv"
    )


st.sidebar.title("Bereon")

page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Procurement Intelligence",
        "Quote Intelligence",
        "Market Intelligence",
        "Settings",
    ],
)

if page == "Dashboard":
    dashboard()
elif page == "Procurement Intelligence":
    procurement()
elif page == "Quote Intelligence":
    quote()
elif page == "Market Intelligence":
    market()
elif page == "Settings":
    settings()