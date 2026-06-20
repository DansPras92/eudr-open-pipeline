-- models/loss_area_per_plot.sql
-- Hansen forest-loss area per plot, with a severity band for display.
select
    plot_id,
    expected_status,
    total_loss_px,
    post2020_loss_px,
    post2020_loss_ha,
    flagged as hansen_flagged,
    case
        when post2020_loss_ha = 0    then 'none'
        when post2020_loss_ha < 1    then 'low'
        when post2020_loss_ha < 10   then 'moderate'
        else 'high'
    end as loss_severity
from {{ source('eudr', 'plot_loss_results') }}