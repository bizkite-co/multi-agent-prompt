"""End-to-end check that the autosave Lua actually saves, using real headless Neovim.

Skipped when nvim isn't installed. Uses -u NONE (skip the test runner's own
init.lua) purely for test speed/determinism — this does not exercise
--clean, it's just how the harness gets a fast, isolated nvim.
"""

import os
import pty
import shutil
import subprocess
import time

import pytest

from multi_agent_prompt.editor import build_autosave_lua, build_nvim_command

pytestmark = pytest.mark.skipif(
    shutil.which("nvim") is None, reason="nvim not installed"
)

needs_map_on_path = pytest.mark.skipif(
    shutil.which("map") is None,
    reason="the `map` console script isn't on PATH (install this package first)",
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


@needs_map_on_path
def test_clear_keymap_archives_and_empties_via_real_map_clear(tmp_path):
    """The in-editor clear keymap shells out to the real `map clear` — this
    exercises that whole round trip: write, archive, truncate, reload."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    prompt_dir = repo / ".ma" / "prompt"
    prompt_dir.mkdir(parents=True)
    file = prompt_dir / "current.md"
    file.write_text("")

    lua = build_autosave_lua(debounce_ms=200)
    argv = [
        "nvim",
        "--headless",
        "-u",
        "NONE",
        "-c",
        f"lua {lua}",
        "-c",
        'call feedkeys("ia draft worth keeping\\<Esc>", "x")',
        "-c",
        "lua vim.wait(50)",
        # Single-quoted Vimscript string: <leader>pc resolves to the literal
        # mapping \pc when mapleader is unset (as under -u NONE). A
        # double-quoted "\pc" is ambiguous — \p isn't a recognized escape —
        # so this must stay single-quoted.
        "-c",
        r"call feedkeys('\pc', 'x')",
        "-c",
        "lua vim.wait(300)",
        "-c",
        "qa!",
        str(file),
    ]
    subprocess.run(argv, timeout=10, capture_output=True, check=True, cwd=repo)

    assert file.read_text() == ""
    archived = list((prompt_dir / "archive").glob("*.md"))
    assert len(archived) == 1
    assert archived[0].read_text().strip() == "a draft worth keeping"


def test_insert_mode_on_open_lets_you_type_without_pressing_i(tmp_path):
    """`--headless` disables real UI attachment, and startinsert! (like
    TextChanged above) depends on it — so unlike the other tests here, this
    one needs a real pseudo-terminal to mean anything. Without insert mode,
    the plain characters below would be interpreted as Normal-mode commands
    instead of typed into the buffer.
    """
    file = tmp_path / "current.md"
    file.write_text("")

    argv = build_nvim_command(file, clean=True)  # includes -u NONE already

    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    try:
        time.sleep(0.5)  # let nvim actually start and the UI attach
        os.write(master, b"typed without pressing i first")
        time.sleep(0.3)
        os.write(master, b"\x1b")  # Esc
        time.sleep(0.2)
        os.write(master, b":wq!\r")
        proc.wait(timeout=10)
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()

    assert file.read_text().strip() == "typed without pressing i first"


def test_history_keymap_lists_and_opens_an_archived_draft_readonly(tmp_path):
    """`:vsplit <archive_dir>` (netrw) was the first approach here, and it
    doesn't hold up: netrw's directory browsing isn't available at all under
    -u NONE (confirmed directly — even `:Explore` errors as "not an editor
    command" there). This exercises the self-contained scratch-buffer
    listing that replaced it, which doesn't depend on netrw either way.
    """
    file = tmp_path / "current.md"
    file.write_text("")
    archive_dir = file.parent / "archive"
    archive_dir.mkdir()
    (archive_dir / "20260101T000000-1.md").write_text("an old draft")

    argv = build_nvim_command(file, clean=True, clear_key=None)

    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    try:
        time.sleep(0.5)
        os.write(master, b"\x1b")  # ensure normal mode (insert mode is the default)
        time.sleep(0.1)
        os.write(master, b"\\ph")  # <leader>ph; mapleader is unset -> "\" under -u NONE
        time.sleep(0.3)
        os.write(master, b"\r")  # open the (only) listed file
        time.sleep(0.3)
        os.write(
            master,
            b":lua vim.g.map_test_result = "
            b"vim.api.nvim_buf_get_name(0) .. '|' .. tostring(vim.bo.readonly)\r",
        )
        time.sleep(0.2)
        # Write the result through a *different* file so we don't depend on
        # scraping terminal escape sequences back out of the pty.
        result_file = tmp_path / "result.txt"
        os.write(
            master,
            f':call writefile([g:map_test_result], "{result_file}")\r'.encode(),
        )
        time.sleep(0.3)
        os.write(master, b":qa!\r:qa!\r:qa!\r")
        proc.wait(timeout=10)
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()

    result = result_file.read_text().strip()
    name, readonly = result.split("|")
    assert name == str(archive_dir / "20260101T000000-1.md")
    assert readonly == "true"


def test_help_keymap_shows_and_closes_a_cheatsheet(tmp_path):
    file = tmp_path / "current.md"
    file.write_text("")

    argv = build_nvim_command(file, clean=True)

    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    result_file = tmp_path / "result.txt"
    try:
        time.sleep(0.5)
        os.write(master, b"\x1b")  # ensure normal mode
        time.sleep(0.1)
        os.write(master, b"g?")
        time.sleep(0.4)
        lua_cmd = (
            ":lua local b = vim.api.nvim_get_current_buf(); "
            "local lines = vim.api.nvim_buf_get_lines(b, 0, -1, false); "
            "vim.fn.writefile("
            "{tostring(vim.fn.winnr('$')) .. '|' .. table.concat(lines, '~')}, "
            f'"{result_file}")\r'
        )
        os.write(master, lua_cmd.encode())
        time.sleep(0.3)
        os.write(master, b":qa!\r:qa!\r:qa!\r")
        proc.wait(timeout=10)
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()

    winnr, content = result_file.read_text().strip().split("|", 1)
    assert winnr == "2"  # the float, on top of the one editing window
    assert "archive current draft" in content
    assert "browse archived drafts" in content
    assert "show this help" in content


def _paste_via_bracketed_paste(master, text: str) -> None:
    """Simulate what a real terminal sends for a paste: text wrapped in the
    bracketed-paste escape sequence, which is how Neovim's vim.paste() gets
    invoked at all — plain os.write of the raw characters does not trigger
    it, it just looks like fast typing.
    """
    os.write(master, b"\x1b[200~" + text.encode() + b"\x1b[201~")


def test_paste_at_or_above_threshold_creates_a_closed_fold(tmp_path):
    file = tmp_path / "current.md"
    file.write_text("")

    argv = build_nvim_command(file, clean=True, clear_key=None, history_key=None, help_key=None)

    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    result_file = tmp_path / "result.txt"
    try:
        time.sleep(0.5)  # already in insert mode (default)
        _paste_via_bracketed_paste(master, "\n".join(f"line {i}" for i in range(10)))
        time.sleep(0.3)
        os.write(master, b"\x1b")
        time.sleep(0.2)
        lua_check = (
            ':lua vim.fn.writefile({tostring(vim.fn.foldclosed(1)) .. "|" .. '
            f'tostring(vim.fn.line("$"))}}, "{result_file}")\r'
        )
        os.write(master, lua_check.encode())
        time.sleep(0.3)
        os.write(master, b":qa!\r:qa!\r")
        proc.wait(timeout=10)
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()

    foldclosed, total_lines = result_file.read_text().strip().split("|")
    assert total_lines == "10"
    assert foldclosed == "1"  # a closed fold starting at line 1 covers the paste


def test_paste_below_threshold_is_not_folded(tmp_path):
    file = tmp_path / "current.md"
    file.write_text("")

    argv = build_nvim_command(file, clean=True, clear_key=None, history_key=None, help_key=None)

    master, slave = pty.openpty()
    proc = subprocess.Popen(argv, stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    result_file = tmp_path / "result.txt"
    try:
        time.sleep(0.5)
        _paste_via_bracketed_paste(master, "\n".join(f"line {i}" for i in range(3)))
        time.sleep(0.3)
        os.write(master, b"\x1b")
        time.sleep(0.2)
        lua_check = f':lua vim.fn.writefile({{tostring(vim.fn.foldclosed(1))}}, "{result_file}")\r'
        os.write(master, lua_check.encode())
        time.sleep(0.3)
        os.write(master, b":qa!\r:qa!\r")
        proc.wait(timeout=10)
    finally:
        os.close(master)
        if proc.poll() is None:
            proc.kill()

    assert result_file.read_text().strip() == "-1"  # no fold: foldclosed() returns -1
