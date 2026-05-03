{{ config(materialized='table') }}

-- One row per patient. Activity summary across sessions + chat.

with patients as (
    select * from {{ ref('stg_users') }} where role = 'patient'
),

session_summary as (
    select
        patient_id,
        count(*)                                         as session_count,
        count(*) filter (where is_ready)                 as ready_session_count,
        min(session_date)                                as first_session_at,
        max(session_date)                                as last_session_at,
        count(distinct therapist_id)                     as distinct_therapist_count
    from {{ ref('stg_sessions') }}
    group by patient_id
),

chat_summary as (
    select
        patient_id,
        count(*)                                         as conversation_count,
        sum(message_count)                               as total_message_count,
        max(created_at)                                  as last_conversation_at
    from {{ source('app', 'conversations') }}
    group by patient_id
)

select
    p.user_id                            as patient_id,
    p.organization_id,
    p.email,
    p.full_name,
    p.is_email_verified,
    p.email_verified_at,
    p.is_totp_enabled,
    p.is_locked,
    coalesce(s.session_count, 0)         as session_count,
    coalesce(s.ready_session_count, 0)   as ready_session_count,
    s.first_session_at,
    s.last_session_at,
    coalesce(s.distinct_therapist_count, 0) as distinct_therapist_count,
    coalesce(c.conversation_count, 0)    as conversation_count,
    coalesce(c.total_message_count, 0)   as total_message_count,
    c.last_conversation_at,
    p.created_at                         as patient_created_at,
    p.updated_at                         as patient_updated_at
from patients p
left join session_summary s on s.patient_id = p.user_id
left join chat_summary c    on c.patient_id = p.user_id
