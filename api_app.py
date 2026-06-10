from fastapi import FastAPI
from pydantic import BaseModel

import streamlit_app as streamlit_bereon

app = FastAPI(title="Bereon API")


class BereonRequest(BaseModel):
    part_number: str


@app.get("/")
def home():
    return {"status": "Bereon API running"}


@app.post("/bereon-report")
def bereon_report(request: BereonRequest):
    incoming_rows = streamlit_bereon.load_rows("Incoming Quotes", "incoming_quotes.csv", "incoming")
    outgoing_rows = streamlit_bereon.load_rows("Outgoing Quotes", "outgoing_quotes.csv", "outgoing")
    po_rows = streamlit_bereon.load_rows("Purchase Orders", "purchase_orders.csv", "po")
    sales_rows = streamlit_bereon.load_rows("Sales Orders", "sales_orders.csv", "sales")

    ils_vendors = streamlit_bereon.load_ils_vendors(None)

    report = streamlit_bereon.run_bereon_report(
        request.part_number,
        outgoing_rows,
        incoming_rows,
        po_rows,
        sales_rows,
        ils_vendors,
    )

    return {
        "part_number": request.part_number.upper(),
        "report": report
    }