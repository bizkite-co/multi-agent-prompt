# Multi-Agent Prompt host commands

`/prompt` hands a draft to the chat. The design rule: **the host, not the
model, does the work.** Reading the draft, splicing it into the outgoing
message, archiving, and clearing the scratch file all happen locally,
before the model sees anything — the model only ever receives the draft
content (plus one framing line and one guard line). No instructions about
files, no tool calls, no "run this command" noise for the model to burn
tokens on.

Each host gets a directory here, named for the host, using whatever
local-expansion primitives that host actually has.

## Template design

The outgoing message should be **indistinguishable from the user having
typed the draft into the chat box**: the draft, verbatim, and nothing else.
No `<draft>` tags, no framing line ("act on this as if typed"), no guard
line ("if empty, say so") — none of it earns tokens, and every such line is
one more thing a model can misread or refuse (a "run this command"
instruction in a leaked template is exactly how agents came to reject
/prompt handoffs as misdirected drafts).

The one case that needs words — nothing was composed — generates them
**locally in the tool instead**: `map pop` (and `map pop --stage`) emits
`EMPTY_HANDOFF_NOTICE` as its entire output, so even a bare template yields
a clear message the model can relay to the user (the trailing "say so and
wait" is load-bearing: without it some models treat the notice as a problem
to investigate — reading files, chasing the tool — instead of a dead end
to report).

## OpenCode

OpenCode discovers commands from `.opencode/commands/` (per project) and
`~/.config/opencode/commands/` (global). Its ``!`cmd` `` template syntax
executes the command **during prompt construction** — in the project root,
before the model sees anything — and splices only its *output* into the
prompt (verified: no command string or tool-call scaffolding reaches the
model). The whole template is the substitution, so the message *is* the
draft:

```markdown
!`map pop`
```

`map pop` reads, archives, and clears in one local Python step (emitting
the empty-handoff notice when nothing was composed), so this single
substitution is the entire handoff.

Project-local (travels with the repo):

```bash
mkdir -p .opencode/commands
ln -sfn ../../commands/opencode/prompt.md .opencode/commands/prompt.md
```

User-global:

```bash
mkdir -p ~/.config/opencode/commands
ln -sfn "$(pwd)/commands/opencode/prompt.md ~/.config/opencode/commands/prompt.md"
```

Restart the TUI after installing — commands are discovered at startup.

## Claude Code

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
   the just-popped draft (or the empty-handoff notice) to `handoff.md` —
   the file the include then reads. Ordering matters and is verified: the
   hook runs *before* the include resolves, which is why the include
   targets the staged copy rather than the scratch file. Silent by design —
   no stdout, every failure swallowed (it's housekeeping, never worth
   blocking a conversation over).

Install the command as a personal slash command (symlinked back to the repo
so edits propagate):

```bash
mkdir -p ~/.claude/commands
ln -sfn "$(pwd)/commands/claude/prompt.md" ~/.claude/commands/prompt.md
```

And the hook (settings entry included below):

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

Gotchas, learned the hard way:

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

## Antigravity CLI (`agy`)

agy has no client-side include or substitution for command content — a
slash-invoked skill's body is delivered to the model as instructions to
follow (verified: an `@file` reference in the body lands as literal text
the model tries to read). Its superpower is the hook system instead:
**`PreInvocation`** fires before every model call and can inject steps into
the trajectory — including a `userMessage`. So the handoff is done entirely
by the hook, with the skill as a bare trigger:

1. **The skill is frontmatter-only** (`commands/agy/prompt.md` — empty
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
multi-invocation turn archives exactly once.

Install (global — agy discovers skills from `~/.gemini/config/skills/`,
hooks from `~/.gemini/config/hooks.json`):

```bash
mkdir -p ~/.gemini/config/skills/prompt ~/.gemini/config
ln -sfn "$(pwd)/commands/agy/prompt.md" ~/.gemini/config/skills/prompt/SKILL.md
# and the hooks.json entry from below
```

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

Gotchas:

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

## What the model actually sees

- **OpenCode**: the draft, verbatim — nothing else.
- **Claude Code**: the draft verbatim; the `@`-include leaves a file-path
  mention as attachment metadata (the model can see *where* content came
  from, but is never asked to *do* anything with it).
- **agy**: the draft as a genuine injected user message — zero file/path
  knowledge, not even an attachment mention. The unavoidable residue is
  agy's own framing for any slash command: the literal `/prompt` trigger
  text plus its "explicitly invoked the (prompt) skill" scaffolding around
  the deliberately-empty skill body.

A handoff is indistinguishable from the user having typed the prompt into
the chat box; when nothing was composed, the entire message is the
locally-generated empty-handoff notice.
