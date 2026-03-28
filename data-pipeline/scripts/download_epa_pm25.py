#!/usr/bin/env python3
"""
Download EPA AirData PM2.5 annual summary data.

Source: https://aqs.epa.gov/aqsweb/airdata/download_files.html
Downloads the annual concentration by monitor file for the most recent year.
"""

import zipfile
from pathlib import Path

from utils import RAW_DIR, download_file, ensure_dirs

# EPA AirData annual summary URL pattern
# Parameter Code 88101 = PM2.5 FRM/FEM Mass
YEAR = 2023  # Most recent complete year available
URL = f"https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_{YEAR}.zip"


def main():
    ensure_dirs()

    zip_path = RAW_DIR / f"annual_conc_by_monitor_{YEAR}.zip"
    csv_path = RAW_DIR / f"annual_conc_by_monitor_{YEAR}.csv"

    print(f"=== Downloading EPA PM2.5 data for {YEAR} ===")
    download_file(URL, zip_path)

    if not csv_path.exists():
        print(f"  Extracting {zip_path.name}...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(RAW_DIR)
        print(f"  Extracted to {csv_path}")
    else:
        print(f"  Already extracted: {csv_path.name}")

    print("Done!")


if __name__ == "__main__":
    main()
