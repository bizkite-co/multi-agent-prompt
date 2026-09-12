"""Launch the user's real Neovim on the scratch prompt file, with autosave bolted on.

This deliberately does not touch the user's ``init.lua`` or try to
reimplement Vim: it loads their actual config as-is (so keymaps, colorscheme,
and plugins "just work" without any import step) and layers small,
buffer-local additions on top via ``-c``, so none of it can ever affect any
other buffer or session:

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
from pathlib import Path

from multi_agent_prompt.paths import ARCHIVE_DIRNAME

DEFAULT_DEBOUNCE_MS = 2000
DEFAULT_NVIM_BIN = "nvim"
DEFAULT_CLEAR_KEY = "<leader>pc"
DEFAULT_HISTORY_KEY = "<leader>ph"


def build_autosave_lua(
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    clear_key: str | None = DEFAULT_CLEAR_KEY,
    history_dir: Path | None = None,
    history_key: str | None = DEFAULT_HISTORY_KEY,
) -> str:
    """Lua snippet, scoped to the current buffer only.

    Always: autosave (debounced + on focus-lost) and auto-reload on
    focus-gained. Optionally: the clear keymap, and — when ``history_dir`` is
    given — the archive-browsing keymap.
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

    return lua


def build_nvim_command(
    file: Path,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    nvim_bin: str = DEFAULT_NVIM_BIN,
    clean: bool = False,
    clear_key: str | None = DEFAULT_CLEAR_KEY,
    history_key: str | None = DEFAULT_HISTORY_KEY,
    insert: bool = True,
) -> list[str]:
    """The argv to launch nvim on ``file`` with autosave (and the clear/history keymaps) enabled.

    ``clean=True`` passes ``-u NONE``, skipping the user's init.lua (and every
    plugin it loads) entirely — a fast, minimal mode for when startup latency
    from a large distro (LSP servers, treesitter, etc.) matters more than
    having every keymap and plugin available for a quick one-file edit.

    ``insert=True`` (default) drops straight into append-mode insert at the
    end of the buffer — a scratch prompt file is written far more than it's
    navigated, so requiring an `i`/`a`/`o` before typing is pure friction.
    """
    history_dir = file.parent / ARCHIVE_DIRNAME
    lua = build_autosave_lua(
        debounce_ms, clear_key=clear_key, history_dir=history_dir, history_key=history_key
    )
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
    insert: bool = True,
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
        insert=insert,
    )
    env = {**os.environ, "MAP_SESSION": "1"}
    result = subprocess.run(argv, check=False, env=env)
    return result.returncode
