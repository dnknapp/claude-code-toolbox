#!/usr/bin/env python3
"""slots: several issues or PRs in flight at once, each in its own folder beside the
main checkout, with its own dev server and its own background Claude Code session.

  slots                     print the table; starts nothing, tidies items whose PR has merged
  slots start 238           start an item; a stopped one gets a new session, handed where the last one left off
  slots start 238 --resume  a stopped item's old session woken with its whole conversation instead
  slots start pr 473        the same, for a PR
  slots start 563+512       two issues in one item
  slots start 238 "note"    with a direction line for the session
  slots start 238 240 126   three separate items
  slots start 238 --base B  a new issue item branched from B, another item's branch, instead of
                            the project's base; its PR targets B
  slots start               start the next queued item
  slots stop [238]          pause one item or all: dev server and session off, work kept
  slots clear 238           abandon an item: folder, branch and session go; refuses if work is unpushed.
                            A queued item that was never started just leaves the queue
  slots setup [--key value] write this machine's config for the project you are in
  slots server stop|start   an item's dev server alone (what a slot session uses on itself)

  -p NAME                   the project, when you are not inside one of its folders; part of its
                            name is enough. Outside every project, `slots` prints each one's table.

Nothing here is kept up to date by hand. ~/.claude/slots/<project>/ holds config.json,
queue.md and the dev-server logs; each item's port, server pid and session id sit in its
worktree's git dir, so they go when the folder goes. The table is derived on demand from
git, GitHub and `claude agents`. Standard library only; runs on macOS and Linux.
"""

import fcntl
import http.client
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HOME = Path(os.environ.get("SLOTS_HOME") or Path.home() / ".claude" / "slots")
GUARD_DIR = Path(os.environ.get("SLOTS_GUARD_DIR") or Path.home() / ".claude" / "cache-guard")
INSTRUCTIONS = Path(__file__).resolve().parent.parent / "slot-instructions.md"
LOCAL_SETTINGS = ".claude/settings.local.json"
STATE_FILE = "slots.json"
READY_SECONDS = 120
# Past the longest SessionEnd hook seen in a project (the dev kit's quality gate, 120 s).
_wait = os.environ.get("SLOTS_FOLDER_WAIT", "").strip()
FOLDER_WAIT = int(_wait) if _wait.isdigit() else 150
CONFIG_KEYS = ("main", "prefix", "base", "remote", "dev", "check", "install", "first_port", "address")
STOPWORDS = set("a an the and or of to in on for with is are be should at from by as it that this when".split())


class Fail(Exception):
    pass


def say(msg=""):
    print(msg, flush=True)


def find_tool(env, preferred, name):
    if os.environ.get(env):
        return os.environ[env]
    # The `claude` on PATH may be a wrapper (cmux) whose subcommands fail.
    if preferred and os.path.exists(os.path.expanduser(preferred)):
        return os.path.expanduser(preferred)
    return shutil.which(name) or name


CLAUDE = find_tool("SLOTS_CLAUDE", "~/.local/bin/claude", "claude")
GH = find_tool("SLOTS_GH", None, "gh")


def run(cmd, cwd=None, timeout=60, check=False, shell=False, env=None):
    shown = cmd if shell else " ".join(cmd)
    shown = shown if len(shown) <= 100 else shown[:100] + "…"
    try:
        p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout, shell=shell, env=env)
    except subprocess.TimeoutExpired:
        raise Fail(f"timed out after {timeout}s: {shown}")
    except FileNotFoundError:
        raise Fail(f"{cmd[0]} not found")
    if check and p.returncode:
        raise Fail(f"`{shown}` failed: {(p.stderr or p.stdout).strip()}")
    return p


def git(where, *args, check=True, timeout=60):
    return run(["git", "-C", str(where)] + list(args), check=check, timeout=timeout).stdout.rstrip("\n")


def git_ok(where, *args):
    return run(["git", "-C", str(where)] + list(args)).returncode == 0


def gh_json(proj, *args):
    p = run([GH] + list(args), cwd=proj["main"], timeout=45)
    if p.returncode:
        raise Fail((p.stderr or p.stdout).strip().splitlines()[-1] if (p.stderr or p.stdout).strip() else "gh failed")
    return json.loads(p.stdout or "null")


