"""Archive-on-clear: never actually lose a draft, just retire it.

Clearing the scratch file — via ``map clear`` or the in-editor keymap — first
copies the current content into a rolling, per-project archive, then prunes
that archive down to the most recent ``keep`` entries (by count, not age:
"keep the last N drafts" is simpler to reason about and configure than a
retention window, and doesn't depend on the clock).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

DEFAULT_ARCHIVE_KEEP = 5
KEEP_ENV_VAR = "MAP_ARCHIVE_KEEP"


def resolve_archive_keep(override: int | None = None) -> int:
    """CLI flag > MAP_ARCHIVE_KEEP env var > default (5)."""
    if override is not None:
        return override
    raw = os.environ.get(KEEP_ENV_VAR)
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_ARCHIVE_KEEP


def _next_archive_path(directory: Path) -> Path:
    """A path in ``directory``, guaranteed to sort after every existing entry.

    The human-readable timestamp prefix is cosmetic; the nanosecond epoch
    suffix is what actually guarantees both uniqueness and correct
    chronological ordering. It must not be a "does this filename already
    exist" counter starting from 0/1/2... — pruning deletes old, *low*
    sequence numbers, so a fresh counter starting from 0 would reuse a freed
    slot for a brand-new file, making a just-created draft sort as the
    *oldest* entry and get immediately pruned by mistake. `time.time_ns()`
    is (for this purpose) always increasing, so a collision is only ever
    possible when the clock genuinely hasn't ticked between two calls —
    handled by incrementing, never by restarting from a fresh, reusable base.
    """
    stamp = time.strftime("%Y%m%dT%H%M%S")
    ns = time.time_ns()
    candidate = directory / f"{stamp}-{ns}.md"
    while candidate.exists():
        ns += 1
        candidate = directory / f"{stamp}-{ns}.md"
    return candidate


def prune_archive(directory: Path, keep: int) -> list[Path]:
    """Delete all but the ``keep`` most recent archived drafts. Returns what was removed."""
    if not directory.is_dir() or keep < 0:
        return []
    files = sorted(directory.glob("*.md"))
    excess = files if keep == 0 else files[:-keep]
    for f in excess:
        f.unlink()
    return excess


def archive_and_clear(
    file: Path,
    keep: int = DEFAULT_ARCHIVE_KEEP,
    archive: bool = True,
) -> Path | None:
    """Archive ``file``'s current content (unless empty or ``archive=False``), then truncate it.

    Returns the path it archived to, or None if there was nothing to archive
    (empty/missing file, or ``archive=False``).
    """
    content = file.read_text(encoding="utf-8") if file.exists() else ""
    archived_to = None

    if archive and content.strip():
        adir = file.parent / "archive"
        adir.mkdir(parents=True, exist_ok=True)
        archived_to = _next_archive_path(adir)
        archived_to.write_text(content, encoding="utf-8")
        prune_archive(adir, keep)

    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("", encoding="utf-8")
    return archived_to
