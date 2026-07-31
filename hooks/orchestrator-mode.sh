#!/bin/sh
# opus5-router mode: while the flag file exists, tell each parent turn that
# it is the orchestrator. No flag means the mode is off — exit silently, one
# stat() per prompt. The enforcement itself lives in orchestrator-guard.sh; this
# injection only explains the posture so the model delegates instead of fighting
# the guard's denials.
FLAG="${HOME}/.claude/opus5-router"
[ -f "$FLAG" ] || exit 0

advisor=$(sed -n 's/^advisor=//p' "$FLAG" | tail -1)
[ -n "$advisor" ] || advisor=fable

if [ "$advisor" = "none" ]; then
  ADV="The fable advisor is disabled (advisor=none): at advisor triggers, ask the user via AskUserQuestion instead."
else
  ADV="Consult the fable advisor (subagent type opus-5-router:advisor) only at the skill's mandatory triggers, and keep one advisor alive across the session via SendMessage instead of respawning it."
fi

cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "opus5-router mode is ON — you are the orchestrator: a PreToolUse hook blocks your direct file edits and mutating Bash. Decompose the task, delegate implementation to opus-5-router:coder-opus48 (complex) or opus-5-router:coder-sonnet (standard), use opus-5-router:scout for mechanical read-only recon (opus-5-router:scout-sonnet when the recon needs interpretation), and review the resulting diffs yourself. ${ADV} Follow the opus5-router skill's rules. If this turn is trivial or conversational, just answer directly without mentioning the orchestrator."
  },
  "suppressOutput": true
}
JSON
