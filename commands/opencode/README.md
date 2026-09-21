# OpenCode

OpenCode discovers commands from `.opencode/commands/` (per project) and
`~/.config/opencode/commands/` (global). Its ``!`cmd` `` template syntax
executes the command **during prompt construction** — in the project root,
before the model sees anything — and splices only its *output* into the
prompt (verified: no command string or tool-call scaffolding reaches the
model). The whole template is the substitution, so the message *is* the
prompt:

```markdown
!`map pop`
```

`map pop` reads, archives, and clears in one local Python step (emitting
the empty-handoff notice when nothing was composed), so this single
substitution is the entire handoff. No hook is needed — one primitive does
inject and pop together, which is why OpenCode is the reference design.

## Install

Project-local (travels with the repo):

```bash
mkdir -p .opencode/commands
ln -sfn ../../commands/opencode/prompt.md .opencode/commands/prompt.md
```

User-global:

```bash
mkdir -p ~/.config/opencode/commands
ln -sfn "$(pwd)/commands/opencode/prompt.md" ~/.config/opencode/commands/prompt.md
```

Restart the TUI after installing — commands are discovered at startup.

See [../README.md](../README.md) for the comparative view and
[../decisions.md](../decisions.md) for the cross-cutting rules.
