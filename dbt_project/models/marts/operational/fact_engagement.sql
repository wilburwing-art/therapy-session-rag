-- Daily patient engagement aggregation
-- Grain: patient_id + activity_date
with daily_sessions as (
    select
        patient_id,
        session_date::date as activity_date,
        count(*) as sessions_count,
        sum(recording_duration_seconds) as total_recording_seconds,
        avg(recording_duration_seconds) as avg_recording_seconds
    from {{ ref('fact_sessions') }}
    group by patient_id, session_date::date
),

daily_messages as (
    select
        user_id as patient_id,
        message_date_key as activity_date,
        count(*) as messages_count,
        avg(source_count) as avg_sources_per_message
    from {{ ref('fact_messages') }}
    group by user_id, message_date_key
),

daily_consent_changes as (
    select
        patient_id,
        granted_at::date as activity_date,
        count(*) filter (where consent_status = 'granted') as consents_granted,
        count(*) filter (where consent_status = 'revoked') as consents_revoked
    from {{ ref('stg_consents') }}
    group by patient_id, granted_at::date
),

-- Combine all activity dates per patient
all_dates as (
    select patient_id, activity_date from daily_sessions
    union
    select patient_id, activity_date from daily_messages
    union
    select patient_id, activity_date from daily_consent_changes
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['ad.patient_id', 'ad.activity_date']) }}
            as engagement_id,
        ad.patient_id,
        ad.activity_date,

        -- Session activity
        coalesce(ds.sessions_count, 0) as sessions_count,
        coalesce(ds.total_recording_seconds, 0) as total_recording_seconds,
        ds.avg_recording_seconds,

        -- Chat activity
        coalesce(dm.messages_count, 0) as messages_count,
        dm.avg_sources_per_message,

        -- Consent activity
        coalesce(dc.consents_granted, 0) as consents_granted,
        coalesce(dc.consents_revoked, 0) as consents_revoked,

        -- Combined engagement score (weighted)
        coalesce(ds.sessions_count, 0) * 10
            + coalesce(dm.messages_count, 0) * 2
            + coalesce(dc.consents_granted, 0) * 1
            as engagement_score
    from all_dates ad
    left join daily_sessions ds
        on ad.patient_id = ds.patient_id and ad.activity_date = ds.activity_date
    left join daily_messages dm
        on ad.patient_id = dm.patient_id and ad.activity_date = dm.activity_date
    left join daily_consent_changes dc
        on ad.patient_id = dc.patient_id and ad.activity_date = dc.activity_date
)

select * from final
