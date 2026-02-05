-- Therapist utilization metrics aggregated by period
-- Grain: therapist_id + period_start
-- Useful for exec dashboards: "How busy are our therapists?"
{{ config(materialized='table') }}

with therapist_sessions as (
    select
        fs.therapist_id,
        date_trunc('week', fs.session_date) as period_start,
        count(*) as sessions_in_period,
        count(distinct fs.patient_id) as patients_in_period,
        sum(fs.recording_duration_seconds) as total_duration_seconds,
        avg(fs.recording_duration_seconds) as avg_duration_seconds,
        count(*) filter (where fs.is_ready) as completed_sessions,
        count(*) filter (where fs.is_failed) as failed_sessions,
        avg(fs.word_count) as avg_word_count,
        avg(fs.seconds_to_ready) as avg_pipeline_seconds
    from {{ ref('fact_sessions') }} fs
    group by fs.therapist_id, date_trunc('week', fs.session_date)
),

therapist_info as (
    select
        therapist_id,
        organization_id,
        email
    from {{ ref('dim_therapists') }}
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['ts.therapist_id', 'ts.period_start']) }}
            as utilization_id,
        ts.therapist_id,
        ti.organization_id,
        ti.email as therapist_email,
        ts.period_start,
        (ts.period_start + interval '7 days')::date as period_end,

        -- Volume
        ts.sessions_in_period,
        ts.patients_in_period,
        ts.total_duration_seconds,
        round(ts.total_duration_seconds / 3600.0, 2) as total_hours,
        ts.avg_duration_seconds,

        -- Quality
        ts.completed_sessions,
        ts.failed_sessions,
        case
            when ts.sessions_in_period > 0
            then round(
                ts.completed_sessions::numeric / ts.sessions_in_period * 100, 2
            )
            else 0
        end as success_rate_pct,

        -- Content depth
        ts.avg_word_count,
        ts.avg_pipeline_seconds
    from therapist_sessions ts
    join therapist_info ti on ts.therapist_id = ti.therapist_id
)

select * from final
