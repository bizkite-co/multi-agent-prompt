from multi_agent_prompt import cli
from multi_agent_prompt.archive import KEEP_ENV_VAR


def test_cmd_where_prints_resolved_path(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)

    parser = cli.build_parser()
    args = parser.parse_args(["where"])
    rc = args.func(args)

    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert out == str(repo / ".ma" / "prompt" / "current.md")


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
    (repo / ".ma" / "prompt").mkdir(parents=True)
    (repo / ".ma" / "prompt" / "current.md").write_text("draft content")

    parser = cli.build_parser()
    args = parser.parse_args(["show"])
    args.func(args)

    assert capsys.readouterr().out == "draft content"


def test_cmd_clear_empties_file(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    (repo / ".ma" / "prompt").mkdir(parents=True)
    target = repo / ".ma" / "prompt" / "current.md"
    target.write_text("stale draft")

    parser = cli.build_parser()
    args = parser.parse_args(["clear"])
    rc = args.func(args)

    assert rc == 0
    assert target.read_text() == ""


def test_cmd_clear_archives_the_previous_draft(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    (repo / ".ma" / "prompt").mkdir(parents=True)
    target = repo / ".ma" / "prompt" / "current.md"
    target.write_text("stale draft")

    parser = cli.build_parser()
    args = parser.parse_args(["clear"])
    args.func(args)

    archived = list((repo / ".ma" / "prompt" / "archive").glob("*.md"))
    assert len(archived) == 1
    assert archived[0].read_text() == "stale draft"
    assert "Archived previous draft" in capsys.readouterr().err


def test_cmd_clear_no_archive_flag_discards_content(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    (repo / ".ma" / "prompt").mkdir(parents=True)
    target = repo / ".ma" / "prompt" / "current.md"
    target.write_text("contained a secret")

    parser = cli.build_parser()
    args = parser.parse_args(["clear", "--no-archive"])
    args.func(args)

    assert target.read_text() == ""
    assert not (repo / ".ma" / "prompt" / "archive").exists()


def test_cmd_clear_keep_flag_overrides_env_var(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)
    monkeypatch.setenv(KEEP_ENV_VAR, "99")
    prompt_dir = repo / ".ma" / "prompt"
    prompt_dir.mkdir(parents=True)
    target = prompt_dir / "current.md"

    parser = cli.build_parser()
    for i in range(4):
        target.write_text(f"draft {i}")
        args = parser.parse_args(["clear", "--keep", "1"])
        args.func(args)

    assert len(list((prompt_dir / "archive").glob("*.md"))) == 1


def test_cmd_clear_noop_when_file_missing(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)

    parser = cli.build_parser()
    args = parser.parse_args(["clear"])
    rc = args.func(args)

    assert rc == 0
    assert (repo / ".ma" / "prompt" / "current.md").read_text() == ""
    assert not (repo / ".ma" / "prompt" / "archive").exists()


def test_edit_errors_cleanly_when_nvim_missing(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    monkeypatch.chdir(repo)

    parser = cli.build_parser()
    args = parser.parse_args(["edit", "--nvim-bin", "definitely-not-a-real-binary"])
    rc = args.func(args)

    assert rc == 1
    assert "not found on PATH" in capsys.readouterr().err
    # Must not have created .ma/ or touched .gitignore on this failure path.
    assert not (repo / ".ma").exists()


def test_bare_invocation_defaults_to_edit(monkeypatch):
    parser = cli.build_parser()
    args = parser.parse_args([])

    assert args.command is None  # main() fills this in as "edit"
