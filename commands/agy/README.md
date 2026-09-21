# Antigravity CLI (`agy`)

agy has no client-side include or substitution for command content — a
slash-invoked skill's body is delivered to the model as instructions to
follow (verified: an `@file` reference in the body lands as literal text
the model tries to read). Its superpower is the hook system instead:
**`PreInvocation`** fires before every model call and can inject steps into
the trajectory — including a `userMessage`. So the handoff is done entirely
by the hook, with the skill as a bare trigger:

1. **The skill is frontmatter-only** (`prompt.md` in this directory — empty
   body). It exists so `/prompt` is a real, discoverable slash command;
   its body deliberately says nothing.
2. **The hook does everything** (`hosts/agy/prompt-pop.py`, wired in
   `~/.gemini/config/hooks.json`): when the newest user step is the
   literal `/prompt` request, it runs `map pop` locally (archive + clear,
   Python) and injects the popped prompt as the user's next message. The
   model receives the prompt as a genuine user message — recorded in the
   transcript as `USER_INPUT`, so the TUI renders it as the user's own
   message. No file, command, or file-operation instruction ever reaches
   the model; when nothing was composed, the injected message is the
   empty-handoff notice.

PreInvocation fires before *every* model call, so the hook guards against
double-firing: it only acts when the *last* user step is the `/prompt`
request, and remembers per-conversation which step it already handled (a
`~/.cache/multi-agent-prompt/agy-pop-state.json` ledger) — verified: a
multi-invocation turn archives exactly once. Without the ledger, the next
invocation would pop empty and inject the "nothing to hand off" notice
into the middle of the turn.

## Install

Global — agy discovers skills from `~/.gemini/config/skills/`, hooks from
`~/.gemini/config/hooks.json`:

```bash
mkdir -p ~/.gemini/config/skills/prompt ~/.gemini/config
ln -sfn "$(pwd)/commands/agy/prompt.md" ~/.gemini/config/skills/prompt/SKILL.md
```

The hook, in `~/.gemini/config/hooks.json`:

```json
{
  "map-prompt-pop": {
    "PreInvocation": [
      {
        "type": "command",
        "command": "python3 /path/to/repo/hosts/agy/prompt-pop.py",
        "timeout": 15
      }
    ]
  }
}
```

## Gotchas

- agy runs hooks from its config directory, so the hook resolves the
  workspace from the payload's `workspacePaths` (the session's mounted
  directories). `MAP_POP_CWD` overrides it — needed for headless `-p`
  testing, where an active TUI session can own the project context.
- Restart the TUI (or `/skills reload`) after installing — skills and
  hooks are discovered at startup.
- The model still sees the literal `/prompt` trigger text and agy's own
  invocation scaffolding around the (empty) skill body — that framing is
  agy-generated and fixed; no *our*-words are in it, and the prompt itself
  arrives as a plain user message.
- Workspace-level installs also work (`.agents/skills/` +
  `.agents/hooks.json` at a repo root) for per-project use; global is the
  default recommendation.

See [../README.md](../README.md) for the comparative view,
[../decisions.md](../decisions.md) for the cross-cutting rules, and
[../turn-end.md](../turn-end.md) for the turn-end hook surface.
