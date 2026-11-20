# PlugMyBrain

The memory brain itself. Six MCP tools, ten slash commands, and everything else is markdown.

@README.md

## Before You Search This Repository

**Code structure comes from the map, not from grepping.** Once this checkout has been digested, call the `plugmybrain` server's `code_map` tool with `brain: "plugmybrain"`, or query the raw graph directly:

```bash
graphify query "where is the vector index created" --graph graph/plugmybrain/graphify-out/graph.json
graphify god-nodes --graph graph/plugmybrain/graphify-out/graph.json
```

If the map is stale, digest again rather than reading files to compensate.

## The Surface Is Small On Purpose

The MCP server in `plugmybrain/server.py` is the whole product. Six tools: `recall`, `brains`, `status` and `code_map` read; `digest` and `reset` write to the index and the vault only. The `/pmb-*` commands in `commands/` are prompts that tell an agent which tool to call, and `/pmb-setup` in `.claude/commands/` wires a machine once.

Do not add a seventh tool or another command because a task would be easier with one. Every tool an agent can see costs context on every turn, which is why cognee-mcp's eleven were replaced.

`plugmybrain/cli.py` is what a background job runs inside the container. It is not the interface; never tell a user to type it.

## Rules That Keep It Honest

- **The server never writes into a project.** `PMB_WORKSPACE` is mounted read-only. Roles, scaffolds and notes are written by the agent's own file tools, as the commands describe.
- **Never write into Cognee directly.** A note is a markdown file in the folder's `memory/`, folded in by the next digest. A note that exists only in the index is gone at the next rebuild, which is why `remember` and `forget` are not exposed.
- **Do not hand-edit anything under the vault's `graph/code/`.** Every digest rebuilds it and every reset deletes it.
- **Isolation is by document id.** Cognee's `datasets` argument does not scope a search, so `retrieve.py` keeps only chunks whose `document_id` belongs to the requested brain in Postgres. Never filter by file name: two brains often share one.
- **One embedding model per database.** `manage.embedding_mismatch` refuses a digest or a search with a model other than the one recorded. Do not weaken it to make a switch easier.
- **Ingestion runs in the container.** On the Windows host Cognee's subprocess workers hang, and a killed run writes host paths into Postgres that no later run can resolve.

## There Is No Chat Model

Do not add one back. A digest runs Cognee's pipeline with `extract_graph_and_summarize` removed: the one step of five that calls a chat model, and the one that produced a real bill, roughly $9 for a 3.6MB corpus. `cognify()` hardcodes its five tasks, so `ingest.py` calls `run_pipeline` with its own list. If a task ever needs adding, check first whether it calls a model.

The cost: no entity graph, so a question needing traversal between documents is not answered by `recall`. Retrieval within documents is unaffected and is what an agent needs.
