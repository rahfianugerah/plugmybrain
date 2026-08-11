# PlugMyBrain

The memory brain itself. Its own rules live in the vault; this file is the entry point.

@README.md
@../docs/memory/memory.rules.md

## Before You Search This Repository

**Code structure comes from the map, not from grepping.** `graph/<project>/graphify-out/graph.json`
is an AST map extracted by tree-sitter, and reading it costs no model tokens. Query it instead
of walking the tree:

```bash
graphify query "where is the vector index created" --graph graph/plugmybrain/graphify-out/graph.json
graphify god-nodes --graph graph/plugmybrain/graphify-out/graph.json
```

If the map is stale, rebuild it with `pmb map .` rather than reading files to compensate.

## Rules Come From the Vault, Not From Here

`../docs/rules/` and `../docs/memory/` are the human-authored control plane and they win on
conflict with anything inferred from this code. Read `../docs/memory/` for decisions already
made; the reasoning behind the VM, the embedding model, the graph store and the retrieval
default is written down there, so do not re-derive it.

Never read the whole vault to answer a question about this code. That is what the map is for.

## The PlugMyBrain MCP Server

At `http://127.0.0.1:9000/mcp`, whether the stack runs here or on the VM behind the tunnel.

**Read with `recall`.** Always pass `datasets`, so one project's memory cannot leak into
another's answer. `curated` is the vault's own rules and memory.

```json
{"query": "why is there no licence", "datasets": ["curated"],
 "search_type": "CHUNKS", "top_k": 15}
```

`search_type: "CHUNKS"` returns sourced passages with no second model call. Use
`GRAPH_COMPLETION` only when you actually want prose synthesised, because it costs an extra
call on a path that runs on every question.

## Two Things Not to Do

- **Never call `remember` or `forget`.** They are exposed by the MCP server and they write
  straight into the index, which the next `pmb sync` overwrites. The memory is markdown: write
  a note into `../docs/memory/`, then run `pmb sync`. A note that exists only in Cognee is a
  note that is already gone, and nothing will warn you.
- Do not hand-edit anything under `../docs/graph/`. It is regenerated and gitignored. If
  something there is worth keeping, `pmb promote` moves it into the memory properly.
