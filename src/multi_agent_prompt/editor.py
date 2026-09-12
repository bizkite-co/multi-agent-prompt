"""Launch the user's real Neovim on the scratch prompt file, with autosave bolted on.

This deliberately does not touch the user's ``init.lua`` or try to
reimplement Vim: it loads their actual config as-is (so keymaps, colorscheme,
and plugins "just work" without any import step) and layers small,
buffer-local additions on top via ``-c``, so none of it can ever affect any
other buffer or session:

  * Autosave, debounced (``debounce_ms`` after the last edit) — the everyday
    case — and immediately on ``FocusLost``/``BufLeave``, so switching to the
    chat pane to hand the prompt off never races the debounce timer.
  * A ``clear_key`` mapping that archives the current draft (via ``map
    clear``, so the CLI and the in-editor keymap share one implementation)
    and reloads the now-empty buffer.

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

DEFAULT_DEBOUNCE_MS = 2000
DEFAULT_NVIM_BIN = "nvim"
DEFAULT_CLEAR_KEY = "<leader>pc"


def build_autosave_lua(
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    clear_key: str | None = DEFAULT_CLEAR_KEY,
) -> str:
    """Lua snippet, scoped to the current buffer only: autosave plus an optional clear keymap."""
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

    return lua


def build_nvim_command(
    file: Path,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    nvim_bin: str = DEFAULT_NVIM_BIN,
    clean: bool = False,
    clear_key: str | None = DEFAULT_CLEAR_KEY,
    insert: bool = True,
) -> list[str]:
    """The argv to launch nvim on ``file`` with autosave (and the clear keymap) enabled.

    ``clean=True`` passes ``-u NONE``, skipping the user's init.lua (and every
    plugin it loads) entirely — a fast, minimal mode for when startup latency
    from a large distro (LSP servers, treesitter, etc.) matters more than
    having every keymap and plugin available for a quick one-file edit.

    ``insert=True`` (default) drops straight into append-mode insert at the
    end of the buffer — a scratch prompt file is written far more than it's
    navigated, so requiring an `i`/`a`/`o` before typing is pure friction.
    """
    lua = build_autosave_lua(debounce_ms, clear_key=clear_key)
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
        insert=insert,
    )
    env = {**os.environ, "MAP_SESSION": "1"}
    result = subprocess.run(argv, check=False, env=env)
    return result.returncode
