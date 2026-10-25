# SPEC — Agente de voz de operaciones (LiveKit Agents)

## 0. Metadatos

- **Proyecto:** `livekit-ops-agent`
- **Entorno:** Windows 11, Python 3.12 y `uv`.
- **Fecha:** 2026-08-07
- **Autor:** Alberto
- **Propósito:** proyecto personal de portfolio sobre agentes de voz aplicados a operaciones.

## 1. Objetivo

Construir un **agente de voz end-to-end con LiveKit Agents** que atienda una llamada de
operaciones de una empresa de logística ficticia: entiende al usuario por voz, consulta
el estado de un envío mediante una **tool**, y responde preguntas de procedimiento
apoyándose en **RAG** sobre documentación interna. Todo el pipeline queda
**instrumentado con métricas** y cubierto por **≥3 evals automáticas**.

El agente debe correr y evaluarse **hoy, en local**, con las credenciales que Alberto ya
tiene, sin depender de una cuenta de LiveKit Cloud.

## 2. Contexto y motivación

El proyecto explora patrones de agentes de voz para operaciones logísticas: consultas mediante herramientas, respuestas basadas en documentación, evaluaciones automatizadas y observabilidad. Las credenciales de los proveedores se configuran localmente en `.env`, que está excluido de Git.

La primera fase se desarrolla y evalúa en modo `console`; la integración con LiveKit Cloud se describe como una fase posterior.

## 3. Alcance funcional

El agente ("operador de voz") simula el soporte de operaciones de una empresa de
logística ficticia. Comportamientos:

1. **Saludo e inicio de sesión de voz**: al arrancar, saluda y ofrece ayuda.
2. **Consulta de envíos (tool)**: ante "¿dónde está el envío SHP-1024?" el agente llama
   a una tool `lookup_shipment(shipment_id)` que devuelve `estado`, `ubicación`, `ETA`.
   Los datos son un conjunto fijo conocido (mock JSON o tabla Supabase — lo decide el
   diseño).
3. **Preguntas de procedimiento (RAG)**: ante "¿cuál es la política de entregas
   fallidas?" o "¿cómo reprogramo una entrega?" recupera de un pequeño corpus de docs
   internos (markdown) y responde **basándose en el contenido recuperado**; si la
   pregunta cae fuera del corpus, dice que no lo sabe en lugar de inventar.
4. **Turn-taking / barge-in**: maneja turnos e interrupciones con VAD + turn detector;
   si el usuario habla mientras el agente responde, el agente se detiene y atiende.
5. **Cierre**: se despide (opcionalmente una tool `end_call`).

## 4. Restricciones y entorno

- **Sistema:** Windows 11.
  OneDrive (evita que se sincronice `.venv`).
- **Toolchain**: Python 3.11+ gestionado con **uv** (`uv.lock` commiteado), **ruff**
  (lint+format), **mypy** (o `ty`) en el código de aplicación.
- **Ejecución y evals**: **console mode** (`uv run <agente> console`) — sin credenciales
  de LiveKit Cloud. El framework de tests corre sin audio real.
- **Plugins directos**, NO LiveKit Inference: se usan las API keys propias
  (`livekit-plugins-deepgram/anthropic/elevenlabs/silero`), no el gateway cloud de
  LiveKit.
