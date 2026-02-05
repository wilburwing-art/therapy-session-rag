-- Every session must reference a consent that was granted before or at the session creation time
-- Returns rows that violate this constraint (should return 0 rows to pass)
with session_consent as (
    select
        s.session_id,
        s.consent_id,
        s.session_created_at,
        c.granted_at
    from {{ ref('stg_sessions') }} s
    join {{ ref('stg_consents') }} c
        on s.consent_id = c.consent_id
)

select *
from session_consent
where granted_at > session_created_at
