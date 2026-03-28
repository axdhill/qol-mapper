#!/usr/bin/env python3
"""
Download EPA eGRID power plant data.

Source: https://www.epa.gov/egrid/download-data
Downloads the plant-level data from the most recent eGRID release.
"""

from utils import RAW_DIR, download_file, ensure_dirs

# eGRID2023 data (most recent as of early 2025)
EGRID_URL = "https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx"


def main():
    ensure_dirs()

    dest = RAW_DIR / "egrid2023_data.xlsx"

    print("=== Downloading EPA eGRID Data ===")
    download_file(EGRID_URL, dest)
    print("Done!")


if __name__ == "__main__":
    main()
