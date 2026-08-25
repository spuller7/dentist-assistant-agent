## Setup

You need Python 3.11+ and two API keys: OpenAI (model calls) and LangSmith (traces / evals).

### Windows

```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
```

Edit `.env` and set `OPENAI_API_KEY` and `LANGSMITH_API_KEY`.

### Mac / Linux

```bash
make setup
source .venv/bin/activate
cp .env.example .env
```

### Run

```bash
python -m src.cli
```

Useful commands:

```bash
python -m src.cli --graph          # print the workflow
python -m src.cli --reset-db       # restore data/office.json from the seed
python -m src.cli --once "Are you open Saturday?"
python -m evals.run_evals          # local expected-outcome scores
python -m evals.run_evals --langsmith
```

Inside the chat you can type `graph`, `reset`, or `quit`.

### Docker

```bash
docker build -t riverside-dental-agent .
docker run --rm -it --env-file .env riverside-dental-agent
```

## Try these prompts

```
Are you open on Saturday?
Do you take Medicaid?
I am Alex Rivera. Book a cleaning with Dr. Chen on Tuesday at 2pm.
This is Sam Ortiz. Any dentist Friday at 9am for a checkup.
I am a new patient named Jamie Cole. Book me tomorrow morning.
Please file my new patient forms. Name: Jamie Cole. Date of birth: 1994-02-08. Phone: 555-0199. Insurance: none. Medical notes: no allergies.
```

After Jamie's forms are saved, ask again to book any dentist. The second turn should succeed.