import streamlit as st

st.set_page_config(
    page_title="Bereon",
    page_icon="✈️",
    layout="wide"
)

st.title("BEREON")
st.subheader("Aviation Intelligence Platform")

part_number = st.text_input("Enter Part Number")

if st.button("Analyze"):
    st.success(f"Analyzing {part_number}")

    st.header("Market Intelligence")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Target Buy Range", "$8,500 - $10,500")
        st.metric("Best Value", "OH 2025 Tag")

    with col2:
        st.metric("Target Sell Range", "$14,000 - $17,000")
        st.metric("Cheapest Usable", "$8,500")

    st.write("Market analysis results will appear here.")