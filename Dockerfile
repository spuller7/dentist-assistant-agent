# FILE: Dockerfile
# WHY: Nice-to-have. Lets a reviewer run the CLI without installing Python locally.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.cli"]
