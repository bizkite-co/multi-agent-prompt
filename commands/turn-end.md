# Turn-end hooks — agent done, question, or report

`/prompt` is the *input* side of the agent loop (compose → hand off). This
documents the *output* side: the hook surface each host exposes when a turn
finishes, errs, or needs attention from the user. **Available surface,
documented for future work — nothing here is implemented by `map` yet.**
Schemas below are from the hosts' official hook references, with the
load-bearing fields called out.

Two properties make this surface attractive: it runs entirely **outside
the model's view** (after or beside the turn), so there is no leak risk of
the kind the input side had to engineer away; and every host has it.

## Claude Code

### `Stop` — the agent finished responding

Fires when the main agent finishes a turn. Does not fire on user
interrupt; API errors go to `StopFailure` instead. No matcher.

Input (beyond the common fields): `stop_hook_active` (true when Claude is
already continuing because of a stop hook — check it to avoid loops;
Claude force-ends the turn after 8 consecutive blocks), **`last_assistant_message`**
(the turn's final text — use this, not `transcript_path`, which is written
asynchronously and may lag the turn), `background_tasks` (in-flight
shell/subagent/monitor/workflow/teammate tasks), `session_crons`.

Decision control:

```json
{ "decision": "block", "reason": "run the test suite before finishing" }
```

prevents the stop and feeds the reason to Claude (the quality-gate
pattern). `{"hookSpecificOutput": {"hookEventName": "Stop",
"additionalContext": "..."}}` is the non-error variant — feedback shown as
hook context rather than a hook error. Exit code 2 behaves like `block`
with stderr as the reason.

### `StopFailure` — the turn died on an API error

Fires instead of `Stop`. `error` matcher values: `rate_limit`,
`overloaded`, `authentication_failed`, `account_on_hold`, `billing_error`,
`invalid_request`, `model_not_found`, `server_error`,
`max_output_tokens`, `cloud_credential_error`, `unknown`. Note
`last_assistant_message` here holds the *error string* ("API Error: Rate
limit reached"), not conversational output. **No decision control** —
alerting/logging only.

### `Notification` — the typed attention signal

The richest "question vs report" signal of any host. Matcher /
`notification_type` values include **`agent_needs_input`** (question
waiting for the user) and **`agent_completed`** (turn produced a report),
plus `permission_prompt`, `idle_prompt`, `auth_success`, `elicitation_*`,
and `quota_auto_resume_*`. Input: `message`, `title`,
`notification_type`. Hooks **cannot block or modify** the notification —
side effects only (forwarding, terminal sequences). The built-in
`inputNeededNotifEnabled` / `agentPushNotifEnabled` settings already
consume these events as desktop notifications.

### Scoped variants

`SubagentStop` (per subagent; has `last_assistant_message` and the
subagent's own transcript path), `TaskCompleted` (exit 2 un-marks the task
and feeds stderr back to the model), `TeammateIdle` (exit 2 keeps the
teammate working; `{"continue": false, "stopReason": ...}` stops it),
`SessionEnd` (cleanup only — `clear`/`resume`/`logout`/`prompt_input_exit`/
`other`; ~1.5s shared budget).

## Antigravity CLI (`agy`)

### `Stop` — the execution loop terminates

Input: `executionNum`, `terminationReason` (`model_stop`,
`max_steps_exceeded`, `error`), `error`, **`fullyIdle`** (false while
background tasks are still running — the difference between "done" and
"done for now").

Decision control:

```json
{ "decision": "continue", "reason": "not done yet" }
```

re-enters the loop with the reason injected as a system message; any other
value (or none) allows the stop. There is no built-in loop cap like
Claude's 8-block guard — a `continue`-ing hook must count its own
`executionNum`s.

### `PostInvocation`

Fires after each model call completes; same `injectSteps` output as
`PreInvocation` (which the [agy handoff](./agy/README.md) uses).

### No typed attention event

agy has no `Notification` equivalent — a question for the user is just the
turn's final output. A done-hook that wants the report/question text reads
the last `PLANNER_RESPONSE` from the transcript path in the payload
(agy's transcript *is* current at Stop, unlike Claude's).

## OpenCode (plugins, not hooks)

OpenCode's equivalent surface is plugin events
(`~/.config/opencode/plugins/`):

- **`session.idle`** — the response is complete; the docs' own
  notification example keys off this event.
- **`permission.asked` / `permission.replied`** — the permission-prompt
  lifecycle (a form of "needs input").
- `session.error`, `session.status`, `session.updated`; and
  `message.part.updated` for streaming-granular needs.

## Candidate uses (options, none built)

- **Attention ping**: Claude's typed `Notification`
  (`agent_needs_input` vs `agent_completed`) is the richest signal; agy
  needs a `Stop` hook reading the transcript tail; opencode a
  `session.idle` plugin. Portable floor is a terminal bell or tmux
  `display-message`; `notify-send` needs a desktop daemon, absent in
  headless/SSH sessions.
- **Auto-open the next draft**: on "done with a question", open a fresh
  `map` draft (optionally pre-seeded with the question) — closes the
  compose → handoff loop.
- **Route the report**: both `Stop` variants expose the final message
  (`last_assistant_message` / transcript tail) — it could be archived to a
  file, docs, or the task-agent inbox.
- **Quality gate**: Claude `Stop` `decision: "block"` and agy `Stop`
  `decision: "continue"` both force continuation ("actually finish the
  task before ending the turn"). Both can loop — Claude has the
  `stop_hook_active` + 8-block guardrail; agy needs a hand-rolled counter.

The same [restart semantics](./decisions.md#restart-semantics) as the
input side apply: hook configs and plugins load at startup.
