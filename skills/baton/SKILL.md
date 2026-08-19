---
name: baton
argument-hint: "[on [advisor=fable|none] [parent=opus|fable] [style=on|off] | off | advisor fable|none | parent opus|fable | style on|off | status]"
description: Run the session's main model (Opus 5 or Fable 5) as a pure orchestrator that thinks, decomposes, delegates, and reviews but never edits directly - a PreToolUse hook blocks its Write/Edit/NotebookEdit and mutating Bash, and caps how much it reads into its own context, while the mode flag exists. Implementation goes to pinned workers (coder-opus48, coder-sonnet, scout on Haiku). Under an Opus parent, Fable 5 is consulted as a persistent advisor at mandatory escalation triggers (or disabled with advisor=none once Fable quota is spent); under a Fable parent the orchestrator is itself the top judgment tier and the advisor is an opt-in second opinion. Use only when the user explicitly invokes /baton, toggles the mode, or when the orchestrator-mode hook injects its directive. Do not invoke implicitly for ordinary tasks.
---

# Orchestrator Mode

The session's main model is a pure orchestrator — it decomposes, delegates, reviews, and integrates, but never edits. Enforcement is mechanical, not aspirational: while the mode flag exists, the plugin's `PreToolUse` hook denies the main agent's `Write`/`Edit`/`NotebookEdit` and any Bash beyond read-only inspection, test/lint/typecheck commands, and the flag-file management below. Subagent calls pass the guard untouched (their hook input carries `agent_id`). The guard never inspects the parent model, so enforcement is identical under either parent profile. One exception: the plan-mode plan file under `.claude/plans/` is written by the orchestrator directly, since Claude Code's plan mode restricts that write to the main agent and workers inherit plan mode too — everything else is still delegated.

The same hook also caps what you **read**. Blocking your writes saves output tokens, but your bill is dominated by input: a file you pull in yourself is context you pay for on every later turn, whereas a scout pays for it once and hands back a summary. So a whole-file read past 64 KB, or a bounded read asking for more than 800 lines, is denied to the main agent — via `Read` and via Bash alike (`cat`, `nl`, an unbounded `sed`, an oversized `head -n`). A reader piped into a bounding stage (`cat big | head -20`) passes, as does anything whose volume is unknowable ahead of time (a glob, a file that is not there). The caps are `BATON_READ_MAX_BYTES` / `BATON_READ_MAX_LINES`. When you hit one, the answer is a scout, not a narrower slice repeated ten times.

## Parent model

The mode supports two parent profiles, recorded as `parent=` in the flag file:

- **`parent=opus`** — Opus 5 orchestrates; Fable 5 judgment is imported only through the advisor at mandatory triggers. The economical default when Fable quota is scarce.
- **`parent=fable`** — Fable 5 orchestrates and is itself the top judgment tier; implementation still goes to the cheap pinned workers, and the advisor becomes an opt-in fresh-context second opinion rather than an escalation target.

The skill cannot switch the session model — pin it per project in `.claude/settings.json` (`"model": "claude-opus-5"` or `"model": "claude-fable-5"`) or with `/model`. What it can do is match the profile to reality: on `on` without an explicit `parent=`, default it from your own model identity (`fable` if you are running as Fable 5, otherwise `opus`). If you can tell the recorded profile contradicts the actual session model (e.g. `parent=opus` while you are Fable), say so and offer to rewrite the flag — a wrong profile misroutes the advisor policy, though enforcement is unaffected.

## Commands

State is the flag file `~/.claude/baton`. Handle arguments before anything else; each command confirms the new state in one line and stops.

