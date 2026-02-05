-- Cleaned experiment definitions
select
    id as experiment_id,
    name as experiment_name,
    description as experiment_description,
    status as experiment_status,
    organization_id,
    variants,
    targeting_rules,
    traffic_percentage,
    started_at,
    ended_at,
    created_at,
    updated_at
from {{ source('therapy_rag', 'experiments') }}
