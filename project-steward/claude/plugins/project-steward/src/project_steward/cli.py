"""`project-steward` CLI. Deterministic operations only — interviews and
judgment belong to the agent skills; this tool owns filesystem, git-read,
schema, scaffolding, and migration mechanics.

Global conventions: `--json` for machine-readable output, `--dry-run`
where destructive, `--yes` to skip interactive confirmation. Never pushes;
commits only via explicit `wrap --commit` under a permitting policy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import StewardError, __version__
from . import backend_broker, doctor, gitutil, hooks
from . import scaffold, sessions, survey as survey_mod
from .paths import find_project_root, is_steward_project
from .state import load_backend, load_config, load_state


def _root(args):
    return Path(args.root).resolve() if args.root else find_project_root()


def _print(obj, as_json):
    if as_json:
        sys.stdout.write(json.dumps(obj, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(str(obj) + "\n")


def _confirm(prompt):
    if not sys.stdin.isatty():
        return False
    try:
        answer = input("%s [y/N] " % prompt).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------

def cmd_survey(args):
    root = _root(args)
    findings = survey_mod.survey(root)
    if args.json:
        _print(findings, True)
        return 0
    lines = ["Survey of %s" % findings["root"]]
    git = findings["git"]
    lines.append("git: repo=%s branch=%s dirty=%d remote=%s"
                 % (git["is_repo"], git["branch"] or "-", git["dirty_count"],
                    git["remote_url"] or "-"))
    lines.append("languages: " + (", ".join(
        "%s(%d)" % (l["language"], l["files"]) for l in findings["languages"])
        or "none detected"))
    lines.append("manifests: " + (", ".join(findings["manifests"]) or "none"))
    lines.append("commands: " + (json.dumps(findings["candidate_commands"])
                                 if findings["candidate_commands"] else "none"))
    active = [k for k, v in findings["task_systems"].items() if v]
    lines.append("task systems: " + (", ".join(active) or "none"))
    if findings["sensitive_paths_present"]:
        lines.append("sensitive paths present (never read/summarize): "
                     + ", ".join(findings["sensitive_paths_present"]))
    lines.append("open questions:")
    for q in findings["open_questions"]:
        lines.append("  - " + q)
    _print("\n".join(lines), False)
    return 0


def cmd_init(args):
    root = _root(args)
    answers = {
        "project_name": args.project_name,
        "one_liner": args.one_liner,
        "primary_language": args.primary_language,
        "build_command": args.build_command,
        "test_command": args.test_command,
        "lint_command": args.lint_command,
        "backend_name": args.backend,
        "first_milestone": args.first_milestone,
        "commit_policy": args.commit_policy,
        "codex_hooks": args.codex_hooks,
    }
    plan, mapping = scaffold.plan_files(root, answers)
    creates = [k for k, v in plan.items() if v[0] == "create"]
    updates = [k for k, v in plan.items() if v[0] == "update"]
    skips = [k for k, v in plan.items() if v[0] == "skip"]

    if args.dry_run or not args.yes:
        _print("init plan for %s" % root, False)
        for rel in sorted(creates):
            _print("  create: %s" % rel, False)
        for rel in sorted(updates):
            _print("  update: %s" % rel, False)
        for rel in sorted(skips):
            _print("  keep:   %s (exists)" % rel, False)
        for rel in ("AGENTS.md", "CLAUDE.md", ".gitignore",
                    ".project-steward/WORKFLOW.md", ".project-steward/config.toml",
                    ".codex/config.toml", ".codex/hooks.json"):
            diff = plan.get(rel, ("", None, ""))[2]
            if not diff and plan.get(rel, ("",))[0] == "create":
                diff = plan[rel][1]
            if diff:
                _print("\n--- diff for %s ---\n%s" % (rel, diff), False)
    for warning in mapping.get("_warnings", []):
        _print("warn: %s" % warning, False)
    if args.dry_run:
        return 0
    if not args.yes:
        if not _confirm("Apply this plan?"):
            _print("Aborted; nothing written. (Use --yes for "
                   "non-interactive runs.)", False)
            return 1
    written = scaffold.apply_plan(root, plan, mapping)
    _print("Wrote %d file(s): %s" % (len(written), ", ".join(sorted(written))),
           False)
    if ".codex/hooks.json" in plan and plan[".codex/hooks.json"][0] != "skip":
        _print("Codex hook files configured. Ensure project-steward is on PATH, "
               "trust the project, and review hooks in Codex /hooks; "
               "activation has not been verified.", False)
    if load_config(root)["git"]["commit_policy"] == "never":
        return 0
    if not gitutil.is_repo(root):
        _print("Note: not a git repository. Recommended (with user "
               "approval): git init && git add -A && git commit -m "
               "\"chore: initialize Project Steward project management\"",
               False)
    else:
        commit_paths = ["AGENTS.md", "CLAUDE.md", ".gitignore"]
        commit_paths.extend(path for path in written if path.startswith(".codex/"))
        _print("Suggested commit: %s" % gitutil.suggest_commit_command(
            root, "chore: initialize Project Steward project management",
            commit_paths), False)
    return 0


def cmd_status(args):
    root = _root(args)
    if not is_steward_project(root):
        _print("Not a Project Steward project (no .project-steward/). "
               "Run `project-steward init`.", False)
        return 1
    recap = sessions.build_recap(root)
    if args.json:
        recap["config"] = load_config(root)
        recap["state"] = load_state(root)
        recap["backend"] = load_backend(root)
        _print(recap, True)
    else:
        _print(sessions.format_recap(recap), False)
    return 0


def cmd_resume(args):
    root = _root(args)
    if not is_steward_project(root):
        return cmd_status(args)
    previous, _record = sessions.claim_session(
        root, args.agent, reuse_current=True)
    recap = sessions.build_recap(root, runtime_record=previous)
    if args.json:
        recap["previous_runtime_claim"] = previous
        _print(recap, True)
    else:
        _print(sessions.format_recap(recap), False)
        if previous.get("status") == "active":
            _print("note: previous runtime claim on this device was still "
                   "active (%s)." % previous.get("agent", "?"), False)
    return 0


def cmd_checkpoint(args):
    root = _root(args)
    if not is_steward_project(root):
        _print("Not a Project Steward project.", False)
        return 1
    sessions.checkpoint(root, args.note, args.agent, auto=args.auto)
    if args.json:
        _print({"ok": True, "checkpoint": True, "auto": bool(args.auto)}, True)
        return 0
    _print("Checkpoint recorded in PROGRESS.md; HANDOFF.md front matter "
           "refreshed.", False)
    return 0


def cmd_wrap(args):
    root = _root(args)
    if not is_steward_project(root):
        _print("Not a Project Steward project.", False)
        return 1
    report = sessions.wrap(root, args.summary, args.agent)
    if args.json and not args.commit:
        _print(dict(report, ok=True, session_status="closed"), True)
        return 0
    for warning in report["warnings"]:
        _print("warn: %s" % warning, False)
    if report["commit_suggestion"]:
        _print("commit policy: %s" % report["commit_policy"], False)
        if args.commit and report["commit_policy"] in ("ask", "auto"):
            rc, out = gitutil.stage_and_commit(
                root,
                "chore(steward): wrap session — %s" % (args.summary or "handoff")[:60],
                [".project-steward", "AGENTS.md", "CLAUDE.md", ".gitignore"],
            )
            _print(out or ("commit rc=%d" % rc), False)
            if rc:
                _print("Session bookkeeping saved, but commit failed.", False)
                return rc
        else:
            _print("suggested: %s" % report["commit_suggestion"], False)
            _print("(run with --commit to let the CLI perform it; never "
                   "pushes)", False)
    _print("Session wrapped (session_status: closed).", False)
    return 0


def cmd_close(args):
    root = _root(args)
    if not is_steward_project(root):
        _print("Not a Project Steward project.", False)
        return 1
    sessions.close_only(root, args.agent)
    if args.json:
        _print({"ok": True, "session_status": "closed", "wrapped": False}, True)
        return 0
    _print("Session marked closed (quick close; handoff body untouched). "
           "Prefer `wrap` when real work happened.", False)
    return 0


def cmd_doctor(args):
    root = _root(args)
    results = doctor.run_checks(root, self_mode=args.self_check)
    if args.json:
        _print(results, True)
        fails = sum(1 for r in results if r["status"] == doctor.FAIL)
    else:
        text, fails = doctor.format_results(results)
        _print(text, False)
    return 1 if fails else 0


def cmd_backend(args):
    root = _root(args)
    action = args.action
    if action == "detect":
        _print(backend_broker.detect(root), True)
        return 0
    if action == "recommend":
        rec = backend_broker.recommend(root)
        if args.json:
            _print(rec, True)
            return 0
        _print("Backend recommendation (signals: %s)"
               % json.dumps(rec["signals"]), False)
        for entry in rec["ranked"][:5]:
            # Print the identifier too: `adopt` takes `spec_kit`, not
            # "GitHub Spec Kit".
            _print("  %3d  %-16s %-28s %s"
                   % (entry["score"], entry["name"], entry["display"],
                      entry["plain"]),
                   False)
            if entry["repo"]:
                _print("       %s" % entry["repo"], False)
        if rec["migration_hint"]:
            _print("hint: %s" % rec["migration_hint"], False)
        _print("Adopt with: project-steward backend adopt <name> "
               "(previews workflow/backend changes for approval)", False)
        return 0
    if action == "adopt":
        if not args.name:
            _print("usage: project-steward backend adopt <name>", False)
            return 2
        report = backend_broker.adopt(
            root, args.name, assume_yes=args.yes,
            confirm=lambda diff: (_print("\nProposed backend changes:\n"
                                         + diff, False)
                                  or _confirm("Apply this change?")))
        if not report.get("ok"):
            _print("error: %s" % report.get("error"), False)
            return 1
        _print("Adopted backend: %s" % report["backend"], False)
        if report.get("install"):
            _print("install (needs your approval to run; verify upstream): "
                   "%s" % report["install"], False)
        if report.get("repo"):
            _print("docs: %s" % report["repo"], False)
        if report.get("pointer_note"):
            _print(report["pointer_note"], False)
        return 0
    if action == "status":
        _print(load_backend(root), True)
        return 0
    _print("unknown backend action: %s" % action, False)
    return 2


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="project-steward",
        description="Cross-agent project stewardship: durable repo-resident "
                    "project memory for Claude Code, Codex, and friends.",
    )
    parser.add_argument("--version", action="version",
                        version="project-steward %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    def common(p):
        p.add_argument("--root", default=None, help="project root override")
        p.add_argument("--json", action="store_true")
        return p

    p = common(sub.add_parser("survey", help="read-only repository survey"))
    p.set_defaults(func=cmd_survey)

    p = common(sub.add_parser("init", help="scaffold steward state "
                                           "(deterministic part of init)"))
    p.add_argument("--project-name")
    p.add_argument("--one-liner")
    p.add_argument("--primary-language")
    p.add_argument("--build-command")
    p.add_argument("--test-command")
    p.add_argument("--lint-command")
    p.add_argument("--backend", choices=sorted(
        set(backend_broker.BACKENDS) - backend_broker.STUBS))
    p.add_argument("--first-milestone")
    p.add_argument("--commit-policy", choices=("auto", "ask", "never"),
                   help="policy for a new config (default: auto; existing configs kept)")
    p.add_argument("--no-codex-hooks", dest="codex_hooks", action="store_false",
                   default=None, help="skip project-local Codex hook setup")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_init)

    p = common(sub.add_parser("status", help="read-only recap"))
    p.set_defaults(func=cmd_status)

    p = common(sub.add_parser("resume", help="claim session + recap "
                                             "(never dirties git)"))
    p.add_argument("--agent", default="cli")
    p.set_defaults(func=cmd_resume)

    p = common(sub.add_parser("checkpoint", help="semantic checkpoint"))
    p.add_argument("--note", required=True)
    p.add_argument("--agent", default="cli")
    p.add_argument("--auto", action="store_true")
    p.set_defaults(func=cmd_checkpoint)

    p = common(sub.add_parser("wrap", help="finalize session handoff"))
    p.add_argument("--summary", required=True)
    p.add_argument("--agent", default="cli")
    p.add_argument("--commit", action="store_true",
                   help="perform the suggested commit (never pushes)")
    p.set_defaults(func=cmd_wrap)

    p = common(sub.add_parser("close", help="quick close without full wrap"))
    p.add_argument("--agent", default="cli")
    p.set_defaults(func=cmd_close)

    p = common(sub.add_parser("doctor", help="health checks"))
    p.add_argument("--self", dest="self_check", action="store_true",
                   help="extra checks for the Project Steward repo itself")
    p.set_defaults(func=cmd_doctor)

    p = common(sub.add_parser("backend", help="task-backend broker"))
    p.add_argument("action",
                   choices=["detect", "recommend", "adopt", "status"])
    p.add_argument("name", nargs="?")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_backend)

    p = sub.add_parser("hook", help="internal: lifecycle hook dispatcher")
    p.add_argument("event")
    p.set_defaults(func=None)  # handled specially to pass through extras
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # Internal: the hook wrapper asks "can you run?" before running a hook
    # for real, so it never has to retry after output has been written.
    if argv == ["--probe"]:
        return 0
    # `hook` passes remaining args straight to the dispatcher.
    if argv and argv[0] == "hook":
        return hooks.main(argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except scaffold.TemplateError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2
    except StewardError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
