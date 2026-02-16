"""
Lifeline Home Buyers - Monthly Property Data Importer

Run this script each month after downloading Franklin County data.
It converts your raw lead data into public-safe property pages for the website.

Usage:
    python scripts/prepare_public_data.py

Input:
    data/imports/  - Your monthly CSV or Excel files from Franklin County

Output:
    data/processed/public_properties.csv  - Safe for website (no owner names/phones)

Then:
    git add data/processed/public_properties.csv
    git push   <-- Railway auto-deploys, pages go live
"""

import re
import pandas as pd
from pathlib import Path
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
IMPORTS_DIR = BASE_DIR / "data" / "imports"
# Output goes to public_site/data/processed/ where the web app reads from
OUTPUT_FILE = BASE_DIR / "public_site" / "data" / "processed" / "public_properties.csv"
OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Columbus zip → neighborhood mapping ───────────────────────────────────────
ZIP_NEIGHBORHOODS = {
    "43201": "Short North",
    "43202": "Clintonville",
    "43203": "Near East Side",
    "43204": "Franklinton",
    "43205": "South Side",
    "43206": "German Village Area",
    "43207": "South Columbus",
    "43209": "Bexley",
    "43210": "University District",
    "43211": "Linden",
    "43212": "Grandview Heights",
    "43213": "East Columbus",
    "43214": "Beechwold",
    "43215": "Downtown Columbus",
    "43219": "Northland",
    "43220": "Upper Arlington",
    "43221": "Upper Arlington West",
    "43222": "Hilltop",
    "43223": "Southwest Columbus",
    "43224": "Northeast Columbus",
    "43227": "Whitehall",
    "43229": "Northland East",
    "43230": "Gahanna",
    "43231": "Northeast Columbus",
    "43232": "Reynoldsburg",
    "43235": "Worthington",
    "43240": "New Albany Area",
}

# ── Slug generation ───────────────────────────────────────────────────────────
def make_slug(address: str, city: str = "columbus", state: str = "oh") -> str:
    """
    Turn '392 MIDLAND AV' → '392-midland-av-columbus-oh'
    """
    text = f"{address} {city} {state}"
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"-+", "-", text)
    return text


# ── Value range estimator ─────────────────────────────────────────────────────
def estimate_value_range(assessed_value: float):
    """
    Franklin County assessed value is typically 35% of market value.
    Return (low, high) market value estimate.
    """
    if not assessed_value or assessed_value <= 0:
        return None, None
    # Ohio auditor uses 35% assessment ratio
    estimated_market = assessed_value / 0.35
    low = round(estimated_market * 0.85 / 1000) * 1000
    high = round(estimated_market * 1.15 / 1000) * 1000
    return int(low), int(high)


# ── Load a single import file ─────────────────────────────────────────────────
def load_import_file(filepath: Path) -> pd.DataFrame:
    """Load CSV or Excel, normalize columns."""
    suffix = filepath.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df = pd.read_excel(filepath, engine="openpyxl")
    else:
        df = pd.read_csv(filepath)

    # Normalize column names
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


