-- One row per therapy session with enriched metrics
-- Grain: session_id
with sessions as (
    select * from {{ ref('stg_sessions') }}
),

transcripts as (
    select * from {{ ref('stg_transcripts') }}
),

chunks as (
    select
        session_id,
        count(*) as chunk_count,
        sum(token_count) as total_tokens,
        count(distinct speaker) as distinct_speakers
    from {{ ref('stg_session_chunks') }}
    group by session_id
),

final as (
    select
        s.session_id,
        s.patient_id,
        s.therapist_id,
        s.consent_id,
        s.session_date,
        s.session_status,
        s.recording_duration_seconds,

        -- Transcript metrics
        t.word_count,
        t.transcript_duration_seconds,
        t.transcript_confidence,
        t.language,

        -- Chunk metrics
        coalesce(c.chunk_count, 0) as chunk_count,
        coalesce(c.total_tokens, 0) as total_tokens,
        coalesce(c.distinct_speakers, 0) as distinct_speakers,

        -- Pipeline timing
        extract(epoch from (t.transcript_created_at - s.session_created_at))
            as seconds_to_transcript,
        extract(epoch from (s.session_updated_at - s.session_created_at))
            as seconds_to_ready,

        -- Status flags
        case when s.session_status = 'ready' then true else false end as is_ready,
        case when s.session_status = 'failed' then true else false end as is_failed,
        s.error_message,

        -- Date key for dim_time join
        s.session_date::date as session_date_key,

        s.session_created_at,
        s.session_updated_at
    from sessions s
    left join transcripts t on s.session_id = t.session_id
    left join chunks c on s.session_id = c.session_id
)

select * from final
