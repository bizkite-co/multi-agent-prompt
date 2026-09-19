#!/usr/bin/env python3
"""Claude Code UserPromptExpansion hook: stage + pop the multi-agent-prompt
draft when /prompt expands.

Why this event and this ordering: Claude Code expands a slash command's
``@``-include *after* this hook returns (verified empirically — popping the
scratch file here made the include read an empty file). So the hook can't
let the include read ``current.md`` after clearing it. Instead it runs
``map pop --stage``, which archives + clears the scratch file and writes the
popped draft to ``.ma/prompt/handoff.md`` — the file the /prompt command's
``@``-include then splices in. The model only ever sees the draft content.

Everything here is local Python, runs in milliseconds, and is deliberately
silent: no stdout (a hook's stdout can inject context), and every failure is
swallowed with exit 0 — this is housekeeping that must never stall or block
a conversation. Worst case without it: the scratch file isn't reset for the
next /prompt.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys


def _main() -> int:
    data = json.load(sys.stdin)
    if (
        data.get("hook_event_name") != "UserPromptExpansion"
        or data.get("expansion_type") != "slash_command"
        or data.get("command_name") != "prompt"
    ):
        return 0
    cmd = shutil.which("map") or "map"
    try:
        subprocess.run(
            [cmd, "pop", "--stage"],
            cwd=data.get("cwd") or ".",
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(_main())