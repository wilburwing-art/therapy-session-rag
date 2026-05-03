# Deploy runbook

Operator-only. Assumes Fly.io as the primary host. Does not cover code
review, testing, or clinical sign-off — see `AGENTS.md` and
`LAUNCH_READINESS.md` for those gates.

**HIPAA prerequisite:** Do not route production PHI through any host
until the vendor BAA checklist in `LAUNCH_READINESS.md` (section 1) is
fully signed. Fly.io offers BAAs on their Enterprise plan; confirm the
signed agreement covers the app region and the Postgres/Redis/storage
add-ons before first real patient.

---

## 0. One-time local tooling

```bash
brew install flyctl              # or: curl -L https://fly.io/install.sh | sh
fly auth login
fly auth whoami                  # sanity check
```

You also need Docker Desktop running for local image builds and
`uv` 0.9.x for ad-hoc migration runs.

---

## 1. First deploy

### 1a. Create the apps

```bash
# Backend API + worker (this repo's fly.toml)
fly apps create therapyrag-api --org <your-org>

# Web frontend — separate app, deploys from ./web with its own Dockerfile.
fly apps create therapyrag-web --org <your-org>
```

If you picked different names, update `app = "..."` at the top of
`fly.toml` and commit. The web app needs its own minimal `fly.toml`
(not in this repo — generate it with `cd web && fly launch --no-deploy`
and select "Use existing Dockerfile"; pin `app = "therapyrag-web"`).

### 1b. Provision managed infrastructure

```bash
# Postgres (Fly Managed Postgres — a PGaaS fork, not the deprecated MPG).
# pgvector is pre-installed; enable it after attach with:
#   fly pg connect -a <pg-app>  then \c <db>; CREATE EXTENSION IF NOT EXISTS vector;
fly postgres create --name therapyrag-pg --region iad --vm-size shared-cpu-1x --volume-size 10
fly postgres attach --app therapyrag-api therapyrag-pg
# `attach` writes DATABASE_URL into the app's secrets automatically.

# Redis — Fly recommends Upstash via their marketplace for HIPAA workloads.
# Upstash offers a BAA on the Enterprise tier; the free tier does NOT.
fly redis create --name therapyrag-redis --org <your-org> --region iad --plan enterprise --enable-eviction=false
# Copy the URL it prints and set it as REDIS_URL (see 1c).

# Object storage — Tigris (Fly's S3-compatible default) for recordings.
# Request BAA via Tigris support before storing PHI.
fly storage create --name therapyrag-recordings
# Outputs AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_ENDPOINT_URL_S3 / BUCKET_NAME.
```

Alternative for object storage: AWS S3 directly under an existing AWS
BAA. The app only speaks S3 via the `minio` Python client pointed at
the alternative endpoint — set `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`,
`MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE=true`.

### 1c. Set secrets

`fly postgres attach` already set `DATABASE_URL`. Set the rest
explicitly. Using a heredoc so nothing ends up in shell history:

```bash
fly secrets set --app therapyrag-api \
  REDIS_URL="redis://default:<password>@<host>:<port>" \
  JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  JWT_COOKIE_SECURE="true" \
  BILLING_ENFORCED="true" \
  CORS_ORIGINS="https://app.your-domain.com" \
  WEB_APP_URL="https://app.your-domain.com" \
  \
  MINIO_ENDPOINT="fly.storage.tigris.dev" \
  MINIO_ACCESS_KEY="<from fly storage create>" \
  MINIO_SECRET_KEY="<from fly storage create>" \
  MINIO_BUCKET="therapyrag-recordings" \
  MINIO_SECURE="true" \
  \
  DEEPGRAM_API_KEY="<deepgram>" \
  OPENAI_API_KEY="<openai>" \
  ANTHROPIC_API_KEY="<anthropic>" \
  \
  STRIPE_SECRET_KEY="sk_live_..." \
  STRIPE_WEBHOOK_SECRET="whsec_..." \
  STRIPE_PRICE_ID="price_..." \
  STRIPE_SUCCESS_URL="https://app.your-domain.com/dashboard?checkout=success" \
  STRIPE_CANCEL_URL="https://app.your-domain.com/billing?checkout=canceled" \
  STRIPE_PORTAL_RETURN_URL="https://app.your-domain.com/billing" \
  \
  RESEND_API_KEY="re_..." \
  EMAIL_FROM_ADDRESS="noreply@your-domain.com" \
  EMAIL_FROM_NAME="TherapyRAG" \
  \
  SENTRY_DSN="https://<public>@<org>.ingest.sentry.io/<project>" \
  SENTRY_ENVIRONMENT="production" \
  SENTRY_TRACES_SAMPLE_RATE="0.05"
```

Optional, only if video chat is live:

```bash
fly secrets set --app therapyrag-api \
  TURN_ENABLED="true" \
  METERED_TURN_USERNAME="..." \
  METERED_TURN_CREDENTIAL="..."
```

For the web frontend:

