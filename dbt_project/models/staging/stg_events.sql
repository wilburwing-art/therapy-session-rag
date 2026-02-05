with source as (
    select * from {{ source('therapy_rag', 'analytics_events') }}
),

renamed as (
    select
        id as event_id,
        event_name,
        event_category,
        actor_id,
        organization_id,
        session_id,
        properties as event_properties,
        contexts as event_contexts,
        event_timestamp,
        received_at as event_received_at
    from source
)

select * from renamed
