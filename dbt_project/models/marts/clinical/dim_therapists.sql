-- Therapist dimension with workload and quality metrics
-- Grain: therapist_id
with therapists as (
    select
        user_id as therapist_id,
        organization_id,
        email,
        user_created_at
    from {{ ref('stg_users') }}
    where user_role = 'therapist'
),

session_stats as (
    select
        therapist_id,
        count(*) as total_sessions,
        count(*) filter (where is_ready) as completed_sessions,
        count(*) filter (where is_failed) as failed_sessions,
        count(distinct patient_id) as distinct_patients,
        min(session_date) as first_session_date,
        max(session_date) as last_session_date,
        avg(recording_duration_seconds) as avg_session_duration_seconds,
        avg(word_count) as avg_session_word_count,
        avg(seconds_to_ready) as avg_pipeline_seconds
    from {{ ref('fact_sessions') }}
    group by therapist_id
),

weekly_stats as (
    select
        therapist_id,
        avg(weekly_sessions) as avg_sessions_per_week
    from (
        select
            therapist_id,
            date_trunc('week', session_date) as session_week,
            count(*) as weekly_sessions
        from {{ ref('fact_sessions') }}
        group by therapist_id, date_trunc('week', session_date)
    ) weekly
    group by therapist_id
),

final as (
    select
        t.therapist_id,
        t.organization_id,
        t.email,
        t.user_created_at as therapist_registered_at,

        -- Session metrics
        coalesce(ss.total_sessions, 0) as total_sessions,
        coalesce(ss.completed_sessions, 0) as completed_sessions,
        coalesce(ss.failed_sessions, 0) as failed_sessions,
        coalesce(ss.distinct_patients, 0) as distinct_patients,
        ss.first_session_date,
        ss.last_session_date,
        ss.avg_session_duration_seconds,
        ss.avg_session_word_count,
        ss.avg_pipeline_seconds,

        -- Throughput
        coalesce(ws.avg_sessions_per_week, 0) as avg_sessions_per_week,

        -- Success rate
        case
            when coalesce(ss.total_sessions, 0) > 0
            then round(
                coalesce(ss.completed_sessions, 0)::numeric
                / ss.total_sessions * 100, 2
            )
            else 0
        end as session_success_rate_pct
    from therapists t
    left join session_stats ss on t.therapist_id = ss.therapist_id
    left join weekly_stats ws on t.therapist_id = ws.therapist_id
)

select * from final
