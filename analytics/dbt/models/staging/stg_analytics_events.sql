{{ config(materialized='view') }}

-- One row per analytics event. Surfaces a few commonly-used properties via
-- the get_properties_field macro so marts don't have to repeat the JSONB
-- gymnastics.
select
    id                                  as event_id,
    event_name,
    event_category,
    actor_id,
    organization_id,
    session_id,
    event_timestamp,
    (event_timestamp at time zone 'UTC')::date as event_date_utc,
    received_at,
    properties,
    contexts,
    retain_forever,
    {{ get_properties_field('source', 'text') }}              as prop_source,
    {{ get_properties_field('duration_ms', 'int') }}          as prop_duration_ms,
    {{ get_properties_field('model_name', 'text') }}          as prop_model_name,
    {{ get_properties_field('risk_flag', 'text') }}           as prop_risk_flag
from {{ source('app', 'analytics_events') }}
