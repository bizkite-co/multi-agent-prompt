# Multi-Agent Prompt ✍️

A crash-proof, autosaving prompt editor for AI coding agent CLIs.

Chat text boxes lose long, carefully-composed prompts to a single wrong
keystroke, and give you almost no editing power while you write. `multi-agent-prompt`
moves composition out of the chat box entirely: write in a real Neovim, in a
split pane next to your agent session, autosaved to disk every couple of
seconds so a crash or a fat-fingered shortcut can never cost you more than a
moment of typing. When you're ready, hand it to the agent with `/prompt` or
`@prompt.md`.

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

This opens `.map/prompt.md` — resolved to the current project's git root, so
every pane in the same repo shares one scratch file — in your actual `nvim`,
your actual `init.lua`, your actual keymaps and plugins. No config import
step, no reimplemented Vim subset: it's just Neovim. A buffer-local autocmd
(scoped only to this one buffer — it never touches how you edit anything
else) autosaves ~2 seconds after you stop typing, and immediately when you
switch away from the pane (`FocusLost`/`BufLeave`), so the save always beats
you to the chat window.

When you're done, switch back to the agent pane and either:

- Type `/prompt` (if the agent's install includes the skill — see below), or
- Reference `@prompt.md` / `@.map/prompt.md` directly, if your agent supports
  file mentions and can see gitignored files.

```
map            # open the scratch file (same as `map edit`)
map where      # print the resolved file path
map show       # print its current content to stdout
map clear      # empty it
map --clean    # skip your init.lua entirely (-u NONE) for faster startup
```

## Agent integration

`skills/prompt/` is a portable [Agent Skill](https://code.claude.com/docs/en/skills)
that teaches a host to read `.map/prompt.md` and treat its content as the
user's message when they type `/prompt`. See [`skills/README.md`](./skills/README.md)
for install paths.

## Why not tmux `send-keys` / auto-injection?

That's the obvious next step — save, close the pane, and have the tool type
`/prompt` into the neighboring agent pane for you — but it needs a reliable
way to identify *which* pane is running the agent, which varies by terminal
(tmux panes, Windows Terminal panes, and OS-level input injection like
`xdotool`/`wtype` all solve a different half of that problem). The manual
handoff above works everywhere today; auto-injection is being explored as a
follow-up, potentially building on [`multi-agent-registry`](https://github.com/InTEGr8or/multi-agent-registry)'s
chat discovery to identify a live agent session in the same directory.

## Design notes

- **The prompt file is per-project, not global.** `.map/prompt.md` resolves
  against the nearest `.git` root, so working on two projects in two
  terminal tabs never mixes up their scratch files.
- **`.gitignore` is managed for you.** The first time `map edit` runs in a
  git repo, it appends `.map/` to `.gitignore` if it isn't already covered.
- **Nothing is cleared automatically.** The whole point is not losing work —
  reading the file (via the skill, or `@prompt.md`) never deletes it. Use
  `map clear` when you're actually done with it.
