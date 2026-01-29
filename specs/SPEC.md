# TherapyRAG - Session Recording & Patient Chatbot Platform

## Overview

A backend platform that enables therapy providers to record sessions (with consent), transcribe them, and persist session data for a patient-facing RAG chatbot. The goal is a demo-ready MVP for pitching to existing telehealth platforms and investors.

## Target Users

1. **Therapists/Providers**: Upload recordings, view transcripts, manage patient consent
2. **Patients/Clients**: Chat with an AI that has context from their sessions
3. **Platform Integrators**: REST API for embedding into existing telehealth products

## Core Requirements

### 1. Consent Management Service

**Purpose**: HIPAA-critical tracking of recording consent with full audit trail.

**Acceptance Criteria**:
- [ ] Patient can grant consent for session recording
- [ ] Patient can revoke consent at any time
- [ ] Consent status is checked before any recording is processed
- [ ] All consent changes are logged with timestamp, IP, user agent
- [ ] Consent records are immutable (append-only audit log)
- [ ] API returns 403 if attempting to process recording without valid consent

**Data Model**:
```
Consent:
  - id: UUID
  - patient_id: UUID (FK)
  - therapist_id: UUID (FK)  
  - consent_type: ENUM('recording', 'transcription', 'ai_analysis')
  - status: ENUM('granted', 'revoked')
  - granted_at: timestamp
  - revoked_at: timestamp (nullable)
  - ip_address: string
  - user_agent: string
  - metadata: JSONB
```

### 2. Recording Ingestion Service

**Purpose**: Accept audio/video uploads, validate, and queue for processing.

**Acceptance Criteria**:
- [ ] Accept multipart file uploads (audio: mp3, wav, m4a, webm; video: mp4, webm)
- [ ] Validate file size (max 500MB)
- [ ] Validate consent exists before accepting upload
- [ ] Store files in S3-compatible storage with encryption at rest
- [ ] Generate unique session ID and return immediately (async processing)
- [ ] Queue transcription job upon successful upload
- [ ] Track upload status: pending, uploaded, processing, completed, failed

**Data Model**:
```
Session:
  - id: UUID
  - patient_id: UUID (FK)
  - therapist_id: UUID (FK)
  - consent_id: UUID (FK)
  - session_date: timestamp
  - recording_path: string (S3 key)
  - recording_duration_seconds: int
  - status: ENUM('pending', 'uploaded', 'transcribing', 'embedding', 'ready', 'failed')
  - error_message: string (nullable)
  - metadata: JSONB
  - created_at: timestamp
  - updated_at: timestamp
```

### 3. Transcription Pipeline

**Purpose**: Convert audio to text with speaker diarization.

**Acceptance Criteria**:
- [ ] Process audio files from queue asynchronously
- [ ] Use Deepgram API for transcription (good speaker diarization, HIPAA-compliant tier available)
- [ ] Identify and label speakers (Therapist vs Patient)
- [ ] Store transcript with timestamps for each segment
- [ ] Handle failures gracefully with retry logic (3 retries, exponential backoff)
- [ ] Update session status throughout pipeline
- [ ] Emit event when transcription complete (for embedding pipeline)

**Data Model**:
```
Transcript:
  - id: UUID
  - session_id: UUID (FK)
  - full_text: text
  - segments: JSONB (array of {speaker, text, start_time, end_time})
  - language: string
  - confidence: float
  - created_at: timestamp

TranscriptionJob:
  - id: UUID
  - session_id: UUID (FK)
  - status: ENUM('queued', 'processing', 'completed', 'failed')
  - attempts: int
  - last_error: string (nullable)
  - started_at: timestamp
  - completed_at: timestamp
```

### 4. Embedding & Vector Storage Pipeline

**Purpose**: Chunk transcripts and store embeddings for semantic search.

**Acceptance Criteria**:
- [ ] Chunk transcripts intelligently (by topic/time, ~500 tokens per chunk)
- [ ] Preserve metadata: session_id, timestamp range, speaker
- [ ] Generate embeddings using OpenAI text-embedding-3-small (or configurable)
- [ ] Store in pgvector for simplicity (single DB)
- [ ] Index for fast similarity search
- [ ] Handle re-embedding if transcript is updated

