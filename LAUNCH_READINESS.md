# Launch readiness tracker

Four things have to be true before a real patient touches this system. Everything here is a phone-call or email-and-wait task — not code. Track status in the right-hand column.

## 1. BAA (Business Associate Agreement) with every PHI vendor

A BAA is a legal contract that makes the vendor a HIPAA business associate. Without signed BAAs, every session transcript going through these services is an uncured HIPAA violation.

| Vendor | Why you need it | How to request | Status |
|---|---|---|---|
| **Anthropic** (Claude) | Recap + themes + chatbot | Requires a paid "Claude for Work" / enterprise agreement. Contact sales: https://www.anthropic.com/enterprise. Ask for BAA addendum. | ☐ not started |
| **OpenAI** (embeddings) | Vector search over transcripts | Self-serve form: https://openai.com/enterprise-privacy/ → "Request BAA". Requires API org in "Team" or "Enterprise" tier. | ☐ not started |
| **Deepgram** (transcription) | Audio → text | BAA is standard on paid plans. Email support@deepgram.com with subject "BAA request" and your account email. | ☐ not started |
| **Stripe** | Subscription billing | Stripe does NOT touch PHI by design — their BAA is unnecessary as long as you don't store clinical data in Stripe customer metadata. Confirm in writing. Verify your `create_customer` call only sends org name + therapist email. | ☐ verify no PHI sent |
| **Resend** | Transactional email | Magic-link + recap emails could contain patient names + therapist names. Email support@resend.com. They've signed BAAs on request. | ☐ not started |
| **Railway / your host** | PHI at rest + in compute | Railway does NOT offer a BAA as of early 2026. **Blocker.** Migrate to: AWS (ECS/RDS with AWS BAA — free on enterprise agreement), GCP (similar), or Fly.io with their SOC-2/BAA plan. | ☐ MIGRATE before launch |
| **MinIO** (if self-hosted) | Recording storage | If you host MinIO yourself on a BAA-covered server, you're the BA for it — fine. If you use a managed S3-compatible service, get their BAA. AWS S3 is the easiest path. | ☐ confirm hosting |
| **Sentry** | Error tracking | Sentry offers BAAs on their Business tier. The `before_send` scrubber already strips bodies/headers, but names in exception messages can still leak. Email enterprise@sentry.io. | ☐ not started |

**Draft outreach email (copy/paste for Anthropic, OpenAI, Deepgram, Resend, Sentry):**

> Subject: BAA request — [Your Practice Name]
>
> Hi,
>
> I'm launching a HIPAA-covered telehealth adjunct product and I'm a current [vendor] customer (account: [email/org ID]). I need a signed Business Associate Agreement in place before we process production PHI.
>
> Could you send me your BAA template, any required addenda, and the signing path (DocuSign / PDF)? I'm on [tier name] today and happy to upgrade if enterprise tier is required.
>
> Thanks,
> [name]

**Expected timeline:** 2-6 weeks per vendor. Start all of them in parallel this week.

## 2. Clinical oversight: a named Clinical Director

Legal reality: a non-clinician running a mental-health AI product that talks to patients is an unenforceable defense. You need a Licensed Mental Health Professional (LMHP — LCSW, LMFT, LPC, LP, or psychiatrist) with an active license in at least the states where patients live.

### Role requirements (minimum)

- Active clinical license in 1+ state, unrestricted, no pending board complaints
- Reviews and signs off on the safety guardrail policy and crisis routing protocol
- Owns the risk-flag triage workflow: when the recap surfaces a risk flag, who gets notified and within what SLA?
- Is the incident-response point person if the chatbot says something clinically wrong
- Reviews at least a sample of chatbot conversations monthly (audit for scope creep)

### How to find one

- **LinkedIn + Indeed**: "fractional clinical director" or "clinical advisor". Budget: $3-8k/mo for ~5-8 hrs/week fractional, or $120-180k for a full-time LCSW/LPC.
- **Referrals**: post in r/therapists, r/privateclinicalpractice, /r/psychotherapy. Former group-practice clinical directors are the right profile.
- **Specialist recruiters**: Therapeutic Talent Group, Rula Health's clinical recruiting.
- **Equity option**: 1-3% over a 4-year vest for a fractional founding Clinical Director.

### Short job spec to post

