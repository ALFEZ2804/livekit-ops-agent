"""Métricas por turno a partir de los eventos del AgentSession.

Responsabilidad (fase de implementación):
    Handler de `MetricsCollectedEvent` + `UsageCollector` / `session.usage` que
    registra por turno en structlog: { turn_id, user_transcript, tool_calls,
    response, stt_ms, llm_ttft_ms, tts_ttfb_ms, tokens }.
    Punto de extensión a OpenTelemetry/Langfuse documentado (no implementado).

Andamiaje: sin implementar todavía.
"""
