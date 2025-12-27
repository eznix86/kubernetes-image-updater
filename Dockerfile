FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv pip install --system --frozen --no-cache -r pyproject.toml

COPY operator.py ./

CMD ["kopf", "run", "/app/operator.py"]
