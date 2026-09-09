FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    FLI_DATA_DIR=/data

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev && mkdir -p /data

EXPOSE 8000

CMD ["/app/.venv/bin/google-flights-proto-web"]
