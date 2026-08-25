"""
FILE: src/forms_ingest.py
WHY: Save labeled new-patient intake fields to the JSON database before
     any LLM call, so DOB / phone / insurance / medical notes never reach
     the model. The assistant only sees a sanitized note plus the name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.db import submit_forms

REQUIRED_FIELDS = (
    "name",
    "date_of_birth",
    "phone",
    "insurance",
    "medical_notes",
)

_FIELD_LABELS = {
    "name": "Name",
    "date_of_birth": "Date of birth",
    "phone": "Phone",
    "insurance": "Insurance",
    "medical_notes": "Medical notes",
}

_LABEL_TO_FIELD = {
    "name": "name",
    "full name": "name",
    "full legal name": "name",
    "date of birth": "date_of_birth",
    "dob": "date_of_birth",
    "phone": "phone",
    "phone number": "phone",
    "insurance": "insurance",
    "dental insurance": "insurance",
    "medical notes": "medical_notes",
    "medical note": "medical_notes",
}

_LABEL_RE = re.compile(
    r"(?i)\b("
    r"full\s+legal\s+name|full\s+name|date\s+of\s+birth|medical\s+notes?|"
    r"phone\s+number|dental\s+insurance|insurance|dob|phone|name"
    r")\s*:\s*"
)


@dataclass(frozen=True)
class IngestResult:
    fields: dict[str, str]
    missing: tuple[str, ...]
    saved: bool
    sanitized: str


def _canonical_field(label: str) -> str | None:
    key = re.sub(r"\s+", " ", label.strip().lower())
    return _LABEL_TO_FIELD.get(key)


def parse_labeled_fields(text: str) -> tuple[dict[str, str], list[tuple[int, int]]]:
    """Return extracted fields and character spans to strip from the message."""
    matches = list(_LABEL_RE.finditer(text))
    fields: dict[str, str] = {}
    spans: list[tuple[int, int]] = []
    for index, match in enumerate(matches):
        field = _canonical_field(match.group(1))
        if not field:
            continue
        value_start = match.end()
        value_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        value = text[value_start:value_end].strip().rstrip(".,;")
        if value:
            fields[field] = value
        spans.append((match.start(), value_end))
    return fields, spans


def strip_labeled_spans(text: str, spans: list[tuple[int, int]]) -> str:
    result = text
    for start, end in reversed(spans):
        result = result[:start] + result[end:]
    cleaned = re.sub(r"\s+", " ", result).strip(" \t\r\n.,;")
    return cleaned


def _sanitized_note(fields: dict[str, str], missing: tuple[str, ...], remainder: str) -> str:
    if missing:
        labels = ", ".join(_FIELD_LABELS[key] for key in missing)
        prefix = f"[Intake incomplete, missing: {labels}.]"
    else:
        name = fields["name"]
        prefix = f"[Intake saved for {name}; forms_complete=true.]"
    if remainder:
        return f"{prefix} {remainder}"
    return prefix


def ingest_labeled_forms(text: str) -> IngestResult | None:
    """Parse labeled intake fields. Save when complete; always strip values.

    Returns None when the message has no labeled intake fields.
    """
    fields, spans = parse_labeled_fields(text)
    if not fields:
        return None

    missing = tuple(key for key in REQUIRED_FIELDS if not fields.get(key))
    remainder = strip_labeled_spans(text, spans)
    saved = False
    if not missing:
        submit_forms(
            fields["name"],
            fields["date_of_birth"],
            fields["phone"],
            fields["insurance"],
            fields["medical_notes"],
        )
        saved = True
    return IngestResult(
        fields=fields,
        missing=missing,
        saved=saved,
        sanitized=_sanitized_note(fields, missing, remainder),
    )
