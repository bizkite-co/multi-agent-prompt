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

### Antigravity CLI (`agy`)

```bash
mkdir -p .agents/skills
cp -a skills/prompt .agents/skills/
```

### Other hosts (Cursor, Copilot, Grok, OpenCode)

Copy `skills/prompt` into that host's skills location. If the host doesn't
support skills at all, `@prompt.md` / `@.ma/prompt/current.md` (file mention)
works anywhere the host can see the file — including gitignored files, in
most hosts. Note that a file mention just reads the content; it doesn't run
`map pop`, so unlike `/prompt` it won't archive or clear the draft.
