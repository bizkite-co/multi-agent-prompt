# Multi-Agent Prompt host commands

`/prompt` hands a draft to the chat. The design rule: **the host, not the
model, does the work.** Reading the draft, splicing it into the outgoing
message, archiving, and clearing the scratch file all happen locally,
while the prompt is being built — the model only ever receives the prompt
**verbatim** (or, when nothing was composed, a single locally-generated
notice). No instructions about files, no tool calls, no "run this command"
noise for the model to burn tokens on.

Each host gets a directory here — its `prompt.md` template plus a
`README.md` with the mechanics and install steps — using whatever
local-expansion primitives that host actually has:

| Host | Trigger | Injection primitive | Pop mechanism | Model sees | Why this design |
|---|---|---|---|---|---|
| [OpenCode](./opencode/README.md) | command file | ``!`map pop` `` — host executes at prompt-build, splices **output only** (verified: no command string or tool scaffolding reaches the model) | the substitution *is* the pop | the prompt, verbatim | one primitive does inject + pop in one local step — no hook needed; the reference design |
| [Claude Code](./claude/README.md) | command file | `@.ma/prompt/handoff.md` include — content-only | `UserPromptExpansion` hook runs `map pop --stage` first | the prompt verbatim; path as attachment metadata | Claude's ``!` `` annotates the model-visible message with `● Bash(...)`; `@` is clean but read-only, so the hook stages — ordering verified: hook fires *before* the include resolves |
| [agy](./agy/README.md) | frontmatter-only skill (empty body — trigger only) | none exists — `PreInvocation` hook injects a `userMessage` step | same hook runs `map pop`, then injects | the prompt as a **genuine user message** (recorded as `USER_INPUT`; the TUI renders it as the user's own) | verified: `@file` in a skill body lands as literal text the model tries to read — agy has no include/substitution, but its hooks can inject trajectory steps |

Hosts with no local-expansion primitives at all (skills-only CLIs) get the
portable [read-only fallback skill](../skills/README.md) instead — the
model *reads* the file but is never allowed to modify, archive, or run
anything against it.

## Where to read what

- **Per-host mechanics and install steps**: each host's `README.md`
  (linked above).
- **Cross-cutting design decisions** — zero-verbiage rule, capture safety,
  exactly-once, failure-swallowing, collision rules, restart semantics,
  version floor, and exactly what the model sees:
  [decisions.md](./decisions.md).
- **Turn-end hooks** — the output side of the agent loop (agent done /
  question / report: `Stop`, `StopFailure`, `Notification`,
  `session.idle`, force-continue patterns), documented surface for future
  work: [turn-end.md](./turn-end.md).
