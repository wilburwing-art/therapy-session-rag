-- Session outcomes summary by organization and period
-- Grain: organization_id + period_start
-- Useful for exec dashboards: "How reliable is the processing pipeline?"
{{ config(materialized='table') }}

with session_periods as (
    select
        p.organization_id,
        date_trunc('week', fs.session_date) as period_start,
        count(*) as total_sessions,
        count(*) filter (where fs.is_ready) as sessions_ready,
        count(*) filter (where fs.is_failed) as sessions_failed,
        count(*) filter (where fs.session_status = 'pending') as sessions_pending,
        count(*) filter (where fs.session_status = 'transcribing') as sessions_transcribing,
        count(*) filter (where fs.session_status = 'embedding') as sessions_embedding,

        -- Duration stats
        avg(fs.recording_duration_seconds) as avg_recording_duration_seconds,
        percentile_cont(0.5) within group (order by fs.recording_duration_seconds)
            as median_recording_duration_seconds,

        -- Content stats
        avg(fs.word_count) as avg_word_count,
        avg(fs.chunk_count) as avg_chunk_count,
        avg(fs.distinct_speakers) as avg_distinct_speakers,

        -- Pipeline performance
        avg(fs.seconds_to_transcript) as avg_seconds_to_transcript,
        avg(fs.seconds_to_ready) as avg_seconds_to_ready,
        percentile_cont(0.95) within group (order by fs.seconds_to_ready)
            as p95_seconds_to_ready
    from {{ ref('fact_sessions') }} fs
    join {{ ref('stg_users') }} p on fs.patient_id = p.user_id
    group by p.organization_id, date_trunc('week', fs.session_date)
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['sp.organization_id', 'sp.period_start']) }}
            as outcome_id,
        sp.organization_id,
        sp.period_start,
        (sp.period_start + interval '7 days')::date as period_end,

        -- Volume
        sp.total_sessions,
        sp.sessions_ready,
        sp.sessions_failed,
        sp.sessions_pending,
        sp.sessions_transcribing,
        sp.sessions_embedding,

        -- Success rate
        case
            when sp.total_sessions > 0
            then round(sp.sessions_ready::numeric / sp.total_sessions * 100, 2)
            else 0
        end as success_rate_pct,
        case
            when sp.total_sessions > 0
            then round(sp.sessions_failed::numeric / sp.total_sessions * 100, 2)
            else 0
        end as failure_rate_pct,

        -- Duration
        round(sp.avg_recording_duration_seconds::numeric, 2) as avg_recording_duration_seconds,
        round(sp.median_recording_duration_seconds::numeric, 2)
            as median_recording_duration_seconds,

        -- Content quality
        round(sp.avg_word_count::numeric, 0) as avg_word_count,
        round(sp.avg_chunk_count::numeric, 1) as avg_chunk_count,
        round(sp.avg_distinct_speakers::numeric, 1) as avg_distinct_speakers,

        -- Pipeline SLA
        round(sp.avg_seconds_to_transcript::numeric, 2) as avg_seconds_to_transcript,
        round(sp.avg_seconds_to_ready::numeric, 2) as avg_seconds_to_ready,
        round(sp.p95_seconds_to_ready::numeric, 2) as p95_seconds_to_ready
    from session_periods sp
)

select * from final
