# Design decisions (cross-cutting)

Why every host's `/prompt` is built the way it is. Per-host mechanics live
in each host's README ([opencode](./opencode/README.md),
[claude](./claude/README.md), [agy](./agy/README.md),
[grok](./grok/README.md)); the comparative table is in the [index](./README.md).
Everything below applies to all of them.

## The message is the prompt, verbatim

The outgoing message should be **indistinguishable from the user having
typed the prompt into the chat box**: the prompt, verbatim, and nothing
else. No `<draft>` tags, no framing line ("act on this as if typed"), no
guard line ("if empty, say so") — none of it earns tokens, and every such
line is one more thing a model can misread or refuse (a "run this command"
instruction in a leaked template is exactly how agents came to reject
/prompt handoffs as misdirected drafts).

The one case that needs words — nothing was composed — generates them
**locally in the tool instead**: `map pop` (and `map pop --stage`) emits
`EMPTY_HANDOFF_NOTICE` as its entire output, so even a bare template yields
a clear message the model can relay to the user. The trailing "say so and
wait" is load-bearing: without it some models treat the notice as a problem
to investigate — reading files, chasing the tool source — instead of a
dead end to report (observed with opencode's default model).

**Grok is the exception to "verbatim", and the rule holds as tightly as
that platform allows.** Grok has no splice, substitution, or injection
primitive, so the content can reach the model only through a read. The
command body is a deliberately *minimal read-only contract* — "read the
file, treat it as the message, and never modify/archive/delete/run
anything" — and names no tools (`map`, `pop`, archive paths) and points at
exactly one path besides the staged file (the scratch file, only to say
"do not read it"). Models have followed it faithfully in testing; the
principle is the same one Claude's skill-collision risk
illustrates — every word in the body is a word a model has to not misuse.

## Capture safety — a pop may never lose the prompt

Archiving and clearing happen only once the content is guaranteed to be in
the outgoing message, and each host gets there differently:

- **OpenCode**: the substitution's output *is* the message — pop and splice
  are a single operation, so there is no window to lose anything.
- **Claude Code**: `UserPromptExpansion` fires *before* the `@`-include
  resolves (verified empirically — a hook-side pop made the include read an
  empty file), so the hook pops to a **staged** `handoff.md` that the
  include then reads. The scratch file is already cleared; the stage
  carries the content.
- **agy**: the hook pops and injects in one call — the popped text becomes
  a `userMessage` trajectory step before the model is invoked.
- **Grok**: `UserPromptSubmit` fires *before* the model is invoked and runs
  `map pop --stage`, staging the popped text (or the notice) where the
  command body reads it — the scratch file is already cleared and archived
  before the model is ever called.

## Exactly-once

- **OpenCode**: one substitution per send, by construction.
- **Claude Code**: one `UserPromptExpansion` per command expansion, by
  construction.
- **Grok**: one `UserPromptSubmit` per submit, by construction — the hook
  fires once per typed `/prompt`, so no ledger is needed (unlike agy);
  verified: a submit both stages and archives exactly once.
- **agy**: `PreInvocation` fires before *every* model call, so the hook
  needs guards: it acts only when the *last* user step is the literal
  `/prompt` request, and keeps a per-conversation handled-step ledger
  (`~/.cache/multi-agent-prompt/agy-pop-state.json`). Verified: a
  multi-invocation turn archives exactly once.

## Failure-swallowing

Hooks print nothing (Claude, Grok) or `{}` (agy) and exit 0, swallowing
every error: this is housekeeping and must never block or stall a
conversation. Worst case without a hook: the scratch file isn't reset for
the next `/prompt` — Grok's model sees the command body's "nothing to act
on // say so and wait" fallback instead of a handoff. Claude's hook is
additionally silent because a `UserPromptSubmit`-family hook's stdout gets
injected as extra context — exactly the noise this design refuses to emit.
(Grok can't inject anything, so its silence is about not stalling the
submit, and keeping the hook's working directory unambiguous.)

## Collision rules

- **Claude Code**: never install a *skill* named `prompt` — a same-named
  skill wins over the slash command, and a skill's body goes to the model
  as instructions ("run `map pop`..."). A leftover skill install was the
  source of agents rejecting handoffs as "misdirected drafts".
- **agy**: the skill *is* the command — skills auto-convert to slash
  commands — so it is frontmatter-only, empty body by design.
- **Grok**: native `.grok/commands/prompt.md` (project, then user) wins the
  bare `/prompt` name over Grok's auto-import of the Claude Code skill
  family — verified on this machine, no compat config needed. Two rules:
  never install a Grok *skill* named `prompt` (same-named-skill mechanics
  as Claude — the body goes to the model as instructions), and keep the
  command body to the read-only contract.
- **OpenCode**: command only. The portable read-only fallback skill
  ([../skills/README.md](../skills/README.md)) is exclusively for hosts
  with no local-expansion primitives at all.

## Restart semantics

TUIs cache command templates, skills, and hook configs at startup:
opencode commands, Claude Code commands, agy skills and hooks, Grok's
commands and hooks (agy offers `/skills reload`, Grok a `/hooks`
extensions modal, without a restart). After editing a template, restart
running sessions — a stale cached template once served the old framing
text to a live session, which is how the pre-purge wording survived the
purge.

## Version floor

Claude Code's and Grok's hooks need `map` ≥ 0.1.4 (`--stage`). On older
installs the hook fails silently (by design) and the symptom is `/prompt`
reading a stale or empty handoff — `map self-up` fixes it. `map hosts`
(the one-command installer) ships in ≥ 0.1.8, so provisioning requires a
fresh install too.

## CLI provisioner (`map hosts`)

`map hosts install` is the supported install path; the manual steps in
each host README are the equivalent by hand. Its policy mirrors the
"never lose, never clobber" rules above:

- **Platform-local roots.** Each host's config root resolves from the
  platform the *running* `map` is on — Windows: `%USERPROFILE%`/
  `%APPDATA%`; elsewhere: `~` / `$XDG_CONFIG_HOME`. Run it in every shell
  you use: PowerShell wires the native-Windows hosts (the fix for the
  WSL-only-install problem where Windows agy had no `/prompt`), WSL wires
  the WSL ones.
- **Idempotent and additive.** Re-running is a no-op. Our files are either
  created, left alone when identical, or skipped when they differ —
  replaced only with `--force`. `settings.json` / `hooks.json` merges add
  only our own hook entry (matched by its exact command string) and never
  reformat or remove anything else; unreadable JSON is reported and left
  untouched.
- **Nothing deleted that we didn't install.** `uninstall` removes only the
  files we wrote and our own hook entry — a user-modified file is skipped
  unless `--force`. Empty directories created by the installer are pruned
  back up to the config root.
- **`--dry-run` / `--host`.** Preview exactly what would change, or scope
  to a single host.

## What the model actually sees

- **OpenCode**: the prompt, verbatim — nothing else.
- **Claude Code**: the prompt verbatim; the `@`-include leaves a file-path
  mention as attachment metadata (the model can see *where* content came
  from, but is never asked to *do* anything with it).
- **agy**: the prompt as a genuine injected user message — zero file/path
  knowledge, not even an attachment mention. The unavoidable residue is
  agy's own framing for any slash command: the literal `/prompt` trigger
  text plus its "explicitly invoked the (prompt) skill" scaffolding around
  the deliberately-empty skill body.
- **Grok**: the prompt, **plus** the literal `/prompt` trigger, the short
  read-only command body, and the model's own `read_file` of the staged
  `.ma/prompt/handoff.md`. This is the most residue of any host — the
  platform offers no way around it (no splice, no injection, no
  substitution) — so the body is engineered to be exactly a read contract
  and nothing else.

A handoff is indistinguishable from the user having typed the prompt into
the chat box; when nothing was composed, the entire message is the
locally-generated empty-handoff notice. (Grok is the one host where the
handoff is *visible* as a machine step — the trade-off for the strongest
mechanism its hooks allow.)