> **Title:** Founding Clinical Director (fractional, $X/mo + equity) — AI co-pilot for therapists
>
> **About:** [Your practice] is building an AI session-recap and between-session chatbot for licensed therapists in private practice. We're looking for a clinically-licensed founding advisor to own our clinical safety posture.
>
> **You:** LCSW / LPC / LMFT / LP / PhD / MD with active license, 5+ years of clinical practice, comfortable reading product specs, have opinions about digital mental health.
>
> **You'll own:** crisis protocol, safety guardrail review, risk flag triage SLAs, sampled conversation audits, response plan for clinical QA incidents.
>
> **Commitment:** ~5-8 hrs/week. Remote. Meet founder weekly.
>
> **Compensation:** $3-6k/mo consulting + 1-2% equity vesting over 4 years.

**Expected timeline:** 4-8 weeks to shortlist + sign.

**Status:** ☐ not started

## 3. Insurance

Two policies, non-optional:

### E&O (Professional Liability / Errors & Omissions)

Covers you when the product gives advice (or is *seen to give advice*) that hurts a patient. Standard for anyone selling software into healthcare.

- **Coverage target:** $1M-$2M per occurrence, $2M-$5M aggregate
- **Typical premium:** $4-12k/yr for a solo founder pre-revenue; scales with revenue
- **Brokers that specialize in digital health:**
  - Vouch (vouch.us) — startup-friendly, quick quote
  - Newfront (newfront.com) — health-tech specialty
  - Founder Shield (foundershield.com)

### Cyber / Data Breach

Covers the cost of breach notification, forensics, and patient credit monitoring if PHI leaks. HIPAA fines can hit $50k-$1.5M per category.

- **Coverage target:** $1M-$3M
- **Typical premium:** $2-8k/yr
- Same brokers cover both, often bundled

**Draft outreach email to a broker:**

> Subject: E&O + cyber quote — pre-revenue digital health startup
>
> Hi,
>
> I'm launching a HIPAA-covered SaaS product for licensed therapists (AI session summaries + patient-facing chatbot). Pre-revenue, founder + fractional clinical director.
>
> I'd like quotes for:
> - Professional liability (E&O), $2M/$5M
> - Cyber / privacy liability, $2M
>
> Tech stack: Python/FastAPI backend, Postgres, Next.js web. PHI encrypted at rest and in transit. BAA in progress with upstream vendors. SOC 2 Type I audit starting Q[X].
>
> Happy to share our architecture doc + privacy pitch.
>
> Thanks,
> [name]

**Expected timeline:** 1-3 weeks from RFP to bound policy.

**Status:** ☐ not started

## 4. Production environment gates

Not legal but on the same critical path. Before the *first* real patient:

- ☐ Postgres production instance provisioned on a BAA-covered host (NOT Railway)
- ☐ `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET` (32+ random bytes), `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`, `RESEND_API_KEY`, `SENTRY_DSN`, `WEB_APP_URL` all set
- ☐ `JWT_COOKIE_SECURE=true`, `BILLING_ENFORCED=true`, `CORS_ORIGINS` set to the actual web origin (not `*`)
- ☐ `uv run alembic upgrade head` run against production
- ☐ Stripe webhook endpoint pointed at `https://<api-host>/api/v1/billing/webhook`
- ☐ Resend sending domain verified (SPF + DKIM + DMARC records live)
- ☐ Sentry env tagged "production"; alert rules wired to Slack or pager
- ☐ Crisis protocol document written and signed by Clinical Director (what happens when a risk flag fires at 2am Saturday?)
- ☐ Privacy policy + terms of service written by a health-tech attorney and linked from the marketing page
- ☐ Dry-run: full end-to-end flow with internal staff as fake patients, in production, before any real one

## Suggested order

**Week 1:** Start all 7 BAA requests in parallel. Post Clinical Director job. Contact Vouch for insurance quote.

**Week 2-3:** BAAs landing, shortlist Clinical Directors.

**Week 4-6:** Sign Clinical Director, bind insurance, migrate host off Railway to a BAA-covered alternative. Run the production gates.

**Week 7+:** Private beta with 3-5 paid therapists who signed up for the trial. Iterate.

Nothing in this file is optional — launch without any one item is the kind of mistake that ends the company.
