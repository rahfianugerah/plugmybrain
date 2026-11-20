# What the brain holds, how to throw it away, and which model it was embedded with.
# The markdown on disk is the memory; the database is an index rebuilt from it.
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from plugmybrain import config


@dataclass
class DatasetRow:
    name: str
    documents: int
    created: str


@dataclass
class Status:
    target: Path
    name: str
    markdown: int
    skipped: int
    human_notes: int
    generated_notes: int
    ingested: int
    datasets: list[DatasetRow] = field(default_factory=list)
    chunks: int = 0
    database: str = ""
    size: str = ""


@dataclass
class ResetReport:
    scope: str
    documents: int
    generated: list[Path]


async def _connect():
    import asyncpg

    return await asyncpg.connect(**config.db_connect_kwargs())


async def embedding_mismatch(record: bool = False) -> str | None:
    """Why this database must not be read or written with the current model, or None.

    `record` stores the current model on first use; a read never writes.
    """
    import asyncpg

    current = config.embedding_signature()
    connection = await _connect()
    try:
        if record:
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS pmb_meta (key text PRIMARY KEY, value text NOT NULL)"
            )
        try:
            stored = await connection.fetchval("SELECT value FROM pmb_meta WHERE key = 'embedding'")
        except asyncpg.exceptions.UndefinedTableError:
            stored = None
        if stored is None and record:
            await connection.execute("INSERT INTO pmb_meta VALUES ('embedding', $1)", current)
    finally:
        await connection.close()

    if stored and stored != current:
        return (
            f"this database was embedded with {stored}, and the embedding is now {current}. "
            "Vectors from two models rank each other wrong without any error. Switch back, or "
            "reset every brain and digest again."
        )
    return None


def _on_disk(target: Path) -> tuple[int, int, int, int]:
    """(markdown, skipped, human notes, generated notes), counted from the files."""
    included, skipped = config.collect_documents(target)
    human = target / config.HUMAN
    name = config.namespace(target)
    written = sum(
        len(list(directory.rglob("*.md")))
        for sub in config.GENERATED_SUBDIRS
        if (directory := config.DOCS / config.GENERATED / sub / name).is_dir()
    )
    return (
        len(included),
        len(skipped),
        len(list(human.rglob("*.md"))) if human.is_dir() else 0,
        written,
    )


async def status(target: Path, scan: bool = True) -> Status:
    """The database, and the folder it came from. `scan=False` skips the disk walk."""
    import asyncpg

    target = target.resolve()
    name = config.namespace(target)
    markdown, skipped, human, generated = _on_disk(target) if scan else (0, 0, 0, 0)

    connection = await _connect()
    try:
        try:
            rows = await connection.fetch(
                "SELECT ds.name, count(dd.data_id) AS documents, min(ds.created_at) AS created "
                "FROM datasets ds LEFT JOIN dataset_data dd ON dd.dataset_id = ds.id "
                "GROUP BY ds.name ORDER BY ds.name"
            )
        except asyncpg.exceptions.UndefinedTableError:
            # cognee creates its schema on the first digest: empty, not broken
            rows = []
        database = str(config.db_connect_kwargs()["database"])
        size = await connection.fetchval("SELECT pg_size_pretty(pg_database_size($1))", database)

        # One table per collection, so the chunk total sums every vector table
        chunks = 0
        for table in await connection.fetch(
            "SELECT DISTINCT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND udt_name = 'vector'"
        ):
            chunks += await connection.fetchval(f'SELECT count(*) FROM "{table["table_name"]}"')
    finally:
        await connection.close()

    datasets = [
        DatasetRow(r["name"], r["documents"], str(r["created"])[:19] if r["created"] else "")
        for r in rows
    ]
    return Status(
        target=target,
        name=name,
        markdown=markdown,
        skipped=skipped,
        human_notes=human,
        generated_notes=generated,
        ingested=next((d.documents for d in datasets if d.name == name), 0),
        datasets=datasets,
        chunks=chunks,
        database=database,
        size=size or "",
    )


