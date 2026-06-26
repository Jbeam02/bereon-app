import pandas as pd

part = "5145-1-77"

df = pd.read_csv("DATA/sales_orders.csv", low_memory=False)
df = df.fillna("")

matches = df[df["PART #"].astype(str).str.upper() == part.upper()]

print(f"\nFound {len(matches)} records\n")

for _, row in matches.iterrows():
    print(
        row["DATE CREATED"],
        "|",
        row["CD"],
        "|",
        row["EXCH FEE / SALES EA"],
        "|",
        row["CUSTOMER"]
    )