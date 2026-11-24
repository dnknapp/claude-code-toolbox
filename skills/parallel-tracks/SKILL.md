---
name: parallel-tracks
description: Split a body of work into self-contained tracks and implement them with parallel track-implementer agents. Use when the user asks to run implementation work in parallel or "spin up sub-agents", sweep a set of issues, or fix N folders/activities/components independently. Also use proactively, without being asked, when remaining implementation work decomposes into ≥3 similar self-contained tracks whose shared contracts already exist — including mid-session, when work you started inline becomes delegable.
---

Orchestrate bounded implementation work across parallel `track-implementer` agents. You (the main session) stay orchestrator: triage, dispatch, escalate, review — you don't implement.

## 1. Define the tracks

From the user's request (an issue list, a folder list, a fix batch), derive tracks where each is:

- **Self-contained** — completable without editing files another track touches. If two candidate tracks share files, merge them into one track.
- **Scoped** — expressible as "these folders/files, this goal." The scope line goes verbatim into the agent prompt.
- **Verifiable** — `npm run check` plus the track's own acceptance criteria can tell whether it's done.

**Granularity: a track is a feature slice, not a file.** ~5+ related files or one self-contained subsystem. Dispatch overhead is a fresh agent's re-orientation (~25× the cost of a warm inline edit), so single components never earn their own track — but don't keep leftovers inline either: merge each small item into the most-related track. Delegation pays through cheaper-tier implementers, preserved orchestrator context, and parallelism — never through per-item token savings, so don't use "inline is cheaper for this one file" as a reason to keep typing once a wave is justified.

**Tracks must never invent shared interfaces.** If two candidate tracks would each need to create or shape a shared component, token, contract, or convention, that shared piece is a prerequisite: build it first, *then* fan out. Fanning out before shared contracts exist produces N slightly-different inventions — drift, not parallelism. Shared/global changes (a shared component, global styles, config) are their own track, run **before** the parallel wave if others depend on it — or handled by you directly if trivial.

Show the user the track list (scope + goal + tier per track) before dispatching if you merged, dropped, added, or re-scoped any track relative to what they enumerated; when tracks map one-to-one to their list, dispatch straight away.

## 2. Triage each track to a model tier

Route by explicit criteria, not vibes:

- **opus (default)** — this is `track-implementer`'s own `model:`, so express it by **omitting the `model` param** and letting the agent file decide. Multi-file features, cross-cutting changes, debugging with an unknown root cause — anything where a stubbed or half-finished track costs a re-dispatch.
- **sonnet (downgrade)** — pass `model: sonnet` only on explicit signals that the track is mechanical: clear spec, an existing in-repo pattern to copy, bounded to a handful of files. Styling/layout/contrast fixes, component ports following existing shapes, config tracks, mechanical refactors.
- **fable (rare, dispatch-time only)** — a track that is known-hard at triage: frontier-difficulty work you would otherwise have kept inline. Never reached by escalation — it's a deliberate triage decision, and the default answer is "keep it inline with the orchestrator instead."
- **haiku — verification work only** (smoke runs, probes). A failed implementation track costs more than the tier saves.

When unsure, omit `model` — the agent file's default applies, and it is the single source of truth for what that default is.

Effort: `track-implementer` pins none, so a track runs at the session's effort unless its dispatch passes `effort`. For one known-hard track, pass a higher `effort` on that dispatch (`effort: high`). When the whole wave is hard, raise the session effort before dispatching, which lifts every implementer. Pass none lower than the session's: nothing has measured an implementer there.

## 2a. Budget the wave

Before each dispatch, run `/usr/bin/python3 ~/.claude/hooks/dan-cache-cold-guard.py --usage` for the plan's 5-hour and weekly usage; its 5-hour % is the wave's *before*. A wave's cost is its *after* minus *before*, from the run file's wave log. Budget from the last wave with a measured cost; a wave whose 5-hour window reset mid-flight has none. With no wave measured yet, dispatch and measure. When current usage plus that cost would pass 90% before the window resets, pause at this boundary instead, per the dan-handoff skill's usage-limit section. A wave cut off by the limit mid-flight loses more than the wait costs.

## 3. Dispatch

Say what is launching, in one line, in the message that dispatches it, and don't wait for an answer: `Wave <n>: <k> tracks (<j> opus, <m> sonnet), then <reviewer | reviewer and issue-verifier> on the combined diff. 5-hour usage <x>%<, last wave cost <y>%>.` A wave is the largest cost a session runs up and often starts without the user asking, so this line is where they see it before it lands.

Dispatch with the tree on a feature branch (CLAUDE.md, merge rule), never on `dev` or `main`: step 6 commits to whatever branch the tree is on.

Spawn all independent tracks in a single message (parallel `Agent` calls), each with `subagent_type: track-implementer` and `model` set **only for downgraded tracks** (the per-invocation `model` overrides the agent file's default — omit it for default-tier tracks so the agent file stays authoritative). Each prompt contains: the scope line, the goal, acceptance criteria, any relevant issue numbers or plan-doc paths, and the wave brief — nothing else; documented conventions are the agent's job to read.

**The wave brief** carries contracts invented this session that aren't yet in any rules file — new tokens, sizing/type conventions, component shapes, API contracts. Write it once, paste the identical block into every prompt. Never ask implementers to infer session decisions, and never write session decisions into `AGENTS.md` just to dispatch — promote a contract to a rules file only when it has recurred across waves and the user agrees it's settled. When a plan doc for the wave already exists, it serves as the brief; reference it by path instead of duplicating it.

Don't tell a track to revert its change to watch a test fail. In a shared tree the revert breaks the sibling tracks' checks, and the implementer's own rules say how to show it.

## 4. Escalation on failure

If a track returns FAIL on `npm run check`, BLOCKED, or its review findings (step 5) show it missed the goal:

- A sonnet-downgraded track: re-dispatch **once** at the default tier (drop the `model` param), with the failure report included in the prompt.
- A default-tier (opus) track: re-dispatch **once** at the same tier with the failure report — the second attempt's value is the diagnosis in the prompt, not a bigger model.
- If that second attempt also fails, the track returns to YOU, the orchestrator — no automatic third dispatch. Two failures on a bounded track usually mean a scoping or spec problem, not a capability shortfall: re-scope it, absorb it inline (you have the cross-track context a fresh subagent lacks), or surface it to the user. Fable is never an escalation rung.
- BLOCKED on an out-of-scope shared file is not a model failure: handle the shared change yourself (or as a new track), then re-dispatch at the same tier.

## 5. Review the combined result

After all tracks report, run the review pass:

- `reviewer` on the combined diff (conventions/standards).
- `issue-verifier` when tracks map to issues or plan docs (spec).

Send a confirmed finding that traces to one track to that track's implementer with `SendMessage`, addressed to the agent id its dispatch returned, so the context it built carries: on 2026-10-09 that took about half the time and a third of the input of a fresh agent given the same finding. Use step 4's escalation only when the findings show the track missed its goal. Fix trivial cross-track issues yourself.

## 6. Aggregate

Commit once the review pass is settled. Implementers never commit, so git is yours: commit each track's files as its own commit on the run's feature branch, staging the paths its report lists, then push and open a draft PR per the merge rule in CLAUDE.md. The user reviews the work there.

Report to the user: per-track status table (track, tier used, escalations, status, files, commit), review-pass summary, the PR link, and anything BLOCKED or unresolved.

Close every wave by running the usage command again for the wave's *after*, then invoking the dan-handoff skill: the run file gets the wave's results and both measured percentages, so the next wave, or a fresh orchestrator, budgets from it.
