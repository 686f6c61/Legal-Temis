FROM python:3.14.6-slim AS constructor

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.14.6-slim

RUN useradd --create-home --shell /usr/sbin/nologin legislacion
WORKDIR /app
COPY --from=constructor /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER legislacion

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/salud', timeout=3)"]

CMD ["uvicorn", "legislacion.app:app", "--host", "0.0.0.0", "--port", "8000"]