def read_json(path):
    try:
        with open(str(path)) as f:
            return json.load(f)
    except Exception:
        return None


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(str(tmp), "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(str(tmp), str(path))


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tail(text, n=12):
    return "\n".join("    " + line for line in text.strip().splitlines()[-n:])


# --- projects ---------------------------------------------------------------

def load_projects():
    out = {}
    if HOME.is_dir():
        for d in sorted(HOME.iterdir()):
            cfg = read_json(d / "config.json")
            if cfg:
                cfg["name"], cfg["dir"] = d.name, d
                cfg.setdefault("remote", "origin")
                out[d.name] = cfg
    return out


def main_checkout(path):
    """The main worktree of the repo `path` is in, or None outside a repo."""
    p = run(["git", "-C", str(path), "worktree", "list", "--porcelain"])
    first = p.stdout.split("\n", 1)[0]
    if p.returncode or not first.startswith("worktree "):
        return None
    return os.path.realpath(first[len("worktree "):])


def resolve_project(name, changing):
    projs = load_projects()
    if name:
        hits = [name] if name in projs else [n for n in projs if name in n]
        if len(hits) != 1:
            raise Fail(f"{'more than one project matches' if hits else 'no project matches'} {name!r}. "
                       f"Set up: {', '.join(projs) or 'none'}.")
        return projs[hits[0]]
    here = main_checkout(os.getcwd())
    for p in projs.values():
        if os.path.realpath(p["main"]) == here:
            return p
    if not projs:
        raise Fail("no project is set up on this machine. cd into a project's main checkout and run `slots setup`.")
    # One project: the table works from anywhere, and so does everything else outside a repo. Inside some
    # other repo a command that changes things is refused, because `slots start 240` there most likely
    # means that repo's #240.
    if len(projs) == 1 and not (changing and here):
        return next(iter(projs.values()))
    if here:
        raise Fail(f"this repo is not set up for slots (`slots setup` does that). To act on another project from "
                   f"here, name it: `slots -p NAME ...` ({', '.join(projs)}).")
    raise Fail(f"which project? `slots -p NAME ...` ({', '.join(projs)}).")


def base_ref(proj, base=None):
    return f"{proj['remote']}/{base or proj['base']}"


class Lock:
    """One changing command at a time per project. The table takes it without waiting, to tidy.
    With no project it is the machine-wide lock held while a port is picked and its server comes up."""

    def __init__(self, proj=None, wait=True):
        self.path, self.wait, self.f = (proj["dir"] if proj else HOME) / ("lock" if proj else "ports.lock"), wait, None

    def __enter__(self):
        self.f = open(str(self.path), "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | (0 if self.wait else fcntl.LOCK_NB))
            return True
        except OSError:
            return False

    def __exit__(self, *exc):
        self.f.close()


# --- items ------------------------------------------------------------------

def worktrees(main):
    out, cur = [], {}
    for line in git(main, "worktree", "list", "--porcelain").splitlines() + [""]:
        if not line:
            if cur:
                out.append(cur)
            cur = {}
        elif line.startswith("worktree "):
            cur["path"] = line[len("worktree "):]
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch "):].replace("refs/heads/", "", 1)
        elif line.startswith("prunable"):
            cur["prunable"] = True
    return out


def worktree_gitdir(folder):
    dotgit = Path(folder) / ".git"
    if dotgit.is_file():
        m = re.match(r"gitdir: (.+)", dotgit.read_text().strip())
        if m:
            return (Path(folder) / m.group(1)).resolve()
    return dotgit


class Item:
    def __init__(self, proj, folder, branch):
        self.proj, self.folder, self.branch = proj, Path(folder), branch or ""
        self.gitdir = worktree_gitdir(folder)
        self.state = read_json(self.gitdir / STATE_FILE) or {}

    kind = property(lambda self: self.state.get("kind", "issue"))
    numbers = property(lambda self: self.state.get("numbers", []))
    @property
    def base(self):
        base = self.state.get("base") or self.proj["base"]
        # A stacked item's base is another item's branch; once that is gone from the remote, the project's base.
        if base != self.proj["base"] and not git_ok(self.proj["main"], "show-ref", "--verify", "--quiet",
                                                    f"refs/remotes/{self.proj['remote']}/{base}"):
            return self.proj["base"]
        return base
    key = property(lambda self: f"{self.kind}-{self.numbers[0]}")
    log = property(lambda self: self.proj["dir"] / "logs" / f"{self.key}.log")
    short = property(lambda self: (self.state.get("session") or "")[:8])

    @property
    def label(self):
        return ("PR #" if self.kind == "pr" else "#") + "+".join(str(n) for n in self.numbers)

    @property
    def title(self):
        return (self.state.get("titles") or [""])[0]

    def save(self):
        write_json(self.gitdir / STATE_FILE, self.state)


def find_items(proj):
    """The worktrees this script made, known by the state file in each one's git dir. A worktree
    made any other way is never listed, stopped or deleted, whatever it is called."""
    out = []
    for wt in worktrees(proj["main"])[1:]:
        if wt.get("prunable") or not os.path.isdir(wt["path"]):
            continue
        item = Item(proj, wt["path"], wt.get("branch"))
        if item.state:
            out.append(item)
    return out


def find_item(items, number):
    for it in items:
        if number in it.numbers:
            return it
    for it in items:
        if it.state.get("pr") == number:
            return it
    return None


def item_at(items, path):
    here = os.path.realpath(path)
    for it in items:
        folder = os.path.realpath(str(it.folder))
        if here == folder or here.startswith(folder + os.sep):
            return it
    return None


def need_item(proj, items, number):
    """The item a number names: an issue it holds, or its PR. Run under the lock: it may record the PR."""
    it = find_item(items, number)
    if not it:
        try:
            head = gh_json(proj, "pr", "view", str(number), "--json", "headRefName")["headRefName"]
        except (Fail, KeyError, TypeError):
            head = None
        it = next((i for i in items if head and i.branch == head), None)
        if it and it.kind == "issue":
            it.state["pr"] = number
            it.save()
    if not it:
        raise Fail(f"no open item for #{number}. Open: {', '.join(i.label for i in items) or 'none'}.")
    return it


def numbers_in(args):
    out = []
    for a in args:
        if a.lower() == "pr":
            continue
        if not re.fullmatch(r"#?\d+", a):
            raise Fail(f"expected an item number, got {a!r}.")
        out.append(int(a.lstrip("#")))
    return out


def slugify(title):
    words = [w for w in re.sub(r"[^a-z0-9]+", " ", title.lower()).split() if w not in STOPWORDS]
    return "-".join(words[:5])[:40].strip("-") or "work"


# --- what git, GitHub and the session list say about an item -----------------

PR_FIELDS = "number,state,isDraft,url,title,headRefName,headRefOid,baseRefName,createdAt,isCrossRepository"


def pr_for(item):
    """The item's PR, or None. An issue item ignores PRs older than itself: a follow-up on the
    same issue can reuse the branch name of a PR that merged last week. Saves nothing: the table
    calls this outside the lock."""
    proj = item.proj
    known = item.numbers[0] if item.kind == "pr" else item.state.get("pr")
    if known:
        return gh_json(proj, "pr", "view", str(known), "--json", PR_FIELDS)
    if not item.branch:
        return None
    prs = gh_json(proj, "pr", "list", "--head", item.branch, "--state", "all", "--limit", "10", "--json", PR_FIELDS)
    prs = [p for p in prs or [] if p.get("createdAt", "") >= item.state.get("created", "")]
    if not prs:
        return None
    return sorted(prs, key=lambda p: (p["state"] == "OPEN", p["number"]))[-1]


def status_paths(folder):
    """Uncommitted and untracked paths, leaving out the settings file this script wrote."""
    out, entries = [], git(folder, "status", "--porcelain", "-z", "--untracked-files=all").split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        if entry[0] in "RC":
            i += 1  # the path it was renamed or copied from
        if entry[3:] != LOCAL_SETTINGS:
            out.append(entry[3:])
    return out


def git_facts(item):
    f, ref = item.folder, base_ref(item.proj, item.base)
    count = lambda *args: int(git(f, "rev-list", "--count", *args, check=False) or 0)
    dirty = status_paths(f)
    mb = git(f, "merge-base", "HEAD", ref, check=False)
    behind = count(f"HEAD..{ref}")
    files = set(dirty)
    moved = set()
    if mb:
        files |= set(git(f, "diff", "--name-only", mb, check=False).splitlines())
        if behind:
            moved = set(git(f, "diff", "--name-only", mb, ref, check=False).splitlines())
    return {
        "head": git(f, "rev-parse", "HEAD", check=False),
        "dirty": dirty,
        "unpushed": count("HEAD", "--not", f"--remotes={item.proj['remote']}"),
        "ahead": count(f"{ref}..HEAD"),
        "behind": behind,
        "files": files,
        "moved": moved & files,
    }


def inspect(item):
    info = {"pr": None, "pr_error": None}
    try:
        info["pr"] = pr_for(item)
    except Fail as e:
        info["pr_error"] = str(e)
    info.update(git_facts(item))
    return info


def sessions():
    """Sessions by short id, or None when the list can't be read. Every kind is kept, so a slot
    session is found by its id however the list files it."""
    try:
        listing = json.loads(run([CLAUDE, "agents", "--json", "--all"], timeout=30).stdout)
    except Exception:
        return None
    return {(a.get("id") or a.get("sessionId") or "")[:8]: a for a in listing if a.get("id") or a.get("sessionId")}


def session_running(item, sess):
    return bool(item.short and sess and (sess.get(item.short) or {}).get("pid"))


def session_text(item, sess):
    if not item.short:
        return "no session"
    if sess is None:
        return "?"
    a = sess.get(item.short) or {}
    # An entry whose process died mid-turn stays listed as working, with no pid.
    if not a.get("pid"):
        return "stopped"
    if a.get("status") == "busy" or a.get("state") == "working":
        return "working"
    return "failed" if a.get("state") == "failed" else "waiting on you"


# --- dev server -------------------------------------------------------------

def port_open(port):
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, port), timeout=0.4):
                return True
        except OSError:
            pass
    return False


def started_at(pid):
    """When a pid started, as `ps` prints it: tells our server from a later process with the same pid.
    Always in the C locale, or a server started in one locale reads as gone in another."""
    p = run(["ps", "-o", "lstart=", "-p", str(pid)], env=dict(os.environ, LC_ALL="C"))
    return p.stdout.strip() if p.returncode == 0 else ""


def server_alive(item):
    s = item.state.get("server") or {}
    return bool(s.get("pid")) and started_at(s["pid"]) == s.get("started") != ""


