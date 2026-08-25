# src/

Application code. Start with `state.py` and `graph.py`.

| File | Why it is here |
| --- | --- |
| `__init__.py` | Makes `src` a package. |
| `__main__.py` | Allows `python -m src`. |
| `paths.py` | Root / data / db locations, including the eval override. |
| `db.py` | JSON database helpers used by every scheduling tool. |
| `guardrails.py` | PII redaction for logs and LangSmith metadata. |
| `rag.py` | LangChain BM25 retriever over `data/knowledge`. |
| `llm.py` | LangChain `ChatOpenAI` factory. |
| `state.py` | LangGraph state schema. |
| `tools.py` | LangChain tools (patient lookup, slots, book, forms, cancel). |
| `graph.py` | Nodes, edges, and compile step. |
| `cli.py` | Streaming CLI. |
| `README.md` | This folder index. |
