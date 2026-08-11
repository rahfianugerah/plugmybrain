# Paths, the exclusion list, and the guards. One Docker stack runs everywhere, so DB_HOST is
# the only thing that differs between the laptop and a server.
#
# The unit of this tool is a folder. Point it at one and its markdown becomes a memory named
# after it. A digested folder is only ever READ; everything generated lands in one Obsidian
# vault, DOCS, namespaced per brain, so no project repository grows a graph/ nobody asked for.
from __future__ import annotations

import fnmatch
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Graphify's raw output: graph.json and its manifest, which are machine files nobody reads.
# Kept inside this repository so pointing the tool at someone else's folder leaves no json in it.
# Only the rendered report is copied into the folder, where Obsidian can show it.
_graph_dir = os.getenv("PMB_GRAPH_DIR", "")
GRAPH_DIR = (
    Path(_graph_dir) if Path(_graph_dir).is_absolute() else REPO_ROOT / (_graph_dir or "graph")
).resolve()

# Every generated note from every brain lands here, namespaced by brain, and nowhere else.
#
# Not inside the folder that was digested: eighteen service repositories would each grow a
# graph/ nobody asked for, and the whole point of an Obsidian vault is that it is ONE vault you
# open and see everything in. A digested folder is therefore only ever read, never written.
DOCS = (
    Path(os.environ["PMB_DOCS"]).resolve()
    if os.getenv("PMB_DOCS")
    else (REPO_ROOT.parent / "docs").resolve()
)

GENERATED = "graph"

# Only these two are machine-written. `graph/` itself also holds a hand-written README, which is
# committed, so `pmb reset` removes what is under the subfolders rather than the parent.
GENERATED_SUBDIRS = ("code", "kg")

# The one folder `pmb reset` must never touch. It is written by hand, it is committed, and it is
# the only reason a wiped database is a rebuild rather than a loss.
HUMAN = "memory"

# pgvector refuses to build an approximate index on a `vector` column wider than this, for
# either HNSW or IVFFlat. Exceeding it does not fail loudly, it just leaves every search doing
# a sequential scan.
MAX_INDEXABLE_DIMENSIONS = 2000

# exact, ivfflat, hnsw, or auto. auto picks exact below the threshold and IVFFlat above it.
# HNSW is opt-in and wants roughly 4 GiB; on a 2 GiB VM its build is the thing that OOMs.
INDEX_KIND = os.getenv("PMB_INDEX", "auto")

# Below this row count an approximate index is worse than no index: pgvector sizes IVFFlat at
# lists = rows / 1000, so a small table gets one list, which is a sequential scan plus overhead.
FLAT_THRESHOLD = int(os.getenv("PMB_INDEX_THRESHOLD", "10000"))

# Markdown only. Obsidian is the viewer, markdown is the substrate, and code structure is
# Graphify's job: ingesting source would pay a model to rediscover what the map already has.
DOCUMENT_SUFFIXES = frozenset({".md"})

# Never read, whatever folder the tool is pointed at. Ingestion uploads file contents, so this
# is the last thing standing between an arbitrary target and a leaked key.
EXCLUDED_DIRS = frozenset(
    {
        "keys",
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        GENERATED,
        "graphify-out",
        ".obsidian",
    }
)
EXCLUDED_NAMES = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "credentials.json",
    "env-vars.yaml",
    "jwt-secret.txt",
)


def namespace(target: Path) -> str:
    """The dataset name for a folder: its directory name, lowercased.

    This is why the ingest container mounts at `/w/<name>` rather than a fixed path. A fixed
    mount point erases the folder's name, and every folder would then be ingested under the
    mount point's name and overwrite the last one.
    """
    name = target.resolve().name.lower()
    if not name:
        raise ValueError(f"cannot derive a name from {target}")
    return name


def generated_path(kind: str, name: str, *parts: str) -> Path:
    """A path under the vault's generated area, for one brain.

    Refuses to escape it. That guard is the only thing standing between a rebuild and the
    hand-written notes in `memory/`, which sit in the same vault.
    """
    if kind not in GENERATED_SUBDIRS:
        raise ValueError(f"unknown generated kind {kind!r}. Use one of: {GENERATED_SUBDIRS}")
    root = (DOCS / GENERATED / kind).resolve()
    path = root.joinpath(name, *parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"refusing to write outside {root}: {path}")
    return path


def is_excluded(path: Path) -> bool:
    """True when a path must never be sent to the model.

    ponytail: name and directory matching only. A secret pasted into an ordinary .md still
    gets through; add a content scan here if that ever stops being an acceptable risk.
    """
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_NAMES)


