#!/bin/sh
# opus5-router: while the flag file exists, the MAIN agent must not mutate
# anything — it thinks, reviews, and delegates. Subagent tool calls pass through
# untouched: their hook input carries agent_id, the main agent's never does.
FLAG="${HOME}/.claude/opus5-router"
[ -f "$FLAG" ] || exit 0

input=$(cat)

case "$input" in
  *'"agent_id"'*) exit 0 ;;
esac

deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$1"
  exit 0
}

tool=$(printf '%s' "$input" | sed -n 's/.*"tool_name" *: *"\([^"]*\)".*/\1/p')

case "$tool" in
  Write|Edit|NotebookEdit)
    deny "orchestrator mode: direct edits are disabled for the main agent. Delegate this change to a worker subagent (coder-sonnet for standard work, coder-opus48 for complex work)."
    ;;
  Bash)
    ;;
  *)
    exit 0
    ;;
esac

# Bash needs real command analysis; the Python filter owns that policy.
filter="$(dirname "$0")/orchestrator-bash-filter.py"
if command -v python3 >/dev/null 2>&1 && [ -f "$filter" ]; then
  printf '%s' "$input" | python3 "$filter"
  exit 0
fi

# No python3: conservative fallback. Allow only a metacharacter-free command
# whose first word is plainly read-only; everything else is delegated.
cmd=$(printf '%s' "$input" | sed -n 's/.*"command" *: *"\(.*\)".*/\1/p')
case "$cmd" in
  *[\;\&\|\>\<\`\$]*)
    deny "orchestrator mode: compound or redirecting Bash is blocked for the main agent. Delegate it to a worker subagent." ;;
esac
case "$cmd" in
  git\ status*|git\ diff*|git\ log*|git\ show*|git\ blame*|git\ branch|git\ remote\ -v*) exit 0 ;;
  git*) deny "orchestrator mode: only read-only git is allowed for the main agent. Delegate this to a worker subagent." ;;
esac
first=${cmd%% *}
case "$first" in
  ls|tree|pwd|wc|du|df|file|stat|head|tail|cat|grep|rg|find|which|date|diff) exit 0 ;;
esac
deny "orchestrator mode: Bash for the main agent is limited to read-only inspection. Delegate this command to a worker subagent."
