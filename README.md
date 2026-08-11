# PlugMyBrain

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)
![Cognee](https://img.shields.io/badge/Cognee-1.4.2-0F766E)
![Graphify](https://img.shields.io/badge/Graphify-0.9.38-B45309)
![Obsidian](https://img.shields.io/badge/Obsidian-Required-7C3AED?logo=obsidian&logoColor=white)
![Status](https://img.shields.io/badge/Status-WIP-D29922)

A plug-and-play memory for coding agents. Point it at a folder of markdown and that folder
becomes a brain: a knowledge graph the agent queries over MCP, a code map it reads instead of
grepping, and more markdown written into your vault so you can see the whole thing.

It exists because an agent with no memory relearns the same context every session and pays for
that in tokens every time.

**Obsidian is required.** It is the viewer, and there is no other. Everything generated is
markdown in one vault, so the graph a model built sits next to the notes a person wrote and
renders in the same graph view.

## Four Commands

That is the whole surface. The folder you point at is the memory, and its name is what the
memory is called.

| Command | Does |
| :- | :- |
| `pmb init root\|brain` | Gives a folder its role, and wires Claude Code and Codex to the brain. Nothing else to set up by hand |
| `pmb digest` | Reads every markdown file into Cognee, builds the Graphify code map, and writes the knowledge graph into the vault as linked markdown |
| `pmb reset` | Deletes that memory from the database and its generated notes. **Every markdown file survives**, so a digest rebuilds it |
| `pmb list` | What the database holds, every memory in it, and how the folder's markdown count compares with what was actually digested |

Each takes an optional folder and defaults to the current one. `pmb digest --dry-run` estimates
the cost before spending anything.

**Asking questions needs no command.** The memory is connected as an MCP server, so a question
is answered by the agent calling it directly. In an agent write `/pmb digest`; in a terminal it
is just `pmb digest`.

There is a fifth thing, and it is not a command: **`/pmb-map <brain>`** tells the current chat
session to read from a different brain from here on. It changes nothing on disk and restarts
nothing; one stack holds every memory, and this is which one gets asked.

**This is built for coding agents.** Claude Code, Codex, opencode, and anything else speaking
MCP. It is not a chatbot back end, and the chat model it uses exists for one job: turning
markdown into a graph, once, when you digest. Reading never calls a model, so an agent asking a
question costs nothing.

## Two Roles

`pmb init` writes a one-word `.pmb` file naming the folder's role. It lives in the folder rather
than in a config file under your home directory, because the container only ever sees the
folder, and it is committed, so a clone on another machine already knows the layout.

| Role | Is | Digested as |
| :- | :- | :- |
| `brain` | The rules and memory folder, like `docs/` or `docs-standard/` | One memory. Scaffolded with `memory/` if it is missing |
| `root` | A parent holding many projects, like `maharum/` | Every child that has markdown, **brain first**, each its own memory |

Brain first because everything else is read against the rules, so a run that stops halfway
still leaves you a standard rather than a pile of code with nothing to judge it by.

```bash
cd C:/Users/you/maharum         &&  pmb init root .        # the parent
cd C:/Users/you/maharum/docs-standard && pmb init brain .  # its rules
cd C:/Users/you/docs            &&  pmb init brain .       # a standalone brain
```

A folder needs neither role. `pmb digest some-project` works on anything with markdown in it;
the roles only exist so a parent can be digested in one go.

## Nothing Is Written Into a Digested Folder

A folder you digest is only ever **read**. Everything generated lands in one Obsidian vault,
namespaced per brain:

```text
your-folder/                      the vault (PMB_DOCS, default ../docs)
  .pmb      root or brain           graph/
  memory/   human-authored            README.md          yours, survives a reset
  ...       every other .md           code/<brain>/      the Graphify map
                                      kg/<brain>/        the Cognee knowledge graph
```

Eighteen service repositories do not each need a `graph/` nobody asked for, and the point of an
Obsidian vault is that it is **one** vault you open and see everything in. So the write path is
the vault and only the vault, which is also why the digest mount can be read-only.

`memory/` and `.pmb` are the only two names a digested folder is expected to have, and both are
optional. Any folder with markdown in it digests.

## Setup

**1. Environment.** Conda, an environment named `env`, Python 3.13.

```bash
conda env update -f environment.yml
conda activate env
pip install -e .
```

**2. Configuration.** Copy the template and fill it in by hand.

```bash
cp .env.example .env
```

Two keys, from different vendors: `EMBEDDING_API_KEY` from Voyage and `LLM_API_KEY` from
whichever chat provider you uncomment. Also set `DB_PASSWORD`.

**The chat key is spent by `digest` and by nothing else.** Cognify makes two model calls per
chunk, one extracting entities and relations as structured JSON and one summarising, so it is
the *output* price that decides the bill. Compare on that, not on the family name: measured
against a 199 KB folder and scaled to 3.6 MB, `gpt-5-nano` costs $0.35, `gemini-2.0-flash`
$0.48, `gpt-5-mini` $1.76, `claude-haiku-4-5` $5.37, and `gemini-3.5-flash` $8.89 — that last
one charges $9.00 per million output tokens, nearly what 2.5-pro does. `gpt-5-mini` is the
sensible default. Reading calls no model at all.

**3. Database.** PostgreSQL 18 with pgvector. Relational, vector and graph in one container.

```bash
docker compose up -d
docker compose ps          # wait for healthy
```

**Step 2 has to come first.** `compose.yaml` declares `.env` as a required env file, so
`docker compose up` without it fails. That is deliberate: made optional, the MCP server would
start on Cognee's embedded SQLite defaults and quietly serve the wrong database.

`compose.override.yaml` is picked up automatically on a laptop and only moves Postgres to port
15432, because a development machine usually already owns 5432.

**4. Tell it what your folders are, and let it wire the agents.**

```bash
cd C:/Users/you/maharum && pmb init root .
cd docs-standard        && pmb init brain .
```

`init` runs on the host, not in the container: it registers the MCP server with Claude Code and
Codex and writes `/pmb` and `/pmb-map` with this checkout's paths already filled in. Restart
both agents afterwards. There is nothing else to configure.

**5. Digest.**

```bash
FOLDER=C:/Users/you/maharum
docker compose run --rm -v "$FOLDER:/w/maharum" pmb digest /w/maharum --dry-run
docker compose run --rm -v "$FOLDER:/w/maharum" pmb digest /w/maharum
```

On a root that walks every child. On any other folder it digests just that one.

**Always run in the container.** `pmb` on the host hangs on Cognee's subprocess database
workers on Windows, and a killed run stores host paths in Postgres that no container can
resolve afterwards, which costs a `docker compose down -v`.

**The mount path carries the folder's name on purpose.** `/w/<name>` is what makes the memory
be called `maharum` rather than the mount point. A fixed mount would erase the name and every
folder would be digested into one shared memory that overwrites the last.

**6. Look at it.** Open the **vault** in Obsidian, not the project. `graph/kg/<brain>/` is the
knowledge graph as linked notes, sitting beside the `memory/` notes that produced it.

## The MCP Server

Two tools, and neither can write.

| Tool | Does |
| :- | :- |
| `recall(query, brain, top_k)` | Searches one brain, or several comma-separated, and returns passages with the file each came from |
| `brains()` | Lists every memory and its document count. What `/pmb-map` reads |

It is `plugmybrain/server.py`, not `cognee-mcp`. cognee-mcp exposes eleven: `remember`,
`recall`, `forget`, `cognify_file`, `create_dataset_json`, `list_datasets_json`,
`list_dataset_data_json`, `get_client_info_json`, `upload_file_ui`, `open_cognee_workspace`
and `visualize_graph_ui`. Three of those write straight into the index, which the next digest
silently overwrites; four dump JSON that `pmb list` already prints; three open a browser UI
that has no place in a coding agent. **Every tool an agent can see costs context on every turn,
whether it is called or not.** Dropping it also dropped its `cognee[docs,neo4j]` dependency
line, which is where torch, triton and 2.7GB of CUDA libraries came from.

Isolation is real here, not advisory. Cognee keeps every memory in one vector collection and
its own `datasets` argument does not scope a search, so `recall` asks Postgres which documents
belong to the brain, over-fetches, and drops the rest before the agent sees them.

`pmb init` wires it: `claude mcp add` for Claude Code, an appended
`[mcp_servers.plugmybrain]` block in `~/.codex/config.toml` because `codex mcp add` handles
stdio servers only, and both slash commands into `~/.claude/commands/` and `~/.codex/prompts/`.
Both config files are appended to, never rewritten. Re-running `init` is safe. If `claude` is
not on PATH it says so and prints the one command to run yourself.

The URL is `http://127.0.0.1:9000/mcp` whether the stack runs here or on a VM behind the
tunnel, which is the point.

## Deployment

One `docker compose` stack, identical on a laptop and on a single always-on Compute Engine VM.
No Cloud Run, no Cloud SQL, no Secret Manager. See `## Deviations From the Standards`.

Nothing below is run for you. Substitute your own project and confirm the cost first.

```bash
export PROJECT=[PROJECT] ZONE=asia-southeast1-a VM=plugmybrain
gcloud compute instances create $VM --project $PROJECT --zone $ZONE \
  --machine-type e2-small --image-family debian-12 --image-project debian-cloud \
  --boot-disk-size 30GB --boot-disk-type pd-balanced
gcloud compute firewall-rules create pmb-iap-ssh --project $PROJECT \
  --allow tcp:22 --source-ranges 35.235.240.0/20
```

30GB is not generosity: Docker images plus Postgres data plus WAL plus logs on a 10GB disk is
how a data directory gets corrupted. There is deliberately no rule for 5432 or 9000; both bind
to the VM's loopback and are reached only through the tunnel.

```bash
gcloud compute ssh $VM --tunnel-through-iap --zone $ZONE
sudo bash scripts/provision-vm.sh              # swap, disk check, docker at boot, Asia/Jakarta
sudo install -m 600 /dev/null /opt/plugmybrain/.env
sudo vi /opt/plugmybrain/.env                  # DB_HOST=postgres inside compose
sudo docker compose up -d
```

From the laptop, one SSH session carries both ports and reconnects if it drops:

```powershell
$env:PMB_VM="plugmybrain"; $env:PMB_ZONE="asia-southeast1-a"; $env:PMB_PROJECT="[PROJECT]"
.\scripts\tunnel.ps1
```

Set `DB_PORT=15432` in the laptop's `.env`. The odd port is deliberate: a dev Postgres already
holding 5432 would otherwise make the forward fail in a way that reads as a database problem.

### Backups

```bash
gcloud storage buckets create gs://[BUCKET] --project $PROJECT --location asia-southeast1
gcloud storage buckets add-iam-policy-binding gs://[BUCKET] \
  --member "serviceAccount:$(gcloud compute instances describe $VM --zone $ZONE \
    --format 'value(serviceAccounts[0].email)')" --role roles/storage.objectAdmin
sudo crontab -e
# 0 3 * * * /opt/plugmybrain/scripts/backup.sh >> /var/log/pmb-backup.log 2>&1
```

The timezone is set by `provision-vm.sh`. Without it cron runs UTC and 03:00 becomes 10:00
local. The script exits non-zero on an empty dump or a nearly full disk, because a backup
script that fails quietly is worse than none: it is trusted.

```bash
gunzip -c plugmybrain-YYYY-MM-DD.sql.gz | docker compose exec -T postgres psql -U plugmybrain -d plugmybrain
```

**Restore once into a scratch database before you trust it.** An untested backup is not a
backup. The real durable store is the markdown: worst case, the whole database comes back from
`pmb digest`.

## One Stack or Several

Measured, so the trade is a number rather than a preference: the MCP server holds **280 MiB**
and Postgres **35 MiB**, so one stack is about 315 MiB.

**One stack, many folders.** The default. Memories are named after the folder they came from,
so any number of them coexist in one database and every one stays queryable at once. Nothing to
start or stop when you switch context.

**A stack per folder.** Compose already does this with `-p`, no file changes needed, and
isolation is then at the database rather than by name.

```bash
MCP_PUBLISH_PORT=9001 DB_PUBLISH_PORT=15433 docker compose -p pmb-work up -d
```

Prefer one stack unless a folder genuinely must not share a database with the others. On a
2 GiB VM, two stacks is the practical ceiling.

## Configuration

Every variable the project reads. Names only; see [[env.rules.md]].

| Variable | Required | Description |
| :- | :- | :- |
| `DB_HOST` `DB_PORT` `DB_NAME` `DB_USERNAME` | Yes | PostgreSQL connection. `postgres:5432` inside compose, `127.0.0.1:15432` from a laptop over the tunnel |
| `DB_PASSWORD` | Yes | Database password |
| `EMBEDDING_PROVIDER` `EMBEDDING_MODEL` | Yes | `voyage` and `voyage/voyage-3.5` |
| `EMBEDDING_DIMENSIONS` | Yes | `1024`. Above 2000 the process refuses to start |
| `EMBEDDING_API_KEY` | Yes | Voyage key. Separate from the chat key |
| `EMBEDDING_ENDPOINT` | If Atlas | Only for a MongoDB Atlas key. A `dash.voyageai.com` key must leave it unset |
| `LLM_PROVIDER` `LLM_MODEL` `LLM_API_KEY` | Yes | The chat model that builds the graph |
| `PMB_DOCS` | No | The one Obsidian vault every brain generates into. Defaults to the sibling `docs` checkout |
| `PMB_GRAPH_DIR` | No | Where Graphify's raw `graph.json` lands. Defaults to `graph/` in this repo |
| `POOL_ARGS` `VECTOR_POOL_ARGS` | No | Connection pool sizing |
| `CHUNK_SIZE` `CHUNK_OVERLAP` | No | Ingestion chunking |
| `PMB_INDEX` | No | `auto`, `exact`, `ivfflat` or `hnsw`. Default `auto` |
| `PMB_INDEX_THRESHOLD` | No | Rows below which exact search beats an index. Default 10000 |
| `BACKUP_BUCKET` `BACKUP_KEEP_DAYS` | No | VM only. Nightly `pg_dump` target and retention |
| `PMB_VM` `PMB_ZONE` `PMB_PROJECT` | No | Laptop only. Used by `scripts/tunnel.ps1` |

Which folder is a brain is not a setting: it is the folder you point `pmb` at, and its name is
the memory. `PMB_DOCS` is only where the generated notes go.

## Project Structure

```text
plugmybrain/
  config.py      # paths, the exclusion list, the dimension and index guards
  bootstrap.py   # init: folder roles, the brain scaffold, and the agent wiring
  ingest.py      # add, cognify, then the vector index cognee does not create
  export.py      # the knowledge graph as Obsidian wikilink notes
  retrieve.py    # brain-scoped search, enforced against Postgres
  server.py      # the MCP server: two read-only tools
  manage.py      # list and reset
  cli.py         # the four commands
agents/
  pmb.md         # /pmb, installed by init into both agents with paths filled in
  pmb-map.md     # /pmb-map, switching which brain a session reads from
compose.yaml     # postgres, the MCP server, and the pmb runner behind a profile
scripts/         # provision-vm.sh, tunnel.ps1, backup.sh, init-pgvector.sql
tests/
```

## Development

```bash
ruff check .          # lint
ruff format .         # format
pytest                # tests
```

## Privacy

**"Local" describes the database only.** Every digested document is sent to the cloud model for
extraction and embedding. Data leaves the machine.

The code map does not: Graphify runs tree-sitter locally with `--code-only` and makes no network
call at all. That is why code structure comes from Graphify and documents from Cognee, rather
than putting source through the model.

`config.py` refuses to digest a path matching the exclusion list, whatever folder it is pointed
at, and prints what it skipped. The ceiling: it matches on names and directories, so a secret
pasted into an ordinary `.md` still gets through.

## Known Limitations

- **Only markdown is digested.** Obsidian is the viewer and markdown is the substrate, so PDF,
  docx and csv are not read. Convert first if you need them.
- **A chat model is required to digest, and there is no way around it.** Cognify is what turns
  markdown into a graph, and extraction is a model call. It runs once per digest and never on a
  query, so the cost is one-off per corpus rather than per question, but "no LLM key at all"
  would mean no Cognee and therefore no retrieval.
- **The graph store is a demo feature.** Postgres-as-graph is released by Cognee as a demo; the
  production version is licensed. It is used here because one database holds relational, vector
  and graph at once. If it proves unstable, `GRAPH_DATABASE_PROVIDER=kuzu` works locally with
  no other change.
- **The embedding model is locked to the corpus.** Swapping the chat model is free. Swapping
  `EMBEDDING_MODEL` or `EMBEDDING_DIMENSIONS` means re-embedding everything.
- **1024 dimensions is a ceiling, not a preference.** pgvector will not index a `vector` column
  wider than 2000, by HNSW or IVFFlat. It does not fail loudly; it just leaves every search
  doing a sequential scan. `config.py` refuses to start above that.
- **The first corpus gets no vector index, on purpose.** pgvector sizes IVFFlat at
  `lists = rows / 1000`, so a few hundred chunks would produce a one-list index: a sequential
  scan carrying index overhead. `pmb digest` prints which index each table got and the row
  count that decided it.
- **HNSW is opt-in and wants roughly 4 GiB.** On a 2 GiB VM the index build is the thing that
  gets OOM-killed. `PMB_INDEX=hnsw` after resizing, not before.
- **Digesting and serving must not run at once on 2 GiB.** The `pmb` service sits behind a
  compose profile so `docker compose up -d` cannot start it, and both containers carry a
  `mem_limit` so Docker kills them before the kernel picks Postgres by size.
- **One VM is one point of failure.** Accepted for a personal brain. The nightly `pg_dump` is
  the mitigation, and the markdown is the real durable store.
- **No temporal layer.** Nothing here answers "what did I know in March". Git history does.

## Deviations From the Standards

Written down because [[deploy.rules.md]] and [[secret.rules.md]] require a deviation to say why.

1. **Not Cloud Run.** [[deploy.rules.md]] requires every deployed project to ship to Cloud Run
   via Cloud Build and Artifact Registry. PlugMyBrain runs as one Docker stack on a flat-cost
   Compute Engine VM instead. That file carries a named exception for this one project; the
   reasoning is in the vault's `memory/decision/`. In short: an always-on Postgres has no idle
   state to scale down to, so the managed equivalent bills a monthly floor for something a
   single small VM already covers. The exception does not generalise.
2. **No Alembic for the vector index**, where [[database.rules.md]] routes migrations through
   Alembic. Cognee owns and mutates its own schema, and a second migration tool fighting it
   breaks on every Cognee upgrade. `ensure_vector_index()` is idempotent DDL run at the end of
   every digest instead, and it has to run every time because Cognee creates a new table per
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