def collect_documents(root: Path) -> tuple[list[Path], list[Path]]:
    """Split a folder into the markdown that will be ingested and the files that will not.

    The skipped list is returned rather than discarded, because a silent skip reads as
    "covered everything" when it did not.
    """
    root = root.resolve()
    included: list[Path] = []
    skipped: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        document = path.suffix.lower() in DOCUMENT_SUFFIXES
        if not is_excluded(path):
            if document:
                included.append(path)
        # Only a refusal a person would want to hear about: markdown that would otherwise have
        # been digested, or a file whose NAME matches a secret pattern whatever its suffix.
        # Reporting every file under .git and node_modules as "skipped" buries the one .env
        # that matters under a few hundred lines of nothing, and `graph/` is skipped by design
        # rather than refused: digesting the model's own output is how a graph cites itself.
        elif GENERATED in path.parts:
            continue
        elif document or any(fnmatch.fnmatch(path.name, p) for p in EXCLUDED_NAMES):
            skipped.append(path)
    return included, skipped


def db_connect_kwargs() -> dict[str, object]:
    """asyncpg connection arguments."""
    return {
        "host": os.environ["DB_HOST"],
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ["DB_USERNAME"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.environ["DB_NAME"],
    }


def configure(chat: bool = True) -> None:
    """Load `.env`, set the invariants, and fail fast on a bad setup.

    Must run before `import cognee`, because cognee reads its configuration from the
    environment at import time.

    `chat=False` for everything except `pmb digest`. A chat model is what turns markdown into a
    graph, and it runs once per digest; reading never calls one. That is the whole cost model:
    an agent asking a question spends nothing from these keys.
    """
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")

    # Invariants of this design rather than user choices, so they are set, not read.
    os.environ.setdefault("DB_PROVIDER", "postgres")
    os.environ.setdefault("VECTOR_DB_PROVIDER", "pgvector")
    os.environ.setdefault("GRAPH_DATABASE_PROVIDER", "postgres")
    os.environ.setdefault("TELEMETRY_DISABLED", "1")

    # cognee 1.x turns authentication and multi-tenancy on by default. With access control on it
    # routes every dataset through per-user databases, and `add` dies in _get_vector_db_info on
    # a connection nothing is listening for. This is one person's brain, so both are off, and
    # they are set here rather than in compose so the CLI and the container agree.
    os.environ.setdefault("REQUIRE_AUTHENTICATION", "false")
    os.environ.setdefault("ENABLE_BACKEND_ACCESS_CONTROL", "false")

    # cognee runs a 30s pre-flight reachability test against the model endpoints. It times out
    # here even when the providers answer in milliseconds by curl, so it fails a setup that
    # works. Skipped: a genuinely bad key then fails at the real call, with the provider's own
    # error, which says more than "connection test timed out" ever did.
    os.environ.setdefault("COGNEE_SKIP_CONNECTION_TEST", "true")

    missing = [
        key for key in ("DB_HOST", "DB_NAME", "DB_USERNAME", "DB_PASSWORD") if not os.getenv(key)
    ]
    if missing:
        raise SystemExit(
            f"missing in .env: {', '.join(missing)}. Copy .env.example and fill it in."
        )

    # Voyage is embeddings only, so the embedding key is separate from the chat key. Without
    # this check cognee silently falls back to LLM_API_KEY and Voyage rejects it with a 401
    # that names the wrong vendor.
    if not os.getenv("EMBEDDING_API_KEY"):
        raise SystemExit(
            "EMBEDDING_API_KEY is not set. Voyage needs its own key, separate from LLM_API_KEY."
        )

    if chat and not os.getenv("LLM_API_KEY"):
        raise SystemExit(
            "LLM_API_KEY is not set. Turning markdown into a graph is the one thing that needs "
            "a chat model, and it runs once per digest. Reading never calls one."
        )

    dimensions = int(os.environ.setdefault("EMBEDDING_DIMENSIONS", "1024"))
    if dimensions > MAX_INDEXABLE_DIMENSIONS:
        raise SystemExit(
            f"EMBEDDING_DIMENSIONS={dimensions} exceeds {MAX_INDEXABLE_DIMENSIONS}, the widest "
            "vector pgvector will index at all. Every search would fall back to a sequential "
            "scan. Use 1024."
        )

    if INDEX_KIND not in ("auto", "exact", "ivfflat", "hnsw"):
        raise SystemExit(f"PMB_INDEX={INDEX_KIND!r}. Use auto, exact, ivfflat or hnsw.")

    # The vector store is the same Postgres as the relational store: one database, one backup.
    for key in ("HOST", "PORT", "NAME", "USERNAME", "PASSWORD"):
        value = os.getenv(f"DB_{key}")
        if value:
            os.environ.setdefault(f"VECTOR_DB_{key}", value)
