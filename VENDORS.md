# Vendor Inventory

Every third-party service that touches TherapyRAG data or infrastructure. Keep this in sync with [LAUNCH_READINESS.md](./LAUNCH_READINESS.md) — the launch doc tracks contract status (BAAs signed, billing live); this file is the living inventory for SOC 2 vendor-management evidence.

## Subprocessors and infrastructure

| Vendor | Purpose | PHI exposure | BAA status | Data retention | Primary contact |
| --- | --- | --- | --- | --- | --- |
| Anthropic | Claude model API for chatbot answers and session summarization | **Direct PHI** — session transcripts, therapist prompts, patient chat messages are sent at inference time | BAA required. Status tracked in [LAUNCH_READINESS.md](./LAUNCH_READINESS.md#baas) | Per Anthropic Enterprise data policy, prompts and completions are not retained for model training; see https://www.anthropic.com/legal/privacy | `privacy@anthropic.com` |
| OpenAI | `text-embedding-3-small` for RAG indexing | **Direct PHI** — transcript chunks are sent for embedding | BAA required for HIPAA workloads. Status in LAUNCH_READINESS | Per OpenAI Enterprise data policy, inputs are not used for training and are retained for abuse monitoring only; see https://openai.com/policies/enterprise-privacy/ | `legal@openai.com` |
| Deepgram | Speech-to-text transcription | **Direct PHI** — session audio | BAA required. Status in LAUNCH_READINESS | Per Deepgram enterprise agreement, audio is not retained after transcription completes; see https://deepgram.com/privacy | `privacy@deepgram.com` |
| Resend | Transactional email (magic links, password resets, verification) | **Indirect PHI** — patient email addresses + metadata | BAA not required (email contents are not PHI by themselves); reviewed separately | Message logs retained 90 days per Resend default; see https://resend.com/legal/privacy-policy | `privacy@resend.com` |
| Stripe | Billing and payments | **No PHI** — therapist billing email + card only. Patient data is never sent to Stripe. | No BAA needed (not PHI). Standard DPA in place | Payment records retained per Stripe's policy for regulatory compliance; see https://stripe.com/legal/privacy-center | `privacy@stripe.com` |
| Sentry | Error tracking and performance monitoring | **Potential PHI** — redacted via `structlog` exclude-keys + Sentry's data scrubbing; stack traces and request metadata only | BAA required where events may include PHI. Status in LAUNCH_READINESS | Retention configured per-project; default 30–90 days; see https://sentry.io/legal/ | `privacy@sentry.io` |
| Fly.io / Railway (app host) | Application runtime hosting | **Indirect PHI** — in-memory during request handling; not persisted to host disk | BAA required for HIPAA workloads. Status in LAUNCH_READINESS | No application data persisted on host; logs forwarded to Sentry and operator log store | `support@fly.io` / `team@railway.app` |
| AWS S3 / Tigris (object store for recordings) | Recording storage (S3-compatible) | **Direct PHI** — session audio | BAA required (AWS) or vendor-equivalent (Tigris). Status in LAUNCH_READINESS | Retention mirrors application retention policy (operator-configurable); recordings are deleted on patient-data-delete | `aws-compliance@amazon.com` / `support@tigrisdata.com` |
| MinIO (local dev only) | S3-compatible store for local development | **No production PHI** — seeded demo data only | N/A — dev only, never production | Local Docker volume; wiped with `docker compose down -v` | N/A |
| PostgreSQL managed host (Fly.io / Railway / Supabase) | Primary application database with pgvector | **Direct PHI** — transcripts, consents, assessments, conversations | BAA required. Status in LAUNCH_READINESS | Database retention follows the 7-year analytics horizon (`therapyrag-admin retention-purge`) and HIPAA-aligned operational backups | Host-specific; tracked in LAUNCH_READINESS |
| Redis managed host (Fly.io / Railway / Upstash) | Rate limiting and RQ job queue | **Minimal PHI** — job payloads reference session IDs only, not transcript contents | BAA required where jobs carry PHI references. Status in LAUNCH_READINESS | Rate-limit keys expire within minutes; RQ jobs cleared on completion | Host-specific; tracked in LAUNCH_READINESS |

## Review cadence

- Vendor inventory is reviewed quarterly as part of the SOC 2 vendor-management control.
- New vendor onboarding requires: security review, BAA in place if PHI exposure is possible, and an entry in this file before production rollout.
- BAA expirations and renewals are tracked in LAUNCH_READINESS.

## Decommissioning

When a vendor is removed:

1. Rotate every credential issued to that vendor.
2. Confirm vendor-side data deletion per their DPA (request written confirmation for PHI-handling vendors).
3. Remove the entry from this file in the same commit that removes the integration code.
