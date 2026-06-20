-- models/ndvi_trend.sql
-- One row per plot: baseline vs current NDVI + change direction.
with pivoted as (
    select
        plot_id,
        min(mean_ndvi) filter (where obs_date = first_date) as ndvi_baseline,
        min(mean_ndvi) filter (where obs_date = last_date)  as ndvi_current,
        min(obs_date) as baseline_date,
        max(obs_date) as current_date
    from (
        select plot_id, obs_date, mean_ndvi,
               min(obs_date) over (partition by plot_id) as first_date,
               max(obs_date) over (partition by plot_id) as last_date
        from {{ source('eudr', 'ndvi_observations') }}
    ) t
    group by plot_id
)
select
    plot_id,
    ndvi_baseline,
    ndvi_current,
    ndvi_current - ndvi_baseline as ndvi_delta,
    case
        when ndvi_current - ndvi_baseline <= -0.10 then 'declining'
        when ndvi_current - ndvi_baseline >=  0.10 then 'recovering'
        else 'stable'
    end as trend,
    baseline_date,
    current_date
from pivoted