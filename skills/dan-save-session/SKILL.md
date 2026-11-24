---
name: dan-save-session
description: Write the session handoff — save new auto-memories and rewrite the memory directory's `NEXT.md` so the next session starts oriented. Use when the user asks to save the session or write a handoff, and when a session is wrapping up or about to be cleared.
---

Write this session's **handoff**: what a cold reader needs to resume the work without re-deriving anything.

Use the memory directory SessionStart printed into context. If that line is absent, read the repo's `.claude/settings.local.json` for `autoMemoryDirectory`, else `~/.claude/projects/<project>/memory/`. If no directory resolves, say so, point the user at `/dan-setup-memory`, and stop.

## Step 1 — Memories: what would otherwise be re-derived

The harness sets memory format and the four types; the global `CLAUDE.md` adds the rules that deviate from it. Apply both as written. What this moment adds:

**What earns a file**

- **The bar is re-derivation.** Keep a decision and the reasoning behind it, an approach tried and abandoned and why, a constraint discovered the hard way, a correction the user made to your approach. Everything else is already in the diff or the git log.
- **Update before adding.** Read the index first. A sharpened existing memory beats a near-duplicate, which splits one meaning across two files and doubles the pruning debt.
- **Pointer lines are recurring cost.** Every `MEMORY.md` line loads on every future session in this repo. Earn each one, and keep it to a line.
- **Durable instructions are CLAUDE.md's job.** When something the user said generalizes past this session ("always do X"), name the scope and ask — that's a `CLAUDE.md` edit, not a memory.

**A lesson a global skill should carry also goes to the inbox**

Ask of each memory you write or update: which global skill or agent would this change? Global means one under `~/.claude/skills/` or `~/.claude/agents/`, not one this project ships. A lesson with a target there goes to the inbox, and so does a fact about the harness, a tool or this machine that no skill fires on, with `global CLAUDE.md` as its target. Project memory is per repo, so such a lesson is invisible everywhere else until it reaches the global setup, and that is written in `claude-tools`.

A lesson with no target stays in this repo's memory, however widely it seems to apply. A correction to one piece of work reads as true in any project once it is written as a principle, and with no skill to fire it the inbox has nowhere to put it. A lesson one of the project's own dev kit skills should carry gets no entry either: name it in the Step 3 report as one for the kit.

Save the memory here as usual, then write `~/Sites/sandbox/claude-tools/inbox/<YYYY-MM-DD>-<repo>-<memory-name>.md`:

```markdown
---
from: <this repo's folder name>
memory: <absolute path of the memory file>
target: <the skill or agent it would change, or global CLAUDE.md>
---
<the lesson in a sentence or two, and the task it bites during>
```

A session there promotes the lesson and removes this project's copy. Write no entry when this repo is `claude-tools`, or when that `inbox/` folder is not on this machine; in the second case say so in the Step 3 report.

**What survives contact with time**

Three write-time habits prevent most of what rots:

- **Keep the reference, skip the status.** "Decided in #43" is provenance and cannot rot; "#98 stays open, close it by hand at release" lies as soon as the work ships — the tracker knows its own state and answers for free, so restating it buys one session of accuracy. Live status belongs in `NEXT.md`, not a memory. One exception: when a not-yet state is itself the finding — a design recorded before it ships — date it, so "not built as of 2026-08-12" ages into history instead of lying.
- **Cite something greppable.** An identifier (`writeSkills()` in `src/index.js`) survives refactors; a `file:line` dies when lines move, and nothing tells the reader. Same for restated counts — give the number a date and frame it as a measurement taken, not a fact that stays true.
- **Correct what this session superseded — in the superseded file.** The index is pointer lines only and a `[[wiki-link]]` bypasses it, so the fix must live in the file body. Open the old file and pick one:
  - **Amend** — the claim is wrong: rewrite it in place, never a correction stapled beside the old text, because the reader picks one.
  - **Forward-point** — still true as history, but replaced: write `[[the-new-memory]]` into the *old* file. Links run backward in time, so the reader who lands there gets no signal unless you leave one.
  - **Delete** — wrong and carrying nothing else: remove the file and its pointer line. A wrong memory costs more than a missing one — it gets acted on.

