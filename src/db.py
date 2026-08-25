"""
FILE: src/db.py
WHY: The "database" for this demo is one JSON file. Tools never invent
     dentists or open slots; they read and write through these helpers.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.paths import SEED_DB, db_path

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def reset_db(dest: Path | None = None) -> Path:
    """Copy the committed seed file over the working database."""
    target = dest or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SEED_DB, target)
    return target


def load_office() -> dict[str, Any]:
    path = db_path()
    if not path.exists():
        reset_db(path)
    return json.loads(path.read_text(encoding="utf-8"))


def save_office(office: dict[str, Any]) -> None:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(office, indent=2) + "\n", encoding="utf-8")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


ANY_DENTIST = {"any", "anyone", "either", "no preference", ""}

SERVICE_TO_SPECIALTY = {
    "cleaning": "General Dentistry",
    "checkup": "General Dentistry",
    "check up": "General Dentistry",
    "exam": "General Dentistry",
    "exams": "General Dentistry",
    "filling": "General Dentistry",
    "fillings": "General Dentistry",
    "general": "General Dentistry",
    "braces": "Orthodontics",
    "invisalign": "Orthodontics",
    "retainer": "Orthodontics",
    "retainers": "Orthodontics",
    "ortho": "Orthodontics",
    "orthodontics": "Orthodontics",
    "alignment": "Orthodontics",
    "child": "Pediatric Dentistry",
    "kid": "Pediatric Dentistry",
    "kids": "Pediatric Dentistry",
    "pediatric": "Pediatric Dentistry",
    "paediatric": "Pediatric Dentistry",
    "extraction": "Oral Surgery",
    "extractions": "Oral Surgery",
    "wisdom": "Oral Surgery",
    "surgery": "Oral Surgery",
    "surgical": "Oral Surgery",
    "oral surgery": "Oral Surgery",
}

PEDIATRIC_SERVICE_KEYS = ("child", "kid", "kids", "pediatric", "paediatric")


def is_any_dentist(query: str | None) -> bool:
    return _norm(query or "") in ANY_DENTIST


def specialty_for_service(service: str | None) -> str | None:
    """Map a visit type (cleaning, braces, child exam, …) to a specialty."""
    q = _norm(service or "")
    if not q:
        return None
    tokens = q.split()
    if any(key == q or key in tokens for key in PEDIATRIC_SERVICE_KEYS):
        return "Pediatric Dentistry"
    if q in SERVICE_TO_SPECIALTY:
        return SERVICE_TO_SPECIALTY[q]
    for key, specialty in sorted(SERVICE_TO_SPECIALTY.items(), key=lambda item: -len(item[0])):
        if key in q:
            return specialty
    return None


def stated_service(text: str | None) -> str | None:
    """Return a canonical visit-type keyword if the caller already named one."""
    q = _norm(text or "")
    if not q:
        return None
    if specialty_for_service(q) == "Pediatric Dentistry":
        return "pediatric"
    for key in sorted(SERVICE_TO_SPECIALTY, key=len, reverse=True):
        if key in q:
            return key
    return None


def dentist_roster(office: dict[str, Any] | None = None) -> str:
    office = office or load_office()
    return "; ".join(f"{row['name']} ({row['specialty']})" for row in office["dentists"])


def unknown_dentist_error(query: str, office: dict[str, Any] | None = None) -> str | None:
    """If the query names someone who is not on staff, explain that and list who is."""
    office = office or load_office()
    if is_any_dentist(query):
        return None
    if find_dentist(query, office):
        return None
    return (
        f"No dentist named {query} is on staff. "
        f"Available dentists: {dentist_roster(office)}"
    )


def find_dentist(query: str, office: dict[str, Any] | None = None) -> dict[str, Any] | None:
    office = office or load_office()
    q = _norm(query)
    if is_any_dentist(q):
        return None
    for dentist in office["dentists"]:
        names = [dentist["name"], dentist["id"], dentist["specialty"], *dentist.get("aliases", [])]
        if any(q == _norm(name) or q in _norm(name) or _norm(name) in q for name in names):
            return dentist
    return None


def find_patient(name: str, office: dict[str, Any] | None = None) -> dict[str, Any] | None:
    office = office or load_office()
    q = _norm(name)
    for patient in office["patients"]:
        if q == _norm(patient["name"]) or q in _norm(patient["name"]):
            return patient
    return None


def today_context(now: datetime | None = None) -> str:
    """Human-readable date and time line for agent system prompts."""
    now = now or datetime.now()
    weekday = WEEKDAYS[now.weekday()]
    clock_12 = now.strftime("%I:%M %p").lstrip("0")
    clock_24 = now.strftime("%H:%M")
    return (
        f"Today is {weekday}, {now.strftime('%B %d, %Y')} ({now.date().isoformat()}). "
        f"The current local time is {clock_12} ({clock_24})."
    )


def parse_date(value: str, today: date | None = None) -> str | None:
    """Accept YYYY-MM-DD, today/tomorrow, a weekday, or month+day. Returns ISO date or None."""
    today = today or date.today()
    raw = value.strip()
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
        return parsed.isoformat()
    except ValueError:
        pass

    token = _norm(raw)
    relative = {"today": 0, "tonight": 0, "now": 0, "tomorrow": 1, "tmrw": 1}
    if token in relative:
        return (today + timedelta(days=relative[token])).isoformat()

    in_days = re.fullmatch(r"in (\d+) days?", token)
    if in_days:
        return (today + timedelta(days=int(in_days.group(1)))).isoformat()

    for offset in range(0, 14):
        candidate = today + timedelta(days=offset)
        if WEEKDAYS[candidate.weekday()].lower() == token:
            return candidate.isoformat()
        if token in {candidate.strftime("%b %d").lower(), candidate.strftime("%B %d").lower()}:
            return candidate.isoformat()
    return None


def parse_time(value: str) -> str | None:
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", value.strip(), flags=re.I)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _weekday_name(iso_date: str) -> str:
    return WEEKDAYS[datetime.strptime(iso_date, "%Y-%m-%d").date().weekday()]


def open_slots(
    dentist_query: str = "any",
    day: str | None = None,
    service: str | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return bookable slots for the next two weeks (or one requested day)."""
    now = now or datetime.now()
    today = today or now.date()
    current_hhmm = now.strftime("%H:%M")
    office = load_office()
    unknown = unknown_dentist_error(dentist_query, office)
    if unknown:
        return {"ok": False, "unknown_dentist": True, "error": unknown, "slots": []}

    booked = {(a["dentist_id"], a["date"], a["time"]) for a in office["appointments"]}
    dentists = office["dentists"]
    chosen = find_dentist(dentist_query, office) if dentist_query else None
    if chosen:
        dentists = [chosen]
    elif service:
        specialty = specialty_for_service(service)
        if not specialty:
            return {
                "ok": False,
                "unknown_dentist": False,
                "error": (
                    f"Unknown service '{service}'. Use cleaning, exam, filling, "
                    "braces, a child visit, or extraction/surgery."
                ),
                "slots": [],
            }
        dentists = [row for row in dentists if row["specialty"] == specialty]
        if not dentists:
            return {
                "ok": False,
                "unknown_dentist": False,
                "error": f"No dentist on staff for {service}.",
                "slots": [],
            }

    wanted = parse_date(day, today=today) if day else None
    days = [wanted] if wanted else [(today + timedelta(days=i)).isoformat() for i in range(0, 14)]

    results: list[dict[str, str]] = []
    for iso in days:
        if datetime.strptime(iso, "%Y-%m-%d").date() < today:
            continue
        weekday = _weekday_name(iso)
        for dentist in dentists:
            if weekday not in dentist["working_days"]:
                continue
            for slot in dentist["slots"]:
                if iso == today.isoformat() and slot <= current_hhmm:
                    continue
                if (dentist["id"], iso, slot) in booked:
                    continue
                results.append(
                    {
                        "dentist_id": dentist["id"],
                        "dentist_name": dentist["name"],
                        "specialty": dentist["specialty"],
                        "date": iso,
                        "weekday": weekday,
                        "time": slot,
                    }
                )
    return {"ok": True, "unknown_dentist": False, "slots": results}


