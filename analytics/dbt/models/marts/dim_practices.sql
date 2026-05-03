{{ config(materialized='table') }}

-- One row per practice (organization). Rollup of therapist / patient counts
-- and session activity so BI can filter without repeating the joins.

with orgs as (
    select * from {{ ref('stg_organizations') }}
),

user_counts as (
    select
        organization_id,
        count(*) filter (where role = 'therapist')    as therapist_count,
        count(*) filter (where role = 'patient')      as patient_count,
        count(*) filter (where role = 'admin')        as admin_count,
        count(*)                                      as total_user_count,
        max(created_at)                               as most_recent_user_created_at
    from {{ ref('stg_users') }}
    group by organization_id
),

session_counts as (
    select
        organization_id,
        count(*)                                       as session_count,
        count(*) filter (where is_ready)               as ready_session_count,
        count(*) filter (where is_failed)              as failed_session_count,
        min(session_date)                              as first_session_at,
        max(session_date)                              as last_session_at
    from {{ ref('stg_sessions') }}
    where organization_id is not null
    group by organization_id
)

select
    o.organization_id,
    o.organization_name,
    o.video_chat_enabled,
    o.subscription_status,
    o.is_entitled,
    o.trial_ends_at,
    o.current_period_end,
    o.disabled_at,
    o.stripe_customer_id,
    o.stripe_subscription_id,
    coalesce(u.therapist_count, 0)              as therapist_count,
    coalesce(u.patient_count, 0)                as patient_count,
    coalesce(u.admin_count, 0)                  as admin_count,
    coalesce(u.total_user_count, 0)             as total_user_count,
    u.most_recent_user_created_at,
    coalesce(s.session_count, 0)                as session_count,
    coalesce(s.ready_session_count, 0)          as ready_session_count,
    coalesce(s.failed_session_count, 0)         as failed_session_count,
    s.first_session_at,
    s.last_session_at,
    o.created_at                                as practice_created_at,
    o.updated_at                                as practice_updated_at
from orgs o
left join user_counts u    on u.organization_id = o.organization_id
left join session_counts s on s.organization_id = o.organization_id