Done when every decision, dead-end, and correction from this session is either written down or named as skipped in the Step 3 report, and every memory this session disproved or superseded carries its amendment, forward pointer, or deletion.

## Step 2 — Rewrite NEXT.md

Write `<memory-dir>/NEXT.md` fresh each time. It is a **snapshot** of where things stand, so the previous contents are raw material to supersede, not a log to extend.

This file is the only memory content printed to the terminal at session start. Hard cap: **25 lines.** Overflow is the signal that something belongs in a memory file or an issue tracker instead — so get under the cap by **removing a bullet**, not by rewording. Tightening prose to reclaim a line or two buys nothing and costs a round trip per attempt; if you are two lines over, one bullet is one bullet too many.

**Re-read the file off disk before rewriting it.** SessionStart printed `NEXT.md` into context, but that copy is only as fresh as the moment this session began. If what is on disk differs, a concurrent session in this repo wrote it after you started — **merge, don't replace**:

- Keep every live item of theirs you cannot personally disprove. You did not do their work, so you cannot tell a finished item from one they dropped.
- Fold your own state in alongside theirs, and say so in the `_Updated_` line so the next reader knows two sessions fed it.
- Merge the "Where we left off" bullets into one set rather than stacking two. If the result overflows 25 lines, push detail into memory files — never buy the room by dropping the other session's items.

A `## Slots` section holds one bullet per open slot (see the `slots` skill), written by that slot's own save, and it doesn't count toward the 25 lines. Outside a slot, carry it over unchanged, except that a bullet whose item has no row in the `slots` table (merged, closed or cleared) is finished: drop it. `slots` drops such bullets itself whenever its table runs outside an item's folder, and leaves a `PR #… merged` line under "Where we left off" for each item that merged: fold those into that section's bullets. A slot session follows its own instructions for this file instead.

```markdown
# Next up — <repo or work-area name>
_Updated YYYY-MM-DD_

## Where we left off
- <2–4 bullets: what actually landed, with issue/PR numbers where they exist>

## Next up
- [ ] <the concrete next action, specific enough to start cold>
- [ ] <...>

## Watch out
- <optional: a live blocker, an open decision, a trap. Omit the section if empty.>
```

What makes it hold up:

- **First thing first.** "Next up" runs in the order the work comes: the top line is what the next session starts on. An item the user calls next goes at the top, not at the end.
- **Name the next action, not the topic.** "Finish the retheme" tells a cold reader nothing; "rebase #195 on main, then re-run the contrast audit — `--color-on-accent` is the remaining AA failure" can be picked up without context.
- **Point outward.** Reference `[[memory-name]]`, issue numbers, and file paths so the detail lives at its source and this file stays scannable.
- **Carry only live items.** Finished work leaves — git history has it. Stale checklist items teach the reader to distrust the file, which costs more than an empty section.
- When nothing is pending, say so in one line. "Nothing open; #195 awaiting review" is a useful startup signal.

Done when a reader who was not in this session could pick the top item and start.

## Step 3 — Commit and report

Commit the memory directory, so nothing the save wrote is left uncommitted: run `${CLAUDE_SKILL_DIR}/scripts/commit-memory.sh <memory-dir> "<what changed>"`. It commits only that directory, other sessions' memory changes included, on the branch its own repo has checked out, and skips one that git ignores (some team repos keep `.memory/` out of git), outside a repo, or on a detached HEAD. When its output says `push-safe`, run `git -C <memory-dir> push` unless the global rules forbid pushing that branch. Put the script's output line, and any hook message above it, in the report.

Then run `/usr/bin/python3 ~/.claude/hooks/dan-cache-cold-guard.py --disarm` and do what it prints: it removes the idle-save job, so the quit dialog lists only real background work.

Tell the user which memories you wrote, updated, or deleted, by name, what you judged not worth keeping, and the headline of what `NEXT.md` now says. They should know whether this worked without opening a file.

Give inbox entries their own part of the report, under a bold **Sent to the Claude Tools inbox** label: one line per entry, with the lesson as you wrote it and the entry's file name, then a line saying that deleting a file drops its entry. The entry is written without asking, so this is the only place the user sees it and can refuse it.

Close by confirming the handoff is complete, so they know it's safe to `/clear` or quit. Nothing further is captured after this point — anything they do next is a new stretch of work needing its own save.