def book_appointment(
    patient_name: str,
    dentist_query: str,
    day: str,
    time: str,
    reason: str,
) -> dict[str, Any]:
    office = load_office()
    patient = find_patient(patient_name, office)
    if not patient:
        return {
            "ok": False,
            "error": "Patient is not on file. New patients must submit intake forms first.",
        }
    if not patient.get("forms_complete"):
        return {
            "ok": False,
            "error": "New-patient forms are incomplete. Collect the required form fields before booking.",
        }

    iso_date = parse_date(day)
    clock = parse_time(time)
    if not iso_date or not clock:
        return {"ok": False, "error": "Could not read that date or time. Use YYYY-MM-DD and HH:MM."}

    slot_result = open_slots(dentist_query, day=iso_date, service=reason)
    if slot_result.get("unknown_dentist") or not slot_result.get("ok", True):
        return {
            "ok": False,
            "error": slot_result.get("error") or "That slot is not open.",
            "unknown_dentist": bool(slot_result.get("unknown_dentist")),
        }
    slots = slot_result["slots"]
    match = next((slot for slot in slots if slot["time"] == clock), None)
    if not match:
        return {
            "ok": False,
            "error": f"That slot is not open for {dentist_query} on {iso_date} at {clock}.",
            "suggestions": slots[:5],
        }

    appointment = {
        "id": f"apt-{uuid.uuid4().hex[:8]}",
        "patient_id": patient["id"],
        "patient_name": patient["name"],
        "dentist_id": match["dentist_id"],
        "dentist_name": match["dentist_name"],
        "date": match["date"],
        "time": match["time"],
        "reason": reason,
    }
    office["appointments"].append(appointment)
    save_office(office)
    return {"ok": True, "appointment": appointment}


