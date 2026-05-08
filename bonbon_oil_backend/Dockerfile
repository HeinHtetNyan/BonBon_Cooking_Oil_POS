# syntax=docker/dockerfile:1.7
ARG PYTHON_VERSION=3.13

# Stage: base — shared Python runtime
FROM python:${PYTHON_VERSION}-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Stage: dependencies — install Python packages
FROM base AS dependencies

COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install -e ".[dev]"

# Stage: development
FROM dependencies AS development

COPY . .

RUN addgroup --system bonbon && \
    adduser --system --group bonbon && \
    mkdir -p /var/log/bonbon_oil && \
    chown -R bonbon:bonbon /app /var/log/bonbon_oil

USER bonbon

EXPOSE 8000

# Stage: production
FROM base AS production

COPY pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install -e "."  # no dev deps

COPY . .

RUN addgroup --system bonbon && \
    adduser --system --group bonbon && \
    mkdir -p /var/log/bonbon_oil && \
    chown -R bonbon:bonbon /app /var/log/bonbon_oil

USER bonbon

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
