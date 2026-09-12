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

- Type `/prompt` (if the agent's install includes the skill — see below) —
  reads the draft, archives it, and clears the file, all in one step, or
- Reference `@prompt.md` / `@.ma/prompt/current.md` directly, if your agent
  supports file mentions and can see gitignored files — this is a plain
  read, so unlike `/prompt` it doesn't archive or clear anything.

Also want to browse past drafts without leaving the editor? A buffer-local
keymap — `<leader>ph` by default — lists archived drafts (newest first) in a
split; `<CR>` opens one, read-only:

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
map edit --no-insert             # open in normal mode instead of insert mode
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
  not something this tool does for you.
- **It's specifically a startup cost, not a per-save one.** The clipboard
  probe runs once, while your init.lua is sourced, not again on autosave, on
  `FocusLost`, or when you switch panes and type `/prompt` — that last step
  never touches nvim at all (`map pop`/reading the file is a separate,
  plain filesystem read and write). If a session still feels slow at the
  hand-off moment specifically, that's terminal pane-switching or the
  agent's own slash-command overhead, not this tool or Neovim.

## Agent integration

`skills/prompt/` is a portable [Agent Skill](https://code.claude.com/docs/en/skills)
that teaches a host to read `.ma/prompt/current.md` and treat its content as
the user's message when they type `/prompt`. See
[`skills/README.md`](./skills/README.md) for install paths.

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
