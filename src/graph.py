"""
FILE: src/graph.py
WHY: This is the LangGraph control flow. Nodes update state; conditional
     edges decide the next step. Read this file to see how a turn moves.

Flow:
    START -> ingest_forms -> redact_pii -> classify_intent -> retrieve_knowledge
          -> (faq) answer_faq -> END
          -> (book/forms/cancel/unknown) assistant <-> tools
          -> if the assistant stalled ("booking now") without a tool call,
             nudge once more, then a fallback question if it stalls again
"""

from __future__ import annotations

import uuid
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from src.db import stated_service, today_context
from src.forms_ingest import ingest_forms
from src.guardrails import redact_pii
from src.llm import get_llm
from src.rag import format_docs, retrieve
from src.state import AgentState
from src.tools import SCHEDULING_TOOLS

FAQ_SYSTEM = """{today}

You are the front-desk assistant for Riverside Family Dental.
Answer using only the retrieved office notes. Each note is labeled with the
source file it came from. If the notes do not cover the question, say you
are not sure and provide the office phone number.
Use the date and time above for relative words like today, tomorrow, this
afternoon, or now. Do not invent dates or times.
Be brief and specific. Give a complete answer, or ask one clarifying question.
"""

ASSISTANT_SYSTEM = """{today}

You are the front-desk assistant for Riverside Family Dental.
You schedule visits and answer office questions. New-patient intake fields
are saved before you see the message. You never receive date of birth, phone,
insurance, or medical notes.

Rules:
- Use tools. Do not invent open slots, dentists, or patient records.
- The live calendar and staff roster come only from tools. Office notes are
  background, not the schedule. Do not offer a dentist unless that person
  appears in a list_dentists or get_open_slots result.
- Use the date and time above for relative words like today, tomorrow, this
  afternoon, or next Tuesday. Pass YYYY-MM-DD, today, tomorrow, or a weekday
  to tools. Do not invent dates or times. Do not offer a slot that has already
  passed today.
- Patients may request a dentist by name or say any dentist.
- Before listing times, you must know the visit type: cleaning/exam/filling,
  braces/Invisalign, a child visit, or extraction/surgery.
- If the visit type is missing, ask once. Do not call get_open_slots yet.
- If they already named the service, skip the question. Do not ask them to
  confirm the same service. Immediately call get_open_slots with that service.
  If they did not name a dentist, pass dentist='any' and service=<visit type>.
  Example: "next available cleaning" -> get_open_slots(dentist='any',
  service='cleaning'). Then list the returned times. Do not ask which dentist
  first.
- A cleaning, exam, checkup, or filling with no mention of a child is adult
  general dentistry. Do not ask whether the patient is a child. Call
  get_open_slots with service='cleaning' (or exam/filling) right away.
- If they already named a dentist, keep that dentist. Still pass their stated
  service as the booking reason.
- After the service is known, recommend the matching specialty and list every
  time the tool returned for that day. Do not omit hours. Do not offer
  dentists who were not in the tool result.
- Never assume who is talking. Names in office notes (Alex Rivera, Sam Ortiz)
  are examples of returning patients, not the current caller. Do not look them
  up or book them unless the patient typed that name in this conversation.
- If they have not typed a patient name, ask for it before lookup_patient or
  book_appointment. A time, dentist, or visit type is not a name.
- If they already gave a patient name, a dentist or 'any', a day, a time, and
  a visit type, look up that name and book in this turn. Do not ask them to
  re-confirm the same slot they just requested.
- Otherwise do not book until they confirm a slot and give a patient name.
- If a named dentist is not on staff, say there is no dentist by that name, list who works here, and offer to book one of them. Do not say the calendar is full.
- New patients must submit forms before you book. Intake is saved
  automatically before you see it: labeled fields, a comma-separated line
  (Name, Date of birth, Phone, Insurance, Medical notes), or a follow-up
  for a missing field. You never receive those values.
  If lookup_patient says they are not on file, ask for the five fields.
  Do not collect, repeat, or invent the field values. Do not book yet.
- If the user message says intake was saved and forms_complete=true, confirm
  the forms are on file for that patient. They can now book. Look them up
  and continue with any dentist, day, time, and visit already chosen.
  Do not ask them to resubmit forms.
- If the user message says intake is incomplete, ask only for the missing
  field listed there. They can reply with just that value. Do not ask them
  to paste values you already have.
- Look up the name they give. Some returning patients already have forms on
  file. Never treat an unnamed caller as a chart on file.
- After a successful booking or form save, confirm the facts (tool result or
  the intake-saved note). Do not echo DOB, phone, insurance, or medical notes.
- Every reply the patient hears must either confirm a completed action
  (booked, cancelled, forms saved) with the tool facts, or ask them a
  specific question so they know what to say next.
- Never end on filler: "one moment", "booking now", "please hold",
  "I will book that", or "let me check". Call the tool first, then speak
  from the tool result. Do not announce a tool call instead of making it.
- Keep replies short.

Retrieved office notes:
{context}
"""


