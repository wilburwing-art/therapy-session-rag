-- Standard date dimension from seed
-- Grain: date_key (calendar date)
with dates as (
    select * from {{ ref('dim_time_seed') }}
),

final as (
    select
        date_key,
        year,
        quarter,
        month,
        month_name,
        week_of_year,
        day_of_month,
        day_of_week,
        day_name,
        is_weekend,
        is_month_start,
        is_month_end
    from dates
)

select * from final
