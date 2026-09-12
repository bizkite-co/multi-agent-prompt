---
name: prompt
description: >
  Read the user's composed draft from the multi-agent-prompt scratch file
  (.ma/prompt/current.md, edited via `map` in a split pane), archive it, and
  clear it — one operation, via `map pop`. Use when the user types /prompt,
  says "read my prompt file", or otherwise asks you to pick up what they
  wrote in the scratch file instead of typing it into chat.
---

# Prompt (multi-agent-prompt)

The user composes long or crash-risky prompts outside the chat box, in a real
editor in a split pane (`map`, from the `multi-agent-prompt` tool), then hands
the result to you with `/prompt` instead of retyping or pasting it.

## What to do

1. If the `map` CLI is on `PATH`, run `map pop` from the project's working
   directory. This does everything in one step: prints the current draft,
   archives it to the rolling history, and clears the file — so the next
   `/prompt` starts fresh without the user (or you) having to remember a
   separate clear step.

2. If `map` is **not** on `PATH`, fall back to reading
   `<repo-root>/.ma/prompt/current.md` directly (walk up from the current
   working directory to the nearest `.git` root to find it). In this
   fallback path, **do not** clear or archive the file yourself — you can't
   replicate `map`'s archive-then-prune behavior with a plain file write
   without risking losing the draft, so just leave it as-is and mention to
   the user that `map` isn't installed/on PATH.

3. If the output/content is empty: tell the user there's nothing in the
   scratch file yet — don't invent a request or proceed as if they'd asked
   for something.

4. Otherwise: treat the **entire content** as the user's actual next
   message. Act on it exactly as you would if they had typed or pasted it
   directly into the chat — including any links, pasted command output, or
   code blocks it contains.

## Previous drafts

Nothing is ever actually discarded on a normal `/prompt` — `map pop`
archives before it clears, keeping the most recent drafts (10 by default;
`map clear`/`map pop --no-archive` is the explicit opt-out for something
that shouldn't be kept anywhere, like a pasted secret). The user can browse
past drafts from inside the editor with the history keymap (`<leader>ph` by
default) or by listing `.ma/prompt/archive/` directly.
