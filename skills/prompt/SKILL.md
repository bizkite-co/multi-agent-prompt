---
name: prompt
description: >
  Read the user's composed draft from the multi-agent-prompt scratch file
  (.map/prompt.md, edited via `map` in a split pane) and treat its content as
  their next message. Use when the user types /prompt, says "read my prompt
  file", or otherwise asks you to pick up what they wrote in the scratch file
  instead of typing it into chat.
---

# Prompt (multi-agent-prompt)

The user composes long or crash-risky prompts outside the chat box, in a real
editor in a split pane (`map`, from the `multi-agent-prompt` tool), then hands
the result to you with `/prompt` instead of retyping or pasting it.

## What to do

1. Resolve the scratch file:
   - If the `map` CLI is on `PATH`, run `map show` from the project's working
     directory — it prints the current content (empty string if there's
     nothing there yet).
   - Otherwise, walk up from the current working directory to the nearest
     `.git` root and read `<root>/.map/prompt.md` directly. If neither the
     directory nor file exists, there is simply nothing composed yet.

2. If the content is empty or the file doesn't exist: tell the user there's
   nothing in the scratch file yet — don't invent a request or proceed as if
   they'd asked for something.

3. If it has content: treat the **entire file content** as the user's actual
   next message. Act on it exactly as you would if they had typed or pasted
   it directly into the chat — including any links, pasted command output, or
   code blocks it contains.

4. **Do not delete or clear the file.** The tool's whole purpose is not
   losing composed work; reading it is non-destructive by design. If the user
   wants it cleared after you've picked it up, they'll run `map clear`
   themselves, or ask you to.
