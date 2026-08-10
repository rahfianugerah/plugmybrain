# One image, two entrypoints: the Cloud Run service runs the API, the Cloud Run Job runs ingest.
FROM python:3.13-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
RUN useradd -m app
COPY --from=build /install /usr/local
COPY --chown=app:app . /app
WORKDIR /app
USER app
# Cloud Run injects PORT. Reading it rather than hardcoding 8080 is the difference between a
# working revision and "the container failed to start and listen on the port".
CMD exec uvicorn brain.api:app --host 0.0.0.0 --port ${PORT:-8080}
