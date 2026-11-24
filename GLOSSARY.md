# Glossary

The words these skills, agents, hooks and docs use in a sense of their own.
General Claude Code terms (skill, subagent, hook, auto-memory) mean what
Claude Code's docs say. `writing-for-agents` defines its own vocabulary
(context pointer, leading word, completion criterion) inside the skill.

## Sessions and handoffs

**Memory directory**:
The folder a repo's auto-memory lives in. Here it is `.memory/` inside the
repo, set per repo by `/dan-setup-memory`, rather than Claude Code's default
under `~/.claude/projects/`.
_Avoid_: memory folder, memories dir

**Session handoff**:
`NEXT.md` in the memory directory: a short snapshot of where the last session
left off and what comes next, rewritten whole at each save and shown at the
next session's start.
_Avoid_: handoff doc, notes, status file

**Run handoff**:
The file `dan-handoff` writes for a multi-agent run: the state a fresh
orchestrator needs to resume the run with no other context. One per run,
under `handoffs/` in the memory directory.

**Save**:
Running `/dan-save-session`: recording new memories and rewriting the session
handoff. Done by hand before `/clear`, or by the idle saver.

**Cold cache**:
A prompt cache that has expired, an hour after the last message. The next
message re-sends the whole conversation at twice the input price.

**Cache guard**:
The `dan-cache-cold-guard.py` hook: in a session past 100k tokens it stops
the first message sent to a cold cache, and runs the idle saver.

**Idle saver**:
The cache guard's check every 20 minutes, which keeps the cache warm while
work goes on and saves the session after about 35 idle minutes.

**Status footer**:
The last lines of every reply: what is uncommitted or unpushed, then `Next:`
with the most pressing open question and a recommendation, and `Also open:`
for the rest.

**Open question**:
A choice Claude cannot make from what the user has said or already decided.
A pick Claude made, with the alternatives named, is not one.

## Reviews

**Axis**:
One of the three questions `/code-review` asks of a change, each answered by
its own agent: _Correctness_ (`blind-reviewer`), _Standards_ (`reviewer`) and
_Spec_ (`issue-verifier`).

**Blind review**:
A correctness review formed from the code alone, without the author's account
of it, in which each finding is proved, usually by running something, before
it is reported.

**Depth**:
How much a blind review runs: _focused_ (type checks and the tests covering
the change), _standard_ (adds the in-process suites and mutation testing) or
_deep_ (adds suites that drive a browser or a running app; only when the user
asks).

**Integration branch**:
The branch a repo's feature branches start from and merge into, such as
`dev` or `main`. Found from the repo's docs or its recent merged PRs, never
assumed.
_Avoid_: base branch (a PR's base can be another feature branch)

## Parallel work

**Orchestrator**:
A session that splits work up and dispatches agents to do it, and does not
implement anything itself.

**Track**:
One bounded, self-contained slice of implementation work, handed to one
`track-implementer` agent.
_Avoid_: task, job

**Wave**:
A set of tracks dispatched together. The next wave starts after this one's
results are in.

**Slot**:
One item in flight under `slots`: a folder beside the main checkout (a git
worktree), a dev server on its own port, and a background Claude Code session
working the item.

**Item**:
What a slot works on: one issue, one PR, or two issues grouped as one
(`58+59`).
_Avoid_: ticket, job

**Main checkout**:
A project's own folder, where the main session runs and beside which the
slots' folders sit.

**Direction line**:
The user's own words, quoted after the item number in `slots start`, passed
verbatim to the slot as its brief.

**Opener**:
A slot session's first message: what the item asks, the problem behind it,
the plan, and one question, sent before any work starts.

## Skills from elsewhere

**Dev kit**:
The shared repo of skills, hooks and conventions that Dan's team at work
ships into each of its projects. Several pieces here refer to it, and act
differently in a repo that has it.

**Fallback skill**:
A personal skill that stands in for a dev kit skill in repos without the kit,
under a name of its own (`dan-issue-pr-format` for `gh-issue-pr-format`), and
is switched off in repos that have the kit's version.

## Maintaining the setup

These name parts of the private repo the setup is deployed from.

**Deploy**:
Copying `dotclaude/` into a machine's `~/.claude/` with `./deploy.sh`.

**Live config**:
What a machine's `~/.claude/` actually holds, which Claude Code runs.

**Machine layer**:
The files that apply to one machine only: `machines/<machine>.md` and the
optional `machines/<machine>.settings.json`, merged over the shared settings.

**devbox**:
The Linux machine development happens on, beside the Mac, reached as
`ssh devbox`. Also called _the box_.

**Drift**:
A live config file that differs from what was last deployed, usually from a
change made inside Claude Code. The pre-commit drift guard blocks a commit
until it is reconciled.

**Lesson**:
Something a session learned that a global skill or agent should carry.
Sessions in other repos file lessons as issues labeled `lesson` in the repo
the setup is deployed from, to be promoted into that skill or agent.

**Export**:
Copying the shareable files to the public repo with `./publish.py`, after a
leak check that refuses any file matching a blocked pattern.
_Avoid_: sync, mirror
