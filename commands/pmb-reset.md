---
description: Delete a folder's PlugMyBrain memory, or all of it, never the markdown
argument-hint: [folder | all]
---

Reset PlugMyBrain memory: $ARGUMENTS

The argument is a folder, `all`, or nothing for the current working directory.

1. **Ask the user first, every time.** Name exactly what goes: the memory for that folder, or every memory in the database for `all`, plus its generated notes under the vault's `graph/`. Say that no markdown file is touched, and that `/pmb-digest` rebuilds it at the cost of embedding it again.
2. **Only after a clear yes**, call the `plugmybrain` MCP server's `reset` tool:
   - For a folder: `folder` as its absolute path, and `confirm` as its name lowercased.
   - For `all`: `everything` true, and `confirm` as `everything`.
3. If the reply says it is still running, call `reset` again with the same arguments to keep waiting.
4. Report what was deleted, and offer `/pmb-digest`.

`all` is the step that lets the embedding model change, since a database cannot mix two.
