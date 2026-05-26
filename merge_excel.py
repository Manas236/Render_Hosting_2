import pandas as pd
import glob
import os
import re

script_dir = os.path.dirname(os.path.abspath(__file__))
files = sorted(glob.glob(os.path.join(script_dir, "*.csv")))

output_path = os.path.join(script_dir, "merged_emails.xlsx")

if not files:
    print("No CSV files found in the script directory.")
    exit(1)

EMAIL_PATTERN = re.compile(r"^[^@]+@[^@]+\.[^@]+$")

def find_email_column(df):
    # Try common email column name variants first
    for col in df.columns:
        if col.strip().lower() in ("email address", "email", "e-mail", "mail", "email_address"):
            return col
    # Fallback: find first column where >50% of non-null values look like emails
    for col in df.columns:
        sample = df[col].dropna().astype(str).head(20)
        if sample.apply(lambda x: bool(EMAIL_PATTERN.match(x.strip()))).mean() > 0.5:
            return col
    return None

print(f"Found {len(files)} file(s):\n")

all_emails = []
for f in files:
    df = pd.read_csv(f)
    col = find_email_column(df)
    if col is None:
        print(f"  WARNING: Could not find email column in {os.path.basename(f)}")
        print(f"           Columns found: {list(df.columns)}")
        continue
    extracted = df[col].dropna().astype(str).str.strip()
    extracted = extracted[extracted.apply(lambda x: bool(EMAIL_PATTERN.match(x)))]
    all_emails.extend(extracted.tolist())
    print(f"  {os.path.basename(f)}: {len(extracted)} emails  (column: '{col}')")

merged = pd.DataFrame({"Email": all_emails})
print(f"\nTotal before dedup : {len(merged)}")
merged = merged.drop_duplicates()
print(f"Total after dedup  : {len(merged)}")

merged.to_excel(output_path, index=False)
print(f"\nSaved to: {output_path}")