class IntentDecision(BaseModel):
    intent: Literal["faq", "book", "forms", "cancel", "unknown"] = Field(
        description="faq=policy/hours/insurance/who works here; book=open slots, next available time, or schedule a visit; forms=submit intake; cancel=cancel or change a visit"
    )


def ingest_forms_node(state: AgentState) -> dict:
    text = state.get("user_text") or ""
    pending = dict(state.get("pending_intake") or {})
    result = ingest_forms(text, pending=pending)
    if result is None:
        return {"forms_ingested": False, "pending_intake": pending}

    updates: dict = {
        "user_text": result.sanitized,
        "forms_ingested": result.saved,
        "pending_intake": {} if result.saved else result.fields,
    }
    messages = state.get("messages") or []
    last_human = next(
        (message for message in reversed(messages) if isinstance(message, HumanMessage)),
        None,
    )
    if last_human is not None:
        updates["messages"] = [
            HumanMessage(content=result.sanitized, id=getattr(last_human, "id", None))
        ]
    return updates


def redact_pii_node(state: AgentState) -> dict:
    cleaned, findings = redact_pii(state["user_text"])
    return {"redacted_text": cleaned, "pii_findings": findings}


def classify_intent_node(state: AgentState) -> dict:
    text = state.get("user_text") or ""
    if state.get("forms_ingested") or text.startswith("[Intake incomplete"):
        return {"intent": "forms"}

    llm = get_llm().with_structured_output(IntentDecision)
    decision = llm.invoke(
        [
            SystemMessage(
                content=(
                    "Classify the front-desk request. "
                    "Use forms when the message says intake was saved, intake is "
                    "incomplete, or the caller is filing new-patient forms. "
                    "Use faq when they ask whether forms are required, or about hours, "
                    "policy, insurance, or dentist bios. "
                    "Use book when they want an appointment, the next available time, "
                    "open slots, or when they can come in — even if they are new. "
                    "Do not use faq for live calendar or next-available questions."
                )
            ),
            HumanMessage(content=state["redacted_text"] or state["user_text"]),
        ]
    )
    return {"intent": decision.intent}


def retrieve_knowledge_node(state: AgentState) -> dict:
    docs = retrieve(state["redacted_text"] or state["user_text"])
    return {"retrieved_context": format_docs(docs)}


def route_after_retrieve(state: AgentState) -> Literal["answer_faq", "assistant"]:
    if state.get("intent") == "faq":
        return "answer_faq"
    return "assistant"


def _wants_next_available(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "next available",
            "next opening",
            "open slot",
            "when is the next",
            "earliest available",
        )
    )


_STALL_PHRASES = (
    "booking now",
    "checking now",
    "looking now",
    "one moment",
    "one second",
    "just a moment",
    "please hold",
    "please wait",
    "hold on",
    "hang on",
    "i will now book",
    "i'll now book",
    "i will book",
    "i'll book",
    "let me book",
    "let me check",
    "let me look",
    "i'll check",
    "i'll look",
    "i will check",
    "i will look",
)

_DONE_PHRASES = (
    "booked",
    "scheduled",
    "confirmed",
    "cancelled",
    "canceled",
    "forms saved",
    "on file",
    "submitted",
)

