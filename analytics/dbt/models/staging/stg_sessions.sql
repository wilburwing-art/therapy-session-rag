{{ config(materialized='view') }}

-- One row per therapy session recording. Derives the calendar date so
-- marts can GROUP BY day without repeating the cast.
select
    s.id                         as session_id,
    s.patient_id,
    s.therapist_id,
    u.organization_id,
    s.consent_id,
    s.session_date,
    (s.session_date at time zone 'UTC')::date as session_date_utc,
    s.recording_duration_seconds,
    s.recording_duration_seconds / 60.0 as recording_duration_minutes,
    s.status,
    s.session_type,
    s.error_message,
    s.status = 'ready'           as is_ready,
    s.status = 'failed'          as is_failed,
    s.created_at,
    s.updated_at
from {{ source('app', 'sessions') }} s
-- Join users to pick up organization_id since sessions table has no direct
-- org column; therapist's organization is the owner of the session.
left join {{ source('app', 'users') }} u
    on u.id = s.therapist_id
