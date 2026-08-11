# PlugMyBrain

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Conda](https://img.shields.io/badge/Conda-Miniconda-44A833?logo=anaconda&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)
![Cognee](https://img.shields.io/badge/Cognee-1.4.2-0F766E)
![Graphify](https://img.shields.io/badge/Graphify-0.9.38-B45309)
![Status](https://img.shields.io/badge/Status-WIP-D29922)

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
pmb map /path/to/any-project
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

**Step 3 has to come first.** `compose.yaml` declares `.env` as a required env file, so
`docker compose up` without it fails with `env file ... not found`. That is deliberate: made
optional, `cognee-mcp` would start on cognee's embedded SQLite and LanceDB defaults and quietly
serve the wrong database.

On the laptop `compose.override.yaml` is picked up automatically. It only moves Postgres to
port 15432, because a development machine usually already owns 5432. The full stack runs
either way, so a local `docker compose up -d` gives a working brain with no VM and no tunnel.

The `vector` extension is created on first start by `scripts/init-pgvector.sql`. It runs only
on an empty data directory, so if you ever change it, `docker compose down -v` first.

**5. Estimate before you spend.** `add` is free; `cognify` calls the model once per chunk.

```bash
pmb sync --dry-run
```

**6. Ingest the curated rules and memory.**

```bash
docker compose run --rm cognee-ingest
```

**Always ingest in the container, on either host.** `pmb sync` run natively on Windows hangs on
cognee's subprocess database workers, and a killed run stores host paths in Postgres that no
container can resolve afterwards, which costs a `docker compose down -v`. Reading (`pmb search`,
`pmb eval`) is fine natively; only ingestion must be containerised.

Read the output. It reports documents ingested, files skipped by the exclusion list, and which
vector index each table got with the row count that decided it. A skip is printed rather than
swallowed, because a silent skip reads as "covered everything" when it did not.

**7. Validate.**

```bash
pmb eval
```

Ten questions against the vault's own rules, two of them multi-hop, scored on whether the
right source file is cited. It also reports p50 and p95 on the warm path.

**8. Look at it.** Three views, none of which needs a server running.

```bash
pmb visualize --project curated   # the knowledge graph, one self-contained HTML file
pmb export    --project curated   # the same graph as vault notes, for the Obsidian graph view
pmb serve                         # optional HTTP API on http://127.0.0.1:8080/health
```

See `## Visualisation` below for what each one is good for.

**9. Wire the agents.** See `## Agent Wiring`.

### The whole thing, once it is set up

Day to day this is the entire loop:

```bash
docker compose up -d              # the brain comes up and stays up
pmb sync                          # after editing anything in the vault's memory/ or rules/
pmb map /path/to/a/project        # after a codebase changes
```

Everything else is a query, and the agents make those themselves over MCP.

## Deployment

One `docker compose` stack, identical on the laptop and on a single always-on Compute Engine
VM. No Cloud Run, no Cloud SQL, no Secret Manager. See `## Deviations From the Standards`.

| Runs on the VM | Runs on the laptop |
| :- | :- |
| `postgres`, always on, loopback only | `pmb map`, entirely local, no network at all |
| `cognee-mcp`, always on, loopback only | The Obsidian vault, which you edit |
| `cognee-ingest`, one-shot, behind a compose profile | Claude Code and Codex, via the tunnel |
| The nightly `pg_dump` | `pmb export` and `pmb sync`, via the tunnel |

If the tunnel is down, `pmb map` still answers code-structure questions. Only the document
brain becomes unreachable. That is the intended degradation, not an outage.

### 1. Create the VM

Nothing here is run for you. Substitute your own project and confirm the cost first.

```bash
export PROJECT=[PROJECT]  ZONE=asia-southeast1-a  VM=plugmybrain
gcloud compute instances create $VM --project $PROJECT --zone $ZONE \
  --machine-type e2-small \
  --image-family debian-12 --image-project debian-cloud \
  --boot-disk-size 30GB --boot-disk-type pd-balanced
```

30GB is not generosity. Docker images plus Postgres data plus WAL plus logs on a 10GB disk is
how a data directory gets corrupted, and disk is the cheapest part of this.

Lock SSH to Identity-Aware Proxy so the tunnel is the only door, and open nothing else:

```bash
gcloud compute firewall-rules create pmb-iap-ssh --project $PROJECT \
  --allow tcp:22 --source-ranges 35.235.240.0/20
```

There is deliberately no rule for 5432 or 9000. Both bind to the VM's loopback and are reached
only through the tunnel.

### 2. Provision the host

```bash
gcloud compute ssh $VM --tunnel-through-iap --zone $ZONE
sudo bash scripts/provision-vm.sh     # swap, disk check, docker at boot, Asia/Jakarta
```

### 3. Configuration, and bring it up

```bash
sudo install -m 600 /dev/null /opt/plugmybrain/.env
sudo vi /opt/plugmybrain/.env               # from .env.example; DB_HOST=postgres inside compose
sudo docker compose up -d
```

`.env` is `0600` and root-owned, so the stack runs as root from `/opt/plugmybrain`.

### 4. The tunnel, from the laptop

```powershell
$env:PMB_VM="plugmybrain"; $env:PMB_ZONE="asia-southeast1-a"; $env:PMB_PROJECT="[PROJECT]"
.\scripts\tunnel.ps1
```

One session carries both ports and reconnects if it drops: `9000` for the MCP server and
`15432` for Postgres. Set `DB_PORT=15432` in the laptop's `.env`. The odd port is deliberate:
a dev Postgres already holding 5432 would otherwise make the forward fail in a way that reads
as a database problem.

### 5. Backups

```bash
gcloud storage buckets create gs://[BUCKET] --project $PROJECT --location asia-southeast1
gcloud storage buckets add-iam-policy-binding gs://[BUCKET] \
  --member "serviceAccount:$(gcloud compute instances describe $VM --zone $ZONE \
    --format 'value(serviceAccounts[0].email)')" --role roles/storage.objectAdmin
```

Set `BACKUP_BUCKET` in the VM's `.env`, then schedule it:

```bash
sudo crontab -e
# 0 3 * * * /opt/plugmybrain/scripts/backup.sh >> /var/log/pmb-backup.log 2>&1
```

The timezone is set by `provision-vm.sh`. Without it cron runs UTC and 03:00 becomes 10:00
local. The script exits non-zero on an empty dump or a nearly full disk, because a backup
script that fails quietly is worse than none: it is trusted.

A disk snapshot schedule is the zero-maintenance complement and covers a different failure:

```bash
gcloud compute resource-policies create snapshot-schedule pmb-nightly \
  --project $PROJECT --region asia-southeast1 \
  --max-retention-days 14 --daily-schedule --start-time 19:00
```

### 6. Restore

```bash
gcloud storage cp gs://[BUCKET]/plugmybrain-YYYY-MM-DD.sql.gz .
gunzip -c plugmybrain-YYYY-MM-DD.sql.gz | docker compose exec -T postgres psql -U plugmybrain -d plugmybrain
```

**Restore once into a scratch database before you trust it.** An untested backup is not a
backup. And the real durable store is the markdown vault: worst case, the whole database is
rebuildable by re-running `pmb sync`.

## Visualisation

Three views, because they answer different questions. All three are files you open, not
services you run.

| View | Command | Shows | Cost |
| :- | :- | :- | :- |
| Code map | `pmb map <path>` | Classes, functions, imports and the call graph, as an interactive `graph.html` | Zero API tokens, entirely local |
| Knowledge graph | `pmb visualize --project <name>` | The Cognee graph as one self-contained HTML file | One query, no model call |
| Vault graph | `pmb export --project <name>` | The same graph as `[[wikilink]]` notes, rendered by Obsidian's own graph view | One query, no model call |

```bash
pmb map C:\path\to\project                        # then open graph/<project>/graphify-out/graph.html
pmb visualize --project curated                   # then open docs/graph/kg/curated/graph.html
pmb export    --project curated                   # then open the vault in Obsidian
```

The vault view is the one to reach for when you want the knowledge graph *next to* the notes
that produced it, since Obsidian renders generated notes and human ones in one graph. The
standalone HTML is the one to reach for when you just want to look.

## One Stack or Several

Measured, so the trade is a number rather than a preference: `cognee-mcp` holds **280 MiB** and
Postgres **35 MiB**, so one stack is about 315 MiB.

**One stack, several vaults and projects.** The default, and what to reach for first. Datasets
are named after the folder they came from, so a personal standards vault, a company one, and
any number of project datasets all coexist in one database. Nothing to start or stop when you
switch context, and every dataset stays queryable at once. Isolation is enforced in
`retrieve.py`, and is tested.

```bash
PMB_VAULT=../docs           docker compose run --rm cognee-ingest   # dataset: docs
PMB_VAULT=../docs-standard  docker compose run --rm cognee-ingest   # dataset: docs-standard
```

**A stack per project.** Compose already does this with `-p`, no file changes needed. Each
project gets its own containers, volumes and database, so isolation is at the database rather
than enforced by this code.

```bash
MCP_PUBLISH_PORT=9001 DB_PUBLISH_PORT=15433 docker compose -p pmb-maia up -d
```

Register each one as its own MCP server, on its own port. The cost is 315 MiB per running
stack and a context switch that means stopping one stack, starting another, and restarting the
agent so it reconnects. On a 2 GiB VM, two stacks is the practical ceiling.

Prefer one stack unless a project genuinely must not share a database with the others. Turning
stacks off and on to save memory is a real strategy, but it buys isolation you already have.

## Moving to a Different Vault

`PMB_VAULT` decides which vault is the brain. Switching it is not a one-line change, because
Cognee stores the absolute path each document was ingested from.

1. The new vault needs `memory/` with `memory.rules.md`, `note.template.md` and the four type
   folders. `configure()` refuses to start without it, on purpose: a wrong path would otherwise
   report an empty corpus, which reads as "the vault is empty" rather than "the path is wrong".
2. It needs `graph/README.md`, and `graph/code/` plus `graph/kg/` in its `.gitignore`.
3. **Wipe the database first: `docker compose down -v`.** The existing dataset holds paths into
   the old vault. Mixing them leaves a corpus that half resolves, which fails later and further
   from the cause. This already cost one rebuild when host paths from Windows got in.
4. Only then set `PMB_VAULT` and re-ingest.

One vault serves every project. Projects are isolated by **dataset name**, not by having a
`memory/` each, so a new project needs `pmb map` and `pmb ingest` and nothing else. Splitting
the memory per project would scatter the shared rules across repositories, which is the problem
the vault exists to solve.

## Keeping What the Graph Found

Everything under `docs/graph/` is gitignored and **regenerated**, so a note you edit there is
destroyed by the next rebuild. That is the point: generated content is disposable, and the
memory is not.

When the graph surfaces something worth keeping, promote it:

```bash
pmb promote docs/graph/kg/curated/some-node.md --type fact
```

It lands in `docs/memory/<type>/` with the five-key frontmatter, a slugged filename, and a
`**Why:**` line waiting to be filled in. From that moment it is yours: committed, editable, and
ingested into the `curated` dataset, which **wins on conflict** with anything a machine
inferred. Edit it, run `pmb sync`, and every agent reads your version.

That is the whole loop. Cognee proposes, you decide, and the decision becomes the memory.

`promote` is the only code in this project that writes above the generated area. It refuses a
source outside `docs/graph/`, refuses to escape `docs/memory/`, and refuses to overwrite an
existing note without `--force`, because that note is human-authored and this program did not
write it.

## Agent Wiring

Both Claude Code and Codex reach the brain as a remote MCP server at
`http://127.0.0.1:9000/mcp`. **The same URL works in both setups**, which is the point:

- **Stack running locally.** `docker compose up -d` publishes the MCP server on loopback. No
  tunnel, no VM, nothing else to start.
- **Stack running on the VM.** Start the tunnel from `## Deployment` step 4; it forwards `8000`
  to the VM's loopback, so the URL the agents already have keeps working.

Neither agent runs a cognee process, and neither pays a cold start.

```powershell
claude mcp add --transport http plugmybrain http://127.0.0.1:9000/mcp --scope user
```

For Codex, add this to `~/.codex/config.toml` by hand. `codex mcp add` only registers stdio
servers, so the CLI cannot do this one:

```toml
[mcp_servers.plugmybrain]
url = "http://127.0.0.1:9000/mcp"
startup_timeout_sec = 60
```

**SSH is the authentication boundary.** The MCP server has no auth of its own and binds only to
the VM's loopback, so the tunnel is the only way to reach it. Plain HTTP is correct rather than
lazy: the traffic never leaves loopback on either end and SSH encrypts the hop between them.

### Slash commands

```bash
pmb install     # then restart Claude Code and Codex
```

Writes the same three files to `~/.claude/commands/` and `~/.codex/prompts/`. One source works
for both, since they share the frontmatter fields and `$ARGUMENTS`.

**The commands live in the vault, at `<vault>/agents/`, not in this repository.** They tell an
agent how to work, which makes them a standard rather than part of the tool. Point `PMB_VAULT`
at a different vault and `pmb install` picks up that vault's commands, with nothing to copy and
no second copy to drift. `PMB_AGENTS_DIR` overrides the location.

| Command | Does |
| :- | :- |
| `/pmb <question>` | Recall from the memory, with the dataset passed and sources cited |
| `/pmb-note [title]` | Summarise this session into a memory note, then ingest it |
| `/pmb-map [path]` | Build the code map, then query it instead of grepping |

They cost nothing from the Gemini or Voyage keys: the agent's own model does the work, and
those keys are only spent during ingestion.

The commands live in `agents/` in this repository rather than being written straight into your
home directory, so they are versioned with the tool they drive and survive a new machine.

`CLAUDE.md` and `AGENTS.md` in this repository are byte-identical and carry the same three
pointers: read `graph.json` for code structure, read the vault's `memory/` for rules, and pass
the dataset on every Cognee query. Other projects copy [[agent.template.md]] from the vault
rather than reinventing them.

## Usage

```bash
pmb map    /path/to/project          # code structure, zero API tokens
pmb ingest /path/to/project          # that project's documents, into its own dataset
pmb search "how is auth handled" --project project
pmb sync                             # re-ingest the curated rules and memory
pmb export    --project project      # knowledge graph as vault notes
pmb visualize --project project      # knowledge graph as one HTML file
pmb promote  <generated-note>        # keep one: move it into the human-authored memory
pmb eval                             # score and latency
pmb serve                            # the HTTP API
```

The dataset is the folder's own name and is required on every read. Nothing is ever scanned
without an explicit path.

**Isolation is enforced here, not by cognee.** Cognee keeps every dataset in one vector
collection and its `datasets` argument does not scope the search: a three-file dataset was
measured returning a decision note from another project. So `retrieve.py` asks Postgres which
documents belong to the dataset, over-fetches, and drops the rest before returning. Cognee's
own multi-tenant path was tried first and fails on this setup, connecting to port 123.

`mode=graph` cannot be filtered, because it returns prose rather than chunks with metadata.
That is one more reason `chunks` is the default.

## Configuration

Every variable the project reads. Names only; see [[env.rules.md]].

| Variable | Required | Description |
| :- | :- | :- |
| `PMB_VAULT` | No | Path to the Obsidian vault. Defaults to the sibling `docs` checkout |
| `PMB_GRAPH_DIR` | No | Where Graphify output lands. Defaults to `graph/` |
| `DB_HOST` `DB_PORT` `DB_NAME` `DB_USERNAME` | Yes | PostgreSQL connection. `postgres:5432` inside compose, `127.0.0.1:15432` from the laptop over the tunnel |
| `DB_PASSWORD` | Yes | Database password |
| `EMBEDDING_PROVIDER` `EMBEDDING_MODEL` | Yes | `voyage` and `voyage/voyage-3.5` |
| `EMBEDDING_DIMENSIONS` | Yes | `1024`. Above 2000 the process refuses to start |
| `EMBEDDING_API_KEY` | Yes | Voyage key. Separate from the chat key |
| `LLM_PROVIDER` `LLM_MODEL` | Yes | The chat model that builds the graph |
| `LLM_API_KEY` | Yes | Unless `LLM_PROVIDER=mcp-sampling`, which only works inside an MCP session |
| `POOL_ARGS` `VECTOR_POOL_ARGS` | No | Connection pool sizing |
| `CHUNK_SIZE` `CHUNK_OVERLAP` | No | Ingestion chunking |
| `PMB_INDEX` | No | `auto`, `exact`, `ivfflat` or `hnsw`. Default `auto` |
| `PMB_INDEX_THRESHOLD` | No | Rows below which exact search beats an index. Default 10000 |
| `BACKUP_BUCKET` `BACKUP_KEEP_DAYS` | No | VM only. Nightly `pg_dump` target and retention |
| `PMB_VM` `PMB_ZONE` `PMB_PROJECT` | No | Laptop only. Used by `scripts/tunnel.ps1` |

## Data

Nothing here is committed.

| Item | Location | Notes |
| :- | :- | :- |
| Code maps | `graph/<project>/graphify-out/` | Gitignored. Produced by `pmb map` |
| Code reports | `<vault>/graph/code/<project>/` | Gitignored in the vault. Never hand-edited |
| Graph export | `<vault>/graph/kg/<dataset>/` | Gitignored in the vault. Never hand-edited |
| The memory itself | `<vault>/memory/` and `<vault>/rules/` | Committed, human-authored, the source of truth |

## Project Structure

```text
plugmybrain/
  config.py      # paths, the exclusion list, the dimension and index guards
  ingest.py      # add, cognify, then the vector index cognee does not create
  retrieve.py    # dataset-scoped search
  export.py      # knowledge graph to vault wikilink notes, and to one HTML file
  promote.py     # the only module that writes into the human-authored memory
  eval.py        # the question set, scored, with p50 and p95
  api.py         # the HTTP surface
  cli.py         # the one entry point
compose.yaml     # postgres, cognee-mcp, and cognee-ingest behind a profile
scripts/
  provision-vm.sh   # swap, disk check, docker at boot, timezone
  tunnel.ps1        # the laptop's SSH forwards to the VM
  backup.sh         # nightly pg_dump to GCS
  init-pgvector.sql # CREATE EXTENSION, on first start only
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

The code map does not: `pmb map` runs tree-sitter locally with `--code-only` and makes no
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
- **1024 dimensions is a ceiling, not a preference.** pgvector will not index a `vector` column
  wider than 2000, by HNSW or IVFFlat. It does not fail loudly; it just leaves every search
  doing a sequential scan. `config.py` refuses to start above that.
- **The first corpus gets no vector index, on purpose.** pgvector sizes IVFFlat at
  `lists = rows / 1000`, so a few hundred chunks would produce a one-list index: a sequential
  scan carrying index overhead. Exact search over the same rows is faster and has perfect
  recall. `pmb sync` prints which index each table got and the row count that decided it.
- **HNSW is opt-in and wants roughly 4 GiB.** On a 2 GiB VM the index build is the thing that
  gets OOM-killed. `PMB_INDEX=hnsw` after resizing, not before.
- **Ingestion and serving must not run at once on 2 GiB.** `cognee-ingest` sits behind a
  compose profile so `docker compose up -d` cannot start it, and both cognee containers carry
  a `mem_limit` so Docker kills them before the kernel picks Postgres by size.
- **One VM is one point of failure.** Accepted for a personal brain. The nightly `pg_dump` is
  the mitigation, and the markdown vault is the real durable store: the database is rebuildable
  from files by re-running `pmb sync`.
- **There is no single no-model mode returning chunks and graph context together.** `chunks`
  returns sourced context with no completion step, `graph` spends an extra call. A combined
  retrieval mode would be a second query, and it is not built until the eval asks for it.
- **`memify` is called by signature introspection.** It is exported by cognee 1.4.2 but its
  definition could not be pinned from source, so `ingest.py` reads the installed function's
  parameters instead of assuming them. It is off unless you pass `--memify`.
- **No temporal layer.** Nothing here answers "what did I know in March". Git history does.

## Deviations From the Standards

Written down because [[deploy.rules.md]] and [[secret.rules.md]] require a deviation to say why.

1. **Not Cloud Run.** [[deploy.rules.md]] requires every deployed project to ship to Cloud Run
   via Cloud Build and Artifact Registry. PlugMyBrain runs as one Docker stack on a flat-cost
   Compute Engine VM instead. That file now carries a named exception for this one project;
   the reasoning is in `docs/memory/decision/`. In short: an always-on Postgres has no idle
   state to scale down to, so the managed equivalent bills a monthly floor for something a
   single small VM already covers. The exception does not generalise.
2. **No Alembic for the vector index**, where [[database.rules.md]] routes migrations through
   Alembic. Cognee owns and mutates its own schema, and a second migration tool fighting it
   breaks on every cognee upgrade. `ensure_vector_index()` is idempotent DDL run at the end of
   every ingest instead, and it has to run every time because cognee creates a new table per
   collection.
3. **No Secret Manager.** Values live in a gitignored `.env` on the laptop and a `0600`
   root-owned `.env` on the VM. [[secret.rules.md]] ranks Secret Manager first and a gitignored
   `.env` second, so this takes the second-ranked option. The cost, stated so it is a decision
   rather than an accident: no rotation history, no per-secret IAM, and a value readable by
   anything that can read the file.
4. **The conda environment is named `env`**, where [[codes.rules.md]] says to name it after the
   project. Chosen deliberately.

## License

None. This is a personal project and carries no licence, which means default copyright: all
rights reserved, and nobody else has permission to use, copy or modify it. That is a deliberate
choice for now, not an oversight. Adding one later is a one-file change.
