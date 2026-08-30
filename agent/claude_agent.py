"""
Tool-use orchestration loop. Kept dependency-light and framework-free so it
can be driven from Streamlit, a CLI, or tests identically.
"""

from __future__ import annotations

import os

import anthropic

from agent.system_prompt import SYSTEM_PROMPT
from agent.tools import TOOL_DEFINITIONS, TOOL_IMPLEMENTATIONS

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOOL_ROUNDS = 6  # guard against runaway tool-call loops


class BIAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
        self.model = model

    def run_turn(self, conversation: list[dict], on_tool_call=None) -> tuple[str, list[dict]]:
        """
        conversation: list of {"role": "user"|"assistant", "content": ...}
        on_tool_call: optional callback(tool_name, tool_input, tool_result_text)
            fired for each tool call, so the UI can show "how this was computed".

        Returns (final_text_reply, updated_conversation).
        """
        messages = list(conversation)

        for _ in range(MAX_TOOL_ROUNDS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                final_text = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                return final_text, messages

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                impl = TOOL_IMPLEMENTATIONS.get(block.name)
                if impl is None:
                    result_text = f"Error: unknown tool '{block.name}'"
                else:
                    try:
                        result_text = impl(**block.input)
                    except Exception as exc:  # noqa: BLE001 — surface to the model, don't crash the app
                        result_text = f"Error running {block.name}: {exc}"

                if on_tool_call:
                    on_tool_call(block.name, block.input, result_text)

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

        return (
            "I made several tool calls but couldn't settle on a final answer — "
            "try narrowing the question (e.g. specify a sector or time period).",
            messages,
        )
