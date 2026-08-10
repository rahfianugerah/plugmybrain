# One image, two entrypoints: cognee-mcp serves, cognee-ingest runs once and exits.
FROM python:3.13-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt \
 # --no-deps on purpose: cognee-mcp declares cognee[docs,neo4j,postgres-binary], and the docs
 # extra pulls torch, triton and 2.7GB of CUDA libraries onto a VM with no GPU. Base cognee
 # and the two packages in requirements.txt are everything it imports.
 && pip install --no-cache-dir --prefix=/install --no-deps cognee-mcp==0.5.5

FROM python:3.13-slim
RUN useradd -m app
COPY --from=build /install /usr/local
COPY --chown=app:app . /app
WORKDIR /app
RUN pip install --no-cache-dir --no-deps -e . \
 # An empty named volume inherits ownership from the image's directory at the mount point.
 # Without this, /data arrives root-owned, and a container that correctly runs as non-root
 # cannot create cognee's state directory inside it.
 && mkdir -p /data && chown app:app /data
USER app
# Overridden per service in compose.yaml. The default is the serving path, because a container
# started with no command should serve rather than mutate anything.
CMD ["cognee-mcp", "--transport", "http"]
