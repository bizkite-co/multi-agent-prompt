"""Launch the user's real Neovim on the scratch prompt file, with autosave bolted on.

This deliberately does not touch the user's ``init.lua`` or try to
reimplement Vim: it loads their actual config as-is (so keymaps, colorscheme,
and plugins "just work" without any import step) and layers small additions
on top via ``-c``. Each ``map`` invocation is its own throwaway nvim
process, so none of this can ever reach the user's other, real nvim
sessions — but not everything below is *buffer*-local within this one
session; see fold-on-paste.

  * Autosave, debounced (``debounce_ms`` after the last edit) — the everyday
    case — and immediately on ``FocusLost``/``BufLeave``, so switching to the
    chat pane to hand the prompt off never races the debounce timer.
  * Auto-reload on ``FocusGained``/``BufEnter``: the counterpart to the
    above. Handing a draft off (e.g. via `/prompt`, which runs `map pop`
    from the *agent's* process, not this nvim) clears the file from outside
    this editor session — without this, the buffer you're still looking at
    would keep showing the old, already-submitted text until you touched it.
  * A ``clear_key`` mapping that archives the current draft (via ``map
    clear``, so the CLI and the in-editor keymap share one implementation)
    and reloads the now-empty buffer.
  * A ``history_key`` mapping that lists archived drafts (newest first) in a
    scratch split — ``<CR>`` opens one, read-only. Deliberately not
    `:vsplit <archive_dir>` / netrw: netrw's directory browsing isn't
    available at all under ``-u NONE`` (confirmed directly — even
    `:Explore` is "not an editor command" there), and under a full config
    it may be intercepted by whatever directory-handling plugin (neo-tree,
    oil.nvim, ...) the user has, which is inconsistent with ``--clean``.
    This tiny listing works identically either way.
  * Fold-on-paste: pasting ``fold_threshold`` lines or more (bracketed
    paste, `"+p`, `"*p`, ...) automatically folds (and closes) just those
    lines, via Neovim's ``vim.paste()`` override — so dropping a long CLI
    transcript or diff into the buffer doesn't bury the rest of what you're
    writing. Standard Vim fold commands (``za``/``zo``/``zc``) toggle it;
    nothing new to bind for that part. ``vim.paste`` is a *global* hook, not
    a buffer-local option — this does apply to any other buffer opened
    within this same throwaway session (e.g. one opened via the history
    keymap), which is fine here since every buffer in this session is
    another scratch markdown file.
  * A small UI layer (``build_ui_lua``), also session-scoped and so isolated
    from the user's own nvim: a prompt-editor gutter (line numbers off, a
    ``> `` prompt marker following the cursor in the sign column), a
    statusline footer listing whichever keymaps are active this session, and
    a forced ``#000000`` background that keeps the user's colorscheme fg.
    Degrades silently on any API mismatch rather than aborting the session.

The launched nvim gets ``MAP_SESSION=1`` in its environment — nothing in
this package reads it, but it's there for a user who wants to guard an
expensive line in their own init.lua (e.g. a `clipboard=unnamedplus` setting
that's slow specifically under WSL) behind ``if not vim.env.MAP_SESSION``,
without multi-agent-prompt ever touching that file itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

from multi_agent_prompt.paths import ARCHIVE_DIRNAME

DEFAULT_DEBOUNCE_MS = 2000
DEFAULT_NVIM_BIN = "nvim"
DEFAULT_CLEAR_KEY = "<leader>pc"
DEFAULT_HISTORY_KEY = "<leader>ph"
DEFAULT_HELP_KEY = "g?"
DEFAULT_FOLD_THRESHOLD = 6
DEFAULT_PROMPT_GUTTER = True
DEFAULT_FOOTER_KEYMAPS = True
DEFAULT_TRUEBLACK_BG = True


def build_autosave_lua(
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    clear_key: str | None = DEFAULT_CLEAR_KEY,
    history_dir: Path | None = None,
    history_key: str | None = DEFAULT_HISTORY_KEY,
    help_key: str | None = DEFAULT_HELP_KEY,
    fold_threshold: int | None = DEFAULT_FOLD_THRESHOLD,
) -> str:
    """Lua snippet, scoped to the current buffer only.

    Always: autosave (debounced + on focus-lost) and auto-reload on
    focus-gained. Optionally: the clear keymap, the archive-browsing keymap
    (when ``history_dir`` is given), fold-on-paste (when ``fold_threshold``
    is a positive int), and a ``g?`` cheatsheet listing whichever of those
    are actually active — reflecting real overrides, not just the defaults,
    since it's built from the same values passed in here.
    """
    lua = f"""
