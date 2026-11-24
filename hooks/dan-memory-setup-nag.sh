#!/bin/bash
# SessionStart hook with two branches for auto-memory:
#
# 1. LOAD: when autoMemoryDirectory resolves to a path in any settings layer,
#    emit a systemMessage naming the resolved directory and the contents of
#    MEMORY.md (capped at 200 lines). Gives the assistant a startup signal
#    so it doesn't fall back to the slug-derived default path.
#
# 2. NAG: when no autoMemoryDirectory is set anywhere, prompt the user to
#    run /dan-setup-memory to redirect into a visible .memory/ in the repo.
#
# Both branches are no-op when:
# - source is not "startup" (skip resume/clear/compact — would be noisy)
# - cwd is not in a git repo
# - cwd is under ~/.claude (don't redirect Claude's own config dir)
# - autoMemoryEnabled is false anywhere visible
#
# Only the NAG branch is suppressed by memorySetupNagSkipped: true in the
# repo's settings.local.json. The LOAD branch always fires when applicable —
# that flag silences the setup nag, not memory loading.
#
# Settings-layer precedence for autoMemoryDirectory (highest first):
#   <repo>/.claude/settings.local.json
#   ~/.claude/settings.json
#   /Library/Application Support/ClaudeCode/managed-settings.json (Linux: /etc/claude-code/)

set -u

input=$(cat)

source_field=$(printf '%s' "$input" | /usr/bin/python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("source",""))
except Exception:
    pass' 2>/dev/null)

# The LOAD branch runs on startup AND on clear/resume/compact: after a /clear the
# context is wiped, and without a re-inject the index and NEXT.md are gone for the
# rest of that session — which kills the passive recall the index exists for. Only
# `startup` gets a visible systemMessage though; re-printing NEXT.md on every clear
# would be the noise this redesign removed.
case "$source_field" in
    startup)               VISIBLE=1 ;;
    clear|resume|compact)  VISIBLE=0 ;;
    *)                     exit 0 ;;
esac

# Must be in a git repo
repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0

# Don't fire inside ~/.claude itself
case "$repo_root" in
    "$HOME/.claude"*) exit 0 ;;
esac

# JSON probe: read a top-level key from a JSON file. Path passed via env to
# avoid quoting issues. Prints the key's value (JSON-encoded) or empty.
read_json_key() {
    F="$1" K="$2" /usr/bin/python3 -c '
import json, os, sys
try:
    with open(os.environ["F"]) as fp:
        d = json.load(fp)
    v = d.get(os.environ["K"])
    if v is None:
        sys.exit(0)
    print(json.dumps(v))
except Exception:
    sys.exit(0)
' 2>/dev/null
}

local_settings="$repo_root/.claude/settings.local.json"
user_settings="$HOME/.claude/settings.json"
managed_settings="/Library/Application Support/ClaudeCode/managed-settings.json"
[ "$(uname -s)" = Linux ] && managed_settings="/etc/claude-code/managed-settings.json"

# Auto-memory globally disabled? Don't fire either branch.
for f in "$user_settings" "$local_settings"; do
    [ -f "$f" ] || continue
    if [ "$(read_json_key "$f" autoMemoryEnabled)" = "false" ]; then
        exit 0
    fi
done

# Resolve autoMemoryDirectory: local > user > managed.
resolved_dir_json=""
for f in "$local_settings" "$user_settings" "$managed_settings"; do
    [ -f "$f" ] || continue
    val=$(read_json_key "$f" autoMemoryDirectory)
    if [ -n "$val" ]; then
        resolved_dir_json="$val"
        break
    fi
done

