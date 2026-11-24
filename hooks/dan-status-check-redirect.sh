#!/bin/bash
# UserPromptSubmit hook: when the user asks a status-check question,
# inject a directive telling Claude to investigate the repo first instead of
# answering from auto-memory. No-op on every other prompt.

set -u

input=$(cat)

# Extract the user's prompt from the hook's JSON payload.
prompt=$(printf '%s' "$input" | /usr/bin/python3 -c 'import json,sys
try:
    print(json.load(sys.stdin).get("prompt",""))
except Exception:
    pass' 2>/dev/null)

[ -z "$prompt" ] && exit 0

# Subagent reports, background-task notifications and other sessions' messages arrive as prompts too; skip them.
printf '%s' "$prompt" | head -c 300 | grep -qE '<task-notification>|<agent-message from=|<cross-session-message|\[Cross-session idle notice\]' && exit 0

# Case-insensitive match against status-check phrasings.
# Patterns deliberately err on the side of conservative — better to miss
# an edge case than fire on every prompt.
pattern='(where did we leave off'
pattern+='|where are we'
pattern+='|where were we'
pattern+='|pick up where'
pattern+='|what'\''?s the status'
pattern+='|what is the status'
pattern+='|catch me up'
pattern+='|what'\''?s next'
pattern+='|recap'
pattern+='|remind me'
pattern+='|refresh my memory'
pattern+='|jog my memory'
pattern+='|what did we do'
pattern+='|what have we'
pattern+='|bring me up to speed)'

if printf '%s' "$prompt" | grep -qiE "$pattern"; then
    cat <<'EOF'
Status-check question detected. Investigate the repository first before answering: run git log, git status, ls of recently-changed directories, and read recently-changed files. Use auto-memory only to fill gaps the repo cannot explain. Do not lead the answer from memory. State what you found in the repo before citing any memory.
EOF
fi

exit 0
