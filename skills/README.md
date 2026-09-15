# Multi-Agent Prompt portable skill

One skill (`prompt`) that teaches a host to read the user's draft from
`.ma/prompt/current.md` — the scratch file `map` edits — treat it as their
next message, and clear it for the next one (via `map pop`, which archives
before it clears) when they type `/prompt`.

## Manual install

Skills are a plain directory. Copy or symlink it into the host's skills path.

### Claude Code

Project-local (recommended):

```bash
mkdir -p .claude/skills
ln -sfn ../../skills/prompt .claude/skills/prompt
```

User-global:

```bash
mkdir -p ~/.claude/skills
cp -a skills/prompt ~/.claude/skills/
```

For Claude Code specifically, prefer the zero-overhead variant instead: its
skills support ``!`cmd` `` dynamic context injection, so
[`commands/claude/prompt.md`](../commands/README.md#claude-code) splices the
draft in before the model sees anything. This portable skill remains the
fallback for every host without injection.

### Antigravity CLI (`agy`)

```bash
mkdir -p .agents/skills
cp -a skills/prompt .agents/skills/
```

### OpenCode

OpenCode discovers skills from `.opencode/skills/` (project) or
`~/.config/opencode/skills/` (global), including the Claude-compatible paths
above. But for typed `/prompt`, prefer the native command instead — the
harness itself runs `map pop` at send time and splices the draft into the
message, zero LLM round trips. See
[`commands/README.md`](../commands/README.md); keep the skill installed
alongside it for natural-language asks.

### Other hosts (Cursor, Copilot, Grok)

Copy `skills/prompt` into that host's skills location. If the host doesn't
support skills at all, `@prompt.md` / `@.ma/prompt/current.md` (file mention)
works anywhere the host can see the file — including gitignored files, in
most hosts. Note that a file mention just reads the content; it doesn't run
`map pop`, so unlike `/prompt` it won't archive or clear the draft.
