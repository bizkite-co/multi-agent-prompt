from __future__ import annotations

import argparse
import sys

from multi_agent_prompt import archive, paths
from multi_agent_prompt.editor import (
    DEFAULT_CLEAR_KEY,
    DEFAULT_DEBOUNCE_MS,
    nvim_available,
    open_editor,
)


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
        insert=not args.no_insert,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="map",
        description=(
            "A crash-proof, autosaving prompt editor for AI coding agent CLIs. "
            "Compose in your real Neovim in a split pane; hand off to the chat "
            "with /prompt or @prompt.md."
        ),
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
        "--no-insert",
        action="store_true",
        help="Open in normal mode instead of dropping straight into insert mode",
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

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # Bare `map` == `map edit` with defaults.
        args.command = "edit"
        args.debounce = DEFAULT_DEBOUNCE_MS
        args.nvim_bin = "nvim"
        args.clean = False
        args.clear_key = DEFAULT_CLEAR_KEY
        args.no_clear_key = False
        args.no_insert = False
        args.func = cmd_edit

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
