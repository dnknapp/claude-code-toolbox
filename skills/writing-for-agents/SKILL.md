---
name: writing-for-agents
description: Writing documents for agents. Load BEFORE writing the first line of a skill, AGENTS.md, or CLAUDE.md — including when that file is one step inside a larger build, which is when it gets skipped.
---

Reference for writing any document an agent consumes — a skill, an `AGENTS.md` / `CLAUDE.md`, a doc reached by a pointer. The packaging differs; the writing does not: the same levers set how much of the agent's _process_ the document fixes from run to run, and how reliably the agent reaches it. The terms below (_context pointer_, the two loads, _completion criterion_, _leading word_) are this skill's own vocabulary, not Anthropic's.

When the document you're writing is a skill, read [`SKILL-MECHANICS.md`](SKILL-MECHANICS.md) for frontmatter, limits, invocation choice, and router skills. When it is a subagent definition (`agents/*.md`), read [`subagent-mechanics`](../subagent-mechanics/SKILL.md) for the description, report contract, tool grant, and one-shot discipline.

## Degrees of freedom

Decide first how much of the process the document fixes, and match it to how fragile the work is:

- **Low freedom** — an exact sequence, a script, a literal template — where one wrong move breaks the result or the steps must run in order (a migration, a deploy, a report another program parses). Here **predictability** is the aim: the agent takes the same process every run.
- **High freedom** — the goal, the constraints, and the reasons behind them — where the right move depends on what the agent finds (a review, a design, a diagnosis). Fixing the process here trades the agent's judgment for a script that fits only the cases you imagined.

One document can hold both: free in how it investigates, fixed in how it reports.

## Baseline first

For a new document or a substantial rewrite, run the task in a fresh session without it before writing more than a few lines, and note where the agent goes wrong. Those gaps are what the document is for; whatever the agent already gets right is a no-op you have not written yet. Write the least that closes the gaps, then run the same task with the document, again in a fresh session: the session you wrote it in carries context that hides what the page leaves out. Keep two or three such tasks and re-run them when the document or the model changes.

## Context pointers

A **context pointer** is a reference held in the agent's context that names some out-of-context material and encodes the condition for reaching it. A skill's description is one; a line in `AGENTS.md` naming a doc is the same object. The pointer's _wording_, not its target, decides when the agent reaches the material — and how reliably. A must-have target behind a weakly worded pointer is a variance bug: sharpen the wording first, and inline the material only if sharpening fails.

A pointer does two jobs — state what the material is, and list the **branches** that should trigger reaching it (a branch is a distinct case the document handles, so different runs take different paths through it). Every word of an always-loaded pointer costs on every turn, so it earns even harder pruning than the body:

- **Front-load the leading word** — the pointer is where it does its triggering work.
- **One trigger per branch.** Synonyms that rename a single branch are one branch written twice; collapse them and keep only genuinely distinct branches.
- **Cut identity the body already carries.**

## The two loads

Every document and pointer you add spends one of two budgets:

- **Context load** — the cost of always-loaded material on the agent's window: an `AGENTS.md` line, a skill description, anything sitting in context every turn, spending tokens and attention whether or not it fires.
- **Cognitive load** — the cost on the human: which documents exist and when to reach for each. The human is the index. Not a cost to minimize — it is the price of human agency; spend it where human judgment matters, remove it where it does not.

Material reached only through a pointer escapes context load at the price of the pointer's own line; material with no pointer at all rides entirely on cognitive load.

## Information hierarchy

