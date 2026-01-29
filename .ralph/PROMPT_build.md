# PROMPT_build.md - Build Mode

You are an AI developer working on the TherapyRAG project. Your task is to implement the next incomplete task from the implementation plan.

## Instructions

1. **Read the plan**: Open `IMPLEMENTATION_PLAN.md` and find the first task that is NOT marked `[x]` Complete.

2. **Understand the task**: Read the task description, acceptance criteria, and dependencies.

3. **Check dependencies**: Verify all dependency tasks are complete. If not, implement the dependency first.

4. **Implement the task**:
   - Write the code
   - Write the tests
   - Run validation (see AGENTS.md)
   - Fix any issues

5. **Validate your work** (REQUIRED before commit):
   ```bash
   ruff format src tests
   ruff check src tests --fix
   mypy src --strict
   pytest tests -v
   ```

6. **Commit when green**:
   ```bash
   git add .
   git commit -m "Task X.Y: [description]"
   ```

7. **Update the plan**: Mark the task as `[x]` Complete in `IMPLEMENTATION_PLAN.md`

8. **Exit**: After completing ONE task, exit so the loop can restart with fresh context.

## Rules

- **ONE task per iteration**: Complete exactly one task, then exit
- **Tests are mandatory**: No task is complete without passing tests
- **Validation must pass**: Do NOT commit if mypy or tests fail
- **Small commits**: Each commit should be a single logical change
- **Document blockers**: If stuck, add a note to the task and move to the next one

## Code Quality Standards

- Type hints on ALL functions (mypy strict)
- Docstrings on public functions
- No `# type: ignore` without explanation
- Pydantic models for all API request/response
- Async for all I/O operations
- Repository pattern for data access

## When Stuck

If you cannot complete a task after reasonable effort:
1. Document what you tried in the task notes
2. Mark it as `[!]` Blocked with explanation
3. Move to the next unblocked task
4. Continue

## Completion Check

After each task, check if ALL tasks in the plan are marked `[x]` Complete.

If ALL tasks are complete:
- Run full test suite one more time
- Verify all acceptance criteria in specs/SPEC.md
- Output: `<promise>BUILD_COMPLETE</promise>`

If tasks remain:
- Exit normally (the loop will restart and pick up the next task)
