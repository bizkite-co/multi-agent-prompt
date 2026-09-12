from multi_agent_prompt import cli


def test_cmd_where_prints_resolved_path(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)

    parser = cli.build_parser()
    args = parser.parse_args(["where"])
    rc = args.func(args)

    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == str(repo / ".map" / "prompt.md")


def test_cmd_show_empty_when_file_missing(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)

    parser = cli.build_parser()
    args = parser.parse_args(["show"])
    rc = args.func(args)

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_cmd_show_prints_content(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    (repo / ".map").mkdir()
    (repo / ".map" / "prompt.md").write_text("draft content")

    parser = cli.build_parser()
    args = parser.parse_args(["show"])
    args.func(args)

    assert capsys.readouterr().out == "draft content"


def test_cmd_clear_empties_file(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    (repo / ".map").mkdir()
    target = repo / ".map" / "prompt.md"
    target.write_text("stale draft")

    parser = cli.build_parser()
    args = parser.parse_args(["clear"])
    rc = args.func(args)

    assert rc == 0
    assert target.read_text() == ""


def test_cmd_clear_noop_when_file_missing(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)

    parser = cli.build_parser()
    args = parser.parse_args(["clear"])
    rc = args.func(args)

    assert rc == 0
    assert not (repo / ".map").exists()


def test_edit_errors_cleanly_when_nvim_missing(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)

    parser = cli.build_parser()
    args = parser.parse_args(["edit", "--nvim-bin", "definitely-not-a-real-binary"])
    rc = args.func(args)

    assert rc == 1
    assert "not found on PATH" in capsys.readouterr().err
    # Must not have created .map/ or touched .gitignore on this failure path.
    assert not (repo / ".map").exists()


def test_bare_invocation_defaults_to_edit(monkeypatch):
    parser = cli.build_parser()
    args = parser.parse_args([])

    assert args.command is None  # main() fills this in as "edit"
