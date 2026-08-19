"""Shared read-cap policy for baton's main-agent guard.

Blocking the main agent's writes saves output tokens, but an orchestrator's
bill is dominated by what it *reads*: every file it pulls in itself is context
it pays for on every later turn, instead of a worker paying for it once and
handing back a summary. These caps push bulk recon to baton:scout. The escape
is always one parameter away (a smaller Read limit, head -n, a sed range) —
like the rest of the guard, the target is model drift, not an adversary.
"""
import os


def _cap(name, default):
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


# A whole-file read of something larger than MAX_READ_BYTES, or an explicitly
# bounded read of more than MAX_READ_LINES lines, is refused for the main agent.
MAX_READ_BYTES = _cap("BATON_READ_MAX_BYTES", 64 * 1024)
MAX_READ_LINES = _cap("BATON_READ_MAX_LINES", 800)

HINT = (
    " Reading is where an orchestrator's tokens go, so bulk recon belongs to a"
    " worker: delegate it to baton:scout (baton:scout-sonnet when it needs"
    " interpretation) and keep the summary, or take a bounded slice"
    " (Read with limit, head -n, sed -n '<start>,<end>p')."
)
FILE_MSG = (
    "orchestrator mode: '{}' is {} KB, past baton's whole-file read cap of"
    " {} KB." + HINT
)
LINES_MSG = (
    "orchestrator mode: this asks for {} lines, past baton's read cap of"
    " {} lines." + HINT
)
BYTES_MSG = (
    "orchestrator mode: this asks for {} bytes, past baton's read cap of"
    " {} bytes." + HINT
)


def oversize(path):
    """File size in bytes when `path` is a literal file past the byte cap, else
    0. A glob, an unexpanded variable, stdin, or a path we cannot stat gives 0:
    the volume is unknowable there, and guessing would deny ordinary reads."""
    if not path or path == "-" or any(c in path for c in "*?[$"):
        return 0
    try:
        size = os.path.getsize(os.path.expanduser(path))
    except OSError:
        return 0
    return size if size > MAX_READ_BYTES else 0
