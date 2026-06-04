# AGENTS.md

## Scope
- This file applies to the entire repository.
- If a deeper `AGENTS.md` is added later, the deeper file takes precedence for its subtree.

## Project Summary
- `LNAgent` is a Python CLI agent for light-novel creation.
- The main runtime entry is `main.py`; it opens or creates a novel project with `--project`.
- Runtime state is persisted under `projects/<project_id>/` by default.
- The current product shape is a multi-turn CLI workflow with explicit author control over adopt / scene-switch actions.

## Environment
- Python version: `>=3.10, <4.0`; repository docs recommend `3.12`.
- Dependencies are defined in `requirements.txt`.
- Setup scripts:
  - macOS / Linux: `scripts/init-env.sh`
  - Windows PowerShell: `scripts/init-env.ps1`
- Required environment variable:
  - `API_KEY`
- Optional environment variables:
  - `MODEL` (default: `gpt-4o-mini`)
  - `API_BASE_URL`
  - `LNAGENT_PROJECTS_DIR` (overrides the default `projects/` directory)

## Common Commands
- Install dependencies: `pip install -r requirements.txt`
- Start the CLI: `python main.py --project <project_id>`
- Start with initial meta JSON: `python main.py --project <project_id> --meta path/to/meta.json`
- Run tests: `python -m unittest`
- Run the main regression file directly: `python -m unittest tests.test_memory_store`

## Repository Map
- `main.py` — CLI entry, argument parsing, interactive loop, command dispatch.
- `lnagent/config.py` — environment-based settings.
- `lnagent/llm.py` — chat model construction.
- `lnagent/session.py` — core multi-turn novel session orchestration.
- `lnagent/project.py` — project creation / loading.
- `lnagent/cli/` — explicit user commands such as `/adopt`, `/scene`, `/undo`, `/fix`, `/config`, `/export`.
- `lnagent/memory/` — JSON-backed memory system, Hot Canon, Cold Archive, context budget, scene switching.
- `tests/test_memory_store.py` — current main automated coverage.
- `docs/features/` — design documents, open questions, and phased implementation notes.

## Project Data Layout
- `projects/<id>/meta.json` — novel metadata.
- `projects/<id>/config.json` — project configuration.
- `projects/<id>/session.json` — current scene session state.
- `projects/<id>/memory/canon.json` — Hot Canon.
- `projects/<id>/memory/synopsis.json` — Cold Archive synopsis data.
- `projects/<id>/manuscript/scene_XXX.md` — adopted prose for each scene.

## Development Notes
- Preserve Chinese CLI output unless the task explicitly changes user-facing language.
- `--project` is required; `python main.py` alone is not a valid full startup command.
- Keep the explicit-author-control product rule unless a task says otherwise:
  - prose adoption is explicit (`/adopt`)
  - scene switching is explicit (`/scene`)
  - the agent may suggest, but should not silently auto-commit these actions
- Prefer minimal, backward-compatible changes to persisted JSON structures; existing tests cover many round-trip cases.
- Use the existing code style: type hints, small focused functions, `unittest`, and minimal changes.
- Do not manually edit generated project state under `projects/` unless the task is specifically about migration, repair, or fixture creation.
- Avoid committing or relying on generated files such as `.venv/`, `__pycache__/`, and `.DS_Store`.

## When Making Changes
- Read `README.md` first for the user-facing workflow.
- Read `docs/features/memory-architecture.md` before changing memory, session, canon, synopsis, or scene-switch behavior.
- If you change command parsing, session persistence, or memory schema, update or add tests in `tests/test_memory_store.py` or adjacent test files.