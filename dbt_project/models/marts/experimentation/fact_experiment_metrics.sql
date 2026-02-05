-- 1 row per metric observation with assignment context
-- Joins metrics to assignments to get the variant each subject was in
with metrics as (
    select * from {{ ref('stg_experiment_metrics') }}
),

assignments as (
    select * from {{ ref('stg_experiment_assignments') }}
),

experiments as (
    select * from {{ ref('stg_experiments') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['m.metric_id']) }} as metric_key,
    m.metric_id,
    m.experiment_id,
    e.experiment_name,
    e.experiment_status,
    e.organization_id,
    m.subject_id,
    a.variant,
    m.metric_name,
    m.metric_value,
    m.recorded_at,
    a.assigned_at,
    -- Time from assignment to metric recording
    extract(epoch from (m.recorded_at - a.assigned_at)) as seconds_since_assignment
from metrics m
inner join assignments a
    on m.experiment_id = a.experiment_id
    and m.subject_id = a.subject_id
inner join experiments e
    on m.experiment_id = e.experiment_id
