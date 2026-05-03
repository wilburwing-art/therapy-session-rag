{{ config(materialized='table') }}

-- Monthly signup cohort retention.
-- Cohort = calendar month of a patient's created_at.
-- Period N = whether that patient sent any chat message in the Nth month
-- since signup (period_number = 0 is the signup month itself).
--
-- Grain: (cohort_month, period_number).

with patients as (
    select
        user_id as patient_id,
        date_trunc('month', created_at)::date as cohort_month
    from {{ ref('stg_users') }}
    where role = 'patient'
),

chat_activity as (
    select
        patient_id,
        date_trunc('month', created_at)::date as activity_month
    from {{ source('app', 'conversations') }}
    group by patient_id, date_trunc('month', created_at)::date
),

cohort_activity as (
    select
        p.cohort_month,
        p.patient_id,
        ca.activity_month,
        ((extract(year from ca.activity_month) - extract(year from p.cohort_month)) * 12
         + (extract(month from ca.activity_month) - extract(month from p.cohort_month)))::int
            as period_number
    from patients p
    inner join chat_activity ca
        on ca.patient_id = p.patient_id
        and ca.activity_month >= p.cohort_month
),

cohort_sizes as (
    select
        cohort_month,
        count(distinct patient_id) as cohort_size
    from patients
    group by cohort_month
)

select
    ca.cohort_month::text || '|' || ca.period_number::text   as grain_key,
    ca.cohort_month,
    ca.period_number,
    cs.cohort_size,
    count(distinct ca.patient_id)                           as retained_patients,
    round(
        count(distinct ca.patient_id)::numeric / nullif(cs.cohort_size, 0),
        4
    ) as retention_rate
from cohort_activity ca
inner join cohort_sizes cs on cs.cohort_month = ca.cohort_month
group by ca.cohort_month, ca.period_number, cs.cohort_size
