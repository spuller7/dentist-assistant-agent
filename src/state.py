"""
FILE: src/state.py
WHY: This is the LangGraph state schema. Reviewers can read this file and
     know exactly which fields move from node to node.
"""

from __future__ import annotations

from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

Intent = Literal["faq", "book", "forms", "cancel", "unknown"]


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_text: str
    redacted_text: str
    intent: Intent | str
    retrieved_context: str
    pii_findings: list[str]
    stall_retries: int
