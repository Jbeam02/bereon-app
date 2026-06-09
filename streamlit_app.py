import streamlit as st
import pandas as pd
from statistics import median

st.set_page_config(page_title="Bereon Aviation Intelligence", layout="wide")

CONDITION_RANK = {
    "NE": 6,
    "OH": 5,
    "RP": 4,
    "SV": 3,
    "IN": 2,
    "AR": 1,
    "": 0,
}

VISIBLE_CONDITIONS = ["OH", "RP", "IN", "SV", "NE"]

PART_COLUMNS = [
    "PART #", "Part #", "Part Number", "PART NUMBER", "P/N", "PN",
    "Part No", "PART NO", "Item", "Item Number", "Part"
]

COND_COLUMNS = ["Condition", "CONDITION", "Cond", "COND"]

PRICE_COLUMNS = [
    "Price", "PRICE", "Cost", "COST", "Unit Cost", "COST PER UNIT",
    "Cost Per Unit", "Unit Price", "Amount", "OUTRIGHT VALUE",
    "EXCH FEE / COST EA"
]

DATE_COLUMNS = [
    "Date", "DATE", "Quote Date", "PO Date", "SO Date",
    "Created Date", "Date Created", "Order Date"
]

VENDOR_COLUMNS = [
    "Vendor", "VENDOR", "Vendor Name", "Company", "Supplier",
    "Purchased From"
]


