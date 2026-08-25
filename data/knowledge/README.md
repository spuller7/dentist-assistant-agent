# data/knowledge/

Tiny RAG corpus. `src/rag.py` keeps most notes as one document each.
`dentists.md` is the exception: it is split on `##` headings so each dentist
is its own segment. Every document keeps `source` (the filename) and
`section` (the heading) so retrieved notes are labeled with where they came from.

| File | Why it is here |
| --- | --- |
| `office_hours.md` | Hours, location, cancel policy, emergency phone. |
| `new_patient_forms.md` | What a new patient must submit before a first booking. |
| `dentists.md` | Who works here and when to pick each dentist. |
| `insurance_and_prep.md` | Insurance, visit lengths, and a few office rules. |
| `README.md` | This folder index. |