STALL_NUDGE = (
    "Your last reply left the patient waiting. Call the tool you still need, "
    "or confirm the completed action using the tool facts, or ask the patient "
    "one specific question. Do not say you will do something later."
)

FALLBACK_CLOSEOUT = (
    "I wasn't able to finish that just now. Should I go ahead with what we "
    "already discussed, or do you want to change the day, time, or dentist?"
)


def _message_text(message) -> str:
    content = getattr(message, "content", "") or ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        return "".join(parts)
    return str(content)


def _has_tool_calls(message) -> bool:
    return bool(getattr(message, "tool_calls", None))


def is_stall_reply(text: str) -> bool:
    """True when a patient-facing reply neither confirms nor asks a question."""
    lowered = (text or "").strip().lower()
    if not lowered:
        return True
    if "?" in lowered:
        return False
    if any(phrase in lowered for phrase in _DONE_PHRASES):
        return False
    return any(phrase in lowered for phrase in _STALL_PHRASES)


def _booking_nudge(user_text: str, has_tool_result: bool) -> str:
    if has_tool_result:
        return ""
    service = stated_service(user_text)
    if service and _wants_next_available(user_text):
        return (
            f"\nRequired next step: call get_open_slots with dentist='any' "
            f"and service='{service}'. Do not ask a question first."
        )
    if not service and _wants_next_available(user_text):
        return (
            "\nRequired next step: ask what type of visit they need "
            "(cleaning, braces, child visit, or surgery). Do not call get_open_slots yet."
        )
    return ""


def _recent_tool_text(messages: list) -> str:
    idx = len(messages) - 1
    while idx >= 0 and not isinstance(messages[idx], ToolMessage):
        if isinstance(messages[idx], HumanMessage):
            return ""
        idx -= 1
    parts = []
    while idx >= 0 and isinstance(messages[idx], ToolMessage):
        parts.append(_message_text(messages[idx]))
        idx -= 1
    return "\n".join(reversed(parts))


def _tool_closeout_nudge(messages: list) -> str:
    text = _recent_tool_text(messages)
    if not text:
        return (
            "\nRequired: your reply must either confirm a completed action or "
            "ask the patient a specific question. Do not say 'one moment' or 'booking now'."
        )
    lowered = text.lower()
    if lowered.startswith("booked") or lowered.startswith("cancelled") or lowered.startswith("forms saved"):
        return (
            "\nRequired next step: tell the patient the action is complete using "
            "the tool facts. Do not ask them to wait."
        )
    if "no patient name given" in lowered:
        return (
            "\nAsk for the patient's name. Do not look up or book Alex Rivera, "
            "Sam Ortiz, or anyone else on file until they type a name."
        )
    if "booking failed" in lowered or "cancel failed" in lowered:
        return (
            "\nTell the patient the action did not go through and ask what "
            "they want to do next."
        )
    if "not on file" in lowered:
        return (
            "\nAsk the patient to send Name, Date of birth, Phone, Insurance, "
            "and Medical notes in one line (labeled or comma-separated). "
            "Do not collect or echo those values. Do not book yet."
        )
    if "forms=complete" in lowered or "already on file with completed forms" in lowered:
        return (
            "\nIf this conversation already has a patient name they typed, a "
            "dentist, day, time, and visit type, call book_appointment now. "
            "If they have not typed a name, ask for it. Do not assume they are "
            "Alex Rivera or Sam Ortiz. Confirm only after the tool returns."
        )
    return (
        "\nRequired: your reply must either confirm a completed action or "
        "ask the patient a specific question. Do not say 'one moment' or 'booking now'."
    )


def route_after_assistant(state: AgentState) -> Literal["tools", "nudge_stall", "fallback_closeout", "__end__"]:
    last = state["messages"][-1] if state.get("messages") else None
    if last is not None and _has_tool_calls(last):
        return "tools"
    if last is not None and is_stall_reply(_message_text(last)):
        if state.get("stall_retries", 0) < 1:
            return "nudge_stall"
        return "fallback_closeout"
    return END