local uv = vim.uv or vim.loop
local timer = uv.new_timer()
local function save_now()
  if vim.bo.modified then
    vim.cmd("silent! write")
  end
end
vim.api.nvim_create_autocmd({{"TextChanged", "TextChangedI"}}, {{
  buffer = 0,
  callback = function()
    timer:stop()
    timer:start({debounce_ms}, 0, vim.schedule_wrap(save_now))
  end,
}})
vim.api.nvim_create_autocmd({{"FocusLost", "BufLeave"}}, {{
  buffer = 0,
  callback = function()
    timer:stop()
    save_now()
  end,
}})
vim.opt.autoread = true
vim.api.nvim_create_autocmd({{"FocusGained", "BufEnter"}}, {{
  buffer = 0,
  callback = function()
    -- Reloads from disk only if this buffer has no unsaved changes of its
    -- own, so a draft in progress here is never silently discarded.
    vim.cmd("silent! checktime")
  end,
}})
""".strip()

    if clear_key:
        lua += f"""
vim.keymap.set("n", "{clear_key}", function()
  timer:stop()
  -- Deliberately not `silent!`: if the write fails, let the error abort
  -- here rather than silently archiving/truncating stale disk content.
  vim.cmd("silent write")
  vim.fn.system("map clear")
  vim.cmd("edit!")
end, {{ buffer = 0, desc = "multi-agent-prompt: archive and clear" }})
""".rstrip()

    if history_dir and history_key:
        hdir = str(history_dir)
        # A self-contained scratch-buffer listing, not `:vsplit <dir>` / netrw:
        # netrw's directory browsing isn't available under -u NONE at all
        # (confirmed directly — even `:Explore` is "not an editor command"
        # there), and under a full config it may be intercepted by whatever
        # directory-handling plugin (neo-tree, oil.nvim, ...) the user has —
        # fine on its own, but inconsistent with --clean. This works
        # identically either way.
        lua += f"""
vim.api.nvim_create_autocmd("BufReadPost", {{
  pattern = "{hdir}/*",
  callback = function()
    vim.bo.readonly = true
    vim.bo.modifiable = false
  end,
  desc = "multi-agent-prompt: archived drafts are read-only",
}})
vim.keymap.set("n", "{history_key}", function()
  local dir = "{hdir}"
  local ok, files = pcall(vim.fn.readdir, dir)
  files = (ok and files) or {{}}
  table.sort(files, function(a, b) return a > b end)  -- filenames sort newest-first
  if #files == 0 then
    vim.notify("multi-agent-prompt: no archived drafts yet", vim.log.levels.INFO)
    return
  end
  vim.cmd("vsplit")
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_win_set_buf(0, buf)
  vim.bo[buf].buftype = "nofile"
  vim.bo[buf].bufhidden = "wipe"
  vim.bo[buf].filetype = "map-history"
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, files)
  vim.bo[buf].modifiable = false
  vim.keymap.set("n", "<CR>", function()
    local line = vim.api.nvim_get_current_line()
    if line ~= "" then
      vim.cmd("edit " .. vim.fn.fnameescape(dir .. "/" .. line))
    end
  end, {{ buffer = buf, desc = "multi-agent-prompt: open archived draft" }})
