"""
FILE: src/forms_ingest.py
WHY: Save new-patient intake fields to the JSON database before any LLM
     call, so DOB / phone / insurance / medical notes never reach the model.
     Accepts labeled fields, a comma-separated line in the same order, or a
     follow-up value for whatever is still missing. The assistant only sees a
     sanitized note plus the patient name.
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

_DOB_RE = re.compile(r"^(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})$")
_NAME_RE = re.compile(
    r"^[A-Za-z][A-Za-z.'\-]+(?:\s+[A-Za-z][A-Za-z.'\-]+)+$"
)
_NEW_REQUEST_RE = re.compile(
    r"(?i)\b("
    r"book|cancel|appointment|reschedule|hours|available|"
    r"medicaid|dentist|cleaning|filling|braces|invisalign"
    r")\b"
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


def parse_unlabeled_fields(text: str) -> dict[str, str]:
    """Parse 'Name, DOB, Phone, Insurance[, Medical notes]' when unlabeled."""
    parts = [part.strip().rstrip(".,;") for part in text.split(",") if part.strip()]
    if len(parts) < 4:
        return {}
    if not _NAME_RE.fullmatch(parts[0]):
        return {}
    if not _DOB_RE.fullmatch(parts[1]):
        return {}
    phone_digits = re.sub(r"\D", "", parts[2])
    if len(phone_digits) < 10:
        return {}
    fields = {
        "name": parts[0],
        "date_of_birth": parts[1],
        "phone": parts[2],
        "insurance": parts[3],
    }
    if len(parts) >= 5:
        fields["medical_notes"] = ", ".join(parts[4:])
    return fields


def parse_followup_fields(text: str, missing: tuple[str, ...]) -> dict[str, str]:
    """Fill remaining intake fields from a short follow-up reply."""
    stripped = text.strip().rstrip(".,;")
    if not stripped or not missing or "?" in stripped:
        return {}
    if _NEW_REQUEST_RE.search(stripped) and len(missing) != 1:
        return {}
    parts = [part.strip().rstrip(".,;") for part in stripped.split(",") if part.strip()]
    if len(parts) == len(missing):
        return dict(zip(missing, parts))
    if len(missing) == 1 and not _NEW_REQUEST_RE.search(stripped):
        return {missing[0]: stripped}
    return {}


def _sanitized_note(fields: dict[str, str], missing: tuple[str, ...], remainder: str) -> str:
    if missing:
        labels = ", ".join(_FIELD_LABELS[key] for key in missing)
        who = f" for {fields['name']}" if fields.get("name") else ""
        prefix = f"[Intake incomplete{who}, missing: {labels}.]"
    else:
        name = fields["name"]
        prefix = f"[Intake saved for {name}; forms_complete=true.]"
    if remainder:
        return f"{prefix} {remainder}"
    return prefix


def ingest_forms(text: str, pending: dict[str, str] | None = None) -> IngestResult | None:
    """Merge this turn's intake with any pending fields and save when complete.

    Returns None when the message is not intake (and no follow-up applied).
    """
    pending = {key: value for key, value in (pending or {}).items() if value}
    labeled, spans = parse_labeled_fields(text)
    unlabeled = {} if labeled else parse_unlabeled_fields(text)
    missing_before = tuple(key for key in REQUIRED_FIELDS if not pending.get(key))
    followup = {}
    if pending and not labeled and not unlabeled:
        followup = parse_followup_fields(text, missing_before)

    if not labeled and not unlabeled and not followup:
        return None

    merged = {**pending, **unlabeled, **labeled, **followup}
    merged = {key: value.strip() for key, value in merged.items() if value and value.strip()}
    missing = tuple(key for key in REQUIRED_FIELDS if not merged.get(key))

    if labeled:
        remainder = strip_labeled_spans(text, spans)
    else:
        remainder = ""

    saved = False
    if not missing:
        submit_forms(
            merged["name"],
            merged["date_of_birth"],
            merged["phone"],
            merged["insurance"],
            merged["medical_notes"],
        )
        saved = True
    return IngestResult(
        fields=merged,
        missing=missing,
        saved=saved,
        sanitized=_sanitized_note(merged, missing, remainder),
    )


def ingest_labeled_forms(text: str) -> IngestResult | None:
    """Parse labeled intake fields. Save when complete; always strip values."""
    return ingest_forms(text)
