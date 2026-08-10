# Cognee knowledge graph to Obsidian wikilink notes. Writes only under the vault generated area.
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from plugmybrain import config

# A vault is a human-readable thing. Dumping ten thousand generated notes into one makes the
# graph view useless, so the export is capped and says what it dropped.
DEFAULT_LIMIT = 500


@dataclass
class ExportReport:
    dataset: str
    written: int
    total: int
    directory: Path

    @property
    def dropped(self) -> int:
        return max(0, self.total - self.written)


def slug(text: str) -> str:
    """A filename from a node label. Stable, so a re-export overwrites rather than duplicates."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (cleaned or "node")[:60]


def _unpack_node(node: object) -> tuple[str, str]:
    """(id, label) for a graph node, whichever shape the adapter returned."""
    if isinstance(node, (tuple, list)) and len(node) == 2:
        node_id, properties = node[0], node[1] or {}
    else:
        node_id, properties = getattr(node, "id", None), getattr(node, "properties", None) or {}
    if node_id is None:
        raise SystemExit(f"unrecognised node shape from the graph engine: {type(node).__name__}")
    if not isinstance(properties, dict):
        properties = {}
    label = properties.get("name") or properties.get("text") or str(node_id)
    return str(node_id), str(label)


def _unpack_edge(edge: object) -> tuple[str, str, str]:
    """(source id, target id, relationship) for a graph edge."""
    if isinstance(edge, (tuple, list)) and len(edge) >= 3:
        return str(edge[0]), str(edge[1]), str(edge[2])
    raise SystemExit(f"unrecognised edge shape from the graph engine: {type(edge).__name__}")


async def export(dataset: str, limit: int = DEFAULT_LIMIT) -> ExportReport:
    """Render the knowledge graph as linked markdown, so the vault graph view shows it.

    Generated notes link to each other and up to the hub, never sideways into a human-authored
    note. A rebuild must not be able to change the human graph.
    """
    config.configure()
    from cognee.infrastructure.databases.graph import get_graph_engine

    engine = await get_graph_engine()
    nodes, edges = await engine.get_graph_data()

    labels = dict(_unpack_node(node) for node in nodes)
    neighbours: dict[str, list[tuple[str, str]]] = {node_id: [] for node_id in labels}
    for edge in edges:
        source, target, relationship = _unpack_edge(edge)
        if source in neighbours and target in labels:
            neighbours[source].append((relationship, target))

    directory = config.generated_path("kg", dataset)
    directory.mkdir(parents=True, exist_ok=True)

    chosen = sorted(labels, key=lambda node_id: (-len(neighbours[node_id]), labels[node_id]))[
        :limit
    ]
    chosen_set = set(chosen)

    for node_id in chosen:
        lines = [
            "> Up: [[README.md]]",
            "",
            f"# {labels[node_id]}",
            "",
            f"Generated from the `{dataset}` knowledge graph. Do not edit; the next export "
            "overwrites this file.",
            "",
        ]
        links = [
            f"- {relationship}: [[{slug(labels[target])}.md]]"
            for relationship, target in neighbours[node_id]
            if target in chosen_set
        ]
        if links:
            lines += ["## Connections", "", *links, ""]
        lines += ["## Related", "", "- [[graph/README.md]]", ""]
        (directory / f"{slug(labels[node_id])}.md").write_text("\n".join(lines), encoding="utf-8")

    return ExportReport(
        dataset=dataset, written=len(chosen), total=len(labels), directory=directory
    )
