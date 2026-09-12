# Multi-Agent Prompt portable skill

One skill (`prompt`) that teaches a host to read `.map/prompt.md` — the
scratch file `map` edits — and treat its content as the user's next message
when they type `/prompt`.

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
support skills at all, `@prompt.md` / `@.map/prompt.md` (file mention) works
anywhere the host can see the file — including gitignored files, in most
hosts.
