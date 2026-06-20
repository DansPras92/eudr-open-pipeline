import pystac_client
import planetary_computer
import rasterio
from rasterio.mask import mask
import geopandas as gpd
import numpy as np
import pandas as pd
import os
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=os.getenv("POSTGRES_PORT", "5433"),
    dbname=os.getenv("POSTGRES_DB", "eudr"),     # <-- confirm this name
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD"),
)

# helper: windowed read of one band for one (already-reprojected) plot
def read_band(href, plot_geom):
    with rasterio.open(href) as src:
        out, _ = mask(src, plot_geom, crop=True, filled=False)
    return out[0]   # drop the band axis → 2D array

def compute_plot_ndvi(item, plot_gdf):
    """NDVI array for one plot from one STAC scene."""
    red_href = item.assets["B04"].href
    nir_href = item.assets["B08"].href

    with rasterio.open(red_href) as src:
        plot_utm = plot_gdf.to_crs(src.crs)   # reproject vector → raster CRS

    red = read_band(red_href, plot_utm.geometry).astype("float32")
    nir = read_band(nir_href, plot_utm.geometry).astype("float32")

    # --- harmonize offset (post-2022 baseline) ---
    boa_offset = item.properties.get("s2:processing_baseline", "00.00")
    if boa_offset >= "04.00":          # baseline ≥ 04.00 added a +1000 offset
        red -= 1000
        nir -= 1000

    return (nir - red) / (nir + red)

catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)

search = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=[110.09, -1.89, 110.20, -1.83],
    datetime="2020-01-01/2020-12-31",
    query={"eo:cloud_cover": {"lt": 20}},
)
items = list(search.items())

# --- the scene + band we're reading ---
baseline = next(i for i in items if "20200615" in i.id and "T49MCT" in i.id)

# add the current scene:
search_current = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=[110.09, -1.89, 110.20, -1.83],
    datetime="2025-05-01/2025-07-31",
    query={"eo:cloud_cover": {"lt": 20}},
)
current_items = list(search_current.items())
current = next(i for i in current_items
               if "20250721" in i.id and "T49MCT" in i.id)

# --- load plots, pick ONE ---
plots = gpd.read_file("data/aoi.gpkg", layer="plots")
one_plot = plots.iloc[[0]]                   # first plot, kept as a GeoDataFrame
print("plot id:", one_plot.iloc[0].get("plot_id", "—"))

ndvi_2020 = compute_plot_ndvi(baseline, one_plot)
ndvi_2025 = compute_plot_ndvi(current, one_plot)

m2020, m2025 = float(np.nanmean(ndvi_2020)), float(np.nanmean(ndvi_2025))
print(f"KTP-001  2020: {m2020:.3f}   2025: {m2025:.3f}   Δ {m2025 - m2020:+.3f}")

# sanity-check the offset actually fired:
print("baseline proc:", baseline.properties.get("s2:processing_baseline"))
print("current  proc:", current.properties.get("s2:processing_baseline"))

# the two scenes, paired with a label for each time point
scenes = [
    ("2020-06-15", baseline),
    ("2025-07-21", current),
]

rows = []
for i in range(len(plots)):
    plot_gdf = plots.iloc[[i]]                       # one-row GeoDataFrame
    plot_id = plot_gdf.iloc[0]["plot_id"]

    for obs_date, item in scenes:
        ndvi = compute_plot_ndvi(item, plot_gdf)
        rows.append({
            "plot_id": plot_id,
            "obs_date": obs_date,
            "mean_ndvi": float(np.nanmean(ndvi)),
        })

# tidy long-format table: one row per (plot, date)
df = pd.DataFrame(rows)
print(df.to_string(index=False))

# pivot to see baseline vs current side by side + delta
pivot = df.pivot(index="plot_id", columns="obs_date", values="mean_ndvi")
pivot["delta"] = pivot["2025-07-21"] - pivot["2020-06-15"]
print("\n", pivot.round(3).to_string())

# --- ensure table exists (idempotent) ---
with conn, conn.cursor() as cur:
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ndvi_observations (
            plot_id    text        NOT NULL,
            obs_date   date        NOT NULL,
            mean_ndvi  real        NOT NULL,
            scene_id   text,
            created_at timestamptz DEFAULT now(),
            PRIMARY KEY (plot_id, obs_date)
        );
    """)

# --- build rows including scene provenance ---
scene_ids = {"2020-06-15": baseline.id, "2025-07-21": current.id}
records = [
    (r["plot_id"], r["obs_date"], r["mean_ndvi"], scene_ids[r["obs_date"]])
    for r in df.to_dict("records")
]

# --- upsert: re-runs overwrite, never duplicate ---
with conn, conn.cursor() as cur:
    execute_values(cur, """
        INSERT INTO ndvi_observations (plot_id, obs_date, mean_ndvi, scene_id)
        VALUES %s
        ON CONFLICT (plot_id, obs_date)
        DO UPDATE SET mean_ndvi = EXCLUDED.mean_ndvi,
                      scene_id   = EXCLUDED.scene_id,
                      created_at = now();
    """, records)

conn.close()
print(f"Upserted {len(records)} rows into ndvi_observations")