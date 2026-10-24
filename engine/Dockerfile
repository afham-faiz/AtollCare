# F-M7.1 / F-M7.3 Engine image (FastAPI + uv)
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /engine
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY tests ./tests

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
