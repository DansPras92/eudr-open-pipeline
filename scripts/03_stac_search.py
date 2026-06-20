import pystac_client
import planetary_computer
import geopandas as gpd
from shapely.geometry import shape, box

# 1. Open the catalog. This URL is Planetary Computer's STAC API root.
catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,  # <-- the URL-signing wrinkle
)

# 2. The four-question search from last session
search = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=[110.09, -1.89, 110.20, -1.83],   # your Ketapang box, EPSG:4326
    datetime="2020-01-01/2020-12-31",      # 2020 baseline window
    query={"eo:cloud_cover": {"lt": 20}},
)

# 3. Pull results into a list and inspect — no pixels read yet
items = list(search.items())
print(f"{len(items)} scenes found\n")

# All scenes from the clean baseline date
june15 = [item for item in items if "20200615" in item.id]

plots = gpd.read_file("data/aoi.gpkg", layer="plots") #adjust path/layer

baseline = next(i for i in june15 if "T49MCT" in i.id)
fp = shape(baseline.geometry)

# does this single tile contain every plot?
inside = plots.geometry.within(fp)
print(f"{inside.sum()} / {len(plots)} plots inside T49MCT")

# Current time point: same season (mid-year), most recent year
search_current = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=[110.09, -1.89, 110.20, -1.83],
    datetime="2025-05-01/2025-07-31",      # ~June ±6 weeks, mirrors baseline season
    query={"eo:cloud_cover": {"lt": 20}},
)
current_items = list(search_current.items())
print(f"{len(current_items)} candidate scenes\n")

# Same filter discipline as before: T49MCT only, sorted by cloud
mct = [i for i in current_items if "T49MCT" in i.id]
mct.sort(key=lambda i: i.properties["eo:cloud_cover"])

for i in mct:
    print(i.id, "|", i.datetime.date(), "|",
          f"{i.properties['eo:cloud_cover']:.1f}% cloud")