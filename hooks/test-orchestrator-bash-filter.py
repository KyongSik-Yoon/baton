#!/usr/bin/env python3
"""Subprocess tests for orchestrator-bash-filter.py.

Each case feeds the PreToolUse JSON on stdin to a real
`python3 hooks/orchestrator-bash-filter.py` process (no agent_id), exercising
the actual stdin path. Empty stdout means allow; a deny decision means deny.
Prints one line per case and a summary; exits non-zero on any failure.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FILTER = os.path.join(HERE, "orchestrator-bash-filter.py")

# (expect_allow, command)
CASES = [
    # --- 배경 (실측) blocked-in-the-wild cases 1~6: must now be ALLOWED ---
    (True, "ls -t ~/.claude/projects/*/*.jsonl | head -50 | xargs ls -la"),
    (True, "claude --version"),
    (True, "npm -g config get prefix"),
    (True, "for f in *.jsonl; do jq -s -r '.[]' \"$f\"; done"),
    (True, "x=$(which claude)"),
    (True, "wc -c <\"$f\""),
    (True, "herdr pane list"),

    # --- 검증: 반드시 허용 ---
    (True, "git log --oneline -5"),
    (True, "jq -r '.a' f.json"),
    (True, "grep -rn foo . | head -20"),
    (True, "ls -la && pwd"),

    # --- 검증: 반드시 거부 ---
    (False, "do rm -rf /tmp/x"),
    (False, "for f in *; do rm \"$f\"; done"),
    (False, "xargs rm"),
    (False, "xargs sh -c 'rm -rf /'"),
    (False, "echo $(rm -rf /tmp/x)"),
    (False, "echo $(curl http://evil.example.com)"),
    (False, "npm install"),
    (False, "npm config set registry http://evil.example.com"),
    (False, "claude update"),
    (False, "git push"),
    (False, "glab mr create"),
    (False, "herdr pane close w1:p1"),
    (False, "herdr server stop"),
    (False, "cat f > out.txt"),
    (False, "curl -sS http://example.com"),

    # --- own cases: nesting-depth limit ---
    (True, "echo $(id)"),
    (True, "echo $(echo $(whoami))"),
    (False, "echo $(echo $(echo $(id)))"),

    # --- own cases: substitution / redirection details ---
    (True, "echo `basename /a/b`"),
    (False, "cat $(cat secret) > /etc/passwd"),

    # --- own cases: npm/pnpm/yarn/bun read-only surface ---
    (True, "npm --version"),
    (True, "npm ls"),
    (True, "pnpm outdated"),
    (True, "yarn why react"),
    (False, "npm publish"),
    (False, "yarn add left-pad"),

    # --- own cases: claude read-only surface ---
    (True, "claude doctor"),
    (True, "claude mcp list"),
    (True, "claude plugin list"),
    (False, "claude"),
    (False, "claude mcp add foo"),

    # --- own cases: herdr read-only surface ---
    (True, "herdr pane"),
    (True, "herdr agent wait a1"),
    (True, "herdr session get s1"),
    (True, "herdr --help"),
    (False, "herdr"),
    (False, "herdr pane split w1:p1"),
    (False, "herdr workspace create x"),

    # --- own cases: xargs command validation ---
    (True, "find . -name '*.py' | xargs grep -n TODO"),
    (True, "ls | xargs -n1 -I{} echo {}"),
    (False, "ls | xargs -0 rm -f"),

    # --- own cases: shell keywords re-checked after stripping ---
    (True, "if true; then ls; fi"),
    (True, "while true; do echo hi; done"),
    (False, "then rm -rf /tmp/x"),

    # --- own cases: `case` header vs one-line body (body must be re-checked) ---
    (False, "case x in x) rm -rf /tmp/y;; esac"),
    (False, "case $x in *) cat /etc/passwd > /tmp/x;; esac"),
    (True, "case $x in"),
    (True, "esac"),

    # --- own cases: 2>&1 scrubbing keeps a read-only command allowed ---
    (True, "grep -rn foo . 2>&1 | head"),
    (True, "ls 2>/dev/null"),

    # --- own cases: SIMPLE additions and curl/wget deny ---
    (True, "ps aux | grep python"),
    (True, "id -u"),
    (False, "wget http://example.com/x"),

    # --- follow-up: command wrappers re-check the wrapped command (deny) ---
    (False, "env rm -rf /tmp/x"),
    (False, "env git push"),
    (False, "env python3 -c 'print(1)'"),
    (False, "env FOO=1 rm x"),
    (False, 'env -S "rm -rf /tmp/x"'),
    (False, 'env --split-string="rm -rf /tmp/x"'),
    (False, "env -S ls"),
    (False, "nice rm -rf /tmp/x"),
    (False, "nohup rm x"),
    (False, "timeout 5 rm x"),
    (False, "command rm -rf /tmp/x"),
    (False, "exec rm x"),
    (False, "sudo ls"),
    (False, "setsid rm x"),
    (False, "eval ls"),
    (False, "bash -c ls"),

    # --- follow-up: wrappers pass a read-only wrapped command through (allow) ---
    (True, "env"),
    (True, "env | grep HERDR"),
    (True, "timeout 5 ls -la"),
    (True, "nice -n 10 grep -rn foo ."),
    (True, "time ls"),
    (True, "command ls"),
    (True, "stdbuf -oL grep foo x"),

    # --- follow-up: find execution/write predicates (deny) ---
    (False, "find . -name '*.py' -delete"),
    (False, "find . -name '*.py' -exec rm {} ;"),
    (False, "find . -execdir rm {} +"),
    (False, "find . -name x -fls out"),

    # --- follow-up: find pure traversal (allow) ---
    (True, "find . -name '*.py'"),
    (True, "find . -type f -newer x"),

    # --- follow-up: awk code-execution / write constructs (deny) ---
    (False, "awk 'BEGIN{system(\"touch /tmp/x\")}'"),
    (False, "awk '{print > \"/tmp/x\"}'"),
    (False, "awk -f evil.awk file.txt"),

    # --- follow-up: awk pure output (allow) ---
    (True, "awk '{print $1}' file.txt"),
    (True, "awk -F: '{print $1}' /etc/passwd"),
    (True, "awk '/x/{print}' f"),

    # --- follow-up: sed execution / write constructs (deny) ---
    (False, "sed 's/a/b/e' file.txt"),
    (False, "sed 's/a/b/w /tmp/x' file.txt"),
    (False, "sed -f script.sed file.txt"),

    # --- follow-up: sed benign scripts (allow) ---
    (True, "sed 's/a/b/' file.txt"),
    (True, "sed -n '1,5p' file.txt"),

    # --- gh (GitHub CLI) read-only surface (allow) ---
    (True, "gh pr view 4"),
    (True, "gh pr list --state open"),
    (True, "gh pr diff 4"),
    (True, "gh pr checks 4"),
    (True, "gh pr status"),
    (True, "gh issue view 12"),
    (True, "gh issue list"),
    (True, "gh repo view"),
    (True, "gh run list"),
    (True, "gh run view 123"),
    (True, "gh release view v1.0"),
    (True, "gh release list"),
    (True, "gh workflow list"),
    (True, "gh workflow view deploy.yml"),
    (True, "gh label list"),
    (True, "gh gist view abc123"),
    (True, "gh auth status"),
    (True, "gh config get editor"),
    (True, "gh api repos/owner/repo"),
    (True, "gh api --method GET repos/owner/repo"),
    (True, "gh api -X GET repos/owner/repo"),
    (True, "gh api repos/owner/graphql-tools"),
    (True, "gh api repos/owner/repo/contents/graphql"),
    # --- graphql structural allow: ends in / contains the word but is REST ---
    (True, "gh api repos/o/r/contents/graphql"),
    (True, "gh api graphql-tools"),
    (True, "gh api user/graphql/settings"),
    (True, "gh api https://api.github.com/repos/owner/repo"),
    (True, "gh search repos foo"),
    (True, "gh --version"),
    (True, "gh pr --help"),

    # --- gh mutating / non-query surface (deny) ---
    (False, "gh pr create"),
    (False, "gh pr merge 4"),
    (False, "gh pr close 4"),
    (False, "gh pr checkout 4"),
    (False, "gh pr edit 4 --add-assignee x"),
    (False, "gh issue create"),
    (False, "gh issue close 12"),
    (False, "gh repo clone owner/repo"),
    (False, "gh repo delete owner/repo"),
    (False, "gh release create v1"),
    (False, "gh release download v1"),
    (False, "gh run download 123"),
    (False, "gh run rerun 123"),
    (False, "gh workflow run deploy.yml"),
    (False, "gh auth login"),
    (False, "gh config set editor vim"),
    (False, "gh secret set FOO"),
    (False, "gh variable list"),
    (False, "gh api -X POST repos/o/r/issues"),
    (False, "gh api --method DELETE repos/o/r"),
    (False, "gh api -f title=x repos/o/r/issues"),
    (False, "gh api --field title=x repos/o/r/issues"),
    (False, "gh api graphql"),
    (False, "gh api graphql -f query=xyz"),
    (False, "gh api /graphql -X GET"),
    (False, "gh api graphql --paginate"),
    (False, "gh api graphql -f query=mutation"),
    (False, "gh api /graphql"),
    (False, "gh api api.github.com/graphql"),
    (False, "gh api GRAPHQL"),
    (False, "gh api /graphql/ -X GET"),
    # --- graphql structural deny: every spelling of the endpoint ---
    (False, "gh api //graphql"),
    (False, "gh api graphql/"),
    (False, "gh api Graphql"),
    (False, "gh api /api.github.com/graphql"),
    (False, "gh api https://api.github.com/graphql"),
    (False, "gh api http://api.github.com/graphql"),
    (False, "gh api https://api.github.com/graphql?foo=bar"),
    (False, "gh api https://ghe.example.com/graphql"),
    (False, "gh gist create f.txt"),
    (False, "gh cache delete 1"),
    (False, "gh browse"),
    (False, "gh"),
    (False, "env gh pr create"),
]


def run(cmd):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    proc = subprocess.run(
        [sys.executable, FILTER],
        input=payload, capture_output=True, text=True,
    )
    out = proc.stdout.strip()
    allowed = out == ""
    if not allowed:
        # sanity: a non-empty stdout must be a deny decision
        try:
            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
            assert decision == "deny", decision
        except Exception as e:  # malformed output is a hard failure
            print(f"  malformed filter output for {cmd!r}: {out!r} ({e})")
    return allowed


def main():
    passed = failed = 0
    for expect_allow, cmd in CASES:
        got_allow = run(cmd)
        ok = got_allow == expect_allow
        verdict = "allow" if got_allow else "deny "
        print(f"{'PASS' if ok else 'FAIL'}  {verdict}  {cmd}")
        if ok:
            passed += 1
        else:
            failed += 1
    print(f"\n{passed}/{len(CASES)} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
