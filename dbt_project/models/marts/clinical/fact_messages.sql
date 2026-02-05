-- One row per chat message event
-- Grain: event_id (for chat.message_sent events)
with chat_events as (
    select
        event_id,
        actor_id,
        organization_id,
        session_id,
        event_properties,
        event_timestamp,
        event_received_at
    from {{ ref('stg_events') }}
    where event_name = 'chat.message_sent'
),

final as (
    select
        event_id as message_event_id,
        actor_id as user_id,
        organization_id,
        session_id,

        -- Extract chat-specific properties
        (event_properties->>'message_length')::int as message_length,
        (event_properties->>'top_k')::int as top_k,
        (event_properties->>'source_count')::int as source_count,
        (event_properties->>'has_conversation_id')::boolean as has_conversation_id,

        -- Timing
        event_timestamp as message_sent_at,
        event_timestamp::date as message_date_key,

        -- Ingestion lag
        extract(epoch from (event_received_at - event_timestamp))
            as ingestion_lag_seconds
    from chat_events
)

select * from final
