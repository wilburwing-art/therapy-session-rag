-- SCD Type 2 snapshot of consent status changes
-- Tracks the full history of consent state transitions
{% snapshot consent_snapshot %}

{{
    config(
        target_schema='snapshots',
        unique_key='id',
        strategy='check',
        check_cols=['status'],
    )
}}

select
    id,
    patient_id,
    therapist_id,
    consent_type,
    status,
    granted_at,
    revoked_at,
    consent_metadata
from {{ source('therapy_rag', 'consents') }}

{% endsnapshot %}
