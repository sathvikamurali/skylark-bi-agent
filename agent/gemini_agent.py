"""
Gemini tool-use orchestration loop.

Kept dependency-light and framework-free so it can be driven from
Streamlit, a CLI, or tests identically.
"""

from __future__ import annotations

import os
import time

from google import genai
from google.genai import types

from agent.system_prompt import SYSTEM_PROMPT
from agent.tools import TOOL_DEFINITIONS, TOOL_IMPLEMENTATIONS


DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash")

MAX_TOOL_ROUNDS = 6
MAX_RETRIES = 3


def _gemini_tools():
    """Convert our existing tool definitions into Gemini function declarations."""
    declarations = []

    for tool in TOOL_DEFINITIONS:
        declarations.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=tool["input_schema"],
            )
        )

    return [types.Tool(function_declarations=declarations)]


def _to_gemini_contents(conversation: list[dict]) -> list[types.Content]:
    """Convert our simple conversation format into Gemini contents."""
    contents = []

    for message in conversation:
        role = "model" if message["role"] == "assistant" else "user"

        contents.append(
            types.Content(
                role=role,
                parts=[types.Part(text=message["content"])],
            )
        )

    return contents


def _is_retryable_error(exc: Exception) -> bool:
    """Return True for temporary Gemini availability errors."""
    error_text = str(exc).lower()

    return (
        "503" in error_text
        or "service unavailable" in error_text
        or "unavailable" in error_text
        or "temporarily overloaded" in error_text
        or "high demand" in error_text
    )


class BIAgent:
    def __init__(self, model: str = DEFAULT_MODEL):
        self.client = genai.Client()
        self.model = model
        self.fallback_model = FALLBACK_MODEL
        self.tools = _gemini_tools()

    def _generate_with_retry(self, contents, config):
        """
        Call Gemini with retry/backoff for temporary 503 errors.

        If the primary model remains unavailable after retries,
        automatically try the fallback model.
        """

        models_to_try = [self.model]

        if self.fallback_model and self.fallback_model != self.model:
            models_to_try.append(self.fallback_model)

        last_error = None

        for model_name in models_to_try:

            for attempt in range(MAX_RETRIES):

                try:
                    return self.client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=config,
                    )

                except Exception as exc:
                    last_error = exc

                    if not _is_retryable_error(exc):
                        raise

                    # Exponential backoff:
                    # 2s → 4s → 8s
                    if attempt < MAX_RETRIES - 1:
                        delay = 2 ** (attempt + 1)

                        time.sleep(delay)

            # Primary model failed all retries.
            # Try fallback model next.

        raise last_error

    def run_turn(
        self,
        conversation: list[dict],
        on_tool_call=None,
    ) -> tuple[str, list[dict]]:
        """
        Run one conversational turn.

        The model can request one or more BI tools. The application executes
        those tools, sends their results back to Gemini, and repeats until
        Gemini produces a final natural-language answer.
        """

        contents = _to_gemini_contents(conversation)

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=self.tools,
        )

        for _ in range(MAX_TOOL_ROUNDS):

            response = self._generate_with_retry(
                contents,
                config,
            )

            model_content = response.candidates[0].content
            contents.append(model_content)

            tool_calls = []

            for part in model_content.parts:
                if part.function_call:
                    tool_calls.append(part.function_call)

            # No tool call means Gemini has produced the final answer.
            if not tool_calls:
                final_text = response.text or ""

                updated_conversation = list(conversation)

                if final_text:
                    updated_conversation.append(
                        {
                            "role": "assistant",
                            "content": final_text,
                        }
                    )

                return final_text, updated_conversation

            # Execute requested tools.
            function_response_parts = []

            for tool_call in tool_calls:
                name = tool_call.name
                tool_input = dict(tool_call.args or {})

                impl = TOOL_IMPLEMENTATIONS.get(name)

                if impl is None:
                    result_text = f"Error: unknown tool '{name}'"
                else:
                    try:
                        result_text = impl(**tool_input)
                    except Exception as exc:
                        result_text = f"Error running {name}: {exc}"

                if on_tool_call:
                    on_tool_call(
                        name,
                        tool_input,
                        result_text,
                    )

                function_response_parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response={"result": result_text},
                    )
                )

            # Send tool results back to Gemini.
            contents.append(
                types.Content(
                    role="user",
                    parts=function_response_parts,
                )
            )

        final_text = (
            "I made several tool calls but couldn't settle on a final answer — "
            "try narrowing the question (e.g. specify a sector or time period)."
        )

        updated_conversation = list(conversation)

        updated_conversation.append(
            {
                "role": "assistant",
                "content": final_text,
            }
        )

        return final_text, updated_conversation
