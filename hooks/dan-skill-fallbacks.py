#!/usr/bin/python3
"""SessionStart hook: switch a fallback skill off in a project that has its own.

A fallback skill is a personal skill that stands in for a project skill in the
repos that ship none (dan-issue-pr-format for the dev kit's gh-issue-pr-format).
It names that skill as `yieldsTo` in a fallback.json beside its SKILL.md.

WHY A SETTING AND NOT A SHARED NAME:
  Claude Code resolves a name held by both a personal and a project skill to the
  personal one, so a shared name would hide the project's copy on this machine.
  With two names both are listed, and the model has to choose. The project's
  copy is preferred by hiding the fallback instead:
  `skillOverrides: {"<fallback>": "off"}` in the project's
  .claude/settings.local.json takes it out of the skill listing. The override
  matches by name, so on a shared name it would hide both copies.

TIMING:
  Settings are read before this hook runs. An override written here takes effect
  from the NEXT session (headless test 2026-10-09: the session that wrote it
  still listed both). For that first session the hook names the skill to use in
  additionalContext. Once the override is in place the hook prints nothing.

Add-only: it never removes an override, so one set by hand through /skills
stays. No-op under ~/.claude and when the project has none of the skills.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
PERSONAL_SKILLS = HOME / ".claude" / "skills"
LOCAL_SETTINGS = Path(".claude") / "settings.local.json"


def fallbacks():
    """{fallback skill name: the project skill it yields to}, from each fallback.json."""
    found = {}
    for meta in sorted(PERSONAL_SKILLS.glob("*/fallback.json")):
        try:
            target = json.loads(meta.read_text()).get("yieldsTo")
        except Exception:
            continue
        if target:
            found[meta.parent.name] = target
    return found


def skill_dirs(cwd, project):
    """Every .claude/skills a session started in `cwd` loads: cwd and its parents up to the repo root."""
    p = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    root = Path(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else project
    dirs, here = [project], cwd
    while True:
        dirs.append(here)
        if here == root or here == here.parent:
            break
        here = here.parent
    return [d / ".claude" / "skills" for d in dirs]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    cwd = Path(data.get("cwd") or os.getcwd()).resolve()
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd).resolve()
    if project == HOME / ".claude" or HOME / ".claude" in project.parents:
        return

    dirs = skill_dirs(cwd, project)
    yielding = {name: target for name, target in fallbacks().items()
                if any((d / target / "SKILL.md").is_file() for d in dirs)}
    if not yielding:
        return

    path = project / LOCAL_SETTINGS
    try:
        settings = json.loads(path.read_text()) if path.exists() else {}
    except Exception:
        settings = None  # not ours to repair; say which skill to use and leave the file
    overrides = settings.get("skillOverrides") if isinstance(settings, dict) else None
    overrides = overrides if isinstance(overrides, dict) else {}
    pending = {name: target for name, target in yielding.items() if overrides.get(name) != "off"}
    if not pending:
        return

    if isinstance(settings, dict):
        settings["skillOverrides"] = dict(overrides, **{name: "off" for name in pending})
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(settings, indent=2) + "\n")
            os.replace(tmp, path)
        except OSError:
            pass

    lines = ["This project has its own `%s` skill: use it, and leave `%s` unloaded. `%s` is the fallback for "
             "projects without one, and is switched off here from the next session." % (target, name, name)
             for name, target in sorted(pending.items())]
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                             "additionalContext": "\n".join(lines)}}))


if __name__ == "__main__":
    main()
