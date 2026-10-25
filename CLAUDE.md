# Contributor guide

## Project
Voice operations agent built with LiveKit Agents. It handles shipment lookups, answers questions from a local document corpus, and reports per-turn metrics.

## Development
- Python 3.12 with `uv`.
- Application code: `src/ops_agent/`.
- Tests: `tests/`.
- Local shipment examples: `data/shipments.json`.
- RAG documents: `data/docs/*.md`.

## Commands
```powershell
uv sync
uv run ops-agent download-files
uv run ops-agent console
uv run pytest
uv run ruff check .
uv run mypy
```

The console agent needs provider credentials from a local `.env`. The test suite uses deterministic local fixtures; provider-backed evaluations run only when the Anthropic key is configured.

## Configuration and data
- Copy `.env.example` to `.env` and set credentials locally.
- Never commit `.env`, provider secrets, or downloaded model files.
- Keep examples and documentation free of real customer data.
- The console workflow is the implemented MVP. LiveKit Cloud `dev`/`start` support is documented but needs a manual end-to-end check with cloud credentials.
