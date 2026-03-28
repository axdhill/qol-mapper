#!/usr/bin/env python3
"""
Download NLCD Tree Canopy Cover data.

Source: https://www.mrlc.gov/data/type/nlcd-tree-canopy-cover
The full CONUS GeoTIFF is very large (~8GB). This script provides the download
URL and instructions for manual download, or can auto-download if desired.

For development/testing, a smaller excerpt can be created using GDAL:
    gdal_translate -projwin -125 50 -66 24 input.tif conus_tree_canopy.tif
"""

from utils import RAW_DIR, ensure_dirs

# NLCD 2021 Tree Canopy Cover direct download (may require manual download)
# This URL points to the MRLC data portal
NLCD_TCC_INFO = "https://www.mrlc.gov/data/nlcd-2021-usfs-tree-canopy-cover-conus"

# Alternatively, use the Science Base download:
# https://www.sciencebase.gov/catalog/item/649595e9d34ef77fcb01dca3


def main():
    ensure_dirs()

    print("=== NLCD Tree Canopy Cover Download ===")
    print()
    print("The NLCD Tree Canopy Cover GeoTIFF is very large (~8 GB).")
    print("Please download manually from:")
    print(f"  {NLCD_TCC_INFO}")
    print()
    print(f"Save the file to: {RAW_DIR / 'nlcd_tcc_conus_2021.tif'}")
    print()
    print("After downloading, run process_tree_canopy.py to generate tiles.")


if __name__ == "__main__":
    main()
