"""End-to-end check that the autosave Lua actually saves, using real headless Neovim.

Skipped when nvim isn't installed. Uses -u NONE (skip the test runner's own
init.lua) purely for test speed/determinism — this does not exercise
--clean, it's just how the harness gets a fast, isolated nvim.
"""

import shutil
import subprocess

import pytest

from multi_agent_prompt.editor import build_autosave_lua

pytestmark = pytest.mark.skipif(
    shutil.which("nvim") is None, reason="nvim not installed"
)


def _run_headless(file, extra_cmds, timeout=10):
    lua = build_autosave_lua(debounce_ms=200)
    argv = ["nvim", "--headless", "-u", "NONE", "-c", f"lua {lua}"]
    for c in extra_cmds:
        argv += ["-c", c]
    argv += ["-c", "qa!", str(file)]
    subprocess.run(argv, timeout=timeout, capture_output=True, check=True)


def test_debounced_autosave_writes_after_edit(tmp_path):
    """The debounce timer itself: fire TextChangedI, confirm it writes ~debounce_ms later.

    Real interactive typing fires TextChangedI on its own (well-established
    Neovim behavior); headless batch execution driven purely by ``-c``
    commands never returns to Neovim's idle/input loop, which is what that
    event is tied to, so it must be triggered explicitly here (``doautocmd``)
    to exercise the same callback a real edit would invoke.
    """
    file = tmp_path / "prompt.md"
    file.write_text("")

    _run_headless(
        file,
        [
            'call feedkeys("ihello from the autosave test\\<Esc>", "x")',
            "doautocmd TextChangedI",
            "lua vim.wait(400)",  # past the 200ms debounce
        ],
    )

    assert file.read_text().strip() == "hello from the autosave test"


def test_no_edit_means_no_spurious_write(tmp_path):
    file = tmp_path / "prompt.md"
    file.write_text("original content")

    _run_headless(file, ["sleep 400m"])

    assert file.read_text() == "original content"


def test_focus_lost_saves_immediately_without_waiting_for_debounce(tmp_path):
    file = tmp_path / "prompt.md"
    file.write_text("")

    # A 5s debounce that would never fire in time on its own; only the
    # immediate FocusLost/BufLeave save path can make this pass.
    lua = build_autosave_lua(debounce_ms=5000)
    argv = [
        "nvim",
        "--headless",
        "-u",
        "NONE",
        "-c",
        f"lua {lua}",
        "-c",
        "normal! iwritten before losing focus",
        "-c",
        "doautocmd FocusLost",
        "-c",
        "sleep 100m",
        "-c",
        "qa!",
        str(file),
    ]
    subprocess.run(argv, timeout=10, capture_output=True, check=True)

    assert file.read_text().strip() == "written before losing focus"
