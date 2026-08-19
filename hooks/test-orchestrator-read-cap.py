#!/usr/bin/env python3
"""Subprocess tests for baton's read cap.

Both halves are exercised against real fixture files in a temp directory: the
Read-tool hook (orchestrator-read-cap.py) and the bulk-read pass the Bash
filter runs after its read-only check. Empty stdout means allow; a deny
decision means deny. Prints one line per case and a summary; exits non-zero on
any failure.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASH_FILTER = os.path.join(HERE, "orchestrator-bash-filter.py")
READ_FILTER = os.path.join(HERE, "orchestrator-read-cap.py")

# Must match baton_read_cap's defaults; the fixtures straddle them.
MAX_BYTES = 64 * 1024
MAX_LINES = 800


def run(script, payload):
    proc = subprocess.run(
        [sys.executable, script],
        input=json.dumps(payload), capture_output=True, text=True,
    )
    out = proc.stdout.strip()
    if proc.returncode != 0:
        print(f"  hook crashed: {proc.stderr.strip()}")
        return None
    if out == "":
        return True
    try:
        assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"
    except Exception as e:
        print(f"  malformed output {out!r} ({e})")
        return None
    return False


def main():
    tmp = tempfile.mkdtemp(prefix="baton-read-cap-")
    big = os.path.join(tmp, "big.py")
    small = os.path.join(tmp, "small.py")
    image = os.path.join(tmp, "shot.png")
    with open(big, "w") as f:
        f.write(("x = 1  # padding to clear the byte cap\n") * 4000)
    with open(small, "w") as f:
        f.write("x = 1\n" * 50)
    with open(image, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\0" * (MAX_BYTES * 2))

    assert os.path.getsize(big) > MAX_BYTES
    assert os.path.getsize(small) < MAX_BYTES

    read_cases = [
        # (expect_allow, tool_input, label)
        (False, {"file_path": big}, "Read whole big file"),
        (True, {"file_path": small}, "Read whole small file"),
        (True, {"file_path": big, "limit": 200}, "Read big file, bounded slice"),
        (True, {"file_path": big, "limit": MAX_LINES}, "Read big file, slice at the cap"),
        (False, {"file_path": big, "limit": MAX_LINES + 1}, "Read big file, slice past the cap"),
        (False, {"file_path": small, "limit": 5000}, "Read small file, absurd limit"),
        (True, {"file_path": image}, "Read an image (line caps say nothing)"),
        (True, {"file_path": os.path.join(tmp, "absent.py")}, "Read a file that is not there"),
        (True, {}, "Read call with no file_path"),
    ]

    bash_cases = [
        # (expect_allow, command, label)
        (False, f"cat {big}", "cat a big file"),
        (True, f"cat {small}", "cat a small file"),
        (True, f"cat {big} | head -20", "cat a big file into a bounding stage"),
        (True, f"head -50 {big}", "head a bounded slice of a big file"),
        (False, f"head -n 100000 {big}", "head past the line cap"),
        (False, f"head -n 5000 {small}", "head past the line cap on a small file"),
        (True, f"sed -n '1,120p' {big}", "sed a bounded range of a big file"),
        (False, f"sed -n '1,9000p' {big}", "sed a range past the line cap"),
        (False, f"sed -n '/start/,/end/p' {big}", "sed a regex range (unbounded) of a big file"),
        (True, f"sed -n '/start/,/end/p' {small}", "sed a regex range of a small file"),
        (False, f"sed 's/a/b/' {big}", "sed streaming a whole big file"),
        (True, f"nl {small}", "nl a small file"),
        (False, f"nl {big}", "nl a big file"),
        (True, f"grep -n foo {big}", "grep a big file (output is sparse, not the file)"),
        (True, f"wc -l {big}", "wc a big file"),
        (True, f"ls -la {tmp}", "ordinary inspection is untouched"),
        (False, f"ls {tmp}; cat {big}", "a big read hidden after a separator"),
        (True, f"cat {tmp}/*.py", "a glob, whose volume cannot be known ahead of time"),
    ]

    passed = failed = 0
    for expect, tool_input, label in read_cases:
        got = run(READ_FILTER, {"tool_name": "Read", "tool_input": tool_input})
        ok = got == expect
        print(f"{'PASS' if ok else 'FAIL'}  {'allow' if got else 'deny '}  Read: {label}")
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    for expect, cmd, label in bash_cases:
        got = run(BASH_FILTER, {"tool_name": "Bash", "tool_input": {"command": cmd}})
        ok = got == expect
        print(f"{'PASS' if ok else 'FAIL'}  {'allow' if got else 'deny '}  Bash: {label}")
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    shutil.rmtree(tmp, ignore_errors=True)
    total = len(read_cases) + len(bash_cases)
    print(f"\n{passed}/{total} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
