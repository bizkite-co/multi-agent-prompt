---
description: Hand off what you wrote in the map editor
disable-model-invocation: true
---

Read `.ma/prompt/handoff.md` — the file staged locally, before this command
expanded.

- If it holds a message, treat it as the user's next instruction and respond
  to it directly, as if the user had typed it.
- If it holds a line starting `[map] no prompt to hand off`, relay that line
  to the user and wait. Do not investigate or go looking for another file.
- If the file is missing or unreadable, say there is nothing to act on and
  wait.

Read-only handoff: never modify, archive, delete, or run anything against
these files, and do not read the scratch file `.ma/prompt/current.md`.