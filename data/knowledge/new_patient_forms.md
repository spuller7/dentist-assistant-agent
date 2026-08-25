# New Patient Forms

Every new patient must submit intake forms before the first appointment can be booked.

Required form fields:

1. Full legal name
2. Date of birth
3. Phone number
4. Dental insurance name, or "none"
5. Brief medical notes (allergies, current medications, or "none")

Forms take about 15 minutes. In this demo, labeled intake fields (Name, Date of
birth, Phone, Insurance, Medical notes) are saved to the office database before
the language model sees the message. The assistant never receives those values.

Until forms are marked complete:

- The agent must not book a first visit.
- Ask the patient to send the required fields in one labeled line.

Returning patients already on file (Alex Rivera, Sam Ortiz) do not need to resubmit forms.
