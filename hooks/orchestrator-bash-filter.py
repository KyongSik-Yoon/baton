#!/usr/bin/env python3
"""Bash policy for opus5-router's main-agent guard.

stdin: the PreToolUse JSON for a Bash call from the MAIN agent (the guard has
already checked the flag file and filtered out subagent calls). stdout: empty
to allow, or a deny decision. Default-deny: only read-only inspection and
test/lint/typecheck commands pass. This aims to make bypasses hard, not
impossible — the enforcement target is model drift, not an adversary.
"""
import json
import re
import shlex
import sys

DELEGATE = " Delegate it to a worker subagent (coder-sonnet / coder-opus48)."

SIMPLE = {
    "ls", "tree", "pwd", "wc", "du", "df", "file", "stat", "head", "tail",
    "cat", "less", "grep", "rg", "find", "fd", "awk", "sort", "uniq", "cut",
    "tr", "echo", "printf", "which", "type", "date", "diff", "cd", "true",
    "test", "[", "column", "jq", "xxd", "strings", "basename", "dirname",
    "realpath", "readlink", "md5sum", "sha256sum", "uname", "whoami", "env",
}
GIT_RO = {
    "status", "diff", "log", "show", "blame", "remote", "rev-parse",
    "ls-files", "ls-remote", "describe", "shortlog", "reflog", "grep",
    "fetch", "cherry", "merge-base", "count-objects", "var",
}
GIT_LIST_SAFE_FLAGS = {
    "-a", "-r", "-v", "-vv", "-l", "--list", "--show-current",
    "--merged", "--no-merged", "--sort=-committerdate",
}
GLAB_RO = {
    "mr": {"list", "view", "diff", "checks", "approvers"},
    "issue": {"list", "view"},
    "ci": {"list", "view", "status", "trace", "lint", "get"},
    "pipe": {"list", "view", "status", "trace", "lint", "get"},
    "pipeline": {"list", "view", "status", "trace", "lint", "get"},
    "release": {"list", "view"},
    "repo": {"view", "search", "contributors"},
    "label": {"list"},
    "auth": {"status"},
}
RUNNERS = {
    "pytest", "tsc", "eslint", "ruff", "mypy", "flake8", "phpunit", "ctest",
    "jest", "vitest", "playwright", "rspec", "tox", "shellcheck",
}
NPM_RUN_OK = re.compile(r"^(test|lint|typecheck|check|coverage)([:.].*)?$")
FLAG_PATH = r"(~|\$HOME|\$\{HOME\})/\.claude/opus5-router"
# The skill itself toggles the flag file from the main agent, so these exact
# management forms must pass even though touch/rm/redirection are otherwise out.
FLAG_MGMT = re.compile(
    r"^\s*(touch\s+[\x22\x27]?" + FLAG_PATH + r"[\x22\x27]?"
    r"|rm\s+-f\s+[\x22\x27]?" + FLAG_PATH + r"[\x22\x27]?"
    r"|(echo|printf)\s+[\x22\x27]?advisor=(fable|none)(\\n)?[\x22\x27]?\s*>\s*[\x22\x27]?"
    + FLAG_PATH + r"[\x22\x27]?)\s*$"
)


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(0)


def glab_ok(args):
    if not args:
        return False
    if args[0] in ("version", "--version", "--help", "-h"):
        return True
    if len(args) < 2:
        return False
    allowed = GLAB_RO.get(args[0])
    return allowed is not None and args[1] in allowed


def git_ok(args):
    # Skip leading global flags; -C and -c take a value.
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c") else 1
    if i >= len(args):
        return False
    sub, rest = args[i], args[i + 1:]
    if sub in GIT_RO:
        return True
    if sub == "config":
        return any(a in ("--get", "--list", "-l") for a in rest)
    if sub in ("branch", "tag"):
        return all(a in GIT_LIST_SAFE_FLAGS for a in rest)
    if sub == "stash":
        return bool(rest) and rest[0] in ("list", "show")
    return False


def segment_ok(seg):
    try:
        words = shlex.split(seg, posix=True)
    except ValueError:
        return False
    while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
        words = words[1:]
    if not words:
        return True
    head, args = words[0].rsplit("/", 1)[-1], words[1:]
    if head in SIMPLE:
        return True
    if head == "sed":
        return "-i" not in args and not any(a.startswith("-i") for a in args)
    if head == "git":
        return git_ok(args)
    if head == "glab":
        return glab_ok(args)
    if head in RUNNERS:
        return True
    if head in ("npm", "pnpm", "yarn", "bun"):
        if not args:
            return False
        if args[0] in ("test", "t"):
            return True
        return args[0] == "run" and len(args) > 1 and bool(NPM_RUN_OK.match(args[1]))
    if head in ("npx", "bunx"):
        return bool(args) and args[0] in RUNNERS
    if head == "go":
        return bool(args) and args[0] in ("test", "vet", "version", "env", "list")
    if head == "cargo":
        return bool(args) and args[0] in ("test", "check", "clippy", "tree", "metadata")
    if head in ("make", "just"):
        return bool(args) and all(
            re.match(r"^(test|lint|check|typecheck)", a) for a in args if not a.startswith("-")
        )
    if head == "mvn":
        return bool(args) and all(a in ("test", "verify") or a.startswith("-") for a in args)
    if head in ("gradle", "gradlew", "./gradlew"):
        return bool(args) and all(a in ("test", "check") or a.startswith("-") for a in args)
    return False


def main():
    try:
        cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except Exception:
        deny("orchestrator mode: could not parse this Bash command." + DELEGATE)

    if FLAG_MGMT.match(cmd):
        return

    scrubbed = re.sub(r"2>&1|2>\s*/dev/null|&?>{1,2}\s*/dev/null", "", cmd)
    if re.search(r">|<\(|\$\(|`", scrubbed):
        deny("orchestrator mode: redirection and command substitution are blocked "
             "for the main agent because they can mutate state." + DELEGATE)

    for seg in re.split(r"\|\||&&|;|\||\n", scrubbed):
        if seg.strip() and not segment_ok(seg):
            first = (seg.strip().split() or ["?"])[0]
            deny("orchestrator mode: Bash for the main agent is limited to read-only "
                 f"inspection and test/lint commands; '{first}' is not on that list."
                 + DELEGATE)


if __name__ == "__main__":
    main()
