# PlugMyBrain

The memory brain itself. Four commands, two MCP tools, and everything else is markdown.

@README.md

## Before You Search This Repository

**Code structure comes from the map, not from grepping.** `graph/plugmybrain/graphify-out/graph.json`
is an AST map extracted by tree-sitter, and reading it costs no model tokens. Query it instead
of walking the tree:

```bash
graphify query "where is the vector index created" --graph graph/plugmybrain/graphify-out/graph.json
graphify god-nodes --graph graph/plugmybrain/graphify-out/graph.json
```

If the map is stale, rebuild it with `pmb digest` rather than reading files to compensate.

## The Surface Is Small On Purpose

`pmb init`, `pmb digest`, `pmb reset`, `pmb list`. Two MCP tools, `recall` and `brains`, and
neither writes. Do not add a fifth command or a third tool because a task would be easier with
one; every tool an agent can see costs context on every turn, which is why cognee-mcp's eleven
were dropped for two.

The folder is the unit. `pmb digest <folder>` makes that folder a memory named after itself.
`.pmb` holds one word, `root` or `brain`. A root digests every child that has markdown, brains
first. Roles are optional: any folder with markdown digests without one.

**A digested folder is only ever read.** Everything generated lands in `config.DOCS`, one
Obsidian vault, under `graph/code/<brain>/` and `graph/kg/<brain>/`. Never write into the folder
being digested; that property is why the mount can be read-only.

`init` runs on the host because it writes into the home directory. The other three run in the
container: native `pmb` hangs on cognee's subprocess workers on Windows, and a killed run writes
host paths into Postgres that no later run can resolve.

## The PlugMyBrain MCP Server

`plugmybrain/server.py`, at `http://127.0.0.1:9000/mcp`. Two tools:

```json
{"query": "why is there no licence", "brain": "plugmybrain", "top_k": 15}
```

`recall` returns passages with the file each came from. Pass `brain`, which is the folder's own
name lowercased; several comma-separated only when a question genuinely spans them. `brains`
lists what exists.

Isolation is enforced against Postgres in `retrieve.py`, not by cognee: cognee keeps every
memory in one vector collection and its `datasets` argument does not scope a search, so
membership is checked and foreign documents are dropped before the agent sees them.

## Two Things Not to Do

- **Never write to Cognee directly.** The memory is markdown: write a note into the folder's
  `memory/`, then digest. A note that exists only in the index is gone at the next rebuild, and
  nothing will warn you. This is why `remember` and `forget` are not exposed.
- Do not hand-edit anything under the vault's `graph/code/` or `graph/kg/`. Both are rebuilt by
  every digest and deleted by every reset. If something there is worth keeping, move it into
  `memory/` yourself and write down why.

## Cost

The chat model runs once per digest and never on a query, so reading is free. Compare models on
**output** price: cognify emits structured JSON per chunk, and that is where the bill is.
`gemini-3.5-flash` charges $9.00/M out, five times `gemini-2.0-flash`, despite the name.
