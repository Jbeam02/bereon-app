import io
import tempfile
from pathlib import Path
from contextlib import redirect_stdout
from collections import defaultdict
from statistics import median

import pandas as pd
import streamlit as st

import bereon_engine as engine

st.set_page_config(page_title="Bereon Aviation Intelligence", layout="wide")

USERS = {
    "Jbeam21": "Bereon2026",
    "Operations": "Supportair2026",
}

DATA_DIR = Path("DATA")
LOGO_PATH = Path("logo.png")


def show_logo(width=450):
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=width)


# ----------------------------
# LOGIN / LOGOUT
# ----------------------------

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "username" not in st.session_state:
    st.session_state.username = ""

if not st.session_state.authenticated:
    show_logo(width=500)

    st.title("Bereon Aviation Intelligence Platform")
    st.caption("Internal Procurement Intelligence System")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if username in USERS and USERS[username] == password:
            st.session_state.authenticated = True
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Invalid username or password")

    st.stop()

with st.sidebar:
    show_logo(width=220)
    st.caption("Aviation Intelligence Platform")
    st.success(f"Logged in as: {st.session_state.username}")

    st.markdown("---")

    if st.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.rerun()

    st.markdown("---")
    st.caption("Internal Use Only")


# ----------------------------
# DATA HELPERS
# ----------------------------

def read_csv_backend(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return []

    try:
        df = pd.read_csv(path, low_memory=False, encoding="utf-8")
    except Exception:
        df = pd.read_csv(path, low_memory=False, encoding="latin1")

    df = df.fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df.to_dict("records")


def read_uploaded_csv(uploaded_file):
    if uploaded_file is None:
        return None

    try:
        df = pd.read_csv(uploaded_file, low_memory=False, encoding="utf-8")
    except Exception:
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, low_memory=False, encoding="latin1")

    df = df.fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df.to_dict("records")


def load_rows(label, filename, key):
    uploaded = st.file_uploader(
        f"Optional upload override: {label}",
        type=["csv"],
        key=key,
    )

    if uploaded is not None:
        rows = read_uploaded_csv(uploaded)
        st.success(f"Using uploaded {label}: {len(rows):,} rows")
        return rows

    rows = read_csv_backend(filename)
    st.success(f"Using backend {label}: DATA/{filename} — {len(rows):,} rows")
    return rows


def capture_print(func, *args, **kwargs):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        func(*args, **kwargs)
    return buffer.getvalue()


def load_ils_vendors(uploaded_ils):
    if uploaded_ils is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp.write(uploaded_ils.getvalue())
            tmp_path = Path(tmp.name)

        return engine.parse_ils_file(tmp_path)

    vendors = []
    for path in engine.find_all_ils_files():
        vendors.extend(engine.parse_ils_file(path))
    return vendors


def internal_history_text(po_rows, sales_rows, part):
    po_index = engine.build_part_index(po_rows, engine.PART_FIELD_NAMES)
    sales_index = engine.build_part_index(sales_rows, engine.PART_FIELD_NAMES)

    po_matches = engine.get_purchase_history_matches(po_index, part)
    sales_matches = engine.get_sales_history_matches(sales_index, part)

    combined = defaultdict(
        lambda: {
            "po": [],
            "sales": [],
            "vendors": [],
            "tagged_by": [],
        }
    )

    for row in po_matches:
        cond = engine.row_condition(row) or "UNK"
        price = engine.row_price(row, "buy")
        vendor = engine.normalize_vendor(
            engine.find_value(row, engine.INVENTORY_VENDOR_FIELD_NAMES + ["VENDOR"])
        )

        if price:
            combined[cond]["po"].append(price)
        if vendor:
            combined[cond]["vendors"].append(vendor)

    for row in sales_matches:
        cond = engine.row_condition(row) or "UNK"
        price = engine.row_price(row, "sell")

        if price:
            combined[cond]["sales"].append(price)

    lines = ["===== INTERNAL HISTORY =====", ""]

    if not combined:
        lines.append("No internal history found for this part.")
        return "\n".join(lines)

    for cond in ["NE", "OH", "RP", "IN", "SV", "NS", "AR", "UNK"]:
        if cond not in combined:
            continue

        info = combined[cond]
        count = len(info["po"]) + len(info["sales"])

        lines.append(f"{cond} | {count} record(s) found")

        purchase_parts = []

        if info["po"]:
            purchase_parts.append(f"total cost {engine.fmt_money(median(info['po']))}")

        if info["vendors"]:
            vendors = list(dict.fromkeys(info["vendors"]))[:3]
            purchase_parts.append("purchased from " + " / ".join(vendors))

        if purchase_parts:
            lines.append("  Purchase history: " + " | ".join(purchase_parts))

        if info["sales"]:
            sales = sorted(info["sales"])
            if len(sales) == 1:
                lines.append(f"  Prior sale: {engine.fmt_money(sales[0])}")
            else:
                lines.append(
                    f"  Prior sales: {engine.fmt_money(sales[0])} – "
                    f"{engine.fmt_money(sales[-1])} | median {engine.fmt_money(median(sales))}"
                )

        lines.append("")

    return "\n".join(lines)


