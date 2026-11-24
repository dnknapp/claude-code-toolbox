#!/usr/bin/env python3
# Prompt-cache and plan-usage guard for large sessions. The cache lives 1h on a
# subscription; the first message after that re-caches the whole context at 2x
# input price.
#
# Modes:
#   (no args)        UserPromptSubmit hook. Blocks the first message of a cold,
#                    large session once (a resend passes), and arms the idle
#                    saver when a session first passes MIN_CONTEXT_TOKENS.
#   --stop           Stop hook. Arms the idle saver when a turn ends past
#                    MIN_CONTEXT_TOKENS and the prompt hook didn't: a session
#                    that crosses 100k inside one turn and then idles, or a
#                    prompt that reached the session through its queue (those
#                    ran no UserPromptSubmit hook, seen on the box 2026-11-03).
#   --session-start  SessionStart hook. A resumed session may have lost its
#                    cron jobs, so forget that it was armed; the re-arm checks
#                    CronList first, since a `claude respawn` keeps them.
#   --check PATH     Run by the idle saver's scheduled prompt. Prints what the
#                    model should do: OK, SAVE (handoff or session save, chosen
#                    by whether this session orchestrates subagents), or STALE.
#                    Stays OK (keeping the cache warm) while subagents or
#                    `claude --bg` sessions launched here are still working.
#                    OK repeats the questions still open for the user instead
#                    of "ok", which would sit under them as the last reply.
#   --disarm         Run by the save skills at wrap-up. The idle-save cron job
#                    otherwise shows in the quit dialog as background work.
#                    Prints the job to delete; the next real prompt re-arms.
#                    Keeps the job while background sessions are still working.
#   --usage          Plan usage and this session's cache state, for agents
#                    (which can't see either). Reads the snapshots that
#                    ~/.claude/statusline.sh writes after every response.

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

IDLE_MINUTES = 55          # cold-guard fallback threshold, a few minutes under the 1h TTL
SAVE_AFTER_MINUTES = 35    # idle saver fires every 20 min, so saves land at 35-55
STUCK_MINUTES = 120        # subagents silent this long are treated as stuck
KEEP_WARM_MINUTES = 180    # keep a session warm for its background sessions this long without the user:
                           # a cold restart (2x write) costs about as much as 3h of idle checks (0.1x reads)
ORCHESTRATOR_AGENTS = 5    # this many subagent launches marks a session as orchestrating
CLAUDE_BIN = os.path.expanduser("~/.local/bin/claude")  # the `claude` on PATH may be a wrapper (cmux) whose subcommands fail
MIN_CONTEXT_TOKENS = 100_000
TAIL_BYTES = 4_000_000
GUARD_DIR = os.path.expanduser("~/.claude/cache-guard")
CHECK_TAG = "idle-save-check"
RESUME_TAG = "handoff-resume"
HOOK = "/usr/bin/python3 ~/.claude/hooks/dan-cache-cold-guard.py"
# An idle check's reply becomes the session's last message, and a background session's job list
# shows it as the status, so it repeats the open questions of the status footer every reply ends
# with (global CLAUDE.md) instead of burying them under "ok". The Stop-hook arming turn says
# nothing instead: the reply it follows, footer and all, is still the last message.
OPEN = ("Reply with only the `Next:` and `Also open:` lines from the footer of your last reply, word for word "
        "(with no footer, the questions you last asked the user that they have not answered), "
        "or `Open: none` when nothing is open.")


def now():
    return datetime.now(timezone.utc)


def parse_ts(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def minutes_since(ts):
    return (now() - parse_ts(ts)).total_seconds() / 60


def fmt_minutes(minutes):
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h else f"{m}m"


def fmt_epoch(epoch):
    t = datetime.fromtimestamp(epoch)
    day = "" if t.date() == datetime.now().date() else t.strftime("%a ")
    return day + t.strftime("%H:%M")


def read_lines(path, tail=None):
    with open(path, "rb") as f:
        if tail:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - tail))
        return f.read().decode("utf-8", "replace").splitlines()


