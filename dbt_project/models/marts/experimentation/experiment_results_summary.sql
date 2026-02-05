-- Summary statistics per experiment per variant per metric
-- Provides the data needed for significance testing in dashboards
with fact_metrics as (
    select * from {{ ref('fact_experiment_metrics') }}
),

experiments as (
    select * from {{ ref('stg_experiments') }}
)

select
    {{ dbt_utils.generate_surrogate_key([
        'f.experiment_id',
        'f.variant',
        'f.metric_name'
    ]) }} as result_key,
    f.experiment_id,
    f.experiment_name,
    f.experiment_status,
    f.organization_id,
    f.variant,
    f.metric_name,
    count(distinct f.subject_id) as subject_count,
    count(*) as observation_count,
    avg(f.metric_value) as metric_mean,
    stddev(f.metric_value) as metric_stddev,
    min(f.metric_value) as metric_min,
    max(f.metric_value) as metric_max,
    percentile_cont(0.5) within group (order by f.metric_value) as metric_median,
    percentile_cont(0.25) within group (order by f.metric_value) as metric_p25,
    percentile_cont(0.75) within group (order by f.metric_value) as metric_p75,
    avg(f.seconds_since_assignment) as avg_seconds_to_conversion,
    e.traffic_percentage,
    e.started_at as experiment_started_at,
    e.ended_at as experiment_ended_at,
    -- Duration of experiment in days (null if still running)
    extract(day from coalesce(e.ended_at, now()) - e.started_at) as experiment_duration_days
from fact_metrics f
inner join experiments e
    on f.experiment_id = e.experiment_id
group by
    f.experiment_id,
    f.experiment_name,
    f.experiment_status,
    f.organization_id,
    f.variant,
    f.metric_name,
    e.traffic_percentage,
    e.started_at,
    e.ended_at