def answer_faq_node(state: AgentState) -> dict:
    llm = get_llm()
    message = llm.invoke(
        [
            SystemMessage(
                content=FAQ_SYSTEM.format(today=today_context())
                + "\n\nOffice notes:\n"
                + state["retrieved_context"]
            ),
            HumanMessage(content=state["user_text"]),
        ]
    )
    return {"messages": [message]}


def assistant_node(state: AgentState) -> dict:
    user_text = state.get("user_text") or ""
    has_tool_result = any(isinstance(message, ToolMessage) for message in state["messages"])
    force_slots = (
        not has_tool_result
        and bool(stated_service(user_text))
        and _wants_next_available(user_text)
    )
    llm = get_llm()
    if force_slots:
        llm = llm.bind_tools(SCHEDULING_TOOLS, tool_choice="get_open_slots")
    else:
        llm = llm.bind_tools(SCHEDULING_TOOLS)
    extra = _booking_nudge(user_text, has_tool_result)
    if state.get("forms_ingested") and not has_tool_result:
        extra += (
            "\nRequired: intake is already saved with forms_complete=true. "
            "Look up the patient named in the intake-saved note. Confirm the "
            "forms are on file. If a dentist, day, time, and visit type are "
            "already in this conversation, call book_appointment now. "
            "Do not ask them to resubmit forms."
        )
    elif (user_text.startswith("[Intake incomplete") and not has_tool_result):
        extra += (
            "\nRequired: ask only for the missing field listed in the user "
            "message. They can reply with just that value. Do not invent "
            "values and do not book."
        )
    if _recent_tool_text(state["messages"]):
        extra += _tool_closeout_nudge(state["messages"])
    if state.get("stall_retries"):
        extra += "\nRequired: " + STALL_NUDGE
    message = llm.invoke(
        [
            SystemMessage(
                content=ASSISTANT_SYSTEM.format(
                    today=today_context(),
                    context=state["retrieved_context"],
                )
                + extra
            ),
            *state["messages"],
        ]
    )
    return {"messages": [message]}


def nudge_stall_node(state: AgentState) -> dict:
    return {
        "stall_retries": state.get("stall_retries", 0) + 1,
        "messages": [SystemMessage(content=STALL_NUDGE)],
    }


def fallback_closeout_node(state: AgentState) -> dict:
    return {"messages": [AIMessage(content=FALLBACK_CLOSEOUT)]}


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("ingest_forms", ingest_forms_node)
    graph.add_node("redact_pii", redact_pii_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("retrieve_knowledge", retrieve_knowledge_node)
    graph.add_node("answer_faq", answer_faq_node)
    graph.add_node("assistant", assistant_node)
    graph.add_node("tools", ToolNode(SCHEDULING_TOOLS))
    graph.add_node("nudge_stall", nudge_stall_node)
    graph.add_node("fallback_closeout", fallback_closeout_node)

    graph.add_edge(START, "ingest_forms")
    graph.add_edge("ingest_forms", "redact_pii")
    graph.add_edge("redact_pii", "classify_intent")
    graph.add_edge("classify_intent", "retrieve_knowledge")
    graph.add_conditional_edges(
        "retrieve_knowledge",
        route_after_retrieve,
        {"answer_faq": "answer_faq", "assistant": "assistant"},
    )
    graph.add_edge("answer_faq", END)
    graph.add_conditional_edges(
        "assistant",
        route_after_assistant,
        {
            "tools": "tools",
            "nudge_stall": "nudge_stall",
            "fallback_closeout": "fallback_closeout",
            END: END,
        },
    )
    graph.add_edge("tools", "assistant")
    graph.add_edge("nudge_stall", "assistant")
    graph.add_edge("fallback_closeout", END)
    return graph.compile()


def starting_state(user_text: str, pending_intake: dict | None = None) -> AgentState:
    return {
        "messages": [HumanMessage(content=user_text, id=str(uuid.uuid4()))],
        "user_text": user_text,
        "redacted_text": "",
        "intent": "unknown",
        "retrieved_context": "",
        "pii_findings": [],
        "stall_retries": 0,
        "forms_ingested": False,
        "pending_intake": dict(pending_intake or {}),
    }
