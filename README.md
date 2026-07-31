# opus-5-router

[README.ko.md](README.ko.md)

Run an **Opus 5 session as a pure orchestrator** — it thinks, decomposes, delegates, and reviews, but never edits. Useful when Opus 5's direct coding underwhelms but its orchestration holds up, and when you want Fable 5 spent only on judgment.

Sibling project: the [fable-router](https://github.com/KyongSik-Yoon/fable-router) plugin takes the opposite approach — Fable 5 as the parent, routing delegable stages down to cheaper models. This plugin previously bundled that skill; it now lives only in its own repository.

## How it works

Enforcement is mechanical, not prompt-based. While the flag file `~/.claude/opus-orchestrator` exists, the plugin's `PreToolUse` hook (`hooks/orchestrator-guard.sh`) denies the **main agent's** `Write`/`Edit`/`NotebookEdit` and any Bash beyond read-only inspection and test/lint commands (`hooks/orchestrator-bash-filter.py`, default-deny). Subagent calls pass untouched — their hook input carries `agent_id`, the main agent's never does. Deny reasons steer the model toward delegation. A `UserPromptSubmit` hook (`hooks/orchestrator-mode.sh`) injects the orchestrator posture each turn.

Implementation goes to workers pinned by frontmatter model ID, so the tiers hold regardless of what the `opus` alias resolves to:

| Agent | Model | Effort | Role |
| --- | --- | --- | --- |
| `opus-5-router:coder-opus48` | `claude-opus-4-8` | high | complex implementation, cross-file refactors, tricky debugging |
| `opus-5-router:coder-sonnet` | `claude-sonnet-5` | medium | standard implementation, test writing, moderate fixes |
| `opus-5-router:scout` | Haiku 4.5 | low | mechanical read-only recon (built-in Explore would inherit the expensive session model) |
| `opus-5-router:scout-sonnet` | `claude-sonnet-5` | low | interpretive read-only recon — ambiguous code, scattered evidence, hypothesis forming |
| `opus-5-router:advisor` | `fable` | high | persistent senior advisor, read-only |

Fable is consulted only at mandatory triggers (architecture decisions, twice-failed validation after a tier escalation, conflicting evidence, final review of high-consequence changes), as **one persistent advisor agent** continued via SendMessage rather than respawned per question. With `advisor=none` — e.g. once your Fable quota is spent — the triggers resolve via AskUserQuestion instead.

## Usage

```
/opus-orchestrator on              # advisor=fable (default)
/opus-orchestrator on advisor=none # pure Opus mode, no Fable at all
/opus-orchestrator advisor none    # switch advisor while staying on
/opus-orchestrator status
/opus-orchestrator off
```

## Install

```
/plugin marketplace add KyongSik-Yoon/opus-5-router
/plugin install opus-5-router@opus-5-router
```

The plugin install is required for the mode to actually enforce anything — the hooks ship with the plugin. A manual checkout must wire `orchestrator-guard.sh` (PreToolUse, matcher `Write|Edit|NotebookEdit|Bash`) and `orchestrator-mode.sh` (UserPromptSubmit) into settings itself.

## Notes

- The skill cannot switch your session model. Pin it per project with `"model": "claude-opus-5"` in `.claude/settings.json`, or use `/model`.
- Don't run it together with the fable-router plugin's auto mode — one assumes a Fable parent, the other an Opus parent. `/opus-orchestrator on` warns if both flags are set.
- The Bash filter aims to make bypasses hard, not impossible: the enforcement target is model drift, not an adversary.
- Why the scout stays on Haiku: recon cost is dominated by input tokens, where effort settings don't help and Sonnet 5's new tokenizer (~30% more tokens for the same text) widens the sticker 3x price gap to ~4x in practice (~2.6x under the intro pricing that ends 2026-08-31). Recon that needs interpretation rather than scanning exceeds Haiku's floor — route it to `opus-5-router:scout-sonnet`.
