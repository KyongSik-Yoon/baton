# baton

[README.ko.md](README.ko.md)

Run your **session as a pure orchestrator** — the one holding the baton makes no sound: it thinks, decomposes, delegates, and reviews, but never edits. The parent model is a profile, not an assumption: with an **Opus 5 parent** you get orchestration on the cheap with Fable 5 imported only for judgment; with a **Fable 5 parent** you get top-tier judgment orchestrating directly while implementation still goes to cheap pinned workers. The enforcement layer never inspects the parent model, so both profiles are enforced identically.

> Formerly published as `opus-5-router` — renamed once the Opus-parent assumption became just one of the two profiles. The old flag file `~/.claude/opus5-router` is no longer read; `/baton on` cleans it up.

Sibling project: the [fable-router](https://github.com/KyongSik-Yoon/fable-router) plugin takes a prompt-routing approach — Fable 5 as the parent, routing delegable stages down to cheaper models by convention. This plugin's `parent=fable` profile covers the same intent with mechanical enforcement instead. The fable-router skill previously bundled here now lives only in its own repository.

## How it works

Enforcement is mechanical, not prompt-based. While the flag file `~/.claude/baton` exists, the plugin's `PreToolUse` hook (`hooks/orchestrator-guard.sh`) denies the **main agent's** `Write`/`Edit`/`NotebookEdit` and any Bash beyond read-only inspection and test/lint commands (`hooks/orchestrator-bash-filter.py`, default-deny). Subagent calls pass untouched — their hook input carries `agent_id`, the main agent's never does. Deny reasons steer the model toward delegation. A `UserPromptSubmit` hook (`hooks/orchestrator-mode.sh`) injects the orchestrator posture each turn.

Implementation goes to workers pinned by frontmatter model ID, so the tiers hold regardless of what the `opus` alias resolves to:

| Agent | Model | Effort | Role |
| --- | --- | --- | --- |
| `baton:coder-opus48` | `claude-opus-4-8` | high | complex implementation, cross-file refactors, tricky debugging |
| `baton:coder-sonnet` | `claude-sonnet-5` | medium | standard implementation, test writing, moderate fixes |
| `baton:scout` | Haiku 4.5 | low | mechanical read-only recon (built-in Explore would inherit the expensive session model) |
| `baton:scout-sonnet` | `claude-sonnet-5` | low | interpretive read-only recon — ambiguous code, scattered evidence, hypothesis forming |
| `baton:reviewer-xhigh` | `claude-opus-4-8` | xhigh | adversarial read-only review of high-consequence diffs; handles the final-review trigger when advisor=none |
| `baton:advisor` | `fable` | high | persistent senior advisor, read-only |

How the escalation triggers (architecture decisions, twice-failed validation after a tier escalation, conflicting evidence, final review of high-consequence changes) resolve depends on the `parent=` profile in the flag file:

- **`parent=opus`** (default): Fable is consulted at the triggers as **one persistent advisor agent**, continued via SendMessage rather than respawned per question. With `advisor=none` — e.g. once your Fable quota is spent — the design/ambiguity triggers resolve via AskUserQuestion instead, while the final-review trigger routes to `baton:reviewer-xhigh`.
- **`parent=fable`**: the orchestrator is itself the top judgment tier — it decides the design/ambiguity triggers in place, and only the final-review trigger is farmed out (to `baton:reviewer-xhigh`, for independence rather than capability). The advisor defaults to `none` here; `advisor=fable` opts into a fresh-context second opinion on the same tier.

On `/baton on` without an explicit `parent=`, the skill defaults the profile from the session's own model identity.

## Usage

```
/baton on               # parent auto-detected; advisor=fable under opus, none under fable
/baton on advisor=none  # opus parent without Fable at all
/baton on parent=fable  # Fable-parent profile explicitly
/baton advisor none     # switch advisor while staying on
/baton parent fable     # switch parent profile while staying on
/baton status
/baton off
```

## Install

```
/plugin marketplace add KyongSik-Yoon/baton
/plugin install baton@baton
```

The plugin install is required for the mode to actually enforce anything — the hooks ship with the plugin. A manual checkout must wire `orchestrator-guard.sh` (PreToolUse, matcher `Write|Edit|NotebookEdit|Bash`) and `orchestrator-mode.sh` (UserPromptSubmit) into settings itself.

## Notes

- The skill cannot switch your session model. Pin it per project with `"model": "claude-opus-5"` (or `"claude-fable-5"`) in `.claude/settings.json`, or use `/model`.
- Don't run it together with the fable-router plugin's auto mode — even under `parent=fable` they are two competing routing schemes over the same session. `/baton on` warns if both flags are set.
- The Bash filter aims to make bypasses hard, not impossible: the enforcement target is model drift, not an adversary.
- Why the scout stays on Haiku: recon cost is dominated by input tokens, where effort settings don't help and Sonnet 5's new tokenizer (~30% more tokens for the same text) widens the sticker 3x price gap to ~4x in practice (~2.6x under the intro pricing that ends 2026-08-31). Recon that needs interpretation rather than scanning exceeds Haiku's floor — route it to `baton:scout-sonnet`.
