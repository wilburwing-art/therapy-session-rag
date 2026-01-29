# IMPLEMENTATION_PLAN.md - TherapyRAG

Last Updated: Auto-generated

## Progress Overview

| Phase | Status | Tasks |
|-------|--------|-------|
| Phase 1: Foundation | Not Started | 0/7 |
| Phase 2: Consent & Auth | Not Started | 0/5 |
| Phase 3: Recording Ingestion | Not Started | 0/5 |
| Phase 4: Transcription Pipeline | Not Started | 0/5 |
| Phase 5: Embedding Pipeline | Not Started | 0/4 |
| Phase 6: RAG Chatbot | Not Started | 0/5 |
| Phase 7: Polish | Not Started | 0/4 |

---

## Phase 1: Foundation

### Task 1.1: Project Setup

**Status**: [ ] Not Started

**Description**: Initialize Python project with pyproject.toml, install dependencies, configure tooling.

**Acceptance Criteria**:
- [ ] pyproject.toml with all dependencies listed
- [ ] Virtual environment works (`pip install -e ".[dev]"`)
- [ ] ruff, mypy, pytest configured
- [ ] Basic .gitignore in place

**Files to Create**:
- pyproject.toml
- .gitignore
- src/__init__.py
- tests/__init__.py

**Tests Required**: None (tooling only)

**Dependencies**: None

---

### Task 1.2: Core Configuration

**Status**: [ ] Not Started

**Description**: Create settings module using Pydantic Settings for environment variable handling.

**Acceptance Criteria**:
- [ ] Settings class loads from environment variables
- [ ] All required env vars from spec are defined
- [ ] Validation fails if required vars missing
- [ ] Settings is a singleton

**Files to Create**:
- src/core/__init__.py
- src/core/config.py
- .env.example

**Tests Required**:
- tests/unit/core/test_config.py: test settings loading, defaults, validation

**Dependencies**: Task 1.1

---

### Task 1.3: Database Setup

**Status**: [ ] Not Started

**Description**: Configure SQLAlchemy async engine, sessionmaker, and base model.

**Acceptance Criteria**:
- [ ] Async engine connects to PostgreSQL
- [ ] Session dependency for FastAPI
- [ ] Base model class with common fields (id, created_at, updated_at)
- [ ] pgvector extension enabled

**Files to Create**:
- src/core/database.py
- src/models/__init__.py
- src/models/db/__init__.py
- src/models/db/base.py

**Tests Required**:
- tests/integration/test_database.py: test connection, session creation

**Dependencies**: Task 1.2

---

### Task 1.4: FastAPI Application Shell

**Status**: [ ] Not Started

**Description**: Create FastAPI app with health check, CORS, error handling.

**Acceptance Criteria**:
- [ ] GET /health returns {"status": "healthy"}
- [ ] CORS configured for all origins (dev mode)
- [ ] Global exception handler returns RFC 7807 format
- [ ] OpenAPI docs at /docs

**Files to Create**:
- src/main.py
- src/api/__init__.py
- src/api/v1/__init__.py
- src/api/v1/router.py
- src/core/exceptions.py

**Tests Required**:
- tests/unit/api/test_health.py: test health endpoint
- tests/unit/core/test_exceptions.py: test error formatting

**Dependencies**: Task 1.2

---

### Task 1.5: Organization Model

**Status**: [ ] Not Started

**Description**: Create Organization SQLAlchemy model and Pydantic schemas.

**Acceptance Criteria**:
- [ ] Organization DB model with id, name, created_at
- [ ] Pydantic schemas: OrganizationCreate, OrganizationRead
- [ ] Alembic migration creates table

**Files to Create**:
- src/models/db/organization.py
- src/models/domain/organization.py
- alembic/versions/001_create_organization.py

**Tests Required**:
- tests/unit/models/test_organization.py: test model creation, schema validation

**Dependencies**: Task 1.3

---

### Task 1.6: User Model

**Status**: [ ] Not Started

**Description**: Create User SQLAlchemy model with role enum.

**Acceptance Criteria**:
- [ ] User DB model with id, organization_id, email, role, created_at
- [ ] UserRole enum: therapist, patient, admin
- [ ] Foreign key to Organization
- [ ] Pydantic schemas: UserCreate, UserRead

