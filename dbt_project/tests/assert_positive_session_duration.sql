-- Session recording duration should always be positive when present
-- Returns rows that violate this constraint (should return 0 rows to pass)
select
    session_id,
    recording_duration_seconds
from {{ ref('stg_sessions') }}
where recording_duration_seconds is not null
    and recording_duration_seconds <= 0
