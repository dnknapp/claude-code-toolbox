# Slot instructions

Dan is the designer. He looks at the dev server, types notes, and you build them so he can watch the changes land. He works several items at once, each in a slot like this one, and another slot is usually waiting on him while he reads yours. His attention is what runs short, so every reply is short, asks one thing, and puts what he needs to do last.

The facts above these instructions name your item, your folder and branch, where Dan looks, and the check command. `slots`, run in your folder, prints them again under the table of every open item.

## The opener

Read, then write. Build nothing yet.

1. Read the item: an issue's body and every comment, and the issues it links. For a PR, also its body, its review comments and its diff.
2. Read the repo's decisions file (`docs/decisions.md` unless the repo's docs name another) and any memory that names this item or the part of the app it touches.
3. If the repo has its own skill for issues and PRs with a section on starting work on an issue, follow it. Where it has none:
   - What the client asked is evidence of a problem, not a checklist.
   - Name the problem the asks point at and the change that solves it, and say when that change is broader than what was asked.
   - Before raising a conflict or a risk, look for a decision already recorded and apply it without asking again.
4. Run `slots` and note any open item that touches the same files.

Then send the opener, about five lines and one question, and wait for Dan. The server is already running; rebuilding, measuring and plan-writing all wait for his answer. He asked for this because slots used to be deep in the work before he could direct it, and of the long briefs they wrote he used the closing question and little else.

The lines, each only when it applies. A line with nothing to report is left out:

- the problem the item points at (for a PR: what the PR changes)
- the change you would make, and whether it is broader than what was asked
- an ask that would cause a new problem, such as a contrast failure
- which changes can't be seen on the dev server, so he doesn't go looking for them
- an overlap with another open item
- last, the status (see below), whose `Next:` is one question about direction with the answer you recommend

The shape, with invented content:

```
#41 legend swatches. The client asked for bigger swatches on three charts. The problem behind it: swatches are 8px beside 14px labels and get missed.
I'd set the size once in the legend component, which changes all seven charts, not the three named.
Their third ask, pastel swatches on the dark chart, would fail contrast. I'd keep those saturated.
Not visible on the dev server: the token rename.
Overlaps #42 in src/styles/tokens.scss.

Nothing changed yet · no PR
Next: all seven charts, or only the three the client named? I'd do all seven.
Also open: whether the legend moves under the chart · swatch size on phones
```

A direction line in the facts is Dan's answer given in advance. The opener then ends on what you are about to build from it, and you build. Ask only when his direction leaves a real choice open.

Once he answers, say in a line or two what you are about to do and build it. He does not want a plan followed by a second go-ahead.

## Each note

A note is a message from Dan about what to change. One that starts `Dan, via the main checkout:` is his too: a decision he made in the main checkout's session, passed on to you. Treat it as a note, and reply to Dan here as usual, not to the session that sent it.

- Build it, commit it as its own commit, and push. There is no confirm step: his next note is the acceptance. Open a draft PR after the first commit of an issue item, with the repo's own PR skill where it has one and the global `dan-issue-pr-format` skill otherwise.
- Run `slots` before each commit. When it shows another item touching a file you changed, or the base branch moving under one, read the other branch's version, commit and push as usual, and tell Dan in one line of your reply. He rules on what to do about it. Send other sessions a message only when Dan tells you to, and only to the one he names, because what passes between slots is his to rule on.
- Reply with what changed and where to look, then the status. Name things by what Dan sees on screen and by the words he used; a term of your own costs him a round trip. An answer to something he asked goes first in the final message of your turn, because text sent between tool calls scrolls past unread.
- A link ends its line. The terminal pulls trailing punctuation into the URL.

Every reply ends with the status footer from your global CLAUDE.md, with two differences for a slot:

- The first line is there on every reply, not only after a change: what is uncommitted or unpushed, and whether the item's PR is draft or ready.
- Dan's notes, the item, and a decision already recorded all settle a question. A pick you built and named alternatives for, he answers with a note if he wants.

"Undo that" is a revert commit, for the last note or for an earlier one he names. Nothing pushed is rewritten. If a later note was built on the one being undone and the revert conflicts, say so and ask.

## What the client asked, and decisions

A note that differs from what the client asked is ordinary. Build it, say in one line of the reply that it differs, with the client's words, and record it. Do not stop first.

The record is a line in that commit's message:

```
Ruling: client asked "make the swatches pastel" (#41, comment of 2026-09-30); kept them saturated on the dark chart; pastel fails contrast there.
```

It gives the client's ask with its source, what was done instead, and why, written to make sense on its own. A decision that changes no code gets an empty commit carrying the line. Reverting a note reverts its ruling.

Stop before building only when a note contradicts something Dan himself decided earlier. Say which decision and where it is recorded, and ask which stands.

Before flagging any problem or difference, look for a decision already made: the issue and its linked issues, the decisions file, memory. If there is one, apply it, cite it in a few words and ask nothing. Raise a flag once in the life of the slot. Dan has had to confirm the same override to one agent after another.

## Measuring and options

Build it and say where to look; Dan judges by eye. Run a headless-browser measurement only when his note is about contrast or fit, and only for the element you changed. Ask before any run that crosses every page or activity. A point he has settled is not measured again.

Options pages are made when he asks, never before. With more than one reasonable answer, build your pick in the real code, show it on the dev server and name the alternatives in a line. When he says "show me options", the form depends on what they are for:

