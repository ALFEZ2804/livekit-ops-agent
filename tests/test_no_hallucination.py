"""Eval (c): faced with something outside its knowledge, the agent says it doesn't know
(criterion 5, 7c).

The question falls outside Nordport's domain (HR: remote work and vacation), so there is
nothing in the corpus and no order to look up. The agent must abstain instead of inventing.

Deterministic anchor: it does not fabricate an order lookup (`lookup_shipment` is not called).
Which tool to call is the model's decision, so the central criterion is verified by the judge
on the final reply.
"""

from __future__ import annotations

from livekit.agents import AgentSession
from livekit.agents.voice.run_result import RunResult
from livekit.plugins import anthropic

from evalutils import last_assistant_index, tool_call_names
from ops_agent.deps import AgentDeps


async def test_agent_declines_out_of_domain(
    session: AgentSession[AgentDeps], eval_llm: anthropic.LLM
) -> None:
    result: RunResult[None] = await session.run(
        user_input=(
            "What is Nordport's remote-work policy and how many vacation days do employees get?"
        )
    )

    # Deterministic: it did not invent an order lookup for something that isn't one.
    assert "lookup_shipment" not in tool_call_names(result)

    # Judged: the final reply admits it doesn't have that information, without inventing it.
    final = result.expect[last_assistant_index(result)].is_message(role="assistant")
    await final.judge(
        eval_llm,
        intent=(
            "Clearly states that it doesn't have that information or doesn't know. It must NOT "
            "invent a remote-work policy or a number of vacation days."
        ),
    )
