# One image, two entrypoints: the MCP server serves, `pmb` runs once and exits.
FROM python:3.13-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
RUN useradd -m app
COPY --from=build /install /usr/local
COPY --chown=app:app . /app
WORKDIR /app
RUN pip install --no-cache-dir --no-deps -e . \
 # An empty named volume inherits ownership from the image's directory at the mount point.
 # Without this, /data arrives root-owned, and a container that correctly runs as non-root
 # cannot create cognee's state directory inside it.
 && mkdir -p /data /docs && chown app:app /data /docs
USER app
# Overridden per service in compose.yaml. The default is the serving path, because a container
# started with no command should serve rather than mutate anything.
CMD ["python", "-m", "plugmybrain.server"]
