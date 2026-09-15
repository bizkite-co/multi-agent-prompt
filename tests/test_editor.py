from unittest.mock import patch

from multi_agent_prompt.editor import (
    DEFAULT_CLEAR_KEY,
    DEFAULT_FOLD_THRESHOLD,
    DEFAULT_HELP_KEY,
    DEFAULT_HISTORY_KEY,
    build_autosave_lua,
    build_nvim_command,
    build_ui_lua,
    open_editor,
)


def test_build_autosave_lua_interpolates_debounce():
    lua = build_autosave_lua(debounce_ms=1500)

    assert "timer:start(1500" in lua


def test_build_autosave_lua_scopes_autocmds_to_current_buffer():
    lua = build_autosave_lua(clear_key=None, help_key=None)

    # TextChanged/TextChangedI (save), FocusLost/BufLeave (save),
    # FocusGained/BufEnter (reload) — one group each, all buffer-local.
    assert lua.count("buffer = 0") == 3


def test_build_autosave_lua_saves_on_focus_lost_and_buf_leave():
    lua = build_autosave_lua()

    assert "FocusLost" in lua
    assert "BufLeave" in lua


def test_build_autosave_lua_reloads_on_focus_gained_and_buf_enter():
    """The other half of FocusLost: `/prompt` clears the file from outside
    this nvim process (it runs `map pop`, not this editor's keymap), so the
    buffer needs its own way to notice and pick up the now-empty file."""
    lua = build_autosave_lua()

    assert "FocusGained" in lua
    assert "BufEnter" in lua
    assert "checktime" in lua
    assert "autoread" in lua


def test_build_autosave_lua_registers_clear_keymap_by_default():
    lua = build_autosave_lua(help_key=None)

    assert f'"{DEFAULT_CLEAR_KEY}"' in lua
    assert "vim.keymap.set" in lua
    assert "map clear" in lua
    # Three autocmd groups plus the keymap, all scoped to this buffer only —
    # never global, so it can't bleed into the user's other buffers/sessions.
    assert lua.count("buffer = 0") == 4


def test_build_autosave_lua_clear_key_is_configurable():
    lua = build_autosave_lua(clear_key="<F5>")

    assert '"<F5>"' in lua
    assert DEFAULT_CLEAR_KEY not in lua


def test_build_autosave_lua_omits_keymap_when_clear_key_is_none():
    lua = build_autosave_lua(clear_key=None, help_key=None)

    assert "vim.keymap.set" not in lua
    assert "map clear" not in lua


def test_build_autosave_lua_clear_writes_before_shelling_out():
    """Order matters: the write must happen before `map clear` reads the file."""
    lua = build_autosave_lua()

    write_pos = lua.index("silent write")
    clear_pos = lua.index("map clear")
    assert write_pos < clear_pos


def test_build_autosave_lua_omits_history_keymap_without_a_directory():
    lua = build_autosave_lua(history_dir=None, clear_key=None, help_key=None)

    assert "vim.keymap.set" not in lua
    assert DEFAULT_HISTORY_KEY not in lua


def test_build_autosave_lua_registers_history_keymap_when_dir_given(tmp_path):
    archive_dir = tmp_path / "archive"

    lua = build_autosave_lua(history_dir=archive_dir, clear_key=None)

    assert f'"{DEFAULT_HISTORY_KEY}"' in lua
    assert str(archive_dir) in lua
    assert "vsplit" in lua


def test_build_autosave_lua_archived_drafts_are_marked_readonly(tmp_path):
    archive_dir = tmp_path / "archive"

    lua = build_autosave_lua(history_dir=archive_dir)

    assert "readonly = true" in lua
    assert "modifiable = false" in lua


def test_build_autosave_lua_registers_help_keymap_by_default():
    lua = build_autosave_lua(clear_key=None, history_dir=None)

    assert f'"{DEFAULT_HELP_KEY}"' in lua
    assert "nvim_open_win" in lua


def test_build_autosave_lua_omits_help_keymap_when_disabled():
    lua = build_autosave_lua(clear_key=None, history_dir=None, help_key=None)

    assert "vim.keymap.set" not in lua
    assert "nvim_open_win" not in lua


def test_build_autosave_lua_help_only_lists_whats_actually_active():
    """The cheatsheet must reflect real overrides, not just print the
    defaults regardless of what was actually configured for this session."""
    lua_all = build_autosave_lua(history_dir=None)  # clear on, history off
    assert DEFAULT_CLEAR_KEY in lua_all
    assert "browse archived drafts" not in lua_all

    lua_none = build_autosave_lua(clear_key=None, history_dir=None)
    assert "archive current draft" not in lua_none
    assert "browse archived drafts" not in lua_none
    assert f'"{DEFAULT_HELP_KEY}"' in lua_none  # help itself always listed


def test_build_autosave_lua_help_key_is_configurable():
    lua = build_autosave_lua(clear_key=None, history_dir=None, help_key="<F1>")

    assert '"<F1>"' in lua
    assert DEFAULT_HELP_KEY not in lua


def test_build_autosave_lua_registers_fold_on_paste_by_default():
    lua = build_autosave_lua(clear_key=None, history_dir=None, help_key=None)

    assert "vim.paste = function" in lua
    assert f">= {DEFAULT_FOLD_THRESHOLD}" in lua


def test_build_autosave_lua_fold_threshold_is_configurable():
    lua = build_autosave_lua(
        clear_key=None, history_dir=None, help_key=None, fold_threshold=12
    )

    assert ">= 12" in lua
    assert f">= {DEFAULT_FOLD_THRESHOLD}" not in lua


def test_build_autosave_lua_omits_fold_on_paste_when_disabled():
    lua = build_autosave_lua(
        clear_key=None, history_dir=None, help_key=None, fold_threshold=None
    )

    assert "vim.paste" not in lua