def submit_forms(
    name: str,
    date_of_birth: str,
    phone: str,
    insurance: str,
    medical_notes: str,
) -> dict[str, Any]:
    office = load_office()
    existing = find_patient(name, office)
    if existing and existing.get("forms_complete"):
        return {"ok": True, "already_on_file": True, "patient": existing}

    patient = existing or {
        "id": f"p-{uuid.uuid4().hex[:8]}",
        "name": name,
        "is_new": True,
    }
    patient.update(
        {
            "phone": phone,
            "date_of_birth": date_of_birth,
            "forms_complete": True,
            "insurance": insurance,
            "medical_notes": medical_notes,
            "preferred_dentist_id": patient.get("preferred_dentist_id"),
        }
    )
    if existing:
        for index, row in enumerate(office["patients"]):
            if row["id"] == existing["id"]:
                office["patients"][index] = patient
                break
    else:
        office["patients"].append(patient)
    save_office(office)
    return {"ok": True, "already_on_file": False, "patient": patient}


def cancel_appointment(patient_name: str, day: str | None = None) -> dict[str, Any]:
    office = load_office()
    patient = find_patient(patient_name, office)
    if not patient:
        return {"ok": False, "error": "No patient by that name is on file."}

    iso_date = parse_date(day) if day else None
    remaining = []
    cancelled = []
    for appointment in office["appointments"]:
        same_person = appointment["patient_id"] == patient["id"]
        same_day = iso_date is None or appointment["date"] == iso_date
        if same_person and same_day:
            cancelled.append(appointment)
        else:
            remaining.append(appointment)

    if not cancelled:
        return {"ok": False, "error": "No matching appointment to cancel."}

    office["appointments"] = remaining
    save_office(office)
    return {"ok": True, "cancelled": cancelled}
