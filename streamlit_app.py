# Bereon Procurement Intelligence - v1

import streamlit as st
import pandas as pd

CONDITION_PRIORITY = {
    "OH": 4,
    "RP": 3,
    "IN": 2,
    "NE": 1
}

def normalize_condition(value):
    if pd.isna(value):
        return ""
    return str(value).strip().upper()

def score_row(row):
    score = 0

    condition = normalize_condition(row.get("Condition", ""))
    score += CONDITION_PRIORITY.get(condition, 0) * 25

    qty = row.get("Qty", 0)
    try:
        qty = float(qty)
        if qty >= 2:
            score += 10
    except:
        pass

    country = str(row.get("Country", "")).upper()
    if "USA" in country or "UNITED STATES" in country:
        score += 10

    warranty = str(row.get("Warranty", "")).lower()
    if "12" in warranty:
        score += 20
    elif "6" in warranty:
        score += 10
    elif "30" in warranty:
        score += 5

    return score

def procurement_page():
    st.title("Procurement Intelligence")
    st.caption("What To Buy For — ILS / InfoTrader Market Analysis")

    uploaded_file = st.file_uploader(
        "Upload ILS or market data file",
        type=["csv", "xlsx"]
    )

    if uploaded_file is None:
        st.info("Upload an ILS or InfoTrader export to begin.")
        return

    if uploaded_file.name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)

    st.subheader("Uploaded Data")
    st.dataframe(df, use_container_width=True)

    part_number = st.text_input("Enter part number")

    if not part_number:
        return

    part_df = df[
        df.astype(str)
        .apply(lambda row: row.str.contains(part_number, case=False, na=False).any(), axis=1)
    ].copy()

    if part_df.empty:
        st.warning("No matching records found.")
        return

    part_df["Condition"] = part_df.get("Condition", "").apply(normalize_condition)
    part_df["Bereon Score"] = part_df.apply(score_row, axis=1)

    ranked = part_df.sort_values("Bereon Score", ascending=False)

    st.subheader("Best Value Recommendation")
    st.success("Top ranked supplier based on condition, warranty, quantity, and location.")
    st.dataframe(ranked.head(1), use_container_width=True)

    st.subheader("Cheapest Usable Options")
    if "Price" in ranked.columns:
        cheapest = ranked.sort_values("Price", ascending=True)
        st.dataframe(cheapest.head(5), use_container_width=True)
    else:
        st.info("No Price column detected.")

    st.subheader("Ranked Market Options")
    st.dataframe(ranked, use_container_width=True)