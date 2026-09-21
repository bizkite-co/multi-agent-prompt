# Grok (xAI Build)

Grok has **no host-side content splice** — unlike opencode (``!`cmd` ``
substitution) or Claude Code (`@`-includes). That was verified empirically,
not assumed:

| Primitive | What we tested | Result |
|---|---|---|
| `` !`cmd` `` in a command body | `/splice` → ``!`printf "SPLICE-TOKEN-CONFIRMED"` `` | **Not executed host-side.** The model saw the literal command text, decided to "run the splice command", and executed it itself via a `run_terminal_command` tool call. A body containing ``!`map pop` `` would leak the operation to the model. |
| `@file` in a command body | `/include` → `@inc.txt` | **Not included host-side.** The model saw the literal `@inc.txt`, then called `read_file` itself (twice — even reading the command's own `.md` source to understand the directive). A `@.ma/prompt/handoff.md` splice target would be a model-side read, not a splice. |
| `UserPromptExpansion` | hooks list | **Does not exist.** Grok's hook events are `SessionStart`/`SessionEnd`, `UserPromptSubmit`, `PreToolUse`/`PostToolUse`/`PostToolUseFailure`/`PermissionDenied`, `Stop`/`StopFailure`/`StopCancelled`, `Notification`, `SubagentStart`/`SubagentStop`, `PreCompact`/`PostCompact`. |
| trajectory injection | docs + bundled reference | **Does not exist.** No `injectSteps`; a `UserPromptSubmit` hook's stdout is discarded on allow (it can only *block*, which discards the prompt). |

Command bodies are delivered to the model as **instructions to follow** (Grok
treats them as skill bodies — verified: a bare frontmatter-less command body
was read back by the model as "the /plain skill which says to respond with
only the token...").

So Grok's handoff is a **staged model-side read** — the strongest design the
platform allows:

1. **The command** (`prompt.md` in this directory) is a short read-only
   instruction: read `.ma/prompt/handoff.md`; treat its content as the
   user's message; if it holds the "no prompt to hand off" notice, relay it
   and wait; never modify/archive/delete/run anything and never read the
   scratch file.
2. **The host does the pop at submit time**: a `UserPromptSubmit` hook
   (`hosts/grok/prompt-pop.py`), which fires *before the model is invoked*
   and receives the **raw** prompt text (`"prompt": "/prompt"`), runs
   `map pop --stage` in the workspace root — archiving + clearing
   `current.md` and writing the popped draft (or the empty-handoff notice)
   to `handoff.md`. Exactly-once by construction: one submit, one pop.

The model's only file action is a read of the staged copy; the pop itself is
host-side housekeeping that happens before anything reaches the model. This
is the same role the read-only fallback skill plays for skills-only hosts,
upgraded so the pop is exactly-once and local.

Verified end-to-end headlessly (fresh draft → `/prompt`): the staged file is
written, `current.md` cleared, the draft archived, and the model reads only
the staged copy and answers with the draft's content; an empty draft stages
the notice, which the model relays verbatim and stops. Both paths archive
exactly once.

## Install (global)

Grok scans `~/.grok/commands/*.md` as user slash commands and
`~/.grok/hooks/*.json` as global (always-trusted) hooks:

```bash
mkdir -p ~/.grok/commands ~/.grok/hooks
ln -sfn "$(pwd)/commands/grok/prompt.md" ~/.grok/commands/prompt.md
```

```bash
cat > ~/.grok/hooks/prompt.json <<'EOF'
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "python3 /path/to/repo/hosts/grok/prompt-pop.py", "timeout": 15 }
        ]
      }
    ]
  }
}
EOF
```

Restart Grok (or run `/hooks` to reload). Verify with `grok inspect` —
`/prompt` should appear in the Skills section with source `user`, and the
hook under the Hooks section. You can test it end-to-end headlessly:

```bash
grok -p "/prompt" --cwd /repo/root --output-format streaming-messages-json
```

Workspace-root paths: the hook uses the payload's `workspaceRoot` (the
discovered project root) so `.ma/prompt/` resolves no matter which
subdirectory the session started in.

## Gotchas, verified the hard way

- **Claude-import collision** — *resolved, verified*: Grok scans
  `~/.claude/commands/` by default, so without a native install it imports
  the Claude Code `/prompt` (body `@.ma/prompt/handoff.md` — a model-side
  read instruction in Grok, not a splice; the model obediently read that
  `.md` source and then the file). A native install **wins the bare name**:
  project `.grok/commands/prompt.md` (highest) and user
  `~/.grok/commands/prompt.md` both outrank the imported Claude command —
  verified here (source `user`, vendor `none`, single `/prompt`). Check
  `grok inspect` to confirm bare `/prompt` points at the native file; if a
  name ever resolves elsewhere, use the qualified form or set the
  `[compat.claude]` cell to stop scanning that vendor.
- **`--stage` needs `map` ≥ 0.1.4.** On older installs the hook fails
  silently (by design) and `/prompt` sees a stale or missing handoff.
  `map self-up`.
- **The model sees the command body and the read.** Unlike opencode/agy
  (prompt verbatim, zero residue) and Claude (verbatim + a path mention),
  Grok's model sees our short instruction text, the literal `/prompt` it
  typed, and its own `read_file` of the staged copy. Keep the body to a
  read-only contract — never mention `map`, `pop`, archive paths, or
  `current.md` beyond the "do not read it" line.
- **`disable-model-invocation: true`** keeps the model from auto-invoking
  /prompt by itself; only the user's slash command runs it.
- **Hooks always fail open.** A crash or timeout just means the handoff file
  isn't staged; the worst case is /prompt answering "nothing to act on".
- **Restart semantics** apply as with every host: commands and hooks load at
  session start (`/hooks` reloads hooks at runtime; command changes need a
  session restart).

## Documentation sources

- Local guide (bundled with the CLI): `~/.grok/docs/user-guide/` —
  `04-slash-commands.md`, `08-skills.md`, `09-plugins.md`, `10-hooks.md`,
  `14-headless-mode.md`
- Online: <https://docs.x.ai/build/overview> · Hooks
  <https://docs.x.ai/build/features/hooks> · Skills & plugins
  <https://docs.x.ai/build/features/skills-plugins-marketplaces> · Modes
  and commands <https://docs.x.ai/build/modes-and-commands> · Headless
  <https://docs.x.ai/build/cli/headless-scripting>

See [../README.md](../README.md) for the comparative view,
[../decisions.md](../decisions.md) for the cross-cutting rules, and
[../turn-end.md](../turn-end.md) for the turn-end hook surface.