**Files to Create**:
- src/models/db/user.py
- src/models/domain/user.py
- alembic/versions/002_create_user.py

**Tests Required**:
- tests/unit/models/test_user.py: test model, role enum, FK constraint

**Dependencies**: Task 1.5

---

### Task 1.7: Alembic Setup

**Status**: [ ] Not Started

**Description**: Configure Alembic for database migrations.

**Acceptance Criteria**:
- [ ] alembic.ini configured for async
- [ ] env.py imports all models
- [ ] `alembic upgrade head` works
- [ ] `alembic revision --autogenerate` works

**Files to Create**:
- alembic.ini
- alembic/env.py
- alembic/script.py.mako

**Tests Required**:
- tests/integration/test_migrations.py: test upgrade/downgrade

**Dependencies**: Task 1.3

---

## Phase 2: Consent & Auth

### Task 2.1: API Key Model

**Status**: [ ] Not Started

**Description**: Create ApiKey model with hashed storage.

**Acceptance Criteria**:
- [ ] ApiKey DB model with hashed key, never plaintext
- [ ] Organization FK
- [ ] is_active, last_used_at, revoked_at fields
- [ ] Pydantic schemas for create (returns key once), read (no key)

**Files to Create**:
- src/models/db/api_key.py
- src/models/domain/api_key.py
- src/core/security.py (hash/verify functions)
- alembic/versions/003_create_api_key.py

**Tests Required**:
- tests/unit/models/test_api_key.py
- tests/unit/core/test_security.py

**Dependencies**: Task 1.5, Task 1.7

---

### Task 2.2: API Key Authentication Dependency

**Status**: [ ] Not Started

**Description**: Create FastAPI dependency that validates API key from header.

**Acceptance Criteria**:
- [ ] Reads X-API-Key header
- [ ] Validates against database
- [ ] Returns 401 if missing/invalid
- [ ] Updates last_used_at on valid request
- [ ] Provides organization_id to endpoint

**Files to Create**:
- src/api/v1/dependencies.py
- src/repositories/api_key_repo.py

**Tests Required**:
- tests/unit/api/test_dependencies.py: test auth flow, missing key, invalid key

**Dependencies**: Task 2.1

---

### Task 2.3: Consent Model

**Status**: [ ] Not Started

**Description**: Create Consent model with audit fields.

**Acceptance Criteria**:
- [ ] Consent DB model per spec
- [ ] ConsentType enum: recording, transcription, ai_analysis
- [ ] ConsentStatus enum: granted, revoked
- [ ] Immutable pattern (new row on revoke, not update)
- [ ] Pydantic schemas

**Files to Create**:
- src/models/db/consent.py
- src/models/domain/consent.py
- alembic/versions/004_create_consent.py

**Tests Required**:
- tests/unit/models/test_consent.py

**Dependencies**: Task 1.6, Task 1.7

---

### Task 2.4: Consent Service

**Status**: [ ] Not Started

**Description**: Service for granting, revoking, and checking consent.

**Acceptance Criteria**:
- [ ] grant_consent() creates new consent record
- [ ] revoke_consent() creates revocation record
- [ ] check_consent() returns current status for patient/type
- [ ] get_audit_log() returns all consent history
- [ ] Captures IP and user agent

**Files to Create**:
- src/services/consent_service.py
- src/repositories/consent_repo.py

**Tests Required**:
- tests/unit/services/test_consent_service.py: all methods, edge cases

**Dependencies**: Task 2.3

---

### Task 2.5: Consent API Endpoints

**Status**: [ ] Not Started

**Description**: REST endpoints for consent management.

**Acceptance Criteria**:
- [ ] POST /api/v1/consent - grant consent
- [ ] DELETE /api/v1/consent/{id} - revoke consent
- [ ] GET /api/v1/consent/{patient_id} - check current consent
- [ ] GET /api/v1/consent/{patient_id}/audit - full history
- [ ] All endpoints require API key auth

**Files to Create**:
- src/api/v1/endpoints/consent.py

**Tests Required**:
- tests/integration/test_consent_api.py: full CRUD flow

**Dependencies**: Task 2.2, Task 2.4

---

## Phase 3: Recording Ingestion

