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
    "cat", "less", "grep", "rg", "find", "fd", "sort", "uniq", "cut",
    "tr", "echo", "printf", "which", "type", "date", "diff", "cd", "true",
    "test", "[", "column", "jq", "xxd", "strings", "basename", "dirname",
    "realpath", "readlink", "md5sum", "sha256sum", "uname", "whoami", "env",
    # read-only inspection additions (tee excluded: it writes files)
    "ps", "pgrep", "nproc", "uptime", "free", "id", "hostname", "groups",
    "seq", "nl", "tac", "rev", "comm", "paste", "join", "expr", "base64",
    "sha1sum", "cksum", "getent", "ss", "lsof",
}
GIT_RO = {
    "status", "diff", "log", "show", "blame", "rev-parse",
    "ls-files", "ls-remote", "describe", "shortlog", "grep",
    "fetch", "cherry", "merge-base", "count-objects", "var",
    "rev-list", "for-each-ref", "show-ref", "show-branch", "ls-tree",
    "cat-file", "check-ignore", "check-attr", "name-rev", "whatchanged",
    "diff-tree", "diff-files", "diff-index", "verify-commit", "verify-tag",
    "verify-pack", "annotate", "version", "help",
}
# Subcommands read-only only for a whitelisted first positional arg (like stash).
# submodule foreach / notes add / bisect start etc. run or mutate — excluded.
GIT_SUB_FIRSTARG = {
    "stash": {"list", "show"},
    "worktree": {"list"},
    "submodule": {"status", "summary"},
    "bisect": {"log", "view"},
    "notes": {"list", "show"},
}
GIT_LIST_SAFE_FLAGS = {
    "-a", "-r", "-v", "-vv", "-l", "--list", "--show-current",
    "--merged", "--no-merged", "--sort=-committerdate",
}
_CI_RO = {"list", "view", "status", "trace", "lint", "get", "config"}
# token/variable excluded: they print secrets. artifact/download/clone excluded:
# they write files to disk (not read-only from the sandbox's point of view).
GLAB_RO = {
    "mr": {"list", "view", "diff", "checks", "approvers"},
    "issue": {"list", "view"},
    "incident": {"list", "view"},
    "ci": _CI_RO,
    "pipe": _CI_RO,
    "pipeline": _CI_RO,
    "job": {"list", "view", "get", "trace"},
    "release": {"list", "view"},
    "repo": {"view", "search", "contributors", "list"},
    "label": {"list"},
    "milestone": {"list"},
    "iteration": {"list"},
    "schedule": {"list"},
    "snippet": {"list", "view"},
    "deploy-key": {"list", "get"},
    "ssh-key": {"list", "get"},
    "gpg-key": {"list", "get"},
    "user": {"events"},
    "auth": {"status"},
    "config": {"get", "list"},
    "changelog": {"generate"},
    "alias": {"list"},
}
# Top-level commands that are read-only for every subcommand/arg combination.
GLAB_RO_TOP = {"search", "check-update", "whatsnew"}
GLAB_API_LONG_MUTATE = ("--field", "--raw-field", "--input")
RUNNERS = {
    "pytest", "tsc", "eslint", "ruff", "mypy", "flake8", "phpunit", "ctest",
    "jest", "vitest", "playwright", "rspec", "tox", "shellcheck",
}
NPM_RUN_OK = re.compile(r"^(test|lint|typecheck|check|coverage)([:.].*)?$")
# Read-only npm/pnpm/yarn/bun subcommands (install/add/remove/publish/link/exec
# and `config set` stay denied — they mutate the tree or the config).
NPM_RO_SUB = {"ls", "list", "view", "root", "prefix", "outdated", "why", "explain"}
# xargs flags that consume a value (glued like -n1 or as the next word like -n 1).
XARGS_VALUE_FLAGS = {"-n", "-P", "-I", "-L", "-s", "-a", "-d", "-E", "-i"}
# Shell keywords: strip and re-check the remainder as a command. `for` heads a
# loop header whose trailing words are a list, not a command; `case` is waved
# through only as a bare header, since a one-line case body shares its segment.
KEYWORDS = {
    "for", "while", "until", "if", "then", "else", "elif", "fi",
    "do", "done", "case", "esac", "{", "}",
}
# herdr read-only subcommands (mutators split/run/send-keys/create/close/stop
# and the bare TUI stay denied).
HERDR_RO = {
    "pane": {"list", "get", "current", "layout", "read", "wait-output"},
    "agent": {"wait"},
    "workspace": {"list"},
    "tab": {"list"},
    "session": {"list", "get"},
    "notification": {"list"},
}
# Groups whose bare form just prints help; includes read-only-less groups so
# `herdr worktree`/`herdr server` print usage without invoking a mutator.
HERDR_GROUPS = set(HERDR_RO) | {"worktree", "server"}
FLAG_PATH = r"(~|\$HOME|\$\{HOME\})/\.claude/opus5-router"
# The skill itself toggles the flag file from the main agent, so these exact
# management forms must pass even though touch/rm/redirection are otherwise out.
FLAG_MGMT = re.compile(
    r"^\s*(touch\s+[\x22\x27]?" + FLAG_PATH + r"[\x22\x27]?"
    r"|rm\s+-f\s+[\x22\x27]?" + FLAG_PATH + r"[\x22\x27]?"
    r"|(echo|printf)\s+[\x22\x27]?advisor=(fable|none)(\\n)?[\x22\x27]?\s*>\s*[\x22\x27]?"
    + FLAG_PATH + r"[\x22\x27]?)\s*$"
)

