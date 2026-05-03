{#
    Extract a field from the analytics_events.properties JSONB column
    with an optional typed cast.

    Usage:
        {{ get_properties_field('duration_seconds', 'int') }}
        {{ get_properties_field('source', 'text') }}
        {{ get_properties_field('score') }}          -- defaults to text

    Returns NULL when the key is missing; cast is applied only when the
    value is present so typing errors never crash the whole row.
#}
{% macro get_properties_field(field_name, cast_type='text') %}
    nullif(properties ->> '{{ field_name }}', '')::{{ cast_type }}
{% endmacro %}