end, {{ buffer = 0, desc = "multi-agent-prompt: browse archived prompts" }})
""".rstrip()

    if fold_threshold and fold_threshold > 0:
        # vim.paste() is Neovim's single hook for every paste source
        # (bracketed/terminal paste, "+p, "*p, ...), called with the
        # complete line list for a small paste (phase -1) or streamed in
        # chunks for a large one (phase 1/2/3). Track cursor position across
        # the call rather than trust `#lines` alone, since a chunked paste's
        # individual calls don't each carry the full line count.
        lua += f"""
local map_orig_paste = vim.paste
local map_paste_start = nil
vim.paste = function(lines, phase)
  if phase == 1 or phase == -1 then
    map_paste_start = vim.api.nvim_win_get_cursor(0)[1]
  end
  local ok = map_orig_paste(lines, phase)
  if (phase == -1 or phase == 3) and map_paste_start then
    local paste_end = vim.api.nvim_win_get_cursor(0)[1]
    if paste_end - map_paste_start >= {fold_threshold} then
      vim.cmd(string.format("%d,%dfold", map_paste_start, paste_end))
    end
    map_paste_start = nil
  end
  return ok
end
""".rstrip()

    if help_key:
        entries = []
        if clear_key:
            entries.append((clear_key, "archive current draft & clear"))
        if history_dir and history_key:
            entries.append((history_key, "browse archived drafts"))
        if fold_threshold and fold_threshold > 0:
            entries.append(("za/zo/zc", f"toggle fold ({fold_threshold}+ line pastes auto-fold)"))
        entries.append((help_key, "show this help"))
        width = max(len(k) for k, _ in entries)
        help_lines = ", ".join(
            f'"  {k.ljust(width)}  {desc}"' for k, desc in entries
        )
        lua += f"""
vim.keymap.set("n", "{help_key}", function()
  local lines = {{ " multi-agent-prompt ", "", {help_lines} }}
  local width = 0
  for _, l in ipairs(lines) do
    width = math.max(width, vim.fn.strdisplaywidth(l))
  end
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false
  vim.bo[buf].bufhidden = "wipe"
  local win = vim.api.nvim_open_win(buf, true, {{
    relative = "cursor",
    row = 1,
    col = 0,
    width = width + 2,
    height = #lines,
    style = "minimal",
    border = "rounded",
  }})
  local close = function()
    pcall(vim.api.nvim_win_close, win, true)
  end
  vim.keymap.set("n", "q", close, {{ buffer = buf, nowait = true }})
  vim.keymap.set("n", "<Esc>", close, {{ buffer = buf, nowait = true }})
end, {{ buffer = 0, desc = "multi-agent-prompt: show keymap help" }})
""".rstrip()

    return lua


_GUTTER_LUA = """
vim.opt.number = false
vim.opt.relativenumber = false
vim.opt.signcolumn = "yes"
local map_gutter_ns = vim.api.nvim_create_namespace("map-gutter")
local map_gutter_id
local function map_place_gutter()
  if map_gutter_id then
    pcall(vim.api.nvim_buf_del_extmark, 0, map_gutter_ns, map_gutter_id)
  end
  local count = vim.api.nvim_buf_line_count(0)
  if count == 0 then
    return
  end
  -- vim.fn.line('.') (not nvim_win_get_cursor) so this also works headless;
  -- headless cursors can report 0-based/0 rows, so clamp to [0, count-1].
  local line = math.max(0, math.min(vim.fn.line(".") - 1, count - 1))
  map_gutter_id = vim.api.nvim_buf_set_extmark(0, map_gutter_ns, line, 0, {
    sign_text = "> ",
    hl_group = "CursorLineNr",
    priority = 200,
  })