def group_alive(pgid):
    """True while any process is left in the process group."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # there, but not ours to signal
    return True


def orphaned_group(item):
    """True when the server's leader has exited but part of its group still runs in the item's folder.
    The folder is the check that the group is ours: a process group ID is not reused while its group
    lives, but it can be once it ends, and an unrelated group would not be running there."""
    pid = (item.state.get("server") or {}).get("pid")
    if not pid or not group_alive(pid):
        return False
    users = [str(p) for p, _ in folder_users(item.folder)]
    groups = run(["ps", "-o", "pgid=", "-p", ",".join(users)]).stdout.split() if users else []
    return str(pid) in groups


def stop_server(item):
    """True when a server of ours was running, or what is left of one in the item's folder. Says so
    when the port is still held afterwards, or part of the group still runs."""
    s = item.state.get("server") or {}
    if not server_alive(item) and not orphaned_group(item):
        if item.state.pop("server", None):
            item.save()
        return False
    pid, port = s["pid"], item.state.get("port") or 0
    # Gone means every process in the group has exited, not just the leader and the port: Next's
    # workers outlive both by a moment, and a tidy that looks in the folder then finds them there.
    gone = lambda: not started_at(pid) and not port_open(port) and not group_alive(pid)
    # The server runs in its own process group, so this reaches npm and what npm started, and nothing
    # else. The group outlives its leader, so a child still running gets the second signal.
    for sig, wait in ((signal.SIGTERM, 8), (signal.SIGKILL, 3)):
        try:
            os.killpg(pid, sig)
        except OSError:
            pass
        deadline = time.time() + wait
        while time.time() < deadline and not gone():
            time.sleep(0.2)
        if gone():
            break
    else:
        say(f"  warning: something is still listening on :{port} after the dev server was stopped"
            if port_open(port) else f"  warning: part of the dev server (process group {pid}) still runs")
    item.state.pop("server", None)
    item.save()
    return True


def pick_port(proj, items, item):
    """The item's own port while it is free, else the lowest free one. A stopped item keeps its
    port, because a session woken with `--resume` keeps the name it was launched with, port included."""
    mine = item.state.get("port")
    if mine and not port_open(mine):
        return mine
    taken = {it.state.get("port") for it in items if it is not item}
    # Every project on the machine shares one run of ports, so a stopped item elsewhere keeps its own too.
    for other in load_projects().values():
        if other["name"] != proj["name"]:
            try:
                taken |= {it.state.get("port") for it in find_items(other)}
            except Fail:
                pass
    port = int(proj.get("first_port") or 3001)
    while port in taken or port_open(port):
        port += 1
    return port


def address(proj, item):
    port = item.state.get("port")
    return (proj.get("address") or "http://localhost:{port}").replace("{port}", str(port)) if port else ""


def start_server(proj, items, item):
    if not proj.get("dev"):
        return
    if server_alive(item) and port_open(item.state.get("port") or 0):
        say(f"  dev server already up on :{item.state['port']}")
        return
    # Two projects starting at once must not pick the same port before either server holds it.
    with Lock():
        launch_server(proj, items, item)


def launch_server(proj, items, item):
    stop_server(item)
    port = pick_port(proj, items, item)
    if item.state.get("port") not in (None, port):
        say(f"  :{item.state['port']} is taken by something else, using :{port}")
    item.state["port"] = port
    item.log.parent.mkdir(parents=True, exist_ok=True)
    cmd = proj["dev"].replace("{port}", str(port))
    with open(str(item.log), "w") as log:
        proc = subprocess.Popen(cmd, shell=True, cwd=str(item.folder), stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True,
                                env=dict(os.environ, PORT=str(port)))
    item.state["server"] = {"pid": proc.pid, "started": started_at(proc.pid)}
    item.save()
    deadline = time.time() + READY_SECONDS
    while not port_open(port):
        if proc.poll() is not None:
            item.state.pop("server", None)
            item.save()
            raise Fail(f"the dev server exited straight away (`{cmd}`):\n{tail(item.log.read_text())}")
        if time.time() > deadline:
            raise Fail(f"the dev server did not open :{port} in {READY_SECONDS}s. Log: {item.log}")
        time.sleep(0.5)
    # Ready means it answers at all. Any status counts, so a route that redirects can't hold this up.
    try:
        conn = http.client.HTTPConnection("localhost", port, timeout=30)
        conn.request("GET", "/")
        answered = f"answers {conn.getresponse().status}"
        conn.close()
    except Exception:
        answered = "listening, first page still compiling"
    say(f"  dev server on :{port} ({answered})")


# --- sessions ---------------------------------------------------------------

def facts_block(proj, item, earlier_direction=False):
    ref = base_ref(proj, item.base)
    titles = item.state.get("titles") or []
    urls = item.state.get("urls") or []
    if item.kind == "pr":
        what = f"PR #{item.numbers[0]} \"{item.title}\", to review with Dan: {(urls or [''])[0]}"
    else:
        what = "; ".join(f"issue #{n} \"{titles[i] if i < len(titles) else ''}\": {urls[i] if i < len(urls) else ''}"
                         for i, n in enumerate(item.numbers))
    lines = [
        "## This item",
        f"- Item: {what}",
        f"- Your folder: {item.folder} (branch `{item.branch}`, base `{ref}`)",
    ]
    if item.state.get("port"):
        lines.append(f"- Where Dan looks: {address(proj, item)} (dev server log: {item.log})")
    else:
        lines.append("- This project has no dev server.")
    lines.append(f"- Check command: `{proj['check']}`" if proj.get("check") else "- No check command is configured; use what the repo's docs name.")
    memory = memory_dir(proj)
    lines.append(f"- Main checkout: {proj['main']}" + (f" (shared memory: {memory})" if memory else ""))
    if item.base != proj["base"]:
        lines.append(f"- Stacked: this branch starts from `{item.base}`, another item's unmerged branch. Open the PR "
                     f"against it (`gh pr create --base {item.base}`), so it shows only this item's commits.")
    direction = item.state.get("direction")
    if direction and earlier_direction:
        # A new session has no history to tell an old direction from a fresh one.
        lines.append(f"- Dan's direction, given at an earlier start of this item: \"{direction}\". The commits "
                     "and the last message show what was built from it; this start gave none.")
    else:
        lines.append(f"- Dan's direction: \"{direction}\"" if direction else "- Dan gave no direction line.")
    return "\n".join(lines)


def session_name(item):
    words = slugify(item.title).replace("-", " ") if item.title else item.branch
    port = f" · :{item.state['port']}" if item.state.get("port") else ""
    # Project first: with two projects open, the agents list is told apart by it, not by the port.
    return f"{item.proj['name']} {item.label} {words}{port}"


def mark_for_guard(session_id):
    """The cache guard reads this flag: a slot's idle save is a session save, not an orchestrator handoff."""
    path = GUARD_DIR / f"{session_id}.json"
    state = read_json(path) or {}
    if not state.get("slot"):
        state["slot"] = True
        write_json(path, state)


def launched_id(proc):
    m = re.search(r"backgrounded · ([0-9a-f]{8})", proc.stdout + proc.stderr)
    return m.group(1) if m else None


def record_session(item, short):
    """Wait for the new session to be listed with its process, so the table that follows shows it running.
    The session it replaces is kept in `earlier`, so `slots clear` and the cleanup after a merge remove its entry too."""
    full = None
    for _ in range(30):
        entry = (sessions() or {}).get(short) or {}
        full = entry.get("sessionId") or full
        if full and entry.get("pid"):
            break
        time.sleep(0.5)
    old = item.state.get("session")
    if old and old[:8] != short:
        item.state["earlier"] = (item.state.get("earlier") or []) + [old]
    item.state["session"] = full or short
    item.save()
    if full:
        mark_for_guard(full)


def transcript(session_id):
    """The session's transcript file, or None. Claude Code keeps it under its config dir, in a folder named after the cwd."""
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    found = sorted((config / "projects").glob(f"*/{session_id}*.jsonl"), key=lambda f: f.stat().st_mtime)
    return found[-1] if found else None


def last_reply(path, limit=4000):
    """The text of the session's last message to Dan. A slot ends every reply on its status, so this is
    where it left off. Long replies keep their end, where the status is."""
    text = None
    try:
        with open(str(path), errors="replace") as f:
            for line in f:
                if '"assistant"' not in line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if (not isinstance(entry, dict) or entry.get("type") != "assistant" or entry.get("isSidechain")
                        or entry.get("isApiErrorMessage")):
                    continue
                content = (entry.get("message") or {}).get("content") if isinstance(entry.get("message"), dict) else None
                blocks = [b.get("text") or "" for b in content if isinstance(b, dict) and b.get("type") == "text"
                          and isinstance(b.get("text") or "", str)] if isinstance(content, list) else []
                if any(b.strip() for b in blocks):
                    text = "\n".join(b for b in blocks if b.strip()).strip()
    except OSError:
        return None
    if text and len(text) > limit:
        text = "[…]\n" + text[-limit:]
    return text


def ensure_session(proj, item, direction, sess, resume=False):
    if session_running(item, sess):
        say(f"  session already running: claude attach {item.short}")
        if direction:
            say("  The direction line was not sent to the running session. Send it from a Claude session "
                "with SendMessage, or attach and type it.")
        return
    if sess is None and item.short:
        raise Fail("`claude agents` could not be read, so it is unknown whether this item's session is running. "
                   "No session was started; try again.")
    sid = item.state.get("session")
    facts = facts_block(proj, item, earlier_direction=bool(sid) and not direction)
    if resume and not (sid and len(sid) > 8):
        say("  --resume: this item has no earlier session to resume, starting a new one")
    if resume and sid and len(sid) > 8:
        message = ("`slots start` resumed this item after a stop.\n\n" + facts + "\n\nRun `slots`, then tell Dan in two "
                   "or three lines where the item stands, end on the status the slot instructions give, and wait for him.")
        # No flags: with any, `--resume --bg` starts a copy under a new id and leaves this one behind.
        p = run([CLAUDE, "--resume", sid, "--bg", message], cwd=item.folder, timeout=120)
        short = launched_id(p)
        if p.returncode == 0 and short:
            if short != item.short:
                record_session(item, short)
            say(f"  session resumed: claude attach {short}")
            return
        say("  the old session could not be resumed, starting a new one")
    if not INSTRUCTIONS.exists():
        raise Fail(f"the slot instructions are missing: {INSTRUCTIONS}")
    parts = ["You are a slot: one background session working one item with Dan, live, in its own folder.", facts]
    ahead = git(item.folder, "rev-list", "--count", f"{base_ref(proj, item.base)}..HEAD", check=False)
    if item.kind == "issue" and int(ahead or 0):
        parts.append("This branch already has commits. Read them and the branch's PR before the opener, "
                     "and open with where the item stands.")
    earlier = transcript(sid) if sid else None
    reply = last_reply(earlier) if earlier else None
    if reply:
        parts.append("An earlier session worked this item and was stopped. This is its last message to Dan, "
                     "where it left off:\n\n<last-message>\n" + reply + "\n</last-message>\n\n"
                     "Open with where the item stands, and carry into the opener those of its `Next:` and "
                     "`Also open:` questions that are still open questions, as \"Each note\" defines them. "
                     "If it does not end on the status, it was stopped mid-turn: compare its last words with "
                     "the branch and the uncommitted files in the table. Its whole conversation is in "
                     f"{earlier}, one JSON object per line. Search it for a specific thing the message, "
                     "the commits and the PR don't settle, such as the wording of an earlier note of Dan's, "
                     "and never read it whole.")
    bullet = saved_bullet(proj, item)
    if bullet:
        parts.append("An earlier session of this item saved this line under `## Slots` in NEXT.md:\n\n"
                     f"{bullet}\n\n" + ("It may be older than the last message above, which wins where they differ. "
                                         if reply else "")
                     + "Carry into the opener those of its `Next:` and `Also open:` questions that "
                     "are still open questions, as \"Each note\" defines them: the branch's commits, the PR, "
                     "a direction line above or a recorded decision may have settled some since. "
                     "Your first save replaces the line.")
    parts.append(INSTRUCTIONS.read_text().strip())
    parts.append(f"These instructions are at {INSTRUCTIONS}. Re-read them if they have left your context; "
                 "`slots` run in your folder prints the facts above again.")
    p = run([CLAUDE, "--bg", "-n", session_name(item), "\n\n".join(parts)], cwd=item.folder, timeout=120)
    short = launched_id(p)
    if p.returncode or not short:
        out = (p.stdout + p.stderr).strip()
        hint = ("\n  Open `claude` once in the main checkout and accept the trust prompt, then start the item again."
                if "not trusted" in out else "")
        raise Fail(f"the session did not start:\n{tail(out)}{hint}")
    record_session(item, short)
    say(f"  session started: claude attach {short}")


