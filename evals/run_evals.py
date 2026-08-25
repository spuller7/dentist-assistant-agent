"""
FILE: evals/run_evals.py
WHY: One small eval set with expected outcomes. Runs locally by default.
     Pass --langsmith to upload the dataset and score runs in LangSmith.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.messages import AIMessage

from src.db import reset_db
from src.graph import build_graph, starting_state
from src.paths import ROOT, db_path

load_dotenv()

DATASET_PATH = Path(__file__).resolve().parent / "dataset.json"
DATASET_NAME = "riverside-dental-front-desk"


def load_cases() -> list[dict]:
    payload = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    return payload["cases"]


def last_ai_text(messages: list) -> str:
    for message in reversed(messages):
        if not isinstance(message, AIMessage) or getattr(message, "tool_calls", None):
            continue
        content = message.content
        if not content:
            continue
        return content if isinstance(content, str) else str(content)
    return ""


def score_case(case: dict, result: dict, created: bool) -> dict:
    answer = last_ai_text(result.get("messages", []))
    intent = result.get("intent")
    expected_intent = case["expected_intent"]
    needles_any = [text.lower() for text in case.get("answer_must_include_any", [])]
    needles_all = [text.lower() for text in case.get("answer_must_include_all", [])]
    needles_none = [text.lower() for text in case.get("answer_must_not_include", [])]
    lowered = answer.lower()

    intent_ok = intent == expected_intent
    any_ok = any(needle in lowered for needle in needles_any) if needles_any else True
    all_ok = all(needle in lowered for needle in needles_all) if needles_all else True
    none_ok = all(needle not in lowered for needle in needles_none) if needles_none else True
    phrase_ok = any_ok and all_ok and none_ok
    booking_ok = created == bool(case.get("appointment_created"))

    return {
        "id": case["id"],
        "intent": intent,
        "intent_ok": intent_ok,
        "phrase_ok": phrase_ok,
        "booking_ok": booking_ok,
        "passed": intent_ok and phrase_ok and booking_ok,
        "answer": answer,
    }


def run_one(graph, case: dict) -> dict:
    before = json.loads(db_path().read_text(encoding="utf-8"))
    before_ids = {row["id"] for row in before.get("appointments", [])}

    result = graph.invoke(
        starting_state(case["question"]),
        config={
            "run_name": f"eval-{case['id']}",
            "tags": ["eval", "riverside-dental"],
            "metadata": {"case_id": case["id"], "expected_intent": case["expected_intent"]},
        },
    )

    after = json.loads(db_path().read_text(encoding="utf-8"))
    after_ids = {row["id"] for row in after.get("appointments", [])}
    created = bool(after_ids - before_ids)
    return score_case(case, result, created)


def run_local() -> list[dict]:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to run evals.")

    temp_dir = Path(tempfile.mkdtemp(prefix="dental-eval-"))
    os.environ["OFFICE_DB_PATH"] = str(temp_dir / "office.json")
    reset_db()
    graph = build_graph()

    rows = []
    try:
        for case in load_cases():
            reset_db()
            rows.append(run_one(graph, case))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
        os.environ.pop("OFFICE_DB_PATH", None)
    return rows


def print_report(rows: list[dict]) -> int:
    passed = sum(1 for row in rows if row["passed"])
    print(f"\n{passed}/{len(rows)} cases passed\n")
    for row in rows:
        flag = "PASS" if row["passed"] else "FAIL"
        print(f"[{flag}] {row['id']}")
        print(f"  intent={row['intent']} intent_ok={row['intent_ok']} phrase_ok={row['phrase_ok']} booking_ok={row['booking_ok']}")
        print(f"  answer={row['answer'][:220].replace(chr(10), ' ')}")
    return 0 if passed == len(rows) else 1


def run_langsmith() -> int:
    from langsmith import Client
    from langsmith.evaluation import evaluate

    if not os.getenv("LANGSMITH_API_KEY"):
        raise RuntimeError("Set LANGSMITH_API_KEY to upload evals.")

    client = Client()
    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        dataset = existing[0]
    else:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Riverside Family Dental front-desk expected outcomes",
        )
        client.create_examples(
            dataset_id=dataset.id,
            examples=[
                {
                    "inputs": {"question": case["question"]},
                    "outputs": {
                        "intent": case["expected_intent"],
                        "answer_must_include_any": case.get("answer_must_include_any", []),
                        "answer_must_include_all": case.get("answer_must_include_all", []),
                        "answer_must_not_include": case.get("answer_must_not_include", []),
                        "appointment_created": case.get("appointment_created", False),
                    },
                    "metadata": {"case_id": case["id"]},
                }
                for case in load_cases()
            ],
        )

    graph = None

    def target(inputs: dict) -> dict:
        nonlocal graph
        if graph is None:
            graph = build_graph()
        reset_db()
        before = json.loads(db_path().read_text(encoding="utf-8"))
        before_ids = {row["id"] for row in before.get("appointments", [])}
        result = graph.invoke(starting_state(inputs["question"]))
        after = json.loads(db_path().read_text(encoding="utf-8"))
        after_ids = {row["id"] for row in after.get("appointments", [])}
        return {
            "answer": last_ai_text(result.get("messages", [])),
            "intent": result.get("intent"),
            "appointment_created": bool(after_ids - before_ids),
        }

    def intent_match(run, example) -> dict:
        expected = (example.outputs or {}).get("intent")
        got = (run.outputs or {}).get("intent")
        return {"key": "intent_match", "score": int(got == expected)}

    def phrase_match(run, example) -> dict:
        outputs = example.outputs or {}
        needles_any = [text.lower() for text in outputs.get("answer_must_include_any", [])]
        needles_all = [text.lower() for text in outputs.get("answer_must_include_all", [])]
        needles_none = [text.lower() for text in outputs.get("answer_must_not_include", [])]
        answer = ((run.outputs or {}).get("answer") or "").lower()
        any_ok = any(needle in answer for needle in needles_any) if needles_any else True
        all_ok = all(needle in answer for needle in needles_all) if needles_all else True
        none_ok = all(needle not in answer for needle in needles_none) if needles_none else True
        return {"key": "phrase_match", "score": int(any_ok and all_ok and none_ok)}

    def booking_match(run, example) -> dict:
        expected = bool((example.outputs or {}).get("appointment_created"))
        got = bool((run.outputs or {}).get("appointment_created"))
        return {"key": "booking_match", "score": int(got == expected)}

    evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[intent_match, phrase_match, booking_match],
        experiment_prefix="riverside-dental",
        metadata={"app": "riverside-dental-agent", "root": str(ROOT)},
    )
    print(f"LangSmith experiment uploaded for dataset '{DATASET_NAME}'.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the dentist-agent eval set")
    parser.add_argument(
        "--langsmith",
        action="store_true",
        help="Also upload the dataset and scores to LangSmith",
    )
    args = parser.parse_args()

    rows = run_local()
    code = print_report(rows)
    if args.langsmith:
        run_langsmith()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
