#!/usr/bin/env python3
"""Read-tool policy for baton's main-agent guard.

stdin: the PreToolUse JSON for a Read call from the MAIN agent (the guard has
already checked the flag file and filtered out subagent calls). stdout: empty
to allow, or a deny decision. Unlike the Bash filter this is not default-deny:
it is a cost guard rather than a safety guard, so anything whose volume it
cannot judge passes.
"""
import json
import sys

from baton_read_cap import (
    FILE_MSG, LINES_MSG, MAX_READ_BYTES, MAX_READ_LINES, oversize,
)

# Read renders these as images or pages rather than lines, so a line cap says
# nothing about them and a scout could not hand the pixels back anyway.
OPAQUE_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".pdf",
)


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return  # unparseable input is not a reason to block a read
    args = data.get("tool_input") or {}
    path = args.get("file_path") or ""
    if not path or path.lower().endswith(OPAQUE_SUFFIXES):
        return

    limit = args.get("limit")
    if isinstance(limit, (int, float)) and not isinstance(limit, bool) and limit > 0:
        # A bounded slice is exactly what the cap is asking for; only refuse a
        # bound so wide it is a whole-file read wearing a parameter.
        if limit > MAX_READ_LINES:
            deny(LINES_MSG.format(int(limit), MAX_READ_LINES))
        return

    size = oversize(path)
    if size:
        deny(FILE_MSG.format(path, size // 1024, MAX_READ_BYTES // 1024))


if __name__ == "__main__":
    main()
