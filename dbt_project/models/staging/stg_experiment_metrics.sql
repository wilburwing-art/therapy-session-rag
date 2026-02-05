-- Cleaned experiment metric observations
select
    id as metric_id,
    experiment_id,
    subject_id,
    metric_name,
    metric_value,
    recorded_at
from {{ source('therapy_rag', 'experiment_metrics') }}
