-- Patient dimension with session history metrics
-- Grain: patient_id
with patients as (
    select
        user_id as patient_id,
        organization_id,
        email,
        user_created_at
    from {{ ref('stg_users') }}
    where user_role = 'patient'
),

session_stats as (
    select
        patient_id,
        count(*) as total_sessions,
        count(*) filter (where is_ready) as completed_sessions,
        count(*) filter (where is_failed) as failed_sessions,
        min(session_date) as first_session_date,
        max(session_date) as last_session_date,
        avg(recording_duration_seconds) as avg_session_duration_seconds,
        avg(word_count) as avg_word_count,
        avg(chunk_count) as avg_chunk_count
    from {{ ref('fact_sessions') }}
    group by patient_id
),

message_stats as (
    select
        e.actor_id as patient_id,
        count(*) as total_messages
    from {{ ref('stg_events') }} e
    where e.event_name = 'chat.message_sent'
    group by e.actor_id
),

consent_stats as (
    select
        patient_id,
        count(*) filter (where consent_status = 'granted') as total_consents_granted,
        count(*) filter (where consent_status = 'revoked') as total_consents_revoked
    from {{ ref('stg_consents') }}
    group by patient_id
),

final as (
    select
        p.patient_id,
        p.organization_id,
        p.email,
        p.user_created_at as patient_registered_at,

        -- Session metrics
        coalesce(ss.total_sessions, 0) as total_sessions,
        coalesce(ss.completed_sessions, 0) as completed_sessions,
        coalesce(ss.failed_sessions, 0) as failed_sessions,
        ss.first_session_date,
        ss.last_session_date,
        ss.avg_session_duration_seconds,
        ss.avg_word_count,
        ss.avg_chunk_count,

        -- Tenure
        case
            when ss.first_session_date is not null
            then extract(day from (current_timestamp - ss.first_session_date))
            else 0
        end as tenure_days,

        -- Chat engagement
        coalesce(ms.total_messages, 0) as total_chat_messages,

        -- Consent history
        coalesce(cs.total_consents_granted, 0) as total_consents_granted,
        coalesce(cs.total_consents_revoked, 0) as total_consents_revoked
    from patients p
    left join session_stats ss on p.patient_id = ss.patient_id
    left join message_stats ms on p.patient_id = ms.patient_id
    left join consent_stats cs on p.patient_id = cs.patient_id
)

select * from final
