"""Unit: carga de config y redacción de secretos en logging.

Tests herméticos: se limpian todas las variables canónicas y se construye con
``Settings(_env_file=None)`` para no depender del `.env` real de la máquina. Cubren:
carga de nombres canónicos, mapeo dual de Deepgram (DEEPGRAM_API_KEY / DEEPGRAM_KEY),
default de CLAUDE_MODEL, degradación a console sin las LIVEKIT_*, y la redacción de
secretos del logging.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ops_agent.config import DEFAULT_CLAUDE_MODEL, Settings
from ops_agent.logging import redact_event

# Todas las variables que la config lee; se borran antes de cada test para aislar del
# entorno real de la máquina y del `.env` del proyecto.
_ALL_VARS = (
    "DEEPGRAM_API_KEY",
    "DEEPGRAM_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
    "ELEVENLABS_MODEL",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "SUPABASE_URL",
    "SUPABASE_KEY",
)

# Mínimo para que la config valide (las tres claves requeridas + los campos de ElevenLabs).
_BASE_ENV = {
    "DEEPGRAM_API_KEY": "dg-canonical",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "ELEVENLABS_API_KEY": "el-test",
    "ELEVENLABS_VOICE_ID": "voice-123",
    "ELEVENLABS_MODEL": "eleven_flash_v2_5",
}


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Borra todas las variables canónicas antes del test (aislamiento)."""
    for var in _ALL_VARS:
        monkeypatch.delenv(var, raising=False)


def _set(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)


def test_loads_canonical_names(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, _BASE_ENV)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.deepgram_api_key.get_secret_value() == "dg-canonical"
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test"
    assert settings.elevenlabs_api_key.get_secret_value() == "el-test"
    assert settings.elevenlabs_voice_id == "voice-123"
    assert settings.elevenlabs_model == "eleven_flash_v2_5"


def test_deepgram_fallback_to_karumi_name(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {k: v for k, v in _BASE_ENV.items() if k != "DEEPGRAM_API_KEY"}
    env["DEEPGRAM_KEY"] = "dg-from-karumi"
    _set(monkeypatch, env)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.deepgram_api_key.get_secret_value() == "dg-from-karumi"


def test_deepgram_canonical_wins_over_fallback(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set(monkeypatch, {**_BASE_ENV, "DEEPGRAM_KEY": "dg-from-karumi"})
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.deepgram_api_key.get_secret_value() == "dg-canonical"


def test_claude_model_default_when_absent(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, _BASE_ENV)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.claude_model == DEFAULT_CLAUDE_MODEL


def test_claude_model_default_when_blank(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, {**_BASE_ENV, "CLAUDE_MODEL": "   "})
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.claude_model == DEFAULT_CLAUDE_MODEL


def test_claude_model_override_is_honored(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, {**_BASE_ENV, "CLAUDE_MODEL": "claude-sonnet-5"})
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.claude_model == "claude-sonnet-5"


def test_degrades_to_console_without_livekit(
    clean_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set(monkeypatch, _BASE_ENV)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.livekit_url is None
    assert settings.livekit_api_key is None
    assert settings.livekit_api_secret is None
    assert settings.livekit_ready is False


def test_livekit_ready_when_all_present(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(
        monkeypatch,
        {
            **_BASE_ENV,
            "LIVEKIT_URL": "wss://example.livekit.cloud",
            "LIVEKIT_API_KEY": "lk-key",
            "LIVEKIT_API_SECRET": "lk-secret",
        },
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.livekit_ready is True
    assert settings.livekit_url == "wss://example.livekit.cloud"


def test_blank_livekit_values_degrade(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(
        monkeypatch,
        {**_BASE_ENV, "LIVEKIT_URL": "", "LIVEKIT_API_KEY": "  ", "LIVEKIT_API_SECRET": ""},
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.livekit_url is None
    assert settings.livekit_ready is False


def test_missing_required_key_fails_loud(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {k: v for k, v in _BASE_ENV.items() if k != "ANTHROPIC_API_KEY"}
    _set(monkeypatch, env)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_repr_does_not_leak_secrets(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _set(monkeypatch, _BASE_ENV)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert "dg-canonical" not in repr(settings)
    assert "sk-ant-test" not in repr(settings)


# --- Redacción de secretos en logging ------------------------------------------------


def test_redacts_by_field_name() -> None:
    redacted = redact_event({"deepgram_api_key": "dg-canonical", "turn_id": 3})
    assert redacted["deepgram_api_key"] == "«redacted»"
    assert redacted["turn_id"] == 3  # los no-secretos se conservan


def test_redacts_secretstr_values() -> None:
    from pydantic import SecretStr

    redacted = redact_event({"payload": SecretStr("hidden")})
    assert redacted["payload"] == "«redacted»"
    assert "hidden" not in str(redacted)
