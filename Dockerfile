FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY controller.py ./

FROM python:3.11-slim
WORKDIR /app
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

COPY --from=builder /app/.venv ${VIRTUAL_ENV}
COPY --from=builder /app/controller.py ./controller.py

CMD ["kopf", "run", "--all-namespaces", "/app/controller.py"]
