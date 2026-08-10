# One image, two entrypoints: cognee-mcp serves, cognee-ingest runs once and exits.
FROM python:3.13-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
RUN useradd -m app
COPY --from=build /install /usr/local
COPY --chown=app:app . /app
WORKDIR /app
RUN pip install --no-cache-dir --no-deps -e .
USER app
# Overridden per service in compose.yaml. The default is the serving path, because a container
# started with no command should serve rather than mutate anything.
CMD ["cognee-mcp", "--transport", "http"]
