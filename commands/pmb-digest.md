---
description: Digest a folder into PlugMyBrain memory, and map its code
argument-hint: [folder]
---

Digest into PlugMyBrain: $ARGUMENTS

Call the `plugmybrain` MCP server's `digest` tool with `folder` set to the folder named above, or to the current working directory as an absolute path.

- **It runs in the background.** While the reply says it is still running, call `digest` again with the same folder to keep waiting. Do not start anything else against the memory meanwhile.
- **When it ends, report per memory**: how many markdown files were digested, what the exclusion list skipped, each index line, and the code map. Quote a failure verbatim; do not paraphrase it.
- **A root folder digests every child**, brains first, each into its own memory.
- **A folder outside the workspace is refused.** The server reads only `PMB_WORKSPACE`. Tell the user to move the folder under it, or widen it in `.env` and run `/pmb-setup` again.

The only cost is embedding: an embedding API bills per token, and Ollama costs nothing. No chat model is involved.
