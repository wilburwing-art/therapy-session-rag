with source as (
    select * from {{ source('therapy_rag', 'organizations') }}
),

renamed as (
    select
        id as organization_id,
        name as organization_name,
        created_at as organization_created_at,
        updated_at as organization_updated_at
    from source
)

select * from renamed
