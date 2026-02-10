# Database migration

Create and run database migrations.

## Usage

If no argument provided, show current migration status.

If description provided, create new migration.

## Steps

1. Check current status:
```bash
uv run alembic current
uv run alembic history --verbose | head -20
```

2. If creating new migration:
```bash
uv run alembic revision --autogenerate -m "$ARGUMENTS"
```

3. Review the generated migration file for:
   - Unintended changes
   - Data loss risks
   - Missing indexes

4. Apply migration:
```bash
uv run alembic upgrade head
```

5. Verify:
```bash
uv run alembic current
```
