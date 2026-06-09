import re
import streamlit as st
import pandas as pd
from pathlib import Path
from statistics import median
from collections import defaultdict, Counter

st.set_page_config(page_title="Bereon Aviation Intelligence", layout="wide")

DATA_DIR = Path("DATA")

INCOMING_FILE = "incoming_quotes.csv"
OUTGOING_FILE = "outgoing_quotes.csv"
PO_FILE = "purchase_orders.csv"
SO_FILE = "sales_orders.csv"

VISIBLE_CONDITIONS = ["OH", "RP", "IN", "SV", "NE"]

COND_MAP = {
    "overhauled": "OH", "overhaul": "OH", "oh": "OH",
    "repaired": "RP", "repair": "RP", "rp": "RP",
    "inspected": "IN", "inspected/tested": "IN", "in": "IN",
    "serviceable": "SV", "sv": "SV",
    "new_item": "NE", "new item": "NE", "new": "NE", "ne": "NE",
    "ns": "NS",
    "as_removed": "AR", "as removed": "AR", "ar": "AR",
}

COND_RANK = {"NE": 6, "OH": 5, "RP": 4, "SV": 3, "IN": 2, "NS": 1, "AR": 0}

SISTER_COMPANIES = {
    "BROWARD AVIATION COMPANY",
    "AIR ACCESSORIES AND AVIONICS",
    "JET AIR MRO",
}


def clean(v):
    if pd.isna(v):
        return ""
    return str(v).strip()


def money(v):
    try:
        text = clean(v).replace("$", "").replace(",", "")
        if text == "":
            return None
        return float(text)
    except:
        return None


def fmt_money(v):
    if v is None:
        return "N/A"
    return f"${v:,.2f}"


def normalize_cond(v):
    text = clean(v).lower()
    return COND_MAP.get(text, clean(v).upper())


def normalize_vendor(v):
    text = clean(v).upper()
    text = text.replace(".", "").replace(",", "")
    text = " ".join(text.split())
    return text


def parse_date(v):
    try:
        dt = pd.to_datetime(v, errors="coerce")
        if pd.isna(dt):
            return None
        return dt
    except:
        return None


