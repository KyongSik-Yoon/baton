#!/bin/sh
# baton mode: while the flag file exists, tell each parent turn that
# it is the orchestrator. No flag means the mode is off — exit silently, one
# stat() per prompt. The enforcement itself lives in orchestrator-guard.sh; this
# injection only explains the posture so the model delegates instead of fighting
# the guard's denials.
FLAG="${HOME}/.claude/baton"
[ -f "$FLAG" ] || exit 0

advisor=$(sed -n 's/^advisor=//p' "$FLAG" | tail -1)
[ -n "$advisor" ] || advisor=fable
parent=$(sed -n 's/^parent=//p' "$FLAG" | tail -1)
[ -n "$parent" ] || parent=opus

if [ "$parent" = "fable" ]; then
  # Fable parent: the orchestrator IS the top judgment tier — design/ambiguity
  # triggers are decided in place, only the independent final review is farmed out.
  if [ "$advisor" = "none" ]; then
    ADV="You are the top judgment tier (parent=fable): decide design, escalation, and ambiguity triggers yourself; route only the final review of high-consequence changes to baton:reviewer-xhigh as an independent pass."
  else
    ADV="You are the top judgment tier (parent=fable): decide design, escalation, and ambiguity triggers yourself. The fable advisor (baton:advisor) is an opt-in fresh-context second opinion — consult it only when independent judgment genuinely adds signal, and keep one alive via SendMessage instead of respawning it."
  fi
elif [ "$advisor" = "none" ]; then
  ADV="The fable advisor is disabled (advisor=none): at advisor triggers, ask the user via AskUserQuestion instead."
else
  ADV="Consult the fable advisor (subagent type baton:advisor) only at the skill's mandatory triggers, and keep one advisor alive across the session via SendMessage instead of respawning it."
fi

cat <<JSON
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "baton mode is ON — you are the orchestrator: a PreToolUse hook blocks your direct file edits and mutating Bash, and caps how much you read into your own context. Decompose the task, delegate implementation to baton:coder-opus48 (complex) or baton:coder-sonnet (standard), send bulk reading to baton:scout for mechanical recon (baton:scout-sonnet when the recon needs interpretation) and keep its summary rather than the files, and review the resulting diffs yourself. ${ADV} Follow the baton skill's rules. If this turn is trivial or conversational, just answer directly without mentioning the orchestrator."
  },
  "suppressOutput": true
}
JSON
