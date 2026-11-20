# Ingestion: add, chunk, embed, then the vector index cognee does not create.
from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from plugmybrain import config

# Table and column names reach DDL by interpolation, so they must pass this allowlist
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64
HNSW_EF_SEARCH = 64

# pgvector's sizing guidance: lists = rows / 1000
IVFFLAT_ROWS_PER_LIST = 1000

# Characters per chunk, so a hit points at a paragraph rather than a page
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1500"))

_LISTS = re.compile(r"lists\s*=\s*'?(\d+)'?")


@dataclass
class IngestReport:
    dataset: str
    ingested: int = 0
    skipped: list[Path] = field(default_factory=list)
    indexes_created: list[str] = field(default_factory=list)
    indexes_skipped: list[str] = field(default_factory=list)
    indexes_rebuild_due: list[str] = field(default_factory=list)
    indexes_refused: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)


def choose_index(rows: int, kind: str = config.INDEX_KIND) -> str:
    """exact, ivfflat or hnsw. Below the threshold an IVFFlat index is a scan with overhead."""
    if kind != "auto":
        return kind
    return "exact" if rows < config.FLAT_THRESHOLD else "ivfflat"


async def ensure_vector_index() -> IngestReport:
    """Give every pgvector column the index its row count deserves, and say which and why.

    Runs after every ingest: cognee makes a table per collection with no index, and IVFFlat
    trained on an empty table has near-useless recall.
    """
    import asyncpg

    report = IngestReport(dataset="")
    connection = await asyncpg.connect(**config.db_connect_kwargs())
    try:
        columns = await connection.fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND udt_name = 'vector'"
        )
        existing = {
            row["tablename"]: row["indexdef"]
            for row in await connection.fetch(
                "SELECT tablename, indexdef FROM pg_indexes WHERE schemaname = 'public' "
                "AND (indexdef ILIKE '%USING hnsw%' OR indexdef ILIKE '%USING ivfflat%')"
            )
        }
        built: set[str] = set()

        for row in columns:
            table, column = row["table_name"], row["column_name"]
            if not (_IDENTIFIER.match(table) and _IDENTIFIER.match(column)):
                report.indexes_refused.append(f"{table}.{column}")
                continue

            count = await connection.fetchval(f'SELECT count(*) FROM "{table}"')

            if table in existing:
                match = _LISTS.search(existing[table])
                # Reported, not rebuilt: dropping an index on a live database unasked is not ours
                if match and count > int(match.group(1)) * IVFFLAT_ROWS_PER_LIST * 10:
                    report.indexes_rebuild_due.append(
                        f"{table} has {count} rows against lists={match.group(1)}"
                    )
                continue

            kind = choose_index(count)
            if kind == "exact":
                report.indexes_skipped.append(f"{table} ({count} rows, exact search is faster)")
                continue

            # cosine, not the l2 default: cognee searches by cosine and ignores an l2 index
            if kind == "ivfflat":
                lists = max(1, count // IVFFLAT_ROWS_PER_LIST)
                index = f"{table}_{column}_ivfflat"
                await connection.execute(
                    f'CREATE INDEX IF NOT EXISTS "{index}" ON "{table}" '
                    f'USING ivfflat ("{column}" vector_cosine_ops) WITH (lists = {lists})'
                )
                report.indexes_created.append(f"{index} (lists={lists}, {count} rows)")
            else:
                index = f"{table}_{column}_hnsw"
                await connection.execute(
                    f'CREATE INDEX IF NOT EXISTS "{index}" ON "{table}" '
                    f'USING hnsw ("{column}" vector_cosine_ops) '
                    f"WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})"
                )
                report.indexes_created.append(f"{index} ({count} rows)")
            built.add(kind)

        # cognee opens its own connections, so search depth is set on the database
        database = str(config.db_connect_kwargs()["database"])
        if not _IDENTIFIER.match(database):
            report.indexes_refused.append(f"database {database}: search depth not set")
        elif "ivfflat" in built:
            lists = max(
                1,
                max(int(m.group(1)) for e in report.indexes_created if (m := _LISTS.search(e))),
            )
            probes = max(1, round(math.sqrt(lists)))
            await connection.execute(f'ALTER DATABASE "{database}" SET ivfflat.probes = {probes}')
        elif "hnsw" in built:
            await connection.execute(
                f'ALTER DATABASE "{database}" SET hnsw.ef_search = {HNSW_EF_SEARCH}'
            )
    finally:
        await connection.close()
    return report


async def _pipeline():
    """cognee's default pipeline minus extract_graph_and_summarize, the one chat-model step.

    That step was the whole bill. Dropping it keeps chunking and embedding, which is all
    retrieval needs, and gives up the entity graph.
    """
    from cognee.modules.chunking.TextChunker import TextChunker
    from cognee.modules.pipelines.tasks.task import Task
    from cognee.tasks.documents import classify_documents, extract_chunks_from_documents
    from cognee.tasks.storage import add_data_points

    return [
        Task(classify_documents),
        Task(extract_chunks_from_documents, max_chunk_size=CHUNK_SIZE, chunker=TextChunker),
        Task(add_data_points, task_config={"batch_size": 2000}),
    ]


async def ingest(target: Path, dataset: str) -> IngestReport:
    """Ingest every markdown file under `target` into `dataset`, then index it. Idempotent."""
    import cognee
    from cognee.modules.pipelines import run_pipeline

    from plugmybrain import manage

    if not target.is_dir():
        raise SystemExit(f"not a directory: {target}")
    documents, skipped = config.collect_documents(target)
    if not documents:
        raise SystemExit(f"no markdown found under {target}, so there is nothing to remember.")

    problem = await manage.embedding_mismatch(record=True)
    if problem:
        raise SystemExit(problem)

    # Identical bytes make cognee attach one Data row twice and die in SQLAlchemy
    duplicates: list[str] = []
    seen: dict[str, Path] = {}
    unique: list[Path] = []
    for path in documents:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        first = seen.get(digest)
        if first is None:
            seen[digest] = path
            unique.append(path)
        else:
            duplicates.append(f"{path.name} is identical to {first.name}")

    report = IngestReport(dataset=dataset, ingested=len(unique), skipped=skipped)
    report.duplicates = duplicates

    await cognee.add([str(path) for path in unique], dataset_name=dataset)

    # run_pipeline, not cognify: cognify hardcodes the chat-model step. Drained to the end
    async for _ in run_pipeline(
        tasks=await _pipeline(),
        datasets=[dataset],
        pipeline_name="pmb_pipeline",
        incremental_loading=True,
    ):
        pass

    indexes = await ensure_vector_index()
    report.indexes_created = indexes.indexes_created
    report.indexes_skipped = indexes.indexes_skipped
    report.indexes_rebuild_due = indexes.indexes_rebuild_due
    report.indexes_refused = indexes.indexes_refused
    return report
