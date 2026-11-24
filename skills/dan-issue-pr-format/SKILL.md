---
name: dan-issue-pr-format
description: Issue and PR format for a repo with no format skill of its own. Use when filing or retitling a GitHub issue, starting work on one, or writing a PR body and its issue links. Where the project has `gh-issue-pr-format`, use that skill and skip this one.
---

# GitHub issue & PR format

The fallback format, for a repo that brings none. The project's own rules win:
when the skill listing has `gh-issue-pr-format`, load it and stop reading this
one; a PR or issue template under `.github/`, or a format the repo's rule files
set, replaces the matching section here. In someone else's project, its
contributing guide and the shape of its recent issues and PRs replace all of it.

Keep the **balance**: enough context for a coding agent to implement it
correctly, short enough for a human to grasp the problem and spot a duplicate.
When in doubt, cut prose, not context.

## Titles

Plain English, the way you'd say it to the project team. A title is read in a
list, with the body out of reach: someone who knows the product but not the
code should understand the issue from the title alone.

- **Lead with the feature or screen by the name the team says out loud**, then
  a colon: `Timeline: year labels overlap on a phone`. A code, ticket ID,
  bracketed tag, abbreviation or component name in that position
  (`[FE-042]`, `TL:`, `GloModal:`) is one only the code's authors can read.
- **Say what a user sees.** The mechanism is the fix, and the body's to carry:
  `Map: a pin held down stays highlighted after the step changes`, over
  `Release the pointer-held pin when its button unmounts`. Work with no
  visible side names the one file or tool that is its clearest handle.
- **Keep the scope's shape.** A shortened title still carries what sets the
  size of the work: a rebuild or a tweak, every screen or one, the trigger that
  reproduces a bug. Test: can a reader guess how big the work is?
- **One job per title** — "X and Y" only when the issue is genuinely both.
  About 70 characters, 90 at most; a list belongs in the body.
- **Retitle when the scope moves.** When a comment sends half the issue
  elsewhere, or the body is rewritten, change the title in the same edit.

## Priority

A **GitHub label**, never a title prefix. Use the priority labels the repo
already has, in its spelling, one per issue; where it has none, leave priority
off. Leave it unset too when it's genuinely unknown — `high` is a judgement,
not a safe default.

## Related issues

Issues and PRs both name the issues they relate to in a `## Related issues`
section: one line per issue, each starting with its keyword.

| Keyword      | Means                      | In an issue                | In a PR                                                              |
| ------------ | -------------------------- | -------------------------- | -------------------------------------------------------------------- |
| `Closes #N`  | this PR finishes #N        | not used                   | #N closes when the PR merges — see [Closing issues](#closing-issues) |
| `Refs #N`    | related, not finished here | a cross-link, nothing more | a link that leaves #N open                                           |
| `Part of #N` | a sub-task of #N           | names its parent           | not used                                                             |

- **`Closes #N`** only for a complete, **verified** fix of the _whole_ issue —
  verified means you exercised the fix, not that it compiles. Anything less is
  `Refs #N`, with a note on what's left.
- **One keyword per issue.** GitHub closes only the issues that carry their own
  keyword: `Closes #12 #14` closes #12 alone.
- **Say how a `Refs` relates:** `Refs #98 — same dropdown, mobile layout`.
- **`Part of #N` is text GitHub does not read.** File the sub-task with
  `gh issue create --parent <N>` as well, so it is a sub-issue of #N.
- **Keywords stay in this section.** GitHub reads `closes`, `fixes` and
  `resolves` before `#N` anywhere in a PR body, prose included: "this fixes
  #12 only partly" in the Summary closes #12 on merge. Everywhere else, write
  `See #N`.
- **The human is authoritative.** If the human — or the issue itself — says how
  to link or close, do that.

A wrongly-closed issue silently drops work; an issue left open is a visible
loose end.

## Issue format

Required sections, plus `## Related issues` when there are any:

```
## Problem
<one line a human can grasp — what's wrong or what's missing>

## Why it's tracked
<one line — the impact, or why this is worth an issue and not just a fix>

## Details
<enough for an agent to act — see bug vs. feature below>

## Related issues
Part of #<parent>                   ← only for a sub-issue
Refs #<n> — <how it relates>
```

- **Bugs** — `Details` carries steps to reproduce, expected vs. actual, and
  where it shows up (repo/route/component, env).
- **Features** — `Details` carries **acceptance criteria**: a short checklist of
  what "done" looks like, so an agent knows when it's finished and a reviewer
  knows what to check.

Keep issues short; a long `Details` usually means the issue should be split.
Add the labels the repo already uses for priority and area. Before opening one,
search open _and_ closed issues for the same symptom or feature: comment on an
existing issue rather than filing a second, and reopen a closed one that's
back, with fresh repro.

## Starting work on an issue

Assign the issue before the first edit, to the person doing the work — the
human whose session this is:

```bash
gh issue edit <n> --add-assignee @me
```

The assignee is how everyone else sees the issue is taken. When the work grows
to cover another issue, assign that one as it is picked up.

## Base branch

A PR targets the branch the repo's merged PRs went into, and the default
branch when it has none. A branch's name settles nothing: a repo can keep a
`dev` it stopped merging into, or integrate on one called `testing`. Read the
base from the repo and pass it explicitly:

```bash
BASE=$(gh pr list --state merged --limit 10 --json baseRefName \
  --jq '[.[].baseRefName] | group_by(.) | max_by(length) | .[0] // empty')
[ -n "$BASE" ] || BASE=$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name)
gh pr create --base "$BASE" ...
```

A human can always override the base for a specific PR.

## Closing issues

A PR's `Closes` lines close issues only when it merges into the repo's
**default branch** (`gh repo view --json defaultBranchRef --jq .defaultBranchRef.name`).
Where PRs target the default branch, that is every PR. Work committed straight
to the default branch has no PR to carry the link: end the commit message with
`Closes #N`, and the issue closes when the commit is pushed.

Where feature PRs merge into an integration branch first (`dev` below, whatever
the repo calls it):

| Default branch | Feature → `dev` PR's `## Related issues`                      | `dev` → `main` PR's `## Related issues`                         |
| -------------- | ------------------------------------------------------------- | --------------------------------------------------------------- |
| `dev`          | `Closes` / `Refs` per issue; merging closes the `Closes` ones | `None — release`; the body is release notes                     |
| `main`         | `Refs` only — this merge closes nothing                       | `Closes #N` for each issue actually complete; omit the WIP ones |

An integration or infra merge that genuinely relates to no issue says
`None — integration merge only`.

## PR body structure

Use this for every PR body unless the human asks for something different:

```
## Summary
<1-2 sentence summary of what the PR does and why>

## Changes
- <bullet per most important change, bolded lead-in where useful>
- ...

## Related issues
Closes #<n>                         ← each issue this PR finishes
Refs #<n> — <how it relates>        ← each one it touches but doesn't finish
```

- **Summary** is the why + what; **Changes** is the handful that matter, not a
  file-by-file diff recap.
- **Related issues** follows [Related issues](#related-issues) and
  [Closing issues](#closing-issues). Find the issues by matching the branch or
  feature to open ones, and fill the section with real numbers or an explicit
  `None — <reason>`; a bare `Closes #` reads the same as a forgotten field.
- **Known gaps** — work the PR leaves undone, a review deferral — each name
  their issue; file it when there is none. An issue this PR also works on is
  `Refs #N` in `## Related issues`; any other is `See #N`. A gap that lives
  only in a merged PR body is where leftovers get lost.
