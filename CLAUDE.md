# livekit-ops-agent

## Qué es
Agente de voz de operaciones para una empresa de logística ficticia sobre **LiveKit
Agents 1.x**. Atiende una llamada por voz, consulta el estado de un envío con una tool y
responde preguntas de procedimiento con RAG local sobre docs internos. Instrumentado con
métricas por turno y cubierto por evals. Doble propósito: preparación para Karumi y base
para la take-home de HappyRobot. La fuente de verdad del alcance es `SPEC.md`.

## Stack
- **CPython 3.12** (requires-python `>=3.11`), gestionado con **uv** (`uv.lock` commiteado).
- Voz: **livekit-agents 1.6.8** con extras `[deepgram,anthropic,elevenlabs,silero,turn-detector]`
  (un solo paquete con extras, NO cinco `livekit-plugins-*` sueltos).
  STT Deepgram · LLM Anthropic/Claude · TTS ElevenLabs · VAD Silero · turn detector local.
- Config: **pydantic-settings 2.x** (`BaseSettings`) + **pydantic 2.x**. Logging:
  **structlog**. RAG: **fastembed** (ONNX CPU, sin torch) + **numpy**, con
  **rank-bm25** como fallback determinista.
- Lint/format: **ruff**. Tipos: **mypy** (estable, config en `pyproject.toml`).
- Despliegue: fase 1 `console` local. Fase 2 (documentada, no ejecutada) worker en
  LiveKit Cloud vía `dev`/`start`, alojado en **Railway** (proceso con estado; NO Vercel).

## Comandos
Todo pasa por `uv run` (el entorno lo gestiona uv, no el Anaconda base). En **PowerShell**,
no en Git Bash (ver Gotchas).
```powershell
uv sync                          # instala deps del lock y crea .venv
uv run ops-agent console         # arranca en local (mic/altavoz). Fase 1.
uv run ops-agent dev             # worker contra LiveKit Cloud (fase 2, necesita LIVEKIT_*)
uv run ops-agent start           # igual que dev, sin hot-reload (comando de arranque en Railway)
uv run ops-agent download-files  # descarga los modelos ONNX locales (una vez, ver Gotchas)
uv run pytest                    # evals + unit tests (sin audio)
uv run ruff check .              # lint
uv run ruff format .             # formato
uv run mypy                      # tipos (files = src, tests)
```

## Estructura
Solo lo no obvio:
- `src/ops_agent/agent.py` — **ÚNICA capa acoplada a LiveKit**: plugins, `OpsAgent`,
  `entrypoint(ctx)`, `AgentSession`, enganche de métricas, `main()->cli.run_app`. El
  mismo fichero corre en `console`/`dev`/`start` sin cambios de código.
- `src/ops_agent/config.py` — única frontera con el entorno (`Settings`). Las `LIVEKIT_*`
  son opcionales: si faltan, degrada a `console` sin fallar.
- `tools/shipments.py` y `rag/retriever.py` definen **Protocols**; el resto del código
  depende de la abstracción, no de la implementación. Hay dos retrievers tras el mismo
  Protocol: `EmbeddingRetriever` (fastembed, runtime) y `Bm25Retriever` (offline/CI/fallback).
- `data/` es contenido, no código: `shipments.json` (dataset fijo) y `docs/*.md` (corpus RAG).

Estado actual: **MVP completo (fase 1)**. Hechos: `agent.py` (plugins + `OpsAgent` **con las
tres tools registradas** + `AgentSession` con `AgentDeps` como `userdata` + `_build_deps`
[EmbeddingRetriever por defecto, fallback a BM25 logueado] + saludo + preflight), `prompts.py`,
`observability/metrics.py` (`MetricsReporter`: línea `turn` por turno con latencias
STT/LLM/TTS y tokens + resumen al cierre), el dominio de envíos (`tools/shipments.py`) y el
RAG local (`rag/index.py` chunking por sección + `rag/retriever.py` con `EmbeddingRetriever`
fastembed por defecto y `Bm25Retriever` determinista tras el `Retriever` Protocol; abstención
por umbral vía `select_relevant`), las tres `@function_tool` (`lookup_shipment` / `search_docs`
/ `end_call` en `tools/agent_tools.py`) y `deps.AgentDeps` (`shipments` + `retriever` +
`settings`). `console` arranca la ida y vuelta STT→LLM→TTS con tools + RAG operativos.

Evals (`session.run` + `expect().judge`) en `conftest.py` + `test_uses_tool.py` /
`test_rag_answers.py` / `test_no_hallucination.py`: ejercitan el `OpsAgent` real en **modo
texto sin audio** (fixture `session`), con `AgentDeps` deterministas (dataset fijo +
`Bm25Retriever` offline) y asserts deterministas (tool llamada, campos exactos) junto a los
juzgados. Helpers de eventos en `tests/evalutils.py`. Usan el LLM real de Anthropic: si
`ANTHROPIC_API_KEY` no tiene valor en el `.env`, las evals se **saltan** (no fallan) para que
`uv run pytest` quede verde en CI/headless; con la clave puesta, corren y juzgan de verdad.

## Flujo de trabajo obligatorio
Aplícalo sin que Alberto lo pida. Trabaja solo y sin revisión humana.

### 1. Antes de escribir código — planificar
- Cambio que toca más de un fichero o introduce un concepto nuevo: modo plan antes de
  editar. Fixes de una línea: directos.

