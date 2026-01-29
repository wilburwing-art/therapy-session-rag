# PROMPT_plan.md - Planning Mode

You are an AI developer working on the TherapyRAG project. Your task is to create or update the implementation plan.

## Instructions

1. **Read the specification**: Study `specs/SPEC.md` thoroughly to understand all requirements and acceptance criteria.

2. **Analyze current state**: Look at the existing codebase to understand what has been implemented.

3. **Create/Update the plan**: Generate `IMPLEMENTATION_PLAN.md` with a prioritized task list.

## Planning Rules

- **One task = one commit**: Each task should be completable in a single iteration
- **Tasks are atomic**: A task either fully works or doesn't (testable)
- **Dependencies first**: Order tasks so dependencies are built before dependents
- **Tests included**: Each implementation task includes writing its tests
- **Small scope**: If a task feels too big, break it into smaller tasks

## Task Format

Each task should follow this format:

```markdown
### Task X.Y: [Short Title]

**Status**: [ ] Not Started / [~] In Progress / [x] Complete

**Description**: What needs to be built

**Acceptance Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2

**Files to Create/Modify**:
- path/to/file.py

**Tests Required**:
- test_something.py: test case description

**Dependencies**: Task X.Z (if any)
```

## Phase Structure

Organize tasks into these phases:

1. **Phase 1: Foundation** - Project setup, database models, basic structure
2. **Phase 2: Consent & Auth** - Consent service, API keys, authentication
3. **Phase 3: Recording Ingestion** - Upload handling, storage, session management
4. **Phase 4: Transcription Pipeline** - Queue, workers, Deepgram integration
5. **Phase 5: Embedding Pipeline** - Chunking, embeddings, vector storage
6. **Phase 6: RAG Chatbot** - Retrieval, Claude integration, chat API
7. **Phase 7: Polish** - Error handling, logging, documentation

## Output

After analyzing, create or update `IMPLEMENTATION_PLAN.md` with the full task breakdown.

When complete, output: `<promise>PLAN_COMPLETE</promise>`
