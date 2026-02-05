#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/../dbt_project"

echo "=== dbt Analytics Pipeline ==="
echo "Project dir: $PROJECT_DIR"
echo ""

cd "$PROJECT_DIR"

# Install dbt packages if not present
if [ ! -d "dbt_packages" ]; then
    echo "--- Installing dbt packages ---"
    dbt deps
    echo ""
fi

# Run seeds first (dim_time_seed)
echo "--- Loading seeds ---"
dbt seed
echo ""

# Run snapshots (consent SCD Type 2)
echo "--- Running snapshots ---"
dbt snapshot
echo ""

# Run all models (staging → marts)
echo "--- Running models ---"
dbt run
echo ""

# Run tests
echo "--- Running tests ---"
dbt test
echo ""

# Generate docs
echo "--- Generating docs ---"
dbt docs generate
echo ""

echo "=== dbt pipeline complete ==="
echo "View docs: dbt docs serve --project-dir $PROJECT_DIR"
