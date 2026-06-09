import streamlit as st
import pandas as pd
from pathlib import Path
from statistics import median
from collections import defaultdict, Counter
from datetime import datetime

st.set_page_config(page_title="Bereon Aviation Intelligence", layout="wide")

DATA_DIR = Path("DATA")

VISIBLE_CONDITIONS = ["OH", "RP", "IN", "NE"]

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
    "new_item": "NE",
    "new item": "NE",
    "new": "NE",
    "ne": "NE",
    "serviceable": "SV",
    "sv": "SV",
    "as removed": "AR",
    "as_removed": "AR",
    "ar": "AR",
}

COND_RANK = {
    "NE": 6,
    "OH": 5,
    "RP": 4,
    "SV": 3,
    "IN": 2,
    "AR": 1,
    "": 0,
}

INCOMING_FILE = "incoming_quotes.csv"
OUTGOING_FILE = "outgoing_quotes.csv"
PO_FILE = "purchase_orders.csv"
SO_FILE = "sales_orders.csv"


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


def parse_date(value):
    try:
        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            return None
        return dt
    except:
        return None


def normalize_cond(value):
    text = clean(value).lower()
    return COND_MAP.get(text, clean(value).upper())


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


@st.cache_data
def load_all_data():
    incoming = read_csv_file(INCOMING_FILE)
    outgoing = read_csv_file(OUTGOING_FILE)
    purchase_orders = read_csv_file(PO_FILE)
    sales_orders = read_csv_file(SO_FILE)

    return incoming, outgoing, purchase_orders, sales_orders


def exact_part_filter(df, column, part):
    if df.empty or column not in df.columns:
        return pd.DataFrame()

    search = part.strip().upper()
    mask = df[column].astype(str).str.strip().str.upper() == search

    return df.loc[mask].copy()


def incoming_matches(incoming, part):
    return exact_part_filter(incoming, "PART #", part)


def outgoing_matches(outgoing, part):
    return exact_part_filter(outgoing, "Part #", part)


def po_matches(po, part):
    matches = exact_part_filter(po, "PART NUMBER", part)

    if "CANCELLED" in matches.columns:
        matches = matches[
            ~matches["CANCELLED"].astype(str).str.lower().isin(
                ["true", "yes", "y", "1", "cancelled", "canceled"]
            )
        ]

    return matches


def so_matches(so, part):
    matches = exact_part_filter(so, "PART #", part)

    if "CANCELLED" in matches.columns:
        matches = matches[
            ~matches["CANCELLED"].astype(str).str.lower().isin(
                ["true", "yes", "y", "1", "cancelled", "canceled"]
            )
        ]

    return matches


def condition_counts(df, cond_col):
    counts = Counter()

    if df.empty or cond_col not in df.columns:
        return counts

    for value in df[cond_col]:
        cond = normalize_cond(value)
        if cond:
            counts[cond] += 1

    return counts


def pricing_by_condition(df, cond_col, price_cols):
    by_cond = defaultdict(list)

    if df.empty or cond_col not in df.columns:
        return by_cond

    for _, row in df.iterrows():
        cond = normalize_cond(row.get(cond_col, ""))

        if cond not in VISIBLE_CONDITIONS:
            continue

        price = None

        for price_col in price_cols:
            if price_col in row:
                price = money(row.get(price_col))
                if price and price > 1:
                    break

        if price and price > 1:
            by_cond[cond].append(price)

    return by_cond


def guidance_table(by_cond, mode):
    rows = []

    for cond in VISIBLE_CONDITIONS:
        prices = by_cond.get(cond, [])

        if not prices:
            continue

        prices = sorted(prices)

        if len(prices) >= 4:
            med = median(prices)
            prices = [p for p in prices if med * 0.50 <= p <= med * 1.50]

        if not prices:
            continue

        med = median(prices)

        if mode == "buy":
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


