# New Patient Forms

Every new patient must submit intake forms before the first appointment can be booked.

Required form fields:

1. Full legal name
2. Date of birth
3. Phone number
4. Dental insurance name, or "none"
5. Brief medical notes (allergies, current medications, or "none")

Forms take about 15 minutes. In this demo, intake is saved to the office
database before the language model sees it. Patients may send:

- Labeled fields: `Name: … Date of birth: … Phone: … Insurance: … Medical notes: …`
- The same five values in one comma-separated line, in that order
- A follow-up with only the missing field (for example `none` for medical notes)

The assistant never receives date of birth, phone, insurance, or medical notes.

Until forms are marked complete:

- The agent must not book a first visit.
- Ask only for the fields that are still missing.

Returning patients who are already on file do not need to resubmit forms.
Confirm that by looking up the name they provide. Never assume who is calling.