**Data Model**:
```
SessionChunk:
  - id: UUID
  - session_id: UUID (FK)
  - transcript_id: UUID (FK)
  - chunk_index: int
  - content: text
  - start_time: float
  - end_time: float
  - speaker: string
  - embedding: vector(1536)
  - metadata: JSONB
  - created_at: timestamp
```

### 5. Patient RAG Chatbot API

**Purpose**: Answer patient questions using their session history.

**Acceptance Criteria**:
- [ ] Patient can only access their own session data (auth required)
- [ ] Semantic search retrieves top-k relevant chunks across all patient sessions
- [ ] Retrieved chunks are passed to Claude API as context
- [ ] System prompt ensures therapeutic, supportive tone
- [ ] Responses cite which session the information came from
- [ ] Rate limiting: 20 messages per hour per patient
- [ ] Conversation history maintained within session (for follow-ups)

**API Endpoints**:
```
POST /api/v1/chat
{
  "patient_id": "uuid",
  "message": "What homework did we discuss last week?",
  "conversation_id": "uuid" (optional, for follow-ups)
}

Response:
{
  "response": "In your session on January 15th, Dr. Smith suggested...",
  "sources": [
    {"session_id": "uuid", "session_date": "2025-01-15", "relevance": 0.89}
  ],
  "conversation_id": "uuid"
}
```

### 6. API Authentication & Multi-tenancy

**Purpose**: Simple API key auth for MVP, scoped to organizations.

**Acceptance Criteria**:
- [ ] API keys scoped to organization
- [ ] Each request must include valid API key in header
- [ ] Keys can be created/revoked via admin endpoint
- [ ] Rate limiting per API key (1000 req/hour)
- [ ] All endpoints require authentication except /health

**Data Model**:
```
Organization:
  - id: UUID
  - name: string
  - created_at: timestamp

ApiKey:
  - id: UUID
  - organization_id: UUID (FK)
  - key_hash: string (hashed, never store plaintext)
  - name: string (for identification)
  - is_active: boolean
  - last_used_at: timestamp
  - created_at: timestamp
  - revoked_at: timestamp (nullable)

User (Therapist/Patient):
  - id: UUID
  - organization_id: UUID (FK)
  - email: string
  - role: ENUM('therapist', 'patient', 'admin')
  - created_at: timestamp
```

## Technical Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI
- **Database**: PostgreSQL 15+ with pgvector extension
- **Queue**: Redis + RQ (simple, sufficient for MVP)
- **Storage**: MinIO (S3-compatible, easy local dev)
- **Transcription**: Deepgram API
- **Embeddings**: OpenAI API (text-embedding-3-small)
- **LLM**: Claude API (claude-sonnet-4-20250514)
- **Testing**: pytest + pytest-asyncio
- **Linting**: ruff
- **Type Checking**: mypy (strict mode)

## Non-Functional Requirements

- All endpoints return JSON
- All errors follow RFC 7807 Problem Details format
- All timestamps in ISO 8601 UTC
- Logs in structured JSON format
- Health check endpoint at /health
- OpenAPI docs auto-generated at /docs

## Out of Scope (for MVP)

- User authentication UI (API keys only)
- Real-time transcription (upload only)
- Video analysis / emotion detection
- HIPAA BAA with cloud providers (that's a business concern)
- Frontend dashboard (API-only for now)
- Multi-language support

## Success Metrics (for Demo)

1. Upload a 30-minute recording → transcribed in <5 minutes
2. Patient asks "What did we discuss about anxiety?" → relevant response in <3 seconds
3. 10 concurrent chat sessions → no degradation
4. Zero data leakage between patients (tested)

## Environment Variables Required

```
DATABASE_URL=postgresql://user:pass@localhost:5432/therapyrag
REDIS_URL=redis://localhost:6379
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=therapy-recordings
DEEPGRAM_API_KEY=your_key
OPENAI_API_KEY=your_key
ANTHROPIC_API_KEY=your_key
```
