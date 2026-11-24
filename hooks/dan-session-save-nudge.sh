#!/bin/bash
# Stop hook: once per session, when enough real work has accumulated, block the
# stop and tell Claude to save memories + refresh .memory/NEXT.md.
#
# WHY A Stop HOOK AND NOT SessionEnd:
#   SessionEnd fires on quit/clear but supports only systemMessage/terminalSequence,
#   cannot block, and the model can no longer act — the session is already over.
#   So it physically cannot write a memory. Stop is the only event that can hand
#   the model an instruction it will act on: exit code 2 "Prevents Claude from
#   stopping, continues the conversation", and the blocking message is "the reason
#   from your JSON's blocking decision when it makes one, and your stderr text
#   otherwise." Hence: stderr + exit 2.
#
#   Note the trap this avoids: the JSON `stopReason` field is explicitly "Not shown
#   to Claude" — it only reaches the user. Instruction text MUST go to stderr.
#
#   Consequence: the save happens at a turn boundary mid-session, not at quit. That
#   is a feature — it survives an abrupt quit, a crash, or a context blowout.
#
# LOOP SAFETY: the per-session marker is written BEFORE exiting 2, so the Stop that
# follows Claude's save turn sees the marker and exits 0. `stop_hook_active` is not
# a documented input field, so this script does not rely on it.
#
# No-op when:
# - cwd is not in a git repo, or is under ~/.claude
# - autoMemoryEnabled is false, or no autoMemoryDirectory resolves (nothing to save
#   into — the SessionStart nag branch covers that case instead)
# - sessionSaveNudgeDisabled: true in the repo's settings.local.json
# - the transcript is smaller than the tier threshold (session did little)
# - this session already fired at that tier
# - the last assistant message already mentions NEXT.md (just handled)

set -u

# Transcript-size tiers, in bytes. A session crossing the first gets one nudge; a
# marathon crosses the second and gets one more, because by then the first save is
# stale. Edit these to retune — note that `env` in settings.json does not reach the
# CLI process, so exporting an override from settings.json will not work.
#
# Calibrated 2026-08-12 against 81 real sessions across three work repos, whose
# sizes ran 0KB–18.4MB with a median of 1.17MB:
#   TIER_1 300KB  ≈ p20 → fires in ~81% of sessions (skips only trivial ones)
#   TIER_2 3.6MB  ≈ p90 → fires in ~15% (genuinely long sessions only)
# TIER_2 was initially 1.2MB, which sat right at the median and gave a typical
# session two nudges instead of one.
TIER_1=300000
TIER_2=3600000

input=$(cat)

eval "$(printf '%s' "$input" | /usr/bin/python3 -c '
import json, shlex, sys
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
for key, var in (
    ("session_id", "SESSION_ID"),
    ("transcript_path", "TRANSCRIPT"),
    ("cwd", "HOOK_CWD"),
    ("last_assistant_message", "LAST_MSG"),
):
    print("%s=%s" % (var, shlex.quote(str(d.get(key) or ""))))
' 2>/dev/null)"

SESSION_ID="${SESSION_ID:-}"
TRANSCRIPT="${TRANSCRIPT:-}"
HOOK_CWD="${HOOK_CWD:-}"
LAST_MSG="${LAST_MSG:-}"

[ -n "$SESSION_ID" ] || exit 0

# Already handled in the turn that just ended.
case "$LAST_MSG" in
    *NEXT.md*) exit 0 ;;
esac

cd "${HOOK_CWD:-$PWD}" 2>/dev/null || exit 0

repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
case "$repo_root" in
    "$HOME/.claude"*) exit 0 ;;
esac

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

for f in "$user_settings" "$local_settings"; do
    [ -f "$f" ] || continue
    [ "$(read_json_key "$f" autoMemoryEnabled)" = "false" ] && exit 0
done

# Per-repo opt-out.
if [ -f "$local_settings" ]; then
    [ "$(read_json_key "$local_settings" sessionSaveNudgeDisabled)" = "true" ] && exit 0
fi

# Memory must have a resolved home, else there is nothing to save into.
memory_dir_json=""
for f in "$local_settings" "$user_settings" "$managed_settings"; do
    [ -f "$f" ] || continue
    val=$(read_json_key "$f" autoMemoryDirectory)
    if [ -n "$val" ]; then
        memory_dir_json="$val"
        break
    fi
done
[ -n "$memory_dir_json" ] || exit 0

memory_dir=$(DIR_JSON="$memory_dir_json" /usr/bin/python3 -c '
import json, os
raw = os.environ["DIR_JSON"]
try:
    print(os.path.expanduser(json.loads(raw)))
except Exception:
    print(os.path.expanduser(raw))
' 2>/dev/null)
[ -n "$memory_dir" ] || exit 0

# How much work has this session done?
[ -n "$TRANSCRIPT" ] && [ -f "$TRANSCRIPT" ] || exit 0
size=$(/usr/bin/stat -f%z "$TRANSCRIPT" 2>/dev/null || echo 0)

tier=0
if [ "$size" -ge "$TIER_2" ]; then
    tier=2
elif [ "$size" -ge "$TIER_1" ]; then
    tier=1
fi
[ "$tier" -gt 0 ] || exit 0

# Once per tier per session.
marker_dir="${TMPDIR:-/tmp}/dan-session-save"
marker="$marker_dir/$SESSION_ID"
fired=0
[ -f "$marker" ] && fired=$(cat "$marker" 2>/dev/null || echo 0)
case "$fired" in ''|*[!0-9]*) fired=0 ;; esac
[ "$tier" -gt "$fired" ] || exit 0

# Write the marker BEFORE blocking — this is the loop guard.
mkdir -p "$marker_dir" 2>/dev/null || exit 0
printf '%s' "$tier" > "$marker" 2>/dev/null || exit 0

# Keep this to one line. Any exit-2 stderr renders in the user's terminal as a
# "Stop hook error", so length here is pure noise — and the procedure lives in the
# skill, which is the single source of truth for it.
echo 'Before finishing: invoke the `dan-save-session` skill to capture this session'"'"'s handoff.' >&2

exit 2