end
vim.api.nvim_create_autocmd({"CursorMoved", "CursorMovedI", "TextChanged", "TextChangedI"}, {
  buffer = 0,
  callback = map_place_gutter,
  desc = "multi-agent-prompt: prompt-marker gutter",
})
map_place_gutter()
""".strip()

#: Highlight groups flattened to a #000000 background (foregrounds kept).
_TRUEBLACK_GROUPS = (
    "Normal",
    "NormalFloat",
    "EndOfBuffer",
    "SignColumn",
    "FoldColumn",
    "LineNr",
    "CursorLineNr",
    "StatusLine",
    "StatusLineNC",
    "WinSeparator",
    "MsgArea",
    "Pmenu",
    "PmenuSel",
    "PmenuSbar",
    "PmenuThumb",
    "CursorLine",
    "ColorColumn",
    "QuickFixLine",
)

#: Lua body for the trueblack background; group list shared with _TRUEBLACK_GROUPS.
_TRUEBLACK_LUA = f"""
vim.opt.background = "dark"
local map_bg_groups = {{{"".join(f'"{g}", ' for g in _TRUEBLACK_GROUPS)}}}
local function map_trueblack(name)
  local ok, cur = pcall(vim.api.nvim_get_hl, 0, {{ name = name }})
  if not ok or not cur or vim.tbl_isempty(cur) then
    return
  end
  local hl = {{ bg = "#000000" }}
  if cur.fg then
    hl.fg = cur.fg
  end
  vim.api.nvim_set_hl(0, name, hl)
end
for _, g in ipairs(map_bg_groups) do
  map_trueblack(g)
