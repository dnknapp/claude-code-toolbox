#!/usr/bin/env python3
"""Mechanical staleness sweep over an auto-memory directory.

Emits a ranked flag list for a model to adjudicate. Decides nothing itself:
every check here is a signal that a file is worth READING, not a verdict.

Check selection is empirical, from a 66-file corpus survey (2026-08-12).
Only classes that actually rot are checked. Deliberately NOT checked --
they scored 97/98 and are pure cost: commit SHAs, code identifiers,
config keys, npm script names.

Usage: sweep.py <memory-dir> [--repo <repo-root>] [--no-gh]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

# Bookkeeping claims rot fastest: 38 of 55 were dead in the survey corpus.
# A closed issue only matters near a word asserting it is still live.
# Bare `open` and `gates?` fire on mechanism nouns ("the shared gate", "open a
# PR") and on dated narration. Only phrasings that ASSERT ongoing openness earn
# a place here.
OPENNESS = re.compile(
    r"\b(still open|stays open|remains open|left open|still unfiled|"
    r"awaits?|awaiting|blocked on|blocker|pending|not yet|unbuilt|unreviewed|"
    r"nothing is merged|to be done|to do|will close|held|deferred|"
    r"next up|next session|next:|"
    # Bare "open" is how openness is usually asserted, but it is also a verb
    # ("open a PR") and a noun modifier ("open question"). Exclude those.
    r"open(?!\s+(?:a|an|the|it|up|question|questions|PR|pull|issue)\b)(?!ed|ing))\b",
    re.I,
)
ISSUE = re.compile(r"(?<![\w/])#(\d{1,5})\b")
WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")
FILELINE = re.compile(r"`?([\w./-]+\.(?:js|mjs|cjs|ts|tsx|jsx|json|md|scss|css|yml|yaml|py|sh)):(\d+)(?:\s*[-–]\s*(\d+))?`?")
PATHISH = re.compile(r"`([\w./-]+\.(?:js|mjs|cjs|ts|tsx|jsx|json|md|scss|css|yml|yaml|py|sh))`")
MEASURED = re.compile(r"\b(\d{2,5})\s*(tests?|/\s*\d+|lines|sections|exports|files|entries)\b", re.I)
# A bare "Update the ..." or "Done when ..." is ordinary prose, so the dated and
# corrective forms are what count.
ACCRETION = re.compile(
    r"(superseded|now stale|no longer (?:true|current)|original .{0,24}follows|"
    r"CORRECTED|^\s*(?:UPDATE|DONE|EDIT)\b[: ]*\d{4}-\d{2}-\d{2}|"
    r"\b(?:update|edit|correction)d?\s+\d{4}-\d{2}-\d{2})",
    re.I | re.M,
)
IDENT = re.compile(r"`([A-Z][A-Z0-9_]{3,}|[a-zA-Z_][\w]*)\(\)`|`([A-Z][A-Z0-9_]{4,})`")
ENTRYPOINT = re.compile(r"(START HERE|NEXT SESSION|▶)")
# Index entries get decorated (**bold**, a ▶ marker), so allow emphasis and
# marker glyphs between the bullet and the link.
INDEX_LINK = re.compile(r"^\s*[-*]\s*[*_▶\s]*\[[^\]]*\]\(([^)]+\.md)\)", re.M)

# Paths that legitimately do not resolve in this repo.
FOREIGN = re.compile(r"^(/tmp/|/private/tmp/|~|\.\./|\d{4}-)|(^|/)(node_modules)/")

SEVERITY = {
    "issue-status": 1,
    "file-line-drift": 2,
    "dead-path": 3,
    "churn": 3,
    "dead-identifier": 3,
    "index-orphan": 4,
    "index-broken-link": 4,
    "entrypoint-collision": 5,
    "accretion": 6,
    "dangling-link": 7,
    "measured-number": 8,
    "frontmatter": 9,
}

# Resolvable without opening a memory: a format fix, an index line, a listed
# number a human confirms. Everything else needs judgment on a claim.
CLEANUP_ONLY = {"measured-number", "frontmatter", "dangling-link"}


def sh(cmd, cwd=None):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
        return r.stdout.strip() if r.returncode == 0 else None
    except (subprocess.SubprocessError, OSError):
        return None


def frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw, body = text[3:end], text[end + 4 :]
    fm = {}
    for line in raw.splitlines():
        m = re.match(r"^\s*([\w-]+):\s*(.*)$", line)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip("\"'")
    return fm, body


def strip_code(text):
    """Fenced blocks hold examples, not claims. Checking them yields noise."""
    return re.sub(r"```.*?```", "", text, flags=re.S)


def build_tracked_index(repo_root):
    """Memories cite `index.js`, not `packages/cli/index.js`. Resolving a bare
    basename against the tracked tree is what separates a real dead path from
    prose naming a file that lives one directory down."""
    out = sh(["git", "ls-files"], cwd=repo_root)
    by_base = defaultdict(list)
    tracked = set()
    for p in (out or "").splitlines():
        tracked.add(p)
        by_base[os.path.basename(p)].append(p)
    return tracked, by_base


def resolve_cite(cite, repo_root, tracked, by_base):
    """Return a repo-relative path for a cited file, or None if it resolves nowhere."""
    if cite in tracked or os.path.exists(os.path.join(repo_root, cite)):
        return cite
    if "/" not in cite:
        hits = by_base.get(cite, [])
        return hits[0] if len(hits) == 1 else (hits[0] if hits else None)
    hits = by_base.get(os.path.basename(cite), [])
    return hits[0] if len(hits) == 1 else None


def gh_issue_states(numbers, repo_root):
    """One API call per repo beats one per issue. Returns {number: state}."""
    if not numbers:
        return {}
    out = sh(["gh", "issue", "list", "--state", "all", "--limit", "1000",
              "--json", "number,state"], cwd=repo_root)
    states = {}
    if out:
        try:
            for it in json.loads(out):
                states[it["number"]] = it["state"].upper()
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    out = sh(["gh", "pr", "list", "--state", "all", "--limit", "1000",
              "--json", "number,state"], cwd=repo_root)
    if out:
        try:
            for it in json.loads(out):
                states.setdefault(it["number"], it["state"].upper())
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return states


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("memory_dir")
    ap.add_argument("--repo", default=None, help="repo root cited paths resolve against")
    ap.add_argument("--no-gh", action="store_true", help="skip issue-status checks")
    ap.add_argument("--paths", action="store_true",
                    help="also check cited file paths (noisy: fires on files in other projects)")
    args = ap.parse_args()

    mem = os.path.abspath(args.memory_dir)
    if not os.path.isdir(mem):
        sys.exit(f"not a directory: {mem}")
    repo = os.path.abspath(args.repo) if args.repo else os.getcwd()

    files = sorted(
        f for f in os.listdir(mem)
        if f.endswith(".md") and f not in ("MEMORY.md", "NEXT.md")
    )
    if not files:
        sys.exit(f"no memory files in {mem}")

    docs = {}
    for f in files:
        with open(os.path.join(mem, f), encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        fm, body = frontmatter(text)
        docs[f] = {"fm": fm, "body": strip_code(body), "raw": text}

    tracked, by_base = build_tracked_index(repo)
    if not tracked:
        print(f"WARNING: `git ls-files` found nothing in {repo}. Cited-path, file:line, "
              f"identifier and churn checks will all no-op. Pass the right --repo.",
              file=sys.stderr)
    flags = defaultdict(list)

    def flag(kind, fname, detail):
        flags[fname].append((kind, detail))

    # --- index bijection -------------------------------------------------
    idx_path = os.path.join(mem, "MEMORY.md")
    indexed = set()
    if os.path.exists(idx_path):
        with open(idx_path, encoding="utf-8") as fh:
            idx = fh.read()
        indexed = {os.path.basename(t) for t in INDEX_LINK.findall(idx)}
        for missing in sorted(indexed - set(files)):
            flag("index-broken-link", "MEMORY.md", f"index points at `{missing}`, which does not exist")
        for orphan in sorted(set(files) - indexed):
            size = os.path.getsize(os.path.join(mem, orphan))
            flag("index-orphan", orphan,
                 f"absent from MEMORY.md ({size}B) - loads into no session, reachable only by wiki-link")
    else:
        print(f"WARNING: no MEMORY.md in {mem}", file=sys.stderr)

    # --- wiki-link resolution --------------------------------------------
    slugs = {f[:-3] for f in files}
    names = {d["fm"].get("name", "").strip() for d in docs.values()}
    norm = lambda s: s.strip().replace("_", "-").lower()
    resolvable = {norm(s) for s in slugs | names if s}
    for f, d in docs.items():
        for target in WIKILINK.findall(d["body"]):
            if norm(target) not in resolvable:
                flag("dangling-link", f,
                     f"`[[{target}]]` resolves to nothing - confirm it is a deliberate cross-repo reference")

    # --- issue / PR status ------------------------------------------------
    if not args.no_gh:
        cited = set()
        for d in docs.values():
            cited |= {int(n) for n in ISSUE.findall(d["body"])}
        states = gh_issue_states(cited, repo)
        if not states:
            print("WARNING: gh returned nothing - skipping issue-status "
                  "(the highest-yield check). Check `gh auth status`.", file=sys.stderr)
        for f, d in docs.items():
            for line in d["body"].splitlines():
                nums = [int(n) for n in ISSUE.findall(line)]
                if not nums or not OPENNESS.search(line):
                    continue
                closed = [n for n in nums if states.get(n) in ("CLOSED", "MERGED")]
                if closed:
                    flag("issue-status", f,
                         f"{', '.join('#%d' % n for n in closed)} closed, but the line asserts it is live: "
                         f"“{line.strip()[:120]}”")

    # --- file:line drift ---------------------------------------------------
    for f, d in docs.items():
        modified = d["fm"].get("modified", "")
        for cite, line_s, _end in FILELINE.findall(d["body"]):
            if FOREIGN.search(cite):
                continue
            real = resolve_cite(cite, repo, tracked, by_base)
            if not real:
                # A `file:line` cite is a precise claim, not prose naming a file
                # in another project -- so a vanished target is the strongest
                # signal available, and it must never be silently dropped.
                flag("file-line-drift", f,
                     f"`{cite}:{line_s}` cites a file that no longer exists")
                continue
            try:
                with open(os.path.join(repo, real), encoding="utf-8", errors="replace") as fh:
                    total = sum(1 for _ in fh)
            except OSError:
                continue
            n, where = int(line_s), cite if real == cite else f"{cite} -> {real}"
            if n > total:
                flag("file-line-drift", f,
                     f"`{where}:{n}` is past end of file ({total} lines)")
            elif modified:
                churn = sh(["git", "log", "--oneline", f"--since={modified[:10]}",
                            "-L", f"{n},{n}:{real}"], cwd=repo)
                if churn:
                    flag("file-line-drift", f,
                         f"`{where}:{n}` changed since this memory was written "
                         f"({len(churn.splitlines())} commits touch that line)")
            elif not modified:
                flag("file-line-drift", f,
                     f"`{where}:{n}` cannot be dated (no `modified` in frontmatter) - "
                     f"line numbers drift silently, so verify by hand")

    # --- dead paths (opt-in: noisy) ----------------------------------------
    # Paths measured 87% clean, and the misses are mostly files that live in
    # OTHER projects -- a consumer's `vite.config.ts`, a scaffolded template.
    # A script cannot tell "dead reference" from "file we are describing
    # elsewhere", so this runs only when asked.
    if args.paths:
        for f, d in docs.items():
            seen = set()
            for cite in PATHISH.findall(d["body"]):
                if cite in seen or FOREIGN.search(cite):
                    continue
                seen.add(cite)
                if not resolve_cite(cite, repo, tracked, by_base):
                    flag("dead-path", f,
                         f"`{cite}` resolves nowhere in this tree - confirm it is not "
                         f"a file in another project before treating it as dead")

    # --- churn triage ------------------------------------------------------
    # The only check that reaches SILENT environmental rot. A memory whose cited
    # code moved a lot since it was written may reason impeccably from a premise
    # that has since inverted -- no marker word, no dead link, nothing to grep.
    for f, d in docs.items():
        modified = d["fm"].get("modified", "")
        if not modified:
            continue
        cited = set()
        for cite in PATHISH.findall(d["body"]):
            real = resolve_cite(cite, repo, tracked, by_base)
            if real:
                cited.add(real)
        for cite, _l, _e in FILELINE.findall(d["body"]):
            real = resolve_cite(cite, repo, tracked, by_base)
            if real:
                cited.add(real)
        if not cited:
            continue
        churn = sh(["git", "log", "--oneline", f"--since={modified[:10]}", "--"]
                   + sorted(cited), cwd=repo)
        n = len(churn.splitlines()) if churn else 0
        if n >= 10:
            flag("churn", f,
                 f"{n} commits touched the code this memory reasons about "
                 f"({', '.join(sorted(cited)[:3])}{'...' if len(cited) > 3 else ''}) "
                 f"since {modified[:10]} - check the premise, not just the citations")

    # --- dead identifiers --------------------------------------------------
    # A grep is near-free, and an identifier that vanished under a load-bearing
    # claim is the silent, high-consequence failure shape.
    for f, d in docs.items():
        seen = set()
        for a, b in IDENT.findall(d["body"]):
            ident = a or b
            if not ident or ident in seen:
                continue
            seen.add(ident)
            if not sh(["git", "grep", "-lw", "--", ident], cwd=repo):
                flag("dead-identifier", f,
                     f"`{ident}` appears nowhere in the tree - renamed, removed, "
                     f"or it belongs to another project")

    # --- entry-point collision ---------------------------------------------
    claimants = [f for f, d in docs.items() if ENTRYPOINT.search(d["raw"])]
    if len(claimants) > 1:
        for f in claimants:
            others = [c for c in claimants if c != f]
            flag("entrypoint-collision", f,
                 f"claims START HERE / NEXT SESSION; so do {len(others)} others "
                 f"({', '.join(others[:3])}{'...' if len(others) > 3 else ''}) - at most one can be current")

    # --- accretion ---------------------------------------------------------
    for f, d in docs.items():
        hits = ACCRETION.findall(d["body"])
        if len(hits) >= 2:
            flag("accretion", f,
                 f"{len(hits)} supersession markers stacked in one file - "
                 f"corrections were appended beside the wrong text rather than amending it")

    # --- measured numbers (listed, never auto-judged) ----------------------
    for f, d in docs.items():
        found = {f"{a} {b}".strip() for a, b in MEASURED.findall(d["body"])}
        if found:
            flag("measured-number", f,
                 f"restated counts, unverifiable by script: {', '.join(sorted(found)[:6])}"
                 f"{' ...' if len(found) > 6 else ''}")

    # --- frontmatter -------------------------------------------------------
    for f, d in docs.items():
        fm, issues = d["fm"], []
        name = fm.get("name", "")
        if name and norm(name) != norm(f[:-3]):
            issues.append(f"`name: {name}` != filename slug (wiki-links resolve by filename)")
        if not fm.get("modified"):
            issues.append("no `modified` timestamp, so age-based triage falls back to mtime")
        if issues:
            flag("frontmatter", f, "; ".join(issues))

    # --- report ------------------------------------------------------------
    if not flags:
        print(f"# Memory sweep: {mem}\n\nNo flags across {len(files)} files.")
        return

    ranked = sorted(
        flags.items(),
        key=lambda kv: (min(SEVERITY.get(k, 99) for k, _ in kv[1]), -len(kv[1])),
    )
    counts = defaultdict(int)
    for _, items in flags.items():
        for kind, _ in items:
            counts[kind] += 1

    # Cleanup is mechanical and needs no reading; mixing it into the same list
    # inflates the apparent workload and dilutes the files that need judgment.
    adjudicate = [(f, i) for f, i in ranked
                  if not {k for k, _ in i} <= CLEANUP_ONLY]
    cleanup = [(f, i) for f, i in ranked if {k for k, _ in i} <= CLEANUP_ONLY]

    print(f"# Memory sweep: {mem}")
    verb = "needs" if len(adjudicate) == 1 else "need"
    print(f"\n{len(files)} files, {sum(counts.values())} flags across {len(flags)} files: "
          f"**{len(adjudicate)} {verb} adjudication**, {len(cleanup)} cleanup only.\n")
    print("| class | flags |\n|---|---|")
    for kind in sorted(counts, key=lambda k: SEVERITY.get(k, 99)):
        print(f"| {kind} | {counts[kind]} |")
    print("\n> Flags mark files worth reading. Recall is partial: the sweep sees "
          "citations and structure, not claims.\n")

    def emit(title, rows, note):
        print(f"\n---\n\n# {title}\n\n{note}")
        for fname, items in rows:
            print(f"\n## {fname}")
            for kind, detail in sorted(items, key=lambda kd: SEVERITY.get(kd[0], 99)):
                print(f"- **{kind}** - {detail}")

    emit("Adjudicate", adjudicate,
         "Each of these needs a memory read and a disposition.")
    emit("Cleanup", cleanup,
         "Mechanical fixes. No memory needs reading to resolve these.")


if __name__ == "__main__":
    main()
