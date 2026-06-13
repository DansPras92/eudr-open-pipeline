# EUDR Compliance Pipeline

Detects post-2020 deforestation on agricultural plots by cross-referencing
plot boundaries against Hansen Global Forest Change data — a working model of
the geolocation and deforestation checks required by the EU Deforestation Regulation (EUDR).

## Background

The EUDR requires that products sold into the EU do not originate from land
deforested or degraded after **31 December 2020**. Operators must submit
high-precision geolocation coordinates linking each product to a specific plot,
alongside evidence of legal, deforestation-free production. The regulation is
**origin-neutral** — it applies to any company placing covered goods on the EU
market, regardless of where production happened — so non-EU producers are equally
in scope. Covered commodities are cattle, cocoa, palm oil, rubber, soy, and wood,
plus derived products (leather, chocolate, tyres, and others).

Enforcement begins December 2026 for large operators, but the 2020 cutoff is fixed —
meaning land cleared at any point from 2021 onward already fails the test.

## What this pipeline does

Given a set of plot boundaries, it checks each one against Hansen Global Forest
Change data and flags any plot showing tree-cover loss after 2020 — the core
"is this plot EUDR-compliant?" question.

**Components:**

| Component | Role |
|---|---|
| **QGIS** | Digitize synthetic plot boundaries and AOI; export GeoPackage |
| **PostGIS (Postgres 16 + PostGIS 3.4)** | Store plot geometries and loss results; spatial queries |
| **Hansen Global Forest Change (v1.12)** | Annual ~30 m global tree-cover-loss raster — the deforestation source |
| **Python + rasterio / geopandas** | Windowed raster reads, per-plot post-2020 loss detection |
| **Docker Compose** | Reproducible local stack (Postgres + Airflow) |
| **Airflow 3** | Orchestration (scaffolded; pipeline DAG planned for a later milestone) |

## Running it locally

**Prerequisites:** Docker + Docker Compose, Python 3.12, QGIS (provides
`ogr2ogr` / `gdalinfo`).

### 1. Clone and configure

```bash
git clone https://github.com/<your-username>/eudr-open-pipeline.git
cd eudr-open-pipeline

cp .env.example .env                                   # then set POSTGRES_PASSWORD
cp docker-compose.override.yml.example docker-compose.override.yml
```

Use a URL-safe password (e.g. `openssl rand -hex 16`) — it is embedded in a
connection string.

### 2. Start the stack

```bash
docker compose up -d
docker compose exec postgres psql -U eudr -d eudr -c "SELECT postgis_version();"
```

PostGIS is enabled automatically on first boot via `init/`. Postgres is exposed
on host port **5433**; the Airflow UI on **http://localhost:8080**.

### 3. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Create plot data (QGIS)

This repo ships no plot data — you supply your own. In QGIS, over your chosen
area of interest:

1. Create a GeoPackage `data/aoi.gpkg` with two polygon layers (EPSG:4326):
   - `aoi` — one polygon, the study-area boundary
   - `plots` — your plot polygons, with text fields `plot_id`, `commodity`,
     `expected_status` (`forest` or `deforested`)
2. Digitize a handful of plots inside the AOI and save.

### 5. Get the matching forest-loss tile

Hansen tiles are 10°×10°, named by their **top-left** corner. Find the tile
covering your AOI and download its `lossyear` layer. For an AOI around
110°E / 1.8°S, that is `00N_110E`:

```bash
mkdir -p data/hansen
wget -P data/hansen \
  https://storage.googleapis.com/earthenginepartners-hansen/GFC-2024-v1.12/Hansen_GFC-2024-v1.12_lossyear_00N_110E.tif
```

Update the `HANSEN` path in `scripts/02_detect_loss.py` if you use a different tile.

### 6. Load plots and run detection

```bash
export POSTGRES_PASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d= -f2)

# load plots into PostGIS
ogr2ogr -f PostgreSQL PG:"host=localhost port=5433 dbname=eudr user=eudr password=$POSTGRES_PASSWORD" \
  data/aoi.gpkg plots -nln plots -lco GEOMETRY_NAME=geom -nlt PROMOTE_TO_MULTI

# detect post-2020 loss per plot → writes plot_loss_results
python scripts/02_detect_loss.py

# inspect results
docker compose exec postgres psql -U eudr -d eudr -c \
  "SELECT plot_id, expected_status, post2020_loss_ha, flagged FROM plot_loss_results ORDER BY plot_id;"
```

## Data sources & credits

| Source | Use | License |
|---|---|---|
| [Hansen Global Forest Change v1.12](https://glad.earthengine.app/view/global-forest-change) | Post-2020 tree-cover-loss detection | CC-BY 4.0 |
| [Esri World Imagery](https://www.esri.com) | Basemap for digitizing plots (QGIS) | Esri terms of use |
| OpenStreetMap | Reference basemap | ODbL |

Plot boundaries are **synthetic**, digitized for demonstration only — they do not
represent real farms or any commercial operation.

**Hansen GFC citation (required by CC-BY 4.0):**

> Hansen, M. C., P. V. Potapov, R. Moore, M. Hancher, S. A. Turubanova,
> A. Tyukavina, D. Thau, S. V. Stehman, S. J. Goetz, T. R. Loveland,
> A. Kommareddy, A. Egorov, L. Chini, C. O. Justice, and J. R. G. Townshend.
> 2013. "High-Resolution Global Maps of 21st-Century Forest Cover Change."
> *Science* 342: 850–853. Data: Global Forest Change 2000–2024 (v1.12).

## Status & roadmap

This is a learning/portfolio project, built in milestones.

- [x] **M0 — Stack:** Docker Compose (Postgres 16 + PostGIS 3.4, Airflow 3),
      reproducible cold-start
- [x] **M1 — Loss detection:** synthetic plots → PostGIS; Hansen windowed reads;
      per-plot post-2020 loss flagging; results self-validated against eyeball labels
- [ ] **M2 — Sentinel-2 NDVI:** STAC queries, windowed COG reads, NDVI time series
      (2020 baseline vs current) per plot
- [ ] **M3 — Orchestration:** single Airflow DAG, idempotent tasks, retries/logging
- [ ] **M4 — Reporting:** dbt models + React/MapLibre map dashboard
- [ ] **M5 — Write-up:** architecture notes, design-decision log