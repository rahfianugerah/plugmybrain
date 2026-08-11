---
description: Build the Graphify code map, then read it instead of grepping the tree
argument-hint: [path, defaults to the current repository]
---

Build or refresh the code map for: $ARGUMENTS (default: the current repository root)

```bash
pmb map <path>
```

This costs **no API tokens and sends nothing anywhere**. Tree-sitter parses the code locally.

Then answer structural questions from the map rather than by reading files:

```bash
graphify query "<question>" --graph <graph-dir>/graphify-out/graph.json --budget 2000
graphify god-nodes --graph <graph-dir>/graphify-out/graph.json
graphify explain "<symbol>" --graph <graph-dir>/graphify-out/graph.json
```

`pmb map` prints where `graph.json` landed. The map is the point: an agent that greps the tree
to work out how code is wired pays for that in tokens every session, and pays more as the
project grows. If the map looks stale, rebuild it rather than reading files to compensate.

Documents are a separate path: they belong to `pmb ingest`, not `pmb map`.