```bash
fly secrets set --app therapyrag-web \
  THERAPYRAG_API_URL="https://therapyrag-api.fly.dev"
# Plus any NEXT_PUBLIC_* keys once they're added to web/.
```

Verify with `fly secrets list --app therapyrag-api`. Values are never
printed; only digests.

### 1d. First deploy

```bash
fly deploy --app therapyrag-api
```

This:
1. Builds the image using `/Dockerfile`.
2. Runs the `release_command` (`uv run alembic upgrade head`) on a
   throwaway release machine. If it exits non-zero, the deploy aborts
   and no traffic shifts.
3. Rolls out one `app` machine and one `worker` machine per
   `fly.toml` process groups.

Web:

```bash
cd web && fly deploy --app therapyrag-web
```

Post-deploy sanity:

```bash
fly status --app therapyrag-api
fly logs --app therapyrag-api
curl -sS https://therapyrag-api.fly.dev/health/ready | jq
```

---

## 2. Migrations

Migrations run automatically on every `fly deploy` via the release
command in `fly.toml`:

```toml
[deploy]
  release_command = "alembic upgrade head"
```

The production image ships `/app/.venv/bin` on PATH; `alembic`, `uvicorn`,
`python`, etc. are all available without `uv` (which is not in the final
runtime stage).

### Run migrations out-of-band

If you need to run migrations without a deploy (e.g. you want to apply
an already-merged migration against a hotfixed DB):

```bash
fly ssh console --app therapyrag-api --command "alembic upgrade head"
```

### Roll back a migration

`alembic downgrade` is available inside the container:

```bash
fly ssh console --app therapyrag-api
# inside the VM:
alembic current
alembic history --verbose
alembic downgrade -1    # one step back
exit
```

**Important:** Alembic downgrades frequently lose data (dropped columns,
dropped tables). Take a Postgres snapshot first:

```bash
fly postgres backup list --app therapyrag-pg
fly postgres backup create --app therapyrag-pg
```

If a migration would be destructive on production data, write a
forward-only fix migration instead of downgrading.

---

## 3. Rollback

Release rollback for code (fastest path):

```bash
fly releases --app therapyrag-api
# Find the last good version number, then:
fly deploy --app therapyrag-api --image registry.fly.io/therapyrag-api:<tag>
# Or redeploy the prior git SHA:
git checkout <sha> && fly deploy --app therapyrag-api
```

Rollback with migration involved:

1. Snapshot the DB: `fly postgres backup create --app therapyrag-pg`.
2. Downgrade the schema: `fly ssh console --app therapyrag-api --command "uv run alembic downgrade <revision>"`.
3. Redeploy the previous image.

If the migration was data-destructive and the backup is the only copy,
restore with `fly postgres backup restore --app therapyrag-pg <backup-id>`
and expect minutes of write downtime.

---

## 4. Secret rotation

Rotating a single secret triggers a zero-downtime rolling restart:

```bash
fly secrets set --app therapyrag-api JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

Multi-secret rotation (stage together to avoid mixed state):

```bash
fly secrets set --app therapyrag-api --stage \
  OPENAI_API_KEY="sk-..." \
  ANTHROPIC_API_KEY="sk-ant-..."
fly deploy --app therapyrag-api
# `--stage` defers the machine restart until the next deploy so both
# keys land in one release instead of two rolling restarts.
```

### Key-specific notes

- **`JWT_SECRET`**: rotating this invalidates every therapist session
  cookie. Users re-login. Acceptable during off-hours or after a
  suspected leak; not acceptable mid-session without a comms plan.
- **`STRIPE_WEBHOOK_SECRET`**: must match the active signing secret in
  Stripe dashboard (Developers → Webhooks → endpoint → Signing
  secret). Rotate both sides in the same window.
- **`DATABASE_URL`**: managed via `fly postgres attach` — do not rotate
  manually. To rotate the Postgres password, run `fly postgres
  users rotate` and re-attach.
- **`DEEPGRAM_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`**:
  provider dashboards let you issue a new key, set it as a Fly secret,
  deploy, then revoke the old one. Deploy-first avoids outage.
- **`RESEND_API_KEY`**: same two-step (issue → set → deploy → revoke
  old). Magic-link email will fail if revoked before deploy lands.

---

## 5. Observability checklist

- `fly logs --app therapyrag-api` — tail live logs (structlog JSON).
- Sentry project shows runtime errors; `SENTRY_ENVIRONMENT` must read
  `production` in the issue tags.
- `/health/ready` should be 200 with DB OK under normal load; watch
  for flips to 503 during deploys (expected during migrations).
- No Prometheus scrape endpoint is exposed yet. When one is added,
  declare it in `fly.toml` under `[metrics]` with the correct port.

---

## 6. Pre-launch gate

Do not point real patient traffic at this until every item in
`LAUNCH_READINESS.md` is checked: signed BAAs (Anthropic, OpenAI,
Deepgram, Resend, Sentry, Fly, object storage), named Clinical
Director, E&O + cyber insurance bound, production environment gates
verified. The Dockerfiles and `fly.toml` here are a hosting primitive,
not a compliance posture.
