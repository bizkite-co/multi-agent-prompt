---
name: prompt
description: >
  Read-only fallback for picking up the user's multi-agent-prompt draft
  (.ma/prompt/current.md, composed in a split-pane editor via `map`). Use
  only when the user asks you to read their prompt file or draft directly
  and no /prompt command ran. Never modify, archive, or clear the file.
---

# Prompt (multi-agent-prompt) — read-only fallback

The user composes long or crash-risky prompts outside the chat box, in a
real editor in a split pane (`map`, from the `multi-agent-prompt` tool).
Handing a draft to the chat is normally done by the host itself — a
`/prompt` command that splices the draft into the message locally, plus a
hook that archives and clears the scratch file, all before the model sees
anything. This skill is only the fallback for when that machinery didn't
run and the user asks you to pick the draft up directly.

## What to do

1. Read `<repo-root>/.ma/prompt/current.md` (walk up from the current
   working directory to the nearest `.git` root to find it).

2. If the file is missing or empty: tell the user there's nothing in the
   scratch file yet — don't invent a request or proceed as if they'd asked
   for something.

3. Otherwise: treat the **entire content** as the user's actual next
   message. Act on it exactly as you would if they had typed or pasted it
   directly into the chat — including any links, pasted command output, or
   code blocks it contains.

## What NOT to do

**Never modify, archive, rename, or clear the scratch file, and don't run
`map pop` or any other command against it.** Archiving and clearing are
handled by the user's local tooling at handoff time; an agent doing file
operations here is wasted round trips at best and lost drafts at worst. If
the draft looks stale (it repeats a request you've already handled), say so
and let the user decide.
