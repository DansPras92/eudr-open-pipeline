# src/eudr/cross_check.py
"""Combine Hansen loss + NDVI change into a per-plot EUDR verdict."""

NDVI_DROP_THRESHOLD = -0.10        # Δ at or below this = significant vegetation loss

def classify_plot(hansen_flagged: bool, ndvi_delta: float) -> str:
    """One plot's compliance status from its two signals.

    hansen_flagged: did Hansen detect post-2020 forest loss?
    ndvi_delta:     current NDVI minus baseline NDVI (negative = greener→barer)
    """
    ndvi_dropped = ndvi_delta <= NDVI_DROP_THRESHOLD

    if hansen_flagged:
        # Hansen is authoritative for the EUDR call: loss since 2020 = non-compliant.
        # But if NDVI strongly recovered, flag for review (regrowth vs. mislabel).
        if not ndvi_dropped and ndvi_delta > 0.10:
            return "needs-review"      # Hansen says loss, NDVI says greener (KTP-010 case)
        return "non-compliant"

    # Hansen sees no loss...
    if ndvi_dropped:
        return "needs-review"          # NDVI fell but Hansen quiet — too small/recent, or missed
    return "compliant"

# src/eudr/cross_check.py  (append below classify_plot)

JOIN_QUERY = """
WITH ndvi_pivot AS (
    SELECT plot_id,
        MIN(mean_ndvi) FILTER (WHERE obs_date = first_date) AS ndvi_baseline,
        MIN(mean_ndvi) FILTER (WHERE obs_date = last_date)  AS ndvi_current
    FROM (SELECT plot_id, obs_date, mean_ndvi,
                 MIN(obs_date) OVER (PARTITION BY plot_id) AS first_date,
                 MAX(obs_date) OVER (PARTITION BY plot_id) AS last_date
          FROM ndvi_observations) t
    GROUP BY plot_id
)
SELECT l.plot_id, l.flagged, (n.ndvi_current - n.ndvi_baseline) AS ndvi_delta,
       l.post2020_loss_ha, l.expected_status
FROM plot_loss_results l JOIN ndvi_pivot n USING (plot_id);
"""

def build_verdicts(rows):
    """Turn joined DB rows into verdict tuples ready for upsert.
    rows: iterable of (plot_id, flagged, ndvi_delta, loss_ha, expected_status)
    """
    out = []
    for plot_id, flagged, ndvi_delta, loss_ha, expected in rows:
        status = classify_plot(bool(flagged), float(ndvi_delta))
        out.append((plot_id, status, float(ndvi_delta), loss_ha, expected))
    return out