def stop_session(item, sess):
    """True when a session was told to stop. With the list unreadable it is told anyway."""
    if not item.short or (sess is not None and not session_running(item, sess)):
        return False
    return run([CLAUDE, "stop", item.short], timeout=30).returncode == 0


# --- starting ---------------------------------------------------------------

def memory_dir(proj):
    """The main checkout's memory directory when its local settings name one."""
    main = Path(proj["main"])
    value = (read_json(main / LOCAL_SETTINGS) or {}).get("autoMemoryDirectory")
    return str((main / os.path.expanduser(value)).resolve()) if value else None


def saved_bullet(proj, item):
    """The item's bullet under `## Slots` in the project's NEXT.md, or None. A bullet starts
    `- #238 title · PR #601 …` (or `- PR #601 …` for a PR item): the first field names the item,
    and the second names its PR only when it starts `PR #`. Before a PR it is where the item
    stands, and any number there or later in the line is another item.
    A bullet whose PR is not this item's own is skipped: it is left from an earlier item on the
    same issue whose PR merged, and stays until no item on that issue is open, when `slots` or the
    main checkout's save drops it."""
    folder = memory_dir(proj)
    try:
        text = (Path(folder) / "NEXT.md").read_text() if folder else ""
    except OSError:
        return None
    ours, own_pr = set(item.numbers), False
    section = False
    for line in text.splitlines():
        if line.startswith("## "):
            section = line.strip() == "## Slots"
            continue
        if not (section and line.startswith("- ")):
            continue
        names = bullet_names(line)
        if not names:
            continue
        named, pr = names
        if not (named | {pr}) & (ours | {item.state.get("pr")}) - {None}:
            continue
        if pr is not None:
            if own_pr is False:
                try:
                    own_pr = (pr_for(item) or {}).get("number")
                except Fail:
                    own_pr = None
            if pr != own_pr:
                continue
        return line.strip()
    return None


def bullet_names(line):
    """The numbers a `## Slots` bullet's first field names, and its PR (None when it names none),
    read as `saved_bullet` describes; None when the first field names no item."""
    fields = line[2:].split(" · ")
    head = re.match(r"(PR )?#(\d+(?:\+\d+)*)\b", fields[0].strip().lstrip("*"))
    if not head:
        return None
    named = [int(n) for n in head.group(2).split("+")]
    second = re.match(r"PR #(\d+)\b", fields[1].strip().lstrip("*")) if len(fields) > 1 else None
    return set(named), int(second.group(1)) if second else (named[0] if head.group(1) else None)


SECTION_END = re.compile(r"#{1,2} ")  # a heading of a `## ` section's level or above ends it


def without_finished_bullets(text, open_numbers, merged):
    """`text` with each `## Slots` bullet that names none of `open_numbers` removed, with its wrapped
    lines, and with the heading once nothing is left under it. A bullet that names no item stays.
    A removed bullet whose item is in `merged` ((numbers, PR number) pairs) becomes a line under
    `## Where we left off`, added if missing. Returns the new text and the removed bullets' first fields."""
    nl = "\r\n" if "\r\n" in text else "\n"
    kept, dropped, landed, heading, section, dropping = [], [], [], None, False, False
    for line in text.splitlines(keepends=True):
        if SECTION_END.match(line):
            section, dropping = line.strip() == "## Slots", False
            heading = len(kept) if section and heading is None else heading
        elif section and line.startswith("- "):
            names = bullet_names(line)
            dropping = bool(names) and not (names[0] | ({names[1]} if names[1] else set())) & open_numbers
            if dropping:
                first = line[2:].split(" · ")[0].strip().strip("*").strip()
                dropped.append(first)
                pr = next((pr for numbers, pr in merged if numbers & names[0] or pr == names[1]), None)
                if pr:
                    landed.append(f"- {first}: PR #{pr} merged {datetime.now().strftime('%Y-%m-%d')}{nl}")
                continue
        elif dropping and line[:1] in (" ", "\t") and line.strip():
            continue  # a dropped bullet's wrapped continuation
        else:
            dropping = False
        kept.append(line)
    if not dropped:
        return text, []
    end = next((i for i in range(heading + 1, len(kept)) if SECTION_END.match(kept[i])), len(kept))
    if not any(l.strip() for l in kept[heading + 1:end]):
        del kept[heading:end]
        while heading and not kept[heading - 1].strip() and (heading == len(kept) or not kept[heading].strip()):
            del kept[heading - 1]
            heading -= 1
    if landed:
        if kept and not kept[-1].endswith("\n"):
            kept[-1] += nl
        at = next((i for i, l in enumerate(kept) if l.strip() == "## Where we left off"), None)
        if at is None:
            at = next((i for i, l in enumerate(kept) if l.startswith("## ")), len(kept))
            block = [f"## Where we left off{nl}", nl] + landed + [nl]
            if at and kept[at - 1].strip():
                block.insert(0, nl)
            kept[at:at] = block if at < len(kept) else block[:-1]
        else:
            end = next((i for i in range(at + 1, len(kept)) if SECTION_END.match(kept[i])), len(kept))
            while end > at + 1 and not kept[end - 1].strip():
                end -= 1
            kept[end:end] = ([nl] if end == at + 1 else []) + landed
    return "".join(kept), dropped


def drop_finished_bullets(proj, open_numbers, merged=()):
    """Take finished bullets out of the project's NEXT.md (see `without_finished_bullets`): a slot's
    save puts its follow-ups under `## Next up`, so nothing goes with the bullet. Live sessions edit the
    file too, so it is replaced only if it still reads as it did, and the pass starts over if not.
    Returns the first field of each bullet dropped."""
    folder = memory_dir(proj)
    if not folder:
        return []
    path = Path(folder) / "NEXT.md"
    tmp = path.with_name(path.name + ".slots-tmp")
    for _ in range(3):
        try:
            with open(path, newline="") as f:  # keep the file's own line endings
                text = f.read()
            new, dropped = without_finished_bullets(text, open_numbers, merged)
            if not dropped:
                return []
            with open(tmp, "w", newline="") as f:
                f.write(new)
            with open(path, newline="") as f:
                if f.read() == text:
                    os.replace(str(tmp), str(path))
                    return dropped
            tmp.unlink()
        except OSError:
            break
    try:
        tmp.unlink()
    except OSError:
        pass
    return []


def write_local_settings(proj, item):
    """A linked worktree does not see the main checkout's local settings, so copy them, with the
    memory directory made absolute: a slot reads and writes the project's memory, not its own."""
    source = read_json(Path(proj["main"]) / LOCAL_SETTINGS)
    target = item.folder / LOCAL_SETTINGS
    if source is None or target.exists():
        return
    if memory_dir(proj):
        source["autoMemoryDirectory"] = memory_dir(proj)
    write_json(target, source)


def install(proj, item):
    cmd = proj.get("install")
    if not cmd or item.state.get("installed"):
        return
    say(f"  installing dependencies ({cmd})")
    p = run(cmd, cwd=item.folder, timeout=1200, shell=True)
    if p.returncode:
        raise Fail(f"`{cmd}` failed:\n{tail(p.stdout + p.stderr)}")
    item.state["installed"] = True
    item.save()


def branch_exists(proj, name):
    main = proj["main"]
    return (git_ok(main, "show-ref", "--verify", "--quiet", f"refs/heads/{name}")
            or git_ok(main, "show-ref", "--verify", "--quiet", f"refs/remotes/{proj['remote']}/{name}"))


