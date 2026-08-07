# livekit-ops-agent

Agente de voz de operaciones para una empresa de logística ficticia, construido sobre
**LiveKit Agents 1.x**. Atiende una llamada por voz, consulta el estado de un envío con
una **tool** y responde preguntas de procedimiento con **RAG local** sobre documentación
interna. Todo el pipeline queda instrumentado con métricas por turno y cubierto por evals
automáticas.

Pipeline de voz: **STT** Deepgram · **LLM** Anthropic/Claude · **TTS** ElevenLabs ·
**VAD** Silero · **turn detector** local del plugin (con fallback a `turn_detection="stt"`).

> Fase 1 (este repo): corre **en local con `console`**, sin cuenta de LiveKit Cloud.
> Fase 2 (documentada abajo): worker en LiveKit Cloud vía `dev` / `start`.

---

## Requisitos

- **Windows** (probado en Windows 11), fuera de OneDrive para no sincronizar `.venv`.
- **[uv](https://docs.astral.sh/uv/)** como gestor de entorno y dependencias.
  Si no lo tienes: `pip install uv` (o el instalador oficial de Astral).
- **Python 3.12** — uv lo aprovisiona solo a partir de `.python-version` si falta.
- Un **micrófono y altavoz** para hablar con el agente en `console`.

## Arranque de cero

```powershell
# 1. Instalar dependencias exactas del lockfile y crear el .venv
uv sync

# 2. Configurar credenciales: copiar la plantilla y rellenar los valores
copy .env.example .env
#   -> edita .env con tus claves (ver "Variables de entorno")

# 3. Descargar los modelos locales (turn detector + Silero VAD).
#    La PRIMERA vez es obligatorio o el primer arranque falla al no encontrarlos.
uv run ops-agent download-files

# 4. Arrancar el agente en local (usa micrófono y altavoz)
uv run ops-agent console
```

## Subcomandos

El **mismo** `agent.py` sirve para los tres modos; solo cambia el subcomando y la
presencia de las variables `LIVEKIT_*`:

| Comando | Para qué | Necesita LiveKit Cloud |
| --- | --- | --- |
| `uv run ops-agent console` | Conversación local por micrófono/altavoz. Fase 1. | No |
| `uv run ops-agent dev` | Registra un worker contra LiveKit Cloud (hot-reload). Fase 2. | Sí |
| `uv run ops-agent start` | Igual que `dev` pero para producción (sin reload). Fase 2. | Sí |
| `uv run ops-agent download-files` | Descarga los modelos ONNX locales. Ejecutar una vez. | No |

## Variables de entorno

Los nombres son los **canónicos** que lee el código (`BaseSettings`). Están en
`.env.example`; el `.env` real está gitignored y **nunca** se commitea.

| Variable | Uso | Obligatoria en fase 1 |
| --- | --- | --- |
| `DEEPGRAM_API_KEY` | STT Deepgram. (En Karumi la var era `DEEPGRAM_KEY`; aquí el valor es el mismo, el nombre está normalizado.) | Sí |
| `ANTHROPIC_API_KEY` | LLM Claude. | Sí |
| `CLAUDE_MODEL` | Id de modelo Claude. Vacío = default de baja latencia del código. | No |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` / `ELEVENLABS_MODEL` | TTS ElevenLabs. | Sí |
| `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | Worker en LiveKit Cloud. Ausentes = degrada a `console`. | No (fase 2) |
| `SUPABASE_URL` / `SUPABASE_KEY` | Reservadas para la extensión RAG sobre pgvector. No usadas por el MVP. | No |

## Tests, lint y tipos

```powershell
uv run pytest          # evals + unit tests (sin audio real)
uv run ruff check .    # lint
uv run ruff format .   # formato
uv run mypy            # tipos (config en pyproject.toml)
```

## RAG local (sin key de embeddings de pago)

El corpus vive en `data/docs/*.md` y se indexa en memoria al arrancar. Hay dos
retrievers tras el mismo `Protocol`:

- **EmbeddingRetriever** (por defecto en runtime): `fastembed` (ONNX en CPU, sin torch),
  modelo multilingüe, similitud coseno con **abstención por umbral**.
- **Bm25Retriever** (CI / offline / fallback): determinista, sin red.

Si ninguna coincidencia supera el umbral, el retriever devuelve vacío y el agente
responde que **no lo sabe** en lugar de inventar.

---

## Fase 2 — LiveKit Cloud + despliegue en Railway (checklist manual)

No se ejecuta en fase 1. Requiere credenciales `LIVEKIT_*` reales.

1. Crear proyecto en LiveKit Cloud y generar una API key. Pegar `LIVEKIT_URL`,
   `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` en el `.env`.
2. `uv run ops-agent dev` → el agente se registra como worker y queda a la espera.
3. Desde el **Agent Playground** de LiveKit, entrar a una room: el agente se une y
   mantiene una conversación de voz real (saludo, tool de envíos, RAG, barge-in).
4. Comprobar en el **dashboard de observability** de LiveKit que aparecen el transcript
   y las métricas de la sesión.
5. **Despliegue en Railway** (proceso con estado, NO Vercel): el comando de arranque es
   `uv run ops-agent start`. Cargar las mismas variables de entorno en el servicio de
   Railway. Verificar el artefacto desplegado, no solo el build en verde.