### Task 3.1: Session Model

**Status**: [ ] Not Started

**Description**: Create Session model for tracking recordings.

**Acceptance Criteria**:
- [ ] Session DB model per spec
- [ ] SessionStatus enum with all states
- [ ] FKs to patient, therapist, consent
- [ ] Pydantic schemas

**Files to Create**:
- src/models/db/session.py
- src/models/domain/session.py
- alembic/versions/005_create_session.py

**Tests Required**:
- tests/unit/models/test_session.py

**Dependencies**: Task 2.3

---

### Task 3.2: MinIO Storage Service

**Status**: [ ] Not Started

**Description**: Service for uploading files to S3-compatible storage.

**Acceptance Criteria**:
- [ ] upload_file() stores file and returns S3 key
- [ ] get_presigned_url() for temporary access
- [ ] delete_file() removes from storage
- [ ] Configurable bucket name
- [ ] Handles connection errors gracefully

**Files to Create**:
- src/services/storage_service.py

**Tests Required**:
- tests/unit/services/test_storage_service.py (mocked)
- tests/integration/test_storage_service.py (real MinIO)

**Dependencies**: Task 1.2

---

### Task 3.3: Session Service

**Status**: [ ] Not Started

**Description**: Service for creating and managing sessions.

**Acceptance Criteria**:
- [ ] create_session() validates consent first
- [ ] update_status() transitions session state
- [ ] get_session() retrieves by ID
- [ ] list_sessions() with filters (patient, therapist, date range)

**Files to Create**:
- src/services/session_service.py
- src/repositories/session_repo.py

**Tests Required**:
- tests/unit/services/test_session_service.py

**Dependencies**: Task 3.1, Task 2.4

---

### Task 3.4: Recording Upload Endpoint

**Status**: [ ] Not Started

**Description**: Endpoint to upload audio/video files.

**Acceptance Criteria**:
- [ ] POST /api/v1/sessions/upload accepts multipart
- [ ] Validates file type (audio/video)
- [ ] Validates file size (<500MB)
- [ ] Checks consent before accepting
- [ ] Returns session ID immediately
- [ ] Queues transcription job

**Files to Create**:
- src/api/v1/endpoints/sessions.py

**Tests Required**:
- tests/integration/test_upload.py

**Dependencies**: Task 3.2, Task 3.3, Task 2.4

---

### Task 3.5: Redis Queue Setup

**Status**: [ ] Not Started

**Description**: Configure Redis and RQ for background jobs.

**Acceptance Criteria**:
- [ ] Redis connection configured
- [ ] RQ queue created
- [ ] Worker can be started separately
- [ ] Job status can be queried

**Files to Create**:
- src/core/queue.py
- src/workers/__init__.py

**Tests Required**:
- tests/integration/test_queue.py

**Dependencies**: Task 1.2

---

## Phase 4: Transcription Pipeline

### Task 4.1: Transcript Model

**Status**: [ ] Not Started

**Description**: Create Transcript and TranscriptionJob models.

**Acceptance Criteria**:
- [ ] Transcript DB model per spec
- [ ] TranscriptionJob for tracking job status
- [ ] Segments stored as JSONB
- [ ] Pydantic schemas

**Files to Create**:
- src/models/db/transcript.py
- src/models/domain/transcript.py
- alembic/versions/006_create_transcript.py

**Tests Required**:
- tests/unit/models/test_transcript.py

**Dependencies**: Task 3.1

---

### Task 4.2: Deepgram Client

**Status**: [ ] Not Started

**Description**: Client for Deepgram transcription API.

**Acceptance Criteria**:
- [ ] transcribe_file() sends audio and returns transcript
- [ ] Handles speaker diarization
- [ ] Returns structured segments with timestamps
- [ ] Retries on transient errors

**Files to Create**:
- src/services/deepgram_client.py

**Tests Required**:
- tests/unit/services/test_deepgram_client.py (mocked)

**Dependencies**: Task 1.2

---

### Task 4.3: Transcription Service

**Status**: [ ] Not Started

**Description**: Orchestrates transcription workflow.

**Acceptance Criteria**:
- [ ] process_transcription() handles full flow
- [ ] Downloads from S3, sends to Deepgram, stores result
- [ ] Updates session status throughout
- [ ] Handles failures with retry logic

