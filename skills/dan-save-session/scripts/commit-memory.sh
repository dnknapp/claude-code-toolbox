#!/usr/bin/env bash
# Commit a memory directory on the branch its own repo has checked out.
# Usage: commit-memory.sh <memory-dir> "<what changed>"
# Prints one line for the report. Exit 0 = committed, skipped or nothing to do;
# exit 1 = git refused (its message is printed above the line).
set -u
dir=${1:?memory dir}
what=${2:?commit subject}

[ -d "$dir" ] || { echo "skip: $dir does not exist"; exit 0; }
# Run git from inside the directory, so a slot worktree's session reaches the repo that holds it.
cd "$dir" || exit 1
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "skip: $dir is not in a git work tree"; exit 0; }
top=$(git rev-parse --show-toplevel)

git check-ignore -q .
case $? in
  0) echo "skip: $dir is ignored in $top"; exit 0 ;;
  1) ;;
  *) echo "skip: git check-ignore failed in $top"; exit 0 ;;
esac

# Another session's merge, cherry-pick, revert or rebase owns the index; staging into it would ride
# along with their commit.
for marker in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply; do
  [ -e "$(git rev-parse --git-path "$marker")" ] \
    && { echo "skip: $top has a ${marker%_HEAD} in progress; memory left uncommitted"; exit 0; }
done

# On a detached HEAD the commit would belong to no branch and be lost.
branch=$(git symbolic-ref -q --short HEAD) \
  || { echo "skip: $top has a detached HEAD; memory left uncommitted"; exit 0; }

# A refusal unstages what this script staged, so nobody else's next commit takes it.
refused() { git reset -q -- . 2>/dev/null; echo "$1 refused in $top (message above); memory left uncommitted"; exit 1; }

git add -A -- . || refused "git add"
if git diff --cached --quiet -- .; then
  echo "nothing to commit in $dir"; exit 0
fi
# The pathspec keeps out whatever other sessions have staged elsewhere.
git commit -q -m "memory: $what" -- . || refused "commit"

msg="committed $(git rev-parse --short HEAD) on $branch in $top"
if ! upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null); then
  echo "$msg; no upstream"
# A push sends every unpushed commit on the branch, and in a shared checkout some may be another
# session's work in progress.
elif git log --format=%s '@{u}..HEAD' | grep -qv '^memory:'; then
  echo "$msg; upstream $upstream; push-unsafe: the branch has unpushed commits that are not memory commits"
else
  echo "$msg; upstream $upstream; push-safe"
fi
