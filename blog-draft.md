# Building a RAG System Where Getting It Wrong Actually Matters

Most RAG demos retrieve documents and generate answers. The interesting part is when "hallucinated a wrong fact" stops being an inconvenience and starts being a clinical liability.

I built TherapyRAG — a system that records therapy sessions (with consent), transcribes them, and lets patients ask questions about their own session history through a chatbot. The technical challenge wasn't the vector search. It was everything around the vector search that makes it safe to deploy in a clinical context.

## The problem

Patients forget most of what happens in therapy. Studies suggest retention of session content drops significantly within days. A patient has a breakthrough at minute 38 — they finally articulate a pattern in their relationships, the therapist names a coping strategy — and by the next appointment, the details are gone. They remember something important happened but not the specifics.

Therapist notes exist, but they're written for the clinician's workflow, not the patient's understanding. There's no mechanism for a patient to go back and ask "what was that breathing technique we talked about?" or "what exactly did my therapist say about my avoidance pattern?"

## The gap

The digital mental health space splits into two camps that both miss this:

**Standalone chatbot apps** like Wysa and Woebot deliver generic CBT exercises. They're useful, but they have no connection to *your* therapy. They don't know what you and your therapist discussed. They can't reference your specific patterns, your specific homework, your specific breakthroughs.

**Clinician tools** like Upheal and Grow Therapy use AI to generate progress notes and reduce admin burden. They work with session transcripts — but the output is for the provider, not the patient.

The gap is a patient-facing tool grounded in the patient's actual sessions. Nobody builds this because the problem is genuinely hard: you need consent management that satisfies HIPAA, speaker-aware transcription, retrieval that understands therapeutic context, and safety guardrails that prevent an AI from accidentally playing therapist.

## The pipeline

The data flow looks like this:

```
Recording → Transcription → Chunking → Embedding → Vector Store → Retrieval → LLM → Safety Check → Response
```

But the interesting decisions are in the details.

### Transcription with speaker diarization

