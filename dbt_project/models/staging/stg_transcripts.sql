with source as (
    select * from {{ source('therapy_rag', 'transcripts') }}
),

renamed as (
    select
        id as transcript_id,
        session_id,
        job_id as transcription_job_id,
        full_text,
        segments,
        word_count,
        duration_seconds as transcript_duration_seconds,
        language,
        confidence as transcript_confidence,
        transcript_metadata,
        created_at as transcript_created_at,
        updated_at as transcript_updated_at
    from source
)

select * from renamed
