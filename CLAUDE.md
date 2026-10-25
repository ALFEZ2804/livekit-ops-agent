# Contributor Guide

## Project

A Python voice operations agent built with LiveKit Agents. It looks up fictional shipment records, answers delivery procedure questions from a local corpus, and reports per-turn metrics.

## Development

- Python 3.12 is selected by .python-version.
- Use uv for dependency and environment management.
- Application code: src/ops_agent/.
- Tests: tests/.
- Shipment examples: data/shipments.json.
- Retrieval documents: data/docs/.

## Commands

~~~powershell
uv sync
uv run ops-agent download-files
uv run ops-agent console
uv run pytest
uv run ruff check .
uv run mypy
~~~

The console workflow requires provider credentials in a local .env. Model-backed evaluations use Anthropic when its key is available; deterministic tests can run without provider calls.

## Configuration and data

Copy .env.example to .env and fill only the credentials needed for the selected workflow. Never commit .env, provider secrets, or downloaded model files. Keep all shipment and policy examples fictional.

The console workflow is the current implemented path. LiveKit Cloud worker modes are documented but still need a manual end-to-end check with cloud credentials.
