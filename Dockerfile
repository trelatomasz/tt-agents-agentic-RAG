FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project
COPY src ./src
COPY data ./data
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src
USER 65532:65532
CMD ["sh", "-c", "uvicorn gpc_rag.main:app --host 0.0.0.0 --port ${PORT}"]
