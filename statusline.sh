#!/bin/bash

# Read JSON input from stdin
input=$(cat)

# Snapshot plan usage and cache state for agents, which can't see either:
# per-session prompt_cache, plus the account-wide rate_limits (latest wins).
# Read by ~/.claude/hooks/dan-cache-cold-guard.py.
(
    snap_dir="$HOME/.claude/cache-guard"
    mkdir -p "$snap_dir/status"
    sid=$(echo "$input" | jq -r '.session_id // empty')
    [[ -n "$sid" ]] && echo "$input" | jq -c --arg t "$(date +%s)" \
        '{captured_at: ($t|tonumber), session_id, rate_limits, prompt_cache, context_window: {used_percentage: .context_window.used_percentage}}' \
        > "$snap_dir/status/$sid.json"
    echo "$input" | jq -e '.rate_limits.five_hour' >/dev/null 2>&1 && echo "$input" | jq -c --arg t "$(date +%s)" \
        '{captured_at: ($t|tonumber), rate_limits}' > "$snap_dir/usage.json"
) 2>/dev/null

# Extract data from JSON
cwd=$(echo "$input" | jq -r '.workspace.current_dir')
model=$(echo "$input" | jq -r '.model.display_name')
# Drop the trailing context-size note, e.g. "Opus 5.5 (1M context)" -> "Opus 5.5"
model="${model% (*}"

# Effective effort for this session, as resolved by Claude Code: session override
# (/effort), --effort launch pin, per-turn override, settings.json effortLevel,
# then the model default -- clamped to what the model actually supports.
# Absent from the payload when the model has no effort control, so no fallback.
effort=$(echo "$input" | jq -r '.effort.level // empty')

# Calculate directory relative to ~/Sites
sites_dir="$HOME/Sites"
if [[ "$cwd" == "$sites_dir"* ]]; then
    rel_dir="${cwd#$sites_dir/}"
    if [[ "$rel_dir" == "$cwd" ]]; then
        rel_dir="Sites"
    fi
else
    rel_dir="$cwd"
fi

# Get git information (if in a git repo)
cd "$cwd" 2>/dev/null || true

git_branch=""
git_modified=0
git_untracked=0
git_deleted=0
git_ahead=0
git_behind=0
git_upstream=""
git_no_remote=0
if git rev-parse --git-dir >/dev/null 2>&1; then
    # Get branch name
    git_branch=$(git symbolic-ref --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || echo "detached")

    # Get file counts
    git_status=$(git -c core.useBuiltinFSMonitor=false status --porcelain -uall 2>/dev/null)

    if [[ -n "$git_status" ]]; then
        git_modified=$(echo "$git_status" | grep -c '^[ MARC]M' 2>/dev/null) || git_modified=0
        git_untracked=$(echo "$git_status" | grep -c '^??' 2>/dev/null) || git_untracked=0
        git_deleted=$(echo "$git_status" | grep -c '^[ MARC]D' 2>/dev/null) || git_deleted=0
    fi

    # Commits not yet pushed. Against the upstream when there is one (behind is
    # as of the last fetch); otherwise, commits on no remote-tracking branch.
    if git_upstream=$(git rev-parse --abbrev-ref '@{u}' 2>/dev/null); then
        read -r git_ahead git_behind < <(git rev-list --left-right --count 'HEAD...@{u}' 2>/dev/null) || true
    elif [[ -n "$(git remote 2>/dev/null)" ]]; then
        git_ahead=$(git rev-list --count HEAD --not --remotes 2>/dev/null) || git_ahead=0
    else
        git_no_remote=1
    fi
fi

# Build status line
status_parts=()
status_parts+=("$rel_dir")

if [[ -n "$git_branch" ]]; then
    # Color branch based on name
    # Red (#E06C75) for main, Yellow (#E5C07B) for dev, Green (#98C379) for others
    if [[ "$git_branch" == "main" || "$git_branch" == "master" ]]; then
        colored_branch=$'\e[38;2;224;108;117m'"$git_branch"$'\e[0m'
    elif [[ "$git_branch" == "dev" || "$git_branch" == "develop" ]]; then
        colored_branch=$'\e[38;2;229;192;123m'"$git_branch"$'\e[0m'
    else
        colored_branch=$'\e[38;2;152;195;121m'"$git_branch"$'\e[0m'
    fi
    status_parts+=("$colored_branch")
    # M: yellow, U: green, D: red; plain when zero
    [[ $git_modified -gt 0 ]] && colored_M=$'\e[38;2;229;192;123m'"M:$git_modified"$'\e[0m' || colored_M="M:$git_modified"
    [[ $git_untracked -gt 0 ]] && colored_U=$'\e[38;2;152;195;121m'"U:$git_untracked"$'\e[0m' || colored_U="U:$git_untracked"
    [[ $git_deleted -gt 0 ]] && colored_D=$'\e[38;2;224;108;117m'"D:$git_deleted"$'\e[0m' || colored_D="D:$git_deleted"
    status_parts+=("$colored_M")
    status_parts+=("$colored_U")
    status_parts+=("$colored_D")
    # Unpushed commits: yellow up-arrow; "no upstream" when the branch has never been pushed
    push_state=""
    [[ ${git_ahead:-0} -gt 0 ]] && push_state+=$'\e[38;2;229;192;123m'"↑$git_ahead"$'\e[0m'
    [[ ${git_behind:-0} -gt 0 ]] && push_state+="${push_state:+ }"$'\e[38;2;97;175;239m'"↓$git_behind"$'\e[0m'
    [[ -z "$git_upstream" && ${git_ahead:-0} -gt 0 ]] && push_state+=" no upstream"
    # No remote at all: nothing can be pushed, so say so (dim) rather than show nothing
    [[ $git_no_remote -eq 1 ]] && push_state=$'\e[2m'"no remote"$'\e[0m'
    [[ -n "$push_state" ]] && status_parts+=("$push_state")
fi

if [[ -n "$effort" ]]; then
    status_parts+=("$model · $effort")
else
    status_parts+=("$model")
fi

# Plan usage (subscribers only; absent until the session's first API response).
# Percent colored green < 50, yellow < 80, red from 80; 5-hour shows its local reset time.
color_pct() {
    local pct=$1
    if (( pct >= 80 )); then printf '\e[38;2;224;108;117m%s%%\e[0m' "$pct"
    elif (( pct >= 50 )); then printf '\e[38;2;229;192;123m%s%%\e[0m' "$pct"
    else printf '\e[38;2;152;195;121m%s%%\e[0m' "$pct"
    fi
}
five_pct=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty | floor')
five_reset=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')
week_pct=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty | floor')
if [[ -n "$five_pct" ]]; then
    usage="5h $(color_pct "$five_pct")"
    # Epoch to local time: BSD date takes -r <seconds>, GNU/uutils date takes -d @<seconds>.
    [[ -n "$five_reset" ]] && usage+=" ↻$(date -r "$five_reset" +%H:%M 2>/dev/null || date -d "@$five_reset" +%H:%M)"
    [[ -n "$week_pct" ]] && usage+=" · 7d $(color_pct "$week_pct")"
    status_parts+=("$usage")
fi

# Join with pipe separators
printf '%s' "${status_parts[0]}"
for ((i=1; i<${#status_parts[@]}; i++)); do
    printf ' | %s' "${status_parts[i]}"
done
