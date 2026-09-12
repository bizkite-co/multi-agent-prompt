"""Resolve where a project's scratch prompt file lives.

The prompt file is stored per-project so a Windows Terminal / tmux / any
other split pane opened in the same working directory as the agent chat
naturally lands on the same file. Resolution walks up from the start
directory to the nearest ``.git`` root (matching how most agent CLIs and
task-agent itself scope their own config), falling back to the start
directory itself when no repo is found.
"""

from __future__ import annotations

from pathlib import Path

PROMPT_DIRNAME = ".map"
PROMPT_FILENAME = "prompt.md"
GITIGNORE_PATTERN = f"{PROMPT_DIRNAME}/"


def find_repo_root(start: Path) -> Path:
    """Walk up from ``start`` to the nearest directory containing ``.git``.

    Returns ``start`` (resolved) if no ``.git`` is found before the
    filesystem root.
    """
    current = start.resolve()
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return start.resolve()
        current = parent


def prompt_dir(start: Path | None = None) -> Path:
    """The ``.map`` directory for the project containing ``start`` (default cwd)."""
    root = find_repo_root(start or Path.cwd())
    return root / PROMPT_DIRNAME


def prompt_file(start: Path | None = None) -> Path:
    """The scratch prompt file path for the project containing ``start``."""
    return prompt_dir(start) / PROMPT_FILENAME


def ensure_gitignored(start: Path | None = None) -> bool:
    """Append ``.map/`` to the project's ``.gitignore`` if not already present.

    No-ops (returns False) when the project has no ``.git`` directory at all
    (nothing to ignore against) or the pattern is already covered. Returns
    True when it actually modified (or created) ``.gitignore``.
    """
    root = find_repo_root(start or Path.cwd())
    if not (root / ".git").exists():
        return False

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    lines = existing.splitlines()

    for line in lines:
        stripped = line.strip()
        if stripped in (GITIGNORE_PATTERN, PROMPT_DIRNAME, f"/{PROMPT_DIRNAME}", f"/{GITIGNORE_PATTERN}"):
            return False

    with gitignore.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(f"{GITIGNORE_PATTERN}\n")
    return True
