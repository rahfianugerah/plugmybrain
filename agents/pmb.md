---
description: Recall from the PlugMyBrain memory before answering
argument-hint: [question]
---

Answer this from the memory, not from general knowledge: $ARGUMENTS

Use the `plugmybrain` MCP server's `recall` tool:

- `datasets`: `["curated"]` for rules and decisions. For a question about a specific codebase,
  use that project's dataset name instead. **Always pass it**, so one project's memory cannot
  leak into another's answer.
- `search_type`: `"CHUNKS"`. It makes no second model call. Use `"GRAPH_COMPLETION"` only when
  prose synthesis is genuinely wanted, because it costs an extra call.
- `top_k`: 15.

Then cite the source files it returned.

If nothing relevant comes back, say so plainly rather than answering from general knowledge. An
unsourced answer that looks sourced is worse than admitting the memory is empty on this.