### 2. Antes de implementar una utilidad — comprobar que no existe ya
- Antes de escribir retries, parseo, validación, chunking, similitud, etc.: aplica
  `managing-dependencies`. Nunca cites un paquete sin verificar que existe y su versión.
- **Los símbolos de la API de livekit-agents (`AgentSession`, `@function_tool`,
  `cli.run_app`, `MetricsCollectedEvent`, `session.run`/`expect().judge`) se verifican
  contra la versión instalada (1.6.8) vía `context7`/introspección — NUNCA de memoria.**
  La API 1.x se mueve rápido.

### 3. Al escribir — el estándar de calidad
- Aplica la skill **`python-clean-async`**: tipos en las fronteras, errores propagados con
  contexto (nada de `except: pass`), **timeout explícito en toda llamada de red**, sin
  credenciales en el código.
- Debe quedar limpio: `uv run ruff check . && uv run mypy && uv run pytest` sin errores.

### 4. Antes de cada commit — revisión con contexto frío
- `/review-pr` sobre el `git diff` (funciona sin PR). Mínimo `silent-failure-hunter` y
  `code-reviewer`; si tocaste tipos o tests, añade `type-design-analyzer` y `pr-test-analyzer`.
- Si algo "debería funcionar y no funciona", usa `fresh-eyes-review`.
- **Verifica el artefacto, no solo el código**: tras cambiar `agent.py`, arranca de verdad
  `uv run ops-agent console` y mira que responde lo nuevo. Un build en verde puede seguir
  sirviendo lo viejo.
- Si el cambio movió ficheros, cambió el stack, añadió comandos o dejó código muerto,
  actualiza este CLAUDE.md en el **mismo commit**.
- **Pregunta antes de `git commit` y antes de `git push`.** Sin excepción.
- En los commits para Alberto, **NO** añadas `Co-Authored-By: Claude` ni atribución a IA.
  Mensajes en español.

## Gotchas
- **`uv` no venía instalado.** Se instaló con `pip install uv` (está en
  `C:\Users\ALBERTO\anaconda3\Scripts\uv.exe`). **Git Bash NO lo ve en PATH**; usa
  PowerShell (o la ruta completa) para cualquier comando `uv`.
- **`console` está deprecated en livekit-agents 1.6.8** (sugiere `lk agent console`). La
  SPEC exige `uv run ops-agent console` y funciona bien: es un WARNING, no un error. **No**
  migres a `lk agent console`.
- **Modelos ONNX locales**: el turn detector y Silero VAD descargan modelos la primera vez.
  Antes del primer `console` con sesión real hay que correr `uv run ops-agent download-files`
  o el arranque falla al no encontrarlos. Los `.onnx` están gitignored.
- **Modelo de embeddings del RAG (fastembed)**: `EmbeddingRetriever` descarga
  `paraphrase-multilingual-MiniLM-L12-v2` (ONNX) la primera vez que se construye; sin red
  falla, por eso CI y el test determinista (`test_retriever.py`) van sobre `Bm25Retriever` y
  el caso de embeddings se **salta** si el modelo no está cacheado. La caché por defecto de
  fastembed cae en un dir temporal; el wiring de runtime puede fijar `cache_dir` a una ruta
  estable (caché gitignored). El umbral de coseno de abstención está calibrado en
  `DEFAULT_EMBEDDING_MIN_SCORE = 0.30` (cubiertas >~0.40, fuera de dominio <~0.14).
- **Claves del `.env`**: hoy el `.env` tiene las `LIVEKIT_*` rellenas pero **Deepgram,
  Anthropic y ElevenLabs VACÍAS** (incluidos `ELEVENLABS_VOICE_ID`/`ELEVENLABS_MODEL`).
  Ya no es inocuo: el `entrypoint` construye el pipeline, y un preflight
  (`_check_phase1_credentials`) **falla al arrancar con un `RuntimeError` que nombra las
  claves vacías** antes de que el plugin reviente con un error opaco. Para un `console` en
  vivo, Alberto debe pegar esas claves (valores de `demo-pilot`). Nota: `Settings` acepta
  cadenas vacías en campos requeridos (son `str` válidos); por eso el preflight vive en
  `agent.py` y no en la validación de `config.py`.
- **Deepgram, doble nombre**: el canónico es `DEEPGRAM_API_KEY`; el código acepta
  `DEEPGRAM_KEY` como fallback (en Karumi la var se llamaba así).
- **hatchling** exige que exista `README.md` (campo `readme` del `pyproject.toml`) o el
  build del paquete falla. Layout `src/`: el paquete se declara en
  `[tool.hatch.build.targets.wheel] packages = ["src/ops_agent"]`.
- **mypy**: los overrides `ignore_missing_imports` de `livekit.*`/`fastembed.*`/`rank_bm25.*`
  cubren librerías sin stubs y no rompen el chequeo de nuestro código. numpy sí trae tipos
  (`numpy.typing.NDArray`), por eso las matrices del retriever van tipadas.

## No tocar
- `.env` — secretos reales, gitignored. Nunca lo commitees ni pegues sus valores en un chat.
- `SPEC.md` — fuente de verdad del alcance; no la reescribas al implementar.
- `uv.lock` — no lo edites a mano; se regenera con `uv lock` / `uv sync`.
- Modelos `*.onnx` descargados por los plugins — generados, gitignored.
