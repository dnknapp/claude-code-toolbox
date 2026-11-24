---
name: code-review
description: Review the changes since a fixed point (commit, branch, tag, or merge-base) along three axes — Correctness (is it actually right, reviewed blind and adversarially?), Standards (does it follow this repo's documented coding standards?) and Spec (does it match what the originating issue/spec asked for?). Runs the reviews in parallel sub-agents and reports them side by side. Use when the user wants to review a branch, a PR, work-in-progress changes, a re-review after a fix, a consolidated document checked against its contract, or asks to "review since X".
---

Three-axis review of the diff between `HEAD` and a fixed point the user supplies:

- **Correctness** — is the change actually right, judged from the code alone?
- **Standards** — does the code conform to this repo's documented coding standards?
- **Spec** — does the code faithfully implement the originating issue / spec?

The axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings.

Issues live on GitHub unless the repo's own docs name another tracker: fetch them with `gh issue view <N> --comments`.

## Process

### 1. Pin the fixed point

Whatever the user said is the fixed point — a commit SHA, branch name, tag, `main`, `HEAD~5`, etc. If they didn't specify one, ask for it.

Capture the diff command once: `git diff <fixed-point>...HEAD` (three-dot, so the comparison is against the merge-base). Also note the list of commits via `git log <fixed-point>..HEAD --oneline`.

Before going further, confirm the fixed point resolves (`git rev-parse <fixed-point>`) and the diff is non-empty. A bad ref or empty diff should fail here — not inside three parallel sub-agents.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. Issue references in the commit messages (`#123`, `Closes #45`, GitLab `!67`, etc.) — fetch per the tracker workflow above.
2. A path the user passed as an argument.
3. A spec file under `docs/`, `specs/`, or `.scratch/` matching the branch name or feature.
4. If nothing is found, ask the user where the spec is. If they say there isn't one, the **Spec** sub-agent will skip and report "no spec available".

### 3. Identify the standards sources

Anything in the repo that documents how code should be written, such as `CODING_STANDARDS.md` or `CONTRIBUTING.md`.

On top of whatever the repo documents, the Standards axis always carries a fixed **smell baseline** (Fowler, _Refactoring_ ch.3). The `reviewer` agent carries the baseline in its own definition, along with its binding rules (repo standards override; every smell is a judgment call; skip anything tooling enforces). The `general-purpose` fallback (step 5) runs without the baseline or the agent's test-scrutiny questions — documented standards only; note that degradation in the final report.

### 4. Brief the Correctness axis

What a reviewer is *given* decides what it can find, so this axis takes a prompt you build rather than a diff base alone. Two shapes, picked by what changed:

- **Code** — the default. The `blind-reviewer` agent carries its own method, so pass only what it cannot know: the repo path, the PR number (or the branch and diff base), the issue numbers, the authority file, the depth, a budget if the user named one, a scratchpad directory if the session has one, any follow-up issue already holding a deferred problem so it isn't re-reported, and **the adversarial targets specific to this change**.

  The targets are the part worth thinking about, and the one part the agent cannot supply itself. Name what could go wrong *in this change* — the two events that can interleave, the two values that can disagree, the external API whose error shape is assumed, the wait that something else could land inside of. Its standing targets are its own; don't restate them.

  **Ask for a strict review when the PR argues its own case.** A detailed, well-reasoned description is the danger: a reviewer that reads it checks the change against the argument instead of judging it. Strict puts the description, issue discussion and commit bodies out of bounds — and you have to ask, since the agent reads them by default.

  **Pick the depth, and say it as you dispatch.** Depth is how much the agent runs, which is what this axis costs: *focused* (typecheck and the in-process test files covering the change), *standard* (plus the in-process suites and mutation), *deep* (plus browser and e2e suites, and repeated runs). When the user named one, pass it as theirs. Otherwise pass your own marked as a pick — `Depth: focused (a pick)` — which the agent may raise: *standard* when the diff changes logic, tests, dependencies or build config, or this is a re-review after a fix; *focused* for everything else. Deep only ever comes from the user: when the change touches concurrency or timing, or a flow only e2e exercises, offer it and carry on at your pick without waiting. In the message that dispatches step 5, tell the user in one line — `Correctness at <depth>: <why>. Expect about <n> minutes, <why that long>.`, plus `Deep would add <what>.` when you are offering it — and don't wait for a reply: the line is so they know what is running and why it takes as long as it does, not a request for approval. Depth sets what the agent runs, not how long it takes: expect 3–5 minutes on a small or cosmetic diff and up to the agent's 15-minute budget on logic it has to build probes for, at focused and standard alike. Deep has no budget.

- **Derived document** — when the change merged, split, or rewrote documents. A whole-diff review of prose returns nits; instead pass the artifact, the contract path it must agree with, and the sources it came from (paths, or `git show <sha>~1:<path>` for ones the change deleted). The agent runs contradictions / lost content / usability against them.

**Run this axis again on the fixes.** The second pass is where a defect introduced *by the first pass's fixes* shows up. Fixes made while the review ran get it every time (step 6). A fix made later gets it when it adds new surface: a race fix, a change to verify logic, a fix that introduces a shell command. Resume the same reviewer while this session can still reach it, since it keeps its copy and its reading. From a later session, dispatch a fresh one with `effort: medium`, the same brief and the new commits; a depth the user named carries over, a pick is made again.

### 5. Spawn the sub-agents in parallel

Send a single message with one `Agent` tool call per axis still in play (three unless an axis was skipped below):

**Correctness** — `subagent_type: blind-reviewer`, with the brief from step 4. Keep session context out of it: what you already believe about the change is exactly what this axis exists not to inherit.

**Standards** — `subagent_type: reviewer`. Prompt: the fixed point (diff base), the commit list, and any standards-source files found in step 3 that the agent wouldn't find on its own (it already walks CLAUDE.md/AGENTS.md/rules/ itself). The agent carries its own brief, baseline, and report shape.

**Spec** — `subagent_type: issue-verifier`. Prompt: the fixed point, the commit list, and the spec source from step 2 (issue number and/or spec/plan path). The agent reconciles issue + plan doc itself and reports disagreements between them as findings.

**Fallback:** if an agent type is unavailable (repo/machine without them installed), fall back to `general-purpose` — on `opus` for Correctness, which needs the tier — with this brief —

Correctness takes one of two briefs, per the shape chosen in step 4. Keep them fenced, never quoted: a quoted brief needs escaped inner quotes, and an escaped quote pasted into a shell becomes a literal character that silently redirects the copy into the repo it promised not to touch.

**Correctness, code shape:**

```
Adversarially review this change, forming your view from the code; the PR description is a
claim to check. <Strict only: Do not read the PR description, the issue discussion, or
commit-message bodies — git log --format=%h and git show --format= suppress them. The code,
the tests, the committed docs and published API schemas are your only sources.> First copy
the repo (use <scratchpad dir> if one is named here instead of mktemp), then read and run only
in the copy, since the original may change while you work:

  DEST=$(mktemp -d) && rsync -a --exclude node_modules "<repo>/" "$DEST/" && cd "$DEST"

There, read the full diff and every caller it touches, and read <authority file>. Send each
finding to main with SendMessage the moment you settle it, worded as it will be in the report,
and carry on without waiting. Below deep you have <budget, 15 unless the user named one>
minutes: past that, finish the probe in hand and list the rest as claims you could not verify.
Start slow commands in the background and work on something else meanwhile.

Depth: <focused | standard | deep><" (a pick)" unless the user named it>. Focused runs the
typecheck and the in-process test files covering the changed paths; a covering test that
drives a browser waits for deep. Standard adds the suites that run in-process, and mutation. Deep adds the suites that drive a browser or a running app, and
three runs of the suite if the change touches concurrency or timing. Run only what your depth
includes: below deep, call the unit runner directly or pass it test files by path to keep
browser suites out. Where the project's docs mark a suite off-limits, leave it unrun at every
depth; where they mark one slow, leave it unrun below deep and, at standard, mutate against
the test files covering the change in its place. A depth marked a pick is yours to raise from
focused to standard if the diff turns out to carry logic. A depth without that mark is the
user's: run it as named, and if you would have picked a heavier one, say which and why in the
verdict line.

For mutation, at standard and deep, remove or invert in turn each new branch a test executes.
One that leaves the suite green is a test that cannot fail — name it. Report the whole result,
not just the survivors: how many tests each removed guard turned red, and any branch that
survives only because a neighboring line catches the same inputs. A branch no test executes
needs no mutant: name it as unpinned. Where a finding turns on a call failing, inject that
failure and watch where control lands. If no test reaches the logic under review, say so —
then build one probe rather than settling for inspection: bundle the module under review with
its real dependencies into a throwaway script in the copy, stub only what it reaches outside
itself, drive it, and run the unchanged path as a control. Say what you built and what you
stubbed, and report which guards the change leaves unpinned.

Targets: <the targets from step 4>.

Report a verdict line (approve / approve with nits / request changes) naming the depth you
ran at, whether you raised it, and each suite you left unrun and why. Then findings ranked
worst-first with file:line, a concrete failure scenario, and CONFIRMED (traced or ran it) or
PLAUSIBLE. Then what you attacked and could not break, and how you attacked it — that tells
the reader what not to re-review. End with claims you could not verify and the probe that
would settle each.

The original repo is read-only: run and mutate only in the copy, write nothing outside it,
and every git and gh command you run is a read. Stop only processes you started, by pid, never
with pkill or killall. Skip style nits. Under 600 words.
```

**Correctness, derived-document shape:**

```
<artifact> was produced from <sources, or their git show <sha>~1:<path> refs>, and
<contract path> wins over it wherever they disagree. Read all of them and run three checks,
reporting the result of each by name, clean ones included:

1. Contradictions — every rule and table row against the contract; report each place the
   document would send a person to a different action.
2. Lost content — every instruction, recovery step, timing fact or warning in a source that
   now appears nowhere. Pure duplication and history don't count.
3. Usability — read it as each audience it names; report any step that cannot be followed as
   written.

Report a verdict line, then findings with file:line and the contract section or source line
each conflicts with. Read-only. Under 600 words.
```
- Standards: "Report — per file/hunk where relevant — every place the diff violates a documented standard: cite the standard (file + rule). Distinguish hard violations from judgment calls. Skip anything tooling enforces. Under 400 words."
- Spec: "Report: (a) requirements the spec asked for that are missing or partial; (b) behavior in the diff that wasn't asked for (scope creep); (c) requirements that look implemented but wrong. Quote the spec line for each finding. Under 400 words."

A fallback report is shaped differently from the agent's own — no *Checks* section, no mutation evidence unless the fallback managed it. Note which axes ran degraded in the final report, as step 3 already requires for Standards.

If the spec is missing, skip the Spec sub-agent and note this in the final report. For a docs-only sweep, skip Correctness unless a document was derived from others — otherwise Standards carries it alone.

### 6. Fix as Correctness findings arrive

The blind reviewer sends each finding to this session as it settles it, minutes ahead of its report. What you do with one depends on whose change this is:

- **This session's own change** (you wrote it, or the user asked you to fix what the review finds): fix each CONFIRMED finding as it arrives, unless its fix is a design choice. One commit per finding when the change under review is already committed, so a single fix can be reverted; fixes to uncommitted work stay uncommitted with it. Hold every PLAUSIBLE finding and every design choice for the user: it goes in the summary unfixed.
- **Anyone else's change** (a second opinion on a PR): fix nothing. The findings wait for the report.

When the reviewer's report arrives and you made fixes, resume it with `SendMessage` to its agent id, naming the fix commits (or the files, for uncommitted work) and asking for a re-review of them. With no fixes made there is nothing to resume.

### 7. Aggregate, then close the Correctness loop

Present the reports under `## Correctness`, `## Standards` and `## Spec` headings, verbatim or lightly cleaned. A re-review's report follows the first under `## Correctness`, and each Correctness finding is marked fixed, with its commit, or held, with why. Do **not** merge or rerank findings — the axes are deliberately separate (see _Why three axes_).

The Correctness report's *Could not verify* list is addressed to you: run the probes that are cheap and available (a live API read, a 30-second experiment) and record what each showed. That list is the axis's second product — a reviewer naming what it could not settle is what makes settling it possible. A deep run on that list, or a verdict line saying the agent would have picked a heavier depth, is the user's call: end your summary with it as an offer to re-run.

When Correctness and Standards both flag the same test as unable to fail, keep the Correctness one when it carries a mutation result: the branch that survived is the proof the other axis can only ask for.

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes — that's the reranking the separation exists to prevent. Findings you accept as-is stay in the report with one line on why.

## Why three axes

A change can pass one axis and fail another:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**
- Code that satisfies the issue and every convention but loses a race → **Standards pass, Spec pass, Correctness fail.**

Reporting them separately stops one axis from masking another. The axes also differ in what they may *do*: Correctness runs tests and probes in a scratch copy, while Standards and Spec are reading-only by design and name the verification they'd need instead.
