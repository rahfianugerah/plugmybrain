---
description: Answer a question from PlugMyBrain memory, with sources
argument-hint: <question>
---

Answer from PlugMyBrain memory: $ARGUMENTS

Call the `plugmybrain` MCP server's `recall` tool with the question as `query`. For `brain`, use the one `/pmb-map` set in this session, otherwise the current folder's name lowercased. If that name is not a brain, call `brains` and ask which one.

- **Answer only from the passages returned**, and name the source file for each claim.
- **If nothing matches, say so.** Do not fill the gap from general knowledge: an unsourced answer that looks sourced is worse than an empty one.
- **Where passages disagree, show both** with their files, and let the user decide which governs.

Any question can reach the memory without this command; the agent calls `recall` on its own. This command makes the memory the only source for one answer.
