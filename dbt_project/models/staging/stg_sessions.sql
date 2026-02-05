with source as (
    select * from {{ source('therapy_rag', 'sessions') }}
),

renamed as (
    select
        id as session_id,
        patient_id,
        therapist_id,
        consent_id,
        session_date,
        recording_path,
        recording_duration_seconds,
        status as session_status,
        error_message,
        session_metadata,
        created_at as session_created_at,
        updated_at as session_updated_at
    from source
)

select * from renamed