# LOAD branch. Two audiences, deliberately different payloads:
#
#   additionalContext (model only) — resolved path + full MEMORY.md index +
#     NEXT.md. The index is what makes passive recall work, so it stays.
#
#   systemMessage (terminal, user reads this) — NEXT.md only, plus a one-line
#     memory summary. The index is NOT repeated here: it was 10KB in the larger
#     repos, which both tripped the hook-output truncation cap and printed a
#     wall of text nobody reads. Continuity beats inventory at startup.
if [ -n "$resolved_dir_json" ]; then
    DIR_JSON="$resolved_dir_json" REPO_ROOT="$repo_root" VISIBLE="$VISIBLE" \
    /usr/bin/python3 -c '
import json, os

raw = os.environ["DIR_JSON"]
try:
    path = json.loads(raw)
except Exception:
    path = raw

# A relative autoMemoryDirectory is relative to the repo, not to wherever the
# session was launched from. Resolving against cwd silently reports "0 memories"
# from a subdirectory.
mem_dir = os.path.expanduser(path)
if not os.path.isabs(mem_dir):
    mem_dir = os.path.join(os.environ["REPO_ROOT"], mem_dir)
header = "Auto-memory directory for this repo: `" + mem_dir + "`"


def read(name):
    try:
        with open(os.path.join(mem_dir, name)) as fp:
            return fp.read()
    except Exception:
        return ""


def clamp(text, cap):
    lines = text.rstrip().splitlines()
    if len(lines) > cap:
        return "\n".join(lines[:cap]) + "\n... [truncated]"
    return "\n".join(lines)


# Memory files, excluding the index and the continuity file.
try:
    count = len([
        f for f in os.listdir(mem_dir)
        if f.endswith(".md") and f not in ("MEMORY.md", "NEXT.md")
    ])
except Exception:
    count = 0

index = read("MEMORY.md").strip()
nxt = read("NEXT.md").strip()


# --- model-facing ---
# The MEMORY.md index is deliberately NOT injected here. Claude Code loads it
# natively into context from this same directory (verified 2026-08-12: a dev-kit
# session reported 57 index entries from the native harness auto-memory block,
# alongside the copy this hook was adding). Emitting it again was pure duplication,
# and since
# the harness truncates any single hook output field at ~10KB, the duplicate was
# the copy that got cut, while the native one arrived whole.
#
# NEXT.md is different: it is not part of the native memory system, so this hook
# is the only thing that puts it in context.
ctx = [header]
if nxt:
    ctx.append("Session continuity (`NEXT.md`) — where the last session left off:\n\n"
               + clamp(nxt, 120))
context_msg = "\n\n".join(ctx)

# --- user-facing ---
if index:
    summary = "%d memor%s at `%s`" % (
        count, "y" if count == 1 else "ies", mem_dir,
    )
else:
    summary = "No MEMORY.md index yet at `%s`" % mem_dir
if nxt:
    visible = clamp(nxt, 40) + "\n\n---\n" + summary
else:
    visible = (
        summary
        + "\n\nNo `NEXT.md` yet — run `/dan-save-session` when you finish a session "
        "to record where it left off, and it will show here next time."
    )

out = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context_msg,
    },
}
if os.environ.get("VISIBLE") == "1":
    out["systemMessage"] = visible
print(json.dumps(out))
'
    exit 0
fi

# NAG branch: no autoMemoryDirectory anywhere. Suppressible per-repo.
# Startup only — nagging again on every clear/resume would be noise.
[ "$VISIBLE" = "1" ] || exit 0

if [ -f "$local_settings" ]; then
    if [ "$(read_json_key "$local_settings" memorySetupNagSkipped)" = "true" ]; then
        exit 0
    fi
fi

REPO="$repo_root" /usr/bin/python3 -c '
import json, os
repo = os.environ["REPO"]
msg = (
    "\n\nAuto-memory for `" + repo + "` is going to the default hidden location under `~/.claude/projects/`.\n\n"
    "- Run `/dan-setup-memory` to redirect it into a visible `.memory/` folder in this repo\n"
    "- Run `/dan-setup-memory skip` to silence this notice"
)
print(json.dumps({"systemMessage": msg}))
'

exit 0
