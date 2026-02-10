# Error Documentation

Known issues and fixes for therapy-session-rag.

---

## Database

### "Connection refused" on tests
**Symptoms**: Tests fail with `ConnectionRefusedError`
**Cause**: PostgreSQL container not running
**Fix**:
```bash
docker compose up -d postgres
# Wait for healthy
docker compose ps
```

### "Target database is not up to date"
**Symptoms**: Alembic refuses to create migration
**Cause**: Pending migrations not applied
**Fix**:
```bash
uv run alembic upgrade head
```

### "Relation does not exist"
**Symptoms**: Query fails with missing table
**Cause**: Migrations not run after model change
**Fix**:
```bash
uv run alembic upgrade head
# If that fails, check migration history
uv run alembic history
```

### pgvector extension not found
**Symptoms**: `extension "vector" does not exist`
**Cause**: pgvector not installed in PostgreSQL
**Fix**:
```bash
# In docker-compose.yml, use pgvector image:
image: pgvector/pgvector:pg16
```

---

## API

### 401 Unauthorized on all requests
**Symptoms**: Every API call returns 401
**Cause**: Missing or invalid X-API-Key header
**Fix**:
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8000/api/v1/...
```

### 422 Validation Error
**Symptoms**: Request rejected with validation details
**Cause**: Request body doesn't match Pydantic schema
**Fix**: Check the `detail` field in response for specific field errors

### Rate limit exceeded
**Symptoms**: 429 Too Many Requests
**Cause**: Redis rate limiter triggered
**Fix**:
```bash
# Clear rate limit (dev only)
redis-cli DEL "rate_limit:patient:{patient_id}"
```

---

## Transcription

### Deepgram API error
**Symptoms**: Transcription job fails
**Cause**: Invalid API key or quota exceeded
**Fix**:
```bash
# Check API key in .env
DEEPGRAM_API_KEY=...

# Verify quota at https://console.deepgram.com
```

### Webhook timeout
**Symptoms**: Transcription starts but never completes
**Cause**: Webhook endpoint not responding within 30s
**Fix**: Ensure webhook acknowledges immediately, processes async

---

## Storage (MinIO/S3)

### "Bucket does not exist"
**Symptoms**: Upload fails with bucket error
**Cause**: MinIO bucket not created
**Fix**:
```bash
docker compose up -d minio-setup
# Or manually:
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/therapy-sessions
```

### Access denied
**Symptoms**: S3 operations fail with permission error
**Cause**: Incorrect credentials or bucket policy
**Fix**: Check `MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` in .env

---

## Tests

### Async test hanging
**Symptoms**: Test never completes
**Cause**: Missing `pytest-asyncio` marker or unclosed session
**Fix**:
```python
@pytest.mark.asyncio
async def test_something():
    ...
```

### Fixture not found
**Symptoms**: `fixture 'xyz' not found`
**Cause**: Missing conftest.py or incorrect import
**Fix**: Ensure fixture is in `conftest.py` or imported module

---

## Type Checking

### mypy "Cannot find module"
**Symptoms**: Import errors in mypy
**Cause**: Missing type stubs or incorrect config
**Fix**:
```bash
# Install stubs
uv add types-redis types-passlib

# Or add to pyproject.toml
[tool.mypy]
ignore_missing_imports = true
```

---

## Add your own errors below

<!-- Template:
### Error title
**Symptoms**: What you see
**Cause**: Why it happens
**Fix**:
```bash
commands to fix
```
-->
