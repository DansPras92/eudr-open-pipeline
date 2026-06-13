# scripts/02_detect_loss.py
# For each plot: count Hansen forest-loss pixels and flag post-2020 (EUDR) loss.

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from sqlalchemy import create_engine    # <-- add this
import os
from dotenv import load_dotenv

# --- config ---
HANSEN = "data/hansen/Hansen_GFC-2024-v1.12_lossyear_00N_110E.tif"
PLOTS  = "data/aoi.gpkg"

#environment keys
load_dotenv()
PG_PASSWORD = os.environ["POSTGRES_PASSWORD"]

# EUDR cutoff is 31 Dec 2020 → loss in 2021+ counts.
# Hansen encodes year as (2000 + value), so 2021 = value 21.
EUDR_CUTOFF_VALUE = 21

# Each Hansen pixel ≈ 0.00025° ≈ 27.8 m at this latitude → ~773 m² per pixel.
# Rough, but good enough to report loss area in hectares.
PIXEL_AREA_M2 = 27.8 * 27.8

# --- load plots and process each one ---
plots = gpd.read_file(PLOTS, layer="plots")

results = []   # we'll collect one dict per plot, then build a table

with rasterio.open(HANSEN) as src:
    plots = plots.to_crs(src.crs)   # align CRS objects (harmless, keeps them identical)

    for _, plot in plots.iterrows():
        geom = [plot["geometry"]]

        # windowed read: only this plot's pixels
        out_image, _ = mask(src, geom, crop=True)
        band = out_image[0]

        # count loss pixels
        total_loss_px    = int(np.count_nonzero(band))                   # any non-zero = some loss
        post2020_loss_px = int(np.count_nonzero(band >= EUDR_CUTOFF_VALUE)) # value >= 21

        # convert the EUDR-relevant count to hectares
        post2020_loss_ha = round(post2020_loss_px * PIXEL_AREA_M2 / 10_000, 2)

        # the decision: flagged if ANY post-2020 loss exists
        flagged = post2020_loss_px > 0

        results.append({
            "plot_id":          plot["plot_id"],
            "expected_status":  plot["expected_status"],
            "total_loss_px":    total_loss_px,
            "post2020_loss_px": post2020_loss_px,
            "post2020_loss_ha": post2020_loss_ha,
            "flagged":          flagged,
        })

# --- build a results table and write to PostGIS ---
import pandas as pd
results_df = pd.DataFrame(results)

print(results_df)   # still show it in the terminal

# connection: same Postgres, via laptop port 5433
# ⚠️ password inline is fine for local dev only — see note below
engine = create_engine(
    f"postgresql+psycopg2://eudr:{PG_PASSWORD}@localhost:5433/eudr"
)

results_df.to_sql(
    "plot_loss_results",   # table name
    engine,
    if_exists="replace",   # overwrite on re-run (see idempotency note)
    index=False,           # don't write pandas' row numbers as a column
)
print("\nWrote", len(results_df), "rows to plot_loss_results")