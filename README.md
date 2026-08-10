# Brain

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Conda](https://img.shields.io/badge/Conda-Miniconda-44A833?logo=anaconda&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)
![Cognee](https://img.shields.io/badge/Cognee-1.4.2-0F766E)
![Graphify](https://img.shields.io/badge/Graphify-0.9.38-B45309)
![Status](https://img.shields.io/badge/Status-WIP-D29922)
![License](https://img.shields.io/badge/License-MIT-750014)

A plug-and-play memory for any AI model. Point it at a folder and it produces two things: a
code map an agent reads instead of grepping the tree, and a knowledge graph over the folder's
documents. Both are namespaced per project, and both are steered by human-authored markdown in
an Obsidian vault. It exists because an agent with no memory relearns the same context every
session, and pays for that in tokens every time.

## Setup

Follow this in order. Steps 1 and 2 are done; step 3 onward needs your keys and Docker.

**1. Environment.** Conda, an environment named `env`, Python 3.13.

```bash
conda env update -f environment.yml
conda activate env
pip install -e .
```

Never use bare `pip` or bare `python` outside the activated environment. On this machine they
resolve to different interpreters, and an install lands somewhere the code cannot import it.

**2. Code map.** No API key, no network, nothing uploaded.

```bash
brain map /path/to/any-project
```

**3. Configuration.** Copy the template and fill it in by hand.

```bash
cp .env.example .env
```

Two keys are required and they are from different vendors: `EMBEDDING_API_KEY` from Voyage,
and `LLM_API_KEY` from whichever chat provider you uncomment. Also set `DB_PASSWORD`.

**4. Database.** PostgreSQL 18 with pgvector. Relational, vector and graph in one container.

```bash
docker compose up -d
docker compose ps          # wait for healthy
```

The `vector` extension is created on first start by `scripts/init-pgvector.sql`. It runs only
on an empty data directory, so if you ever change it, `docker compose down -v` first.

**5. Estimate before you spend.** `add` is free; `cognify` calls the model once per chunk.

```bash
brain sync --dry-run
```

**6. Ingest the curated rules and memory.**

```bash
brain sync
```

Read the output. It reports documents ingested, files skipped by the exclusion list, and the
HNSW indexes it created. A skip is printed rather than swallowed, because a silent skip reads
as "covered everything" when it did not.

**7. Validate.**

```bash
brain eval
```

Ten questions against the vault's own rules, two of them multi-hop, scored on whether the
right source file is cited. It also reports p50 and p95 on the warm path.

**8. Optional: the HTTP API and the graph export.**

```bash
brain serve                      # http://127.0.0.1:8080/health
brain export --project curated   # knowledge graph into the vault, as wikilink notes
```

## Usage

```bash
brain map    /path/to/project          # code structure, zero API tokens
brain ingest /path/to/project          # that project's documents, into its own dataset
brain search "how is auth handled" --project project
brain sync                             # re-ingest the curated rules and memory
brain export --project project         # knowledge graph as vault notes
brain eval                             # score and latency
brain serve                            # the HTTP API
```

The dataset is the folder's own name, and it is required on every read. That is what keeps one
project's memory out of another's answers. Nothing is ever scanned without an explicit path.

## Configuration

Every variable the project reads. Names only; see [[env.rules.md]].

| Variable | Required | Description |
| :- | :- | :- |
| `BRAIN_PROFILE` | No | `local` or `cloud`. Selects where the database lives. Default `local` |
| `BRAIN_VAULT` | No | Path to the Obsidian vault. Defaults to the sibling `docs` checkout |
| `BRAIN_GRAPH_DIR` | No | Where Graphify output lands. Defaults to `graph/` |
| `DB_HOST` `DB_PORT` `DB_NAME` `DB_USERNAME` | Yes | PostgreSQL connection |
| `DB_PASSWORD` | Yes | Database password |
| `EMBEDDING_PROVIDER` `EMBEDDING_MODEL` | Yes | `voyage` and `voyage/voyage-3.5` |
| `EMBEDDING_DIMENSIONS` | Yes | `1024`. Above 2000 the process refuses to start |
| `EMBEDDING_API_KEY` | Yes | Voyage key. Separate from the chat key |
| `LLM_PROVIDER` `LLM_MODEL` | Yes | The chat model that builds the graph |
| `LLM_API_KEY` | Yes | Unless `LLM_PROVIDER=mcp-sampling`, which only works inside an MCP session |
| `POOL_ARGS` `VECTOR_POOL_ARGS` | No | Connection pool sizing |
| `CHUNK_SIZE` `CHUNK_OVERLAP` | No | Ingestion chunking |
| `CLOUDSQL_INSTANCE` | No | `cloud` profile only. `PROJECT:REGION:INSTANCE` |

## Data

Nothing here is committed.

| Item | Location | Notes |
| :- | :- | :- |
| Code maps | `graph/<project>/graphify-out/` | Gitignored. Produced by `brain map` |
| Code reports | `<vault>/graph/code/<project>/` | Gitignored in the vault. Never hand-edited |
| Graph export | `<vault>/graph/kg/<dataset>/` | Gitignored in the vault. Never hand-edited |
| The memory itself | `<vault>/memory/` and `<vault>/rules/` | Committed, human-authored, the source of truth |

## Project Structure

```text
brain/
  config.py      # paths, profile, the exclusion list, the dimension guard
  ingest.py      # add, cognify, then the HNSW index cognee does not create
  retrieve.py    # dataset-scoped search
  export.py      # knowledge graph to vault wikilink notes
  eval.py        # the question set, scored, with p50 and p95
  api.py         # the HTTP surface
  cli.py         # the one entry point
scripts/         # database init, MCP launcher
tests/
```

## Development

```bash
ruff check .          # lint
ruff format .         # format
pytest                # tests
```

## Privacy

**"Local" describes the database only.** In both profiles every ingested document is sent to
the cloud model for extraction and embedding. Data leaves the machine either way.

The code map does not: `brain map` runs tree-sitter locally with `--code-only` and makes no
network call at all. That is why code structure comes from Graphify and documents from Cognee,
rather than putting source through the model.

`config.py` refuses to ingest a path matching the exclusion list, whatever folder it is pointed
at, and prints what it skipped. The ceiling: it matches on names and directories, so a secret
pasted into an ordinary `.md` still gets through.

## Known Limitations

- **The graph store is a demo feature.** Postgres-as-graph is released by cognee as a demo; the
  production version is licensed. It is used here because one database holds relational, vector
  and graph at once, so the whole local setup is a single `docker compose up`. If it proves
  unstable, `GRAPH_DATABASE_PROVIDER=kuzu` works locally with no other change.
- **The embedding model is locked to the corpus.** Swapping the chat model is free. Swapping
  `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS` means re-embedding everything.
- **1024 dimensions is a ceiling, not a preference.** pgvector will not build an HNSW index on
  a `vector` column wider than 2000. It does not fail loudly; it just leaves every search doing
  a sequential scan. `config.py` refuses to start above that.
- **There is no single no-model mode returning chunks and graph context together.** `chunks`
  returns sourced context with no completion step, `graph` spends an extra call. A combined
  retrieval mode would be a second query, and it is not built until the eval asks for it.
- **`memify` is called by signature introspection.** It is exported by cognee 1.4.2 but its
  definition could not be pinned from source, so `ingest.py` reads the installed function's
  parameters instead of assuming them. It is off unless you pass `--memify`.
- **No temporal layer.** Nothing here answers "what did I know in March". Git history does.

## Deviations From the Standards

Written down because [[deploy.rules.md]] and [[secret.rules.md]] require a deviation to say why.

1. **`--max-instances 2`**, where [[deploy.rules.md]] fixes 5. Tighter than the rule's ceiling,
   for cost. The agent path is a local process, so the service absorbs no agent traffic.
2. **No Alembic for the HNSW index**, where [[database.rules.md]] routes migrations through
   Alembic. Cognee owns and mutates its own schema, and a second migration tool fighting it
   breaks on every cognee upgrade. `ensure_hnsw()` is idempotent DDL run at the end of every
   ingest instead, and it has to run every time because cognee creates a new table per
   collection.
3. **No Secret Manager.** Values live in a gitignored `.env` locally and a gitignored
   `env-vars.yaml` on cloud. [[secret.rules.md]] ranks Secret Manager first and a gitignored
   `.env` second, so this takes the second-ranked option. The cost, stated so it is a decision
   rather than an accident: no rotation history, no per-secret IAM, and a value readable by
   anything that can read the file or describe the revision.
4. **The conda environment is named `env`**, where [[codes.rules.md]] says to name it after the
   project. Chosen deliberately.

## License

MIT
