FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 POETRY_VIRTUALENVS_CREATE=false
WORKDIR /app
RUN pip install poetry==2.5.1
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root --no-interaction
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 libgomp1 && rm -rf /var/lib/apt/lists/*
RUN python -c "import rasterio, onnxruntime"
COPY api ./api
COPY models ./models
COPY worker ./worker
COPY scripts ./scripts
COPY modelos ./modelos
RUN useradd --uid 10001 --create-home geo && chown -R geo:geo /app
USER geo
CMD ["uvicorn","api.index:app","--host","0.0.0.0","--port","8000","--proxy-headers"]
