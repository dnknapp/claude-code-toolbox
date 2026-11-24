# claude-code-toolbox

Skills, subagents and hooks from Dan Knapp's Claude Code setup, shared in case
some of them help you. The layout mirrors `~/.claude/`, so each piece goes in
the same place under yours.

This is a copy, exported from the private repo that holds the rest of the
configuration. Issues and pull requests are welcome, but a change gets made in
the private repo and arrives here with the next export, so a merged pull
request may come back reworded.

Words these files use in a sense of their own (slot, session handoff, idle
saver, dev kit) are defined in [`GLOSSARY.md`](./GLOSSARY.md).

MIT licensed (`LICENSE`); the skills forked from Matt Pocock's keep his MIT
notice (`THIRD-PARTY-LICENSES.md`).

## Skills

A skill is a folder with a `SKILL.md` that Claude loads when its description
matches the task, or when you type `/<name>`.

| Skill | What it does | Needs |
|---|---|---|
| `code-review` | Reviews a change since a fixed point on three axes: Correctness, Standards, and Spec (against the issue). Runs one subagent per axis in parallel. | The `blind-reviewer`, `reviewer` and `issue-verifier` agents. Replaces the built-in `/code-review`. |
| `parallel-tracks` | Splits implementation work into self-contained tracks and runs one `track-implementer` agent per track. | `track-implementer`; a project with `npm run check`. |
| `research` | Investigates a question against primary sources and writes the findings to a Markdown file in the repo. | The `researcher` agent. |
| `slots` | Works several issues or PRs at once, each in its own folder with its own dev server and background Claude Code session. | `gh`, `claude --bg`, and the script on your `PATH` (see below). |
| `grilling` | Questions you hard about a plan or decision, in rounds of about five questions. | Nothing. |
| `diagnosing-bugs` | A diagnosis loop for hard bugs and performance regressions. | Nothing. |
| `prototype` | Builds a throwaway prototype to answer a logic or UI design question. | Nothing. |
| `wizard` | Writes an interactive bash script that walks a person through steps only they can do (dashboards, credentials, cutovers). | Nothing. |
| `writing-for-agents` | How to write a skill, `CLAUDE.md` or `AGENTS.md` that an agent will follow. | Nothing. |
| `subagent-mechanics` | How to write a subagent definition: description, report contract, tools, model tier. | Nothing. |
| `dan-save-session` | Saves new auto-memories and rewrites `NEXT.md`, the handoff the next session starts from. | Works best with `dan-setup-memory` and the memory hook. |
| `dan-handoff` | Writes the handoff file a fresh orchestrator resumes a multi-agent run from. | Used by `parallel-tracks` and the cache guard. |
| `dan-setup-memory` | Points a repo's auto-memory at `./.memory/` inside the repo, moving any existing memories there. | Type `/dan-setup-memory`. |
| `dan-audit-memory` | Sweeps a memory directory for stale or wrong memories with a script, then fixes what the evidence supports. | Type `/dan-audit-memory`. |
| `dan-browser-automation` | Ground rules for driving Chrome through the claude-in-chrome extension, so what Claude sees is real. | claude-in-chrome. |
| `dan-issue-pr-format` | An issue and PR format. | Nothing; see "Fallback skills". |
| `dan-project-glossary` | Keeps a project's `GLOSSARY.md` as words get settled. | Nothing; see "Fallback skills". |

Several of these started as forks of
[Matt Pocock's skills](https://github.com/mattpocock/skills) and have been
changed since; `THIRD-PARTY-LICENSES.md` lists them.

**Fallback skills.** `dan-issue-pr-format` and `dan-project-glossary` stand in
for `gh-issue-pr-format` and `project-glossary`, skills that the dev kit ships
into its projects (see `GLOSSARY.md`). The `dan-skill-fallbacks.py` hook switches each one off in
any project that has the kit's version (`fallback.json` names it). Without
that hook, they are ordinary skills.

## Agents

| Agent | Model | What it does |
|---|---|---|
| `blind-reviewer` | Opus | Adversarial correctness review, formed from the code alone, that proves each finding (usually by running something) instead of suspecting it. Read-only. |
| `reviewer` | Opus | Reviews a branch against the repo's documented conventions, a code-smell baseline, and whether new tests can actually fail. Read-only. |
| `issue-verifier` | Opus | Checks implemented work against the issue, acceptance criteria or plan it was meant to satisfy. Read-only. |
| `scout` | Opus | Reads a pile of local sources and returns one report or writes one document, keeping the reading out of the main session. |
| `researcher` | Sonnet | External research against primary sources: official docs, source code, changelogs, issue trackers. |
| `track-implementer` | Opus | Implements one bounded track of work inside its assigned scope. Never commits. |
| `docs-sync` | Sonnet | Updates a project's behavior docs to match a diff. |
| `project-smoke` | Haiku | Runs `npm run check` and `npm run build`, serves the build, and checks that key routes respond. |

## Hooks

Each script's header comment documents it in full. `settings.example.json`
shows how they are wired up.

| Hook | Event | What it does |
|---|---|---|
| `dan-memory-setup-nag.sh` | SessionStart | In a repo whose memory lives in the repo, shows `NEXT.md` in the terminal and adds it to Claude's context. In a repo whose memory doesn't, suggests `/dan-setup-memory`. |
| `dan-status-check-redirect.sh` | UserPromptSubmit | When you ask "where did we leave off?" or similar, tells Claude to check git and the repo before answering from memory. |
| `dan-cache-cold-guard.py` | UserPromptSubmit, SessionStart, Stop | For sessions past 100k tokens: stops the first message sent after the prompt cache has expired (sending it again goes through), and saves the session with `/dan-save-session` after about 35 idle minutes. Reads plan usage that `statusline.sh` saves. |
| `dan-skill-fallbacks.py` | SessionStart | Switches off a fallback skill in any project that ships its own version. |
| `dan-config-behind.sh` | SessionStart | Says when a machine's live config is behind the repo it is deployed from. Only useful with a deploy setup like the private repo's. |
| `dan-session-save-nudge.sh` | Stop | Not wired up. A size-triggered save prompt, kept for reference. |

`statusline.sh` is a status line showing the directory, git branch, changed
files, push state, model and effort. `themes/atom-one-dark.json` is a color
theme.

## Installing a piece

- **A skill**: copy its whole folder to `~/.claude/skills/<name>/`, since
  some bundle scripts or reference files. For `slots`, also put the script on
  your `PATH`:
  `ln -s ~/.claude/skills/slots/scripts/slots.py ~/.local/bin/slots`.
- **An agent**: copy its file to `~/.claude/agents/`, then restart Claude
  Code.
- **A hook**: copy the script to `~/.claude/hooks/`, make it executable, and
  add its entry from `settings.example.json` to the `hooks` block of your
  `~/.claude/settings.json`. The hooks need `python3`, and some need `jq`.
  They run on macOS and Linux.

Check the Needs column first: a skill that calls agents by name needs those
agents too.

These files were written for one person's setup. Many name Dan, and some
refer to habits his global `CLAUDE.md` sets: draft PRs, a review on every PR,
a status footer on every reply. Edit those lines to suit how you work.
