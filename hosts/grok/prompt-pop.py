#!/usr/bin/env python3
"""Grok UserPromptSubmit hook: stage + pop the map draft when /prompt is sent.

Grok has no host-side content splice (verified empirically: ``!`cmd` `` bodies
are handed to the model as instructions it runs itself, ``@file`` references
are read by the model rather than included, and there is no UserPromptExpansion
or trajectory-injection hook). So the host can't put the draft *into* the
message. Instead this hook runs the pop side while the /prompt command body
(prompt.md) tells the model to read the file this hook stages:

  UserPromptSubmit fires with the RAW prompt text (``"prompt": "/prompt"``)
  and this hook runs ``map pop --stage`` in the workspace root — archiving +
  clearing the scratch file and writing the popped draft (or the
  empty-handoff notice) to ``.ma/prompt/handoff.md``. The model then reads
  that staged file per the command body; it never touches the scratch file,
  archives anything, or runs any command. Pop happens exactly once per
  submit (the hook fires once per UserPromptSubmit).

Silent and fail-open by design: no stdout on allow (a submit hook's stdout is
discarded anyway), every failure swallowed, exit 0. Housekeeping must never
stall a conversation — the worst case is the handoff file isn't staged and
/prompt tells the model there's nothing to act on.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

_PROMPT_RE = re.compile(r"^/prompt\b")


def _main() -> int:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if os.environ.get("GROK_HOOK_EVENT") not in (None, "", "user_prompt_submit"):
        return 0
    prompt = data.get("prompt", "")
    if not _PROMPT_RE.match(prompt):
        return 0
    root = (data.get("workspaceRoot") or data.get("cwd") or ".").rstrip("/\\")
    cmd = shutil.which("map") or "map"
    try:
        subprocess.run(
            [cmd, "pop", "--stage"],
            cwd=root,
            capture_output=True, check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return 0


if __name__ == "__main__":
    sys.exit(_main())