"""Launch the user's real Neovim on the scratch prompt file, with autosave bolted on.

This deliberately does not touch the user's ``init.lua`` or try to
reimplement Vim: it loads their actual config as-is (so keymaps, colorscheme,
and plugins "just work" without any import step) and layers a small,
buffer-local autosave autocmd on top via ``-c``, so it can never affect any
other buffer or session.

Autosave fires two ways:
  * Debounced (``debounce_ms`` after the last edit) — the everyday case.
  * Immediately on ``FocusLost``/``BufLeave`` — so switching to the chat
    pane to hand the prompt off never races the debounce timer.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

DEFAULT_DEBOUNCE_MS = 2000
DEFAULT_NVIM_BIN = "nvim"


def build_autosave_lua(debounce_ms: int = DEFAULT_DEBOUNCE_MS) -> str:
    """Lua snippet, scoped to the current buffer only, that autosaves it."""
    return f"""
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


def build_nvim_command(
    file: Path,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    nvim_bin: str = DEFAULT_NVIM_BIN,
    clean: bool = False,
) -> list[str]:
    """The argv to launch nvim on ``file`` with autosave enabled.

    ``clean=True`` passes ``-u NONE``, skipping the user's init.lua (and every
    plugin it loads) entirely — a fast, minimal mode for when startup latency
    from a large distro (LSP servers, treesitter, etc.) matters more than
    having every keymap and plugin available for a quick one-file edit.
    """
    lua = build_autosave_lua(debounce_ms)
    argv = [nvim_bin]
    if clean:
        argv.append("-u")
        argv.append("NONE")
    argv += ["-c", f"lua {lua}", str(file)]
    return argv


def nvim_available(nvim_bin: str = DEFAULT_NVIM_BIN) -> bool:
    return shutil.which(nvim_bin) is not None


def open_editor(
    file: Path,
    debounce_ms: int = DEFAULT_DEBOUNCE_MS,
    nvim_bin: str = DEFAULT_NVIM_BIN,
    clean: bool = False,
) -> int:
    """Open ``file`` in nvim (inheriting the terminal) with autosave. Returns nvim's exit code."""
    file.parent.mkdir(parents=True, exist_ok=True)
    if not file.exists():
        file.touch()
    argv = build_nvim_command(file, debounce_ms=debounce_ms, nvim_bin=nvim_bin, clean=clean)
    result = subprocess.run(argv, check=False)
    return result.returncode
