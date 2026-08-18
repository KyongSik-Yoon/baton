#!/bin/sh
# baton style injection: while the flag file carries `style=on`, inject a
# per-model communication-style prompt into the session. It fires only for
# models that ship a matching styles/<model-id>.md file, so an unstyled model
# sees nothing. One script serves both SessionStart and SubagentStart — the
# hookEventName is echoed back from stdin. Any of: no flag file, no `style=on`
# line, no model in the input, or no matching style file -> exit 0 silently.
FLAG="${HOME}/.claude/baton"
[ -f "$FLAG" ] || exit 0

style=$(sed -n 's/^style=//p' "$FLAG" | tail -1)
[ "$style" = "on" ] || exit 0

input=$(cat)

model=$(printf '%s' "$input" | jq -r '.model // empty' 2>/dev/null)
[ -n "$model" ] || exit 0

event=$(printf '%s' "$input" | jq -r '.hook_event_name // empty' 2>/dev/null)
[ -n "$event" ] || exit 0

# Styles directory: CLAUDE_PLUGIN_ROOT when set, else resolve relative to this
# script (hooks/ -> ../styles).
if [ -n "${CLAUDE_PLUGIN_ROOT}" ]; then
  STYLES_DIR="${CLAUDE_PLUGIN_ROOT}/styles"
else
  STYLES_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../styles" 2>/dev/null && pwd)
fi
[ -n "$STYLES_DIR" ] || exit 0

# Try the model id as-is first, then progressively normalized variants: a
# trailing bracketed suffix stripped (e.g. claude-opus-5[1m] -> claude-opus-5),
# a trailing -YYYYMMDD date suffix stripped (e.g. claude-opus-5-20260501 ->
# claude-opus-5), and both stripped together, bracket first then date (e.g.
# claude-opus-5-20260501[1m] -> claude-opus-5).
nobracket=$(printf '%s' "$model" | sed 's/\[[^][]*\]$//')
nodate=$(printf '%s' "$model" | sed 's/-[0-9]\{8\}$//')
stripped=$(printf '%s' "$nobracket" | sed 's/-[0-9]\{8\}$//')
FILE=""
for id in "$model" "$nobracket" "$nodate" "$stripped"; do
  if [ -f "${STYLES_DIR}/${id}.md" ]; then
    FILE="${STYLES_DIR}/${id}.md"
    break
  fi
done
[ -n "$FILE" ] || exit 0

jq -n --arg event "$event" --rawfile p "$FILE" \
  '{hookSpecificOutput: {hookEventName: $event, additionalContext: $p}, suppressOutput: true}'
