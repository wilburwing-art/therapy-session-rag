-- AI safety and chat quality metrics by organization and period
-- Grain: organization_id + period_start
-- Useful for compliance dashboards and AI governance reporting
-- Will be enriched with Phase 4 safety events (safety.risk_detected, safety.guardrail_triggered)
{{ config(materialized='table') }}

with chat_metrics as (
    select
        fm.organization_id,
        date_trunc('week', fm.message_sent_at) as period_start,
        count(*) as total_messages,
        avg(fm.message_length) as avg_message_length,
        avg(fm.source_count) as avg_sources_per_response,
        count(*) filter (where fm.source_count = 0) as zero_source_responses,
        count(*) filter (where fm.source_count > 0) as grounded_responses,
        avg(fm.top_k) as avg_top_k_requested
    from {{ ref('fact_messages') }} fm
    group by fm.organization_id, date_trunc('week', fm.message_sent_at)
),

-- Safety events (will be populated after Phase 4 implementation)
safety_events as (
    select
        organization_id,
        date_trunc('week', event_timestamp) as period_start,
        count(*) filter (where event_name = 'safety.risk_detected') as risk_detections,
        count(*) filter (where event_name = 'safety.guardrail_triggered') as guardrail_triggers,
        count(*) filter (where event_name = 'safety.escalation_created') as escalations
    from {{ ref('stg_events') }}
    where event_name like 'safety.%'
    group by organization_id, date_trunc('week', event_timestamp)
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['cm.organization_id', 'cm.period_start']) }}
            as safety_metric_id,
        cm.organization_id,
        cm.period_start,
        (cm.period_start + interval '7 days')::date as period_end,

        -- Chat volume
        cm.total_messages,
        cm.avg_message_length,

        -- RAG quality indicators
        cm.avg_sources_per_response,
        cm.zero_source_responses,
        cm.grounded_responses,
        case
            when cm.total_messages > 0
            then round(
                cm.grounded_responses::numeric / cm.total_messages * 100, 2
            )
            else 0
        end as grounding_rate_pct,

        cm.avg_top_k_requested,

        -- Safety metrics (Phase 4)
        coalesce(se.risk_detections, 0) as risk_detections,
        coalesce(se.guardrail_triggers, 0) as guardrail_triggers,
        coalesce(se.escalations, 0) as escalations,
        case
            when cm.total_messages > 0
            then round(
                coalesce(se.guardrail_triggers, 0)::numeric / cm.total_messages * 100, 4
            )
            else 0
        end as guardrail_trigger_rate_pct
    from chat_metrics cm
    left join safety_events se
        on cm.organization_id = se.organization_id
        and cm.period_start = se.period_start
)

select * from final