def test_build_autosave_lua_omits_fold_on_paste_when_threshold_zero():
    lua = build_autosave_lua(
        clear_key=None, history_dir=None, help_key=None, fold_threshold=0
    )

    assert "vim.paste" not in lua


def test_build_autosave_lua_help_mentions_fold_toggle_when_active():
    lua_on = build_autosave_lua(clear_key=None, history_dir=None)
    assert "za/zo/zc" in lua_on

    lua_off = build_autosave_lua(clear_key=None, history_dir=None, fold_threshold=None)
    assert "za/zo/zc" not in lua_off


def test_build_nvim_command_basic(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file)

    assert argv[0] == "nvim"
    assert str(file) == argv[-1]
    assert "-c" in argv


def test_build_nvim_command_starts_in_insert_mode_by_default(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file)

    assert "startinsert!" in argv
    # File path must still come last regardless of how many -c flags precede it.
    assert argv[-1] == str(file)


def test_build_nvim_command_no_insert_stays_in_normal_mode(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file, insert=False)

    assert "startinsert!" not in argv
    assert "normal! G" not in argv


def test_build_nvim_command_clean_mode_adds_u_none(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file, clean=True)

    assert "-u" in argv
    assert "NONE" in argv
    assert argv.index("-u") < argv.index("NONE")


def test_build_nvim_command_derives_history_dir_from_file(tmp_path):
    file = tmp_path / ".ma" / "prompt" / "current.md"

    argv = build_nvim_command(file)

    assert str(tmp_path / ".ma" / "prompt" / "archive") in " ".join(argv)


def test_build_nvim_command_no_history_key_omits_it(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file, history_key=None)

    assert "vsplit" not in " ".join(argv)


def test_build_nvim_command_no_help_key_omits_it(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file, help_key=None)

    assert "nvim_open_win" not in " ".join(argv)


def test_build_nvim_command_no_fold_paste_omits_it(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file, fold_threshold=None)

    assert "vim.paste" not in " ".join(argv)


def test_build_nvim_command_respects_custom_binary(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file, nvim_bin="/opt/nvim/bin/nvim")

    assert argv[0] == "/opt/nvim/bin/nvim"


def test_build_ui_lua_is_pcall_guarded():
    """A UI API/version mismatch must degrade to a no-op, never abort the
    session start (which shares the same -c as the autosave Lua)."""
    lua = build_ui_lua()

    assert lua.startswith("pcall(function()")


def test_build_ui_lua_prompt_gutter_disables_numbers_and_adds_marker():
    lua = build_ui_lua()

    assert "vim.opt.number = false" in lua
    assert "vim.opt.relativenumber = false" in lua
    assert 'vim.opt.signcolumn = "yes"' in lua
    assert 'sign_text = "> "' in lua
    for event in ("CursorMoved", "CursorMovedI", "TextChanged", "TextChangedI"):
        assert event in lua


def test_build_ui_lua_prompt_gutter_off_leaves_numbers_alone():
    lua = build_ui_lua(prompt_gutter=False)

    assert "vim.opt.number" not in lua
    assert 'sign_text = "> "' not in lua


def test_build_ui_lua_footer_lists_active_keys_by_default():
    lua = build_ui_lua(prompt_gutter=False, trueblack_bg=False)

    assert "vim.opt.laststatus = 3" in lua
    assert "statusline" in lua
    assert "archive & clear" in lua
    assert "browse history" in lua
    assert "za/zo/zc toggle fold" in lua
    assert "help" in lua


def test_build_ui_lua_footer_reflects_key_overrides():
    lua = build_ui_lua(
        prompt_gutter=False,
        trueblack_bg=False,
        clear_key=None,
        history=False,
        help_key="<F1>",
        fold_threshold=0,
    )

    assert "archive & clear" not in lua
    assert "browse history" not in lua
    assert "za/zo/zc" not in lua
    assert '"<F1> help"' in lua or "<F1> help" in lua
    assert DEFAULT_CLEAR_KEY not in lua


def test_build_ui_lua_footer_off_never_touches_statusline():
    lua = build_ui_lua(footer_keymaps=False)

    assert "statusline" not in lua
    assert "laststatus" not in lua


def test_build_ui_lua_trueblack_flattens_background_keeps_fg():
    lua = build_ui_lua(prompt_gutter=False, footer_keymaps=False)

    assert 'vim.opt.background = "dark"' in lua
    assert 'bg = "#000000"' in lua
    assert "if cur.fg then" in lua
    assert "NormalFloat" in lua
    assert "StatusLine" in lua


def test_build_ui_lua_trueblack_off_keeps_colorscheme_background():
    lua = build_ui_lua(trueblack_bg=False)

    assert "#000000" not in lua
    assert 'vim.opt.background' not in lua


def test_build_ui_lua_all_disabled_is_empty():
    lua = build_ui_lua(
        prompt_gutter=False, footer_keymaps=False, trueblack_bg=False
    )

    assert lua == ""


def test_build_nvim_command_layers_ui_lua_after_autosave(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(file)

    joined = " ".join(argv)
    autosave_pos = joined.index("timer:start(")
    ui_pos = joined.index("sign_text = \"> \"")
    assert autosave_pos < ui_pos


def test_build_nvim_command_no_ui_flags_omit_the_visual_layer(tmp_path):
    file = tmp_path / "current.md"

    argv = build_nvim_command(
        file, prompt_gutter=False, footer_keymaps=False, trueblack_bg=False
    )

    joined = " ".join(argv)
    assert "sign_text" not in joined
    assert "statusline" not in joined
    assert "#000000" not in joined
    assert "timer:start(" in joined  # autosave unaffected


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
