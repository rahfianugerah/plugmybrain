---
description: Point this session at a different PlugMyBrain brain
argument-hint: [folder or brain name, blank to list]
---

Switch which memory this session reads from: $ARGUMENTS

Call the `plugmybrain` MCP server's `brains` tool first. It lists every memory on this machine with its document count.

- **No argument.** Show the list and ask which one. Do not guess.
- **An argument.** Resolve it to a brain name: a path becomes its folder name lowercased, so `C:\Users\you\work\docs-standard` becomes `docs-standard`. A bare name is used as is. If it is not in the list, say so and show what is, rather than calling `recall` with a name that does not exist.

Then confirm in one line: *"This session now reads from `<name>` (`<n>` documents)."*

**For the rest of this session, pass `brain: "<name>"` on every `recall` call, and the same name on every `code_map` call.** That is the whole mechanism: one database holds every memory, and the brain is which one a question is answered from. Nothing restarts and nothing on disk changes.

Several at once is allowed where a question genuinely spans them, comma-separated: `brain: "docs-standard,billing-service"`. Prefer one. A question answered from two brains cites two sets of rules, and the user then has to work out which one governs.

If the user asks for a brain that has not been digested yet, tell them to run `/pmb-digest` in that folder. Do not offer to answer from general knowledge instead.
