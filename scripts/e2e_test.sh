#!/bin/bash
# End-to-end test script for therapy-session-rag
# Used as the success criteria for Ralph Wiggum loops
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo_step() {
    echo -e "${YELLOW}=== $1 ===${NC}"
}

echo_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

echo_fail() {
    echo -e "${RED}✗ $1${NC}"
}

# Track failures
FAILURES=0

run_check() {
    local name="$1"
    shift
    echo_step "$name"
    if "$@"; then
        echo_success "$name passed"
    else
        echo_fail "$name failed"
        FAILURES=$((FAILURES + 1))
    fi
    echo ""
}

# 1. Lint check (fast, catches obvious issues)
run_check "Ruff Lint" uv run ruff check src/ tests/

# 2. Type checking
run_check "MyPy Type Check" uv run mypy src/ --ignore-missing-imports

# 3. Unit tests
run_check "Unit Tests" uv run pytest tests/unit -v --tb=short -q 2>/dev/null || uv run pytest tests/ -v --tb=short -q --ignore=tests/integration

# 4. Integration tests (only if services are running)
if docker compose ps 2>/dev/null | grep -q "running"; then
    run_check "Integration Tests" uv run pytest tests/integration -v --tb=short -q
else
    echo_step "Integration Tests"
    echo -e "${YELLOW}⚠ Skipped (docker services not running)${NC}"
    echo ""
fi

# Summary
echo_step "Summary"
if [ $FAILURES -eq 0 ]; then
    echo_success "All checks passed!"
    exit 0
else
    echo_fail "$FAILURES check(s) failed"
    exit 1
fi
