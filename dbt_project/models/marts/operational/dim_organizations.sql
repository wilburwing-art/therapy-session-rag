-- Organization dimension with usage summary
-- Grain: organization_id
with organizations as (
    select * from {{ ref('stg_organizations') }}
),

user_counts as (
    select
        organization_id,
        count(*) as total_users,
        count(*) filter (where user_role = 'patient') as patient_count,
        count(*) filter (where user_role = 'therapist') as therapist_count,
        count(*) filter (where user_role = 'admin') as admin_count
    from {{ ref('stg_users') }}
    group by organization_id
),

session_counts as (
    select
        fs.patient_id,
        p.organization_id,
        count(*) as total_sessions,
        count(*) filter (where fs.is_ready) as completed_sessions
    from {{ ref('fact_sessions') }} fs
    join {{ ref('stg_users') }} p on fs.patient_id = p.user_id
    group by fs.patient_id, p.organization_id
),

org_sessions as (
    select
        organization_id,
        sum(total_sessions) as total_sessions,
        sum(completed_sessions) as completed_sessions
    from session_counts
    group by organization_id
),

event_counts as (
    select
        organization_id,
        count(*) as total_events,
        min(event_timestamp) as first_event_at,
        max(event_timestamp) as last_event_at
    from {{ ref('stg_events') }}
    group by organization_id
),

final as (
    select
        o.organization_id,
        o.organization_name,
        o.organization_created_at,

        -- User breakdown
        coalesce(uc.total_users, 0) as total_users,
        coalesce(uc.patient_count, 0) as patient_count,
        coalesce(uc.therapist_count, 0) as therapist_count,
        coalesce(uc.admin_count, 0) as admin_count,

        -- Session usage
        coalesce(os.total_sessions, 0) as total_sessions,
        coalesce(os.completed_sessions, 0) as completed_sessions,

        -- Event activity
        coalesce(ec.total_events, 0) as total_events,
        ec.first_event_at,
        ec.last_event_at,

        -- Org tenure
        extract(day from (current_timestamp - o.organization_created_at))
            as org_age_days
    from organizations o
    left join user_counts uc on o.organization_id = uc.organization_id
    left join org_sessions os on o.organization_id = os.organization_id
    left join event_counts ec on o.organization_id = ec.organization_id
)

select * from final
