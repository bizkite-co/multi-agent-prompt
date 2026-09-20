from __future__ import annotations

import argparse
import subprocess
import sys

import verkit
from rich.console import Console

from multi_agent_prompt import archive, paths
from multi_agent_prompt.editor import (
    DEFAULT_CLEAR_KEY,
    DEFAULT_DEBOUNCE_MS,
    DEFAULT_FOLD_THRESHOLD,
    DEFAULT_HELP_KEY,
    DEFAULT_HISTORY_KEY,
    nvim_available,
    open_editor,
)

PACKAGE_NAME = "multi-agent-prompt"


def cmd_edit(args: argparse.Namespace) -> int:
    file = paths.prompt_file()
    if not nvim_available(args.nvim_bin):
        print(
            f"error: '{args.nvim_bin}' not found on PATH. "
            "multi-agent-prompt's autosave relies on Neovim's Lua API "
            "(https://neovim.io/) — plain Vim isn't supported.",
            file=sys.stderr,
        )
        return 1

    if paths.ensure_gitignored():
        print(f"Added {paths.GITIGNORE_PATTERN} to .gitignore", file=sys.stderr)

    return open_editor(
        file,
        debounce_ms=args.debounce,
        nvim_bin=args.nvim_bin,
        clean=args.clean,
        clear_key=None if args.no_clear_key else args.clear_key,
        history_key=None if args.no_history_key else args.history_key,
        help_key=None if args.no_help_key else args.help_key,
        fold_threshold=None if args.no_fold_paste else args.fold_threshold,
        insert=not args.no_insert,
        prompt_gutter=not args.no_prompt_gutter,
        footer_keymaps=not args.no_footer,
        trueblack_bg=not args.no_trueblack,
    )


def cmd_where(args: argparse.Namespace) -> int:
    print(paths.prompt_file())
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    file = paths.prompt_file()
    if not file.exists():
        return 0
    sys.stdout.write(file.read_text(encoding="utf-8"))
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    file = paths.prompt_file()
    keep = archive.resolve_archive_keep(args.keep)
    archived_to = archive.archive_and_clear(file, keep=keep, archive=not args.no_archive)

    if archived_to is not None:
        print(f"Archived previous draft to {archived_to}", file=sys.stderr)
    print(f"Cleared {file}", file=sys.stderr)
    return 0


#: The entire user-visible message when /prompt runs with nothing drafted —
#: printed by `map pop` (and staged by `--stage`) so the host templates need
#: no framing or guard verbiage around the draft at all: a handoff message
#: is the draft verbatim, and this notice is the "empty draft" case. The
#: final clause matters: without it some models treat the notice as a
#: problem to investigate (reading files, chasing the tool) instead of a
#: dead end to report.
EMPTY_HANDOFF_NOTICE = (
    "[map] no draft to hand off — .ma/prompt/current.md is empty. "
    "Nothing to act on; say so and wait."
)


def cmd_pop(args: argparse.Namespace) -> int:
    """Read the draft, archive it, clear the file, and print what was read — one operation.

    This is what `/prompt` uses: hand the draft off and reset for the next
    one in a single step, so there's no separate "now go clear it" the user
    has to remember to do. What the model receives is the draft verbatim —
    or, when nothing was drafted, ``EMPTY_HANDOFF_NOTICE``.
    """
    file = paths.prompt_file()
    content = file.read_text(encoding="utf-8") if file.exists() else ""
    keep = archive.resolve_archive_keep(args.keep)
    archive.archive_and_clear(file, keep=keep, archive=not args.no_archive)
    out = content if content.strip() else EMPTY_HANDOFF_NOTICE
    if args.stage:
        # Hosts whose /prompt splices file content via an ``@``-include
        # (Claude Code) pop through a hook *before* the include resolves,
        # so the include must read this staged copy, not the scratch file.
        handoff = paths.handoff_file()
        handoff.parent.mkdir(parents=True, exist_ok=True)
        handoff.write_text(out, encoding="utf-8")
    sys.stdout.write(out)
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    """Show version, promote it, tag it, or run a full release — via verkit.

    Mirrors task-agent's `ta version` surface (verkit is the shared
    version-management library across this developer's projects): bare
    `map version` shows installed vs. latest-on-PyPI; `promote` bumps
    semver and commits; `tag` tags HEAD from the committed version and
    pushes; `release` does both atomically.
    """
    console = Console()
    verkit.display_version_info(console, PACKAGE_NAME, upgrade_cmd="map self-up")

    try:
        if args.version_command == "release":
            new_v = verkit.promote_version(args.part, console=console)
            console.print(f"[blue]Release {new_v}: tagging and pushing...[/blue]")
            verkit.tag_version(console=console, push=args.push, push_branch=args.push_branch)
            console.print(f"[bold green]Release v{new_v} complete.[/bold green]")
        elif args.version_command == "promote":
            new_v = verkit.promote_version(args.part, console=console)
            console.print(
                "[dim]Next: map version tag[/dim]  "
                "[dim](or use map version release for one-shot)[/dim]"
            )
            console.print(f"[dim]HEAD is now v{new_v}; tag when ready to publish.[/dim]")
        elif args.version_command == "tag":
            verkit.tag_version(console=console, push=args.push, push_branch=args.push_branch)
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 - deliberate top-level boundary for verkit's git/subprocess errors
        console.print(f"[red]Error during version operation: {e}[/red]")
        return 1

    return 0


