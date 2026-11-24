---
name: dan-audit-memory
description: Audit a repo's auto-memory directory for stale and wrong memories, and fix what the evidence supports.
disable-model-invocation: true
---

Memory rot is **silent**. In the corpus this skill was built against, not one wrong memory showed decay from the inside — no broken link, no hedge, no formatting artifact. So the audit runs outside-in: a script checks what memories *cite* against the world, and you adjudicate what it surfaces.

Run it when a repo's index has grown past what you'd trust yourself to select from, or before leaning hard on memories you haven't touched in months.

## Step 1 — Sweep

Resolve the memory directory (the one SessionStart printed, else `autoMemoryDirectory` in the repo's `.claude/settings.local.json`, else `~/.claude/projects/<project>/memory/`), and the repo it describes (usually the repo root above `.memory/`). Then:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/sweep.py <memory-dir> --repo <repo-root>
```

`--no-gh` when the repo has no GitHub remote. `--paths` also checks cited file paths — noisy, because it fires on files that live in *other* projects the memories describe.

**A flag is a reason to read a file, never a verdict.** A dead reference sits under sound advice as often as under a wrong conclusion: one memory citing a deleted test runner still gives correct advice; another citing a removed CLI coupling is wrong end to end. Identical signal, opposite dispositions.

**The sweep sees structure and drift, not claims — its recall is partial by construction.** On the corpus it was calibrated against, it reached 4 of 6 known-wrong files. It cannot see: a claim with no citation attached, a contradiction between two memories, external package versions, or state in another repo. So treat the flag list as the *cheap* pass, not the whole audit, and read `MEMORY.md` end to end yourself — 60-odd pointer lines is a minute, and a description you cannot square with what you know is a lead the script has no way to produce.

Done when both lists exist and you have read the index alongside them.

## Step 2 — Adjudicate

Work the sweep's **Adjudicate** list; **Cleanup** needs no reading and waits for Step 3.

Whichever route you take below, read each file's **index line** alongside it. The two surfaces drift into carrying different states of the world, in both directions, so the correction you are about to write may already exist in the other layer.

**Under ten files, read them yourself.** For a `file:line` flag, read the cited source too — that is the only way to tell drift from breakage. A subagent costs 120–400K tokens of cold re-orientation against 4–5K to read a file on a warm orchestrator, so fanning out a small audit spends tokens to save none.

**At ten or more, fan out verification — never adjudication.** Batch by flag class, one agent per class, so each dispatch carries five or more files and earns its re-orientation. What comes back is evidence; the dispositions stay with you, because the two findings worth most are cross-file — a contradiction between two memories, and a forward pointer that edits a file in some other batch's slice. Nothing but you may write, and `MEMORY.md` in particular is a single shared file that concurrent writers would corrupt.

Send each agent this brief, with that class's entries pasted in:

```
Verify memory claims in <memory-dir> against the repo at <repo-root>.
Read-only: make no edits, and do not commit.

Files and the flags raised against them:
<paste this class's entries from the Adjudicate list>

For each file, return:
- file
- claim — the sentence the flag points at, quoted
- verdict — HOLDS | DEAD | UNVERIFIABLE
- evidence — what you ran (git log, grep, a tracker query) and what it showed
- framing — NARRATION if the sentence is dated and stays true as history,
  ASSERTION if it claims a present fact
- premise — the load-bearing fact the file's conclusion rests on, and whether
  it still holds

Report UNVERIFIABLE rather than guessing. Return findings only: propose no
fixes and do not judge whether a memory should be kept.
```

Then, on what you read or what came back, ask four questions:

1. **Is this bookkeeping?** Forward-looking issue and PR status was the largest single class of rot — 38 of 55 such claims dead, over half of everything that rotted, all in the same direction (the thing shipped). **Keep the reference, strip the status.** "Decided in #43" is provenance and cannot rot; "#98 stays open — close it by hand at release" is a dead imperative. The tracker is authoritative and free to query, so re-asserting its state buys one session of accuracy at the same cost, forever. (A repo with no tracker has none of this class; its rot sits in the next two questions instead.)
2. **Is the sentence narration or assertion?** "Three instances found in one session (2026-07-20)" ages gracefully. "`styles/global.scss` ships `--color-primary-dark`" does not. Only a reader can tell dated narration from a live claim, and the difference decides whether a stale number matters.
3. **Does the stale specific invalidate the conclusion?** Reasoning inherits the half-life of the fact it stands on. A memory can reason impeccably from "the kit pins `typescript@^5`" to a conclusion that inverts when the pin moves to `~6.0`, with no sentence being wrong. Find the load-bearing premise and check *that*. A `churn` flag means exactly this: the code underneath moved a lot, and the citations may still resolve.
4. **Was it ever true?** Ask last, because it is the most expensive — but ask before choosing a disposition, since a memory that was never right gets deleted rather than amended. Freshness cannot be inferred from age in either direction: one memory in the source corpus was *born false*, asserting a coupling removed two months before it was written. When a memory rests on an inherited premise nobody verified, date the premise with `git log -S`.

Each flag class has a question that usually decides it, and an outcome to expect — a starting point, not a substitute for reading:

| flag | decided by | usual outcome |
|---|---|---|
| `issue-status` | Q1 | Amend — the reference stays, the status goes |
| `churn`, `file-line-drift`, `dead-identifier` | Q3 | Amend, or Leave when the conclusion survives its citation |
| `measured-number` | Q2 | Leave if dated narration; Amend if it reads as a live fact |
| `accretion` | Q2 | Amend — fold the stacked corrections into one current claim |
| `entrypoint-collision` | Q2 | Amend all but the current one; live handoff state belongs in `NEXT.md` |
| `index-orphan`, `index-broken-link` | — | An index edit; no memory file changes |

Then assign each file exactly one disposition:

- **Leave** — the flag is noise, or the claim is framed as history and still true as history.
- **Amend** — correct the claim in place. **Amend, never append.** A correction stapled beside the wrong text leaves both in context and the reader picks one; the source corpus has a file carrying four stacked "now stale / original follows" appendices. When the reasoning is sound and only its conclusion inverted, keep the reasoning and re-derive the conclusion.
- **Forward-point** — the memory is fine as history but something supersedes it. Write the pointer **into the superseded file**, because that is the file a `[[wiki-link]]` opens. In the source corpus, links ran ~80% backward in time (95 new→old against 24 old→new), so the reader who lands on the old memory gets no signal unless you put one there.
- **Merge** — two memories split one meaning. Keep the one whose name a future session would search for.
- **Delete** — the memory is wrong and carries nothing worth keeping, or a `CLAUDE.md` rule now covers it. Six publish memories in the source corpus were duplicated by an always-loaded rules section and had silently diverged from it.

Done when every file you read carries exactly one disposition and a one-line reason.

## Step 3 — Apply

Establish whether the memory directory is under version control, and say which:

```bash
git ls-files -- <memory-dir> | head -1
```

Non-empty means tracked, so edits are recoverable. **Empty means unprotected** — `git status --short` cannot tell you this, since it prints nothing for a gitignored directory and nothing for a clean one. The default `~/.claude/projects/<slug>/memory/` location is never in the repo. When it is unprotected, tell the user before changing anything and get their go-ahead.

With that established: apply the **Cleanup** list and your **amendments and forward pointers** directly. Cleanup is mechanical — a frontmatter field, a missing index line, a dangling link confirmed as a deliberate cross-repo reference — and the rest is additive and reversible.

Bring **merges and deletions** to the user first, as a list with one line of evidence each. Losing a memory that was right costs more than carrying one that was wrong.

Keep `MEMORY.md` in step with every file you touched. Because a wiki-link bypasses the index entirely, a correction that lives only in a pointer line is invisible to any hop between memories: both surfaces or neither.

Done when every disposition is either applied or listed as declined.

## Step 4 — Report

Give the user, in this order: flags by class; files changed with their disposition; merges and deletions awaiting approval; and what went unchecked — external package versions, test counts, cross-repo issue numbers (the sweep resolves every `#N` against one repo, so a number belonging to another project is silently unverified), and any file the sweep could not reach.

Close with what the audit implies for *writing* memories, where the same defect appeared more than twice. That is the finding worth more than the cleanup.