REDIRECT_MSG = (
    "orchestrator mode: output redirection, process substitution, and command "
    "substitution that is not itself a read-only command are blocked for the "
    "main agent because they can mutate state." + DELEGATE
)
CURL_MSG = (
    "orchestrator mode: curl/wget are blocked for the main agent because they "
    "can POST and exfiltrate data; use the WebFetch tool for network reads."
    + DELEGATE
)
GENERIC_MSG = (
    "orchestrator mode: Bash for the main agent is limited to read-only "
    "inspection and test/lint commands; '{}' is not on that list." + DELEGATE
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
    if any(a in ("-h", "--help") for a in args):
        return True  # help is read-only regardless of where it appears
    if args[0] in ("version", "--version", "-v", "help"):
        return True
    if args[0] in GLAB_RO_TOP:
        return True
    if args[0] == "api":
        return _glab_api_ok(args[1:])
    if len(args) < 2:
        return False
    allowed = GLAB_RO.get(args[0])
    return allowed is not None and args[1] in allowed


def _glab_api_ok(args):
    for i, a in enumerate(args):
        # long flags: bare or --flag=value; -f/-F: bare or glued -fvalue/-Fvalue
        if a in GLAB_API_LONG_MUTATE or a.split("=", 1)[0] in GLAB_API_LONG_MUTATE:
            return False
        if a in ("-f", "-F") or (len(a) > 2 and a[:2] in ("-f", "-F")):
            return False
        if a == "--method" or a.startswith("--method="):
            value = a.split("=", 1)[1] if "=" in a else args[i + 1] if i + 1 < len(args) else ""
            if value.upper() != "GET":
                return False
        elif a == "-X" or (len(a) > 2 and a[:2] == "-X"):
            value = a[2:] if len(a) > 2 else args[i + 1] if i + 1 < len(args) else ""
            if value.upper() != "GET":
                return False
    return True


def git_ok(args):
    # Skip leading global flags; -C and -c take a value.
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in ("-C", "-c") else 1
    if i >= len(args):
        return False
    sub, rest = args[i], args[i + 1:]
    positionals = [a for a in rest if not a.startswith("-")]
    if sub in GIT_RO:
        return True
    if sub == "config":
        return any(a in ("--get", "--list", "-l") for a in rest)
    if sub in ("branch", "tag"):
        return all(a in GIT_LIST_SAFE_FLAGS for a in rest)
    if sub in GIT_SUB_FIRSTARG:
        return bool(positionals) and positionals[0] in GIT_SUB_FIRSTARG[sub]
    if sub == "symbolic-ref":  # reads with <=1 arg; a second arg (or -d) writes.
        return "-d" not in rest and "--delete" not in rest and len(positionals) <= 1
    if sub == "remote":
        return not positionals or positionals[0] in ("show", "get-url")
    if sub == "reflog":
        return not positionals or positionals[0] == "show"
    return False


def npm_ok(args):
    # Skip leading global flags (so `npm -g config get prefix` reaches config);
    # a bare -v/--version with no subcommand is a read-only version query.
    version_flag = False
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i] in ("-v", "--version"):
            version_flag = True
        i += 1
    if i >= len(args):
        return version_flag
    sub = args[i]
    if sub in ("test", "t"):
        return True
    if sub == "run":
        rest = args[i + 1:]
        return bool(rest) and bool(NPM_RUN_OK.match(rest[0]))
    if sub in NPM_RO_SUB:
        return True
    if sub == "config":  # only `config get`; `config set` mutates
        pos = [a for a in args[i + 1:] if not a.startswith("-")]
        return bool(pos) and pos[0] == "get"
    return False


