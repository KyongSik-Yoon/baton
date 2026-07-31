# fable-router

[README.ko.md](README.ko.md)

Inspired by [gpt-5.6-router](https://github.com/volition79/gpt-5.6-router), ported to Claude Code. Saves Fable 5 (parent) tokens by routing delegable work stages to Opus/Sonnet/Haiku via the Agent tool's `model` override.

## Flow

1. **Gate 1** — pick a PERFORMANCE / BALANCED / TOKEN_SAVER profile (AskUserQuestion)
2. **Read-only discovery** — Haiku/Sonnet subagents gather only the minimum evidence needed to route
3. **Route design** — assign the lowest-cost capable model and lowest safe reasoning effort per stage, compare against Fable-direct
4. **Gate 2** — explicit route approval, then execution
5. **Completion report** — actual route, validation results, deviations, residual risk

## Changes from the original

- Sol/Terra/Luna remapped to Fable / Opus·Sonnet / Haiku capability floors
- Removed `spawn_agent` runtime classification (A/B/C) and Codex troubleshooting — the Claude Code Agent tool always supports the `model` parameter
- Merged references/assets docs into a single SKILL.md
- Added effort routing: the Agent tool has no per-call effort parameter, so the plugin ships `worker-low` / `worker-medium` / `worker-high` agent definitions (`agents/`) and routes effort by `subagent_type`, composing freely with the `model` override

## Install

### Claude Code (plugin marketplace)

```
/plugin marketplace add KyongSik-Yoon/fable-router
/plugin install fable-router@fable-router
```

### Manual (any Claude Code checkout)

```bash
git clone https://github.com/KyongSik-Yoon/fable-router
ln -s "$(pwd)/fable-router/skills/fable-router" ~/.claude/skills/fable-router
# effort-variant worker agents (skip if you only want model routing)
for f in fable-router/agents/*.md; do ln -s "$(pwd)/$f" ~/.claude/agents/; done
```

Note: the manual install registers workers as `worker-low` etc. (no `fable-router:` prefix); the plugin install is the documented path.

### Claude Desktop / claude.ai

Upload the `skills/fable-router` folder (or a zip of it) in Settings → Capabilities → Skills.

Then invoke with `/fable-router`. Activates only on explicit invocation.

## Auto mode

Off by default. `/fable-router auto on` creates the flag file `~/.claude/fable-router-auto`; while it exists, the skill skips the profile and route-approval questions and runs its recommended route (BALANCED unless a profile is named in the arguments) immediately. `/fable-router auto off` removes the flag. Safety invariants and normal permission prompts still apply.

With the plugin install, auto mode also stops needing `/fable-router` on every turn: the bundled `UserPromptSubmit` hook (`hooks/auto-route.sh`) checks the same flag and injects a routing directive into each turn. The directive tells the router to skip trivial and conversational turns — routing overhead would cost more than it saves there — so short follow-ups stay direct. With no flag the hook exits silently and injects nothing.

Manual installs do not pick up the hook (symlinking the skill registers no hooks). To get it without the plugin, point a `UserPromptSubmit` hook in `~/.claude/settings.json` at your checkout's `hooks/auto-route.sh`.

## Opus orchestrator mode

The inverse of fable-router: instead of Fable delegating down, an **Opus 5 session acts as a pure orchestrator** — it thinks, decomposes, delegates, and reviews, but never edits. Useful when Opus 5's direct coding underwhelms but its orchestration holds up, and when you want Fable spent only on judgment.

Enforcement is mechanical, not prompt-based. While the flag file `~/.claude/opus-orchestrator` exists, the plugin's `PreToolUse` hook (`hooks/orchestrator-guard.sh`) denies the **main agent's** `Write`/`Edit`/`NotebookEdit` and any Bash beyond read-only inspection and test/lint commands (`hooks/orchestrator-bash-filter.py`, default-deny). Subagent calls pass untouched — their hook input carries `agent_id`, the main agent's never does. Deny reasons steer the model toward delegation. A `UserPromptSubmit` hook (`hooks/orchestrator-mode.sh`) injects the orchestrator posture each turn.

Implementation goes to workers pinned by frontmatter model ID, so the tiers hold regardless of what the `opus` alias resolves to:

| Agent | Model | Effort | Role |
| --- | --- | --- | --- |
| `fable-router:coder-opus48` | `claude-opus-4-8` | high | complex implementation, cross-file refactors, tricky debugging |
| `fable-router:coder-sonnet` | `claude-sonnet-5` | medium | standard implementation, test writing, moderate fixes |
| `fable-router:scout` | Haiku 4.5 | low | read-only recon (built-in Explore would inherit the expensive session model) |
| `fable-router:advisor` | `fable` | high | persistent senior advisor, read-only |

Fable is consulted only at mandatory triggers (architecture decisions, twice-failed validation after a tier escalation, conflicting evidence, final review of high-consequence changes), as **one persistent advisor agent** continued via SendMessage rather than respawned per question. With `advisor=none` — e.g. once your Fable quota is spent — the triggers resolve via AskUserQuestion instead.

```
/opus-orchestrator on              # advisor=fable (default)
/opus-orchestrator on advisor=none # pure Opus mode, no Fable at all
/opus-orchestrator advisor none    # switch advisor while staying on
/opus-orchestrator status
/opus-orchestrator off
```

Notes:
- The skill cannot switch your session model. Pin it per project with `"model": "claude-opus-5"` in `.claude/settings.json`, or use `/model`.
- Requires the plugin install (hooks). Manual installs must wire `orchestrator-guard.sh` (PreToolUse, matcher `Write|Edit|NotebookEdit|Bash`) and `orchestrator-mode.sh` (UserPromptSubmit) in settings themselves.
- Don't run it together with fable-router auto mode — one assumes a Fable parent, the other an Opus parent. `/opus-orchestrator on` warns if both flags are set.
- The Bash filter aims to make bypasses hard, not impossible: the enforcement target is model drift, not an adversary.