**Files to Create**:
- src/services/transcription_service.py
- src/repositories/transcript_repo.py

**Tests Required**:
- tests/unit/services/test_transcription_service.py

**Dependencies**: Task 4.1, Task 4.2, Task 3.2

---

### Task 4.4: Transcription Worker

**Status**: [ ] Not Started

**Description**: RQ worker that processes transcription jobs.

**Acceptance Criteria**:
- [ ] Picks jobs from queue
- [ ] Calls transcription service
- [ ] Handles exceptions gracefully
- [ ] Updates job status
- [ ] Emits event for embedding pipeline

**Files to Create**:
- src/workers/transcription_worker.py

**Tests Required**:
- tests/integration/test_transcription_worker.py

**Dependencies**: Task 4.3, Task 3.5

---

### Task 4.5: Transcript API Endpoints

**Status**: [ ] Not Started

**Description**: Endpoints to retrieve transcripts.

**Acceptance Criteria**:
- [ ] GET /api/v1/sessions/{id}/transcript
- [ ] GET /api/v1/sessions/{id}/status
- [ ] Returns 404 if not found
- [ ] Returns 202 if still processing

**Files to Create**:
- Update src/api/v1/endpoints/sessions.py

**Tests Required**:
- tests/integration/test_transcript_api.py

**Dependencies**: Task 4.3

---

## Phase 5: Embedding Pipeline

### Task 5.1: SessionChunk Model with pgvector

**Status**: [ ] Not Started

**Description**: Create model for storing transcript chunks with embeddings.

**Acceptance Criteria**:
- [ ] SessionChunk DB model per spec
- [ ] Vector column type (1536 dimensions)
- [ ] Index for similarity search
- [ ] Pydantic schemas

**Files to Create**:
- src/models/db/session_chunk.py
- src/models/domain/session_chunk.py
- alembic/versions/007_create_session_chunk.py

**Tests Required**:
- tests/unit/models/test_session_chunk.py

**Dependencies**: Task 4.1

---

### Task 5.2: Embedding Client

**Status**: [ ] Not Started

**Description**: Client for OpenAI embeddings API.

**Acceptance Criteria**:
- [ ] embed_text() returns vector for single text
- [ ] embed_batch() handles multiple texts efficiently
- [ ] Handles rate limits with backoff
- [ ] Configurable model (default: text-embedding-3-small)

**Files to Create**:
- src/services/embedding_client.py

**Tests Required**:
- tests/unit/services/test_embedding_client.py (mocked)

**Dependencies**: Task 1.2

---

### Task 5.3: Embedding Service

**Status**: [ ] Not Started

**Description**: Chunks transcripts and generates embeddings.

**Acceptance Criteria**:
- [ ] chunk_transcript() splits by semantic boundaries (~500 tokens)
- [ ] Preserves metadata (timestamps, speaker)
- [ ] process_embedding() generates and stores embeddings
- [ ] Handles re-embedding on transcript update

**Files to Create**:
- src/services/embedding_service.py
- src/repositories/chunk_repo.py

**Tests Required**:
- tests/unit/services/test_embedding_service.py

**Dependencies**: Task 5.1, Task 5.2, Task 4.3

---

### Task 5.4: Embedding Worker

**Status**: [ ] Not Started

**Description**: RQ worker for embedding generation.

**Acceptance Criteria**:
- [ ] Picks jobs from embedding queue
- [ ] Calls embedding service
- [ ] Updates session status to 'ready' when complete
- [ ] Handles failures gracefully

**Files to Create**:
- src/workers/embedding_worker.py

**Tests Required**:
- tests/integration/test_embedding_worker.py

**Dependencies**: Task 5.3, Task 3.5

---

## Phase 6: RAG Chatbot

### Task 6.1: Vector Search Repository

**Status**: [ ] Not Started

**Description**: Repository for semantic search over chunks.

**Acceptance Criteria**:
- [ ] search_similar() returns top-k chunks by cosine similarity
- [ ] Filters by patient_id (security critical!)
- [ ] Returns with relevance scores
- [ ] Configurable k (default: 5)

**Files to Create**:
- src/repositories/vector_search_repo.py

