# Lint and type check

Run linting and type checking, fix issues.

## Steps

1. Run Ruff linter:
```bash
uv run ruff check src/ tests/
```

2. If issues found, auto-fix:
```bash
uv run ruff check src/ tests/ --fix
```

3. Run mypy:
```bash
uv run mypy src/
```

4. Report any remaining issues that need manual attention.
