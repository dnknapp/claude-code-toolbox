# Skill mechanics

The skill-specific branch of [`writing-for-agents`](SKILL.md): what changes when the document is a skill — frontmatter, limits, the invocation choice, and router skills. Everything else about writing it is the universal reference in `SKILL.md`.

## Limits

- **`name`** — at most 64 characters: lowercase letters, digits, and hyphens, without "anthropic" or "claude". Claude Code defaults it to the directory name.
- **`description`** — at most 1,024 characters on the platform. Claude Code's skill listing shows at most 1,536 characters of `description` plus `when_to_use`, and when the whole listing runs over its budget it shortens the least-invoked skills first. Put the key use case first, so truncation costs only the tail.
- **Body** — under 500 lines. Past that, move reference into sibling files and say in `SKILL.md` what each holds and when to read it.
- **Sibling files** — one level deep from `SKILL.md`: a file reached only through another reference file tends to be previewed, not read. Give a reference file over 100 lines a table of contents for the same reason.
- **Compaction** — after a conversation is compacted, Claude Code re-attaches only the first 5,000 tokens of each invoked skill, so what must survive a long session goes at the top.

## Invocation

Two choices, trading the two loads:

- A **model-invoked** skill keeps a `description`, so the agent can fire it autonomously — and other skills can reach it. You can still type its name: model-invocation always _includes_ user reach; a description only ever adds agent discovery, never removes the human's. The description is the skill's top-level context pointer, forced to stay loaded at all times — permanent context load in exchange for discoverability. A model-invoked skill whose content is all reference is also one home for shared reference: another skill can invoke it, so reference needed by several skills lives in one place. Mechanics: omit `disable-model-invocation`, and write a model-facing description carrying the trigger branches (the pointer-writing rules in `SKILL.md` apply in full).
- A **user-invoked** skill strips the description from the agent's reach: only the human typing its name can invoke it, and no other skill can. Zero context load, but it spends cognitive load — you are the index that must remember it exists. Mechanics: set `disable-model-invocation: true`; the `description` becomes human-facing — a one-line summary, trigger lists stripped.

Pick model-invocation only when the agent must reach the skill on its own, or another skill must. If it only ever fires by hand, make it user-invoked and pay no context load.

Shared reference that two user-invoked skills both need can live in neither — with no descriptions, neither can fire the other. Push it to a plain file outside the skill system: external reference any skill can point at.

## Splitting by invocation

The invocation cut of splitting (the sequence cut lives in `SKILL.md`): split off a model-invoked skill when you have a distinct leading word that should trigger it on its own — a trigger word you actually use in your prompts — or another skill must reach it. You pay context load for the new always-loaded description, so that independent reach has to be worth it.

## Router skills

When user-invoked skills multiply past what you can remember, that piled-up cognitive load is cured by a **router skill**: one user-invoked skill that names the others and when to reach for each, so the human has one skill to remember instead of many. It can only hint, never fire them: user-invoked skills have no description, so nothing but the human can reach them.
