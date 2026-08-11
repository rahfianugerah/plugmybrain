---
description: Save what this session learned into the PlugMyBrain memory
argument-hint: [optional title]
---

Write one memory note for this session. Title hint, if given: $ARGUMENTS

**First apply the test, and be willing to fail it.** From `memory.rules.md`: would the next
session waste time without this? If not, say so and write nothing. A memory full of noise is a
memory nobody reads. One note per session, never one per turn.

Never record a secret, a real configuration value, anything the code or git history already
says, or a running summary of the conversation. Write the durable finding, not the transcript.

Then run this from the `plugmybrain` repository:

```bash
pmb note "<title that states the thing, not the topic>" --type session --tags <project>,<topic> <<'EOF'
<what happened, short enough to read on one screen>

**Fix:** <what actually resolved it>
**Lesson:** <what stays true after today>
EOF
```

Use `--type decision` instead when it records why one option was chosen over another; then use
the `**Decision:** / **Why:** / **Rejected:** / **Cost accepted:**` shape from
`note.template.md`.

Then fold it into the memory:

```bash
docker compose run --rm cognee-ingest
```

**Never use the MCP `remember` tool for this.** It writes straight into the index, and the next
ingest overwrites it with no warning that a note was lost. The memory is markdown; the index is
rebuilt from it.
