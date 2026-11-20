# Ingestion: add, cognify, index. The half of `pmb digest` that costs money, and the reason the
# `pmb` service sits behind a compose profile: never co-resident with serving on a 2 GiB VM.
from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from plugmybrain import config

# Table and column names come from information_schema, never from a user, but Postgres will not
# bind an identifier so they still reach the DDL by interpolation. The allowlist is what makes
# that safe, and anything it rejects is reported rather than skipped in silence.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

HNSW_M = 16
HNSW_EF_CONSTRUCTION = 64
HNSW_EF_SEARCH = 64

# pgvector's own sizing guidance: lists = rows / 1000 up to a million rows.
IVFFLAT_ROWS_PER_LIST = 1000

# Characters per chunk. Small enough that a hit points at a paragraph rather than a page.
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1500"))

# `WITH (lists='100')` inside pg_indexes.indexdef, so a stale index can be spotted.
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
    estimate: object | None = None


def choose_index(rows: int, kind: str = config.INDEX_KIND) -> str:
    """Which index a table of `rows` vectors should get: exact, ivfflat or hnsw.

    `exact` means no index at all. Below the threshold that is the right answer, not a
    concession: pgvector sizes IVFFlat at lists = rows / 1000, so a few hundred chunks would
    produce a single-list index, which is a sequential scan carrying index overhead. Exact
    search over the same rows is faster and has perfect recall.
    """
    if kind != "auto":
        return kind
    return "exact" if rows < config.FLAT_THRESHOLD else "ivfflat"


async def ensure_vector_index() -> IngestReport:
    """Give every pgvector column the index its row count deserves, and say which and why.

    Cognee's pgvector adapter creates the table and the vector column but no index at all, and
    it creates a new table per collection. So this runs after every ingest rather than once:
    a one-time CREATE INDEX goes stale the moment a new dataset appears.

    Runs after the data is loaded, which IVFFlat requires. It has a training step, so an
    IVFFlat index built on an empty table has near-useless recall and fails silently.
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
                # An IVFFlat sized for a tenth of the current rows still answers, just badly.
                # Reported rather than rebuilt: dropping an index on a live database unasked
                # is not a thing to do.
                if match and count > int(match.group(1)) * IVFFLAT_ROWS_PER_LIST * 10:
                    report.indexes_rebuild_due.append(
                        f"{table} has {count} rows against lists={match.group(1)}"
                    )
                continue

            kind = choose_index(count)
            if kind == "exact":
                report.indexes_skipped.append(f"{table} ({count} rows, exact search is faster)")
                continue

            # vector_cosine_ops, not the vector_l2_ops default: cognee searches by cosine
            # distance, and an index built for the wrong operator is never used.
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

        # Cognee opens its own connections, so neither probes nor ef_search can be set per
        # session. Both default to a value tuned for speed over recall.
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
    """Cognee's own pipeline with the one step that calls a chat model taken out.

    Its default is five tasks and cognee's own comments name what each does:

        classify_documents              EXTRACT: raw Data into typed Document objects
        extract_chunks_from_documents   EXTRACT: split Documents into semantic chunks
        extract_graph_and_summarize     COGNIFY: LLM-extract entities, LLM-summarize each chunk
        add_data_points                 LOAD: persist nodes, edges and embeddings
        extract_dlt_fk_edges            LOAD: foreign-key edges

    Only the third one calls a chat model, and it is the whole bill: it emits structured JSON
    per chunk, so output tokens dominate. Dropping it leaves chunking and embedding, which is
    all that retrieval needs, and takes the chat model out of this project entirely.

    What is lost is the entity graph, and with it any question answered by traversing between
    documents rather than matching text in one. That is a real capability, priced at roughly
    ten dollars per corpus, and this trades it away deliberately.
    """
    from cognee.modules.chunking.TextChunker import TextChunker
    from cognee.modules.pipelines.tasks.task import Task
    from cognee.tasks.documents import classify_documents, extract_chunks_from_documents
    from cognee.tasks.storage import add_data_points

    # Not cognee's get_max_chunk_tokens(): it sizes a chunk at half the CHAT model's context
    # window, which is a number with no meaning once there is no chat model. CHUNK_SIZE is a
    # setting that already exists and the only ceiling left that matters is the embedding
    # model's, which 1500 is comfortably under.
    return [
        Task(classify_documents),
        Task(extract_chunks_from_documents, max_chunk_size=CHUNK_SIZE, chunker=TextChunker),
        Task(add_data_points, task_config={"batch_size": 2000}),
    ]


async def ingest(target: Path, dataset: str) -> IngestReport:
    """Ingest every markdown file under `target` into `dataset`, then index it.

    Idempotent: cognee loads incrementally, and ensure_vector_index only creates what is
    missing.
    """
    import cognee
    from cognee.modules.pipelines import run_pipeline

    if not target.is_dir():
        raise SystemExit(f"not a directory: {target}")
    documents, skipped = config.collect_documents(target)

    if not documents:
        raise SystemExit(
            f"no markdown found under {target}. PlugMyBrain digests markdown; a folder with "
            "none has nothing to remember."
        )

    from plugmybrain import manage

    problem = await manage.embedding_mismatch(record=True)
    if problem:
        raise SystemExit(problem)

    # Two files with identical bytes make cognee build one Data row and then attach it to the
    # dataset twice, which dies in SQLAlchemy's identity map. This project causes it on purpose:
    # CLAUDE.md and AGENTS.md are kept byte-identical so neither agent reads a different rule.
    report_duplicates: list[str] = []
    seen: dict[str, Path] = {}
    unique: list[Path] = []
    for path in documents:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        first = seen.get(digest)
        if first is None:
            seen[digest] = path
            unique.append(path)
        else:
            report_duplicates.append(f"{path.name} is identical to {first.name}")
    documents = unique

    report = IngestReport(dataset=dataset, ingested=len(documents), skipped=skipped)
    report.duplicates = report_duplicates

    await cognee.add([str(path) for path in documents], dataset_name=dataset)

    # run_pipeline rather than cognify, because cognify hardcodes its five tasks and the third
    # is the chat model. There is no flag for this; the task list is the flag.
    # An async generator, not a coroutine: it yields a status per dataset as it goes. Drained
    # rather than awaited, so the run is actually finished before the index is built on it.
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
