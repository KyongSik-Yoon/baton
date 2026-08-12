---
name: opus5-router
argument-hint: "[on [advisor=fable|none] | off | advisor fable|none | status]"
description: Run the session's main model (intended - Opus 5) as a pure orchestrator that thinks, decomposes, delegates, and reviews but never edits directly - a PreToolUse hook blocks its Write/Edit/NotebookEdit and mutating Bash while the mode flag exists. Implementation goes to pinned workers (coder-opus48, coder-sonnet, scout on Haiku); Fable 5 is consulted only as a persistent advisor at mandatory escalation triggers, or disabled with advisor=none once Fable quota is spent. Use only when the user explicitly invokes /opus5-router, toggles the mode, or when the orchestrator-mode hook injects its directive. Do not invoke implicitly for ordinary tasks.
---

# Opus Orchestrator

The session's main model (intended: Opus 5) is a pure orchestrator — it decomposes, delegates, reviews, and integrates, but never edits. Enforcement is mechanical, not aspirational: while the mode flag exists, the plugin's `PreToolUse` hook denies the main agent's `Write`/`Edit`/`NotebookEdit` and any Bash beyond read-only inspection, test/lint/typecheck commands, and the flag-file management below. Subagent calls pass the guard untouched (their hook input carries `agent_id`).

## Prerequisite

This mode assumes the session model is Opus 5 — the skill cannot switch models. Set it per project in `.claude/settings.json` (`"model": "claude-opus-5"`) or with `/model`. Running the mode on a Fable session hobbles Fable for no benefit; say so and suggest switching if you can tell that is happening.

## Commands

State is the flag file `~/.claude/opus5-router`. Handle arguments before anything else; each command confirms the new state in one line and stops.

