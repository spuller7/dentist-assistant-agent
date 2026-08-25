"""
FILE: src/guardrails.py
WHY: Nice-to-have PII redaction. The live agent still sees the original
     message (it needs a phone number to save forms). LangSmith metadata
     and debug prints get the redacted copy instead.
"""

from __future__ import annotations

import re
from typing import Pattern

_RULES: list[tuple[str, Pattern[str]]] = [
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),
    ("PHONE", re.compile(r"\b(?:\+1[-.\s]?)?(?:\(?\d{3}\)?[-.\s])\d{3}[-.\s]?\d{4}\b")),
    ("PHONE", re.compile(r"\b\d{3}[-.\s]\d{4}\b")),
    ("DOB", re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")),
]


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Return (redacted_text, list of PII labels found)."""
    found: list[str] = []
    cleaned = text
    for label, pattern in _RULES:
        if pattern.search(cleaned):
            found.append(label)
            cleaned = pattern.sub(f"[REDACTED_{label}]", cleaned)
    return cleaned, found
