---
name: slots
description: Slots - several issues or PRs worked at once, each in its own folder with its own background Claude Code session. Use when the user asks to start, resume, stop or clear an item "in a slot", asks for the slots table, gives a list of issues to plan into slots, or wants a project set up for slots.
argument-hint: "[issue numbers to plan]"
---

A **slot** is one item, an issue or a PR, in flight: a folder beside the main checkout, a dev server on its own port, and a background session that works the item live with Dan. The `slots` script does all the mechanics and is on PATH (`~/.local/bin/slots`, linked to `${CLAUDE_SKILL_DIR}/scripts/slots.py`). This file is for a session in the main checkout. A slot session works from `slot-instructions.md`, which arrives in its first message.

## Running a command for Dan

Four jobs, one command each. Keep them apart when you describe them: Dan once read cleanup as needing a restart, and the bare table as erasing a stopped item.

| He wants | Run |
|---|---|
| to see where everything stands | `slots` (starts nothing; removes the folder of any item whose PR has merged) |
| an item started, or a stopped one picked up where it was | `slots start 41`, `slots start pr 73`, `slots start 58+59` for two issues in one item, `slots start 42 --base issue-41-…` to branch from another item's unmerged branch (its PR targets that branch), `slots start` for the next queued one |
| a pause: server and session off, work kept | `slots stop 41`, or `slots stop` for all |
| an item abandoned before its PR merged, or a queued one taken off the queue | `slots clear 41` |

- A stopped item starts again in a new session, handed the old session's last message, its saved `## Slots` bullet and the branch. When Dan says "resume 41" or "pick up 41", that is this plain start. Add `--resume` (`slots start 41 --resume`) only when he asks for the old session or its conversation back: it wakes the old session with its whole history.
- Run exactly what he named. Starting an item is always his call, so a finished item is a break for him and never a cue to start the next.
- A direction line is his words, verbatim, in quotes after the number: `slots start 41 "keep them at 12px"`. Write none for him. With none, the slot's opener asks.
- Show him the output as printed, in a code block. The table is derived on demand from git, GitHub and the session list, so it is the answer to "where is everything".
- When `clear` or the cleanup after a merge refuses, pass on what it says and stop there. It refuses for one of three reasons, and its message says which:
  - Work would be lost. What happens to that work is Dan's decision.
  - Something still runs in the folder ("still in use"): a shell or editor left there, or a hook that outlived its session. Nothing was deleted. Once that process has gone, the next `slots` or `slots clear` finishes.
  - The folder was only partly deleted. The item is gone, and the folder holds the files it lists. Dan looks at them and deletes the folder.
- After a start you are finished. Dan attaches to each slot himself.

## Passing Dan's decisions to a slot

When Dan decides something in this session that bears on an open item, such as an answer to a question your research raised, a change of scope or a ruling, send it to that item's slot with `SendMessage` without asking first. Address it by the session's name from `ListAgents`, which starts with the project and the item (`web #41 …`). Then say in one line of your reply which slot got what, so he can catch a wrong one.

- Start the message with `Dan, via the main checkout:` so the slot treats it as his note.
- Give his decision in his words, with a link to where it is recorded (issue comment, research doc), and add nothing of your own: no scope notes, no plan. Direction is his. In September an orchestrator's own launch notes set the direction, and 3 of 13 were walked back.
- When it bears on several items, send each its own message.

Send nothing else unasked. A slot finds overlaps and a moved base branch itself, in the table. When `slots start` reports that a direction line was not sent to a running session, send that line the same way.

## Planning a list

When Dan gives several issues and wants help grouping them (`/slots 41 42 17 58 59`):

1. Run `slots` to see what is already open, and read every issue he listed with its comments.
2. Send one message, in his order: which issues belong together in one item, and which are likely to collide on the same files, with each other or with an open item. Name the files or the component for each collision. End by asking which to start now. Done when every issue he listed sits in exactly one proposed item.
3. He adjusts the grouping, may add a line of direction to any item, and says which to start.
4. Write the whole plan to `~/.claude/slots/<project>/queue.md`, where `<project>` is the first word of the table's first line. One list line per item, in his order:

   ```
   - 41 — keep them at 12px
   - 58+59 — both are the date picker
   - pr 73
   ```

5. Start the ones he chose, by number: `slots start 41 58`. A started item takes its grouping and direction from the queue and leaves it. Run `slots` once more: the rest show as queued, and a line the script could not read is reported there. Then you are finished.

His order stands and the grouping is a proposal: say what you see and let him move things. What follows a dash in the queue is only ever his own words.

## Setting up a project

Once per project per machine, in the project's main checkout: `slots setup`. It detects the folder prefix, base branch, install, dev-server and check commands, and prints them with what each is for. Read the values back to Dan and correct any he names with a flag, for example `slots setup --dev "npm run dev -- -p {port}" --address "http://devbox.local:{port}"`. `{port}` is filled in per item; the address is where he looks from his own machine, which is not `localhost` when the code runs on another one.

Several projects can be set up side by side, each with its own items and queue, sharing one run of ports. A command acts on the project whose main checkout or item folder it is run in. Anywhere else, name the project with `slots -p <part of its name> ...`; a bare `slots` there prints every project's table.
