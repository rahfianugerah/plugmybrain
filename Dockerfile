# The MCP server image. Digests run inside it as a subprocess, so nothing else is needed.
FROM python:3.13-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim
RUN useradd -m app
COPY --from=build /install /usr/local
COPY --chown=app:app . /app
WORKDIR /app
# An empty named volume takes the owner of its mount point, so /data must belong to app
RUN pip install --no-cache-dir --no-deps -e . \
 && mkdir -p /data /docs /workspace /app/graph \
 && chown app:app /data /docs /app/graph
USER app
CMD ["python", "-m", "plugmybrain.server"]
