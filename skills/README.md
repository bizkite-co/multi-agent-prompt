# Multi-Agent Prompt portable skill

One skill (`prompt`): the **read-only fallback** for hosts that can't run
local expansion at all. It teaches a host only to *read*
`.ma/prompt/current.md` and treat the content as the user's next message —
and explicitly forbids the agent from running `map pop`, archiving, or
otherwise touching the file.

The handoff itself is supposed to be invisible to the model: hosts with
local expansion primitives do the read-splice-archive-clear entirely
client-side (see [`commands/README.md`](../commands/README.md) — opencode
``!` `` substitution, Claude Code `@`-include + hook, Grok's staged
model-side read). This skill exists
only for hosts with no such machinery, and for natural-language asks like
"read my prompt file". Where a `/prompt` command file is installed, prefer
it — the skill never needs to run.

## Manual install

Skills are a plain directory. Copy or symlink it into the host's skills path.

### Antigravity CLI (`agy`) — use the command + hook instead

agy's `/prompt` is built from a frontmatter-only skill plus a
`PreInvocation` hook that pops and injects the prompt as a user message —
see [`commands/agy/README.md`](../commands/agy/README.md).
Don't install this fallback skill for agy: a same-named skill would win
the `/prompt` name and its instruction body is exactly the model-driven
behavior the command + hook design avoids. (The fallback skill remains
for hosts with no hook or expansion primitives at all.)

### OpenCode

OpenCode discovers skills from `.opencode/skills/` (project) or
`~/.config/opencode/skills/` (global), including Claude-compatible paths.
For typed `/prompt`, the native command is strictly better (local splice,
zero model involvement) — see
[`commands/README.md`](../commands/README.md). Install the skill only for
natural-language asks on hosts without the command.

### Grok — use the command + hook instead

Grok's `/prompt` is built from a flat command file plus a `UserPromptSubmit`
hook that pops host-side and stages the result for the model to read — see
[`commands/grok/README.md`](../commands/grok/README.md). Don't install this
fallback skill for Grok: a same-named skill would win the `/prompt` name,
and its instruction body ("read the file") is exactly the model-driven
behavior the staged-read design exists to constrain.

### Other hosts (Cursor, Copilot)

Copy `skills/prompt` into that host's skills location. If the host doesn't
support skills at all, `@prompt.md` / `@.ma/prompt/current.md` (file
mention) works anywhere the host can see the file — including gitignored
files, in most hosts. A file mention only reads the content; it doesn't
archive or clear the draft.

### Claude Code — do NOT install this skill

A same-named skill beats the slash command, and a skill's body goes to the
model as instructions — which reintroduces exactly the "agent runs file
operations" behavior the command+hook architecture exists to avoid. Claude
Code should have only the command + hook from
[`commands/claude/README.md`](../commands/claude/README.md).