def best_value_from_incoming(df):
    rows = []

    if df.empty:
        return pd.DataFrame()

    for _, row in df.iterrows():
        cond = normalize_cond(row.get("COND", ""))
        price = money(row.get("COST PER UNIT"))

        if not price:
            price = money(row.get("EXCH. FEE"))

        if cond not in VISIBLE_CONDITIONS or not price:
            continue

        score = 0
        score += COND_RANK.get(cond, 0) * 25
        score -= price / 1000

        qty = money(row.get("QTY"))
        if qty and qty >= 2:
            score += 5

        warranty = clean(row.get("WARRANTY"))
        if "12" in warranty or "year" in warranty.lower():
            score += 15
        elif "6" in warranty:
            score += 8
        elif warranty:
            score += 3

        rows.append({
            "Vendor": clean(row.get("VENDOR")),
            "Condition": cond,
            "Price": fmt_money(price),
            "Qty": clean(row.get("QTY")),
            "Tagged By": clean(row.get("TAGGED BY")),
            "Tag Date": clean(row.get("TAG DATE")),
            "Warranty": warranty,
            "Bereon Score": round(score, 2),
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Bereon Score", ascending=False)


def cheapest_usable_from_incoming(df):
    rows = []

    for _, row in df.iterrows():
        cond = normalize_cond(row.get("COND", ""))
        price = money(row.get("COST PER UNIT"))

        if not price:
            price = money(row.get("EXCH. FEE"))

        if cond not in VISIBLE_CONDITIONS or not price:
            continue

        rows.append({
            "Vendor": clean(row.get("VENDOR")),
            "Condition": cond,
            "Price": price,
            "Price Display": fmt_money(price),
            "Qty": clean(row.get("QTY")),
            "Tag Date": clean(row.get("TAG DATE")),
            "Warranty": clean(row.get("WARRANTY")),
        })

    if not rows:
        return pd.DataFrame()

    df_out = pd.DataFrame(rows).sort_values("Price", ascending=True)
    return df_out.drop(columns=["Price"])


def last_record(df, date_col):
    if df.empty or date_col not in df.columns:
        return None

    temp = df.copy()
    temp["_parsed_date"] = temp[date_col].apply(parse_date)
    temp = temp.dropna(subset=["_parsed_date"])

    if temp.empty:
        return None

    temp = temp.sort_values("_parsed_date", ascending=False)
    return temp.iloc[0]


def show_metric_row(records):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Incoming Quotes", records["incoming"])
    c2.metric("Outgoing Quotes", records["outgoing"])
    c3.metric("Purchase Orders", records["po"])
    c4.metric("Sales Orders", records["so"])


def show_last_purchase(po_df):
    st.subheader("Last Purchase")

    last = last_record(po_df, "DATE CREATED")

    if last is None:
        st.info("No purchase history found.")
        return

    price = money(last.get("EXCH FEE / COST EA"))
    if not price:
        price = money(last.get("OUTRIGHT VALUE"))

    st.write(
        f"**{clean(last.get('VENDOR'))}** | "
        f"{normalize_cond(last.get('CONDITION'))} | "
        f"{fmt_money(price)} | "
        f"{clean(last.get('DATE CREATED'))}"
    )


def show_last_sale(so_df):
    st.subheader("Last Sale")

    last = last_record(so_df, "DATE CREATED")

    if last is None:
        st.info("No sales history found.")
        return

    price = money(last.get("EXCH FEE / SALES EA"))
    if not price:
        price = money(last.get("OUTRIGHT VALUE"))
    if not price:
        price = money(last.get("AMOUNT PAID"))

    st.write(
        f"**{clean(last.get('CUSTOMER'))}** | "
        f"{normalize_cond(last.get('CD'))} | "
        f"{fmt_money(price)} | "
        f"{clean(last.get('DATE CREATED'))}"
    )


def intelligence_search():
    st.title("Bereon Intelligence Search")
    st.caption("One part number search across buying, quoting, purchase history, and sales history.")

    incoming, outgoing, po, so = load_all_data()

    with st.expander("Backend data status", expanded=False):
        st.write(f"Incoming Quotes: {len(incoming):,} rows")
        st.write(f"Outgoing Quotes: {len(outgoing):,} rows")
        st.write(f"Purchase Orders: {len(po):,} rows")
        st.write(f"Sales Orders: {len(so):,} rows")

    part = st.text_input("Search Part Number", placeholder="Example: 3202222-1")

    if not part:
        return

    inc = incoming_matches(incoming, part)
    out = outgoing_matches(outgoing, part)
    po_part = po_matches(po, part)
    so_part = so_matches(so, part)

    st.success(f"Search complete for {part.upper()}")

    show_metric_row({
        "incoming": len(inc),
        "outgoing": len(out),
        "po": len(po_part),
        "so": len(so_part),
    })

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Executive Summary",
        "Buy Intelligence",
        "Quote Intelligence",
        "Purchase History",
        "Sales History",
    ])

    with tab1:
        st.header("Executive Summary")

        col1, col2 = st.columns(2)

        with col1:
            show_last_purchase(po_part)

        with col2:
            show_last_sale(so_part)

        st.subheader("Condition Snapshot")

        incoming_counts = condition_counts(inc, "COND")
        outgoing_counts = condition_counts(out, "Condition")
        po_counts = condition_counts(po_part, "CONDITION")
        so_counts = condition_counts(so_part, "CD")

        snapshot_rows = []

        for cond in ["NE", "OH", "RP", "IN", "SV", "AR"]:
            total = (
                incoming_counts.get(cond, 0)
                + outgoing_counts.get(cond, 0)
                + po_counts.get(cond, 0)
                + so_counts.get(cond, 0)
            )

            if total:
                snapshot_rows.append({
                    "Condition": cond,
                    "Incoming Quotes": incoming_counts.get(cond, 0),
                    "Outgoing Quotes": outgoing_counts.get(cond, 0),
                    "Purchase Orders": po_counts.get(cond, 0),
                    "Sales Orders": so_counts.get(cond, 0),
                    "Total": total,
                })

        if snapshot_rows:
            st.dataframe(pd.DataFrame(snapshot_rows), use_container_width=True)
        else:
            st.info("No condition data found.")

    with tab2:
        st.header("Buy Intelligence")

        incoming_buy = pricing_by_condition(
            inc,
            "COND",
            ["COST PER UNIT", "EXCH. FEE"],
        )

        po_buy = pricing_by_condition(
            po_part,
            "CONDITION",
            ["EXCH FEE / COST EA", "OUTRIGHT VALUE"],
        )

        st.subheader("Incoming Quote Buy Guidance")
        incoming_guidance = guidance_table(incoming_buy, "buy")

        if incoming_guidance.empty:
            st.info("No incoming quote pricing found.")
        else:
            st.dataframe(incoming_guidance, use_container_width=True)

        st.subheader("Purchase Order Buy Guidance")
        po_guidance = guidance_table(po_buy, "buy")

        if po_guidance.empty:
            st.info("No purchase order pricing found.")
        else:
            st.dataframe(po_guidance, use_container_width=True)

        st.subheader("Best Value Options")
        best_value = best_value_from_incoming(inc)

        if best_value.empty:
            st.info("No best value options found.")
        else:
            st.dataframe(best_value.head(15), use_container_width=True)

        st.subheader("Cheapest Usable")
        cheapest = cheapest_usable_from_incoming(inc)

        if cheapest.empty:
            st.info("No cheapest usable options found.")
        else:
            st.dataframe(cheapest.head(10), use_container_width=True)

    with tab3:
        st.header("Quote Intelligence")

        outgoing_sell = pricing_by_condition(
            out,
            "Condition",
            ["Price Per Unit"],
        )

        sales_sell = pricing_by_condition(
            so_part,
            "CD",
            ["EXCH FEE / SALES EA", "OUTRIGHT VALUE", "AMOUNT PAID"],
        )

        st.subheader("Outgoing Quote Guidance")
        out_guidance = guidance_table(outgoing_sell, "sell")

        if out_guidance.empty:
            st.info("No outgoing quote pricing found.")
        else:
            st.dataframe(out_guidance, use_container_width=True)

        st.subheader("Completed Sales Guidance")
        sales_guidance = guidance_table(sales_sell, "sell")

        if sales_guidance.empty:
            st.info("No completed sales pricing found.")
        else:
            st.dataframe(sales_guidance, use_container_width=True)

        if not out.empty:
            with st.expander("Raw outgoing quotes"):
                st.dataframe(out.head(100), use_container_width=True)

    with tab4:
        st.header("Purchase History")

        if po_part.empty:
            st.info("No purchase order history found.")
        else:
            st.dataframe(po_part.head(100), use_container_width=True)

    with tab5:
        st.header("Sales History")

        if so_part.empty:
            st.info("No sales order history found.")
        else:
            st.dataframe(so_part.head(100), use_container_width=True)