def pick_issue_branch(proj, number, slug):
    """(branch, pr number or None, adopt). Adopts a branch already on the remote for this issue when
    its work is unmerged: an item cleared and started again, or begun on another machine."""
    main, remote = proj["main"], proj["remote"]
    found = []
    refs = git(main, "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}/issue-{number}-*")
    for ref in refs.splitlines():
        name = ref.split("/", 1)[1]
        prs = gh_json(proj, "pr", "list", "--head", name, "--state", "all", "--limit", "10", "--json", "number,state")
        open_prs = [p["number"] for p in prs or [] if p["state"] == "OPEN"]
        unmerged = int(git(main, "rev-list", "--count", f"{base_ref(proj)}..{ref}", check=False) or 0)
        if open_prs or (unmerged and not prs):
            found.append((name, open_prs[0] if open_prs else None))
    if len(found) > 1:
        raise Fail(f"#{number} has more than one unmerged branch on {remote}: {', '.join(n for n, _ in found)}. "
                   "Start the one you mean by its PR (`slots start pr N`), or delete the others.")
    if found:
        return found[0][0], found[0][1], True
    name, n = f"issue-{number}-{slug}", 1
    while branch_exists(proj, name):
        n += 1
        name = f"issue-{number}-{slug}-{n}"
    return name, None, False


def new_folder(proj, name):
    folder = Path(proj["main"]).parent / f"{proj['prefix']}-{name}"
    if folder.exists():
        raise Fail(f"{folder} is in the way: it exists and is not one of this project's items.")
    return folder