- **`on [advisor=fable|none] [parent=opus|fable] [style=on|off]`** — write the flag: `printf 'advisor=<a>\nparent=<p>\nstyle=<s>\n' > ~/.claude/baton` with the literal values filled in. Default `parent` from your own model identity as above. Default `advisor`: `fable` when `parent=opus`, `none` when `parent=fable` (a same-model advisor is opt-in, not default). Default `style`: `off`. If `~/.claude/fable-router-auto` exists (the separate fable-router plugin's auto mode), warn that the two modes conflict (fable-router's own routing vs this plugin's orchestration) and ask which to keep before proceeding. If the pre-rename flag `~/.claude/opus5-router` exists, remove it with `rm -f ~/.claude/opus5-router` — it belongs to this plugin's old name and is no longer read.
- **`off`** — `rm -f ~/.claude/baton`.
- **`advisor fable|none`** — rewrite the flag with the new advisor value, keeping the current `parent` and `style`; mode stays on.
- **`parent opus|fable`** — rewrite the flag with the new parent value, keeping the current `advisor` and `style`; mode stays on.
- **`style on|off`** — rewrite the flag with the new style value, keeping the current `advisor` and `parent`; mode stays on.
- **`status`** — report flag existence, advisor, parent, and style settings (`test -f` / `cat`; a flag without a `parent=` line means `parent=opus`, and one without a `style=` line means `style=off`).

These exact command forms are allowlisted in the guard; do not improvise variants. Every rewrite emits three lines via the same `printf 'advisor=<a>\nparent=<p>\nstyle=<s>\n' > ~/.claude/baton` form (a flag written without a `style=` line, or with `style=off`, means style injection is off). The `style=` line, when present, must follow the `parent=` line — that is the only ordering the guard allowlists.

## Style injection

When the flag file carries `style=on`, a `SessionStart` hook (`hooks/style-inject.sh`) injects a per-model communication-style prompt into the session, and a `SubagentStart` hook does the same for subagents whose hook input carries a model. Injection is model-scoped: it fires only for a model that ships a matching `styles/<model-id>.md` file, so an unstyled model sees nothing. The hook resolves the id from the hook input's `model` field, trying it as-is and then with a trailing `-YYYYMMDD` date suffix stripped. It applies to the main session on every `SessionStart` source (startup, resume, clear, compact) but does **not** follow a mid-session `/model` switch, since no hook fires on that. This plugin ships `styles/claude-opus-5.md` (a clear/concise/actionable communication style, adapted from IndyDevDan's "Fixing Opus 5" repo, MIT). To style another model, drop a `styles/<model-id>.md` file using the resolved model id — no code change needed.

## Orchestration Loop

With the mode on, run every non-trivial task through this loop. Trivial or conversational turns are answered directly — routing overhead would cost more than it saves.

