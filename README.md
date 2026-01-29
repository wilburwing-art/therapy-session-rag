# TherapyRAG 🧠💬

**Session Recording → Transcription → Patient-Facing RAG Chatbot**

A demo-ready backend platform that enables therapy providers to record sessions (with consent), transcribe them, and power a patient-facing chatbot that can answer questions like "What homework did we discuss last week?"

> Built for pitching to existing telehealth platforms and investors.

## Features

- ✅ **HIPAA-Critical Consent Management** - Full audit trail, immutable records
- 🎙️ **Recording Ingestion** - Accept audio/video uploads with async processing
- 📝 **Automatic Transcription** - Deepgram integration with speaker diarization
- 🔍 **Semantic Search** - pgvector embeddings for relevant context retrieval
- 🤖 **RAG Chatbot** - Claude-powered responses with session citations
- 🔐 **API Key Authentication** - Simple auth for platform integration

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Recording UI   │────▶│  Transcription   │────▶│  Vector Store   │
│  + Consent      │     │  Pipeline        │     │  (pgvector)     │
└─────────────────┘     └──────────────────┘     └────────┬────────┘
                                                          │
┌─────────────────┐     ┌──────────────────┐              │
│  Patient Chat   │◀───▶│  RAG Chatbot     │◀─────────────┘
│  Interface      │     │  (Claude)        │
└─────────────────┘     └──────────────────┘
```

## Quick Start

### 1. Clone and Setup

```bash
git clone <repo-url>
cd therapy-session-rag

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env
# Edit .env with your API keys (Deepgram, OpenAI, Anthropic)
```

### 2. Start Services

```bash
# Start PostgreSQL, Redis, MinIO
docker compose up -d

# Wait for services to be healthy
docker compose ps
```

### 3. Run Migrations

```bash
alembic upgrade head
```

### 4. Start the API

```bash
uvicorn src.main:app --reload
```

Visit http://localhost:8000/docs for the interactive API documentation.

## Development with Ralph Wiggum Loop 🔄

This project is set up for autonomous AI development using the [Ralph Wiggum technique](https://awesomeclaude.ai/ralph-wiggum).

### What is Ralph?

Ralph is a bash loop that feeds an AI agent (Claude Code) a prompt repeatedly until the task is complete. Progress persists in git and files, not in the LLM's context window.

### How to Use

1. **Planning Mode** - Generate/update the implementation plan:
   ```bash
   ./scripts/ralph-loop.sh plan
   ```

2. **Build Mode** - Implement tasks one at a time:
   ```bash
   ./scripts/ralph-loop.sh build
   ```

3. **Using Claude Code Plugin** (alternative):
   ```bash
   # Install plugin
   /plugin install ralph-wiggum@claude-plugins-official
   
   # Run loop
   /ralph-loop "Implement the next task from IMPLEMENTATION_PLAN.md" \
     --completion-promise "BUILD_COMPLETE" \
     --max-iterations 50
   ```

### Key Files

| File | Purpose |
|------|---------|
| `specs/SPEC.md` | Full requirements specification |
| `IMPLEMENTATION_PLAN.md` | Task breakdown with status |
| `AGENTS.md` | Build/test commands for backpressure |
| `.ralph/PROMPT_plan.md` | Planning mode instructions |
| `.ralph/PROMPT_build.md` | Build mode instructions |

### Philosophy

> "Sit on the loop, not in it." — Geoffrey Huntley

- **Backpressure over direction**: Tests and linting reject bad work automatically
- **One task per iteration**: Small, focused commits
- **Fresh context**: Each iteration starts clean, reads state from files
- **Deterministically bad**: Predictable failures are useful for tuning prompts

## API Overview

### Authentication
All endpoints (except `/health`) require an API key in the `X-API-Key` header.

### Core Endpoints

```
POST   /api/v1/consent              # Grant recording consent
DELETE /api/v1/consent/{id}         # Revoke consent
GET    /api/v1/consent/{patient_id} # Check consent status

POST   /api/v1/sessions/upload      # Upload recording
GET    /api/v1/sessions/{id}/status # Check processing status
GET    /api/v1/sessions/{id}/transcript # Get transcript

POST   /api/v1/chat                 # Patient chatbot
```

### Example: Chat Request

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "X-API-Key: your_key" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "uuid",
    "message": "What did we discuss about managing anxiety?"
  }'
```

Response:
```json
{
  "response": "In your session on January 15th, you and Dr. Smith discussed several techniques for managing anxiety...",
  "sources": [
    {
      "session_id": "uuid",
      "session_date": "2025-01-15",
      "relevance": 0.89
    }
  ],
  "conversation_id": "uuid"
}
```

## Testing

```bash
# Run all tests
pytest tests -v

# With coverage
pytest tests -v --cov=src --cov-report=html

# Unit tests only
pytest tests/unit -v

# Integration tests (requires Docker services)
pytest tests/integration -v
```

## Tech Stack

- **Python 3.11+** / FastAPI
- **PostgreSQL 16** with pgvector
- **Redis** + RQ for job queue
- **MinIO** for S3-compatible storage
- **Deepgram** for transcription
- **OpenAI** for embeddings
- **Claude** for chat responses

## Project Status

See `IMPLEMENTATION_PLAN.md` for current progress.

## License

MIT
