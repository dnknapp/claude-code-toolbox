---
name: dan-handoff
description: Write or update an orchestrator run's handoff file — the durable state a fresh orchestrator resumes from with no other context. Use at every wave boundary of /parallel-tracks or a Workflow run, when pausing for the plan usage limit, when the idle saver asks for it, and when resuming a paused run.
---

A **run file** is the handoff between orchestrator sessions: the reader is a fresh agent holding nothing but this file and the repo. It is not NEXT.md, which is the user's short checklist; a run gets one line there, pointing here.

Plan usage, cache state and the local clock come from `/usr/bin/python3 ~/.claude/hooks/dan-cache-cold-guard.py --usage` (agents can't see the first two otherwise). Run it at the start of every update: every time you write into the run file comes from its `Now` line.

## Write or update the run file

**Locate it.** One file per run at `<memory-dir>/handoffs/<YYYY-MM-DD>-<run-slug>.md`, using the memory directory SessionStart printed. If this session already wrote one, or NEXT.md points at one for this run, update that file; otherwise create it. Rewrite every section to the current state except the wave log, which only grows.

```markdown
# Run: <run name>
_Status: active | paused (<reason>, resume <when>) | done — updated YYYY-MM-DD HH:MM_

## Goal
<the user's goal, in their words where possible>

## Constraints
- <every instruction the user gave that binds the run: scope limits, review gates, who commits, what not to touch>

## Tracks
| Track | Scope | Issue/PR | Branch | Status |
|---|---|---|---|---|
| <name> | <folders/files> | #123 | <branch> | done @ <sha> / in flight / queued / blocked: <why> |

## In flight
- <agentId> — <track>, launched HH:MM, working on <branch>. Reconcile on resume: <what finished looks like — a commit, a PR, a report>.

## Wave log
- Wave N (HH:MM–HH:MM): <tracks> → <result>. 5-hour usage <before>% → <after>% | window reset mid-wave.

## Decisions
- <decision> — <why>. Contracts invented this run (the wave brief) go here or in a plan doc named here.

## Dead ends
- <what was tried> — <why it failed>, so the next orchestrator doesn't retry it.

## Repo state
<branch, uncommitted work, open PRs awaiting review; the commands that verify the work, e.g. `npm run check`>

## Resume
1. Read this file, then `git log --oneline -20` and `git status`.
2. Reconcile every In flight entry against its branch or PR: finished → mark done; absent → queue it for re-dispatch.
3. Run the verification commands above and confirm the tree is green.
4. Run the usage command, then take up the first Tracks row that isn't done, per /parallel-tracks.

Resume prompt: `handoff-resume: read <path to this file> and continue the run from its Resume section.`
```

The Resume steps stay generic: what comes next lives in Tracks, and what to check lives in In flight's reconcile notes, so keeping those two sections current keeps Resume current.

Done when a fresh orchestrator holding only this file and the repo could dispatch the next wave without asking anything, and every wave-log line carries a measured before and after (the *before* from the usage run at dispatch, the *after* from this update's).

**Point NEXT.md at it.** Re-read `<memory-dir>/NEXT.md` off disk, then keep exactly one line for this run under "Next up", replacing any earlier line for the same run and leaving every other line as it is: `- [ ] Resume run <name> (<status>) — handoffs/<file>`.

**When the status is `done`,** run `/usr/bin/python3 ~/.claude/hooks/dan-cache-cold-guard.py --disarm` and do what it prints, so the idle-save job stops showing in the quit dialog as background work.

## Pause for the usage limit

When /parallel-tracks' budget check says the next wave won't fit before the 5-hour reset:

1. Let running subagents finish and record their results; dispatch nothing new.
2. Update the run file with status `paused (usage limit, resets HH:MM)` and point NEXT.md at it.
3. Choose the resume by the session's cold-restart size, from the usage command's `re-caches ~Nk tokens` line:
   - **Under 200k:** resume in this session. CronCreate a one-shot (`recurring: false`) three minutes after the reset, with the run file's resume prompt.
   - **200k or more:** leave the resume to the user. The NEXT.md line says `paused for usage limit, resets HH:MM — /clear, then paste the resume prompt from handoffs/<file>`. A fresh session reading the run file starts far smaller than a cold restart of this one.
4. Tell the user where the run stopped and which resume you chose.

## Resume a paused run

A `handoff-resume` prompt, or the user pasting one, starts here: follow the run file's Resume section, then set its status back to `active`.
