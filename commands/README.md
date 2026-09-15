# Multi-Agent Prompt host commands

The [skill](../skills/README.md) teaches the *LLM* to run `map pop` when the
user types `/prompt` — one Bash tool call plus the skill body in context,
every use. Hosts that can run shell commands while **building** the prompt —
before the LLM is ever involved — can do better: a command file whose
template injects `map pop`'s output directly, so the draft arrives as part of
the user's message with zero extra round trips, no skill body, and no
tool-call scaffolding. Archive-then-clear still happens — at send time, so a
crash right after handoff can never lose the draft.

Each host that supports this gets a directory here, named for the host.

## Template design

The model doesn't need to know *how* the draft got into the message — fetch
mechanics, archive paths, PATH fallbacks are noise it pays for on every use,
and each mechanic invites its own guard instruction ("don't run it again"),
which is more noise. What earns its tokens:

1. **The draft itself, first, clearly bounded** — it's the payload. Wrap it
   in `<draft>` tags, not a code fence: a fence collides with code blocks
   inside the draft.
2. **One framing line** — the tagged block is the user's actual next
   message; act on it as if typed directly.
3. **One guard line** — empty or error output means say so and wait; never
   invent a request.

## OpenCode

OpenCode discovers commands from `.opencode/commands/` (per project) and
`~/.config/opencode/commands/` (global). Its template syntax injects shell
output inline with ``!`cmd` `` — expanded at send time, in the project root,
before the model sees anything.

Project-local (travels with the repo):

```bash
mkdir -p .opencode/commands
ln -sfn ../../commands/opencode/prompt.md .opencode/commands/prompt.md
```

User-global:

```bash
mkdir -p ~/.config/opencode/commands
cp commands/opencode/prompt.md ~/.config/opencode/commands/
```

Restart the TUI after installing — commands are discovered at startup.

## Claude Code

Claude Code merged commands into skills: `.claude/commands/prompt.md` and
`.claude/skills/prompt/SKILL.md` both create `/prompt`, and both support
``!`cmd` `` dynamic context injection — the command runs at invocation and
its output is spliced in before the model sees the content.

Install as a personal skill, with SKILL.md symlinked back to the repo so
template edits propagate (or plain-`cp` it if you don't need that; edits
through the symlink may need a session restart, since live skill-reload
watches the directory rather than the link target):

```bash
mkdir -p ~/.claude/skills/prompt
ln -sfn "$(pwd)/commands/claude/prompt.md" ~/.claude/skills/prompt/SKILL.md
```

Gotchas, both learned the hard way:

- **A skill and a same-named command file collide — the skill wins.** Install
  one or the other, not both.
- **Never `cp` into `~/.claude/skills/prompt/SKILL.md` while
  `~/.claude/skills/prompt` is a directory symlink** (e.g. one pointing at
  this repo's `skills/prompt`) — the write goes through the link and
  clobbers its target. Check `ls -la ~/.claude/skills/` first.
- `~/.claude/skills/` is a compat source for Grok and OpenCode too. Give
  those hosts a native copy of the portable skill (`~/.grok/skills/prompt` —
  verified via `grok inspect` to win the bare `/prompt` name over the
  `~/.claude` source). OpenCode's primary path is its own command, above;
  its natural-language fallback will see the unexpanded ``!`map pop` ``
  marker and usually recovers by running it as a shell command.
- **Windows/PowerShell:** ``!`cmd` `` injection defaults to bash; on a
  Windows install without Git Bash, add `shell: powershell` to the
  frontmatter so it runs via Claude Code's PowerShell tool (on by default
  there). The ``!` `` marker is parsed by Claude Code, not the shell, so
  PowerShell's backtick-escape rules never touch the template. `map` itself
  is pure Python and installs on Windows (`uv tool install
  multi-agent-prompt`); OpenCode on Windows is WSL-first — inside WSL
  everything is Linux-side and this template works unchanged.

Keep the skill installed alongside it: the command covers the typed
`/prompt` shortcut with zero overhead, while the skill still covers
natural-language asks like "read my prompt file" and hosts without the
command file.