**Tests Required**:
- tests/integration/test_vector_search.py

**Dependencies**: Task 5.1

---

### Task 6.2: Claude Client

**Status**: [ ] Not Started

**Description**: Client for Claude API with chat completions.

**Acceptance Criteria**:
- [ ] chat() sends messages and returns response
- [ ] Supports system prompt
- [ ] Handles context (previous messages)
- [ ] Configurable model (default: claude-sonnet-4-20250514)

**Files to Create**:
- src/services/claude_client.py

**Tests Required**:
- tests/unit/services/test_claude_client.py (mocked)

**Dependencies**: Task 1.2

---

### Task 6.3: Chat Service

**Status**: [ ] Not Started

**Description**: RAG service that retrieves context and generates responses.

**Acceptance Criteria**:
- [ ] chat() retrieves relevant chunks, calls Claude, returns response
- [ ] System prompt ensures therapeutic tone
- [ ] Includes source citations in response
- [ ] Maintains conversation history
- [ ] Rate limits per patient (20/hour)

**Files to Create**:
- src/services/chat_service.py
- src/models/domain/chat.py

**Tests Required**:
- tests/unit/services/test_chat_service.py

**Dependencies**: Task 6.1, Task 6.2

---

### Task 6.4: Chat API Endpoint

**Status**: [ ] Not Started

**Description**: REST endpoint for patient chat.

**Acceptance Criteria**:
- [ ] POST /api/v1/chat per spec
- [ ] Validates patient has access to their own data only
- [ ] Returns response with sources
- [ ] Handles conversation_id for follow-ups
- [ ] Rate limit enforced

**Files to Create**:
- src/api/v1/endpoints/chat.py

**Tests Required**:
- tests/integration/test_chat_api.py

**Dependencies**: Task 6.3, Task 2.2

---

### Task 6.5: Chat Rate Limiting

**Status**: [ ] Not Started

**Description**: Implement rate limiting for chat endpoint.

**Acceptance Criteria**:
- [ ] 20 messages per hour per patient
- [ ] Returns 429 when exceeded
- [ ] Reset counter after hour
- [ ] Stored in Redis

**Files to Create**:
- src/services/rate_limiter.py

**Tests Required**:
- tests/unit/services/test_rate_limiter.py

**Dependencies**: Task 6.4, Task 3.5

---

## Phase 7: Polish

### Task 7.1: Structured Logging

**Status**: [ ] Not Started

**Description**: Configure JSON structured logging.

**Acceptance Criteria**:
- [ ] All logs in JSON format
- [ ] Request ID tracked through request
- [ ] Log level configurable
- [ ] Sensitive data redacted

**Files to Create**:
- src/core/logging.py
- Update src/main.py

**Tests Required**:
- tests/unit/core/test_logging.py

**Dependencies**: Task 1.4

---

### Task 7.2: Docker Compose

**Status**: [ ] Not Started

**Description**: Docker setup for local development.

**Acceptance Criteria**:
- [ ] PostgreSQL with pgvector
- [ ] Redis
- [ ] MinIO
- [ ] App service
- [ ] Worker service

**Files to Create**:
- docker-compose.yml
- Dockerfile
- .dockerignore

**Tests Required**: Manual verification

**Dependencies**: Task 1.1

---

### Task 7.3: API Documentation

**Status**: [ ] Not Started

**Description**: Enhance OpenAPI documentation.

**Acceptance Criteria**:
- [ ] All endpoints have descriptions
- [ ] All models have examples
- [ ] Error responses documented
- [ ] Authentication documented

**Files to Create**:
- Update all endpoint files with docstrings

**Tests Required**: Manual review

**Dependencies**: All API endpoints

---

### Task 7.4: README and Demo Guide

**Status**: [ ] Not Started

**Description**: Write comprehensive README.

**Acceptance Criteria**:
- [ ] Project overview
- [ ] Quick start guide
- [ ] API reference
- [ ] Demo walkthrough
- [ ] Architecture diagram

**Files to Create**:
- README.md
- docs/DEMO.md
- docs/architecture.md

**Tests Required**: None

**Dependencies**: All tasks

---

## Notes

- **Blocked tasks**: Document issues here
- **Learnings**: Add patterns discovered during implementation
