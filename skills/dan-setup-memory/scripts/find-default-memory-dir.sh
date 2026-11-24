#!/bin/bash
# Locate the Claude Code default auto-memory dir for a given repo path.
#
# Claude Code stores per-project state under
#   ~/.claude/projects/<slug>/
# where <slug> is the absolute repo path with `/` replaced by `-`.
# Auto-memory (when no autoMemoryDirectory override is set) lives at
#   ~/.claude/projects/<slug>/memory/.
#
# Usage:   find-default-memory-dir.sh <absolute-repo-path>
# Stdout:  exactly one of these forms (no other lines):
#            FOUND <path>           - obvious slug exists, use this path
#            NONE                    - obvious slug missing, no other matches
#            CANDIDATES              - obvious slug missing, but other dirs
#            <path>                    sharing the repo basename exist;
#            <path>                    skill should ask the user which (if any)
#            ...                       is theirs.
# Exit:    0 on success, 2 on usage error. Never exits 1 — caller branches on
#          stdout instead, so empty stdout always indicates a script bug.

set -u

repo="${1:-}"
if [ -z "$repo" ]; then
    echo "usage: $0 <absolute-repo-path>" >&2
    exit 2
fi

projects_root="$HOME/.claude/projects"

if [ ! -d "$projects_root" ]; then
    echo "NONE"
    exit 0
fi

# Slug = repo path with all `/` -> `-`. Leading slash becomes a leading `-`.
slug="${repo//\//-}"
obvious="$projects_root/$slug/memory"

if [ -d "$obvious" ]; then
    echo "FOUND $obvious"
    exit 0
fi

# Fall back: scan for project dirs whose name ends in the repo basename.
# Catches edge cases where Claude Code applied transforms beyond the simple
# slash-to-hyphen swap (e.g., dots in the path).
basename="${repo##*/}"
matches=()
for dir in "$projects_root"/*/; do
    [ -d "$dir" ] || continue
    name="$(basename "$dir")"
    case "$name" in
        *"$basename")
            mem="${dir}memory"
            [ -d "$mem" ] && matches+=("$mem")
            ;;
    esac
done

if [ ${#matches[@]} -eq 0 ]; then
    echo "NONE"
else
    echo "CANDIDATES"
    for m in "${matches[@]}"; do
        echo "$m"
    done
fi
exit 0
