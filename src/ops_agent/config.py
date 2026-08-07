"""Configuración de la aplicación: única frontera con el entorno.

`Settings(BaseSettings)` lee del `.env` los nombres CANÓNICOS exactos (los mismos que
espera cada plugin de LiveKit) y no deja que ninguna otra parte del código toque
`os.environ`. Decisiones que fija esta capa:

- **Dual Deepgram**: el nombre canónico es ``DEEPGRAM_API_KEY``; se acepta ``DEEPGRAM_KEY``
  como fallback defensivo (en el `demo-pilot` de Karumi la variable se llamaba así).
- **Degradación a console**: las ``LIVEKIT_*`` son opcionales. Si faltan (o vienen
  vacías), quedan en ``None`` y el agente corre en `console` sin fallar; su presencia no
  fuerza `dev`/`start` — eso lo decide el subcomando de la CLI.
- **Secretos**: las claves son ``SecretStr`` para que ni un `repr` ni un log accidental
  las filtren. El valor crudo solo se extrae con ``.get_secret_value()`` al pasarlo
  explícitamente a cada plugin.
"""

from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default de latencia baja (verificado activo: 200K ctx, el Claude más rápido). Se puede
# sobreescribir con CLAUDE_MODEL (p. ej. claude-sonnet-5) sin tocar código.
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"


class Settings(BaseSettings):
    """Configuración tipada cargada desde el entorno / `.env`.

    Instanciar sin argumentos en la app (lee `.env` + variables de entorno). En tests se
    pasa ``Settings(_env_file=None)`` para aislarse del `.env` real y controlar el entorno
    con ``monkeypatch``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- STT: Deepgram -------------------------------------------------------------
    deepgram_api_key: SecretStr = Field(
        validation_alias=AliasChoices("DEEPGRAM_API_KEY", "DEEPGRAM_KEY"),
    )

    # --- LLM: Anthropic ------------------------------------------------------------
    anthropic_api_key: SecretStr
    claude_model: str = DEFAULT_CLAUDE_MODEL

    # --- TTS: ElevenLabs -----------------------------------------------------------
    elevenlabs_api_key: SecretStr
    elevenlabs_voice_id: str
    elevenlabs_model: str

    # --- LiveKit Cloud (fase 2) — opcionales: ausentes => degrada a console --------
    livekit_url: str | None = None
    livekit_api_key: SecretStr | None = None
    livekit_api_secret: SecretStr | None = None

    # --- Supabase (opcional, reservado; no usado por el MVP) -----------------------
    supabase_url: str | None = None
    supabase_key: SecretStr | None = None

    @field_validator("claude_model", mode="before")
    @classmethod
    def _model_default_if_blank(cls, value: object) -> object:
        """``CLAUDE_MODEL`` vacío en el `.env` => usar el default de baja latencia."""
        if isinstance(value, str) and not value.strip():
            return DEFAULT_CLAUDE_MODEL
        return value

    @field_validator(
        "livekit_url",
        "livekit_api_key",
        "livekit_api_secret",
        "supabase_url",
        "supabase_key",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """Un valor vacío en un opcional es "ausente": normaliza "" -> None.

        Evita pasar cadenas vacías a LiveKit y hace fiable el chequeo ``is None``.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def livekit_ready(self) -> bool:
        """True solo si las tres ``LIVEKIT_*`` están; si no, el agente degrada a console."""
        return (
            self.livekit_url is not None
            and self.livekit_api_key is not None
            and self.livekit_api_secret is not None
        )
