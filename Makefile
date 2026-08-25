# FILE: Makefile
# WHY: One-command setup, run, graph print, and evals. Nice-to-have for reviewers.

.PHONY: setup run eval eval-smith graph reset docker-build docker-run

setup:
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt || .venv/Scripts/pip install -r requirements.txt
	@echo "Copy .env.example to .env and add OPENAI_API_KEY and LANGSMITH_API_KEY."

run:
	python -m src.cli

eval:
	python -m evals.run_evals

eval-smith:
	python -m evals.run_evals --langsmith

graph:
	python -m src.cli --graph

reset:
	python -m src.cli --reset-db

docker-build:
	docker build -t riverside-dental-agent .

docker-run:
	docker run --rm -it --env-file .env riverside-dental-agent
