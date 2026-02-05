-- Cleaned experiment variant assignments
select
    id as assignment_id,
    experiment_id,
    subject_id,
    variant,
    assigned_at,
    created_at,
    updated_at
from {{ source('therapy_rag', 'experiment_assignments') }}