def claude_ok(args):
    # Bare `claude` opens a REPL, so an empty arg list is denied.
    if not args:
        return False
    if args[0] in ("--version", "-v", "doctor"):
        return True
    if args[0] in ("mcp", "plugin"):
        return len(args) > 1 and args[1] == "list"
    return False


def herdr_ok(args):
    # Bare `herdr` opens the TUI; a bare known group just prints help.
    if not args:
        return False
    if any(a in ("-h", "--help") for a in args):
        return True
    if len(args) == 1:
        return args[0] in HERDR_GROUPS
    allowed = HERDR_RO.get(args[0])
    return allowed is not None and args[1] in allowed


def xargs_ok(args):
    # Skip xargs' own flags (value-taking ones may be glued or a separate word),
    # then validate the command it would run. No command means implicit echo.
    i = 0
    while i < len(args) and args[i].startswith("-"):
        if args[i][:2] in XARGS_VALUE_FLAGS and len(args[i]) == 2:
            i += 2  # value is the next word
        else:
            i += 1  # valueless flag, or a glued value like -n1 / -I{}
    if i >= len(args):
        return True
    return words_ok(args[i:])


def words_ok(words):
    while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
        words = words[1:]
    while words and words[0] in KEYWORDS:
        if words[0] == "for":
            return True  # `for f in <list>` — a word list, not a command
        if words[0] == "case":
            # Accept only a bare header `case <word> [in]`; a `)` means a one-line
            # pattern body shares this segment, so refuse it rather than wave the
            # body command (e.g. `case x in x) rm -rf /tmp/y`) through unchecked.
            return not any(")" in w for w in words[1:])
        words = words[1:]  # strip the keyword and re-check the remainder
    if not words:
        return True  # keyword-only segment (done, fi, esac, })
    head, args = words[0].rsplit("/", 1)[-1], words[1:]
    if head in SIMPLE:
        return True
    if head == "sed":
        return "-i" not in args and not any(a.startswith("-i") for a in args)
    if head == "awk":
        return not any(">" in a for a in args)
    if head == "git":
        return git_ok(args)
    if head == "glab":
        return glab_ok(args)
    if head == "claude":
        return claude_ok(args)
    if head == "herdr":
        return herdr_ok(args)
    if head == "xargs":
        return xargs_ok(args)
    if head in RUNNERS:
        return True
    if head in ("npm", "pnpm", "yarn", "bun"):
        return npm_ok(args)
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


def segment_ok(seg):
    try:
        words = shlex.split(seg, posix=True)
    except ValueError:
        return False
    return words_ok(words)


class Dangerous(Exception):
    """A construct the shell would execute that we refuse: output redirection,
    process substitution, or a command substitution whose inner command is not
    itself read-only (or nests past the depth limit)."""


def scrub(text):
    return re.sub(r"2>&1|2>\s*/dev/null|&?>{1,2}\s*/dev/null", "", text)


