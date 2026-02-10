# Lessons Learned

Project-specific discoveries and insights for therapy-session-rag.

---

## Architecture

### YYYY-MM-DD: Repository pattern pays off
**Context**: [Describe situation]
**Learning**: Having repositories between services and ORM made testing much easier. Could mock the entire data layer.
**Impact**: Test suite runs in seconds without database.

### YYYY-MM-DD: Cursor pagination > offset pagination
**Context**: [Describe situation]
**Learning**: Offset pagination breaks when data changes mid-pagination. Cursor-based is more reliable for large datasets.
**Impact**: Implemented cursor pagination from the start.

---

## Database

### YYYY-MM-DD: pgvector index tuning
**Context**: [Describe situation]
**Learning**: Default HNSW parameters caused slow queries. Needed to tune `m` and `ef_construction` for our dataset size.
**Impact**: [Quantify improvement]

### YYYY-MM-DD: Alembic autogenerate limitations
**Context**: [Describe situation]
**Learning**: Autogenerate doesn't catch all changes (e.g., index changes, check constraints). Always review generated migrations.
**Impact**: Added migration review to PR checklist.

---

## Transcription

### YYYY-MM-DD: Deepgram webhook pattern
**Context**: [Describe situation]
**Learning**: Must acknowledge webhook within 30 seconds. Process transcription async, respond immediately.
**Impact**: Restructured webhook handler to queue processing.

### YYYY-MM-DD: Speaker diarization accuracy
**Context**: [Describe situation]
**Learning**: Diarization works best with clear audio and distinct speakers. Background noise confuses it.
**Impact**: Added audio quality recommendations to documentation.

---

## AI/RAG

### YYYY-MM-DD: Chunk size matters
**Context**: [Describe situation]
**Learning**: Smaller chunks (256 tokens) gave better retrieval precision than larger (1024). But too small loses context.
**Impact**: Settled on 512 tokens with 50 token overlap.

### YYYY-MM-DD: Citation format for therapy
**Context**: [Describe situation]
**Learning**: Patients prefer "In your session on [date]..." over technical citation format.
**Impact**: Customized RAG output template.

---

## Security/HIPAA

### YYYY-MM-DD: Audit trail immutability
**Context**: [Describe situation]
**Learning**: Consent records must be append-only. Use soft deletes or versioning, never UPDATE/DELETE.
**Impact**: Added database constraints preventing consent modification.

### YYYY-MM-DD: PHI in error messages
**Context**: [Describe situation]
**Learning**: Exceptions were leaking patient data in stack traces. Need to sanitize all error outputs.
**Impact**: Added exception handler that strips PHI before logging.

---

## Performance

### YYYY-MM-DD: [Title]
**Context**: [Describe situation]
**Learning**: [What you learned]
**Impact**: [How it changed the project]

---

## Testing

### YYYY-MM-DD: [Title]
**Context**: [Describe situation]
**Learning**: [What you learned]
**Impact**: [How it changed the project]

---

## Template

<!--
### YYYY-MM-DD: Brief title
**Context**: What were you trying to do?
**Learning**: What did you discover?
**Impact**: How did this change the project?
-->
