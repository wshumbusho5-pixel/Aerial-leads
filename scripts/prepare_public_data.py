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
RAW_DIR = BASE_DIR / "data" / "sellers" / "raw"   # Franklin County Excel files live here
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
def load_franklin_county_excel() -> list:
    """
    Process the three Franklin County bulk Excel files:
      data/sellers/raw/TaxDetail.xlsx  — tax amounts owed
      data/sellers/raw/Parcel.xlsx     — addresses, owner names, neighborhoods
      data/sellers/raw/Value.xlsx      — assessed and market values

    Returns list of public-safe property dicts (no owner names/phones).
    """
    tax_file = RAW_DIR / "TaxDetail.xlsx"
    parcel_file = RAW_DIR / "Parcel.xlsx"
    value_file = RAW_DIR / "Value.xlsx"

    if not parcel_file.exists():
        return []

    print("\n→ Loading Franklin County bulk Excel files (this takes ~30 seconds)...")

    # Load Parcel (addresses)
    print("  Loading Parcel.xlsx ...")
    df_parcel = pd.read_excel(parcel_file, engine="openpyxl")
    df_parcel.columns = [c.strip() for c in df_parcel.columns]

    # Normalize key columns — handle various column name formats
    col_map = {}
    for c in df_parcel.columns:
        cl = c.lower().replace(" ", "").replace("_", "")
        if cl in ("parcelid", "parcelnumber", "parcelno"):
            col_map[c] = "parcel_id"
        elif "siteaddress" in cl or (cl == "address" and "parcel_id" not in col_map.values()):
            col_map[c] = "address"
        elif "ownername" in cl or cl == "owner1":
            col_map[c] = "owner_name"
        elif "zipcode" in cl or cl == "zip":
            col_map[c] = "zip_code"
        elif "neighborhood" in cl or cl == "nbhd":
            col_map[c] = "neighborhood"
        elif "lucdesc" in cl or "landuse" in cl or "propertytype" in cl:
            col_map[c] = "property_type"
    df_parcel = df_parcel.rename(columns=col_map)

    needed = [c for c in ["parcel_id", "address", "zip_code"] if c in df_parcel.columns]
    if not needed:
        print("  ⚠️  Could not find address/parcel columns in Parcel.xlsx")
        return []

    rows = []

    # Load TaxDetail (amounts owed) if available
    taxes_by_parcel = {}
    if tax_file.exists():
        print("  Loading TaxDetail.xlsx ...")
        df_tax = pd.read_excel(tax_file, engine="openpyxl")
        df_tax.columns = [c.strip() for c in df_tax.columns]
        for _, row in df_tax.iterrows():
            pid = str(row.get("Parcel Id") or row.get("ParcelId") or row.get("PARCEL ID") or "").strip()
            amt = float(row.get("TotTotal") or row.get("TotalDue") or row.get("taxes_owed") or 0)
            if pid and amt > 0:
                taxes_by_parcel[pid] = amt

    # Load Value (assessed/market values) if available
    values_by_parcel = {}
    if value_file.exists():
        print("  Loading Value.xlsx ...")
        df_val = pd.read_excel(value_file, engine="openpyxl")
        df_val.columns = [c.strip() for c in df_val.columns]
        for _, row in df_val.iterrows():
            pid = str(row.get("Parcel Id") or row.get("ParcelId") or row.get("PARCEL ID") or "").strip()
            market = float((row.get("MarketLand") or 0) + (row.get("MarketImpr") or 0))
            assessed = float((row.get("TaxableLand") or 0) + (row.get("TaxableImpr") or 0))
            if pid:
                values_by_parcel[pid] = {"market": market, "assessed": assessed}

    print(f"  Processing {len(df_parcel):,} parcels ...")
    for _, row in df_parcel.iterrows():
        address = str(row.get("address") or "").strip()
        if not address or address.lower() in ("nan", ""):
            continue

        pid = str(row.get("parcel_id") or "").strip()
        zip_code = str(row.get("zip_code") or "").strip()
        if zip_code in ("nan", "0", ""):
            zip_code = ""
        else:
            zip_code = zip_code.split(".")[0]  # remove .0 from numeric

        city = "Columbus"
        neighborhood = row.get("neighborhood") or ZIP_NEIGHBORHOODS.get(zip_code, "Columbus")
        if not neighborhood or str(neighborhood) == "nan":
            neighborhood = ZIP_NEIGHBORHOODS.get(zip_code, "Columbus")

        taxes_owed = taxes_by_parcel.get(pid, 0)
        val_data = values_by_parcel.get(pid, {})
        market = val_data.get("market", 0)
        assessed = val_data.get("assessed", 0)

        if market > 0:
            val_low = int(market * 0.85 / 1000) * 1000
            val_high = int(market * 1.15 / 1000) * 1000
        else:
            val_low, val_high = estimate_value_range(assessed)

        lead_type = "tax_delinquent" if taxes_owed > 0 else "motivated_seller"

        rows.append({
            "slug": make_slug(address, city),
            "address": address.title(),
            "city": city,
            "zip": zip_code or None,
            "state": "OH",
            "neighborhood": neighborhood,
            "lead_type": lead_type,
            "assessed_value": int(assessed) if assessed > 0 else None,
            "val_low": val_low,
            "val_high": val_high,
            "taxes_owed": int(taxes_owed) if taxes_owed > 0 else None,
            "years_delinquent": None,
            "source_file": "FranklinCounty_bulk",
            "imported_at": datetime.now().strftime("%Y-%m-%d"),
        })

    print(f"  ✅ {len(rows):,} properties loaded from Franklin County Excel files")
    return rows


def main():
    print("=" * 60)
    print("Lifeline Home Buyers - Property Data Import")
    print(f"Scanning: {IMPORTS_DIR}")
    print("=" * 60)

    all_rows = []

    # ── Step 1: Franklin County bulk Excel files (the big source) ─────────────
    fc_rows = load_franklin_county_excel()
    all_rows.extend(fc_rows)

    # ── Step 2: Any additional CSVs in imports/ ────────────────────────────────
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