def _folder_lines(status: Status) -> list[str]:
    lines = [
        f"folder:    {status.target}",
        f"memory:    {status.name}",
        "",
        f"markdown in the folder:   {status.markdown}",
        f"  of which memory/:       {status.human_notes} (human-authored, survives a reset)",
        f"  digested:               {status.ingested}",
        f"  generated into graph/:  {status.generated_notes} (rebuilt by digest)",
        f"  skipped as a secret:    {status.skipped}",
    ]
    if status.markdown != status.ingested:
        lines.append(f"  {status.markdown - status.ingested} not digested. Digest this folder.")
    return [*lines, ""]


def _child_line(status: Status) -> str:
    gap = "" if status.markdown == status.ingested else f"  ({status.markdown} not digested)"
    if status.markdown == status.ingested and status.markdown:
        gap = "  up to date"
    return f"  {status.name:<26} {status.ingested:>4} of {status.markdown:>4} markdown{gap}"


def _database_lines(status: Status, highlight: set[str]) -> list[str]:
    lines = [
        f"database:  {status.database} ({status.size}), {status.chunks} chunk(s) embedded",
        f"embedding: {config.embedding_signature()}",
    ]
    if not status.datasets:
        return [*lines, "           empty. Nothing has been digested yet."]
    width = max(len(d.name) for d in status.datasets)
    for row in status.datasets:
        here = "  <-" if row.name in highlight else ""
        lines.append(
            f"           {row.name:<{width}}  {row.documents:>4} doc(s)  {row.created}{here}"
        )
    return lines


async def describe(target: Path | None) -> str:
    """What `status` and `pmb list` print: a folder, a root's children, or the database alone."""
    if target is None:
        return "\n".join(_database_lines(await status(config.WORKSPACE, scan=False), set()))

    if config.role_of(target) == "root":
        lines = [f"root:      {target}", ""]
        names = set()
        for path in config.children(target):
            child = await status(path)
            lines.append(_child_line(child))
            names.add(child.name)
        lines.append("")
        return "\n".join(lines + _database_lines(await status(target, scan=False), names))

    folder = await status(target)
    return "\n".join(_folder_lines(folder) + _database_lines(folder, {folder.name}))


async def reset(target: Path, everything: bool = False) -> ResetReport:
    """Throw away the derived memory and this brain's generated notes. Never the markdown."""
    import cognee

    target = target.resolve()
    name = config.namespace(target)

    if everything:
        await cognee.prune.prune_data()
        await cognee.prune.prune_system(graph=True, vector=True, metadata=True)
        connection = await _connect()
        try:
            # Nothing is embedded any more, so the next digest may use any model
            await connection.execute("DROP TABLE IF EXISTS pmb_meta")
        finally:
            await connection.close()
        documents = -1
    else:
        connection = await _connect()
        try:
            rows = await connection.fetch(
                "SELECT dd.data_id, dd.dataset_id FROM dataset_data dd "
                "JOIN datasets ds ON ds.id = dd.dataset_id WHERE ds.name = $1",
                name,
            )
        finally:
            await connection.close()
        if not rows:
            raise SystemExit(
                f"nothing named {name!r} in the database. `status` shows what is there."
            )
        # cognee's own delete: one row is three stores, and a raw DELETE orphans two of them
        for row in rows:
            await cognee.delete(data_id=row["data_id"], dataset_id=row["dataset_id"], mode="hard")
        documents = len(rows)

    # This brain's folder only: other brains and the hand-written graph/README.md sit beside it
    removed = []
    for sub in config.GENERATED_SUBDIRS:
        directory = config.DOCS / config.GENERATED / sub / name
        if directory.is_dir():
            shutil.rmtree(directory)
            removed.append(directory)
    graph = config.GRAPH_DIR / name
    if graph.is_dir():
        shutil.rmtree(graph)
        removed.append(graph)

    return ResetReport(
        scope="everything" if everything else name, documents=documents, generated=removed
    )
