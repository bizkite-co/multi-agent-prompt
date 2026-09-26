import json

import pytest

from multi_agent_prompt import cli, hosts


@pytest.fixture(autouse=True)
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MAP_HOSTS_HOME", str(home))
    monkeypatch.setattr(hosts, "on_windows", lambda: False)
    return home


def run(argv, capsys=None):
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    rc = args.func(args)
    if capsys is not None:
        out = capsys.readouterr().out
        return rc, out
    return rc


def test_install_opencode_writes_command_file(fake_home, capsys):
    """opencode needs no hook or JSON — its template's !`map pop` substitution
    does the read+clear+archive at prompt-build time."""
    rc, out = run(["hosts", "install", "--host", "opencode"], capsys)
    assert rc == 0
    target = fake_home / ".config" / "opencode" / "commands" / "prompt.md"
    assert target.read_text() == hosts._payload("commands/opencode/prompt.md")
    assert not (fake_home / ".config" / "opencode" / "hooks").exists()
    assert "wrote" in out


def test_install_claude_writes_files_and_settings(fake_home):
    rc = run(["hosts", "install", "--host", "claude"])
    root = fake_home / ".claude"
    assert rc == 0
    assert (root / "commands" / "prompt.md").read_text() == hosts._payload("commands/claude/prompt.md")
    assert (root / "hooks" / "map-prompt-pop.py").read_text() == hosts._payload("hosts/claude/prompt-pop.py")
    settings = json.loads((root / "settings.json").read_text())
    groups = settings["hooks"]["UserPromptExpansion"]
    assert len(groups) == 1
    hook = groups[0]["hooks"][0]
    assert hook["type"] == "command"
    assert str(root / "hooks" / "map-prompt-pop.py") in hook["command"]


def test_install_agy_writes_skill_and_hooks_json(fake_home):
    rc = run(["hosts", "install", "--host", "agy"])
    root = fake_home / ".gemini" / "config"
    assert rc == 0
    assert (root / "skills" / "prompt" / "SKILL.md").read_text() == hosts._payload("commands/agy/prompt.md")
    assert (root / "hooks" / "map-prompt-pop.py").exists()
    hooks = json.loads((root / "hooks.json").read_text())
    assert "map-prompt-pop" in hooks
    assert hooks["map-prompt-pop"]["PreInvocation"][0]["type"] == "command"


def test_install_grok_writes_command_hook_and_hook_json(fake_home):
    rc = run(["hosts", "install", "--host", "grok"])
    root = fake_home / ".grok"
    assert rc == 0
    assert (root / "commands" / "prompt.md").read_text() == hosts._payload("commands/grok/prompt.md")
    assert (root / "hooks" / "map-prompt-pop.py").exists()
    hook_file = json.loads((root / "hooks" / "map-prompt.json").read_text())
    submit = hook_file["hooks"]["UserPromptSubmit"][0]["hooks"][0]
    assert submit["timeout"] == 15


def test_install_is_idempotent(fake_home, capsys):
    run(["hosts", "install"])
    before = (fake_home / ".claude" / "settings.json").read_text()
    rc, out = run(["hosts", "install"], capsys)
    assert rc == 0
    assert "up to date" in out
    assert "already installed" in out
    assert (fake_home / ".claude" / "settings.json").read_text() == before


def test_install_merges_preserving_user_json_keys(fake_home):
    root = fake_home / ".claude"
    settings = root / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(
        json.dumps({"hooks": {"UserPromptExpansion": [{"hooks": [{"type": "command", "command": "echo mine", "timeout": 5}]}]}, "permissions": {"allow": ["Bash"]}})
    )
    rc = run(["hosts", "install", "--host", "claude"])
    assert rc == 0
    merged = json.loads(settings.read_text())
    cmds = [g["hooks"][0]["command"] for g in merged["hooks"]["UserPromptExpansion"]]
    assert "echo mine" in cmds
    assert merged["permissions"] == {"allow": ["Bash"]}
    assert len(cmds) == 2


def test_install_skips_different_file_without_force(fake_home, capsys):
    root = fake_home / ".claude"
    target = root / "commands" / "prompt.md"
    target.parent.mkdir(parents=True)
    target.write_text("user's own content")
    rc, out = run(["hosts", "install", "--host", "claude"], capsys)
    assert rc == 1
    assert "skip" in out
    assert "use --force" in out
    assert target.read_text() == "user's own content"
    rc = run(["hosts", "install", "--host", "claude", "--force"])
    assert rc == 0
    assert target.read_text() == hosts._payload("commands/claude/prompt.md")