def _find_paren_close(text, i):
    """Index of the `)` closing a `$(` whose inner text starts at i, tracking
    nested parens and quote state; -1 if unmatched."""
    depth, quote, n = 1, None, len(text)
    while i < n:
        c = text[i]
        if quote:
            if c == "\\" and quote == '"' and i + 1 < n:
                i += 2; continue
            if c == quote:
                quote = None
            i += 1; continue
        if c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _find_backtick_close(text, i):
    n = len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n:
            i += 2; continue
        if text[i] == "`":
            return i
        i += 1
    return -1


def _sub_ok(inner, depth):
    """A command substitution is allowed only below the nesting limit and when
    its inner text is itself a valid read-only command."""
    return depth < 2 and command_ok(inner, depth + 1)


def scan(text, depth):
    """Single left-to-right pass tracking quote state, so separators and
    dangerous metacharacters are only acted on where the shell would honour
    them. Returns the command split into segments on unquoted separators;
    raises Dangerous for redirects / process substitution, and for command
    substitutions whose inner command fails validation. Validated command
    substitutions are replaced by a harmless placeholder word."""
    segments, cur = [], []
    quote = None  # None, "'" or '"'
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if quote == "'":  # single quotes: everything literal until the next '
            cur.append(c)
            if c == "'":
                quote = None
            i += 1
        elif quote == '"':
            if c == "\\" and i + 1 < n:  # backslash escapes the next char
                cur.append(c); cur.append(text[i + 1]); i += 2
            elif c == "`":  # still expands inside double quotes
                end = _find_backtick_close(text, i + 1)
                if end < 0 or not _sub_ok(text[i + 1:end], depth):
                    raise Dangerous
                cur.append("_SUBST_"); i = end + 1
            elif c == "$" and text[i + 1:i + 2] == "(":
                end = _find_paren_close(text, i + 2)
                if end < 0 or not _sub_ok(text[i + 2:end], depth):
                    raise Dangerous
                cur.append("_SUBST_"); i = end + 1
            else:
                cur.append(c)
                if c == '"':
                    quote = None
                i += 1
        else:  # unquoted
            if c == "\\" and i + 1 < n:
                cur.append(c); cur.append(text[i + 1]); i += 2
            elif c in "'\"":
                quote = c; cur.append(c); i += 1
            elif c == ">" or (c == "<" and text[i + 1:i + 2] == "("):
                raise Dangerous  # output redirection / process substitution
            elif c == "`":
                end = _find_backtick_close(text, i + 1)
                if end < 0 or not _sub_ok(text[i + 1:end], depth):
                    raise Dangerous
                cur.append("_SUBST_"); i = end + 1
            elif c == "$" and text[i + 1:i + 2] == "(":
                end = _find_paren_close(text, i + 2)
                if end < 0 or not _sub_ok(text[i + 2:end], depth):
                    raise Dangerous
                cur.append("_SUBST_"); i = end + 1
            elif text[i:i + 2] in ("||", "&&"):
                segments.append("".join(cur)); cur = []; i += 2
            elif c in ";|\n":  # bare & stays a normal char, matching prior behavior
                segments.append("".join(cur)); cur = []; i += 1
            else:
                cur.append(c); i += 1
    segments.append("".join(cur))
    return segments


def command_ok(text, depth):
    """Whole-command decision: scrub redirection noise, split on separators
    (validating any command substitution recursively), and require every
    segment to be read-only."""
    try:
        segments = scan(scrub(text), depth)
    except Dangerous:
        return False
    return all(segment_ok(s) for s in segments if s.strip())


def explain(cmd):
    """Reconstruct why command_ok(cmd, 0) refused, for a useful deny message."""
    try:
        segments = scan(scrub(cmd), 0)
    except Dangerous:
        return REDIRECT_MSG
    for seg in segments:
        if seg.strip() and not segment_ok(seg):
            first = (seg.strip().split() or ["?"])[0].rsplit("/", 1)[-1]
            if first in ("curl", "wget"):
                return CURL_MSG
            return GENERIC_MSG.format(first)
    return GENERIC_MSG.format("?")


def main():
    try:
        cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except Exception:
        deny("orchestrator mode: could not parse this Bash command." + DELEGATE)

    if FLAG_MGMT.match(cmd):
        return

    if not command_ok(cmd, 0):
        deny(explain(cmd))


if __name__ == "__main__":
    main()