A document is built from two content types — **steps** (the ordered actions the agent performs) and **reference** (definitions, rules, facts consulted on demand) — that mix freely: all steps (a recipe), all reference (a review's rules, this skill), or both. The core decision is where each piece sits on the **information hierarchy**, a ladder ranked by how immediately the agent needs the material:

1. **In-file step** — the primary tier: what the agent does, in order.
2. **In-file reference** — consulted on demand. Often a legitimately flat peer-set (every rule of a review on one rung) — a fine arrangement, not a smell.
3. **Disclosed reference** — pushed out into a separate file, reached by a context pointer, loaded only when the pointer fires. Spans a sibling file in the same folder through fully external reference that lives anywhere and any document can point at.

Push too little down and the top bloats; push too much and you hide material the agent actually needs. That tension is the whole decision.

**Progressive disclosure** is the move down the ladder — out of the main file and behind a pointer — so the top stays legible. Not primarily a token optimization: it is how the hierarchy is protected. Branching is the cleanest disclosure test: inline what every branch needs, and push behind a pointer what only some branches reach. When a document has steps, in-file reference that should be disclosed buries them and turns attending to them into a coin-flip — a variance lever, not just a legibility one.

**Co-location** is the within-file companion: where the ladder decides _how far down_ a piece sits, co-location decides _what sits beside it_ once there. Keep a concept's definition, rules, and caveats under one heading rather than scattered, so reading one part brings its neighbors with it. The test: the document should read like documentation written for the agent — grouped material reads that way; scattered material does not. (Distinct from duplication: that repeats one meaning in two places; scattering fragments one meaning across many.)

**Sprawl** is the failure mode here: a document simply too long, even when every line is live and unique. Attention thins across the excess, and every extra line is one more to keep relevant. The cure is the ladder: disclose reference behind pointers, and split by branch or sequence so each path carries only what it needs. Anthropic's target for a `CLAUDE.md` is under 200 lines, since longer files are followed less well, and an imported file loads at launch too, so importing moves lines without saving any. A skill's limits are in [`SKILL-MECHANICS.md`](SKILL-MECHANICS.md).

## Steps and completion criteria

Every step ends on a **completion criterion** — the condition that tells the agent the work is done. Two properties make it a lever:

- **Clarity** — can the agent tell done from not-done? A vague bound ("understanding reached") invites **premature completion**: ending the step before it is genuinely done, attention slipping to _being done_. The visible steps still ahead — the **post-completion steps** — supply the pull; the criterion's clarity is the resistance. Defend in order: **sharpen the bound first** (local and cheap); only if it is irreducibly fuzzy _and_ you observe the rush, hide the later steps by splitting the sequence — and hiding only works across a real context boundary (a hand-off or a subagent dispatch; an inline call leaves the later steps in context and clears nothing).
- **Demand** — how much it requires. "Every modified model accounted for" forces thorough work where "produce a change list" does not. Demand drives **legwork** — the digging the agent does within the work, latent in the wording rather than written as its own step — and it is not step-bound: "every rule applied" binds a body of flat reference just as "every step done" binds a sequence, which is how an all-reference document still carries an exhaustiveness bar.

The strongest criteria are both checkable and exhaustive.

A criterion asks for a result, not for the agent's reasoning. A document that tells the agent to write out its thinking, verbatim or in a fixed format, can be refused by current Claude models (the `reasoning_extraction` refusal); ask for a short explanation of the answer or a summary of what was done.

## When to split

Splitting one document into two spends one of the two loads, so split only when the cut earns it:

- **By sequence** — split a run of steps where the post-completion steps tempt the agent to rush the one in front of it. Keeping them out of view drives more legwork on the current task. Beware the reverse: merging sequences exposes each step's later steps to what follows, inviting premature completion.
- **By invocation** — skill-specific: see [`SKILL-MECHANICS.md`](SKILL-MECHANICS.md).

## Leading words

A **leading word** is a compact concept already living in the model's pretraining that the agent thinks with while running the document (_lesson_, _fog of war_, _tracer bullets_). Repeated as a token, never as a sentence, it accumulates a distributed definition and anchors a whole region of behavior in the fewest tokens, by recruiting priors the model already holds. Coining your own works if you define it clearly, but a made-up word recruits no priors — you pay in definition tokens what a pretrained word gives free; reach for an existing word first.

It anchors twice. In the body, _execution_: the agent reaches for the same behavior every time the word appears, and inside flat reference it focuses attention on a class of thing to look for. In a pointer, _invocation_: when the same word lives in your prompts, your docs, and your codebase, the agent links that shared language to the material and reaches it more reliably.

Hunt for opportunities to refactor with leading words. A triad spelled out at three sites, a pointer spending a sentence to gesture at one idea — each is a passage begging to collapse into a single token:

- "fast, deterministic, low-overhead" → _tight_ (a _tight_ loop).
- "a loop you believe in" → _red_ — a fuzzy gate becomes a binary observable state (the loop goes _red_ on the bug, or it doesn't).

You win twice: fewer tokens, and a sharper hook for the agent to hang its thinking on. Assume every document is carrying restatements that leading words retire — go find them.

**Negation** needs the same care. For format and style, prompt the **positive**: state the target ("write one-line comments") rather than the ban, because a general ban ("avoid a generic look") mostly swaps one default for another. A prohibition works when it is **specific and paired**: it names the exact pattern to avoid and says what to do instead ("don't add tests that weren't asked for; mention the gap at the end instead"). Write scope limits and hard guardrails that way.

## Reasons and examples

Give the **reason** behind a rule whenever it isn't obvious. A bare rule covers the cases you wrote down; a rule with its reason lets the agent settle the case you didn't ("no ellipses" bans one character, "no ellipses, because a text-to-speech engine reads this aloud" covers everything the engine would stumble on). The reason also tells a later editor whether the rule is still live.

Show an **example** when the target is a format, a tone, or a level of detail: one complete example fixes more than a paragraph describing it. Where the agent might copy a single example too closely, give several that differ, and prefer a few canonical ones to a list of edge cases.

## Pruning

- Keep each meaning in a **single source of truth**: one authoritative place, so changing the behavior is a one-place edit. **Duplication** — the same meaning in more than one place — costs maintenance and tokens, and inflates a meaning's prominence on the ladder past its real rank. (The accidental inverse of a leading word, which repeats a token on purpose, never the meaning.)
- The **environment** is a source of truth too — `package.json` scripts, config files, the directory layout, `--help` output — and a document that restates it is a **cache**: a copy of a lookup, earning its load only when the lookup is expensive. Cache what the agent cannot find by looking: the unwritten convention, the reason behind a choice, the gotcha no config confesses. Leave the one-file, one-command lookups to the environment, where they cannot go stale.
- Check every line for **relevance**: does it still bear on what the document does? A line loses relevance by never bearing on the task (mere exposition, or a branch that should be disclosed) or by going stale as the behavior or world it describes changes. Shorter documents are easier to keep relevant. Without a pruning discipline the default fate is **sediment**: stale layers that settle because adding feels safe and removing feels risky, until you must core down through them to find what is still live.
- Hunt **no-ops** sentence by sentence: an instruction the model already obeys by default pays load to say nothing. The test — does it change behavior versus the default? — is model-relative, not reader-relative: two people disagreeing about a no-op disagree about the default, and settle it by running the document, not by debate. When a sentence fails, delete the whole sentence rather than trim words from it. The test also grades leading words: a word too weak to beat the default (_be thorough_ when the agent is already thorough-ish) is a no-op. Delete it; if the behavior is still missing, give the reason it matters or a completion criterion that demands it ("every modified model accounted for"), not a louder word. Emphasis (_IMPORTANT_, capitals) is the last resort for one line the agent keeps skipping; spread over many lines it marks none of them. Re-run the test when the model changes: an instruction that compensated for an older model (forced re-checks, "think carefully", scheduled status updates) can push a newer one to overdo the thing.
