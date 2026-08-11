---
description: Point this session at a different brain
argument-hint: [folder or brain name, blank to list]
---

Switch which memory this session reads from: $ARGUMENTS

Call the `plugmybrain` MCP server's `brains` tool first. It lists every memory on this machine
with its document count.

- **No argument.** Show the list and ask which one. Do not guess.
- **An argument.** Resolve it to a brain name: a path becomes its folder name lowercased,
  `C:\Users\Rahfi\maharum\docs-standard` becomes `docs-standard`. A bare name is used as is.
  If it is not in the list, say so and show what is, rather than calling `recall` with a name
  that does not exist.

Then confirm in one line: *"This session now reads from `<name>` (`<n>` documents)."*

## What it changes

**For the rest of this session, pass `brain: "<name>"` on every `recall` call.** That is the
whole mechanism: one stack holds every memory, and the brain is which one a question is
answered from. There is no container to restart and nothing on disk to change.

Use it when the work moves to a different project or a different set of standards mid-session,
which is exactly when an answer sourced from the previous brain would look right and be wrong.

Several at once is allowed where the question genuinely spans them, comma-separated:
`brain: "docs-standard,maia-erp-backend"`. Prefer one. A question answered from two brains
cites two sets of rules, and the user then has to work out which one governs.

If the user asks for a brain that has not been digested yet, tell them to run `/pmb digest` in
that folder. Do not offer to answer from general knowledge instead.
