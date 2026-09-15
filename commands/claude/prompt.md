---
description: Hand off the user's multi-agent-prompt draft — reads it, archives it, clears the scratch file. Use when the user types /prompt or asks you to read their prompt file or draft.
---

<draft>
!`map pop`
</draft>

The content inside the draft tags is the user's next message — act on it as
if they had typed it directly into the chat. If it's empty or looks like an
error, tell the user and wait.