def clean(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def money(value):
    try:
        if pd.isna(value):
            return None
        text = str(value).replace("$", "").replace(",", "").strip()
        if text == "":
            return None
        return float(text)
    except:
        return None


def fmt_money(value):
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def find_column(df, possible_names):
    compact_cols = {c.lower().replace(" ", "").replace("/", "").replace("#", ""): c for c in df.columns}

    for name in possible_names:
        key = name.lower().replace(" ", "").replace("/", "").replace("#", "")
        if key in compact_cols:
            return compact_cols[key]

    for col in df.columns:
        col_key = col.lower().replace(" ", "").replace("/", "").replace("#", "")
        for name in possible_names:
            key = name.lower().replace(" ", "").replace("/", "").replace("#", "")
            if key in col_key or col_key in key:
                return col

    return None


@st.cache_data
def read_file(uploaded_file):
    if uploaded_file is None:
        return pd.DataFrame()

    name = uploaded_file.name.lower()

    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(uploaded_file)
    else:
        return pd.DataFrame()

    df = df.fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def filter_part(df, part_number):
    if df.empty or not part_number:
        return pd.DataFrame()

    part_col = find_column(df, PART_COLUMNS)

    if part_col is None:
        st.warning("No part-number column found. Select one manually.")
        part_col = st.selectbox("Part number column", df.columns)

    mask = df[part_col].astype(str).str.strip().str.upper() == part_number.strip().upper()
    return df.loc[mask].copy()


def get_condition(row):
    for col in COND_COLUMNS:
        if col in row:
            return clean(row[col]).upper()
    return ""


def get_price(row):
    for col in PRICE_COLUMNS:
        if col in row:
            value = money(row[col])
            if value is not None and value > 1:
                return value
    return None


def get_vendor(row):
    for col in VENDOR_COLUMNS:
        if col in row:
            return clean(row[col])
    return ""


def pricing_guidance(df):
    results = {}

    if df.empty:
        return results

    for _, row in df.iterrows():
        cond = get_condition(row)
        price = get_price(row)

        if cond not in VISIBLE_CONDITIONS:
            continue

        if price is None:
            continue

        if cond not in results:
            results[cond] = []

        results[cond].append(price)

    guidance = {}

    for cond, prices in results.items():
        prices = sorted(prices)

        if len(prices) >= 4:
            med = median(prices)
            prices = [p for p in prices if med * 0.5 <= p <= med * 1.5]

        if not prices:
            continue

        med = median(prices)

        guidance[cond] = {
            "low": med * 0.90,
            "target": med,
            "high": med * 1.10,
            "count": len(prices),
        }

    return guidance


def best_buy_options(df):
    if df.empty:
        return pd.DataFrame()

    rows = []

    for _, row in df.iterrows():
        cond = get_condition(row)
        price = get_price(row)
        vendor = get_vendor(row)

        if cond not in VISIBLE_CONDITIONS:
            continue

        if price is None:
            continue

        score = 0
        score += CONDITION_RANK.get(cond, 0) * 25
        score -= price / 1000

        rows.append({
            "Vendor": vendor,
            "Condition": cond,
            "Price": price,
            "Bereon Score": round(score, 2),
        })

    if not rows:
        return pd.DataFrame()

    output = pd.DataFrame(rows)
    output = output.sort_values("Bereon Score", ascending=False)
    return output


def show_pricing_table(title, guidance):
    st.subheader(title)

    if not guidance:
        st.info("No usable pricing records found.")
        return

    rows = []

    for cond in VISIBLE_CONDITIONS:
        if cond not in guidance:
            continue

        info = guidance[cond]

        rows.append({
            "Condition": cond,
            "Low": fmt_money(info["low"]),
            "Target": fmt_money(info["target"]),
            "High": fmt_money(info["high"]),
            "Records": info["count"],
        })

    st.dataframe(pd.DataFrame(rows), use_container_width=True)


def dashboard_page():
    st.title("Bereon Aviation Intelligence Platform")
    st.caption("Internal aviation sourcing, buying, quoting, and market intelligence for Support Air.")

    st.write("Use the sidebar to open Procurement Intelligence, Quote Intelligence, or Market Intelligence.")


def procurement_page():
    st.title("Procurement Intelligence")
    st.caption("What To Buy For")

    uploaded_file = st.file_uploader(
        "Upload incoming quotes, PO history, or ILS market Excel/CSV file",
        type=["xlsx", "xls", "csv"],
        key="procurement_file"
    )

    df = read_file(uploaded_file)

    if df.empty:
        st.info("Upload a file to begin.")
        return

    st.success(f"Loaded {len(df):,} rows")
    st.dataframe(df.head(50), use_container_width=True)

    part_number = st.text_input("Enter exact part number")

    if not part_number:
        return

    matches = filter_part(df, part_number)

    if matches.empty:
        st.warning("No matching records found.")
        return

    st.success(f"Found {len(matches):,} matching record(s)")

    guidance = pricing_guidance(matches)
    show_pricing_table("Buy Range Recommendations", guidance)

    ranked = best_buy_options(matches)

    st.subheader("Best Value Options")

    if ranked.empty:
        st.info("No usable buy options found.")
    else:
        st.dataframe(ranked.head(20), use_container_width=True)

        best = ranked.iloc[0]
        st.success(
            f"Best Value: {best['Vendor']} | {best['Condition']} | {fmt_money(best['Price'])}"
        )

    with st.expander("Matching raw records"):
        st.dataframe(matches.head(100), use_container_width=True)


def quote_page():
    st.title("Quote Intelligence")
    st.caption("What To Quote")

    uploaded_file = st.file_uploader(
        "Upload outgoing quote history, sales history, or quote Excel/CSV file",
        type=["xlsx", "xls", "csv"],
        key="quote_file"
    )

    df = read_file(uploaded_file)

    if df.empty:
        st.info("Upload a file to begin.")
        return

    st.success(f"Loaded {len(df):,} rows")
    st.dataframe(df.head(50), use_container_width=True)

    part_number = st.text_input("Enter exact part number", key="quote_part")

    if not part_number:
        return

    matches = filter_part(df, part_number)

    if matches.empty:
        st.warning("No matching quote records found.")
        return

    st.success(f"Found {len(matches):,} matching quote record(s)")

    guidance = pricing_guidance(matches)
    show_pricing_table("Quote Range Recommendations", guidance)

    prices = []

    for _, row in matches.iterrows():
        price = get_price(row)
        if price is not None:
            prices.append(price)

    if prices:
        st.metric("Average Quote", fmt_money(sum(prices) / len(prices)))
        st.metric("Median Quote", fmt_money(median(prices)))
        st.metric("High Quote", fmt_money(max(prices)))
        st.metric("Low Quote", fmt_money(min(prices)))

    with st.expander("Matching raw quote records"):
        st.dataframe(matches.head(100), use_container_width=True)


def market_page():
    st.title("Market Intelligence")
    st.caption("Simple market file viewer and part lookup")

    uploaded_file = st.file_uploader(
        "Upload market file",
        type=["xlsx", "xls", "csv"],
        key="market_file"
    )

    df = read_file(uploaded_file)

    if df.empty:
        st.info("Upload a file to begin.")
        return

    st.success(f"Loaded {len(df):,} rows")
    st.dataframe(df.head(100), use_container_width=True)

    part_number = st.text_input("Enter exact part number", key="market_part")

    if part_number:
        matches = filter_part(df, part_number)

        if matches.empty:
            st.warning("No matching market records found.")
        else:
            st.success(f"Found {len(matches):,} matching record(s)")
            st.dataframe(matches.head(100), use_container_width=True)


def settings_page():
    st.title("Settings")
    st.write("Bereon v1")
    st.write("Browser-safe mode is ON.")
    st.write("Large files are previewed at 50–100 rows to prevent crashing.")


st.sidebar.title("Bereon")
page = st.sidebar.radio(
    "Navigation",
    [
        "Dashboard",
        "Procurement Intelligence",
        "Quote Intelligence",
        "Market Intelligence",
        "Settings",
    ]
)

if page == "Dashboard":
    dashboard_page()
elif page == "Procurement Intelligence":
    procurement_page()
elif page == "Quote Intelligence":
    quote_page()
elif page == "Market Intelligence":
    market_page()
elif page == "Settings":
    settings_page()