1. **Decompose** the task into stages: recon, design, implementation, verification, integration — as applicable. Prefer the fewest stages that keep context packets narrow.
2. **Recon** — never via built-in Explore, which inherits the expensive session model. Mechanical recon (file discovery, pattern scanning, bulk evidence gathering) goes to `baton:scout` (pinned Haiku — recon cost is input-token-dominated, where Haiku is ~4x cheaper in practice and effort settings don't help). Recon that needs interpretation or synthesis (ambiguous code, scattered evidence, hypothesis forming) exceeds Haiku's floor: use `baton:scout-sonnet` (Sonnet 5, effort low) instead. A recon that would exceed the scout's 200K context is a decomposition failure — split it across parallel scouts rather than upgrading the model.
3. **Design** stays with you, the orchestrator. If the design decision meets an escalation trigger (below), resolve it per the Advisor Policy for your parent profile before committing to it.
4. **Delegate implementation**: `baton:coder-sonnet` (Sonnet 5, effort medium) for standard work with clear acceptance criteria; `baton:coder-opus48` (Opus 4.8, effort high) for complex implementation, cross-file refactors, tricky debugging. Each worker gets a narrow packet: objective, evidence (paths, not dumps), allowed write surface, non-goals, acceptance criteria, validation command, output shape, report destination. Acceptance criteria are mandatory and are not a restatement of the objective: write the concrete cases the change must satisfy — what must now work, and what must still fail — before the worker starts. The must-fail half is the half that earns its keep, because a worker that knows only the goal will test only the goal, and its self-review inherits the same blind spot. When a change genuinely has no expressible pass/fail cases, say so in the packet and name what the worker should verify instead. If you spawn a worker with a `name` (making it an addressable teammate), the packet must explicitly instruct it to send its result via `SendMessage(to: "main")`, because teammate final text is not relayed to you. Parallel independent stages go in one message; use `isolation: "worktree"` only when workers mutate files in parallel. One worker per packet: a correction inside the packet you already sent goes back to that worker via `SendMessage`, but anything that makes you rewrite the objective, write surface, or acceptance criteria is a new packet and gets a new worker — a coder accumulates file contents, not judgment, so carrying a finished stage's context into the next one costs more than it saves. The tier rule below caps how long any one worker lives; no separate counter is needed.
5. **Review** the diffs yourself — read-only git and test runs are allowed to you. Judge sufficiency; do not rubber-stamp worker self-reports. A worker's report is a claim, not evidence: "tests pass" in a report is not a test result, and a summarized run is not a run. Re-execute the validation and read the diff yourself before you accept a stage. Re-read the state at the moment you judge it, not the state described in the report you are holding — a worker may have amended, extended, or rebased its work after reporting, so confirm the commit or file you are reviewing is the current one. For a high-consequence change you may commission `baton:reviewer-xhigh` (Opus 4.8, effort xhigh, read-only) as an independent second pass without spending Fable. The verdict is input to your judgment, not a substitute for it — you remain accountable.
6. **Escalate** on failure, cheapest step first: retry the worker once with the failure evidence — via `SendMessage` to that same worker, not a fresh spawn, since it already holds the files and only needs the delta; then move the stage up one tier (sonnet → opus48); then resolve escalation trigger 2 per the Advisor Policy for your parent profile. A stage that fails validation twice at the same tier always moves, never retries in place.
7. **Integrate and report**: actual stages run, models used, validation results, deviations, residual risk.

Mutating git (add/commit/push) is blocked for you like any other mutation: hand the exact commit message and file list to a worker, or leave committing to the user.

## Advisor Policy

The escalation triggers are the same under both parent profiles; what differs is where they resolve.

**Mandatory triggers** — act, not optional, when any of these hold:

1. An architecture or design decision with lasting consequence (public interfaces, data models, irreversible migrations).
2. The same stage failed validation twice after a tier escalation.
3. Conflicting evidence or requirements ambiguity that blocks decomposition.
4. Final review of a high-consequence change (security-sensitive, destructive, hard to roll back).

### `parent=opus`

Fable 5 is the scarce resource; the advisor exists so its judgment lands only where it changes the outcome. On any trigger, consult the advisor. Outside the triggers, do not consult — decide yourself. This is a floor against under-consulting and a ceiling against outsourcing your job.

**Mechanics**: spawn `baton:advisor` once, on the first trigger; thereafter continue the same agent via SendMessage so it accumulates context — never respawn per question. Each consultation is a briefing packet: goal, constraints, what was tried, conflicting evidence, file paths, and one specific question. The advisor advises; you decide and remain accountable for the decision.

**`advisor=none`** (Fable quota spent or deliberately excluded): triggers still fire. Triggers 1–3 (design decision, twice-failed validation, conflicting evidence) resolve via AskUserQuestion to the user — only they can decide on your behalf. Trigger 4 (final review of a high-consequence change) routes to `baton:reviewer-xhigh` instead, because a subtle correctness review is not something the user can answer for you. This is not a violation of "never silently substitute another model as advisor": the reviewer produces findings, not decisions — you still decide.

### `parent=fable`

You are the top judgment tier — escalating a judgment call to another Fable would outsource your own job. Triggers 1–3 you decide yourself, in place; a trigger firing means "stop and judge deliberately", not "delegate the decision". Trigger 4 still needs independence rather than more capability: route it to `baton:reviewer-xhigh`, whose value is a fresh context outside the history that produced the change.

**`advisor=fable`** (opt-in under this profile, not the default): the advisor becomes a fresh-context second opinion on your own tier. Use it sparingly, on triggers where an independent reading of the evidence genuinely adds signal — typically trigger 3 (conflicting evidence) or a trigger-1 decision you keep flip-flopping on. Same mechanics as above: one persistent agent, continued via SendMessage, briefed in packets. Its opinion is input; the decision stays yours.

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
