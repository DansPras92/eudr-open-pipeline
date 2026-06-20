-- models/plot_risk_status.sql
-- Dashboard-ready view: one row per plot with verdict + the context behind it.

select
    plot_id,
    status,
    ndvi_delta,
    post2020_loss_ha,
    expected_status,
    -- a display helper: map status → a colour the dashboard can use directly
    case status
        when 'compliant'     then 'green'
        when 'non-compliant' then 'red'
        when 'needs-review'  then 'amber'
    end as status_color,
    checked_at
from {{ source('eudr', 'plot_compliance') }}