FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8090

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY scripts ./scripts
COPY docs ./docs

RUN pip install --upgrade pip && pip install .

EXPOSE 8090

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