def run_bereon_report(part, outgoing_rows, incoming_rows, po_rows, sales_rows, ils_vendors):
    outgoing_index = engine.build_part_index(
        outgoing_rows,
        ["Part #", "PART #", "Part Number", "PART NUMBER", "P/N", "PN"],
    )
    incoming_index = engine.build_part_index(
        incoming_rows,
        ["PART #", "Part #", "Part Number", "PART NUMBER", "P/N", "PN"],
    )
    po_index = engine.build_part_index(po_rows, engine.PART_FIELD_NAMES)
    sales_index = engine.build_part_index(sales_rows, engine.PART_FIELD_NAMES)

    po_history = engine.load_po_history(po_rows)

    sections = []

    sections.append(f"PART: {part.upper()}")
    sections.append("")
    sections.append(internal_history_text(po_rows, sales_rows, part))
    sections.append("")

    sections.append(
        capture_print(
            engine.show_call_list,
            ils_vendors,
            po_history,
            part,
            False,
            False,
        )
    )

    sections.append(
        capture_print(
            engine.show_market_snapshot,
            ils_vendors,
            part,
            False,
        )
    )

    sections.append(
        capture_print(
            engine.show_buy_quote,
            part,
            outgoing_index,
            incoming_index,
            po_index,
            sales_index,
            [],
            False,
        )
    )

    return "\n".join(sections)


# ----------------------------
# MAIN APP
# ----------------------------

def main():
    page = st.sidebar.radio("Navigation", ["Bereon Intelligence Search", "Settings"])

    if page == "Settings":
        show_logo(width=450)
        st.title("Settings")
        st.write("Backend engine: `bereon_engine.py`")
        st.write("Backend files:")
        st.code(
            "DATA/incoming_quotes.csv\n"
            "DATA/outgoing_quotes.csv\n"
            "DATA/purchase_orders.csv\n"
            "DATA/sales_orders.csv\n"
            "Optional ILS .txt files in DATA/"
        )

        st.markdown("---")
        st.caption("© 2026 Bereon Aviation | Aviation Intelligence Platform | Internal Use Only")
        return

    show_logo(width=450)

    st.subheader("Aviation Procurement Intelligence Platform")
    st.caption("Market Intelligence • Vendor Discovery • Pricing Guidance")

    with st.expander("File inputs", expanded=False):
        c1, c2 = st.columns(2)

        with c1:
            incoming_rows = load_rows("Incoming Quotes", "incoming_quotes.csv", "incoming")
            outgoing_rows = load_rows("Outgoing Quotes", "outgoing_quotes.csv", "outgoing")

        with c2:
            po_rows = load_rows("Purchase Orders", "purchase_orders.csv", "po")
            sales_rows = load_rows("Sales Orders", "sales_orders.csv", "sales")

        uploaded_ils = st.file_uploader(
            "Optional upload override: ILS text file",
            type=["txt"],
            key="ils",
        )

    ils_vendors = load_ils_vendors(uploaded_ils)

    st.info(f"ILS vendor groups loaded: {len(ils_vendors):,}")

    part = st.text_input("Enter exact part number", placeholder="3202222-1")

    if not part:
        st.markdown("---")
        st.caption("© 2026 Bereon Aviation | Aviation Intelligence Platform | Internal Use Only")
        return

    report = run_bereon_report(
        part,
        outgoing_rows,
        incoming_rows,
        po_rows,
        sales_rows,
        ils_vendors,
    )

    st.subheader("Bereon Report")
    st.code(report)

    with st.expander("Raw engine output text"):
        st.text(report)

    st.markdown("---")
    st.caption("© 2026 Bereon Aviation | Aviation Intelligence Platform | Internal Use Only")


if __name__ == "__main__":
    main()