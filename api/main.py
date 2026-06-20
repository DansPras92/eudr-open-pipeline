from fastapi import FastAPI, HTTPException
from db import fetch_all
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="EUDR Plot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

PLOTS_QUERY = """
    SELECT
        p.plot_id
        ,r.status
        ,r.status_color
        ,r.ndvi_delta
        ,r.post2020_loss_ha
        ,ST_AsGeoJSON(p.geom)::json AS geometry
    FROM public.plots as p
    JOIN analytics.plot_risk_status as r USING (plot_id);
"""

PLOT_DETAIL_QUERY = """
    SELECT
        r.plot_id,
        r.status,
        r.status_color,
        r.ndvi_delta,
        r.post2020_loss_ha,
        r.expected_status,
        t.ndvi_baseline,
        t.ndvi_current,
        t.trend,
        l.loss_severity,
        l.hansen_flagged
    FROM analytics.plot_risk_status r
    LEFT JOIN analytics.ndvi_trend t        USING (plot_id)
    LEFT JOIN analytics.loss_area_per_plot l USING (plot_id)
    WHERE r.plot_id = %s;
"""

@app.get("/api/plots")
def get_plots():
    rows = fetch_all(PLOTS_QUERY)

    features = [
        {
            "type": "Feature",
            "geometry": row["geometry"],
            "properties": {
                "plot_id": row["plot_id"],
                "status": row["status"],
                "status_color": row["status_color"],
                "ndvi_delta": float(row["ndvi_delta"])
                            if row["ndvi_delta"] is not None else None,
                "post2020_loss_ha": float(row["post2020_loss_ha"])
                            if row["post2020_loss_ha"] is not None else None,
            },
        }
        for row in rows
    ]

    return {"type": "FeatureCollection", "features": features}

@app.get("/api/plots/{plot_id}")
def get_plot(plot_id: str):
    rows = fetch_all(PLOT_DETAIL_QUERY,(plot_id,))

    if not rows:
        raise HTTPException(status_code=404, detail=f"plot '{plot_id}' not found")
    
    row = rows[0]
    for key in ("ndvi_delta", "post2020_loss_ha", "ndvi_baseline", "ndvi_current"):
        if row.get(key) is not None:
            row[key] = float(row[key])
    
    return row

@app.get("/health")
def health():
    return {"status": "ok"}