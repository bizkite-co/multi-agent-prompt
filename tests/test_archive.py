from multi_agent_prompt.archive import (
    DEFAULT_ARCHIVE_KEEP,
    KEEP_ENV_VAR,
    _next_archive_path,
    archive_and_clear,
    prune_archive,
    resolve_archive_keep,
)


def test_archive_and_clear_moves_content_to_archive(tmp_path):
    file = tmp_path / "current.md"
    file.write_text("a carefully composed draft")

    archived_to = archive_and_clear(file)

    assert archived_to is not None
    assert archived_to.read_text() == "a carefully composed draft"
    assert file.read_text() == ""


def test_archive_and_clear_noop_archive_when_file_empty(tmp_path):
    file = tmp_path / "current.md"
    file.write_text("")

    archived_to = archive_and_clear(file)

    assert archived_to is None
    assert not (tmp_path / "archive").exists()


def test_archive_and_clear_noop_archive_when_content_is_only_whitespace(tmp_path):
    file = tmp_path / "current.md"
    file.write_text("   \n\n  ")

    archived_to = archive_and_clear(file)

    assert archived_to is None


def test_archive_and_clear_handles_missing_file(tmp_path):
    file = tmp_path / "current.md"

    archived_to = archive_and_clear(file)

    assert archived_to is None
    assert file.exists()
    assert file.read_text() == ""


def test_archive_and_clear_respects_no_archive_flag(tmp_path):
    file = tmp_path / "current.md"
    file.write_text("contains a secret, don't keep it anywhere")

    archived_to = archive_and_clear(file, archive=False)

    assert archived_to is None
    assert file.read_text() == ""
    assert not (tmp_path / "archive").exists()


def test_archive_and_clear_prunes_to_keep_count(tmp_path):
    file = tmp_path / "current.md"
    for i in range(7):
        file.write_text(f"draft {i}")
        archive_and_clear(file, keep=3)

    remaining = sorted((tmp_path / "archive").glob("*.md"))
    assert len(remaining) == 3
    # The three most recent drafts (4, 5, 6) survive; earlier ones are pruned.
    contents = {p.read_text() for p in remaining}
    assert contents == {"draft 4", "draft 5", "draft 6"}


def test_next_archive_path_avoids_same_second_collisions(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    first = _next_archive_path(tmp_path)
    first.write_text("first")
    second = _next_archive_path(tmp_path)

    assert first != second
    # Simulate the collision actually happening.
    second.write_text("second")
    assert first.read_text() == "first"
    assert second.read_text() == "second"


def test_prune_archive_keep_zero_removes_everything(tmp_path):
    for i in range(3):
        (tmp_path / f"20260101T00000{i}.md").write_text(f"draft {i}")

    removed = prune_archive(tmp_path, keep=0)

    assert len(removed) == 3
    assert list(tmp_path.glob("*.md")) == []


def test_prune_archive_keep_larger_than_existing_removes_nothing(tmp_path):
    (tmp_path / "20260101T000000.md").write_text("only one")

    removed = prune_archive(tmp_path, keep=5)

    assert removed == []
    assert len(list(tmp_path.glob("*.md"))) == 1


def test_prune_archive_missing_directory_is_a_noop(tmp_path):
    missing = tmp_path / "does-not-exist"

    assert prune_archive(missing, keep=5) == []


def test_resolve_archive_keep_cli_override_wins(monkeypatch):
    monkeypatch.setenv(KEEP_ENV_VAR, "9")

    assert resolve_archive_keep(override=2) == 2


def test_resolve_archive_keep_falls_back_to_env_var(monkeypatch):
    monkeypatch.setenv(KEEP_ENV_VAR, "9")

    assert resolve_archive_keep(override=None) == 9


def test_resolve_archive_keep_default_when_nothing_set(monkeypatch):
    monkeypatch.delenv(KEEP_ENV_VAR, raising=False)

    assert resolve_archive_keep(override=None) == DEFAULT_ARCHIVE_KEEP


def test_resolve_archive_keep_ignores_invalid_env_value(monkeypatch):
    monkeypatch.setenv(KEEP_ENV_VAR, "not-a-number")

    assert resolve_archive_keep(override=None) == DEFAULT_ARCHIVE_KEEP
