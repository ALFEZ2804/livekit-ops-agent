# Logistics Voice Agent

A voice operations agent for a fictional logistics company, built with LiveKit Agents. It looks up shipment status through a tool, answers delivery-policy questions using a local document corpus, and records per-turn metrics.

## Capabilities

- **Shipment lookup:** retrieves status, location, and estimated delivery from a local JSON dataset.
- **Grounded procedure answers:** searches local markdown policies and answers from retrieved content; the retriever can abstain when relevance is below its threshold.
- **Voice turn-taking:** Deepgram speech recognition, Anthropic Claude, ElevenLabs speech synthesis, Silero VAD, and the LiveKit multilingual turn detector.
- **Observability and evaluation:** reports per-turn metrics and includes automated tests for tool use, RAG answers, and unsupported questions.

## Architecture

The application is organized around the LiveKit AgentSession and an OpsAgent with three tools: shipment lookup, document search, and ending a call. Shipment records are read from data/shipments.json. The document corpus in data/docs is indexed at startup. Runtime retrieval uses local FastEmbed embeddings; BM25 provides a deterministic offline retriever for tests and fallback use.

The local console mode is the implemented development path. LiveKit Cloud worker modes are documented, but still require a manual end-to-end check with cloud credentials.

## Requirements

- Python 3.12 (selected by .python-version)
- uv
- A microphone and speakers or headphones
- Provider API credentials for the local voice pipeline

## Run locally

~~~powershell
uv sync
Copy-Item .env.example .env
~~~

Add values for DEEPGRAM_API_KEY, ANTHROPIC_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, and ELEVENLABS_MODEL to .env. CLAUDE_MODEL is optional and defaults to a low-latency model.

Download the local voice models once, then start the console agent:

~~~powershell
uv run ops-agent download-files
uv run ops-agent console
~~~

The first command downloads the local VAD and turn-detection models. The console mode uses your microphone and speakers.

## Tests and code quality

~~~powershell
uv run pytest
uv run ruff check .
uv run ruff format .
uv run mypy
~~~

The automated evaluation tests use Anthropic when a key is available and are skipped when it is not. The RAG tests use deterministic BM25 retrieval, so they do not need embedding downloads.

## Configuration

- DEEPGRAM_API_KEY is the canonical setting; DEEPGRAM_KEY is accepted as a legacy alias.
- LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET are only needed for the documented LiveKit Cloud worker path.
- SUPABASE_URL and SUPABASE_KEY are reserved for a possible future extension and are not used by the current MVP.
- Keep real credentials in .env. Never commit .env or provider secrets.

## Current scope

The logistics company and shipment records are fictional. This repository does not include a production deployment or a customer-facing web interface. LiveKit Cloud and Railway steps are not presented as completed deployments.
