# Brain API

![FastAPI](https://img.shields.io/badge/FastAPI-0.1-009688?logo=fastapi&logoColor=white)
![API](https://img.shields.io/badge/API-v1-4C1D95)

Retrieval over the Cognee knowledge graph. Optional: Claude Code and Codex reach the brain
through a local stdio MCP process, so nothing on the agent path uses this.

Base URL, local: `http://127.0.0.1:8080`

## Authentication

None. The service binds to loopback locally, and on Cloud Run it is deployed without
`--allow-unauthenticated`. Adding auth is out of scope; do not expose this publicly as it is.

## Endpoints

| Method | Path | Purpose | Auth |
| :- | :- | :- | :- |
| GET | `/health` | Liveness, for the Cloud Run health check | No |
| GET | `/search` | Search one dataset | No |

### GET /health

```http
GET /health
```

```json
{ "status": "ok" }
```

### GET /search

```http
GET /search?q=what%20makes%20a%20value%20a%20secret&project=curated&mode=chunks&top_k=15
```

| Field | Required | Description |
| :- | :- | :- |
| `q` | Yes | The question |
| `project` | Yes | The dataset to search. Required, not defaulted, so projects stay isolated |
| `mode` | No | `chunks` (default, no completion step) or `graph` (one extra model call) |
| `top_k` | No | 1 to 100, default 15 |

```json
{
  "project": "curated",
  "mode": "chunks",
  "sources": ["secret.rules.md"],
  "results": []
}
```

## Errors

```json
{ "error": { "code": "string", "message": "string" } }
```

| Status | Means |
| :- | :- |
| 400 | `mode` was not `chunks` or `graph` |
| 422 | `q` or `project` was missing, or `top_k` was out of range |
| 500 | The database or the model provider was unreachable |

FastAPI returns its own `{"detail": ...}` shape for 400 and 422. Normalising that to the error
object above is not done, because nothing consumes this API yet.

## Rate Limits

None. The cost ceiling is `--max-instances 2` and, in `chunks` mode, the absence of a model
call per request.

## Notes

- `mode=chunks` returns retrieved context and its sources with no completion step. That is the
  cheap path and the default.
- `mode=graph` spends one model call to synthesise an answer.
- The container reads `PORT` rather than hardcoding 8080.

## Related

- [[docs.rules.md]]
- [[deploy.rules.md]]
