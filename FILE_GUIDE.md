# File-by-file readme

This is the readme for every file in the project: what it is, and why it was included.

---

## Root

### `README.md`
**Purpose:** How to run the demo, what the agent does, and how the graph decides.
**Why included:** A reviewer should be able to set keys, start the CLI, and understand the workflow without opening every source file.

### `FILE_GUIDE.md`
**Purpose:** This document.
**Why included:** You asked for a readme for each file, with the reason it exists.

### `.env.example`
**Purpose:** Names of the keys the app reads.
**Why included:** LangChain needs an OpenAI key. LangSmith needs a tracing key. The example file shows both without putting secrets in git.

### `.gitignore`
**Purpose:** Ignore `.venv`, `.env`, and cache files.
**Why included:** Keeps keys and local junk out of version control.

### `requirements.txt`
**Purpose:** Python packages for LangChain, LangGraph, LangSmith, BM25, and dotenv.
**Why included:** One install command should recreate the demo.

### `Makefile`
**Purpose:** `setup`, `run`, `eval`, `reset`, and Docker shortcuts.
**Why included:** Nice-to-have setup script for Mac/Linux reviewers.

### `setup.ps1`
**Purpose:** Same setup on Windows PowerShell.
**Why included:** This workspace is on Windows. Make is not always installed.

### `Dockerfile`
**Purpose:** Run the CLI in a container.
**Why included:** Nice-to-have. A reviewer can try the app without a local venv.

### `.dockerignore`
**Purpose:** Keep `.venv`, `.env`, and git metadata out of the image.
**Why included:** The Docker build should not copy secrets or the local virtualenv.

---

## `data/`

### `data/README.md`
**Purpose:** Index of the JSON database and knowledge folder.
**Why included:** Folder-level readme so the data files are not unexplained.

### `data/office.seed.json`
**Purpose:** Clean snapshot of dentists, two returning patients, and two already-booked visits.
**Why included:** Reset and evals copy from this file so a demo booking does not permanently change the starting world.

### `data/office.json`
**Purpose:** The live JSON database tools read and write.
**Why included:** The challenge allows a JSON file instead of a real database. This is that file.

### `data/knowledge/README.md`
**Purpose:** Index of the RAG documents.
**Why included:** Explains why the knowledge base is split into four short notes.

### `data/knowledge/office_hours.md`
**Purpose:** Hours, parking, cancel fee, emergency phone.
**Why included:** FAQ questions need a source of truth.

### `data/knowledge/new_patient_forms.md`
**Purpose:** Required intake fields and the "no booking until forms are done" rule.
**Why included:** The agent has to know why a new patient is blocked.

### `data/knowledge/dentists.md`
**Purpose:** Four dentists, specialties, and when to pick each one.
**Why included:** Patients can ask for a named dentist or "any dentist." Retrieval should know the difference.

### `data/knowledge/insurance_and_prep.md`
**Purpose:** PPO list, Medicaid (not accepted), visit lengths.
**Why included:** A second FAQ path so RAG is not only about hours.

---

## `src/`

### `src/README.md`
**Purpose:** Index of the Python modules.
**Why included:** Points a reviewer at `state.py` and `graph.py` first.

### `src/__init__.py`
**Purpose:** Marks `src` as a package.
**Why included:** Needed for `python -m src.cli` and for evals to import the graph.

### `src/__main__.py`
**Purpose:** Entry point for `python -m src`.
**Why included:** Slightly shorter command than `python -m src.cli`.

### `src/paths.py`
**Purpose:** Resolves project folders and `OFFICE_DB_PATH`.
**Why included:** Evals point the database at a temp file. That override lives in one place.

### `src/db.py`
**Purpose:** Load/save JSON, find patients/dentists, compute open slots, book, cancel, save forms.
**Why included:** Tools should not contain file-handling details. This is the only place JSON is written.

### `src/guardrails.py`
**Purpose:** Regex redaction for SSN, email, phone, and slash-style dates.
**Why included:** Nice-to-have PII guardrail. The original text still goes to tools (a phone number is needed to save forms). The redacted copy is what we attach to LangSmith metadata.

### `src/rag.py`
**Purpose:** Split markdown notes into heading segments, keep the source filename on each one, and retrieve with LangChain `BM25Retriever`.
**Why included:** The challenge requires LangChain RAG. BM25 keeps that requirement without a vector database or embeddings key. Source labels show which knowledge file a retrieved segment came from.

### `src/llm.py`
**Purpose:** Build `ChatOpenAI` from `.env`.
**Why included:** Every model call should go through one factory so tracing and the model name stay consistent.

### `src/state.py`
**Purpose:** TypedDict for graph state: messages, raw text, redacted text, intent, retrieved notes, PII labels.
**Why included:** Graph clarity starts with the state schema. Nodes only return the fields they change.

### `src/tools.py`
**Purpose:** Six LangChain `@tool` functions the assistant can call.
**Why included:** The challenge requires at least one tool. These are the office actions: lookup, list dentists, slots, forms, book, cancel.

### `src/graph.py`
**Purpose:** Wire the nodes and edges, then compile the graph.
**Why included:** This is the LangGraph control flow. Classify decides FAQ vs scheduling. FAQ ends after a grounded answer. Scheduling loops through tools until the model stops calling them.

### `src/cli.py`
**Purpose:** Interactive chat, `--reset-db`, `--once`, and streamed tokens.
**Why included:** The challenge allows a CLI. Streaming is a nice-to-have.

---

## `evals/`

### `evals/README.md`
**Purpose:** How to run the dataset.
**Why included:** Folder-level readme for the eval entry point.

### `evals/__init__.py`
**Purpose:** Marks `evals` as a package.
**Why included:** Needed for `python -m evals.run_evals`.

### `evals/dataset.json`
**Purpose:** Seven cases with expected intent, required phrases, and whether a booking should be written.
**Why included:** The challenge asks for one small dataset with expected outcomes.

### `evals/run_evals.py`
**Purpose:** Run each case against a temp copy of the database. Optionally upload the same scores to LangSmith.
**Why included:** Local evals work even if you only want a terminal report. `--langsmith` satisfies the LangSmith eval requirement.