def entries(lines):
    for raw in lines:
        try:
            d = json.loads(raw)
        except Exception:
            continue
        if not d.get("isSidechain") and d.get("timestamp"):
            yield raw, d


def is_tagged(text):
    head = text[:500]
    return CHECK_TAG in head or RESUME_TAG in head


HANDBACK_MARKERS = ("<task-notification>", "<agent-message from=",
                    "<cross-session-message", "[Cross-session idle notice]")


def is_handback(text):
    """Subagent reports, background-task notifications and messages from other sessions also arrive as prompts; nobody resends them."""
    head = text[:300]
    return any(m in head for m in HANDBACK_MARKERS)


def arm_result(lines):
    """Outcome of this transcript's last CronCreate for the idle check: 'ok', 'denied', or None if never tried."""
    asks, result = set(), None
    for _, d in entries(lines):
        content = (d.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "tool_use" and c.get("name") == "CronCreate" \
                    and CHECK_TAG in str((c.get("input") or {}).get("prompt", "")):
                asks.add(c.get("id"))
            elif c.get("type") == "tool_result" and c.get("tool_use_id") in asks:
                text = c.get("content")
                text = text if isinstance(text, str) else json.dumps(text)
                result = "ok" if "Scheduled" in text else "denied"
    return result


def prompt_text(d):
    """The text of a user prompt entry, or None for tool results and non-user entries."""
    if d.get("type") != "user":
        return None
    content = (d.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        if any(c.get("type") == "tool_result" for c in content if isinstance(c, dict)):
            return None
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return None


def last_main_response(lines):
    ts, ctx = None, 0
    for _, d in entries(lines):
        usage = (d.get("message") or {}).get("usage") if d.get("type") == "assistant" else None
        if usage:
            ts = d["timestamp"]
            ctx = sum(usage.get(k) or 0 for k in (
                "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return ts, ctx


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def state_path(session_id):
    return os.path.join(GUARD_DIR, os.path.basename(session_id or "unknown") + ".json")


def load_state(session_id):
    return load_json(state_path(session_id))


def save_state(session_id, state):
    os.makedirs(GUARD_DIR, exist_ok=True)
    with open(state_path(session_id), "w") as f:
        json.dump(state, f)


def snapshot(session_id):
    """This session's statusline snapshot: prompt_cache and rate_limits."""
    return load_json(os.path.join(GUARD_DIR, "status", os.path.basename(session_id or "") + ".json"))


def cold_estimate(session_id, lines):
    """(is_cold, idle_minutes, recache_tokens), preferring Claude Code's own cache numbers."""
    ts, ctx = last_main_response(lines)
    if not ts:
        return False, 0, 0
    idle = minutes_since(ts)
    cache = snapshot(session_id).get("prompt_cache") or {}
    expires = cache.get("expires_at")
    recache = cache.get("recache_tokens_if_cold") or ctx
    if expires:
        return now().timestamp() >= expires - 120, idle, recache
    return idle >= IDLE_MINUTES, idle, recache


def hook():
    data = json.load(sys.stdin)
    prompt = data.get("prompt", "").lstrip()
    if prompt.startswith("/") or is_tagged(prompt):
        return
    path = data.get("transcript_path")
    sid = data.get("session_id")
    if not path or not os.path.exists(path):
        return

    lines = read_lines(path, TAIL_BYTES)
    ts, ctx = last_main_response(lines)
    if not ts or ctx < MIN_CONTEXT_TOKENS:
        return
    state = load_state(sid)
    cold, idle, recache = cold_estimate(sid, lines)

    # Cold guard: block once per idle period; the marker records which response we warned about.
    # Never block a hand-back: the report would be lost, not resent.
    if cold and state.get("warned_ts") != ts and not is_handback(prompt):
        state["warned_ts"] = ts
        save_state(sid, state)
        k = recache // 1000
        saved = state.get("saved_at")
        handoff = (f"  - A handoff was saved at {saved}: /clear and start from NEXT.md.\n" if saved
                   else "  - Done with this context? /clear and start from NEXT.md.\n")
        reason = (
            f"Cache is cold: idle {fmt_minutes(idle)}, context ~{k}k tokens. "
            f"Sending now re-caches all ~{k}k at 2x input price "
            "(one turn costing as much as dozens of warm ones).\n"
            "  - Small task (commit, save a file)? Open a fresh session, or run it yourself with `! git ...`.\n"
            + handoff +
            "  - Need this context? Resend your message; it goes through this time."
        )
        print(json.dumps({"decision": "block", "reason": reason}))
        return

    # A denied CronCreate leaves the session with no idle saver, and the denial tells the
    # model never to retry, so say so once instead of re-asking.
    if state.get("armed") and not state.get("denial_reported") and arm_result(lines) == "denied":
        state["denial_reported"] = True
        save_state(sid, state)
        print(
            "[cache-guard] Auto mode denied the idle-save job, so this session has no idle saver or "
            "keep-warm checks. After handling the user's message, tell them in one line: add "
            "\"CronCreate\" to permissions.allow in ~/.claude/settings.json to stop these denials. "
            "Don't retry the job."
        )
        return

    # Arm the idle saver once per session (stdout on UserPromptSubmit reaches the model). After a
    # save disarmed it, only the user's own next prompt re-arms: a late subagent report or session
    # message would otherwise start a second unattended save of a session the user wrapped up.
    # The session may act on that hand-back, so the saved handoff no longer covers it: drop the note
    # that names it, and the cold block falls back to its general line.
    if state.get("disarmed") and is_handback(prompt):
        if state.pop("saved_at", None):
            save_state(sid, state)
        return
    if not state.get("armed"):
        print(arm(sid, path, state, "Then handle the user's message normally."))


def arm(sid, path, state, then):
    """Mark the session armed and return the instruction that creates its idle-save job."""
    state["armed"] = True
    for key in ("saved_at", "disarmed", "disarmed_at"):
        state.pop(key, None)
    save_state(sid, state)
    check = f"{CHECK_TAG}: run `{HOOK} --check {path}` and do exactly what its output says."
    return (
        "[cache-guard] This session's context has passed 100k tokens. Before anything else, "
        f"run CronList: if a job whose prompt contains {sid} is already there, keep it and create "
        "no other. Otherwise load CronCreate (via ToolSearch if deferred) and create a recurring job "
        f'with cron "7,27,47 * * * *" and this exact prompt:\n{check}\n'
        f"{then} Don't mention the job unless asked."
    )


def last_prompts(lines):
    """(text of the last prompt that started a turn, timestamp of the user's last own prompt). The
    user's own skips checks, hand-backs, skill bodies and local commands."""
    last_text, human = None, None
    for _, d in entries(lines):
        att = d.get("attachment") or {}
        if d.get("type") == "attachment" and att.get("type") == "queued_command":
            # A prompt typed while a turn runs lands mid-turn as an attachment, not a user entry.
            p = att.get("prompt")
            if isinstance(p, list):  # a pasted image makes it a list of content blocks
                p = " ".join(c.get("text", "") for c in p if isinstance(c, dict))
            if isinstance(p, str) and (att.get("origin") or {}).get("kind") == "human" \
                    and not is_tagged(p) and not is_handback(p):
                human = d["timestamp"]
            continue
        text = prompt_text(d)
        if text is None:
            continue
        text = text.lstrip()
        # Claude Code records the idle check's cron prompt with isMeta, like a skill body. Other isMeta
        # entries can quote the tag (this hook's own Stop feedback, a peer's report), so match the start.
        if d.get("isMeta"):
            if text.startswith(CHECK_TAG) or text.startswith(RESUME_TAG):
                last_text = text
            continue
        if not text or text.startswith("<local-command") or text.startswith("<command-"):
            continue
        last_text = text
        if (d.get("origin") or {}).get("kind", "human") == "human" \
                and not is_tagged(text) and not is_handback(text):
            human = d["timestamp"]
    return last_text, human


def stop():
    """Arm at the end of a turn that the prompt hook didn't arm. It blocks the stop once, so the
    model creates the job before going idle; `armed` is saved first, so the next stop passes."""
    data = json.load(sys.stdin)
    path, sid = data.get("transcript_path"), data.get("session_id")
    if not path or not sid or not os.path.exists(path):
        return
    state = load_state(sid)
    if state.get("armed"):
        return
    lines = read_lines(path, TAIL_BYTES)
    ts, ctx = last_main_response(lines)
    if not ts or ctx < MIN_CONTEXT_TOKENS:
        return
    # Headless `claude -p` runs end when the turn does; a job would die unused.
    if '"entrypoint":"sdk-cli"' in "".join(lines[-50:]):
        return
    # A turn the idle check started may have just deleted the job (SAVE, STALE); re-arming would undo it.
    last_text, human = last_prompts(lines)
    if last_text and is_tagged(last_text):
        return
    # A save disarmed this session: the turn that ran it ends here too, and so do turns that only
    # handled a late report. Only a prompt from the user after the save re-arms.
    if state.get("disarmed"):
        since = state.get("disarmed_at")
        if not human or not since or parse_ts(human) <= parse_ts(since):
            return
    print(json.dumps({"decision": "block",
                      "reason": arm(sid, path, state, "Then stop, saying nothing more to the user.")}))


def scan(lines):
    """Walk the transcript: last real activity, last user prompt, last check prompt, subagents and
    background shells in flight, orchestration signals, and the background sessions launched here."""
    in_check, last_real, last_user, last_check = False, None, None, None
    agents = {}          # agentId -> ("running" | "done", timestamp of last event)
    shells = set()       # background Bash task ids with no completion notification yet
    sessions = set()     # names, ids and socket addresses of `claude --bg` sessions launched or messaged here
    launches, orchestrating = 0, False
    for raw, d in entries(lines):
        ts = d["timestamp"]
        text = prompt_text(d)
        if text is not None:
            in_check = CHECK_TAG in text[:500]
            if in_check:
                last_check = ts
            elif not is_handback(text):
                last_user = ts
        if not in_check:
            last_real = ts

        content = (d.get("message") or {}).get("content")
        if d.get("type") == "assistant" and isinstance(content, list):
            for c in content:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                name, inp = c.get("name"), c.get("input") or {}
                if name == "Workflow" or (name == "Skill" and inp.get("skill") in ("parallel-tracks", "dan-handoff")):
                    orchestrating = True
                if name == "SendMessage" and inp.get("to") in agents:
                    agents[inp["to"]] = ("running", ts)
                elif name == "SendMessage" and inp.get("to"):
                    sessions.add(inp["to"])
                cmd = (inp.get("command") or "") if name == "Bash" else ""
                if "--bg" in cmd:
                    sessions.update(m[1] for m in re.findall(r"""(?:-n|--name)\s+(["'])(.+?)\1""", cmd))
        sessions.update(re.findall(r"backgrounded · ([0-9a-f]{8})", raw))
        # Launches and completions can land in tool results, queued messages, or attachments,
        # so match the raw line rather than one entry type.
        for a in re.findall(r"Async agent launched successfully.{0,400}?agentId: (\w+)", raw):
            agents[a] = ("running", ts)
            launches += 1
        for a in re.findall(r"Command running in background with ID: (\w+)|moved to the background \(ID: (\w+)\)", raw):
            shells.add(a[0] or a[1])
        for a in re.findall(r"<task-id>(\w+)</task-id>", raw) + re.findall(r'agent-message from=\\?"(\w+)', raw):
            shells.discard(a)
            if a in agents:
                agents[a] = ("done", ts)

    running = {a: t for a, (s, t) in agents.items() if s == "running"}
    return (last_real, last_user, last_check, running, shells,
            orchestrating or launches >= ORCHESTRATOR_AGENTS, sessions)


def background_sessions(keys, own_sid):
    """Live `claude --bg` sessions matching `keys` (from scan), as {'id "name"': state}; state 'working' means mid-task."""
    if not keys:
        return {}
    exe = CLAUDE_BIN if os.path.exists(CLAUDE_BIN) else shutil.which("claude")
    try:
        out = subprocess.run([exe, "agents", "--json"], stdin=subprocess.DEVNULL,
                             capture_output=True, text=True, timeout=20).stdout
        listing = json.loads(out)
    except Exception:
        return {}
    found = {}
    for a in listing:
        pid = a.get("pid")
        # Entries without a pid are stale: the session is gone even if its state still says working.
        if a.get("kind") != "background" or not pid or a.get("sessionId") == own_sid:
            continue
        if not ({a.get("id"), a.get("name"), a.get("sessionId")} & keys
                or any(k.endswith(f"/{pid}.sock") for k in keys)):
            continue
        working = a.get("status") == "busy" or a.get("state") == "working"
        found[f'{a.get("id")} "{a.get("name")}"'] = "working" if working else (a.get("state") or a.get("status") or "idle")
    return found


def working_sessions(found):
    return sorted(k for k, s in found.items() if s == "working")


def moved_transcript(path):
    """EnterWorktree and ExitWorktree move a live transcript into the project directory of the new
    cwd, so the path the cron prompt was created with goes missing while its session carries on."""
    hits = glob.glob(os.path.join(os.path.dirname(os.path.dirname(path)), "*", os.path.basename(path)))
    return max(hits, key=os.path.getmtime) if hits else None


def check(path):
    sid = os.path.splitext(os.path.basename(path))[0]
    state = load_state(sid)
    # After a /clear the job fires in the new conversation, so the reply still lands under its questions.
    stale = (f"STALE: this job belongs to a previous session. CronList and CronDelete every job "
             f"whose prompt contains {sid}. Then r{OPEN[1:]}")
    if not os.path.exists(path):
        path = moved_transcript(path)
    last_check = None
    if path:
        last_real, last_user, last_check, running, shells, orchestrating, launched = scan(read_lines(path))

    # The prompt that ran this check must be in this transcript; if not, the job
    # outlived a /clear and is watching a transcript nobody is using.
    if not last_check or minutes_since(last_check) > 10:
        if state.get("armed"):
            state["armed"] = False  # the job is being deleted, so a live session re-arms on its next prompt
            save_state(sid, state)
        print(stale)
        return

    idle = minutes_since(last_real) if last_real else 0
    stuck = running and idle >= STUCK_MINUTES
    ok = f"OK: session is active. {OPEN}"
    if idle < SAVE_AFTER_MINUTES or state.get("saved_for") == last_real:
        print(ok)
        return
    if running and not stuck:
        # Subagents are still working; these checks keep the cache warm until they report.
        print(ok)
        return
    sessions = background_sessions(launched, sid)
    away = minutes_since(last_user) if last_user else idle
    if working_sessions(sessions) and away < KEEP_WARM_MINUTES:
        # Background sessions launched here are still working. Stay warm so their idle notices
        # and the user's check-ins don't each pay for a cold restart.
        print(ok)
        return

    state["saved_for"] = last_real
    state["saved_at"] = datetime.now().strftime("%H:%M")
    state["armed"] = False  # the next real prompt re-arms
    state["disarmed"] = True
    state["disarmed_at"] = now().isoformat()
    save_state(sid, state)
    tail = (f"Then CronList and CronDelete every job whose prompt contains {sid}, and stop on a short report "
            "that ends with the status footer as usual, so the open questions stay the last thing on screen.")
    notes = ""
    if shells:
        # A command that times out is moved to the background and can run until the session exits.
        notes = (f" {len(shells)} background shell command(s) never reported ({', '.join(sorted(shells))}): "
                 "read each one's output file, stop any that is hung or no longer needed with TaskStop, "
                 "and record any left running on purpose (a dev server) in the handoff.")
    if sessions:
        listed = "; ".join(f"{k}: {s}" for k, s in sorted(sessions.items()))
        notes += (f" Background sessions launched here: {listed}. Record each one's state in the handoff; "
                  "leave them running, since their idle notices still reach this session.")
    # A slot's reviews count as subagent launches, but its save is one NEXT.md bullet, not a run file.
    if orchestrating and not state.get("slot"):
        note = ""
        if stuck:
            note = (f" {len(running)} subagent(s) launched here have been silent for over "
                    f"{fmt_minutes(STUCK_MINUTES)} ({', '.join(sorted(running))}); record them as in flight.")
        print(
            f"SAVE (orchestrator run): idle {fmt_minutes(idle)}; the prompt cache goes cold within the hour."
            f"{note}{notes} The user is away, so wait on no answer: invoke the dan-handoff skill to bring this "
            f"run's handoff file up to date. {tail}"
        )
    else:
        print(
            f"SAVE: idle {fmt_minutes(idle)}; the prompt cache goes cold within the hour.{notes} "
            "The user is away, so wait on no answer: invoke the dan-save-session skill now and "
            f"record any open questions in NEXT.md as well. {tail}"
        )


def usage():
    # Local clock first: run files take their timestamps from this line.
    print(f"Now {datetime.now():%H:%M}.")
    snap = load_json(os.path.join(GUARD_DIR, "usage.json"))
    limits = snap.get("rate_limits") or {}
    if not limits:
        print("Plan usage: unknown (no statusline snapshot yet; it appears after the first response "
              "in any session on a Pro/Max plan).")
        return
    age = (now().timestamp() - snap.get("captured_at", 0)) / 60
    parts = []
    for key, label in (("five_hour", "5-hour"), ("seven_day", "weekly")):
        w = limits.get(key)
        if not w:
            continue
        resets = w.get("resets_at") or 0
        if resets and resets <= now().timestamp():
            parts.append(f"{label} window has reset since the snapshot (treat as ~0%)")
        else:
            left = fmt_minutes((resets - now().timestamp()) / 60)
            parts.append(f"{label} {w.get('used_percentage', 0):.0f}% used, resets {fmt_epoch(resets)} (in {left})")
    print(f"Plan usage (snapshot {fmt_minutes(age)} old): " + " · ".join(parts))

    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    cache = snapshot(sid).get("prompt_cache") or {}
    if cache:
        recache = (cache.get("recache_tokens_if_cold") or 0) // 1000
        warm = (f"warm until {fmt_epoch(cache['expires_at'])}" if cache.get("warm") and cache.get("expires_at")
                else "cold")
        print(f"This session's cache: {warm}; a cold restart re-caches ~{recache}k tokens.")


def disarm():
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    # The user stepping away isn't quitting: while background sessions launched here still
    # work, the job's checks are what keep this session warm for them.
    paths = glob.glob(os.path.expanduser(f"~/.claude/projects/*/{sid}.jsonl")) if sid else []
    if paths:
        launched = scan(read_lines(paths[0]))[-1]
        working = working_sessions(background_sessions(launched, sid))
        if working:
            print(f"Keep the idle-save job; delete nothing. Background sessions launched here are still "
                  f"working ({', '.join(working)}), and its checks keep this session's cache warm until they "
                  f"finish, for up to {fmt_minutes(KEEP_WARM_MINUTES)} without the user.")
            return
    if sid:
        state = load_state(sid)
        state["armed"] = False
        state["disarmed"] = True  # a hand-back after this must not re-arm
        state["disarmed_at"] = now().isoformat()
        state["saved_at"] = datetime.now().strftime("%H:%M")  # the cold block then says a handoff exists
        save_state(sid, state)
    match = sid or CHECK_TAG
    print(f"CronList and CronDelete every job whose prompt contains {match}. "
          "If the user keeps working, their next message re-arms the idle check.")


def session_start():
    data = json.load(sys.stdin)
    sid = data.get("session_id")
    state = load_state(sid)
    if state.get("armed"):
        state["armed"] = False
        save_state(sid, state)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if mode == "--check" and len(sys.argv) > 2:
            check(sys.argv[2])
        elif mode == "--usage":
            usage()
        elif mode == "--disarm":
            disarm()
        elif mode == "--session-start":
            session_start()
        elif mode == "--stop":
            stop()
        else:
            hook()
    except Exception as e:
        if mode == "--check":
            print(f"OK: guard error, skipping this check. {OPEN}")
        elif mode == "--usage":
            print(f"Plan usage: unavailable ({e}).")
        # never get between the user and their session because of a guard bug
