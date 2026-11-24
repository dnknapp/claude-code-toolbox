#!/bin/bash
# SessionStart hook: one line for Dan when this machine's Claude config is out of
# date, so a config change pushed from the other machine (Mac or devbox) doesn't
# sit undeployed. It reminds and never deploys. Lines, each printed only when true:
#
#   - origin/main has config changes merged since this machine's deploy
#   - this machine runs config that is not origin/main's: deployed from an
#     unmerged branch, with uncommitted edits, or a partial deploy (named files,
#     or one that refused a file)
#   Both give the one command that takes main's config, from any branch. The
#   repo's rule is merged = live (claude-tools CLAUDE.md, "Going live").
#   (deploy.sh records what it deployed in ~/.claude/.claude-tools-deployed)
#   - Linux only: /var/run/reboot-required exists (a restart is pending)
#
# Speed: it never waits on the network. At most once an hour it starts a detached
# `git fetch` and compares against the remote-tracking refs as of the last fetch,
# so a push shows up from the first session after the fetch that saw it. The fetch
# has a connect timeout, no prompts, and a 60s watchdog. Silent offline, when the
# repo or origin/main is missing, and on resume/clear/compact.
# Every failure path exits 0 with no output: this must never get in a session's way.

set -u

input=$(cat)
case "$input" in
    *'"source":"startup"'*|*'"source": "startup"'*) ;;
    *) exit 0 ;;
esac

REPO="$HOME/Sites/sandbox/claude-tools"
STATE_DIR="$HOME/.claude/dan-config-behind"
FETCH_EVERY=3600
lines=()

if [ "$(uname -s)" = Linux ] && [ -f /var/run/reboot-required ]; then
    lines+=("A restart is pending on this box (/var/run/reboot-required). From your Mac, when convenient: \`ssh -t devbox 'sudo reboot'\`.")
fi

if [ -d "$REPO/.git" ]; then
    # Hourly background fetch, detached from the hook's stdout so Claude Code
    # doesn't wait for it.
    now=$(date +%s)
    last=$(cat "$STATE_DIR/fetched-at" 2>/dev/null || echo 0)
    case "$last" in ''|*[!0-9]*) last=0 ;; esac
    if [ $((now - last)) -ge "$FETCH_EVERY" ] && mkdir -p "$STATE_DIR" 2>/dev/null; then
        printf '%s' "$now" > "$STATE_DIR/fetched-at" 2>/dev/null
        (
            GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=5" \
                git -C "$REPO" fetch --quiet origin &
            fetch=$!
            ( sleep 60; kill "$fetch" 2>/dev/null ) &
            watchdog=$!
            wait "$fetch"
            kill "$watchdog" 2>/dev/null
        ) </dev/null >/dev/null 2>&1 &
    fi

    # Merged = live: ~/.claude should be origin/main's config, whatever branch the
    # checkout is on. Compared by content, so a squash merge of the deployed
    # branch counts as live.
    record="$HOME/.claude/.claude-tools-deployed"
    main=$(git -C "$REPO" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)
    take="\`cd ~/Sites/sandbox/claude-tools && git switch ${main#origin/} && git pull && ./deploy.sh\`"
    deployed=$(head -n 1 "$record" 2>/dev/null || true)
    from=$(sed -n 's/^branch //p' "$record" 2>/dev/null | head -n 1)
    [ "$from" = detached ] && from=""
    extra=""
    grep -qx uncommitted "$record" 2>/dev/null && extra=" with uncommitted edits"
    grep -qx partial "$record" 2>/dev/null && extra="$extra plus a partial deploy (named files, or a deploy that refused one)"
    if [ -n "$deployed" ] && git -C "$REPO" cat-file -e "$deployed^{commit}" 2>/dev/null \
        && git -C "$REPO" cat-file -e "$main^{commit}" 2>/dev/null; then
        if [ -n "$extra" ] || ! git -C "$REPO" diff --quiet "$deployed" "$main" -- dotclaude deploy.sh 2>/dev/null; then
            if [ -z "$extra" ] && git -C "$REPO" merge-base --is-ancestor "$deployed" "$main" 2>/dev/null; then
                lines+=("$main has config changes that are not live on this machine. To take them: $take.")
            elif [ -z "$extra" ] && [ "$from" = "${main#origin/}" ] \
                && git -C "$REPO" merge-base --is-ancestor "$deployed" "refs/heads/${main#origin/}" 2>/dev/null; then
                lines+=("The live config on this machine came from commits on ${main#origin/} that are not on $main yet. Pushing them clears this: \`cd ~/Sites/sandbox/claude-tools && git switch ${main#origin/} && git pull && git push\`.")
            else
                lines+=("The live config on this machine came from ${from:-commit ${deployed:0:7}}$extra, not from $main. To take $main's config: $take.")
            fi
        fi
    fi
fi

[ ${#lines[@]} -gt 0 ] || exit 0

# JSON-escape backslashes and double quotes (a branch name from the record can
# carry them), then newlines.
msg=$(printf '%s\n' "${lines[@]}" | sed 's/\\/\\\\/g; s/"/\\"/g')
msg=${msg//$'\n'/\\n}
printf '{"systemMessage": "%s"}\n' "$msg"
exit 0
