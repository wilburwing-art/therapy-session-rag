with source as (
    select * from {{ source('therapy_rag', 'users') }}
),

renamed as (
    select
        id as user_id,
        organization_id,
        email,
        role as user_role,
        created_at as user_created_at,
        updated_at as user_updated_at
    from source
)

select * from renamed
