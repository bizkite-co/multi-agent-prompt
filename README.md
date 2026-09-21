# Multi-Agent Prompt ✍️

A crash-proof, autosaving prompt editor for AI coding agent CLIs.

Chat text boxes lose long, carefully-composed prompts to a single wrong
keystroke, and give you almost no editing power while you write. `multi-agent-prompt`
moves composition out of the chat box entirely: write in a real Neovim, in a
split pane next to your agent session, autosaved to disk every couple of
seconds so a crash or a fat-fingered shortcut can never cost you more than a
moment of typing. When you're ready, hand it to the agent with `/prompt` —
which reads it, archives it, and clears the file in one step, so there's no
separate "now go clear it" to remember.

---

## Install

```bash
pip install multi-agent-prompt
# or
uv tool install multi-agent-prompt
```

Requires [Neovim](https://neovim.io/) — the autosave hook is Lua, so plain
Vim isn't supported.

## Usage

Open a split pane next to your agent CLI (Windows Terminal: `Alt+Shift+-`;
tmux: `<prefix> "`) in the **same working directory**, then run:

```bash
map
```

This opens `.ma/prompt/current.md` — resolved to the current project's git
root, so every pane in the same repo shares one scratch file — in your actual
`nvim`, your actual `init.lua`, your actual keymaps and plugins. No config
import step, no reimplemented Vim subset: it's just Neovim. You land in
**insert mode already**, cursor at the end of the buffer, so there's no `i`
to press before you start typing (`--no-insert` if you'd rather open in
normal mode). A buffer-local autocmd (scoped only to this one buffer — it
never touches how you edit anything else) autosaves ~2 seconds after you stop
typing, and immediately when you switch away from the pane
(`FocusLost`/`BufLeave`), so the save always beats you to the chat window.

When you're done, switch back to the agent pane and either:

- Type `/prompt` (if the agent's install includes the command — see below).
  The **host**, not the model, reads the draft, splices it into your
  message, archives it, and clears the file — the model only ever sees the
  draft content, never a command or a file-operation instruction, or
- Reference `@prompt.md` / `@.ma/prompt/current.md` directly, if your agent
  supports file mentions and can see gitignored files — this is a plain
  read (by the model), so unlike `/prompt` it doesn't archive or clear
  anything.

Pasting a long CLI transcript or diff in? Anything **6 lines or more**
(bracketed paste, `"+p`, `"*p` — any paste source) auto-folds, closed, so it
doesn't bury the rest of what you're writing — `za`/`zo`/`zc` (standard Vim)
toggle it open.

The session is also styled like a prompt editor (again, only for the
throwaway nvim `map` launches, never your own): line numbers are off and a
`> ` prompt marker follows your cursor in the gutter, a statusline footer
lists whichever keymaps are active this session, and the background is
forced true black (`#000000`) so it melts into a black terminal while your
colorscheme's foregrounds survive. All of it degrades to a no-op on an
older Neovim instead of blocking the session.

Also want to browse past drafts without leaving the editor? A buffer-local
keymap — `<leader>ph` by default — lists archived drafts (newest first) in a
split; `<CR>` opens one, read-only. Forgot what any of this is bound to?
Press `g?` — it shows exactly the keymaps active for *this* session
(respecting any `--clear-key`/`--history-key` overrides, and omitting
whichever ones you disabled):

```
map            # open the scratch file (same as `map edit`)
map where      # print the resolved file path
map show       # print its current content to stdout (does not clear it)
map pop        # print it, archive it, and clear it — what /prompt uses
map clear      # archive the current draft, then empty it, without printing it
map --clean    # skip your init.lua entirely (-u NONE) for faster startup
```

```
map edit --clear-key '<F5>'      # rebind the in-editor clear keymap
map edit --no-clear-key          # don't register it at all
map edit --history-key '<F6>'    # rebind the in-editor history-browse keymap
map edit --no-history-key        # don't register it at all
map edit --help-key '<F1>'       # rebind the in-editor g? cheatsheet keymap
map edit --no-help-key           # don't register it at all
map edit --fold-threshold 3      # auto-fold pastes of 3+ lines instead of 6
map edit --no-fold-paste         # don't auto-fold pastes at all
map edit --no-insert             # open in normal mode instead of insert mode
map edit --no-prompt-gutter      # keep your line numbers/gutter (no '> ' marker)
map edit --no-footer             # don't add the keymap footer to the statusline
map edit --no-trueblack          # keep your colorscheme's own background
map clear --keep 20              # override how many archived drafts to retain
map clear --no-archive           # discard instead of archiving (e.g. it had a secret in it)
```

`map pop` accepts the same `--keep`/`--no-archive` as `map clear`.

### The archive

`map pop`/`map clear` — from the CLI or the in-editor keymap, which shells
out to `map clear` — never actually discard a non-empty draft; they move it
to `.ma/prompt/archive/<timestamp>-<seq>.md` first, then prune that archive
down to the most recent entries. Pruning is by **count**, not age (`--keep` /
`MAP_ARCHIVE_KEEP` env var, default **10**) — simpler to reason about than a
retention window, and it doesn't depend on the clock. Use `--no-archive` for
the one case that shouldn't be kept anywhere: you pasted a secret and want it
actually gone.

## Performance

A `map` session opens your *entire* Neovim config, which is exactly the
point — but if that config is large, startup isn't free. Two things worth
knowing, from actually measuring it (not guessing):

- **It's not a one-time thing.** Whatever makes your first `map` slow will
  make every subsequent one about equally slow, unless something changes
  (lazy.nvim itself finishes installing/compiling once; LSP servers and
  large plugin trees generally don't get meaningfully faster after that).
- **On WSL specifically, check for `vim.opt.clipboard = 'unnamedplus'` (or
  similar) in your own init.lua.** Setting that option makes Neovim probe for
  a clipboard provider immediately, and on WSL that probe walks every `PATH`
  entry checking `executable()` — including everything under `/mnt/c/...`,
  which is slow cross-filesystem interop. Measured on this project's own dev
  machine: ~900ms startup with that line in play, ~160ms with the Windows
  `PATH` entries stripped, ~4ms with `-u NONE`. That's not multi-agent-prompt
  overhead; it's one line in a personal init.lua interacting badly with WSL,
  and fixing it (or guarding it — see `MAP_SESSION` below) speeds up *every*
  Neovim session, not just `map`.
- **`map --clean` (`-u NONE`)** sidesteps all of it by skipping your config
  entirely — the built-in fast path when you don't need your plugins for a
  quick edit.
- **`MAP_SESSION=1`** is set in the environment of every nvim `map` launches.
  Nothing in this package reads it — it's there so you can guard an
  expensive line in your *own* init.lua behind
  `if not vim.env.MAP_SESSION then ... end`, if you want full-config speed
  back without giving up faster `map` startup. That's your config to edit,
  not something this tool does for you. This isn't just for the clipboard
  line above — a scratch prompt buffer has no use for a file-tree sidebar or
  git tooling either, and with [lazy.nvim](https://github.com/folke/lazy.nvim)
  you can skip those specific plugins the same way, with `cond` on the spec:

  ```lua
  return {
    'nvim-neo-tree/neo-tree.nvim',
    cond = not vim.env.MAP_SESSION,
    -- ...
  }
  ```

  Confirmed on this project's own dev config: with `neo-tree.nvim` and
  `gitsigns.nvim` guarded this way, `<leader>e` (NeoTree's toggle) becomes a
  no-op in a `map` session, and their entire module trees (dozens of
  individual `require()` calls each) simply don't load — real startup
  savings, not just fewer keymaps to trip over. `cond` is evaluated on every
  start, so this takes effect immediately; no `:Lazy sync`/restart needed.
- **It's specifically a startup cost, not a per-save one.** The clipboard
  probe runs once, while your init.lua is sourced, not again on autosave, on
  `FocusLost`, or when you switch panes and type `/prompt` — that last step
  never touches nvim at all (`map pop`/reading the file is a separate,
  plain filesystem read and write). If a session still feels slow at the
  hand-off moment specifically, that's terminal pane-switching or the
  agent's own slash-command overhead, not this tool or Neovim.
- **`/prompt`'s own overhead is small, and it isn't Neovim's.** Measured on
  this project's own dev machine: `map pop` runs in ~60-85ms end to end —
  bare `python3 -c pass` alone is ~30ms of that, this package's own imports
  add maybe another ~20ms, and the rest is the file read/archive/write. If
  `/prompt` still feels slow, that latency lives in the *agent host's* own
  prompt-construction path, not in anything this package does — there's no
  nvim process in this path at all. Claude Code's variant adds one hook
  subprocess (`map pop --stage`, same ~60-85ms budget).

## Agent integration

The design rule for `/prompt`: **the host, not the model, does the work.**
Reading the draft, splicing it into the outgoing message, archiving, and
clearing the scratch file all run locally while the prompt is being built.
The model receives the draft **verbatim** — a handoff is indistinguishable
from the user having typed it into the chat box — or, when nothing was
composed, a single locally-generated notice ("no prompt to hand off"). No
tags, no framing, no file-operation instructions.

- **OpenCode**: a command file whose ``!`map pop` `` template substitution
  executes at send time and splices only the output into the prompt.
- **Claude Code**: a command file that `@`-includes the draft, plus a
  `UserPromptExpansion` hook that runs `map pop --stage` first — archive +
  clear + stage the content where the include reads it. (Claude's own
  ``!` `` injection annotates the model-visible message with a
  `● Bash(...)` line, hence the different mechanism.)
- **Antigravity CLI (`agy`)**: a frontmatter-only skill (so `/prompt`
  exists as a slash command) plus a `PreInvocation` hook that pops locally
  and injects the prompt as a genuine user message — agy has no include or
  substitution primitive, but its hooks can inject trajectory steps.

See [`commands/README.md`](./commands/README.md) for the per-host
comparative table, templates, hook scripts, and install steps —
[`commands/decisions.md`](./commands/decisions.md) for the cross-cutting
design decisions, and [`commands/turn-end.md`](./commands/turn-end.md) for
the turn-end hook surface (agent done / question / report).

`skills/prompt/` is a **read-only fallback** for hosts without local
expansion primitives: it teaches an agent only to *read*
`.ma/prompt/current.md` — and explicitly forbids running `map pop` or
touching the file. Never install it where a `/prompt` command file exists
(a same-named skill wins in Claude Code, and its instruction body is
exactly the model-driven file-op noise the command design avoids). See
[`skills/README.md`](./skills/README.md).

## Why not tmux `send-keys` / auto-injection?

That's the obvious next step — save, close the pane, and have the tool type
`/prompt` into the neighboring agent pane for you — but it needs a reliable
way to identify *which* pane is running the agent, which varies by terminal
(tmux panes, Windows Terminal panes, and OS-level input injection like
`xdotool`/`wtype` all solve a different half of that problem). The manual
handoff above works everywhere today; auto-injection is being explored as a
follow-up, potentially building on [`multi-agent-registry`](https://github.com/InTEGr8or/multi-agent-registry)'s
chat discovery to identify a live agent session (not just a recent one) in
the same directory.

If/when that lands: prefer sending a widely-supported "submit" keystroke —
`Ctrl+Enter` is the closest thing to a universal convention across chat
input boxes — into the target pane after typing `/prompt`, over anything
input-method-specific, so the same injection code has a chance of working
across agents rather than being re-tuned per host.

## Design notes

- **The prompt file is per-project, not global.** `.ma/prompt/current.md`
  resolves against the nearest `.git` root, so working on two projects in two
  terminal tabs never mixes up their scratch files.
- **`.ma/` is a shared root, not this tool's alone.** It's the umbrella
  directory for the whole multi-agent-* line (`map`'s CLI alias is the shared
  `ma` prefix of `map`/`mar`/`maa`) — one dotfolder instead of one per
  product. Only `.ma/prompt/` is this tool's; a sibling product could use
  `.ma/registry/`, etc., without colliding. Note that `task-agent`'s existing
  `.task-agent/` convention predates this and stays as-is — migrating an
  already-shipped tool's config layout is a separate, larger decision.
- **`.gitignore` is managed for you.** The first time `map edit` runs in a
  git repo, it appends `.ma/prompt/` to `.gitignore` if it isn't already
  covered — including by a broader pre-existing `.ma/` entry.
- **Reading is non-destructive; handing off isn't, but it never discards
  either.** `map show` and `@prompt.md` (file mention) just print/read — the
  file is untouched either way. `/prompt` (`map pop`) clears it, because the
  whole point is not needing a separate "now go clear it" step — but it
  archives first, so "cleared" never means "gone". `--no-archive` is the
  explicit opt-out for content that shouldn't be kept anywhere at all.
- **The editor notices when the file changes out from under it.** `/prompt`
  runs `map pop` from the *agent's* process, not from inside the running
  nvim session — so if you're still looking at that buffer when you hand a
  draft off, it auto-reloads (`autoread` + `checktime` on
  `FocusGained`/`BufEnter`) the next time you focus it, rather than keep
  showing the text you already submitted. It won't discard anything you've
  since typed there unsaved.
