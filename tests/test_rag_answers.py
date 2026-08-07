"""Eval (b): the RAG answers a procedure question correctly (criterion 5, 7b).

`session.run(...)` drives the question; the agent must call `search_docs`, which over the
deterministic `Bm25Retriever` retrieves the "failed deliveries" section. Deterministic asserts
(tool called + the retrieved passage contains the fact) alongside the judged final reply.
"""

from __future__ import annotations

from livekit.agents import AgentSession
from livekit.agents.voice.run_result import RunResult
from livekit.plugins import anthropic

from evalutils import last_assistant_index, tool_call_outputs
from ops_agent.deps import AgentDeps


async def test_agent_answers_from_docs(
    session: AgentSession[AgentDeps], eval_llm: anthropic.LLM
) -> None:
    result: RunResult[None] = await session.run(
        user_input=(
            "How many delivery attempts do you make when a delivery fails, and do you notify "
            "the recipient?"
        )
    )

    # Deterministic: it consulted the documentation instead of answering from memory.
    result.expect.contains_function_call(name="search_docs")

    # Deterministic: the retrieved passage (BM25, reproducible) carries the key fact from the
    # failed-deliveries doc: up to three attempts.
    outputs = " || ".join(tool_call_outputs(result))
    assert "three attempts" in outputs

    # Judged: the final reply conveys the procedure grounded in what was retrieved.
    final = result.expect[last_assistant_index(result)].is_message(role="assistant")
    await final.judge(
        eval_llm,
        intent=(
            "Explains that Nordport makes up to three delivery attempts on business days and "
            "that, after a failed attempt, the recipient is notified. It must be grounded in "
            "the documentation, not say it doesn't know."
        ),
    )
