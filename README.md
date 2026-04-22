# TherapyRAG

**AI co-pilot for private-practice therapists.** Upload a session recording → get a structured recap, cross-session themes, and a patient-facing chatbot that answers questions grounded in the patient's own sessions.

[![CI](https://github.com/wilburwing-art/therapy-session-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/wilburwing-art/therapy-session-rag/actions/workflows/ci.yml)

## What it does

- **Session recap** — 2-3 sentence brief, key topics, emotional tone, homework assigned, follow-ups, and clinical risk flags (SI, abuse disclosure, mandatory-reporting triggers) for therapist review after every session.
- **Cross-session themes** — recurring topics, emotional patterns, coping strategies mentioned, progress indicators, and ongoing concerns, synthesized across a patient's recap history.
- **Patient chatbot** — patient clicks a one-time magic link and can ask questions like *"what did we discuss about sleep last week?"* with citations back to the source session and timestamp.
- **Outcome tracking** — PHQ-9 and GAD-7 with standard severity bands, history charted on the patient page.
- **Consent + audit** — append-only consent records with IP/user-agent/timestamp, full revocation audit trail.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Next.js 15 (web/)                           │
│  (marketing)   (public-auth)         (therapist)        (patient)    │
│   landing       login/signup           dashboard          chat       │
│                  forgot/reset          patient detail                │
│                  verify-email          session upload                │
│                                        billing / Stripe              │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ cookies (JWT)
┌──────────────────────────▼───────────────────────────────────────────┐
│                       FastAPI (src/)                                 │
│  /auth  /billing  /sessions  /patients  /consent  /chat              │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Services: auth, billing, email, summarization, themes, chat,  │ │
│  │  assessment, consent, transcription, embedding, safety         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Workers: transcription → embedding → summarization (RQ)        │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────┬────────────────────┬─────────────────┬─────────────────┬──────┘
       │                    │                 │                 │
   ┌───▼───┐          ┌─────▼─────┐      ┌────▼────┐       ┌────▼────┐
   │ Postgres        │ Redis      │      │ MinIO   │       │ Stripe  │
   │ + pgvector      │ (RQ + rate │      │ (S3)    │       │ + Resend│
   │ HIPAA tenant    │  limiting) │      │ recording│      │ + Sentry│
   │ isolation       │            │      │ storage │       │         │
   └─────────────────┴────────────┘      └─────────┘       └─────────┘
```

**External AI vendors** (BAA required for production): Deepgram (transcription), OpenAI text-embedding-3-small (embeddings), Anthropic Claude Sonnet 4 (chat + recaps + themes).

**Tenant isolation**: every query is scoped to the authenticated organization via a `TenantContext` at the repository layer, not just the API layer. Patient A can never see Patient B's data.

## Quick start

```bash
# Backend
uv sync
cp .env.example .env     # fill in API keys + JWT_SECRET
docker compose up -d postgres redis minio minio-setup
uv run alembic upgrade head
uv run uvicorn src.main:app --reload

# RQ workers (separate terminals)
uv run python -m rq.cli worker transcription --url redis://localhost:6379
uv run python -m rq.cli worker embedding --url redis://localhost:6379
uv run python -m rq.cli worker summarization --url redis://localhost:6379

# Web app
cd web
cp .env.example .env.local  # set THERAPYRAG_API_URL
npm install
npm run dev  # http://localhost:3000
```

## Environment variables

| Group | Keys |
|-------|------|
| Core | `DATABASE_URL` `REDIS_URL` `APP_ENV` |
| AI vendors | `DEEPGRAM_API_KEY` `OPENAI_API_KEY` `ANTHROPIC_API_KEY` |
| Storage | `MINIO_ENDPOINT` `MINIO_ACCESS_KEY` `MINIO_SECRET_KEY` `MINIO_BUCKET` |
| Auth | `JWT_SECRET` `JWT_COOKIE_SECURE` `JWT_ACCESS_TOKEN_TTL_SECONDS` |
| Billing | `STRIPE_SECRET_KEY` `STRIPE_WEBHOOK_SECRET` `STRIPE_PRICE_ID` `BILLING_ENFORCED` |
| Email | `RESEND_API_KEY` `EMAIL_FROM_ADDRESS` `EMAIL_FROM_NAME` `WEB_APP_URL` |
| Observability | `SENTRY_DSN` `SENTRY_ENVIRONMENT` |
| Safety | `SAFETY_ENABLED` `CHAT_RATE_LIMIT_PER_HOUR` |

## Development

```bash
# Backend
uv run ruff check src/ tests/
uv run mypy src/                    # strict mode
uv run pytest tests/unit            # 667+ unit tests
uv run pytest tests/integration     # needs Postgres + Redis

# Web
cd web
npm run typecheck
npm run build
```

### Project layout

```
src/
├── api/v1/endpoints/     # FastAPI routes (auth, billing, sessions, patients, chat, consent…)
├── services/             # Business logic
├── repositories/         # Data access (SQLAlchemy async)
├── models/
│   ├── db/               # SQLAlchemy ORM
│   └── domain/           # Pydantic DTOs (never leak ORM to the API)
├── core/                 # Config, database, auth, observability, tenant isolation
├── workers/              # RQ background jobs (transcription, embedding, summarization)
└── evaluation/           # RAG quality metrics

web/
├── app/
│   ├── (marketing)/      # Public landing page
│   ├── (public-auth)/    # Login, signup, password reset, verify email
│   ├── (therapist)/      # Protected — auth-gated dashboard, billing
│   └── (patient)/        # Magic-link chat
├── components/           # AppShell, AudioRecorder, ChatSurface, SubscriptionBanner
└── lib/                  # api client, types, auth helpers

tests/
├── unit/
└── integration/          # Full-stack tests against real Postgres
```

## HIPAA / security notes

- Consent is append-only — never `UPDATE` or `DELETE` consent rows
- API keys are HMAC-hashed; JWTs are audience-scoped (therapist vs. patient)
- Sentry's `before_send` hook strips Authorization/Cookie/X-API-Key headers and request bodies
- Claude guardrails: crisis detection with a canned 988 response, output filtering, scope limits ("this AI cannot diagnose, prescribe, or provide clinical advice")
- Tenant isolation enforced at the repository layer via `TenantContext`
- Signed BAAs required before production launch: Anthropic, OpenAI, Deepgram, Stripe, Resend, your host

## Production checklist

Before real patients touch this:

1. `uv run alembic upgrade head` against production Postgres
2. `JWT_SECRET` set to a 256-bit random string (not the dev default)
3. `JWT_COOKIE_SECURE=true` and `BILLING_ENFORCED=true`
4. Stripe: production keys, webhook endpoint set to `https://yourhost/api/v1/billing/webhook`, price + product configured
5. Resend: production API key, verified sending domain, DMARC/SPF/DKIM configured
6. Sentry: DSN configured with production environment tag
7. BAAs signed with every upstream AI + storage + infra vendor
8. Clinical Director appointed and credentialed in the relevant state(s)
9. Liability insurance: E&O, cyber
10. Crisis protocol documented: what happens when a risk flag fires after hours

## License

MIT
