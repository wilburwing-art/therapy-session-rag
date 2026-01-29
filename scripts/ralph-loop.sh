#!/bin/bash

# ralph-loop.sh - Autonomous AI coding loop
# Usage: ./scripts/ralph-loop.sh [plan|build]
# 
# Based on Geoffrey Huntley's Ralph Wiggum technique:
# "A bash loop that feeds an AI's output back into itself until it dreams up the correct answer."

set -e

MODE="${1:-build}"
MAX_ITERATIONS="${MAX_ITERATIONS:-50}"
ITERATION=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[ralph]${NC} $1"
}

success() {
    echo -e "${GREEN}[ralph]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[ralph]${NC} $1"
}

error() {
    echo -e "${RED}[ralph]${NC} $1"
}

# Determine which prompt to use
if [ "$MODE" = "plan" ]; then
    PROMPT_FILE=".ralph/PROMPT_plan.md"
    COMPLETION_MARKER="PLAN_COMPLETE"
    log "Starting PLANNING mode..."
elif [ "$MODE" = "build" ]; then
    PROMPT_FILE=".ralph/PROMPT_build.md"
    COMPLETION_MARKER="BUILD_COMPLETE"
    log "Starting BUILD mode..."
else
    error "Unknown mode: $MODE"
    echo "Usage: $0 [plan|build]"
    exit 1
fi

# Check prompt file exists
if [ ! -f "$PROMPT_FILE" ]; then
    error "Prompt file not found: $PROMPT_FILE"
    exit 1
fi

log "Max iterations: $MAX_ITERATIONS"
log "Completion marker: <promise>$COMPLETION_MARKER</promise>"
echo ""

# The loop
while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Iteration $ITERATION / $MAX_ITERATIONS"
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Run Claude Code with the prompt
    # Capture output to check for completion marker
    OUTPUT=$(cat "$PROMPT_FILE" | claude -p 2>&1) || true
    
    # Print the output
    echo "$OUTPUT"
    echo ""
    
    # Check for completion
    if echo "$OUTPUT" | grep -q "<promise>$COMPLETION_MARKER</promise>"; then
        success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        success "🎉 COMPLETE after $ITERATION iterations!"
        success "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        exit 0
    fi
    
    # Brief pause between iterations
    sleep 2
done

warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
warn "Max iterations ($MAX_ITERATIONS) reached without completion"
warn "Check IMPLEMENTATION_PLAN.md for progress"
warn "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
exit 1