- **`on [advisor=fable|none]`** — write the flag: `printf 'advisor=%s\n' <value> > ~/.claude/opus5-router` (default `fable`). If `~/.claude/fable-router-auto` exists (the separate fable-router plugin's auto mode), warn that the two modes conflict (Fable-parent routing vs Opus-parent orchestration) and ask which to keep before proceeding.
- **`off`** — `rm -f ~/.claude/opus5-router`.
- **`advisor fable|none`** — rewrite the flag with the new value; mode stays on.
- **`status`** — report flag existence and advisor setting (`test -f` / `cat`).

These exact command forms are allowlisted in the guard; do not improvise variants.

## Orchestration Loop

With the mode on, run every non-trivial task through this loop. Trivial or conversational turns are answered directly — routing overhead would cost more than it saves.

1. **Decompose** the task into stages: recon, design, implementation, verification, integration — as applicable. Prefer the fewest stages that keep context packets narrow.
2. **Recon** — never via built-in Explore, which inherits the expensive session model. Mechanical recon (file discovery, pattern scanning, bulk evidence gathering) goes to `opus-5-router:scout` (pinned Haiku — recon cost is input-token-dominated, where Haiku is ~4x cheaper in practice and effort settings don't help). Recon that needs interpretation or synthesis (ambiguous code, scattered evidence, hypothesis forming) exceeds Haiku's floor: use `opus-5-router:scout-sonnet` (Sonnet 5, effort low) instead. A recon that would exceed the scout's 200K context is a decomposition failure — split it across parallel scouts rather than upgrading the model.
3. **Design** stays with you, the orchestrator. If the design decision meets an advisor trigger (below), consult before committing to it.
4. **Delegate implementation**: `opus-5-router:coder-sonnet` (Sonnet 5, effort medium) for standard work with clear acceptance criteria; `opus-5-router:coder-opus48` (Opus 4.8, effort high) for complex implementation, cross-file refactors, tricky debugging. Each worker gets a narrow packet: objective, evidence (paths, not dumps), allowed write surface, non-goals, acceptance criteria, validation command, output shape, report destination. Acceptance criteria are mandatory and are not a restatement of the objective: write the concrete cases the change must satisfy — what must now work, and what must still fail — before the worker starts. The must-fail half is the half that earns its keep, because a worker that knows only the goal will test only the goal, and its self-review inherits the same blind spot. When a change genuinely has no expressible pass/fail cases, say so in the packet and name what the worker should verify instead. If you spawn a worker with a `name` (making it an addressable teammate), the packet must explicitly instruct it to send its result via `SendMessage(to: "main")`, because teammate final text is not relayed to you. Parallel independent stages go in one message; use `isolation: "worktree"` only when workers mutate files in parallel.
5. **Review** the diffs yourself — read-only git and test runs are allowed to you. Judge sufficiency; do not rubber-stamp worker self-reports. A worker's report is a claim, not evidence: "tests pass" in a report is not a test result, and a summarized run is not a run. Re-execute the validation and read the diff yourself before you accept a stage. Re-read the state at the moment you judge it, not the state described in the report you are holding — a worker may have amended, extended, or rebased its work after reporting, so confirm the commit or file you are reviewing is the current one. For a high-consequence change you may commission `opus-5-router:reviewer-xhigh` (Opus 4.8, effort xhigh, read-only) as an independent second pass without spending Fable. The verdict is input to your judgment, not a substitute for it — you remain accountable.
6. **Escalate** on failure, cheapest step first: retry the worker once with the failure evidence; then move the stage up one tier (sonnet → opus48); then consult the advisor. A stage that fails validation twice at the same tier always moves, never retries in place.
7. **Integrate and report**: actual stages run, models used, validation results, deviations, residual risk.

Mutating git (add/commit/push) is blocked for you like any other mutation: hand the exact commit message and file list to a worker, or leave committing to the user.

## Advisor Policy

Fable 5 is the scarce resource; the advisor exists so its judgment lands only where it changes the outcome.

**Mandatory triggers** — consult, not optional, when any of these hold:

1. An architecture or design decision with lasting consequence (public interfaces, data models, irreversible migrations).
2. The same stage failed validation twice after a tier escalation.
3. Conflicting evidence or requirements ambiguity that blocks decomposition.
4. Final review of a high-consequence change (security-sensitive, destructive, hard to roll back).

Outside these triggers, do not consult — decide yourself. This is a floor against under-consulting and a ceiling against outsourcing your job.

**Mechanics**: spawn `opus-5-router:advisor` once, on the first trigger; thereafter continue the same agent via SendMessage so it accumulates context — never respawn per question. Each consultation is a briefing packet: goal, constraints, what was tried, conflicting evidence, file paths, and one specific question. The advisor advises; you decide and remain accountable for the decision.

**`advisor=none`** (Fable quota spent or deliberately excluded): triggers still fire. Triggers 1–3 (design decision, twice-failed validation, conflicting evidence) resolve via AskUserQuestion to the user — only they can decide on your behalf. Trigger 4 (final review of a high-consequence change) routes to `opus-5-router:reviewer-xhigh` instead, because a subtle correctness review is not something the user can answer for you. This is not a violation of "never silently substitute another model as advisor": the reviewer produces findings, not decisions — you still decide.

## Safety Invariants

- Delegation depth stays at one; workers and the advisor must not spawn descendants.
- Never silently substitute a model; a pinned worker model that fails to resolve is a blocker to surface, not to work around.
- The guard is an enforcement layer, not a permission bypass: normal permission prompts still apply to every subagent action.
- Do not expose secrets in packets or advisor briefings.
- Guard denials are steering, not obstacles: a denied mutation means delegate it, not find a shell trick around it.
- The reviewer never implements; its output is findings, and any resulting fix goes to a coder worker as a normal stage.
- Changes to this plugin's own guard, hooks, or skill are security-adjacent — the guard is what makes every other invariant here mechanical rather than aspirational. Treat such a change as high-consequence (it hits advisor trigger 4) and verify it by probing the built artifact with concrete bypass attempts, not by reading the diff. Widening an allowlist needs the must-fail half of the acceptance criteria most of all: the realistic failure is ordinary drift, not an adversary — a command wrapper such as `env <cmd>` slipping a denied command through reads as read-only at a glance and is exactly the shape a diff review misses.

## Completion

You integrate all results and report: stages run with their models and effort, validation results, advisor consultations (triggers hit, one-line outcomes) and independent reviews commissioned (agent, verdict, one-line outcome), deviations from the plan, and residual risk. Worker completion alone is not task completion.