def cmd_self_up(_args: argparse.Namespace) -> int:
    """Upgrade the installed `map` tool to the latest PyPI release via uv.

    Mirrors task-agent's `ta self-up`: `map` ships as a uv tool, so this is
    just `uv tool upgrade multi-agent-prompt` — no source checkout needed.
    """
    console = Console()
    console.print("[blue]Upgrading multi-agent-prompt via uv...[/blue]")
    try:
        subprocess.run(["uv", "tool", "upgrade", PACKAGE_NAME], check=True)
        console.print("[bold green]Successfully upgraded multi-agent-prompt.[/bold green]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error upgrading multi-agent-prompt: {e}[/red]")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="map",
        description=(
            "A crash-proof, autosaving prompt editor for AI coding agent CLIs. "
            "Compose in your real Neovim in a split pane; hand off to the chat "
            "with /prompt or @prompt.md."
        ),
    )
    parser.add_argument(
        "-V", "--version", action="store_true", help="Show version and exit"
    )
    subparsers = parser.add_subparsers(dest="command")

    edit_parser = subparsers.add_parser(
        "edit", help="Open the project's scratch prompt file (default command)"
    )
    edit_parser.add_argument(
        "--debounce",
        type=int,
        default=DEFAULT_DEBOUNCE_MS,
        help=f"Autosave debounce in milliseconds (default: {DEFAULT_DEBOUNCE_MS})",
    )
    edit_parser.add_argument(
        "--nvim-bin",
        default="nvim",
        help="Neovim binary to launch (default: nvim)",
    )
    edit_parser.add_argument(
        "--clean",
        action="store_true",
        help="Skip the user's init.lua entirely (-u NONE) for faster startup",
    )
    edit_parser.add_argument(
        "--clear-key",
        default=DEFAULT_CLEAR_KEY,
        help=f"Buffer-local normal-mode keymap that archives and clears (default: {DEFAULT_CLEAR_KEY})",
    )
    edit_parser.add_argument(
        "--no-clear-key",
        action="store_true",
        help="Don't register the in-editor clear keymap at all",
    )
    edit_parser.add_argument(
        "--history-key",
        default=DEFAULT_HISTORY_KEY,
        help=(
            "Buffer-local normal-mode keymap that opens the archive directory "
            f"(read-only) in a split (default: {DEFAULT_HISTORY_KEY})"
        ),
    )
    edit_parser.add_argument(
        "--no-history-key",
        action="store_true",
        help="Don't register the in-editor archive-browsing keymap at all",
    )
    edit_parser.add_argument(
        "--help-key",
        default=DEFAULT_HELP_KEY,
        help=(
            "Buffer-local normal-mode keymap that shows a cheatsheet of "
            f"whichever keymaps are active (default: {DEFAULT_HELP_KEY})"
        ),
    )
    edit_parser.add_argument(
        "--no-help-key",
        action="store_true",
        help="Don't register the in-editor help keymap at all",
    )
    edit_parser.add_argument(
        "--fold-threshold",
        type=int,
        default=DEFAULT_FOLD_THRESHOLD,
        help=(
            "Auto-fold a paste of this many lines or more, closed by default "
            f"(za/zo/zc to toggle) (default: {DEFAULT_FOLD_THRESHOLD})"
        ),
    )
    edit_parser.add_argument(
        "--no-fold-paste",
        action="store_true",
        help="Don't auto-fold large pastes at all",
    )
    edit_parser.add_argument(
        "--no-insert",
        action="store_true",
        help="Open in normal mode instead of dropping straight into insert mode",
    )
    edit_parser.add_argument(
        "--no-prompt-gutter",
        action="store_true",
        help="Keep line numbers / the regular gutter instead of a cursor-tracking '> ' prompt marker",
    )
    edit_parser.add_argument(
        "--no-footer",
        action="store_true",
        help="Don't show an active-keymap footer in the statusline",
    )
    edit_parser.add_argument(
        "--no-trueblack",
        action="store_true",
        help="Don't force a #000000 background (keep the colorscheme's own background)",
    )
    edit_parser.set_defaults(func=cmd_edit)

    where_parser = subparsers.add_parser(
        "where", help="Print the resolved scratch prompt file path"
    )
    where_parser.set_defaults(func=cmd_where)

    show_parser = subparsers.add_parser(
        "show", help="Print the scratch prompt file's current content"
    )
    show_parser.set_defaults(func=cmd_show)

    pop_parser = subparsers.add_parser(
        "pop",
        help="Print the current draft, archive it, and clear the file — one operation",
    )
    pop_parser.add_argument(
        "--keep",
        type=int,
        default=None,
        help=(
            f"How many archived drafts to retain (default: {archive.DEFAULT_ARCHIVE_KEEP}, "
            f"or ${archive.KEEP_ENV_VAR})"
        ),
    )
    pop_parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Discard the draft instead of archiving it (e.g. it contained a secret)",
    )
    pop_parser.add_argument(
        "--stage",
        action="store_true",
        help=(
            "Also write the popped draft to .ma/prompt/handoff.md — the staged "
            "copy a host's @-include reads when /prompt pops via a pre-expansion "
            "hook (Claude Code)"
        ),
    )
    pop_parser.set_defaults(func=cmd_pop)

    clear_parser = subparsers.add_parser(
        "clear", help="Archive the current draft, then empty the scratch prompt file"
    )
    clear_parser.add_argument(
        "--keep",
        type=int,
        default=None,
        help=(
            f"How many archived drafts to retain (default: {archive.DEFAULT_ARCHIVE_KEEP}, "
            f"or ${archive.KEEP_ENV_VAR})"
        ),
    )
    clear_parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Discard the current draft instead of archiving it first (e.g. it contained a secret)",
    )
    clear_parser.set_defaults(func=cmd_clear)

    up_parser = subparsers.add_parser(
        "self-up", help="Upgrade the installed `map` tool to the latest PyPI release via uv"
    )
    up_parser.set_defaults(func=cmd_self_up)

    version_parser = subparsers.add_parser(
        "version", help="Show version, promote, tag, or run a full release"
    )
    v_sub = version_parser.add_subparsers(dest="version_command")
    promote_parser = v_sub.add_parser(
        "promote",
        help=(
            "Bump semver and commit it (amends only if HEAD is unpushed/untagged; "
            "otherwise creates chore(release): vX.Y.Z)"
        ),
    )
    promote_parser.add_argument("part", choices=["major", "minor", "patch"])
    version_tag_parser = v_sub.add_parser(
        "tag",
        help="Tag HEAD as vX.Y.Z from committed version; push branch then tag",
    )
    version_tag_parser.add_argument(
        "--no-push",
        dest="push",
        action="store_false",
        help="Create the local tag only (do not push branch or tag)",
    )
    version_tag_parser.add_argument(
        "--no-push-branch",
        dest="push_branch",
        action="store_false",
        help="When pushing, push only the tag (not the branch)",
    )
    version_tag_parser.set_defaults(push=True, push_branch=True)
    version_release_parser = v_sub.add_parser(
        "release", help="Atomic promote + tag + push branch + push tag"
    )
    version_release_parser.add_argument("part", choices=["major", "minor", "patch"])
    version_release_parser.add_argument(
        "--no-push",
        dest="push",
        action="store_false",
        help="Promote and tag locally only",
    )
    version_release_parser.set_defaults(push=True, push_branch=True)
    version_parser.set_defaults(func=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        verkit.display_version_info(Console(), PACKAGE_NAME, upgrade_cmd="map self-up")
        sys.exit(0)

    if args.command is None:
        # Bare `map` == `map edit` with defaults.
        args.command = "edit"
        args.debounce = DEFAULT_DEBOUNCE_MS
        args.nvim_bin = "nvim"
        args.clean = False
        args.clear_key = DEFAULT_CLEAR_KEY
        args.no_clear_key = False
        args.history_key = DEFAULT_HISTORY_KEY
        args.no_history_key = False
        args.help_key = DEFAULT_HELP_KEY
        args.no_help_key = False
        args.fold_threshold = DEFAULT_FOLD_THRESHOLD
        args.no_fold_paste = False
        args.no_insert = False
        args.no_prompt_gutter = False
        args.no_footer = False
        args.no_trueblack = False
        args.func = cmd_edit

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
