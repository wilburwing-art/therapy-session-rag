with source as (
    select * from {{ source('therapy_rag', 'consents') }}
),

renamed as (
    select
        id as consent_id,
        patient_id,
        therapist_id,
        consent_type,
        status as consent_status,
        granted_at,
        revoked_at,
        ip_address,
        user_agent,
        consent_metadata
    from source
)

select * from renamed
