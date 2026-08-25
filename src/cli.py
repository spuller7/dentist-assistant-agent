"""
FILE: src/cli.py
WHY: Simple interface for the demo. Prints the final patient-facing reply
     after a turn finishes. Flags reset the JSON database or run one turn.
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from langchain_core.messages import AIMessage

from src.db import reset_db
from src.graph import build_graph, starting_state
from src.guardrails import redact_pii
from src.paths import db_path

load_dotenv()


def _trace_config(turn: int, redacted: str = "") -> dict:
    return {
        "run_name": f"front-desk-turn-{turn}",
        "tags": ["riverside-dental", "demo"],
        "metadata": {
            "app": "riverside-dental-agent",
            "redacted_input": redacted,
        },
    }


def _visible_text(content) -> str:
    if not content:
        return ""
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


def _last_patient_reply(messages: list) -> str:
    """Last assistant utterance meant for the patient, not a tool-call aside."""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not _has_tool_calls(message):
            text = _visible_text(message.content)
            if text:
                return text
    return ""


def _print_turn_footer(final_state: dict) -> None:
    redacted = final_state.get("redacted_text") or ""
    findings = final_state.get("pii_findings") or []
    intent = final_state.get("intent")
    print(f"(intent={intent}" + (f", redacted PII={','.join(findings)}" if findings else "") + ")")
    if findings:
        print(f"(logged as: {redacted})")


def run_turn(graph, user_text: str, history: list, turn: int) -> list:
    state = starting_state(user_text)
    if history:
        state["messages"] = [*history, *state["messages"]]

    cleaned, _ = redact_pii(user_text)
    config = _trace_config(turn, cleaned)

    print("Agent: ", end="", flush=True)
    final_state = None
    try:
        for event in graph.stream(state, config=config, stream_mode="values"):
            final_state = event
    except Exception:
        final_state = graph.invoke(state, config=config)

    if final_state:
        print(_last_patient_reply(final_state.get("messages", [])), end="", flush=True)

    print("\n")
    if not final_state:
        return state["messages"]

    _print_turn_footer(final_state)
    return final_state.get("messages", state["messages"])


def chat_loop() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        print("Missing OPENAI_API_KEY. Copy .env.example to .env and add your keys.")
        sys.exit(1)

    graph = build_graph()
    history: list = []
    turn = 1

    print("Welcome to Riverside Family Dental.")
    print()
    print("I can help you:")
    print("- Book a visit with a named dentist or any available dentist")
    print("- Submit new-patient forms (required before a first appointment)")
    print("- Cancel an existing visit")
    print("- Answer questions about hours, insurance, and who works here")
    print()
    print(f"Database: {db_path()}")
    print("Type 'quit' to exit or 'reset' to restore the seed database.\n")

    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return
        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit"}:
            print("Goodbye.")
            return
        if user_text.lower() == "reset":
            reset_db()
            history = []
            print("Database reset. Conversation cleared.\n")
            continue

        history = run_turn(graph, user_text, history, turn)
        turn += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Riverside Family Dental front-desk agent")
    parser.add_argument("--reset-db", action="store_true", help="Restore data/office.json from the seed file and exit")
    parser.add_argument("--once", metavar="TEXT", help="Run one turn and exit (useful for scripts)")
    args = parser.parse_args()

    if args.reset_db:
        path = reset_db()
        print(f"Restored {path} from seed.")
        return
    if args.once:
        if not os.getenv("OPENAI_API_KEY"):
            print("Missing OPENAI_API_KEY. Copy .env.example to .env and add your keys.")
            sys.exit(1)
        graph = build_graph()
        run_turn(graph, args.once, [], 1)
        return
    chat_loop()


if __name__ == "__main__":
    main()
