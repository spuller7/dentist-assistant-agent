# evals/

One small dataset and a runner that scores expected outcomes.

| File | Why it is here |
| --- | --- |
| `__init__.py` | Makes `evals` a package. |
| `dataset.json` | Cases with expected intent, required phrases, and whether a booking should happen. |
| `run_evals.py` | Local scoring, plus optional LangSmith upload. |
| `README.md` | This folder index. |

```bash
python -m evals.run_evals
python -m evals.run_evals --langsmith
```
