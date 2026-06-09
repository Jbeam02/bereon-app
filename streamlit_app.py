import streamlit as st
import pandas as pd
from pathlib import Path
from statistics import median

st.set_page_config(page_title="Bereon Aviation Intelligence", layout="wide")

DATA_DIR = Path("DATA")

CONDITIONS = ["OH", "RP", "IN", "SV", "NE"]

PART_COLUMNS = ["PART #", "Part #", "Part Number", "PART NUMBER", "P/N", "PN", "Part No", "PART NO", "Part"]
COND_COLUMNS = ["Condition", "CONDITION", "Cond", "COND"]
PRICE_COLUMNS = ["Price", "PRICE", "Cost", "COST", "Unit Cost", "Cost Per Unit", "COST PER UNIT", "Unit Price", "Amount", "OUTRIGHT VALUE"]
VENDOR_COLUMNS = ["Vendor", "VENDOR", "Vendor Name", "Company", "Supplier", "Purchased From"]


def clean(v):
    return "" if pd.isna(v) else str(v).strip()


def money(v):
    try:
        text = clean(v).replace("$", "").replace(",", "")
        return float(text) if text else None
    except:
        return None


def fmt_money(v):
    return "N/A" if v is None else f"${v:,.2f}"


def find_column(df, possible):
    for col in df.columns:
        for name in possible:
            if str(col).strip().lower() == name.strip().lower():
                return col

    for col in df.columns:
        c = str(col).lower().replace(" ", "").replace("/", "").replace("#", "")
        for name in possible:
            n = name.lower().replace(" ", "").replace("/", "").replace("#", "")
            if n in c or c in n:
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
    df.columns = [str(c).strip() for c in df.columns]
    return df


def filter_part(df, part_number):
    if df.empty or not part_number:
        return pd.DataFrame()

    part_col = find_column(df, PART_COLUMNS)

    if part_col is None:
        st.error("No part-number column found in this file.")
        return pd.DataFrame()

    mask = df[part_col].astype(str).str.strip().str.upper() == part_number.strip().upper()
    return df.loc[mask].copy()


def get_cell(row, columns):
    for col in columns:
        if col in row:
            return clean(row[col])
    return ""


def get_price(row):
    for col in PRICE_COLUMNS:
        if col in row:
            val = money(row[col])
            if val and val > 1:
                return val
    return None


def pricing_guidance(matches):
    by_cond = {}

    for _, row in matches.iterrows():
        cond = get_cell(row, COND_COLUMNS).upper()
        price = get_price(row)

        if cond in CONDITIONS and price:
            by_cond.setdefault(cond, []).append(price)

    rows = []

    for cond in CONDITIONS:
        prices = by_cond.get(cond, [])

        if not prices:
            continue

        med = median(prices)

        rows.append({
            "Condition": cond,
            "Low": fmt_money(med * 0.90),
            "Target": fmt_money(med),
            "High": fmt_money(med * 1.10),
            "Records": len(prices),
        })

    return pd.DataFrame(rows)


def ranked_buy_options(matches):
    rows = []
    rank = {"NE": 6, "OH": 5, "RP": 4, "SV": 3, "IN": 2}

    for _, row in matches.iterrows():
        cond = get_cell(row, COND_COLUMNS).upper()
        price = get_price(row)
        vendor = get_cell(row, VENDOR_COLUMNS)

        if cond not in CONDITIONS or not price:
            continue

        score = rank.get(cond, 0) * 25 - price / 1000

        rows.append({
            "Vendor": vendor,
            "Condition": cond,
            "Price": fmt_money(price),
            "Bereon Score": round(score, 2),
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Bereon Score", ascending=False)


def load_backend_file(filename):
    df = read_csv_file(filename)

    if df.empty:
        st.warning(f"No saved DATA/{filename} found or file could not be read.")
    else:
        st.success(f"Using saved file: DATA/{filename} — {len(df):,} rows")

    return df


def dashboard():
    st.title("Bereon Aviation Intelligence Platform")
    st.write("Search Support Air backend CSV data by part number.")


def procurement():
    st.title("Procurement Intelligence")
    st.caption("What To Buy For")

    source = st.radio("Data source", ["Incoming Quotes", "Purchase Orders"], horizontal=True)

    if source == "Incoming Quotes":
        df = load_backend_file("incoming_quotes.csv")
    else:
        df = load_backend_file("purchase_orders.csv")

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

    st.subheader("Buy Range Recommendations")
    guidance = pricing_guidance(matches)

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

    with st.expander("Raw matching records"):
        st.dataframe(matches.head(100), use_container_width=True)


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

    guidance = pricing_guidance(matches)

    st.subheader("Quote Range Recommendations")

    if guidance.empty:
        st.info("No usable quote pricing found.")
    else:
        st.dataframe(guidance, use_container_width=True)

    prices = [get_price(row) for _, row in matches.iterrows()]
    prices = [p for p in prices if p]

    if prices:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Average", fmt_money(sum(prices) / len(prices)))
        c2.metric("Median", fmt_money(median(prices)))
        c3.metric("Low", fmt_money(min(prices)))
        c4.metric("High", fmt_money(max(prices)))

    with st.expander("Raw matching records"):
        st.dataframe(matches.head(100), use_container_width=True)


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
    else:
        st.success(f"Found {len(matches):,} sales record(s)")
        st.dataframe(matches.head(100), use_container_width=True)


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