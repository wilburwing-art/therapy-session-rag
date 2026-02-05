-- System event metrics for pipeline monitoring
-- Grain: event_id (system and performance events)
with system_events as (
    select
        event_id,
        event_name,
        event_category,
        organization_id,
        session_id,
        event_properties,
        event_contexts,
        event_timestamp,
        event_received_at
    from {{ ref('stg_events') }}
    where event_category in ('system', 'performance')
),

final as (
    select
        event_id,
        event_name,
        event_category,
        organization_id,
        session_id,

        -- Common event properties
        event_properties,

        -- Pipeline stage classification
        case
            when event_name like 'session.%' then 'session_lifecycle'
            when event_name like 'transcription.%' then 'transcription_pipeline'
            when event_name like 'embedding.%' then 'embedding_pipeline'
            when event_name like 'request.%' then 'api_request'
            else 'other'
        end as pipeline_stage,

        -- Request context (if available)
        event_contexts->'request'->>'method' as request_method,
        event_contexts->'request'->>'path' as request_path,
        (event_contexts->'request'->>'duration_ms')::numeric as request_duration_ms,
        (event_contexts->'request'->>'status_code')::int as response_status_code,

        event_timestamp,
        event_timestamp::date as event_date_key,
        extract(epoch from (event_received_at - event_timestamp))
            as ingestion_lag_seconds
    from system_events
)

select * from final
