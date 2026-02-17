"""
Push public_properties.csv directly into Railway's PostgreSQL database.
Run this from your local machine — no git, no upload needed.

Usage:
    python scripts/push_properties_to_db.py
"""

import os
import sys
import pandas as pd
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL")
CSV_FILE = BASE_DIR / "public_site" / "data" / "processed" / "public_properties.csv"

if not DATABASE_URL:
    print("❌ DATABASE_URL not found in .env")
    sys.exit(1)

if not CSV_FILE.exists():
    print(f"❌ CSV not found. Run prepare_public_data.py first.")
    sys.exit(1)

print("=" * 60)
print("Pushing property data to Railway database...")
print("=" * 60)

# Load CSV
print(f"\n→ Loading {CSV_FILE.name} ...")
df = pd.read_csv(CSV_FILE)
print(f"  {len(df):,} properties to import")

# Connect
print("\n→ Connecting to Railway database ...")
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# Ensure table exists
cursor.execute("""
    CREATE TABLE IF NOT EXISTS public_properties (
        id SERIAL PRIMARY KEY,
        slug VARCHAR(500) UNIQUE NOT NULL,
        address VARCHAR(500) NOT NULL,
        city VARCHAR(100) DEFAULT 'Columbus',
        zip VARCHAR(10),
        state VARCHAR(5) DEFAULT 'OH',
        neighborhood VARCHAR(100),
        lead_type VARCHAR(50) DEFAULT 'motivated_seller',
        assessed_value INTEGER,
        val_low INTEGER,
        val_high INTEGER,
        taxes_owed INTEGER,
        years_delinquent INTEGER,
        imported_at DATE DEFAULT CURRENT_DATE,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()
print("  ✓ Table ready")

# Insert in batches of 1000
BATCH = 1000
total = len(df)
inserted = 0
updated = 0

print(f"\n→ Upserting {total:,} records in batches of {BATCH} ...")

rows = df.where(df.notna(), other=None).to_dict("records")

for i in range(0, total, BATCH):
    batch = rows[i:i + BATCH]
    for r in batch:
        def v(val):
            if val is None or (isinstance(val, float) and str(val) == "nan"):
                return None
            return val

        cursor.execute("""
            INSERT INTO public_properties
                (slug, address, city, zip, neighborhood, lead_type,
                 assessed_value, val_low, val_high, taxes_owed, years_delinquent, imported_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CURRENT_DATE)
            ON CONFLICT (slug) DO UPDATE SET
                address = EXCLUDED.address,
                city = EXCLUDED.city,
                zip = EXCLUDED.zip,
                neighborhood = EXCLUDED.neighborhood,
                lead_type = EXCLUDED.lead_type,
                assessed_value = EXCLUDED.assessed_value,
                val_low = EXCLUDED.val_low,
                val_high = EXCLUDED.val_high,
                taxes_owed = EXCLUDED.taxes_owed,
                years_delinquent = EXCLUDED.years_delinquent,
                imported_at = CURRENT_DATE,
                updated_at = CURRENT_TIMESTAMP
        """, (
            v(r.get("slug")), v(r.get("address")), v(r.get("city")) or "Columbus",
            v(r.get("zip")), v(r.get("neighborhood")), v(r.get("lead_type")) or "motivated_seller",
            v(r.get("assessed_value")), v(r.get("val_low")), v(r.get("val_high")),
            v(r.get("taxes_owed")), v(r.get("years_delinquent"))
        ))

    conn.commit()
    done = min(i + BATCH, total)
    pct = done / total * 100
    print(f"  {done:,} / {total:,} ({pct:.0f}%)", end="\r")

conn.close()

print(f"\n\n{'=' * 60}")
print(f"✅ Done! {total:,} properties live in Railway database.")
print(f"   Pages available at: https://life-line-homebuyers.com/property/<slug>")
print("=" * 60)
