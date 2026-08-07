"""Eval (a): the agent calls `lookup_shipment` for an order query (criterion 3, 7a).

Uses LiveKit's eval framework: `session.run(...)` drives the turn in text; then we mix
**deterministic** asserts (the right tool was called and returned the exact fields from the
fixed dataset) with an **LLM-judged** assert on the final reply.
"""

from __future__ import annotations

from livekit.agents import AgentSession
from livekit.agents.voice.run_result import RunResult
from livekit.plugins import anthropic

from evalutils import last_assistant_index, tool_call_names, tool_call_outputs
from ops_agent.deps import AgentDeps


async def test_agent_uses_lookup_shipment(
    session: AgentSession[AgentDeps], eval_llm: anthropic.LLM
) -> None:
    result: RunResult[None] = await session.run(
        user_input="Hi, can you tell me where order 1024 is and when it will arrive?"
    )

    # Deterministic: it called the right tool instead of inventing the status.
    result.expect.contains_function_call(name="lookup_shipment")
    assert "lookup_shipment" in tool_call_names(result)

    # Deterministic (exact fields): the tool returned the real data for order 1024 from the
    # fixed dataset (status, location and ETA), not a value made up by the model.
    outputs = " || ".join(tool_call_outputs(result))
    assert "out for delivery" in outputs
    assert "London" in outputs
    assert "today before 6 PM" in outputs

    # Judged: the final reply communicates status and ETA consistent with that data.
    final = result.expect[last_assistant_index(result)].is_message(role="assistant")
    await final.judge(
        eval_llm,
        intent=(
            "Confirms that order 1024 is out for delivery and that it arrives today before "
            "6 PM (or an equivalent time). It must not ask for the number again or say it "
            "doesn't have the information."
        ),
    )
