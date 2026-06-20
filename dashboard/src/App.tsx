import { useEffect, useState } from "react";
import Map, { Source, Layer } from "react-map-gl/maplibre";
import type { MapLayerMouseEvent } from "react-map-gl/maplibre";
import type { FeatureCollection } from "geojson";

// the shape of the detail endpoint's response (typed API boundary)
interface PlotDetail {
  plot_id: string;
  status: string;
  status_color: string;
  ndvi_delta: number | null;
  ndvi_baseline: number | null;
  ndvi_current: number | null;
  trend: string | null;
  post2020_loss_ha: number | null;
  loss_severity: string | null;
  hansen_flagged: boolean | null;
  expected_status: string | null;
}

function App() {
  const [plots, setPlots] = useState<FeatureCollection | null>(null);
  const [selected, setSelected] = useState<PlotDetail | null>(null);

  useEffect(() => {
    fetch("/api/plots")
      .then((res) => res.json())
      .then((data: FeatureCollection) => setPlots(data))
      .catch((err) => console.error("Failed to load plots:", err));
  }, []);

  // click handler: find the clicked plot, fetch its detail
  function handleClick(event: MapLayerMouseEvent) {
    console.log("click fired", event.features);
    const feature = event.features?.[0];        // topmost feature under the cursor
    if (!feature) {
      setSelected(null);                         // clicked empty map → clear panel
      return;
    }
    const plotId = feature.properties?.plot_id;
    fetch(`/api/plots/${plotId}`)
      .then((res) => res.json())
      .then((data: PlotDetail) => setSelected(data))
      .catch((err) => console.error("Failed to load detail:", err));
  }

  return (
    <div style={{ position: "relative", width: "100%", height: "100vh", overflow: "hidden" }}>
      <Map
        initialViewState={{ longitude: 110.145, latitude: -1.86, zoom: 12 }}
        style={{ width: "100%", height: "100%" }}
        mapStyle={{
          version: 8,
          sources: {
            satellite: {
              type: "raster",
              tiles: [
                "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
              ],
              tileSize: 256,
              attribution: "Tiles © Esri",   // attribution — keep this
            },
          },
          layers: [
            { id: "satellite", type: "raster", source: "satellite" },
          ],
        }}
        interactiveLayerIds={["plots-fill"]}
        onClick={handleClick}
      >
        {plots && (
          <Source id="plots" type="geojson" data={plots}>
            <Layer id="plots-fill" type="fill"
              paint={{
                "fill-color": ["match", ["get", "status_color"],
                  "green", "#22c55e", "red", "#ef4444", "amber", "#f59e0b",
                  "#9ca3af"],
                "fill-opacity": 0.5,
              }} />
            <Layer id="plots-outline" type="line"
              paint={{ "line-color": "#1f2937", "line-width": 1.5 }} />
          </Source>
        )}
      </Map>

      {/* side panel — only shown when a plot is selected */}
      {selected && (
        <div style={{
          position: "absolute", top: 0, right: 0, height: "100%", width: "320px",
          background: "white", boxShadow: "-2px 0 8px rgba(0,0,0,0.15)",
          padding: "20px", overflowY: "auto", boxSizing: "border-box",
        }}>
          <button onClick={() => setSelected(null)}
            style={{ float: "right", border: "none", background: "none",
                     fontSize: "20px", cursor: "pointer" }}>×</button>
          <h2 style={{ marginTop: 0 , color:"black"}}>{selected.plot_id}</h2>
          <p><strong>Status:</strong>{" "}
            <span style={{ color: selected.status_color }}>{selected.status}</span></p>
          <p><strong>NDVI:</strong> {fmt(selected.ndvi_baseline)} → {fmt(selected.ndvi_current)}
             {" "}(Δ {fmt(selected.ndvi_delta)}, {selected.trend})</p>
          <p><strong>Forest loss:</strong> {fmt(selected.post2020_loss_ha)} ha
             {" "}({selected.loss_severity})</p>
          <p><strong>Hansen flagged:</strong> {selected.hansen_flagged ? "yes" : "no"}</p>
          <p><strong>Expected (label):</strong> {selected.expected_status ?? "—"}</p>
        </div>
      )}
    </div>
  );
}

// small helper: format nullable numbers to 3 decimals, or a dash
function fmt(n: number | null): string {
  return n === null ? "—" : n.toFixed(3);
}

export default App;