# src/eudr/loss.py
"""Hansen forest-loss detection per plot — pure logic, no DB."""
import numpy as np
import rasterio
from rasterio.mask import mask

# EUDR cutoff 31 Dec 2020 → loss in 2021+. Hansen encodes year as (2000 + value).
EUDR_CUTOFF_VALUE = 21
# ~27.8 m per pixel at this latitude → m² per pixel
PIXEL_AREA_M2 = 27.8 * 27.8


def loss_records(hansen_path: str, plots) -> list:
    """Per-plot Hansen loss → list of (plot_id, expected_status,
    total_loss_px, post2020_loss_px, post2020_loss_ha, flagged) tuples.
    plots: GeoDataFrame with plot_id, expected_status, geometry.
    """
    records = []
    with rasterio.open(hansen_path) as src:
        plots = plots.to_crs(src.crs)
        for _, plot in plots.iterrows():
            out_image, _ = mask(src, [plot["geom"]], crop=True)
            band = out_image[0]

            total_loss_px    = int(np.count_nonzero(band))
            post2020_loss_px = int(np.count_nonzero(band >= EUDR_CUTOFF_VALUE))
            post2020_loss_ha = round(post2020_loss_px * PIXEL_AREA_M2 / 10_000, 2)
            flagged          = post2020_loss_px > 0

            records.append((
                plot["plot_id"],
                plot["expected_status"],
                total_loss_px,
                post2020_loss_px,
                post2020_loss_ha,
                flagged,
            ))
    return records