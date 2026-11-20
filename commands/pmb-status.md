---
description: Show what PlugMyBrain holds against what a folder has
argument-hint: [folder]
---

Show the PlugMyBrain status: $ARGUMENTS

Call the `plugmybrain` MCP server's `status` tool with `folder` set to the folder named above, or to the current working directory as an absolute path. Pass an empty `folder` when the user asks about the database as a whole.

Show the result as it comes, then say in one line what needs doing, if anything:

- **Markdown not yet digested.** Offer `/pmb-digest`.
- **A job still running.** Say what it is and how long it has run.
- **An `embedding` line that differs from the model the user expects.** A database built with one model cannot be searched with another. Offer `/pmb-reset all` followed by `/pmb-digest`, or switching back.

It reads only. Nothing is written and nothing is billed.
