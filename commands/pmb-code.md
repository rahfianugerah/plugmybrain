---
description: Ask a folder's Graphify code map where something lives
argument-hint: [question]
---

Ask the PlugMyBrain code map: $ARGUMENTS

Call the `plugmybrain` MCP server's `code_map` tool. For `brain`, use the current folder's name lowercased unless the user named another. Pass the question as `question`; with no question, the tool lists the most connected parts of the codebase, which is the fastest way into an unfamiliar one.

- **Open the files the map names**, rather than searching the whole tree. The map was extracted from the source by tree-sitter, so reading it costs no model tokens.
- **A map is as fresh as the last digest.** If it names something that no longer exists, offer `/pmb-digest`.
- **No map means no source code**, or a folder never digested. A folder of pure markdown has none.
