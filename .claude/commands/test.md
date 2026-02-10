# Run test suite

Run the test suite and report results.

## Steps

1. Run unit tests:
```bash
uv run pytest tests/unit -v --tb=short
```

2. If unit tests pass, run integration tests:
```bash
uv run pytest tests/integration -v --tb=short
```

3. Report summary:
   - Total tests run
   - Passed/failed counts
   - Any failures with brief explanation

4. If failures, suggest fixes based on error messages.