def create_issue_item(proj, numbers, infos, base=None):
    main, remote = proj["main"], proj["remote"]
    if base and not git_ok(main, "show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{base}"):
        raise Fail(f"--base {base}: there is no such branch on {remote}. Push it first.")
    branch, pr, adopt = pick_issue_branch(proj, numbers[0], slugify(infos[0]["title"]))
    folder = new_folder(proj, branch)
    if adopt and git_ok(main, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"):
        git(main, "worktree", "add", str(folder), branch)
    elif adopt:
        git(main, "worktree", "add", "--track", "-b", branch, str(folder), f"{remote}/{branch}")
    else:
        git(main, "worktree", "add", "--no-track", "-b", branch, str(folder), base_ref(proj, base))
    say(f"  {folder.name}" + (f" (branch {branch} was already on {remote}, carrying on from it)" if adopt else "")
        + (f" (from {base})" if base and not adopt else ""))
    item = Item(proj, folder, branch)
    item.state = {"kind": "issue", "numbers": numbers, "base": base or proj["base"], "created": "" if adopt else utc_now(),
                  "titles": [i["title"] for i in infos], "urls": [i["url"] for i in infos]}
    if pr:
        item.state["pr"] = pr
    item.save()
    return item


def create_pr_item(proj, number, items):
    main = proj["main"]
    pr = gh_json(proj, "pr", "view", str(number), "--json", PR_FIELDS)
    if pr["state"] != "OPEN":
        raise Fail(f"PR #{number} is {pr['state'].lower()}; there is nothing to start.")
    for it in items:
        if it.branch == pr["headRefName"]:
            it.state["pr"] = number
            it.save()
            return it, False
    folder = new_folder(proj, "pr-%d-%s" % (number, re.sub(r"[^A-Za-z0-9._-]+", "-", pr["headRefName"])))
    git(main, "fetch", "--quiet", proj["remote"], pr["baseRefName"], check=False)
    git(main, "worktree", "add", "--detach", str(folder), base_ref(proj, pr["baseRefName"]))
    try:
        run([GH, "pr", "checkout", str(number)], cwd=folder, timeout=120, check=True)
    except Fail as e:
        # Without its state file the folder is not an item, so nothing later would clean it up.
        git(main, "worktree", "remove", "--force", str(folder), check=False)
        raise Fail(f"could not check out PR #{number}: {e}")
    say(f"  {folder.name}")
    item = Item(proj, folder, git(folder, "branch", "--show-current"))
    item.state = {"kind": "pr", "numbers": [number], "base": pr["baseRefName"], "created": utc_now(),
                  "titles": [pr["title"]], "urls": [pr["url"]]}
    item.save()
    return item, True


def parse_specs(args):
    """`238`, `563+512`, `pr 473`, each optionally followed by a direction line in quotes."""
    specs, i, loose = [], 0, False
    while i < len(args):
        a = args[i]
        number = re.fullmatch(r"#?\d+(\+#?\d+)*", a)
        if (number or a.lower() == "pr") and loose:
            # `238 keep them at 24 px`: is 24 an issue? Quoted, the direction is one word of the command line.
            raise Fail(f"{a!r} follows a direction that is not in quotes, so it could be part of it or another item. "
                       "Put the direction in quotes: `slots start 238 \"keep them at 24 px\" 240`.")
        if a.lower() == "pr" and i + 1 < len(args) and re.fullmatch(r"#?\d+", args[i + 1]):
            specs.append({"kind": "pr", "numbers": [int(args[i + 1].lstrip("#"))], "direction": ""})
            i += 1
        elif number:
            specs.append({"kind": "issue", "numbers": [int(n.lstrip("#")) for n in a.split("+")], "direction": ""})
        elif specs:
            loose = loose or bool(specs[-1]["direction"]) or " " not in a.strip()
            specs[-1]["direction"] = (specs[-1]["direction"] + " " + a).strip()
        else:
            raise Fail(f"expected an issue number or `pr <number>` first, got {a!r}.")
        i += 1
    return specs


def start_one(proj, spec, items, queue, sess, base=None, resume=False):
    kind, numbers, direction = spec["kind"], spec["numbers"], spec["direction"]
    # A queued item keeps the grouping and direction it was planned with, however it is started.
    # Issues and PRs share one run of numbers, so the number alone finds the queued item.
    queued = spec if "line" in spec else next((q for q in queue["entries"] if set(numbers) & set(q["numbers"])), None)
    if queued and queued is not spec:
        numbers, direction = queued["numbers"], direction or queued["direction"]
        kind = "pr" if "pr" in (kind, queued["kind"]) else "issue"
    if queued:
        say(f"  from the queue: {'+'.join(map(str, numbers))}" + (f" ({direction})" if direction else ""))

    item = next((it for n in numbers for it in [find_item(items, n)] if it), None)
    if item and len(numbers) > 1 and set(numbers) != set(item.numbers):
        say(f"  {item.label} is already open, so it is started as it is; a grouping is fixed when an item is made")
    created = False
    if base and (item or kind == "pr"):
        say(f"  --base ignored: {'an open item keeps the base it was made with' if item else 'a PR item takes its PR base'}")
    if not item:
        infos = [] if kind == "pr" else [
            gh_json(proj, "issue", "view", str(n), "--json", "number,title,url,state") for n in numbers]
        if infos and len(numbers) == 1 and "/pull/" in infos[0]["url"]:
            kind = "pr"
            say(f"  #{numbers[0]} is a PR, starting it as one")
        if kind == "pr":
            item, created = create_pr_item(proj, numbers[0], items)
        else:
            for info in infos:
                if "/pull/" in info["url"]:
                    raise Fail(f"#{info['number']} is a PR. A PR is its own item: `slots start pr {info['number']}`.")
                if info["state"] != "OPEN":
                    say(f"  note: issue #{info['number']} is {info['state'].lower()}")
            item, created = create_issue_item(proj, numbers, infos, base), True
        if created:
            items.append(item)
    if direction:
        item.state["direction"] = direction
        item.save()
    write_local_settings(proj, item)
    install(proj, item)
    start_server(proj, items, item)
    ensure_session(proj, item, direction, sess, resume)
    if queued:
        remove_from_queue(proj, queued)
    return item


def cmd_start(proj, args):
    base = None
    if "--base" in args:
        i = args.index("--base")
        if i + 1 >= len(args):
            raise Fail("--base needs a branch name: `slots start 238 --base issue-200-first-part`.")
        base, args = args[i + 1], args[:i] + args[i + 2:]
    resume = "--resume" in args
    args = [a for a in args if a != "--resume"]
    specs = parse_specs(args)
    failed = False
    with Lock(proj):
        queue = read_queue(proj)
        if not specs:
            if not queue["entries"]:
                raise Fail("nothing is queued. `slots start 238` starts an issue, `slots start pr 473` a PR.")
            specs = [queue["entries"][0]]
        say(f"fetching {proj['remote']}")
        git(proj["main"], "fetch", "--quiet", "--prune", proj["remote"], check=False, timeout=90)
        items, sess = find_items(proj), sessions()
        for spec in specs:
            say(("PR #" if spec["kind"] == "pr" else "#") + "+".join(map(str, spec["numbers"])))
            try:
                start_one(proj, spec, items, read_queue(proj), sess, base, resume)
            except Fail as e:
                failed = True
                say(f"  FAILED: {e}")
    say()
    cmd_table(proj, tidy=False, fetch=False)
    return 1 if failed else 0


# --- the queue --------------------------------------------------------------

def read_queue(proj):
    """queue.md: one list line per item, `- 238`, `- 563+512 — direction`, `- pr 473: direction`."""
    path = proj["dir"] / "queue.md"
    entries, bad = [], []
    lines = path.read_text().splitlines() if path.exists() else []
    for i, line in enumerate(lines):
        m = re.match(r"\s*[-*]\s+(?:\[.\]\s*)?(.*\S)\s*$", line)
        if not m:
            continue
        sm = re.match(r"(?i)(pr\s+)?(#?\d+(?:\s*\+\s*#?\d+)*)\s*(?:(?:—|–|--|-|:)\s*(.*))?$", m.group(1))
        if not sm:
            bad.append(i + 1)
            continue
        entries.append({"kind": "pr" if sm.group(1) else "issue", "direction": (sm.group(3) or "").strip(),
                        "numbers": [int(n) for n in re.findall(r"\d+", sm.group(2))], "line": i})
    return {"path": path, "entries": entries, "bad": bad}


def queued_entry(queue, number):
    """The queue line holding a number; issues and PRs share one run of numbers."""
    return next((q for q in queue["entries"] if number in q["numbers"]), None)


def queue_label(entry):
    return ("PR #" if entry["kind"] == "pr" else "#") + "+".join(map(str, entry["numbers"]))


def remove_from_queue(proj, entry):
    queue = read_queue(proj)
    match = next((q for q in queue["entries"] if (q["kind"], q["numbers"]) == (entry["kind"], entry["numbers"])), None)
    if match:
        lines = queue["path"].read_text().splitlines()
        del lines[match["line"]]
        queue["path"].write_text("\n".join(lines) + "\n")


# --- stopping, clearing, tidying --------------------------------------------

def pause(item, sess):
    server, session = stop_server(item), stop_session(item, sess)
    done = [w for w, did in (("dev server", server), ("session", session)) if did]
    say(f"{item.label}: {' and '.join(done) + ' stopped' if done else 'already stopped'}. "
        f"Work kept in {item.folder.name}; `slots start {item.numbers[0]}` picks it up in a new session.")
    if sess is None and item.short:
        say(f"  The session list could not be read, so check it yourself: claude attach {item.short}")


def cmd_stop(proj, args):
    with Lock(proj):
        items, sess = find_items(proj), sessions()
        chosen = [need_item(proj, items, n) for n in numbers_in(args)] if args else items
        if not chosen:
            say("No open items.")
        for it in chosen:
            pause(it, sess)
    return 0


class PartlyRemoved(Fail):
    """The folder delete started and did not finish: unlike a plain Fail, something was deleted."""


def ancestors():
    """This process and the ones that started it: the shell `slots` was run from may sit in the folder."""
    pids, pid = set(), os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        p = run(["ps", "-o", "ppid=", "-p", str(pid)])
        pid = int(p.stdout.strip()) if p.stdout.strip().isdigit() else 0
    return pids


def folder_users(folder, mine=frozenset()):
    """(pid, command) for every process whose working directory is in `folder`, except `mine`."""
    folder, out = os.path.realpath(str(folder)), []
    inside = lambda p: p == folder or p.startswith(folder + os.sep)
    if os.path.isdir("/proc/self"):
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                cwd = os.readlink(f"/proc/{pid}/cwd")
                cmd = Path(f"/proc/{pid}/comm").read_text().strip()
                # VS Code's language servers run its own node, and their comm is only "MainThread".
                # argv[0] alone: a VS Code terminal's shell has a .vscode-server script among its args.
                argv0 = Path(f"/proc/{pid}/cmdline").read_text(errors="replace").split("\0", 1)[0]
                if "/.vscode-server/" in argv0:
                    cmd = VSCODE
            except OSError:
                continue  # gone, or not ours to read
            if inside(cwd) and int(pid) not in mine:
                out.append((int(pid), cmd))
        return out
    pid = cmd = None
    # Run from /, or lsof itself would be in the folder.
    for line in run(["lsof", "-w", "-n", "-P", "-d", "cwd", "-F", "pcn"], cwd="/", timeout=30).stdout.splitlines():
        tag, val = line[:1], line[1:]
        if tag == "p":
            pid, cmd = int(val), "?"
        elif tag == "c":
            cmd = val
        elif tag == "n" and inside(val) and pid not in mine:
            out.append((pid, cmd))
    return out


VSCODE = "VS Code"


class InUse(Fail):
    """Something still runs in the folder; nothing was deleted."""


def wait_for_folder(item, deadline=None):
    """Wait until nothing runs in the item's folder, until `deadline` (default FOLDER_WAIT from now).
    A stopped session's SessionEnd hooks keep running after `claude stop` returns, and a `tsc` among
    them writes its build info as the folder goes."""
    start, mine = time.time(), ancestors()
    deadline = start + FOLDER_WAIT if deadline is None else deadline
    users = folder_users(item.folder, mine)
    if users and deadline > start:
        say(f"  {item.label}: waiting for what still runs in {item.folder.name}: "
            + ", ".join(sorted({c for _, c in users})))
    while users and time.time() < deadline:
        time.sleep(0.5)
        users = folder_users(item.folder, mine)
    if users:
        waited = f" after {round(time.time() - start)}s" if deadline > start else ""
        by = {}
        for p, c in users:
            by.setdefault(c, []).append(str(p))
        names = ", ".join(f"{c} (pid{'s' if len(ps) > 1 else ''} {', '.join(ps[:4])}"
                          f"{f' and {len(ps) - 4} more' if len(ps) > 4 else ''})" for c, ps in by.items())
        hint = (f"; a {VSCODE} window has this folder open: close it, or open another folder in it"
                if VSCODE in by else "")
        raise InUse(f"still in use{waited} by {names}{hint}")


def remove_item(proj, item, sess, lost, deadline=None):
    """Dev server, session and its list entry, folder, branch. `lost()` names what deleting would lose,
    or None. It is asked here, once everything is stopped, because a session can still write or commit
    while it is being stopped; the caller asks it first too, to refuse before stopping anything."""
    if sess is None and item.short:
        raise Fail("`claude agents` could not be read, so its session can't be confirmed stopped")
    stop_server(item)
    stop_session(item, sess)
    wait_for_folder(item, deadline)
    blocker = lost()
    if blocker:
        raise Fail(f"{blocker} appeared while it was being stopped")
    for sid in (item.state.get("earlier") or []) + [item.state.get("session") or ""]:
        if sid and sess.get(sid[:8]):
            run([CLAUDE, "rm", sid[:8]], timeout=30)
        if len(sid) > 8:
            try:
                (GUARD_DIR / f"{sid}.json").unlink()
            except OSError:
                pass
    log, branch, base = item.log, item.branch, item.base
    try:
        git(proj["main"], "worktree", "remove", "--force", str(item.folder))
    except Fail as e:
        if item.folder.exists() and not item.gitdir.exists():
            # Git deleted part of the folder and then forgot the worktree, so it is no longer an item.
            # What was in it was checked above, so the branch and log go as they would have.
            removed = "branch and log removed" if finish(proj, branch, base, log) else "log removed"
            left = sorted(str(p.relative_to(item.folder)) for p in item.folder.rglob("*") if not p.is_dir())
            raise PartlyRemoved(f"the folder was only partly deleted ({str(e).splitlines()[-1]}). It is no longer "
                                f"a slot; session, {removed}. Left in {item.folder}: "
                                f"{f'{len(left)} file(s), ' + some(left) if left else 'empty folders'}. "
                                "Look, then delete the folder yourself")
        raise
    finish(proj, branch, base, log)


def finish(proj, branch, base, log):
    """The branch and log of an item whose folder git has let go of. True when the branch went."""
    gone = False
    if branch and branch not in (proj["base"], base):
        gone = git_ok(proj["main"], "branch", "-D", branch)
    if log.exists():
        log.unlink()
    return gone


def tidy_blocker(item, pr):
    """What deleting a merged item's folder would lose, or None. Reads the folder afresh."""
    dirty = status_paths(item.folder)
    if dirty:
        return f"{len(dirty)} uncommitted file(s)"
    head, pr_head = git(item.folder, "rev-parse", "HEAD", check=False), pr.get("headRefOid") or ""
    if head == pr_head or git_ok(item.folder, "merge-base", "--is-ancestor", head, base_ref(item.proj, item.base)):
        return None
    if pr_head and git_ok(item.folder, "merge-base", "--is-ancestor", head, pr_head):
        return None
    return "commits made after the PR merged"


def clear_blocker(item):
    """What abandoning an item would lose, or None. Reads the folder afresh; trustworthy only after
    a fetch that pruned, since "pushed" means reachable from a branch the remote still has."""
    dirty = status_paths(item.folder)
    unpushed = int(git(item.folder, "rev-list", "--count", "HEAD", "--not", f"--remotes={item.proj['remote']}",
                       check=False) or 0)
    what = [f"{len(dirty)} uncommitted file(s)"] if dirty else []
    what += [f"{unpushed} commit(s) not pushed"] if unpushed else []
    return " and ".join(what) or None


def cmd_clear(proj, args):
    numbers = numbers_in(args)
    if not numbers:
        raise Fail("which item? `slots clear 238`.")
    status = 0
    with Lock(proj):
        # A number no started item holds but a queue line does is only waiting: its line goes, and
        # nothing else exists to remove, so this needs no fetch. A started item is cleared as before.
        # Every line holding the number goes, so a number queued twice is not left half-cleared.
        # A started item wins, found the way the clear below finds it: by its numbers or its PR's branch.
        items, rest, unqueued = find_items(proj), [], set()
        for n in numbers:
            if n in unqueued:
                continue
            try:
                need_item(proj, items, n)
                started = True
            except Fail:
                started = False
            entry = None if started else queued_entry(read_queue(proj), n)
            if not entry:
                rest.append(n)
            while entry:
                remove_from_queue(proj, entry)
                unqueued |= set(entry["numbers"])
                say(f"{queue_label(entry)}: unqueued. Its line is gone from {proj['dir'] / 'queue.md'}.")
                entry = queued_entry(read_queue(proj), n)
        if not rest:
            return status
        try:
            git(proj["main"], "fetch", "--quiet", "--prune", proj["remote"], timeout=90)
        except Fail:
            raise Fail(f"could not fetch {proj['remote']}, so there is no telling what is pushed. "
                       + ("Nothing else was cleared." if unqueued else "Nothing was cleared."))
        sess = sessions()
        for n in rest:
            item = need_item(proj, items, n)
            try:
                pr = pr_for(item)
            except Fail:
                pr = None
            on_remote = git_ok(proj["main"], "show-ref", "--verify", "--quiet",
                               f"refs/remotes/{proj['remote']}/{item.branch}")
            lost = lambda item=item: clear_blocker(item)
            blocker = lost()
            if not blocker:
                try:
                    remove_item(proj, item, sess, lost)
                except PartlyRemoved as e:
                    status = 1
                    say(f"{item.label}: not fully cleared: {e}.")
                    continue
                except Fail as e:
                    status = 1
                    say(f"{item.label}: not cleared: {e}. Nothing was deleted; `slots clear {n}` tries again.")
                    continue
            else:
                status = 1
                say(f"{item.label}: not cleared. {blocker} in {item.folder}. Push it, or discard it there yourself, "
                    "then clear again.")
                continue
            items.remove(item)
            left = ""
            if pr and pr["state"] == "OPEN":
                left = f" PR #{pr['number']} is still open on GitHub."
            elif on_remote:
                left = f" Branch {item.branch} is still on {proj['remote']}."
            say(f"{item.label}: cleared. Session, folder and local branch removed.{left}")
    return status


# --- the table --------------------------------------------------------------

def work_text(info):
    parts = [f"{len(info['dirty'])} uncommitted"] if info["dirty"] else []
    parts += [f"{info['unpushed']} unpushed"] if info["unpushed"] else []
    return ", ".join(parts) or ("pushed" if info["ahead"] else "no commits yet")


def pr_text(info):
    pr = info["pr"]
    if info["pr_error"]:
        return "?"
    if not pr:
        return "none yet"
    state = {"MERGED": "merged", "CLOSED": "closed"}.get(pr["state"], "draft" if pr.get("isDraft") else "ready")
    return f"#{pr['number']} {state}"


def some(paths, n=4):
    paths = sorted(paths)
    return ", ".join(paths[:n]) + (f" and {len(paths) - n} more" if len(paths) > n else "")


def cmd_table(proj, tidy=True, fetch=True):
    notes, needs, landed = [], [], []
    if fetch:
        try:
            git(proj["main"], "fetch", "--quiet", "--prune", proj["remote"], timeout=45)
        except Fail:
            notes.append(f"Could not fetch {proj['remote']}; what follows is as of the last fetch.")
    items = find_items(proj)
    here = item_at(items, os.getcwd())
    sess = sessions()
    with ThreadPoolExecutor(max_workers=8) as pool:
        infos = dict(zip([id(it) for it in items], pool.map(inspect, items)))

    merged = [it for it in items if (infos[id(it)]["pr"] or {}).get("state") == "MERGED"]
    if merged and (here or not tidy):
        if here:
            notes.append("Merged items are tidied when `slots` runs outside an item's folder: "
                         + ", ".join(it.label for it in merged) + ".")
    elif merged:
        with Lock(proj, wait=False) as free:
            losts = {id(it): (lambda it=it, pr=infos[id(it)]["pr"]: tidy_blocker(it, pr)) for it in merged}
            blockers = {id(it): losts[id(it)]() for it in (merged if free else [])}
            # Every session told to stop first, so their SessionEnd hooks run side by side, under one
            # deadline. An item whose session was already stopped gets no wait: what runs in its folder
            # is no hook of ours, and waiting for it would hold up every table.
            stopped, deadline = set(), time.time() + FOLDER_WAIT
            if sess is not None:
                for it in merged if free else []:
                    if not blockers[id(it)] and stop_session(it, sess):
                        stopped.add(id(it))
                sess = sessions() or sess
            for it in merged if free else []:
                info = infos[id(it)]
                lost, blocker = losts[id(it)], blockers[id(it)]
                if not blocker:
                    try:
                        remove_item(proj, it, sess, lost, deadline if id(it) in stopped else time.time())
                    except PartlyRemoved as e:
                        needs.append(f"{it.label}: PR #{info['pr']['number']} merged, but it was not fully tidied: {e}.")
                        items.remove(it)
                        continue
                    except InUse as e:
                        needs.append(f"{it.label}: PR #{info['pr']['number']} merged, but it was not tidied yet: "
                                     f"{e}. Nothing was deleted. The next `slots` tidies it once that has left "
                                     f"{it.folder}.")
                        continue
                    except Fail as e:
                        blocker = str(e)
                if blocker:
                    needs.append(f"{it.label}: PR #{info['pr']['number']} merged, but it was not tidied: {blocker}. "
                                 f"Nothing was deleted: {it.folder}\n    Push or discard what is there, then "
                                 f"`slots clear {it.numbers[0]}`.")
                else:
                    items.remove(it)
                    landed.append((set(it.numbers), info["pr"]["number"]))
                    notes.append(f"Tidied {it.label}: PR #{info['pr']['number']} merged; "
                                 "session, folder and branch removed.")

    queue = read_queue(proj)
    if tidy and not here:
        open_numbers = {n for q in queue["entries"] for n in q["numbers"]}
        for it in items:
            pr = (infos[id(it)]["pr"] or {}).get("number")
            open_numbers |= set(it.numbers) | {n for n in (it.state.get("pr"), pr) if n}
        dropped = drop_finished_bullets(proj, open_numbers, landed)
        if dropped:
            notes.append(f"NEXT.md: dropped the `## Slots` bullet of {', '.join(dropped)}, no longer open"
                         + ("; what merged is now under `## Where we left off`." if landed else "."))
    rows = []
    for it in items:
        info = infos[id(it)]
        port = it.state.get("port")
        where = "-" if not port else f":{port}" + ("" if port_open(port) else " off")
        title = it.title if len(it.title) <= 34 else it.title[:33] + "…"
        rows.append((("> " if it is here else "") + it.label, title, where, session_text(it, sess),
                     work_text(info), pr_text(info)))
    for q in queue["entries"]:
        label = queue_label(q)
        direction = q["direction"] if len(q["direction"]) <= 34 else q["direction"][:33] + "…"
        rows.append((label, direction, "-", "queued", "-", "-"))

    say(f"{proj['name']} · base {proj['base']} · {len(items)} open, {len(queue['entries'])} queued")
    if rows:
        head = ("ITEM", "WHAT", "SERVER", "SESSION", "WORK", "PR")
        widths = [max(len(r[i]) for r in rows + [head]) for i in range(len(head))]
        say()
        for r in [head] + rows:
            say("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip())
    else:
        say("\nNothing open. `slots start 238` starts an issue, `slots start pr 473` a PR.")

    overlaps = []
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            both = infos[id(a)]["files"] & infos[id(b)]["files"]
            if both:
                overlaps.append(f"  {a.label} and {b.label}: {some(both)}")
    moved = [f"  {it.label}: {it.base} is {infos[id(it)]['behind']} commit(s) ahead and changed {some(infos[id(it)]['moved'])}"
             for it in items if infos[id(it)]["moved"]]
    errors = sorted({infos[id(it)]["pr_error"] for it in items if infos[id(it)]["pr_error"]})
    for heading, lines in (("Both touch:", overlaps), ("The base branch moved under:", moved), ("Needs you:", ["  " + n for n in needs])):
        if lines:
            say("\n" + heading)
            for line in lines:
                say(line)
    if errors:
        notes.append("GitHub could not be read (" + "; ".join(errors) + "), so the PR column is unknown and nothing was tidied.")
    if queue["bad"]:
        notes.append(f"{queue['path']}: line(s) {', '.join(map(str, queue['bad']))} are not an item "
                     "(`- 238`, `- 563+512 — direction`, `- pr 473`).")
    if notes:
        say()
        for n in notes:
            say(n)
    if here:
        say("\n" + facts_block(proj, here))
    elif queue["entries"]:
        say(f"\nQueue: {queue['path']}")
    return 0


# --- server, setup ----------------------------------------------------------

def cmd_server(proj, args):
    if not args or args[0] not in ("start", "stop"):
        raise Fail("`slots server stop` or `slots server start`, with an item number when you are not in its folder.")
    with Lock(proj):
        items = find_items(proj)
        item = need_item(proj, items, numbers_in(args[1:2])[0]) if len(args) > 1 else item_at(items, os.getcwd())
        if not item:
            raise Fail("which item? Run this in the item's folder, or give its number.")
        if args[0] == "stop":
            say(f"{item.label}: dev server stopped." if stop_server(item) else f"{item.label}: dev server was not running.")
        else:
            say(item.label)
            start_server(proj, items, item)
    return 0


def shares_number(main):
    """True when another repo beside this one starts with the same project number, as two repos
    for one client project can. The number alone would then not say which repo an item's folder belongs to."""
    main = Path(main)
    m = re.match(r"(\d+)-", main.name)
    return bool(m) and any(d != main and (d / ".git").is_dir() for d in main.parent.glob(m.group(1) + "-*"))


def gh_out(main, *args):
    """gh's stdout, stripped, or "" when gh fails or is missing."""
    try:
        p = run([GH] + list(args), cwd=main, timeout=20)
    except Fail:
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def detect_base(main):
    """The integration branch, as the global CLAUDE.md defines it. Of its first step, what the repo documents,
    only `.nk-config.json`'s `defaultBranch` is machine-readable; setup prints the result for correction with
    --base for the prose cases. Then the most common base of the last 10 merged PRs, else `dev` where origin
    has one, else GitHub's default branch, else origin/HEAD, else the current branch. A branch's name settles
    nothing on its own: a repo can keep a `dev` it stopped merging into, or integrate on `testing`. The local
    origin/HEAD is a snapshot from clone time, so it is only the fallback for when gh can't answer."""
    documented = (read_json(Path(main) / ".nk-config.json") or {}).get("defaultBranch")
    if isinstance(documented, str) and documented.strip():
        return documented.strip()
    try:
        prs = json.loads(gh_out(main, "pr", "list", "--state", "merged", "--limit", "10",
                                "--json", "baseRefName,mergedAt") or "[]")
        # gh lists by creation date, not merge date; sort so a tie goes to the most recently merged.
        bases = [p["baseRefName"] for p in sorted(prs, key=lambda p: p.get("mergedAt") or "", reverse=True)
                 if p.get("baseRefName")]
    except (ValueError, AttributeError, TypeError, KeyError):
        bases = []
    if bases:
        return max(bases, key=bases.count)  # max keeps the first of equals: the most recently merged
    if git_ok(main, "rev-parse", "--verify", "-q", "refs/remotes/origin/dev"):
        return "dev"
    default = gh_out(main, "repo", "view", "--json", "defaultBranchRef", "-q", ".defaultBranchRef.name")
    if default:
        return default
    head = git(main, "symbolic-ref", "--short", "refs/remotes/origin/HEAD", check=False)
    return head.split("/", 1)[1] if "/" in head else (git(main, "branch", "--show-current", check=False) or "main")


def detect(main):
    """Defaults for a project nobody has set up yet."""
    main = Path(main)
    name = main.name
    m = re.match(r"(\d+)-", name)
    cfg = {"main": str(main), "prefix": m.group(1) if m and not shares_number(main) else name,
           "remote": "origin", "dev": "", "check": "",
           "install": "", "first_port": 3001, "address": "http://localhost:{port}"}
    cfg["base"] = detect_base(main)
    scripts = (read_json(main / "package.json") or {}).get("scripts") or {}
    pm, ci = "npm", "npm ci"
    if (main / "pnpm-lock.yaml").exists():
        pm, ci = "pnpm", "pnpm install --frozen-lockfile"
    elif (main / "yarn.lock").exists():
        pm, ci = "yarn", "yarn install --frozen-lockfile"
    if (main / "package.json").exists():
        cfg["install"] = ci
    if "dev" in scripts:
        cfg["dev"] = "npm run dev -- --port {port}" if pm == "npm" else f"{pm} dev --port {{port}}"
    if "check" in scripts:
        cfg["check"] = f"{pm} run check"
    return cfg


def cmd_setup(args):
    opts, i = {}, 0
    while i < len(args):
        key = args[i].lstrip("-").replace("-", "_")
        if not args[i].startswith("--") or key not in CONFIG_KEYS + ("name",) or i + 1 >= len(args):
            raise Fail(f"setup takes --name and {', '.join('--' + k.replace('_', '-') for k in CONFIG_KEYS if k != 'main')}, each with a value.")
        opts[key] = args[i + 1]
        i += 2
    main = main_checkout(os.getcwd())
    if not main:
        raise Fail("run `slots setup` inside the project's main checkout.")
    projs = load_projects()
    existing = next((p for p in projs.values() if os.path.realpath(p["main"]) == main), None)
    cfg = {k: existing[k] for k in CONFIG_KEYS if k in existing} if existing else detect(main)
    name = opts.pop("name", None) or (existing or {}).get("name")
    cfg.update(opts)
    if not str(cfg["first_port"]).isdigit():
        raise Fail("--first-port takes a number.")
    cfg["first_port"] = int(cfg["first_port"])
    if not name:
        name = cfg["prefix"]
        if name in projs:
            name = cfg["prefix"] = Path(main).name
    if name in projs and os.path.realpath(projs[name]["main"]) != main:
        raise Fail(f"a project named {name} already points at {projs[name]['main']}. Pass --name and --prefix.")
    path = HOME / name / "config.json"
    write_json(path, cfg)
    say(f"{'Updated' if existing else 'Wrote'} {path}\n")
    meaning = {
        "main": "the main checkout", "prefix": "item folders are <prefix>-issue-N-… beside it",
        "base": "new issue branches start here", "remote": "", "dev": "dev server; {port} is filled in. Empty: none",
        "check": "what a slot runs before marking a PR ready", "install": "run once in each new folder",
        "first_port": "ports are handed out from here", "address": "where you look; {port} is filled in",
    }
    for k in CONFIG_KEYS:
        say(f"  {k:<11} {str(cfg.get(k, '')) or '(none)'}" + (f"\n  {'':<11} ({meaning[k]})" if meaning[k] else ""))
    say("\nChange a value with `slots setup --dev \"…\"`, or edit the file.")
    if not existing and cfg["prefix"] == Path(main).name and shares_number(main):
        say("Another repo beside this one starts with the same number, so the prefix is the whole folder name. "
            "`slots setup --prefix …` sets a shorter one, before the first item is started.")
    for tool, probe in ((CLAUDE, [CLAUDE, "--version"]), (GH, [GH, "auth", "status"])):
        try:
            ok = run(probe, timeout=30).returncode == 0
        except Fail:
            ok = False
        if not ok:
            say(f"Warning: `{' '.join(probe)}` fails here; slots needs it.")
    return 0


def main(argv):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    project = None
    if len(argv) > 1 and argv[0] in ("-p", "--project"):
        project, argv = argv[1], argv[2:]
    cmd, args = (argv[0], argv[1:]) if argv else ("table", [])
    try:
        if cmd in ("-h", "--help", "help"):
            say(__doc__.strip())
            return 0
        if cmd == "setup":
            return cmd_setup(args)
        commands = {"table": lambda p, a: cmd_table(p), "start": cmd_start, "stop": cmd_stop,
                    "clear": cmd_clear, "server": cmd_server}
        if cmd not in commands:
            raise Fail(f"unknown command {cmd!r}. `slots --help` lists them.")
        projs = load_projects()
        here = main_checkout(os.getcwd())
        if cmd == "table" and not project and len(projs) > 1 and not any(
                os.path.realpath(p["main"]) == here for p in projs.values()):
            # Several projects and you are in none of them: where everything stands is every table.
            status = 0
            for i, p in enumerate(projs.values()):
                if i:
                    say()
                status |= cmd_table(p)
            return status
        return commands[cmd](resolve_project(project, changing=cmd != "table"), args)
    except Fail as e:
        say(f"slots: {e}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
