#!/usr/bin/env python3
"""Antigravity CLI (agy) PreInvocation hook: hand off the multi-agent-prompt
draft when /prompt is invoked.

agy has no client-side include or substitution for skill bodies — a slash-
invoked skill's body is delivered to the model as instructions to follow
(verified: an ``@file`` reference in the body lands as literal text the
model tries to read). So the handoff happens entirely in this hook, before
the model is called: when the newest user step is the /prompt invocation,
``map pop`` runs locally (archive + clear, Python on this machine) and the
popped prompt is injected as the user's next message via ``injectSteps``.
The model only ever sees the prompt as a plain user message — never a
file, a command, or a file-operation instruction.

PreInvocation fires before every model call, so two guards keep it exact:
- Act only when the *last* user step is the literal /prompt request.
- Remember, per conversation, which /prompt step was already handled, so
  follow-up invocations in the same turn never pop or inject twice (a
  second pop would read empty and inject the "nothing to hand off" notice
  into the middle of the turn).

Every failure is swallowed and answered with ``{}`` — this is housekeeping
and must never stall or block a conversation. Without it the worst case is
/prompt behaving like an empty skill.

cwd resolution for the pop: agy runs hooks from its config directory, so
the workspace comes from the hook payload's ``workspacePaths`` (the
directories the session was launched with); ``MAP_POP_CWD`` overrides it
for testing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_MARKER = "/prompt"
_STATE_PATH = Path.home() / ".cache" / "multi-agent-prompt" / "agy-pop-state.json"
_STATE_MAX_CONVERSATIONS = 100


def _last_user_step(transcript_path: str) -> tuple[object, bool] | None:
    """(step_index, is_prompt) for the newest USER_INPUT step, or None.

    Reads only the transcript tail; partial or unparseable trailing lines
    (the file is being appended to live) are ignored.
    """
    try:
        with open(transcript_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 65536))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return None
    last: tuple[object, bool] | None = None
    for line in tail.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            step = json.loads(line)
        except ValueError:
            continue
        if step.get("type") != "USER_INPUT":
            continue
        content = step.get("content") or ""
        request = ""
        if content.startswith("<USER_REQUEST>"):
            end = content.find("</USER_REQUEST>")
            inner = content[len("<USER_REQUEST>") :] if end == -1 else content[len("<USER_REQUEST>") : end]
            request = inner.strip()
        last = (step.get("step_index"), request == _MARKER)
    return last


def _handled(conversation_id: str) -> object:
    try:
        return json.loads(_STATE_PATH.read_text()).get(conversation_id)
    except (OSError, ValueError):
        return None


def _record_handled(conversation_id: str, step_index: object) -> None:
    try:
        state = json.loads(_STATE_PATH.read_text())
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    state[conversation_id] = step_index
    while len(state) > _STATE_MAX_CONVERSATIONS:  # dicts keep insertion order
        state.pop(next(iter(state)))
    try:
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(state))
    except OSError:
        pass


def _pop_cwd(payload: dict) -> str | None:
    override = os.environ.get("MAP_POP_CWD")
    if override:
        return override
    for path in payload.get("workspacePaths") or []:
        if Path(path).is_dir():
            return path
    return None


def _main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        print("{}")
        return 0

    transcript_path = payload.get("transcriptPath")
    conversation_id = payload.get("conversationId")
    if not transcript_path or not conversation_id:
        print("{}")
        return 0

    last = _last_user_step(transcript_path)
    if not last or not last[1]:
        print("{}")
        return 0
    step_index, _ = last
    if _handled(conversation_id) == step_index:
        print("{}")
        return 0

    cwd = _pop_cwd(payload)
    if not cwd:
        print("{}")
        return 0
    cmd = shutil.which("map") or "map"
    try:
        result = subprocess.run(
            [cmd, "pop"], cwd=cwd, capture_output=True, check=False, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError, ValueError):
        print("{}")  # no state recorded: a later invocation may retry
        return 0

    _record_handled(conversation_id, step_index)
    print(json.dumps({"injectSteps": [{"userMessage": result.stdout}]}))
    return 0


if __name__ == "__main__":
    sys.exit(_main())