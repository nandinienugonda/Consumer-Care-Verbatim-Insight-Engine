# Build context is the repository root (see docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MIGRATIONS_DIR=/app/db/migrations

WORKDIR /app

COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/src backend/src
RUN pip install ./backend

COPY db/migrations db/migrations

RUN useradd --system --uid 10001 ccvie
USER ccvie

EXPOSE 8000
CMD ["uvicorn", "ccvie.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
