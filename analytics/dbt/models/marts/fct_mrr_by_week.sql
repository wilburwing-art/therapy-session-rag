{{ config(materialized='table') }}

-- Weekly MRR by subscription tier. Joins billing_usage to the subscription
-- tier reference seed via the organization's Stripe price_id tag, which is
-- stamped onto billing_usage rows by the billing service (as a plain text
-- column `tier_code` when that ships) or falls back to 'solo' if unknown.
--
-- Grain: (week_start, tier_code).

with usage as (
    select
        bu.id                               as billing_usage_id,
        bu.organization_id,
        bu.period_start,
        bu.period_end,
        bu.sessions_transcribed,
        bu.recaps_generated,
        bu.chat_messages,
        date_trunc('week', bu.period_start)::date as week_start,
        coalesce(o.subscription_status, 'none')    as subscription_status,
        -- For now, derive tier_code heuristically from usage volume until the
        -- billing service stamps tier directly on the row.
        case
            when bu.sessions_transcribed > 500 then 'enterprise'
            when bu.sessions_transcribed > 100 then 'group'
            when bu.sessions_transcribed > 0   then 'solo'
            else 'trial'
        end as tier_code
    from {{ source('app', 'billing_usage') }} bu
    left join {{ ref('stg_organizations') }} o
        on o.organization_id = bu.organization_id
    where bu.period_start is not null
),

tiers as (
    select * from {{ ref('subscription_tier_list') }}
)

select
    u.week_start::text || '|' || u.tier_code                 as grain_key,
    u.week_start,
    u.tier_code,
    t.tier_name,
    t.monthly_price_usd,
    count(distinct u.organization_id)                     as paying_org_count,
    count(distinct u.organization_id) * t.monthly_price_usd as mrr_usd,
    sum(u.sessions_transcribed)                           as sessions_transcribed_total,
    sum(u.recaps_generated)                               as recaps_generated_total,
    sum(u.chat_messages)                                  as chat_messages_total
from usage u
left join tiers t on t.tier_code = u.tier_code
group by u.week_start, u.tier_code, t.tier_name, t.monthly_price_usd
