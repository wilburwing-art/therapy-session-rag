-- Patient engagement trends over time (weekly rollup)
-- Grain: organization_id + period_start
-- Useful for exec dashboards: "Are patients using the platform more or less?"
{{ config(materialized='table') }}

with weekly_engagement as (
    select
        p.organization_id,
        date_trunc('week', fe.activity_date) as period_start,
        count(distinct fe.patient_id) as active_patients,
        sum(fe.sessions_count) as total_sessions,
        sum(fe.messages_count) as total_messages,
        avg(fe.engagement_score) as avg_engagement_score,
        sum(fe.consents_granted) as consents_granted,
        sum(fe.consents_revoked) as consents_revoked
    from {{ ref('fact_engagement') }} fe
    join {{ ref('dim_patients') }} p on fe.patient_id = p.patient_id
    group by p.organization_id, date_trunc('week', fe.activity_date)
),

org_patient_counts as (
    select
        organization_id,
        patient_count as total_patients
    from {{ ref('dim_organizations') }}
),

final as (
    select
        {{ dbt_utils.generate_surrogate_key(['we.organization_id', 'we.period_start']) }}
            as trend_id,
        we.organization_id,
        we.period_start,
        (we.period_start + interval '7 days')::date as period_end,

        -- Engagement counts
        we.active_patients,
        opc.total_patients,
        case
            when opc.total_patients > 0
            then round(
                we.active_patients::numeric / opc.total_patients * 100, 2
            )
            else 0
        end as patient_activation_rate_pct,

        -- Activity
        we.total_sessions,
        we.total_messages,
        we.avg_engagement_score,

        -- Per-patient averages
        case
            when we.active_patients > 0
            then round(we.total_sessions::numeric / we.active_patients, 2)
            else 0
        end as avg_sessions_per_patient,
        case
            when we.active_patients > 0
            then round(we.total_messages::numeric / we.active_patients, 2)
            else 0
        end as avg_messages_per_patient,

        -- Consent health
        we.consents_granted,
        we.consents_revoked,
        we.consents_granted - we.consents_revoked as net_consent_change
    from weekly_engagement we
    left join org_patient_counts opc
        on we.organization_id = opc.organization_id
)

select * from final
