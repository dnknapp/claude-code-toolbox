---
description: Redirect auto-memory into this repo's ./.memory/ via .claude/settings.local.json. Migrates any pre-existing memories from the slug-derived default location.
disable-model-invocation: true
argument-hint: "[skip|nag off]"
---

You are configuring per-project auto-memory for the current repository.

## Steps

1. **Confirm we're in a git repo.** Run `git rev-parse --show-toplevel`. If it fails, tell the user this command only works inside a git repo and stop.

2. **Check current state.** First check existence with `ls <repo-root>/.claude/settings.local.json`. If it exists, use the **`Read` tool** (not `cat`/`Bash`) to load it — the harness only counts the `Read` tool toward the Read-before-Write requirement, so a `Bash cat` here will cause step 6's `Edit`/`Write` to fail.
   - If `autoMemoryDirectory` is already set, report the current value to the user and ask whether to change it. If they say no, stop.
   - If a `memorySetupNagSkipped` flag is set, mention it and ask whether to clear it as part of this run.

3. **Compute the target path:** `<repo-root>/.memory`. When the repo is under `$HOME`, write the path as `~/<path below home>` (e.g. `~/Sites/foo/.memory`), not the absolute form: a `~/` path still points at the project after it is copied to another machine with the same layout under its home folder, whose home path differs. Use the absolute path only for a repo outside `$HOME`.

4. **Create the directory** if missing: `mkdir -p "<repo-root>/.memory"` (the absolute form; the shell is not the setting).

5. **Detect existing memories at the default location and offer to migrate.**
   Run `${CLAUDE_SKILL_DIR}/scripts/find-default-memory-dir.sh "<repo-root>"`. The output's first line is one of:
   - `NONE` — no default-location memory dir exists. Continue to step 6.
   - `FOUND <path>` — the slug-derived default exists at `<path>`. Treat that as the source dir.
   - `CANDIDATES` — the obvious slug didn't exist, but other project dirs share this repo's basename. Subsequent lines are candidate paths. Show them to the user, ask which (if any) is theirs, and use their answer as the source dir. If they say "none of them", continue to step 6.

   With the resolved source dir:
   - List its contents (`ls -la <source>`). If empty, or the only meaningful file is a stub `MEMORY.md`, report nothing to migrate and continue to step 6.
   - Count entries and surface the list to the user. Ask: **move**, **copy**, or **skip**?
     - One-line tradeoff: move = clean cutover, no duplication; copy = old dir kept as a safety backup; skip = old memories become invisible to Claude after the redirect (still on disk, just not loaded).
   - **Conflict guard.** Before moving or copying, list `<repo-root>/.memory/`. If it contains anything beyond what step 4 just created (i.e., it already has files), do NOT overwrite. Show the user both directories' contents and ask how to resolve before proceeding.
   - **Move** →
     ```
     bash -c 'shopt -s dotglob nullglob; mv "<source>"/* "<repo-root>/.memory/"' && rmdir "<source>" 2>/dev/null || true
     ```
     `dotglob` ensures hidden files come along. `rmdir` only succeeds if `<source>` is now empty; failure is harmless and ignored.
   - **Copy** → `cp -R "<source>/." "<repo-root>/.memory/"`. Tell the user the original is untouched at `<source>` and they can delete it manually once they've confirmed the new location works.
   - **Skip** → leave both alone.

6. **Update `.claude/settings.local.json`.** Merge — don't clobber. Preserve any existing keys (permissions, sandbox, etc.). Set `autoMemoryDirectory` to the path from step 3 (`~/` form under home). If `memorySetupNagSkipped` was set and the user agreed, remove it.
   - If the file already exists: you already read it in step 2 — use the `Edit` tool to apply the merge in place.
   - If it doesn't exist: create the parent dir if needed (`mkdir -p <repo-root>/.claude`), then use `Write` to create it with just `{"autoMemoryDirectory": "..."}`.

7. **Prompt the user about gitignore.** Do NOT pick for them — this is a per-project judgment call. Surface relevant signals first:
   - Unique author count: `git log --format='%ae' | sort -u | wc -l`
   - Whether the repo has a remote (`git remote -v`)
   - Whether `.gitignore` already covers `.memory/` (would be a no-op)
   Then ask plainly: "Should `.memory/` be tracked in git or added to `.gitignore` for this repo?" Include a one-line tradeoff reminder: track = audit trail + visible diffs (good for solo / single-user repos); gitignore = no PR noise, no leaking project-specific notes (good for team / shared repos).
   Wait for the answer.
   - **Track** → leave `.gitignore` alone. Mention they'll see memory writes in `git status` / `git diff`.
   - **Gitignore** → append `.memory/` to `<repo-root>/.gitignore` (create if missing). Skip if `.memory/` is already present (exact match or covered by a broader pattern).

8. **Confirm.** Report the memory dir path as written in the setting, the path of the settings file, the gitignore decision, and what was migrated (move/copy/skip + entry count, or "nothing to migrate"). Note that the override takes effect on the **next** Claude Code session in this directory — settings load before this slash command runs, so the current session still uses the old path.

## Opt-out variant

If the user invokes this command with `skip` or `nag off` (check `$ARGUMENTS`), instead of doing setup, merge `{"memorySetupNagSkipped": true}` into `<repo-root>/.claude/settings.local.json`: read it first if it exists, then `Edit` to add the key (or `Write` a new file with just that key if it doesn't exist). Then confirm. This silences the SessionStart nag for this repo without redirecting memory.

## Notes

- `autoMemoryDirectory` is rejected from `.claude/settings.json` (project-shared) for security. It must go in `settings.local.json` (per-machine), user, or managed scope. We use local.
- Path must be absolute or `~/`-expanded. Template variables (`${CLAUDE_PROJECT_DIR}` etc.) are not supported as of Claude Code 2.1.119.
- Don't set this in `~/.claude/settings.json` as a one-size-fits-all — there's no per-project substitution, so it would force every repo's memory into one shared dir.
- The dir is named `.memory/` (dotfile) so it sits alongside `.claude/` / `.git/` and stays out of casual file listings; visibility of *contents* is controlled by the gitignore decision in step 7, not by the leading dot.
