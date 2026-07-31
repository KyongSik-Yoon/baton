#!/bin/sh
# fable-router auto mode: while the flag file exists, tell the parent turn to
# route through the skill. No flag means auto mode is off, so exit silently and
# inject nothing — the hook costs one stat() per prompt in that case.
[ -f "${HOME}/.claude/fable-router-auto" ] || exit 0

# Keep this to one line: it is a fixed per-turn cost. The routing policy lives
# in SKILL.md and loads only once the skill runs; SKILL.md also states that this
# injection counts as explicit invocation, so no need to argue it here. The
# bail-out cannot move there — deciding not to route has to precede the load.
cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "fable-router auto mode is ON — route this turn through the fable-router skill. If the turn is trivial or conversational, skip routing and just answer, without mentioning the router."
  },
  "suppressOutput": true
}
JSON