- **Credenciales**: el **`.env` ya existe** en el root con los nombres **canónicos**
  que el código debe leer **exactamente** (vía `BaseSettings`). No los renombres ni
  asumas otros:
  - LiveKit (fase 2): `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`.
  - STT: `DEEPGRAM_API_KEY` (¡ojo!, en  la var se llama `DEEPGRAM_KEY`; aquí es
    `DEEPGRAM_API_KEY` — Alberto copia el valor, el nombre ya está normalizado).
  - LLM: `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (opcional; default de latencia baja en el
    código si viene vacío).
  - TTS: `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL`.
  - RAG (opcional): `SUPABASE_URL`, `SUPABASE_KEY`.
  - El `.env` está **gitignored**; genera un `.env.example` alineado con estos nombres.
    **Cero secretos en el código o en git.**
- **Doble modo desde el diseño**: el **mismo** `agent.py` debe correr en `console`
  (fase 1, sin credenciales) y en `dev`/`start` (fase 2, con LiveKit Cloud) **sin
  cambios de código** — solo cambia el subcomando y la presencia de las `LIVEKIT_*`. La
  config carga `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` si están, y no
  falla si no están (degrada a console).

## 5. Stack

**Fijado:**
- **LiveKit Agents v1.x**: `livekit-agents` + plugins `deepgram`, `anthropic`,
  `elevenlabs`, `silero`, `turn-detector`.
- **STT** Deepgram · **LLM** Anthropic/Claude · **TTS** ElevenLabs · **VAD** Silero ·
  **turn detector** (modelo local del plugin, o `turn_detection="stt"`).
- **Config** con pydantic `BaseSettings`; **logging** con `structlog`; **retries** en
  llamadas de red flaky con `tenacity`.

**A decidir por el diseño (justificando la elección):**
- Modelo Claude concreto: **priorizar latencia** (un modelo rápido tipo *sonnet*, no
  *opus* — opus penaliza el turn-taking). Verificar el id de modelo real contra la API
  antes de fijarlo.
- **Motor RAG**: Supabase/pgvector (hay `SUPABASE_URL`) vs índice local. **Restricción:
  no hay key de embeddings de pago (ni OpenAI ni Voyage)** → optar por **embeddings
  locales** (p.ej. `fastembed`/`sentence-transformers`) o retrieval por keyword/BM25
  sobre el corpus pequeño. Que el diseño elija y lo justifique.
- Fuente de datos de envíos: mock JSON vs tabla Supabase.
- Estructura de carpetas y límites entre módulos (agente / tools / rag / config /
  observabilidad / evals).

## 6. Requisitos no funcionales

- **Latencia**: pipeline conversacional fluido; medir TTFT y latencias por etapa
  (STT/LLM/TTS) con las métricas de `AgentSession`. Objetivo *best-effort*: inicio de
  respuesta hablada < ~1.5 s tras fin de turno (no bloqueante para el MVP).
- **Observabilidad**: capturar `MetricsCollectedEvent` + `session.usage`; log
  estructurado por turno (transcript del usuario, tool calls, respuesta, latencias).
  Dejar documentado (no necesariamente implementado) el **punto de extensión** para
  exportar a OpenTelemetry/Langfuse.
- **Turn-taking**: barge-in funcional.
- **Calidad de código**: tipos en las fronteras, errores **propagados con contexto**
  (nada de excepciones tragadas), **timeout explícito** en toda llamada de red, sin
  credenciales en el código.
- **Reproducibilidad**: `uv sync` + `.env` presente → arranca. README con pasos exactos.

## 7. Criterios de aceptación

Verificables uno a uno. (El MVP no sirve interfaz web: la verificación es por consola y
por la suite de tests, no visual.)

1. `uv sync` instala sin errores y `uv run <agente> console` arranca el agente en
   consola **sin excepciones**, con las keys del `.env` presentes.
2. En console mode, el agente **saluda al iniciar** y responde a una pregunta general
   completando la ida y vuelta STT→LLM→TTS.
3. Consulta de **envío existente** (ej. "estado del envío SHP-1024") → el agente
   **invoca `lookup_shipment`** y responde con estado/ubicación/ETA coherentes con los
   datos.
4. Consulta de **envío inexistente** → la tool devuelve "no encontrado" y el agente lo
   comunica con gracia, **sin inventar datos y sin crash**.
5. Pregunta de **procedimiento cubierta por los docs** → recupera vía RAG y responde con
   el contenido correcto; una pregunta **fuera del corpus** → responde que **no lo sabe**
   en lugar de alucinar.
6. **Barge-in**: si el usuario habla mientras el agente responde, el agente se detiene y
   atiende (VAD + turn detector operativos). Verificable en console o por test de
   eventos.
7. Existen **≥3 evals automatizadas** con el test framework de LiveKit (`session.run(...)`
   + `expect(...).judge(llm, intent=...)`) que cubren: (a) que **usa la tool** ante una
   consulta de envío, (b) que el **RAG responde correctamente** una pregunta de
   procedimiento, (c) que **NO alucina** ante algo fuera de su conocimiento.
   `uv run pytest` las pasa.
8. **Métricas por turno**: al terminar una interacción, el sistema registra en log
   estructurado las latencias de STT/LLM/TTS y el uso de tokens vía las métricas de
   `AgentSession`.
9. `ruff check` y `mypy` (o `ty`) pasan sin errores en el código de aplicación.
10. `README.md` + `.env.example` permiten a un tercero arrancar de cero; documentado el
    paso para conectar a LiveKit Cloud (`dev`/`start`) y los tres subcomandos.

### 7.b. Criterios de fase 2 — LiveKit Cloud (verificación manual de Alberto)

Requieren credenciales `LIVEKIT_*` reales. **El pipeline automatizado (`build-project`)
NO los verifica** porque no dispone de la cuenta de Alberto; quedan como checklist que
Alberto ejecuta tras sacar las credenciales. El código de fase 1 debe soportarlos sin
modificación.

- **F2.1** Con las `LIVEKIT_*` en el `.env`, `uv run <agente> dev` arranca, el agente se
  **registra como worker** sin errores y queda a la espera de jobs.
- **F2.2** Desde el **Agent Console / playground** del navegador se entra a una room, el
  agente se une como participante y mantiene una **conversación de voz real** (mismo
  comportamiento que en console: saludo, tool de envíos, RAG, barge-in).
- **F2.3** El **dashboard de observability** de LiveKit Cloud muestra el transcript y las
  métricas de la sesión.

## 8. Fuera de alcance (no objetivos)

- **Sin frontend web propio**: se usa console mode; el playground/telephony de LiveKit
  Cloud es opcional y documentado, no implementado.
- **Sin aprendizaje en vivo de una web** (no forma parte del alcance de este proyecto). Aquí el dominio es
  fijo y conocido.
- **Sin deployment gestionado 24/7 ni infra de escalado**: probar el agente en una room
  de LiveKit Cloud vía `dev`/`start` SÍ entra (fase 2); lo que queda fuera es el
  despliegue permanente y el escalado (múltiples workers, autoscaling), que se documenta
  como "cómo", no se ejecuta.
- Sin autenticación de usuarios ni multi-tenant.

## 9. Riesgos conocidos

- **Nombre de variable:** se utiliza `DEEPGRAM_API_KEY` como nombre canónico;
  mapear explícitamente en config o el STT no autentica.
- **Embeddings sin key de pago**: si se va a Supabase/pgvector hace falta generar
  embeddings; sin OpenAI/Voyage, usar embeddings locales o keyword retrieval.
- **Turn detector local** descarga un modelo ONNX la primera vez
  (`uv run <agente> download-files`): documentarlo o el primer arranque falla.
- **RAG sobre Supabase** requiere que el token del `.env` dé acceso; si no, fallback a
  índice local.
- **Console mode necesita micrófono**; las evals deben ir por el **test framework
  (texto)**, no por audio real, para poder correr en CI/headless.
- **Latencia con Claude**: usar un modelo rápido; *opus* penaliza el turn-taking.
- **ElevenLabs**: elegir modelo/voz compatibles con streaming de baja latencia.