@st.cache_data
def read_csv_backend(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(path, low_memory=False, encoding="utf-8")
    except:
        df = pd.read_csv(path, low_memory=False, encoding="latin1")

    df = df.fillna("")
    df.columns = [clean(c) for c in df.columns]
    return df


def read_uploaded_csv(uploaded_file):
    if uploaded_file is None:
        return pd.DataFrame()

    try:
        df = pd.read_csv(uploaded_file, low_memory=False, encoding="utf-8")
    except:
        df = pd.read_csv(uploaded_file, low_memory=False, encoding="latin1")

    df = df.fillna("")
    df.columns = [clean(c) for c in df.columns]
    return df


def load_data_with_upload(label, backend_filename, key):
    st.markdown(f"**{label}**")

    uploaded = st.file_uploader(
        f"Optional override upload for {label}",
        type=["csv"],
        key=key,
    )

    if uploaded is not None:
        df = read_uploaded_csv(uploaded)
        st.success(f"Using uploaded file — {len(df):,} rows")
        return df

    df = read_csv_backend(backend_filename)

    if df.empty:
        st.warning(f"No backend file found: DATA/{backend_filename}")
    else:
        st.success(f"Using backend file: DATA/{backend_filename} — {len(df):,} rows")

    return df


def exact_part_filter(df, column, part):
    if df.empty or column not in df.columns:
        return pd.DataFrame()

    search = part.strip().upper()
    mask = df[column].astype(str).str.strip().str.upper() == search
    return df.loc[mask].copy()


def remove_cancelled(df):
    if df.empty or "CANCELLED" not in df.columns:
        return df

    cancelled_values = ["true", "yes", "y", "1", "cancelled", "canceled"]
    return df[
        ~df["CANCELLED"].astype(str).str.lower().isin(cancelled_values)
    ].copy()


def get_price_from_row(row, columns):
    for col in columns:
        if col in row:
            price = money(row.get(col))
            if price and price > 1:
                return price
    return None


def price_list_by_condition(df, cond_col, price_cols):
    output = defaultdict(list)

    if df.empty or cond_col not in df.columns:
        return output

    for _, row in df.iterrows():
        cond = normalize_cond(row.get(cond_col))
        price = get_price_from_row(row, price_cols)

        if cond in VISIBLE_CONDITIONS and price:
            output[cond].append(price)

    return output


def range_from_prices(prices):
    if not prices:
        return None

    prices = sorted(prices)

    if len(prices) >= 4:
        med = median(prices)
        prices = [p for p in prices if med * 0.50 <= p <= med * 1.50]

    if not prices:
        return None

    med = median(prices)
    return med * 0.90, med, med * 1.10, len(prices)


def confidence(count):
    if count >= 6:
        return "HIGH"
    if count >= 3:
        return "MED"
    return "LOW"


def build_guidance_text(by_cond, mode):
    lines = []

    for cond in VISIBLE_CONDITIONS:
        result = range_from_prices(by_cond.get(cond, []))
        if not result:
            continue

        low, med, high, count = result

        if mode == "buy":
            lines.append(
                f"{cond}: Expected range {fmt_money(low)} - {fmt_money(high)} | {confidence(count)}"
            )
        else:
            lines.append(
                f"{cond}: Quote around {fmt_money(med)} | {confidence(count)}"
            )

    return lines


def build_guidance_table(by_cond, mode):
    rows = []

    for cond in VISIBLE_CONDITIONS:
        result = range_from_prices(by_cond.get(cond, []))
        if not result:
            continue

        low, med, high, count = result

        if mode == "buy":
            rows.append({
                "Condition": cond,
                "Target Buy": fmt_money(low),
                "Median": fmt_money(med),
                "Max Buy": fmt_money(high),
                "Confidence": confidence(count),
                "Records": count,
            })
        else:
            rows.append({
                "Condition": cond,
                "Low Quote": fmt_money(low),
                "Suggested Quote": fmt_money(med),
                "High Quote": fmt_money(high),
                "Confidence": confidence(count),
                "Records": count,
            })

    return pd.DataFrame(rows)


def summarize_internal_history(po_df, so_df):
    combined = defaultdict(lambda: {
        "po_count": 0,
        "so_count": 0,
        "costs": [],
        "srps": [],
        "vendors": [],
        "tagged_by": [],
        "sales": [],
    })

    for _, row in po_df.iterrows():
        cond = normalize_cond(row.get("CONDITION"))
        if not cond:
            cond = "UNK"

        info = combined[cond]
        info["po_count"] += 1

        cost = get_price_from_row(row, ["EXCH FEE / COST EA", "OUTRIGHT VALUE"])
        if cost:
            info["costs"].append(cost)

        vendor = normalize_vendor(row.get("VENDOR"))
        if vendor:
            info["vendors"].append(vendor)

    for _, row in so_df.iterrows():
        cond = normalize_cond(row.get("CD"))
        if not cond:
            cond = "UNK"

        info = combined[cond]
        info["so_count"] += 1

        sale = get_price_from_row(row, ["EXCH FEE / SALES EA", "OUTRIGHT VALUE", "AMOUNT PAID"])
        if sale:
            info["sales"].append(sale)

    return combined


def build_internal_history_lines(po_df, so_df):
    summary = summarize_internal_history(po_df, so_df)
    lines = []

    if not summary:
        return ["No internal history found for this part."]

    for cond in ["NE", "OH", "RP", "IN", "SV", "AR", "UNK"]:
        if cond not in summary:
            continue

        info = summary[cond]
        total_records = info["po_count"] + info["so_count"]

        lines.append(f"{cond} | {total_records} record(s) found")

        details = []

        if info["costs"]:
            details.append(f"total cost {fmt_money(median(info['costs']))}")

        if info["vendors"]:
            vendors = list(dict.fromkeys(info["vendors"]))[:3]
            details.append("purchased from " + " / ".join(vendors))

        if details:
            lines.append("  Purchase history: " + " | ".join(details))

        if info["sales"]:
            sales = sorted(info["sales"])
            if len(sales) == 1:
                lines.append(f"  Prior sale: {fmt_money(sales[0])}")
            else:
                lines.append(
                    f"  Prior sales: {fmt_money(sales[0])} – {fmt_money(sales[-1])} | median {fmt_money(median(sales))}"
                )

        lines.append("")

    return lines


def best_value_options(incoming_df):
    rows = []

    for _, row in incoming_df.iterrows():
        cond = normalize_cond(row.get("COND"))
        price = get_price_from_row(row, ["COST PER UNIT", "EXCH. FEE"])

        if cond not in VISIBLE_CONDITIONS or not price:
            continue

        vendor = normalize_vendor(row.get("VENDOR"))

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
            "Vendor": vendor,
            "Condition": cond,
            "Price": fmt_money(price),
            "Qty": clean(row.get("QTY")),
            "Tag Date": clean(row.get("TAG DATE")),
            "Tagged By": clean(row.get("TAGGED BY")),
            "Warranty": warranty,
            "Bereon Score": round(score, 2),
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Bereon Score", ascending=False)


def supplier_history(po_all):
    history = defaultdict(lambda: {"total_po": 0, "parts": Counter()})

    if po_all.empty:
        return history

    for _, row in po_all.iterrows():
        if clean(row.get("CANCELLED")).lower() in ["true", "yes", "1", "cancelled", "canceled"]:
            continue

        vendor = normalize_vendor(row.get("VENDOR"))
        part = clean(row.get("PART NUMBER")).upper()

        if not vendor:
            continue

        history[vendor]["total_po"] += 1
        if part:
            history[vendor]["parts"][part] += 1

    return history


def market_snapshot_from_incoming(incoming_df):
    counts = Counter()
    vendors = set()

    for _, row in incoming_df.iterrows():
        cond = normalize_cond(row.get("COND"))
        vendor = normalize_vendor(row.get("VENDOR"))

        if cond:
            qty = money(row.get("QTY")) or 1
            counts[cond] += int(qty)

        if vendor:
            vendors.add(vendor)

    lines = []
    lines.append(f"Vendor groups with usable listings: {len(vendors)}")

    for cond in ["NE", "OH", "RP", "IN", "SV", "NS", "AR"]:
        if counts.get(cond, 0):
            lines.append(f"{cond}: {counts[cond]} listed")

    return lines


def call_list_from_incoming(incoming_df, po_all, part):
    if incoming_df.empty:
        return pd.DataFrame()

    history = supplier_history(po_all)

    vendor_data = defaultdict(lambda: {
        "conditions": set(),
        "qty": 0,
        "best_price": None,
        "tagged_by": set(),
        "warranty": set(),
    })

    for _, row in incoming_df.iterrows():
        vendor = normalize_vendor(row.get("VENDOR"))
        if not vendor:
            continue

        cond = normalize_cond(row.get("COND"))
        qty = money(row.get("QTY")) or 1
        price = get_price_from_row(row, ["COST PER UNIT", "EXCH. FEE"])

        vendor_data[vendor]["conditions"].add(cond)
        vendor_data[vendor]["qty"] += int(qty)

        if price:
            if vendor_data[vendor]["best_price"] is None or price < vendor_data[vendor]["best_price"]:
                vendor_data[vendor]["best_price"] = price

        tagged = clean(row.get("TAGGED BY"))
        if tagged:
            vendor_data[vendor]["tagged_by"].add(tagged)

        warranty = clean(row.get("WARRANTY"))
        if warranty:
            vendor_data[vendor]["warranty"].add(warranty)

    rows = []

    for vendor, data in vendor_data.items():
        total_po = history[vendor]["total_po"]
        part_po = history[vendor]["parts"][part.upper()]

        relationship = ""
        if vendor in SISTER_COMPANIES:
            relationship = "sister company"

        score = 0
        score += min(total_po, 500) * 5
        score += min(part_po, 25) * 100
        score += data["qty"] * 3

        if relationship:
            score += 1000

        best_cond_rank = max([COND_RANK.get(c, 0) for c in data["conditions"] if c], default=0)
        score += best_cond_rank * 20

        if data["best_price"]:
            score -= data["best_price"] / 1000

        conditions = "/".join(
            sorted(data["conditions"], key=lambda c: COND_RANK.get(c, 0), reverse=True)
        )

        reasons = []

        if relationship:
            reasons.append(relationship)

        if part_po:
            reasons.append(f"bought this P/N {part_po} time(s)")
        elif total_po:
            reasons.append(f"{total_po} prior PO(s)")

        reasons.append(f"{data['qty']} total listed")

        if conditions:
            reasons.append(f"conditions {conditions}")

        if data["warranty"]:
            reasons.append("warranty info")

        rows.append({
            "Vendor": vendor,
            "Action": "",
            "Why": "; ".join(reasons),
            "Conditions": conditions,
            "Qty": data["qty"],
            "Best Price": fmt_money(data["best_price"]),
            "Prior POs": total_po,
            "Same P/N POs": part_po,
            "Score": round(score, 2),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values("Score", ascending=False)

    actions = []
    for i in range(len(df)):
        if i == 0:
            actions.append("CALL FIRST")
        elif i <= 2:
            actions.append("CALL NEXT")
        else:
            actions.append("BACKUP")

    df["Action"] = actions

    return df


def report_block(title, lines):
    st.markdown(f"### {title}")
    text = "\n".join(lines)
    st.code(text)


def intelligence_search():
    st.title("Bereon Intelligence Search")
    st.caption("One part number search across backend files, with optional upload overrides.")

    with st.expander("File inputs / backend data", expanded=False):
        c1, c2 = st.columns(2)

        with c1:
            incoming = load_data_with_upload("Incoming Quotes", INCOMING_FILE, "incoming_upload")
            outgoing = load_data_with_upload("Outgoing Quotes", OUTGOING_FILE, "outgoing_upload")

        with c2:
            po_all = load_data_with_upload("Purchase Orders", PO_FILE, "po_upload")
            so_all = load_data_with_upload("Sales Orders", SO_FILE, "so_upload")

    part = st.text_input("Enter exact part number", placeholder="3202222-1")

    if not part:
        return

    inc = exact_part_filter(incoming, "PART #", part)
    out = exact_part_filter(outgoing, "Part #", part)
    po_part = remove_cancelled(exact_part_filter(po_all, "PART NUMBER", part))
    so_part = remove_cancelled(exact_part_filter(so_all, "PART #", part))

    st.success(f"Search complete for {part.upper()}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Incoming Quotes", len(inc))
    m2.metric("Outgoing Quotes", len(out))
    m3.metric("Purchase Orders", len(po_part))
    m4.metric("Sales Orders", len(so_part))

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Bereon Summary",
        "Buy Intelligence",
        "Quote Intelligence",
        "Call List",
        "Raw Records",
    ])

    with tab1:
        st.header(f"PART: {part.upper()}")

        internal_lines = build_internal_history_lines(po_part, so_part)
        report_block("INTERNAL HISTORY", internal_lines)

        call_df = call_list_from_incoming(inc, po_all, part)

        call_lines = []
        if call_df.empty:
            call_lines.append("No supplier call list found.")
        else:
            for idx, row in call_df.head(8).iterrows():
                call_lines.append(f"{len(call_lines)+1}. {row['Vendor']} | {row['Action']}")
                call_lines.append(f"   Why: {row['Why']}")

        report_block("WHO TO CALL FIRST", call_lines)

        market_lines = market_snapshot_from_incoming(inc)
        report_block("MARKET SNAPSHOT", market_lines)

        buy_from_incoming = price_list_by_condition(inc, "COND", ["COST PER UNIT", "EXCH. FEE"])
        buy_from_po = price_list_by_condition(po_part, "CONDITION", ["EXCH FEE / COST EA", "OUTRIGHT VALUE"])
        sell_from_outgoing = price_list_by_condition(out, "Condition", ["Price Per Unit"])
        sell_from_sales = price_list_by_condition(so_part, "CD", ["EXCH FEE / SALES EA", "OUTRIGHT VALUE", "AMOUNT PAID"])

        combined_buy = defaultdict(list)
        for source in [buy_from_po, buy_from_incoming]:
            for cond, prices in source.items():
                combined_buy[cond].extend(prices)

        combined_sell = defaultdict(list)
        for source in [sell_from_sales, sell_from_outgoing]:
            for cond, prices in source.items():
                combined_sell[cond].extend(prices)

        pricing_lines = []
        pricing_lines.append("BUY SIDE / ACQUISITION GUIDANCE")
        pricing_lines.extend(build_guidance_text(combined_buy, "buy") or ["No usable buy-side pricing found."])
        pricing_lines.append("")
        pricing_lines.append("SELL SIDE / QUOTE GUIDANCE")
        pricing_lines.extend(build_guidance_text(combined_sell, "sell") or ["No usable sell-side pricing found."])

        report_block("PRICING GUIDANCE", pricing_lines)

    with tab2:
        st.header("Buy Intelligence")

        buy_from_incoming = price_list_by_condition(inc, "COND", ["COST PER UNIT", "EXCH. FEE"])
        buy_from_po = price_list_by_condition(po_part, "CONDITION", ["EXCH FEE / COST EA", "OUTRIGHT VALUE"])

        st.subheader("Incoming Quote Buy Guidance")
        incoming_table = build_guidance_table(buy_from_incoming, "buy")
        if incoming_table.empty:
            st.info("No incoming quote pricing found.")
        else:
            st.dataframe(incoming_table, use_container_width=True)

        st.subheader("Purchase Order Buy Guidance")
        po_table = build_guidance_table(buy_from_po, "buy")
        if po_table.empty:
            st.info("No PO pricing found.")
        else:
            st.dataframe(po_table, use_container_width=True)

        st.subheader("Best Value Options")
        best = best_value_options(inc)
        if best.empty:
            st.info("No best value options found.")
        else:
            st.dataframe(best.head(20), use_container_width=True)

    with tab3:
        st.header("Quote Intelligence")

        sell_from_outgoing = price_list_by_condition(out, "Condition", ["Price Per Unit"])
        sell_from_sales = price_list_by_condition(so_part, "CD", ["EXCH FEE / SALES EA", "OUTRIGHT VALUE", "AMOUNT PAID"])

        st.subheader("Outgoing Quote Guidance")
        out_table = build_guidance_table(sell_from_outgoing, "sell")
        if out_table.empty:
            st.info("No outgoing quote pricing found.")
        else:
            st.dataframe(out_table, use_container_width=True)

        st.subheader("Completed Sales Guidance")
        so_table = build_guidance_table(sell_from_sales, "sell")
        if so_table.empty:
            st.info("No completed sales pricing found.")
        else:
            st.dataframe(so_table, use_container_width=True)

    with tab4:
        st.header("Supplier Call List")

        call_df = call_list_from_incoming(inc, po_all, part)

        if call_df.empty:
            st.info("No call-list suppliers found.")
        else:
            st.dataframe(call_df.head(25), use_container_width=True)

    with tab5:
        st.header("Raw Matching Records")

        with st.expander("Incoming Quotes"):
            st.dataframe(inc.head(200), use_container_width=True)

        with st.expander("Outgoing Quotes"):
            st.dataframe(out.head(200), use_container_width=True)

        with st.expander("Purchase Orders"):
            st.dataframe(po_part.head(200), use_container_width=True)

        with st.expander("Sales Orders"):
            st.dataframe(so_part.head(200), use_container_width=True)


def settings_page():
    st.title("Settings")
    st.write("Bereon backend mode: CSV with optional upload overrides.")
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
        "Settings",
    ],
)

if page == "Bereon Intelligence Search":
    intelligence_search()
elif page == "Settings":
    settings_page()