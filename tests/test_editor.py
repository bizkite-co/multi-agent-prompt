from unittest.mock import patch

from multi_agent_prompt.editor import (
    DEFAULT_CLEAR_KEY,
    build_autosave_lua,
    build_nvim_command,
    open_editor,
)


def test_build_autosave_lua_interpolates_debounce():
    lua = build_autosave_lua(debounce_ms=1500)

    assert "timer:start(1500" in lua


def test_build_autosave_lua_scopes_autocmds_to_current_buffer():
    lua = build_autosave_lua(clear_key=None)

    assert lua.count("buffer = 0") == 2  # one per autocmd group


def test_build_autosave_lua_saves_on_focus_lost_and_buf_leave():
    lua = build_autosave_lua()

    assert "FocusLost" in lua
    assert "BufLeave" in lua


def test_build_autosave_lua_registers_clear_keymap_by_default():
    lua = build_autosave_lua()

    assert f'"{DEFAULT_CLEAR_KEY}"' in lua
    assert "vim.keymap.set" in lua
    assert "map clear" in lua
    # Two autocmds plus the keymap, all scoped to this buffer only — never
    # global, so it can't bleed into the user's other buffers/sessions.
    assert lua.count("buffer = 0") == 3


def test_build_autosave_lua_clear_key_is_configurable():
    lua = build_autosave_lua(clear_key="<F5>")

    assert '"<F5>"' in lua
    assert DEFAULT_CLEAR_KEY not in lua


def test_build_autosave_lua_omits_keymap_when_clear_key_is_none():
    lua = build_autosave_lua(clear_key=None)

    assert "vim.keymap.set" not in lua
    assert "map clear" not in lua


def test_build_autosave_lua_clear_writes_before_shelling_out():
    """Order matters: the write must happen before `map clear` reads the file."""
    lua = build_autosave_lua()

    write_pos = lua.index("silent write")
    clear_pos = lua.index("map clear")
    assert write_pos < clear_pos


def test_build_nvim_command_basic(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file)

    assert argv[0] == "nvim"
    assert str(file) == argv[-1]
    assert "-c" in argv


def test_build_nvim_command_clean_mode_adds_u_none(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file, clean=True)

    assert "-u" in argv
    assert "NONE" in argv
    assert argv.index("-u") < argv.index("NONE")


def test_build_nvim_command_respects_custom_binary(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file, nvim_bin="/opt/nvim/bin/nvim")

    assert argv[0] == "/opt/nvim/bin/nvim"


def test_open_editor_creates_parent_directory_before_launching(tmp_path):
    """Regression: `:write` fails silently in a directory that doesn't exist
    yet, so the parent must exist before nvim ever opens the buffer."""
    file = tmp_path / ".ma" / "prompt" / "current.md"
    assert not file.parent.exists()

    with patch("multi_agent_prompt.editor.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        open_editor(file)

    assert file.parent.is_dir()
    assert file.exists()


def test_open_editor_does_not_overwrite_existing_file(tmp_path):
    file = tmp_path / ".ma" / "prompt" / "current.md"
    file.parent.mkdir(parents=True)
    file.write_text("existing draft, must survive")

    with patch("multi_agent_prompt.editor.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        open_editor(file)

    assert file.read_text() == "existing draft, must survive"


def test_open_editor_returns_nvim_exit_code(tmp_path):
    file = tmp_path / "current.md"

    with patch("multi_agent_prompt.editor.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 42
        rc = open_editor(file)

    assert rc == 42


def test_open_editor_sets_map_session_env_var(tmp_path):
    """So a user can guard an expensive line in their own init.lua behind it."""
    file = tmp_path / "current.md"

    with patch("multi_agent_prompt.editor.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        open_editor(file)

    _args, kwargs = mock_run.call_args
    assert kwargs["env"]["MAP_SESSION"] == "1"