end
""".strip()


def build_ui_lua(
    *,
    prompt_gutter: bool = True,
    footer_keymaps: bool = True,
    trueblack_bg: bool = True,
    clear_key: str | None = DEFAULT_CLEAR_KEY,
    history_key: str | None = DEFAULT_HISTORY_KEY,
    history: bool = True,
    help_key: str | None = DEFAULT_HELP_KEY,
    fold_threshold: int | None = DEFAULT_FOLD_THRESHOLD,
) -> str:
    """Lua for the prompt editor's visual layer, applied to the whole session.

    Unlike ``build_autosave_lua`` these are session-level (a dedicated
    throwaway nvim process, so they can never leak into the user's normal
    nvim), not buffer-local:

      * ``prompt_gutter`` — line numbers off; a ``> `` prompt marker follows
        the cursor in the sign column, replacing the number gutter.
      * ``footer_keymaps`` — a statusline footer listing whichever keymaps
        are actually active this session (built from the same key arguments
        here, so it reflects real overrides like ``build_autosave_lua``'s
        ``g?`` cheatsheet does).
      * ``trueblack_bg`` — keeps the user's colorscheme foregrounds but
        flattens every background surface to ``#000000`` to match a
        trueblack terminal.

    The whole snippet runs inside ``pcall``: any API/version mismatch (e.g.
    a Neovim too old for ``sign_text``) degrades to a logged no-op instead
    of aborting the session start (which would also drop autosave, since
    this runs in the same ``-c`` as ``build_autosave_lua``).
    """
    body: list[str] = []

    if prompt_gutter:
        body.append(_GUTTER_LUA)

    if footer_keymaps:
        entries = []
        if clear_key:
            entries.append((clear_key, "archive & clear"))
        if history and history_key:
            entries.append((history_key, "browse history"))
        if fold_threshold and fold_threshold > 0:
            entries.append(("za/zo/zc", "toggle fold"))
        if help_key:
            entries.append((help_key, "help"))

        if entries:
            hint = " · ".join(f"{k} {d}" for k, d in entries)
            body.append(
                'vim.opt.laststatus = 3\n'
                f"vim.opt.statusline = ' > map · {hint} %= %m %03l:%02c '\n"
            )

    if trueblack_bg:
        body.append(_TRUEBLACK_LUA)

    if not body:
        return ""

    inner = textwrap.indent("\n\n".join(body), "  ", predicate=lambda line: bool(line))
    return f"pcall(function()\n{inner}\nend)\n"


def build_nvim_command(
    file: Path,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    nvim_bin: str = DEFAULT_NVIM_BIN,
    clean: bool = False,
    clear_key: str | None = DEFAULT_CLEAR_KEY,
    history_key: str | None = DEFAULT_HISTORY_KEY,
    help_key: str | None = DEFAULT_HELP_KEY,
    fold_threshold: int | None = DEFAULT_FOLD_THRESHOLD,
    insert: bool = True,
    prompt_gutter: bool = DEFAULT_PROMPT_GUTTER,
    footer_keymaps: bool = DEFAULT_FOOTER_KEYMAPS,
    trueblack_bg: bool = DEFAULT_TRUEBLACK_BG,
) -> list[str]:
    """The argv to launch nvim on ``file`` with autosave (and the clear/history/help/fold keymaps) enabled.

    ``clean=True`` passes ``-u NONE``, skipping the user's init.lua (and every
    plugin it loads) entirely — a fast, minimal mode for when startup latency
    from a large distro (LSP servers, treesitter, etc.) matters more than
    having every keymap and plugin available for a quick one-file edit.

    ``insert=True`` (default) drops straight into append-mode insert at the
    end of the buffer — a scratch prompt file is written far more than it's
    navigated, so requiring an `i`/`a`/`o` before typing is pure friction.

    ``prompt_gutter`` / ``footer_keymaps`` / ``trueblack_bg`` toggle the
    prompt-editor visual layer (see ``build_ui_lua``). The buffer-scoped
    autosave/keymap Lua always runs first; if the visual layer fails on an
    older Neovim it is pcall-guarded, so autosave is never lost.
    """
    history_dir = file.parent / ARCHIVE_DIRNAME
    lua = build_autosave_lua(
        debounce_ms,
        clear_key=clear_key,
        history_dir=history_dir,
        history_key=history_key,
        help_key=help_key,
        fold_threshold=fold_threshold,
    )
    ui = build_ui_lua(
        prompt_gutter=prompt_gutter,
        footer_keymaps=footer_keymaps,
        trueblack_bg=trueblack_bg,
        clear_key=clear_key,
        history_key=history_key,
        history=history_dir is not None and history_key is not None,
        help_key=help_key,
        fold_threshold=fold_threshold,
    )
    if ui:
        lua = lua + "\n\n" + ui
    argv = [nvim_bin]
    if clean:
        argv.append("-u")
        argv.append("NONE")
    argv += ["-c", f"lua {lua}"]
    if insert:
        argv += ["-c", "normal! G", "-c", "startinsert!"]
    argv += [str(file)]
    return argv


def nvim_available(nvim_bin: str = DEFAULT_NVIM_BIN) -> bool:
    return shutil.which(nvim_bin) is not None


def open_editor(
    file: Path,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    nvim_bin: str = DEFAULT_NVIM_BIN,
    clean: bool = False,
    clear_key: str | None = DEFAULT_CLEAR_KEY,
    history_key: str | None = DEFAULT_HISTORY_KEY,
    help_key: str | None = DEFAULT_HELP_KEY,
    fold_threshold: int | None = DEFAULT_FOLD_THRESHOLD,
    insert: bool = True,
    prompt_gutter: bool = DEFAULT_PROMPT_GUTTER,
    footer_keymaps: bool = DEFAULT_FOOTER_KEYMAPS,
    trueblack_bg: bool = DEFAULT_TRUEBLACK_BG,
) -> int:
    """Open ``file`` in nvim (inheriting the terminal) with autosave. Returns nvim's exit code."""
    file.parent.mkdir(parents=True, exist_ok=True)
    if not file.exists():
        file.touch()
    argv = build_nvim_command(
        file,
        debounce_ms=debounce_ms,
        nvim_bin=nvim_bin,
        clean=clean,
        clear_key=clear_key,
        history_key=history_key,
        help_key=help_key,
        fold_threshold=fold_threshold,
        insert=insert,
        prompt_gutter=prompt_gutter,
        footer_keymaps=footer_keymaps,
        trueblack_bg=trueblack_bg,
    )
    env = {**os.environ, "MAP_SESSION": "1"}
    result = subprocess.run(argv, check=False, env=env)
    return result.returncode
