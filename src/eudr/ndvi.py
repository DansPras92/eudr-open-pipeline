# src/eudr/ndvi.py
"""NDVI computation from Sentinel-2 scenes — pure logic, no Airflow/DB."""
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.mask import mask
import pystac_client
import planetary_computer

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"


def open_scenes(scene_ids: dict) -> dict:
    """Re-open STAC items from their IDs, keyed by actual capture date.
    scene_ids: {"baseline": "S2A_...", "current": "S2A_..."}
    returns:   {"2020-06-15": <item>, "2025-07-21": <item>}
    """
    catalog = pystac_client.Client.open(
        STAC_URL, modifier=planetary_computer.sign_inplace
    )

    def item_by_id(scene_id):
        return next(catalog.search(
            collections=["sentinel-2-l2a"],
            ids=[scene_id],
        ).items())

    items = {}
    for role in ("baseline", "current"):
        item = item_by_id(scene_ids[role])
        items[item.datetime.date().isoformat()] = item
    return items


def _read_band(href, geom):
    """Windowed COG read clipped to a plot geometry."""
    with rasterio.open(href) as src:
        out, _ = mask(src, geom, crop=True, filled=False)
    return out[0]


def compute_plot_ndvi(item, plot_gdf):
    """NDVI array for one plot from one scene (reproject + offset-harmonize)."""
    red_href, nir_href = item.assets["B04"].href, item.assets["B08"].href
    with rasterio.open(red_href) as src:
        plot_utm = plot_gdf.to_crs(src.crs)          # vector → raster CRS
    red = _read_band(red_href, plot_utm.geometry).astype("float32")
    nir = _read_band(nir_href, plot_utm.geometry).astype("float32")
    if item.properties.get("s2:processing_baseline", "00.00") >= "04.00":
        red -= 1000; nir -= 1000                     # +1000 offset (baseline ≥ 04.00)
    return (nir - red) / (nir + red)


def ndvi_records(items: dict, plots) -> list:
    """Loop plots × scenes → list of (plot_id, obs_date, mean_ndvi, scene_id) tuples.
    items: output of open_scenes(). plots: GeoDataFrame with plot_id + geom.
    """
    records = []
    for i in range(len(plots)):
        plot_gdf = plots.iloc[[i]]
        plot_id = plot_gdf.iloc[0]["plot_id"]
        for obs_date, item in items.items():
            ndvi = compute_plot_ndvi(item, plot_gdf)
            records.append((plot_id, obs_date, float(np.nanmean(ndvi)), item.id))
    return records