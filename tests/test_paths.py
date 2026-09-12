from multi_agent_prompt import paths


def test_find_repo_root_walks_up_to_git(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    nested = repo / "src" / "deep"
    nested.mkdir(parents=True)

    assert paths.find_repo_root(nested) == repo


def test_find_repo_root_falls_back_to_start_when_no_git(tmp_path):
    lonely = tmp_path / "no-repo-here"
    lonely.mkdir()

    assert paths.find_repo_root(lonely) == lonely.resolve()


def test_prompt_file_is_under_ma_prompt_at_repo_root(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    nested = repo / "a" / "b"
    nested.mkdir(parents=True)

    assert paths.prompt_file(nested) == repo / ".ma" / "prompt" / "current.md"


def test_archive_dir_is_under_the_prompt_dir(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    assert paths.archive_dir(repo) == repo / ".ma" / "prompt" / "archive"


def test_ensure_gitignored_creates_gitignore(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    changed = paths.ensure_gitignored(repo)

    assert changed is True
    assert ".ma/prompt/" in (repo / ".gitignore").read_text()


def test_ensure_gitignored_appends_to_existing_gitignore(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".gitignore").write_text("*.pyc\n")

    changed = paths.ensure_gitignored(repo)

    text = (repo / ".gitignore").read_text()
    assert changed is True
    assert "*.pyc" in text
    assert ".ma/prompt/" in text


def test_ensure_gitignored_is_idempotent(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)

    first = paths.ensure_gitignored(repo)
    second = paths.ensure_gitignored(repo)

    assert first is True
    assert second is False
    assert (repo / ".gitignore").read_text().count(".ma/prompt/") == 1


def test_ensure_gitignored_noop_without_git(tmp_path):
    lonely = tmp_path / "no-repo-here"
    lonely.mkdir()

    changed = paths.ensure_gitignored(lonely)

    assert changed is False
    assert not (lonely / ".gitignore").exists()


def test_ensure_gitignored_respects_exact_existing_pattern(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".gitignore").write_text(".ma/prompt\n")

    changed = paths.ensure_gitignored(repo)

    assert changed is False


def test_ensure_gitignored_respects_broader_ma_pattern(tmp_path):
    """A sibling multi-agent-* product (or the user) may already ignore all of `.ma/`."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".gitignore").write_text(".ma/\n")

    changed = paths.ensure_gitignored(repo)

    assert changed is False
    assert ".ma/prompt/" not in (repo / ".gitignore").read_text()
