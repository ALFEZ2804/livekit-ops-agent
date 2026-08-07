"""Configuración de la aplicación: única frontera con el entorno.

Responsabilidad (fase de implementación):
    `Settings(BaseSettings)` que lee del `.env` los nombres CANÓNICOS exactos:
    DEEPGRAM_API_KEY (con fallback defensivo a DEEPGRAM_KEY), ANTHROPIC_API_KEY,
    CLAUDE_MODEL (default de baja latencia en código), ELEVENLABS_API_KEY/_VOICE_ID/
    _MODEL, LIVEKIT_URL/_API_KEY/_API_SECRET (Optional -> degrada a console mode),
    SUPABASE_URL/_KEY (Optional, no usados por el MVP).

Andamiaje: sin implementar todavía.
"""