def test_install_leaves_invalid_json_untouched(fake_home, capsys):
    root = fake_home / ".claude"
    settings = root / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{{{ not json")
    rc, out = run(["hosts", "install", "--host", "claude"], capsys)
    assert rc == 1
    assert "left untouched" in out
    assert settings.read_text() == "{{{ not json"


def test_dry_run_writes_nothing(fake_home, capsys):
    rc, out = run(["hosts", "install", "--dry-run"], capsys)
    assert rc == 0
    assert "[dry-run]" in out
    assert not (fake_home / ".claude").exists()
    assert not (fake_home / ".gemini").exists()


def test_uninstall_removes_installed_integration(fake_home):
    run(["hosts", "install"])
    rc = run(["hosts", "uninstall"])
    assert rc == 0
    assert not (fake_home / ".claude" / "commands" / "prompt.md").exists()
    assert not (fake_home / ".claude" / "hooks" / "map-prompt-pop.py").exists()
    assert not (fake_home / ".claude" / "settings.json").exists()
    assert not (fake_home / ".gemini" / "config" / "skills").exists()
    assert not (fake_home / ".grok" / "commands" / "prompt.md").exists()
    assert not (fake_home / ".grok" / "hooks" / "map-prompt.json").exists()


def test_uninstall_keeps_user_hooks_and_keys(fake_home):
    root = fake_home / ".claude"
    settings = root / "settings.json"
    settings.parent.mkdir(parents=True)
    user = {
        "hooks": {"UserPromptExpansion": [{"hooks": [{"type": "command", "command": "echo mine", "timeout": 5}]}]},
        "permissions": {"allow": ["Bash"]},
    }
    settings.write_text(json.dumps(user))
    run(["hosts", "install", "--host", "claude"])
    rc = run(["hosts", "uninstall", "--host", "claude"])
    assert rc == 0
    remaining = json.loads(settings.read_text())
    cmds = [g["hooks"][0]["command"] for g in remaining["hooks"]["UserPromptExpansion"]]
    assert cmds == ["echo mine"]
    assert remaining["permissions"] == {"allow": ["Bash"]}


def test_uninstall_modified_files_need_force(fake_home, capsys):
    run(["hosts", "install", "--host", "grok"])
    root = fake_home / ".grok"
    target = root / "commands" / "prompt.md"
    target.write_text("I tweaked it")
    rc, out = run(["hosts", "uninstall", "--host", "grok"], capsys)
    assert rc == 1
    assert "skip" in out
    assert target.exists()
    rc = run(["hosts", "uninstall", "--host", "grok", "--force"])
    assert rc == 0
    assert not target.exists()


def test_status_reports_states(fake_home, capsys):
    rc, out = run(["hosts", "status"], capsys)
    assert rc == 0
    assert "missing" in out
    run(["hosts", "install"])
    rc, out = run(["hosts", "status"], capsys)
    assert rc == 0
    assert "installed (up to date)" in out
    assert "hook entry installed" in out


def test_host_filter_limits_scope(fake_home):
    run(["hosts", "install", "--host", "claude"])
    assert (fake_home / ".claude" / "settings.json").exists()
    assert not (fake_home / ".gemini").exists()
    assert not (fake_home / ".grok").exists()


def test_unknown_host_rejected_by_argparse(fake_home):
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["hosts", "status", "--host", "ayer"])


def test_hosts_bare_prints_usage(fake_home, capsys):
    rc, out = run(["hosts"], capsys)
    assert rc == 0
    assert "usage:" in out


def test_windows_roots_use_appdata_and_userprofile(tmp_path, monkeypatch, capsys):
    home = tmp_path / "winhome"
    (home / "AppData" / "Roaming").mkdir(parents=True)
    monkeypatch.setenv("MAP_HOSTS_HOME", str(home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(hosts, "on_windows", lambda: True)
    assert hosts.config_root("opencode") == home / "AppData" / "Roaming" / "opencode"
    assert hosts.config_root("claude") == home / ".claude"
    assert hosts.config_root("agy") == home / ".gemini" / "config"
    assert hosts.config_root("grok") == home / ".grok"