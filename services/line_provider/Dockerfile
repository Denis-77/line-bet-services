FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml ./

RUN poetry config virtualenvs.create false && poetry install --no-interaction --no-ansi

COPY src ./src
