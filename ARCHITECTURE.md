# Architecture and Design Notes

This document describes the implementation in the current repository. README.md is the source of truth for setup and supported commands.

## System overview

The project is a voice operations agent for a fictional logistics provider. A LiveKit AgentSession connects speech recognition, language generation, speech synthesis, voice activity detection, and turn detection. The agent can:

1. Look up a shipment in the local JSON repository.
2. Search a local corpus of delivery procedures and answer from retrieved passages.
3. End the call through a tool.

The application does not connect to a real logistics system or customer dataset.

## Runtime components

- **Agent:** src/ops_agent/agent.py builds the session, registers tools, injects dependencies, and reports metrics.
- **Configuration:** src/ops_agent/config.py validates provider settings and keeps secrets wrapped as secret values.
- **Tools:** src/ops_agent/tools/ contains shipment lookup and document search.
- **Retrieval:** src/ops_agent/rag/ loads markdown documents and exposes embedding and BM25 retrievers.
- **Observability:** src/ops_agent/observability/ records session and per-turn metrics.
- **Knowledge base:** data/docs/ contains fictional delivery policies.
- **Shipment data:** data/shipments.json contains fictional sample records.
- **Tests:** tests/ covers configuration, retrieval, shipment lookup, tool use, and refusal when evidence is missing.

## Retrieval behavior

The runtime retriever uses FastEmbed embeddings on CPU. Retrieved content is compared with a relevance threshold; low-relevance queries return no document so the agent can say it does not know. A deterministic BM25 retriever is used by tests and can act as a local fallback.

## Voice and model providers

The current pipeline uses Deepgram for STT, Anthropic Claude for the LLM, ElevenLabs for TTS, Silero for VAD, and LiveKit's multilingual turn detector. The provider keys are configured through .env; LiveKit Cloud credentials are not required for the console workflow.

## Evaluation and validation

The automated suite includes tests for shipment-tool usage, RAG-based answers, and unsupported questions. Model-backed evaluation tests call Anthropic when its key is configured; without that key they are skipped. Run the commands in README.md.

The LiveKit Cloud worker and Railway deployment workflow are documented as future/manual steps. They have not been verified as an end-to-end deployment.