Raw audio goes to Deepgram, which returns not just text but structured segments: who spoke, when they started, when they stopped, and a confidence score. This is critical. A therapy transcript without speaker labels is nearly useless for retrieval — "you should practice progressive muscle relaxation" means something completely different depending on whether the therapist said it (a recommendation) or the patient said it (they're recalling a previous technique).

### Chunking that respects speaker boundaries

This is where most RAG systems make a domain-specific mistake. Standard chunking strategies — fixed-size windows, recursive text splitting, sentence-based splits — don't account for the fact that speaker changes are semantic boundaries in conversational transcripts.

My chunking algorithm splits on three conditions:

1. **Speaker changes** — when the voice switches from therapist to patient (or vice versa), that's almost always a semantic boundary
2. **Size limits** — hard cap at ~750 tokens, target of ~500, floor of ~100 (too-small chunks become noise)
3. **Target size** — force a split when we hit the target, even within the same speaker

The minimum size constraint prevents degenerate cases. A patient saying "mm-hm" shouldn't become its own chunk. But a long therapist explanation should be chunked, even though the speaker doesn't change, so that retrieval can find the specific relevant section rather than pulling in five minutes of monologue.

Each chunk carries its speaker label, start/end timestamps, and segment indices. When the chatbot cites a source, it can say "your therapist mentioned at 12:35 in your March 8th session" rather than just "based on your sessions."

```python
# Each chunk preserves therapeutic context
@dataclass
class ChunkData:
    content: str
    chunk_index: int
    start_time: float | None
    end_time: float | None
    speaker: str | None
    segment_indices: list[int]
```

### pgvector instead of a dedicated vector database

I'm storing embeddings in Postgres with the pgvector extension instead of using Pinecone, Weaviate, or Qdrant. This is a deliberate tradeoff.

In a HIPAA-regulated context, every service that touches protected health information (PHI) needs a Business Associate Agreement. Every additional vendor is another BAA to negotiate, another attack surface to secure, another system to audit. Keeping vectors in the same Postgres instance as relational data means one database to back up, one to encrypt at rest, one to put access controls around.

The cost is real: no built-in hybrid search, no reranking, limited filtering compared to purpose-built vector stores. But at the scale of therapy sessions (a patient might accumulate hundreds of sessions over years, not millions of documents), pgvector with an IVFFlat index and cosine distance is more than sufficient. Operational simplicity is the compliance strategy.

```python
# Similarity search is filtered by patient_id at the query level
query = (
    select(SessionChunk, similarity_expr)
    .join(Session, SessionChunk.session_id == Session.id)
    .where(Session.patient_id == patient_id)       # security boundary
    .where(SessionChunk.embedding.isnot(None))
    .order_by(text("similarity DESC"))
    .limit(top_k)
)
```

### Retrieval and context assembly

The chat service embeds the patient's question with `text-embedding-3-small`, runs cosine similarity search against their chunks (filtered to only their sessions — never cross-patient), and assembles the top-k results into a context block for Claude. Each chunk is formatted with its speaker label and timestamp:

```
[Therapist] (at 120.5s) Let's talk about what happens when you notice
the anxiety building. You mentioned last week that you tend to...

---

[Patient] (at 185.2s) Yeah, I've been trying that thing where I name
five things I can see, but I keep forgetting to do it in the moment...
```

The system prompt instructs Claude to cite specific sessions, help the patient connect insights across sessions, and — critically — to refuse to make up information when the retrieved context doesn't cover the question. When no relevant chunks are found (similarity score below 0.5), a separate system prompt gracefully acknowledges the limitation instead of letting the model confabulate.

## The real engineering problem: safety

This is the part that doesn't exist in most RAG tutorials.

A therapy chatbot that hallucinates clinical advice is dangerous. A patient asking "should I stop taking my medication?" and getting a confident, grounded-sounding "yes" from an LLM is a failure mode with real consequences. So is a patient in crisis getting a canned response instead of immediate resources.

I built a dual-gate safety system — one gate on input, one on output — with four action levels:

**ALLOW** — message is safe, process normally.

**ESCALATE** — crisis signal detected (suicidal ideation, self-harm, homicidal intent). The response still generates, but crisis resources (988 Lifeline, Crisis Text Line, 911) are automatically prepended. The system doesn't try to handle the crisis itself — it immediately connects to real help.

**BLOCK** — harmful content request detected (e.g., "how to hurt myself"). Returns a refusal with crisis resources. No LLM call.

**MODIFY** — clinical boundary violation detected in the LLM's output (e.g., the model said "you have depression" or "you should take medication"). The response is appended with a disclaimer redirecting to their therapist. The model's answer still gets through, because the violation might be quoting the therapist — but the boundary is explicitly marked.

```python
class Guardrails:
    def check_input(self, text: str) -> GuardrailResult:
        """Gate 1: before the LLM sees the message."""
        assessment = self._detector.assess_input(text)
        if assessment.level == RiskLevel.CRITICAL:
            return GuardrailResult(action=GuardrailAction.ESCALATE, ...)
        if assessment.level == RiskLevel.HIGH:
            return GuardrailResult(action=GuardrailAction.BLOCK, ...)
        return GuardrailResult(action=GuardrailAction.ALLOW, ...)

    def check_output(self, text: str) -> GuardrailResult:
        """Gate 2: after the LLM responds, before the patient sees it."""
        assessment = self._detector.assess_output(text)
        if assessment.level == RiskLevel.MEDIUM:
            return GuardrailResult(
                action=GuardrailAction.MODIFY,
                modified_text=text + BOUNDARY_DISCLAIMER,
            )
        ...
```

The detection is pattern-based (regex), not ML-based. This is intentional: pattern matching is deterministic, fast, requires no additional API calls, and is fully auditable. You can look at the rule set and know exactly what triggers a flag. An ML classifier would catch more nuanced cases, but it introduces latency, cost, and opacity. For an MVP where false negatives have real consequences, I'd rather have clear rules that I can expand than a black box that's probabilistically better.

The input gate has 10 crisis patterns and 3 harmful-content patterns. The output gate has 5 clinical boundary patterns. Every rule has a name (`crisis_suicide`, `boundary_diagnosis`, `harmful_instructions`) that gets logged when triggered, so you can audit exactly why a response was modified or blocked.

## Consent as a data model, not a checkbox

In most applications, consent is a boolean flag on a user record. In a HIPAA-regulated system, consent is an audit trail.

TherapyRAG's consent model is append-only. Granting consent creates a new record with `status='granted'`. Revoking consent creates a *new* record with `status='revoked'`. Records are never updated after creation. The active consent state is determined by querying the most recent record for a given patient-therapist-type combination.

```python
class Consent(Base):
    """Append-only. Records are never updated after creation."""
    patient_id: Mapped[uuid.UUID]
    therapist_id: Mapped[uuid.UUID]
    consent_type: Mapped[ConsentType]  # RECORDING | TRANSCRIPTION | AI_ANALYSIS
    status: Mapped[ConsentStatus]       # GRANTED | REVOKED
    granted_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    ip_address: Mapped[str | None]      # captured at time of consent action
    user_agent: Mapped[str | None]      # captured at time of consent action
```

Sessions have a foreign key to consent with `ON DELETE RESTRICT` — you literally cannot delete a consent record that has sessions attached to it. The database enforces the audit trail at the schema level, not just the application level.

This matters because consent in healthcare isn't "did the user click agree." It's "can we prove the user agreed, when, from what device, and can we prove we never tampered with that record."

## Multi-tenancy and data isolation

Every API request is authenticated via an API key scoped to an organization. The key is stored as an HMAC-SHA256 hash (never plaintext). On authentication, the organization ID is extracted and injected into a `TenantContext` that validates every data access:

```python
@dataclass
class TenantContext:
    organization_id: uuid.UUID
    db_session: AsyncSession

    async def validate_user_in_org(self, user_id: uuid.UUID) -> User:
        """Raises ForbiddenError if user belongs to different org."""
        ...

    async def validate_session_access(self, session_id: uuid.UUID) -> None:
        """Validates both patient and therapist belong to the org."""
        ...
```

Vector search is additionally filtered by `patient_id` at the query level. A patient can only retrieve embeddings from their own sessions, regardless of what organization they belong to. The security boundary is enforced in the SQL query itself, not just in application logic.

## Evaluation: measuring whether the system actually works

I built a four-layer evaluation framework, because "it generates a response" is not a useful quality bar for clinical AI:

1. **Hallucination detection** — extracts keywords from each response sentence, compares them against the source chunks. A sentence needs 30% keyword overlap to be considered grounded. Meta-sentences like "based on your sessions" are auto-passed. Returns a 0-1 grounding score.

2. **Relevance scoring** — measures whether the response actually addresses the query, not just whether it contains real information.

3. **Clinical accuracy** — flags responses that cross clinical boundaries: diagnosing, prescribing, undermining the therapist relationship.

4. **Test case categories** — factual recall (can it find a specific detail?), crisis handling (does it escalate correctly?), boundary testing (does it refuse to diagnose?), adversarial (jailbreak resistance), no-context (graceful degradation when nothing relevant exists).

The hallucination detector is keyword-based rather than using an LLM-as-judge. It's less sophisticated, but it's free, fast, and doesn't have the circular problem of using an LLM to evaluate an LLM.

## Architecture choices that connect to the domain

Some decisions that might look like generic "good engineering" are actually domain-driven:

**Async-first** — the system is I/O-bound in every direction: Deepgram for transcription, OpenAI for embeddings, Anthropic for chat, asyncpg for Postgres, httpx for S3. A synchronous architecture would block on every one of these calls. FastAPI + async SQLAlchemy + AsyncAnthropic keeps throughput high without thread pool complexity.

**Repository pattern** — services never touch ORM models directly. This matters for testability (mock the repo, not the database) and for a future where the storage layer might change (different vector store, different object storage).

**Cursor pagination** — offset-based pagination breaks when records are inserted or deleted between pages. For an event stream or conversation history that's being actively written to, cursor pagination (keyed on `created_at` + `id`) avoids missing or duplicating records.

**RQ over Celery** — transcription jobs can take minutes for long recordings. RQ is simpler than Celery for an MVP, and Redis is already in the stack for rate limiting. The tradeoff is less sophisticated failure handling, which is acceptable at this scale.

## What's next

The current system handles the core loop: record, transcribe, embed, retrieve, chat. The product roadmap includes:

- **Predictive analytics** — using engagement patterns (session frequency, chat volume, sentiment trends) to flag patients who might need proactive outreach
- **Measurement-based care** — tracking standardized assessments (PHQ-9, GAD-7) over time and correlating with session content
- **AI-assisted progress notes** — reducing documentation time for therapists from 30 minutes to 5 minutes per session
- **Between-session reflections** — structured prompts that help patients engage with insights between appointments

But the foundation — consent management, safety guardrails, speaker-aware retrieval, clinical evaluation — had to come first. You can't build patient-facing AI that therapists will trust if the safety story is an afterthought.

## The takeaway

The interesting part of building a clinical RAG system isn't the retrieval. It's the constraints. Every design decision — append-only consent, dual-gate safety, patient-scoped vector search, pattern-based risk detection, speaker-aware chunking — exists because the domain demands it. The same technique that works fine in a document Q&A demo becomes a liability when the document is a therapy transcript and the user is a patient in distress.

Building this taught me that the gap between "RAG that works" and "RAG that's safe to deploy" is where the real engineering lives.
