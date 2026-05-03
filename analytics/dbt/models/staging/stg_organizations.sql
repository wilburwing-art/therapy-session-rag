{{ config(materialized='view') }}

-- One row per practice. Flattens Stripe subscription fields and derives
-- entitlement the same way the FastAPI Organization.is_entitled() does.
select
    id                           as organization_id,
    name                         as organization_name,
    video_chat_enabled,
    stripe_customer_id,
    stripe_subscription_id,
    subscription_status,
    trial_ends_at,
    current_period_end,
    disabled_at,
    (
        disabled_at is null
        and subscription_status in ('trialing', 'active')
    )                            as is_entitled,
    created_at,
    updated_at
from {{ source('app', 'organizations') }}