def procurement_page():
    st.title("Procurement Intelligence")
    st.caption("Original dedicated buying view")

    incoming = read_csv_file(INCOMING_FILE)

    st.success(f"Using saved file: DATA/{INCOMING_FILE} — {len(incoming):,} rows")

    part = st.text_input("Search Part Number", key="procurement_part")

    if not part:
        return

    inc = incoming_matches(incoming, part)

    if inc.empty:
        st.warning("No matching records found.")
        return

    st.success(f"Found {len(inc):,} record(s) for {part.upper()}")

    buy = pricing_by_condition(inc, "COND", ["COST PER UNIT", "EXCH. FEE"])
    st.subheader("Buy Range Recommendations")
    guidance = guidance_table(buy, "buy")

    if guidance.empty:
        st.info("No usable pricing found.")
    else:
        st.dataframe(guidance, use_container_width=True)

    st.subheader("Best Value Options")
    best_value = best_value_from_incoming(inc)

    if best_value.empty:
        st.info("No best value options found.")
    else:
        st.dataframe(best_value.head(20), use_container_width=True)


def quote_page():
    st.title("Quote Intelligence")

    outgoing = read_csv_file(OUTGOING_FILE)

    st.success(f"Using saved file: DATA/{OUTGOING_FILE} — {len(outgoing):,} rows")

    part = st.text_input("Search Part Number", key="quote_part")

    if not part:
        return

    out = outgoing_matches(outgoing, part)

    if out.empty:
        st.warning("No matching quote records found.")
        return

    st.success(f"Found {len(out):,} quote record(s) for {part.upper()}")

    sell = pricing_by_condition(out, "Condition", ["Price Per Unit"])
    guidance = guidance_table(sell, "sell")

    if guidance.empty:
        st.info("No usable quote pricing found.")
    else:
        st.dataframe(guidance, use_container_width=True)


def market_page():
    st.title("Market Intelligence")
    st.info("Market Intelligence will later include ILS call-list ranking and supplier scoring.")
    st.write("For now, use Bereon Intelligence Search for the combined view.")


def settings_page():
    st.title("Settings")
    st.write("Bereon backend mode: CSV")
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
        "Bereon Intelligence Search",
        "Procurement Intelligence",
        "Quote Intelligence",
        "Market Intelligence",
        "Settings",
    ],
)

if page == "Bereon Intelligence Search":
    intelligence_search()
elif page == "Procurement Intelligence":
    procurement_page()
elif page == "Quote Intelligence":
    quote_page()
elif page == "Market Intelligence":
    market_page()
elif page == "Settings":
    settings_page()