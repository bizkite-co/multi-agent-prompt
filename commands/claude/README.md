# Claude Code

Claude Code's ``!` `` injection annotates the model-visible message with a
`● Bash(cmd 2>&1)` line, so the opencode one-liner isn't clean here.
Instead `/prompt` is built from two local primitives:

1. **The command file splices file content with an `@`-include:**
   ```markdown
   @.ma/prompt/handoff.md
   ```
   Claude resolves `@`-references locally at expansion — the model sees the
   file's contents, not a command.
2. **A `UserPromptExpansion` hook pops first**: `hosts/claude/prompt-pop.py`
   (wired in `~/.claude/settings.json`) sees `command_name == "prompt"` and
   runs `map pop --stage`, which archives + clears `current.md` and writes
   the just-popped prompt (or the empty-handoff notice) to `handoff.md` —
   the file the include then reads. Ordering matters and is verified: the
   hook runs *before* the include resolves, which is why the include
   targets the staged copy rather than the scratch file. Silent by design —
   no stdout, every failure swallowed (it's housekeeping, never worth
   blocking a conversation over).

## Install

The command, as a personal slash command (symlinked back to the repo so
edits propagate):

```bash
mkdir -p ~/.claude/commands
ln -sfn "$(pwd)/commands/claude/prompt.md" ~/.claude/commands/prompt.md
```

The hook, in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptExpansion": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/repo/hosts/claude/prompt-pop.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

## Gotchas, learned the hard way

- **A skill and a same-named command collide — never install
  `~/.claude/skills/prompt/`.** A skill's body goes to the model as
  instructions ("run `map pop`..."), which is exactly the leak this
  architecture exists to prevent; the leftover skill install was the source
  of agents refusing /prompt handoffs as "misdirected drafts". The
  read-only fallback skill in `skills/prompt/` is for *other* hosts and
  natural-language asks only — never install it as Claude Code's /prompt.
- **`map` must support `--stage`** (v0.1.4+); the hook swallows the error on
  older installs, which surfaces as `/prompt` reading a stale or empty
  handoff. `map self-up` fixes it.
- **Both paths resolve from the directory Claude was launched in** — launch
  agents at the repo root, like the opencode command (which runs in the
  project root).
- The hook fires on any `/prompt`-named slash command expansion
  (`command_name` match), from any source — that's the intent.

## Documentation sources

- Slash commands (`!` execution, `@` file references, personal vs project):
  <https://docs.anthropic.com/en/docs/claude-code/slash-commands>
- Hooks reference (events, JSON I/O, exit codes):
  <https://docs.anthropic.com/en/docs/claude-code/hooks>

See [../README.md](../README.md) for the comparative view,
[../decisions.md](../decisions.md) for the cross-cutting rules, and
[../turn-end.md](../turn-end.md) for the turn-end hook surface.
