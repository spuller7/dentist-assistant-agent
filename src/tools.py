"""
FILE: src/tools.py
WHY: LangChain tools the model can call. Each one is a thin wrapper over
     the JSON database so the graph never has to know how files are stored.
"""

from __future__ import annotations

from langchain_core.tools import tool

from src import db


@tool
def lookup_patient(name: str) -> str:
    """Look up a patient by name. Use this before booking or cancelling."""
    patient = db.find_patient(name)
    if not patient:
        return (
            f"{name} is not on file. Treat them as a new patient. "
            "They must submit intake forms before an appointment can be booked."
        )
    status = "complete" if patient.get("forms_complete") else "incomplete"
    preferred = patient.get("preferred_dentist_id") or "none"
    return (
        f"Found {patient['name']} (id={patient['id']}). "
        f"new_patient={patient.get('is_new', False)}, forms={status}, "
        f"preferred_dentist={preferred}, insurance={patient.get('insurance', 'unknown')}."
    )


@tool
def list_dentists(name_or_specialty: str = "any") -> str:
    """List dentists. Pass a name, a specialty, or 'any'."""
    unknown = db.unknown_dentist_error(name_or_specialty)
    if unknown:
        return unknown
    office = db.load_office()
    dentist = None if db.is_any_dentist(name_or_specialty) else db.find_dentist(name_or_specialty, office)
    pool = [dentist] if dentist else office["dentists"]
    lines = [
        f"{row['name']} ({row['id']}) — {row['specialty']}; days: {', '.join(row['working_days'])}"
        for row in pool
    ]
    return "\n".join(lines)


@tool
def get_open_slots(dentist: str = "any", day: str = "", service: str = "") -> str:
    """Get open appointment slots. dentist can be a name or 'any'. day can be today, tomorrow, YYYY-MM-DD, a weekday, or empty for the next two weeks. service is the visit type (cleaning, braces, child exam, extraction) and filters to matching dentists when dentist is 'any'."""
    result = db.open_slots(dentist, day=day or None, service=service or None)
    if result.get("unknown_dentist"):
        return result["error"]
    if result.get("error") and not result.get("ok", True):
        return result["error"]
    slots = result["slots"]
    if not slots:
        return f"No open slots for dentist='{dentist}' service='{service or 'any'}' day='{day or 'next 14 days'}'."
    if day:
        preview = slots
        extra = ""
    else:
        first_date = slots[0]["date"]
        preview = [row for row in slots if row["date"] == first_date]
        later = len(slots) - len(preview)
        extra = f"\n({later} more slots on later days not shown.)" if later else ""
    lines = [f"{row['date']} {row['weekday']} {row['time']} with {row['dentist_name']} ({row['specialty']})" for row in preview]
    return "\n".join(lines) + extra


@tool
def submit_new_patient_forms(
    name: str,
    date_of_birth: str,
    phone: str,
    insurance: str,
    medical_notes: str,
) -> str:
    """Save new-patient intake forms. Required before a first appointment can be booked."""
    result = db.submit_forms(name, date_of_birth, phone, insurance, medical_notes)
    if result.get("already_on_file"):
        return f"{name} is already on file with completed forms."
    return f"Forms saved for {name}. They can now book an appointment."


@tool
def book_appointment(patient_name: str, dentist: str, day: str, time: str, reason: str) -> str:
    """Book an appointment. dentist can be a name or 'any'. day is today, tomorrow, YYYY-MM-DD, or a weekday. time is like 14:00 or 2pm."""
    result = db.book_appointment(patient_name, dentist, day, time, reason)
    if not result.get("ok"):
        suggestions = result.get("suggestions") or []
        hint = ""
        if suggestions:
            hint = " Nearby opens: " + "; ".join(
                f"{row['date']} {row['time']} {row['dentist_name']}" for row in suggestions
            )
        return f"Booking failed: {result.get('error')}{hint}"
    appt = result["appointment"]
    return (
        f"Booked {appt['patient_name']} with {appt['dentist_name']} "
        f"on {appt['date']} at {appt['time']} for {appt['reason']} (id={appt['id']})."
    )


@tool
def cancel_appointment(patient_name: str, day: str = "") -> str:
    """Cancel a patient's appointment. Pass today, tomorrow, a date, or a weekday to cancel one visit, or omit day to cancel all of theirs."""
    result = db.cancel_appointment(patient_name, day=day or None)
    if not result.get("ok"):
        return f"Cancel failed: {result.get('error')}"
    parts = [f"{row['date']} {row['time']} with {row['dentist_name']}" for row in result["cancelled"]]
    return "Cancelled: " + "; ".join(parts)


SCHEDULING_TOOLS = [
    lookup_patient,
    list_dentists,
    get_open_slots,
    submit_new_patient_forms,
    book_appointment,
    cancel_appointment,
]