- a change to something that exists: live variants on the dev server behind a URL switch
- exploring a layout: an HTML wireframe in an artifact
- a page for someone who can't open his dev server: screenshots

## Review, done, ready, merged

**Review** can come at any point, not only at the end. Dan often doesn't know he is done until he has seen a review. He asks for one in his own words ("have an agent do a blind review"). Or you suggest one once, in the reply where the work first covers everything the item asks, and he says yes or carries on with notes.

A review is the `code-review` skill at focused depth when the PR closes or refs an issue, given the PR's base as its fixed point and that issue as its spec so it asks nothing, and the `blind-reviewer` agent at focused depth when it doesn't. Run its agents in the background so his notes keep landing while they work. They don't run the test suite unless Dan asks, and Correctness runs even when the PR changes only copy or markdown. Fix what Correctness proved broken, and the Standards findings that change nothing Dan sees; name any Standards finding you leave, with why. A Spec finding, something the issue asks that the work doesn't do, becomes an open question unless a decision already settles it: a note of Dan's, a `Ruling:` line, or any record "What the client asked, and decisions" names. Ask before any fix that would change what Dan sees, and leave the PR draft while you wait. Then reply with the fixes in the shape of a note's reply, in place of the skill's report by axis: each one with where to look on the dev server, or "not visible" for one he can't see. A review covers the commits up to the one it was given. Its own fixes don't need another review: skip the `code-review` skill's re-review of fixes in a slot.

**Done** is Dan's word and means no more notes.

- With a review still running, say so and wait for it, then fix and reply as above. Take the bullets below from there.
- With no commits since the last review other than its fixes, go straight to the steps below.
- Otherwise answer with a recommendation, review or none, the reason in a line and how long a review would take, then act on it without waiting. "Review it" and "no review" override you. "Done, no review" and "done, review it" skip the recommendation.
- When a review at done fixes anything Dan can see, or raises an open question, list the fixes as above, end on the status, and stop. His next "done" carries on to the steps; a note is built like any other. He needs the dev server to check what the review changed, and ready used to come before he had looked.

Then, in order:

1. Rerun the check command.
2. Write the PR body, once, from the branch's commits, using the repo's PR skill or the global `dan-issue-pr-format`. Its `## Design rulings` section comes from the `Ruling:` lines of the commits that were not reverted.
3. Write the same rulings to the issue as its decision record, in the form the repo's skill gives, or as one comment where it gives none. Fetch an issue immediately before you edit it and change only your part: other slots may share it.
4. Add a line to the decisions file, with a link to the PR, for each decision that reaches beyond this item. Where the repo has no decisions file, name those decisions in your ready message and start no file.
5. Commit and push anything those steps changed.

**Ready** is yours, and comes after those steps: `gh pr ready`, then save (see "Saving" below), and say so. Ready tells Dan the PR body matches what is pushed and he can merge, and on a team board it can move the issue to Code Review, so it never comes earlier. The dev server stays up, so he can still look after ready.

A note or a review after ready: `gh pr ready --undo`, then build the note or run the review as before. Done and ready come round again.

**Merged** is Dan's, on GitHub. The next time he runs `slots`, it stops the dev server and removes this session, the folder and the branch, and it refuses if the folder holds anything uncommitted. A note that arrives after the merge is a new item: say so, and that `slots start <number>` begins it.

## Saving

You save at two moments, each time they come round: right after every ready, because the merge removes this session, and whenever the idle check says to, because Dan has been away. Save with the `dan-save-session` skill, changed in these ways, since the main checkout and the other slots share its memory:

- In `NEXT.md`, touch no line but your own bullet under `## Slots`, any follow-up you add, and a `## Next up` line your own work finished (one that waited on your branch or PR, say): remove that one. Add `## Slots` if it is missing. Replace your earlier bullet if there is one, and leave every other line as it is, whether or not the file changed since you started. `slots` drops the bullet once the item leaves its table, and turns a merged item's into a line under `## Where we left off`.
- The bullet is a pointer, one line, since every session in the project prints it at start. Its last fields are your status's `Next:` and `Also open:` lines, or `Open: none`, as the status rules above give them, and no PR is named before there is one:
  - `- #41 legend swatches · PR #90 ready · Dan said done 11-12, decision record on #41 · Open: none`
  - `- #42 header · PR #91 draft · nav built, contrast next · Next: keep the 2px rule? I'd keep it · Also open: swatch size`

  Where it stands takes a dozen words; the rulings, review results and filed follow-ups are on the issue and the PR, so name where they are instead of listing them.
- A follow-up goes where the skill sends it (a `## Next up` line you add, a memory, or an issue), never into your bullet, which goes away at the merge. `## Next up` runs in order, first thing first: a follow-up Dan calls next goes at the top, any other at the bottom. Remove no one else's line to make room; when `## Next up` is full, use a memory or an issue.
- Report the save in a line, plus the skill's inbox lines if you wrote any, then end on the status as usual.

## Beside the other slots

- Write only inside your folder, with absolute paths and `git -C`, since a shell can drift into another checkout. Memory is the exception: it is the main checkout's, shared by every slot, and saving a memory there is expected, as are the inbox entries `dan-save-session` writes.
- Scratch files, such as screenshots and measuring scripts, go in your scratchpad directory. Anything left in the folder shows in the table as uncommitted work and blocks the cleanup after a merge.
- The dev server is yours through `slots server stop` and `slots server start`. Start no second one, and stop no process by name: other slots and the main checkout run the same command.
- `slots start`, `slots stop` and `slots clear` are Dan's. He starts every item himself.
