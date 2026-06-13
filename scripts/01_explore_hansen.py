# scripts/01_explore_hansen.py
# Goal: read Hansen lossyear pixels under ONE plot and inspect the values
# before trusting any "value = year" assumption.

import geopandas as gpd          # vector data (your plots) as a dataframe
import rasterio                  # raster data (Hansen GeoTIFF)
from rasterio.mask import mask   # clips a raster to a polygon shape

# --- file paths ---
HANSEN = "data/hansen/Hansen_GFC-2024-v1.12_lossyear_00N_110E.tif"
PLOTS  = "data/aoi.gpkg"

# --- load the plots (vector) ---
plots = gpd.read_file(PLOTS, layer="plots")
print("Plots loaded:", len(plots))
print("Plots CRS:", plots.crs)

# --- open the raster and inspect ONE plot ---
with rasterio.open(HANSEN) as src:
    print("Raster CRS:", src.crs)
    print("Raster size:", src.width, "x", src.height)

    # align plots to the raster's exact CRS object (fixes axis-order mismatch)
    plots_aligned = plots.to_crs(src.crs)

    # take the first plot's geometry
    first_plot = plots_aligned.iloc[0]
    print("\nInspecting plot:", first_plot["plot_id"],
          "| expected:", first_plot["expected_status"])

    # mask = clip the raster to this polygon's exact shape
    geom = [first_plot["geometry"]]          # mask() wants a list of geometries
    out_image, out_transform = mask(src, geom, crop=True)

    # out_image is a 3D array: (bands, rows, cols). Hansen has 1 band.
    band = out_image[0]
    print("Window shape (rows, cols):", band.shape)

    # what values actually appear under this plot?
    import numpy as np
    values, counts = np.unique(band, return_counts=True)
    print("Pixel values present:", dict(zip(values.tolist(), counts.tolist())))