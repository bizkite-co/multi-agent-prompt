"""Resolve where a project's scratch prompt file (and its archive) live.

State lives under ``.ma/prompt/`` — ``.ma`` is the shared root directory for
the whole multi-agent-* product line (``map``'s CLI alias is itself the
shared ``ma`` prefix of ``map``/``mar``/``maa``), with each product getting
its own subdirectory so a project never accumulates a `.map/`, `.mar/`,
`.maa/`... pile of top-level dotfolders. Only this tool's own subdirectory
(``.ma/prompt/``) is touched here; task-agent's separate, already-shipped
``.task-agent/`` convention is out of scope for this rename.

Resolution walks up from the start directory to the nearest ``.git`` root
(matching how most agent CLIs and task-agent itself scope their own config),
falling back to the start directory itself when no repo is found.
"""

from __future__ import annotations

from pathlib import Path

MA_DIRNAME = ".ma"
PRODUCT_DIRNAME = "prompt"
PROMPT_FILENAME = "current.md"
ARCHIVE_DIRNAME = "archive"
#: Written by ``map pop --stage``: the just-popped draft, staged for hosts
#: (Claude Code) whose ``@``-include command files can only read a file, not
#: run a command. The host's hook pops *before* the include resolves, so the
#: include sees this file instead of the already-cleared scratch file.
HANDOFF_FILENAME = "handoff.md"

# Anything that already covers `.ma/prompt/` — including a broader existing
# `.ma/` entry a future sibling product's setup might have added — counts as
# "already ignored".
_COVERING_GITIGNORE_LINES = frozenset(
    {
        f"{MA_DIRNAME}/{PRODUCT_DIRNAME}/",
        f"{MA_DIRNAME}/{PRODUCT_DIRNAME}",
        f"/{MA_DIRNAME}/{PRODUCT_DIRNAME}/",
        f"/{MA_DIRNAME}/{PRODUCT_DIRNAME}",
        f"{MA_DIRNAME}/",
        MA_DIRNAME,
        f"/{MA_DIRNAME}/",
        f"/{MA_DIRNAME}",
    }
)
GITIGNORE_PATTERN = f"{MA_DIRNAME}/{PRODUCT_DIRNAME}/"


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
    """The ``.ma/prompt`` directory for the project containing ``start`` (default cwd)."""
    root = find_repo_root(start or Path.cwd())
    return root / MA_DIRNAME / PRODUCT_DIRNAME


def prompt_file(start: Path | None = None) -> Path:
    """The scratch prompt file path for the project containing ``start``."""
    return prompt_dir(start) / PROMPT_FILENAME


def archive_dir(start: Path | None = None) -> Path:
    """Where previously-cleared drafts for this project are kept."""
    return prompt_dir(start) / ARCHIVE_DIRNAME


def handoff_file(start: Path | None = None) -> Path:
    """The staged-handoff file for the project containing ``start``.

    ``map pop --stage`` writes the popped draft here so hosts that splice
    file content into a prompt (``@``-includes) can pick it up after the
    scratch file has already been archived and cleared. Overwritten on
    every staged pop — with the prompt, or with the empty-handoff notice
    when nothing was composed, so it can never serve stale content.
    """
    return prompt_dir(start) / HANDOFF_FILENAME


def ensure_gitignored(start: Path | None = None) -> bool:
    """Append ``.ma/prompt/`` to the project's ``.gitignore`` if not already covered.

    No-ops (returns False) when the project has no ``.git`` directory at all
    (nothing to ignore against), or an existing line already covers it —
    either the exact pattern or a broader ``.ma/`` entry. Returns True when
    it actually modified (or created) ``.gitignore``.
    """
    root = find_repo_root(start or Path.cwd())
    if not (root / ".git").exists():
        return False

    gitignore = root / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    lines = existing.splitlines()

    for line in lines:
        if line.strip() in _COVERING_GITIGNORE_LINES:
            return False

    with gitignore.open("a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(f"{GITIGNORE_PATTERN}\n")
    return True