# ── Detect lead type from data ────────────────────────────────────────────────
def detect_lead_type(row: pd.Series, filename: str) -> str:
    """
    Try to infer lead type from filename or data columns.
    """
    fname = filename.lower()
    if "probate" in fname:
        return "probate"
    if "tax" in fname or "delinquent" in fname:
        return "tax_delinquent"
    if "sheriff" in fname or "foreclosure" in fname:
        return "sheriff_sale"
    if "violation" in fname:
        return "code_violation"
    # Check taxes_owed column if present
    taxes = row.get("taxes_owed", 0) or row.get("tax_owed", 0)
    if taxes and float(taxes) > 0:
        return "tax_delinquent"
    return "motivated_seller"


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Lifeline Home Buyers - Property Data Import")
    print(f"Scanning: {IMPORTS_DIR}")
    print("=" * 60)

    all_rows = []

    import_files = sorted(IMPORTS_DIR.glob("*.csv")) + sorted(IMPORTS_DIR.glob("*.xlsx"))

    if not import_files:
        print(f"\n❌ No CSV or Excel files found in {IMPORTS_DIR}")
        print("   Drop your Franklin County files there and re-run.")
        return

    for filepath in import_files:
        print(f"\n→ Loading {filepath.name} ...")
        try:
            df = load_import_file(filepath)
        except Exception as e:
            print(f"  ⚠️  Skipped (error reading file): {e}")
            continue

        # Must have an address column
        address_col = next((c for c in df.columns if "address" in c), None)
        if not address_col:
            print(f"  ⚠️  Skipped (no address column found). Columns: {list(df.columns)}")
            continue

        count = 0
        for _, row in df.iterrows():
            address = str(row.get(address_col, "")).strip()
            if not address or address.lower() in ("nan", ""):
                continue

            # Extract zip from address if not separate column
            zip_code = str(row.get("zip_code", row.get("zip", ""))).strip()
            if not zip_code or zip_code == "nan":
                # Try to pull 5-digit zip from address string
                m = re.search(r"\b(4[0-9]{4})\b", address)
                zip_code = m.group(1) if m else ""

            city = str(row.get("city", "Columbus")).strip()
            if not city or city == "nan":
                city = "Columbus"

            neighborhood = ZIP_NEIGHBORHOODS.get(zip_code, "Columbus")

            # Value fields (from Franklin County Excel data)
            assessed = float(row.get("assessed_value", 0) or row.get("taxable_value", 0) or 0)
            market = float(row.get("market_value", 0) or 0)
            taxes_owed = float(row.get("taxes_owed", 0) or row.get("tax_owed", 0) or 0)
            years_delinquent = int(row.get("years_delinquent", 0) or 0)

            # Value range estimate
            if market > 0:
                val_low = int(market * 0.85 / 1000) * 1000
                val_high = int(market * 1.15 / 1000) * 1000
            else:
                val_low, val_high = estimate_value_range(assessed)

            lead_type = detect_lead_type(row, filepath.name)
            slug = make_slug(address, city)

            all_rows.append({
                "slug": slug,
                "address": address.title(),
                "city": city,
                "zip": zip_code,
                "state": "OH",
                "neighborhood": neighborhood,
                "lead_type": lead_type,
                "assessed_value": int(assessed) if assessed > 0 else None,
                "val_low": val_low,
                "val_high": val_high,
                "taxes_owed": int(taxes_owed) if taxes_owed > 0 else None,
                "years_delinquent": years_delinquent if years_delinquent > 0 else None,
                "source_file": filepath.name,
                "imported_at": datetime.now().strftime("%Y-%m-%d"),
            })
            count += 1

        print(f"  ✅ {count} properties loaded from {filepath.name}")

    if not all_rows:
        print("\n❌ No properties found. Check your import files.")
        return

    df_out = pd.DataFrame(all_rows)

    # Deduplicate by slug — keep the one with more data
    df_out = df_out.sort_values("assessed_value", ascending=False, na_position="last")
    df_out = df_out.drop_duplicates(subset=["slug"], keep="first")

    df_out.to_csv(OUTPUT_FILE, index=False)

    print(f"\n{'=' * 60}")
    print(f"✅ Done! {len(df_out)} properties written to:")
    print(f"   {OUTPUT_FILE}")
    print(f"\nBreakdown by type:")
    for t, cnt in df_out["lead_type"].value_counts().items():
        print(f"   {t}: {cnt}")
    print(f"\nNext step:")
    print(f"   git add public_site/data/processed/public_properties.csv")
    print(f"   git commit -m 'Update property data {datetime.now().strftime('%Y-%m')}'")
    print(f"   git push   ← Railway deploys automatically")
    print("=" * 60)


if __name__ == "__main__":
    main()
