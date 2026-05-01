FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FANTASY_PL_PROJECT_ROOT=/app

WORKDIR /app

COPY pyproject.toml README.md fantasy-bodovani-fotbal.md run_today.sh /app/
COPY src /app/src

RUN pip install --upgrade pip setuptools wheel \
    && pip install . \
    && useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["fantasy-pl-api"]
