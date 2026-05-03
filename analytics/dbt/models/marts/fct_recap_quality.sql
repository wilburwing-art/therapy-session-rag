{{ config(materialized='table') }}

-- LLM recap QA features, one row per recap.
-- Surfaces length + count metrics the summarization team uses to spot
-- regressions after prompt changes.

with recaps as (
    select
        r.id                                 as recap_id,
        r.session_id,
        r.brief,
        r.key_topics,
        r.emotional_tone,
        r.homework_assigned,
        r.follow_ups,
        r.risk_flags,
        r.model_name,
        r.generated_at,
        r.created_at,
        r.updated_at
    from {{ source('app', 'session_recaps') }} r
),

joined as (
    select
        r.*,
        s.organization_id,
        s.therapist_id,
        s.patient_id,
        s.session_date
    from recaps r
    left join {{ ref('stg_sessions') }} s on s.session_id = r.session_id
)

select
    recap_id,
    session_id,
    organization_id,
    therapist_id,
    patient_id,
    session_date,
    model_name,
    generated_at,
    length(brief)                              as brief_char_length,
    array_length(
        string_to_array(trim(brief), ' '),
        1
    )                                          as brief_word_count,
    jsonb_array_length(key_topics)             as key_topic_count,
    jsonb_array_length(homework_assigned)      as homework_count,
    jsonb_array_length(follow_ups)             as follow_up_count,
    jsonb_array_length(risk_flags)             as risk_flag_count,
    jsonb_array_length(risk_flags) > 0         as has_risk_flag,
    emotional_tone
from joined
