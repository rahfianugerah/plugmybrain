# The optional HTTP surface over retrieval. Nothing on the agent path uses it: Claude Code and
# Codex reach the brain through a local stdio MCP process instead.
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from plugmybrain import retrieve

app = FastAPI(title="plugmybrain", description="Retrieval over the Cognee knowledge graph.")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/search")
async def search(
    q: str = Query(..., description="the question"),
    project: str = Query(
        ..., description="the dataset to search, required so projects stay isolated"
    ),
    mode: str = Query("chunks", description="chunks or graph"),
    top_k: int = Query(15, ge=1, le=100),
) -> dict[str, object]:
    if mode not in retrieve.MODES:
        raise HTTPException(status_code=400, detail=f"mode must be one of {list(retrieve.MODES)}")
    results = await retrieve.search(q, dataset=project, mode=mode, top_k=top_k)
    return {
        "project": project,
        "mode": mode,
        "sources": retrieve.sources(results),
        "results": results,
    }
