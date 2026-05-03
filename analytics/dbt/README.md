# TherapyRAG Analytics (dbt)

Transforms the TherapyRAG operational Postgres database into analytics-ready
staging views and curated marts for product, clinical, and finance reporting.

## Layout

```
analytics/dbt/
├── dbt_project.yml          # project config, profile = therapyrag
├── profiles.yml.example     # copy to ~/.dbt/profiles.yml or point DBT_PROFILES_DIR here
├── models/
│   ├── staging/             # 1:1 views over source tables, typed + renamed
│   └── marts/               # curated tables (fct_*, dim_*) for BI
├── macros/                  # reusable jinja helpers
└── seeds/                   # static reference CSVs checked into git
```

## Source tables

Staging reads from the application schema (`public`). The `_sources.yml` file
declares four relevant tables:

| Source | Staging model | Purpose |
|--------|---------------|---------|
| `organizations` | `stg_organizations` | practice tenants + Stripe subscription status |
| `users` | `stg_users` | therapists, patients, admins |
| `sessions` | `stg_sessions` | recording + transcription lifecycle |
| `analytics_events` | `stg_analytics_events` | Snowplow-style event stream |

Two marts (`fct_recap_quality`, `fct_cohort_retention`) also read directly from
`session_recaps` and `conversations` via `source()` — declared in `_sources.yml`.

## Marts

| Model | Grain | Purpose |
|-------|-------|---------|
| `fct_sessions_daily` | (organization_id, session_date) | daily session volume + funnel, incremental |
| `fct_mrr_by_week` | (week_start, subscription_tier) | MRR trend from billing usage |
| `fct_cohort_retention` | (cohort_month, period_number) | monthly signup cohort → chat-active retention |
| `fct_recap_quality` | recap_id | LLM recap QA features (length, risk flags, etc.) |
| `dim_practices` | organization_id | one row per practice, Stripe + entitlement |
| `dim_patients` | patient_id | one row per patient, activity summary |

## Running

```bash
# install the analytics extra
uv sync --extra analytics

# parse only (no DB required)
uv run dbt parse --project-dir analytics/dbt --profiles-dir analytics/dbt

# full build against a running Postgres
export POSTGRES_HOST=localhost POSTGRES_USER=therapy_user \
       POSTGRES_PASSWORD=therapy_pass POSTGRES_DB=therapy_rag
uv run dbt build --project-dir analytics/dbt --profiles-dir analytics/dbt
```

The `fct_sessions_daily` model is incremental on `session_date`; first run
materializes a full table, subsequent runs append rows for new dates only.
Use `--full-refresh` to rebuild from scratch.

## Conventions

- **Staging = views** — zero duplicated storage, cheap to rebuild.
- **Marts = tables** — materialized for BI read performance.
- **Primary key tests** — every mart has `not_null` + `unique` on its grain.
- **Source freshness** — not configured yet; add via `freshness:` block in
  `_sources.yml` once alerting is wired up.
