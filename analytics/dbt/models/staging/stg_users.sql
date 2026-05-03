{{ config(materialized='view') }}

-- One row per user. Roles: therapist / patient / admin.
select
    id                           as user_id,
    organization_id,
    lower(email)                 as email,
    role,
    full_name,
    email_verified_at,
    email_verified_at is not null as is_email_verified,
    totp_enabled_at is not null   as is_totp_enabled,
    failed_login_count,
    locked_until,
    (locked_until is not null and locked_until > now()) as is_locked,
    created_at,
    updated_at
from {{ source('app', 'users') }}
