# Retrieval. Chunks by default, so the agent path never pays for a second model call.
from __future__ import annotations

from brain import config

MODES = ("chunks", "graph")


async def search(query: str, dataset: str, mode: str = "chunks", top_k: int = 15) -> list:
    """Search one dataset. `chunks` returns sourced context with no completion step;
    `graph` spends an extra model call to synthesise an answer from the graph.

    The dataset is required rather than defaulted, which is what keeps projects isolated.
    """
    if mode not in MODES:
        raise SystemExit(f"unknown mode {mode!r}. Use one of: {', '.join(MODES)}")

    config.configure()
    import cognee
    from cognee import SearchType

    if mode == "graph":
        return await cognee.search(
            query_text=query,
            query_type=SearchType.GRAPH_COMPLETION,
            datasets=[dataset],
            top_k=top_k,
        )

    # only_context skips the completion step, so this returns retrieved chunks and their
    # sources rather than prose. That is the cheap path and the default.
    return await cognee.search(
        query_text=query,
        query_type=SearchType.CHUNKS,
        datasets=[dataset],
        top_k=top_k,
        only_context=True,
    )


def sources(results: list) -> list[str]:
    """The source file names cited by a result set, in order, de-duplicated."""
    seen: list[str] = []
    for item in results:
        for value in _walk(item):
            name = value.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if name and name not in seen:
                seen.append(name)
    return seen


def _walk(value: object) -> list[str]:
    """Every file-ish string inside a result, whatever shape cognee returned it in."""
    found: list[str] = []
    if isinstance(value, str):
        if "." in value and ("/" in value or "\\" in value):
            found.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in ("file_path", "source", "sourceFile", "name") and isinstance(item, str):
                found.append(item)
            else:
                found.extend(_walk(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(_walk(item))
    elif hasattr(value, "__dict__"):
        found.extend(_walk(vars(value)))
    return found
