# Architecture

## System Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Client/API     │────▶│  FastAPI Backend │────▶│  PostgreSQL     │
│  (Platform)     │     │  (Async)         │     │  + pgvector     │
└─────────────────┘     └────────┬─────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌─────────┐  ┌─────────┐  ┌─────────┐
              │ Deepgram│  │  MinIO  │  │  Redis  │
              │ (ASR)   │  │ (S3)    │  │ (Queue) │
              └─────────┘  └─────────┘  └─────────┘
```

## Component Map

```
src/
├── main.py                 # FastAPI app entry, lifespan, middleware
├── api/
│   └── v1/
│       ├── router.py       # Route aggregation
│       ├── dependencies.py # Auth, tenant context, rate limiting
│       └── endpoints/
│           ├── consent.py  # Consent CRUD (immutable audit trail)
│           ├── sessions.py # Recording upload, transcription status
│           └── chat.py     # RAG chatbot endpoint
├── services/               # Business logic layer
│   ├── consent_service.py
│   ├── session_service.py
│   ├── transcription_service.py
│   └── chat_service.py     # RAG orchestration
├── repositories/           # Data access layer (SQLAlchemy async)
│   ├── consent_repo.py
│   ├── session_repo.py
│   └── embedding_repo.py
├── models/
│   ├── domain/             # Pydantic DTOs (API contracts)
│   │   ├── consent.py
│   │   ├── session.py
│   │   └── chat.py
│   └── db/                 # SQLAlchemy ORM models
│       ├── base.py
│       ├── consent.py
│       ├── session.py
│       └── embedding.py
├── core/
│   ├── config.py           # Pydantic settings from env
│   ├── database.py         # Async engine, session factory
│   ├── logging.py          # Structlog configuration
│   ├── security.py         # API key validation
│   ├── tenant.py           # TenantContext for RLS
│   └── pagination.py       # Cursor-based pagination
├── workers/                # RQ background jobs
│   └── transcription.py    # Deepgram processing
└── evaluation/             # RAG quality metrics
```

## Data Flow

### Recording Upload
```
1. Client uploads audio → POST /sessions
2. Session created in DB (status: pending)
3. Audio stored in MinIO
4. RQ job queued for transcription
5. Worker: Deepgram transcribes → stores transcript
6. Worker: Generate embeddings → store in pgvector
7. Session status updated (status: complete)
```

### RAG Chat
```
1. Patient sends message → POST /chat
2. TenantContext set from API key
3. Message embedded via OpenAI
4. pgvector similarity search (top-k chunks)
5. Context + message sent to Claude
6. Response returned with citations
```

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Async everywhere | I/O-bound workload (DB, HTTP, S3) |
| Repository pattern | Testable, swappable data layer |
| Domain/DB model separation | API contracts don't leak ORM details |
| pgvector over Pinecone | Single DB, simpler ops, good enough scale |
| RQ over Celery | Simpler for this scale, Redis already present |
| Cursor pagination | Efficient for large result sets, no offset drift |

## Security Boundaries

```
┌─────────────────────────────────────────────────┐
│                 API Gateway                      │
│  • API Key validation                           │
│  • Rate limiting (Redis)                        │
│  • Request logging                              │
└─────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│              TenantContext                       │
│  • Set from API key → platform_id               │
│  • All queries filtered by tenant               │
│  • Row-level security                           │
└─────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────┐
│              Data Layer                          │
│  • Consent audit trail (immutable)              │
│  • PHI encrypted at rest                        │
│  • No direct DB access from API                 │
└─────────────────────────────────────────────────┘
```

## Infrastructure

| Component | Local Dev | Production |
|-----------|-----------|------------|
| Database | Docker postgres:16 + pgvector | RDS/Cloud SQL |
| Object Storage | MinIO | S3 |
| Queue | Redis + RQ | Redis + RQ |
| API | uvicorn --reload | Gunicorn + uvicorn workers |
