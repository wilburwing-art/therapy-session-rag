{{
    config(
        materialized='incremental',
        unique_key=['organization_id', 'session_date_utc'],
        on_schema_change='sync_all_columns',
        incremental_strategy='delete+insert'
    )
}}

-- Daily session funnel per practice.
-- Grain: (organization_id, session_date_utc).
-- Incremental on session_date_utc; rebuilds the trailing 7 days each run so
-- late-arriving status transitions (e.g. pending -> ready) are captured.

with sessions as (
    select *
    from {{ ref('stg_sessions') }}
    {% if is_incremental() %}
    where session_date_utc >= (select coalesce(max(session_date_utc), '1900-01-01'::date) - interval '7 days' from {{ this }})
    {% endif %}
)

select
    organization_id::text || '|' || session_date_utc::text   as grain_key,
    organization_id,
    session_date_utc,
    count(*)                                                 as session_count,
    count(*) filter (where status = 'pending')               as pending_count,
    count(*) filter (where status = 'uploaded')              as uploaded_count,
    count(*) filter (where status = 'transcribing')          as transcribing_count,
    count(*) filter (where status = 'embedding')             as embedding_count,
    count(*) filter (where status = 'ready')                 as ready_count,
    count(*) filter (where status = 'failed')                as failed_count,
    count(*) filter (where session_type = 'video_call')      as video_call_count,
    count(*) filter (where session_type = 'upload')          as upload_count,
    sum(recording_duration_minutes)                          as total_duration_minutes,
    avg(recording_duration_minutes) filter (where is_ready)  as avg_ready_duration_minutes,
    count(distinct therapist_id)                             as active_therapist_count,
    count(distinct patient_id)                               as active_patient_count
from sessions
where organization_id is not null
group by organization_id, session_date_utc
