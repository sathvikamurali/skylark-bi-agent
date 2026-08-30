"""
Streamlit chat front-end for the monday.com BI agent.

Run locally: streamlit run app.py
Deploy: push to a GitHub repo, connect it on share.streamlit.io, and set the
four secrets listed in README.md. No other setup needed.
"""

import os

import streamlit as st

from agent.claude_agent import BIAgent
from agent.tools import clear_cache
from monday.client import MondayClient, MondayAPIError

st.set_page_config(page_title="Skylark BI Agent", page_icon="📊", layout="centered")

REQUIRED_ENV_VARS = [
    "GEMINI_API_KEY",
    "MONDAY_API_TOKEN",
    "MONDAY_WORK_ORDERS_BOARD_ID",
    "MONDAY_DEALS_BOARD_ID"
]


def _load_secrets_into_env():
    """Streamlit Cloud exposes secrets via st.secrets; mirror them into
    os.environ so the rest of the codebase (agent/tools/client) can stay
    framework-agnostic and testable outside Streamlit."""
    for key in REQUIRED_ENV_VARS:
        if key not in os.environ and key in st.secrets:
            os.environ[key] = st.secrets[key]


_load_secrets_into_env()

st.title("📊 Skylark BI Agent")
st.caption("Ask about pipeline, revenue, or delivery performance — pulled live from monday.com.")

missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
if missing:
    st.error(
        "Missing configuration: " + ", ".join(missing) +
        ". Set these as environment variables (local) or Streamlit secrets (hosted). "
        "See README.md."
    )
    st.stop()

with st.sidebar:
    st.subheader("Connection status")
    try:
        who = MondayClient().ping()
        st.success(f"Connected to monday.com as {who}")
    except MondayAPIError as e:
        st.error(f"monday.com connection failed: {e}")
        st.stop()

    if st.button("🔄 Refresh data cache"):
        clear_cache()
        st.success("Cache cleared — next question will re-fetch from monday.com.")

    st.markdown("---")
    st.markdown(
        "**Try asking:**\n"
        "- How's our pipeline looking for the energy sector this quarter?\n"
        "- What's our total delivered revenue by sector?\n"
        "- Which work orders look overdue?\n"
        "- Prepare a leadership update on Q3 performance."
    )

if "agent" not in st.session_state:
    st.session_state.agent = BIAgent()
if "messages" not in st.session_state:
    st.session_state.messages = []  # display-layer history: [{"role", "content"}]
if "api_conversation" not in st.session_state:
    st.session_state.api_conversation = []  # full Anthropic-format history incl. tool blocks

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("Ask a business question...")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.api_conversation.append({"role": "user", "content": user_input})

    tool_calls_made = []

    def _on_tool_call(name, tool_input, result_text):
        tool_calls_made.append((name, tool_input, result_text))

    with st.chat_message("assistant"):
        with st.spinner("Checking monday.com..."):
            try:
                reply_text, updated_conversation = st.session_state.agent.run_turn(
                    st.session_state.api_conversation, on_tool_call=_on_tool_call
                )
                st.session_state.api_conversation = updated_conversation
            except Exception as exc:  # noqa: BLE001
                reply_text = f"Something went wrong talking to the agent: {exc}"

        st.markdown(reply_text)

        if tool_calls_made:
            with st.expander("🔍 How this was computed"):
                for name, tool_input, result_text in tool_calls_made:
                    st.markdown(f"**{name}**({tool_input})")
                    st.code(result_text, language="json")

    st.session_state.messages.append({"role": "assistant", "content": reply_text})
