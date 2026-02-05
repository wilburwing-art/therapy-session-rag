-- Excludes embedding vector column (not useful for analytics)
with source as (
    select * from {{ source('therapy_rag', 'session_chunks') }}
),

renamed as (
    select
        id as chunk_id,
        session_id,
        transcript_id,
        chunk_index,
        content,
        start_time as chunk_start_time,
        end_time as chunk_end_time,
        speaker,
        token_count,
        chunk_metadata,
        created_at as chunk_created_at,
        updated_at as chunk_updated_at
    from source
)

select * from renamed
