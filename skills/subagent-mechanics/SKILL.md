---
name: subagent-mechanics
description: Writing subagent definitions. Use when creating or editing an agent file (agents/*.md) — its description, report contract, tool grant, or model/effort tier.
---

An agent definition is a system prompt wrapped in a harness contract (`tools`, `model`, `effort`). An agent runs **one-shot**, unattended, in its own context, and returns a single report. Those three facts decide everything below. Nobody can correct it mid-run, so fix what must come out the same every time (the report, the bound on each tool, the default at each fork) and leave the method as free as the work needs.

The subagent branch of [`/writing-for-agents`](../writing-for-agents/SKILL.md), which carries the universal reference for any document an agent reads — degrees of freedom, context pointers, the two loads, the information hierarchy, completion criteria, leading words, reasons and examples, and pruning. The rules below are what changes when the document is an agent definition; everything else about writing it is there.

## The description

The description is always loaded in every spawning session — it spends tokens and attention there every turn, so it earns hard pruning. It does two jobs: state what the agent is, and list the distinct triggers that should fire it.

- Front-load the word that does the invocation work.
- One trigger per distinct case; synonyms restating one case are duplication — collapse them.
- Cut method that belongs in the body — the description triggers the dispatch, it doesn't explain the work.
- State the delegation posture: "Use proactively when…" invites auto-delegation; "Invoke explicitly…" reserves the trigger for the human.
- Routing redirects ("not for X — that's the Y agent") earn their tokens: they steer the spawner across the roster, which no single body can do.
- When a run is slow or expensive, say so ("a run takes minutes") — the spawner is deciding whether to dispatch, and cost is trigger-relevant.

## The body is a system prompt

- **Anchor with pretrained words.** A compact concept the model already holds (*scout*, *smoke-test*, *surgical*) anchors a region of behavior in few tokens. Prefer one strong word over a spelled-out triad.
- **Delete no-ops.** An instruction the model already follows by default pays load to say nothing. Test each line: does it change behavior versus the default?
- **Pair every prohibition.** For format and style, state the target behavior. For scope and guardrails, a prohibition works when it names the specific thing and says what to do instead ("never edit — describe the edit in the report instead"). The pairing matters *more* for agents: one told only what not to do has no user to ask what to do.
- **One meaning, one place.** Each rule lives in exactly one spot, so changing the behavior is a one-place edit.
- **Prune on every touch.** Stale layers settle because adding feels safe and removing feels risky; check each line still bears on what the agent does.

## Self-containment

An agent is a lone file with no bundled folder. What reaches it at startup: its own body, the dispatch prompt, the `CLAUDE.md` files of the repo it runs in (unless it sets `omitClaudeMd: true`), and the full content of every skill named in its `skills:` frontmatter. Inline what is specific to the agent. Rules the repo's `CLAUDE.md` carries need no restating, but an agent meant to run in any repo can't count on one being there.

Reference that already lives in a skill comes in through `skills:`, not by copying it or pointing at the skill's file. The skill loads in full on every run, so list one only when every run needs it, and a skill with `disable-model-invocation: true` can't be listed at all.

A file pointer is allowed only at a repo file with a stable path, guarded by an existence check and a default ("read `defaultBranch` from `.nk-config.json`; absent, default `main`"). Never point an *agent definition* at a skill's or another agent's file: a skill gets a base directory and its siblings ship with it, but an agent has no guaranteed neighbors — so the reference resolves for *you* while editing, then breaks in the context where it fires. Skills pointing at their siblings are fine, and this file does it above.

The description has no opt-out — every agent pays its always-loaded cost. So creating an agent asks a hard question: does this work recur often enough, and cost enough main-session context, to earn a permanent description slot? If the main session could write the prompt ad hoc, it doesn't.

## The report contract

The agent-shaped completion criterion, and the highest-leverage section in the file. The report is the agent's only product; a fuzzy contract is where rushed, thin work shows up.

- Make it literal: a fenced template, not prose.
- Bound it against dumping — the agent exists to absorb noise, so say what to *omit* ("surprises only, never full logs"; "last ~10 lines of stderr").
- Write the empty case ("if zero edits, say so and end") — an unwritten empty case invites padding.

## Least-privilege tools, mirrored in hard rules

The `tools:` allowlist is the outer wall; hard rules draw the boundary the allowlist can't express. Every granted tool that can mutate state needs a matching rule bounding its use: Bash for git reads → "no state-mutating git commands"; Write for one deliverable → "at most ONE file". A mutation path with no bounding rule is an unlocked door.

## Decided forks

One-shot means no mid-run clarifying questions — every fork the agent can hit needs a decided default written down ("if only one source exists, verify against it and record the other as missing"; "state the reading you chose at the top rather than guessing silently"). Audit for undecided forks: each one is a variance bug. When a fork genuinely needs the orchestrator, the default is "return the question as your report" — the agent can't pause, only finish.

## Model and effort triage

Match the tier to the work: mechanical run-and-report → haiku/low; bounded summarization and doc updates → sonnet; work where rework is the dominant cost — implementation, review, verification against a spec — → opus, effort raised where the reading is dense. Omitting a field is also a choice: an absent field inherits the spawning session's setting, right when the work should scale with the session (an implementer that pins `model` but omits effort, so raising session effort lifts every dispatch). Pick pin-or-inherit deliberately per field.

## When a skill dispatches the agent

The agent definition owns the method; the skill carries orchestration only. A skill's fallback branch must stand alone — it fires precisely when the agent (and its file) is out of reach.

The dispatch prompt is the **brief**, and it is all the caller passes: the agent sees none of the conversation. A brief carries the objective and what the result is for; what is already known or ruled out; the paths, error text, and decisions the agent needs, by value; the boundaries (what is in scope and what to leave alone); and what to return, where that differs from the definition's report contract. A dispatching skill writes the brief as a template with those slots, so the orchestrator fills in facts instead of composing one from memory.
