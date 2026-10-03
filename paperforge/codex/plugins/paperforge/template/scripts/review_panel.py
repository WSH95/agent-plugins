#!/usr/bin/env python3
"""Run selected reviewers against separate, minimal paper snapshots.

BACKEND=claude|codex|grok scripts/review_panel.sh N [--resume]
    [--reviewers reviewer-stats,reviewer-theory] [--jobs N]
BRIEFING=1 includes verified briefs. Resume inherits the saved backend,
briefing choice, and reviewer selection unless explicitly supplied again.
Snapshots limit supplied context; the CLI's sandbox controls filesystem access.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from workspace import WorkspaceError, load_workspace


class RoundError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save_run(directory, run):
    temp = directory / "run.json.tmp"
    temp.write_text(json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(directory / "run.json")


def read_run(directory):
    try:
        run = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RoundError(f"Cannot read round metadata: {exc}")
    if not isinstance(run, dict) or run.get("schema_version") != 1:
        raise RoundError("Unsupported round metadata; start a new round")
    names = run.get("reviewers")
    if (not isinstance(names, list) or not names or len(set(map(str, names))) != len(names)
            or any(not isinstance(n, str) or not re.fullmatch(r"reviewer-[A-Za-z0-9_-]+", n) for n in names)
            or not isinstance(run.get("runs"), dict)
            or any(not isinstance(run["runs"].get(n), dict) for n in names)):
        raise RoundError("Invalid reviewer selection/status in round metadata")
    return run


def review_errors(text):
    headings = [r"# Review\b", r"## Summary\b", r"## Strengths\b",
                r"## Weaknesses\s*[-–—]\s*major\b", r"## Weaknesses\s*[-–—]\s*minor\b",
                r"## Questions for the authors\b", r"## Scores\b", r"## Recommendation\b"]
    return [h.replace(r"\b", "") for h in headings
            if not re.search("^" + h, text, re.MULTILINE | re.IGNORECASE)]


def completed_reviews(directory, run=None):
    """Gate adjudication and verify that saved completed outputs are intact."""
    run = run or read_run(directory)
    reviews = []
    for name in run["reviewers"]:
        record = run["runs"][name]
        if record.get("status") != "complete":
            raise RoundError(f"{name} is {record.get('status', 'unfinished')}; resume the panel before adjudication")
        path = directory / (name + ".md")
        if not path.is_file() or digest(path.read_bytes()) != record.get("output_sha256"):
            raise RoundError(f"Completed review {name} is missing or changed; start a new round")
        if review_errors(path.read_text(encoding="utf-8")):
            raise RoundError(f"Completed review {name} has an incomplete structure")
        reviews.append(path)
    return reviews


@contextmanager
def round_lock(path):
    # OS locks are released even after a crash; an old lock file never blocks
    # --resume. Keep the file to avoid unlink/open races between two runners.
    with path.open("a+b") as lock:
        lock.seek(0, os.SEEK_END)
        if lock.tell() == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RoundError("This round is already running; wait for it to finish before resuming")
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def prepare_snapshot(workspace, destination, briefed):
    hashes = {}
    for source in workspace.files:
        target = destination / "manuscript" / source.relative_to(workspace.source_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(source), str(target))
        hashes[target.relative_to(destination).as_posix()] = digest(target.read_bytes())
    if briefed:
        briefs = workspace.root / "state/related-work/briefs"
        if not briefs.is_dir() or not any(briefs.rglob("*.md")):
            raise RoundError("BRIEFING=1 needs source-verified files in state/related-work/briefs/")
        for source in sorted(briefs.rglob("*.md")):
            if source.is_symlink() or any(p.is_symlink() for p in source.parents if p != workspace.root):
                raise RoundError("Briefing files must be regular files inside the workspace")
            target = destination / "briefing" / source.relative_to(briefs)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(str(source), str(target))
            hashes[target.relative_to(destination).as_posix()] = digest(target.read_bytes())
    return hashes


def command(backend, executable, prompt_path, workdir, message):
    if backend == "claude":
        return [executable, "-p", "--disallowedTools",
                "Write,Edit,NotebookEdit,Bash,WebFetch,WebSearch"]
    if backend == "codex":
        return [executable, "exec", "--sandbox", "read-only", "--skip-git-repo-check",
                "--output-last-message", str(message), "-"]
    return [executable, "--prompt-file", str(prompt_path), "--verbatim", "--no-plan",
            "--tools", "read_file,grep,list_dir", "--disallowed-tools", "Agent",
            "--cwd", str(workdir)]


def stop_process(process):
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()
    except ProcessLookupError:
        pass


def execute(directory, run, snapshot, prompts, executable, jobs):
    pending = [n for n in run["reviewers"] if run["runs"][n].get("status") != "complete"]
    active = {}
    interrupted = []
    handlers = {}
    for sig in (signal.SIGINT, signal.SIGTERM):
        handlers[sig] = signal.signal(sig, lambda signum, frame: interrupted.append(signum))
    diagnostics = directory / "diagnostics"
    diagnostics.mkdir(exist_ok=True)
    try:
        while pending or active:
            while pending and len(active) < jobs and not interrupted:
                name = pending.pop(0)
                record = run["runs"][name]
                attempt = record.get("attempts", 0) + 1
                record.update(status="running", attempts=attempt)
                save_run(directory, run)
                workdir = snapshot.parent / name
                shutil.copytree(str(snapshot), str(workdir))
                prefix = diagnostics / f"{name}-attempt-{attempt}"
                stdout_path = Path(str(prefix) + ".stdout.txt")
                stderr_path = Path(str(prefix) + ".stderr.txt")
                message = Path(str(prefix) + ".message.txt")
                # Keep long multiline prompts out of command arguments (notably
                # Windows .cmd shims). Prompt files stay outside the paper copy.
                prompt_path = snapshot.parent / (name + ".prompt.txt")
                prompt_path.write_text(prompts[name], encoding="utf-8")
                out = stdout_path.open("wb")
                err = stderr_path.open("wb")
                start = time.monotonic()
                print(f">>> {name} (attempt {attempt})", flush=True)
                try:
                    with prompt_path.open("rb") as prompt_input:
                        proc = subprocess.Popen(command(run["backend"], executable, prompt_path, workdir, message),
                                                cwd=str(workdir),
                                                stdin=prompt_input if run["backend"] != "grok" else subprocess.DEVNULL,
                                                stdout=out, stderr=err, start_new_session=os.name == "posix")
                except OSError as exc:
                    out.close()
                    err.close()
                    record.update(status="failed", error=str(exc), elapsed_seconds=0)
                    save_run(directory, run)
                    continue
                active[name] = (proc, out, err, message if run["backend"] == "codex" else stdout_path, start)
            if interrupted:
                for proc, *_ in active.values():
                    stop_process(proc)
            for name, (proc, out, err, output_path, start) in list(active.items()):
                if proc.poll() is None:
                    continue
                out.close()
                err.close()
                record = run["runs"][name]
                record.update(exit_code=proc.returncode, elapsed_seconds=round(time.monotonic() - start, 3))
                raw = output_path.read_bytes() if output_path.exists() else b""
                missing = review_errors(raw.decode("utf-8", errors="replace"))
                if not interrupted and proc.returncode == 0 and not missing:
                    final = directory / (name + ".md")
                    temp = directory / (name + ".md.tmp")
                    temp.write_bytes(raw)
                    temp.replace(final)
                    record.update(status="complete", output_sha256=digest(raw))
                    record.pop("error", None)
                else:
                    reason = "interrupted" if interrupted else (
                        f"backend exited {proc.returncode}" if proc.returncode else
                        "missing review sections: " + ", ".join(missing))
                    record.update(status="failed", error=reason)
                save_run(directory, run)
                print(f"<<< {name}: {record['status']} ({record['elapsed_seconds']}s)", flush=True)
                del active[name]
            if interrupted:
                break
            if active:
                time.sleep(0.05)
    finally:
        for proc, out, err, _, _ in active.values():
            stop_process(proc)
            out.close()
            err.close()
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    done = sum(r.get("status") == "complete" for r in run["runs"].values())
    print(f"Panel: {done}/{len(run['reviewers'])} reviews complete in {directory.name}.")
    if done != len(run["reviewers"]):
        print(f"Resume with: scripts/review_panel.sh {run['round']} --resume (diagnostics/ has failure output)", file=sys.stderr)
        return 1
    print("Next: run check_reviews.py N --panel-only, then the area-chair adjudication step.")
    return 0


def run_panel(args, root, directory):
    saved = None
    if directory.exists():
        if not args.resume:
            raise RoundError("Round already exists. Use --resume for unchanged inputs, or start a new round")
        if not (directory / "run.json").exists():
            raise RoundError("This is a legacy round without run metadata; start a new round instead of resuming")
        saved = read_run(directory)
    elif args.resume:
        raise RoundError("Round does not exist; omit --resume to start it")
    available = {p.stem: p for p in (root / ".claude/agents").glob("reviewer-*.md")}
    names = args.reviewers.split(",") if args.reviewers is not None else (
        saved["reviewers"] if saved else sorted(available))
    if not names or len(set(names)) != len(names) or any(n not in available for n in names):
        raise RoundError("Select existing reviewer-* personas once each; area-chair runs separately")
    names = sorted(names)
    backend = os.environ.get("BACKEND", saved["backend"] if saved else "claude")
    if backend not in {"claude", "codex", "grok"}:
        raise RoundError("BACKEND must be claude, codex, or grok")
    briefing = os.environ.get("BRIEFING", "1" if saved and saved.get("briefed") else "0")
    if briefing not in {"0", "1"}:
        raise RoundError("BRIEFING must be 0 or 1")
    workspace = load_workspace(root)
    executable = shutil.which(backend)
    if not executable:
        raise RoundError(f"Backend '{backend}' is not installed or not on PATH")
    version = subprocess.run([executable, "--version"], capture_output=True, timeout=30)
    if version.returncode:
        raise RoundError(f"Cannot read {backend} --version; fix the backend before starting a round")
    backend_version = (version.stdout + version.stderr).decode("utf-8", errors="replace").strip()
    project = root / "state/project.md"
    text = project.read_text(encoding="utf-8") if project.exists() else ""
    match = re.search(r"^- Venue:\s*(.*)$", text, re.MULTILINE)
    venue = match.group(1).split("(", 1)[0].strip() if match else ""
    personas = {n: available[n].read_text(encoding="utf-8") for n in names}
    with tempfile.TemporaryDirectory(prefix="paperforge-panel-") as temp:
        snapshot = Path(temp) / "snapshot"
        snapshot.mkdir()
        files = prepare_snapshot(workspace, snapshot, briefing == "1")
        inputs = {"files": files, "layout": workspace.describe(), "venue": venue,
                  "personas": {n: digest(personas[n].encode("utf-8")) for n in names},
                  "backend": backend, "backend_version": backend_version, "briefed": briefing == "1"}
        fingerprint = digest(json.dumps(inputs, sort_keys=True).encode("utf-8"))
        if saved:
            if saved.get("input_fingerprint") != fingerprint:
                raise RoundError("Panel inputs or backend changed; start a new round")
            for name in names:
                if saved["runs"][name].get("status") == "complete":
                    single = dict(saved, reviewers=[name])
                    completed_reviews(directory, single)
            run = saved
        else:
            directory.mkdir()
            run = {"schema_version": 1, "round": args.round, "backend": backend,
                   "backend_version": backend_version, "briefed": briefing == "1",
                   "reviewers": names, "inputs": inputs, "input_fingerprint": fingerprint,
                   "runs": {n: {"status": "pending", "attempts": 0} for n in names}}
            (directory / "backend-version.txt").write_text(backend_version + "\n", encoding="utf-8")
        run["jobs"] = args.jobs
        save_run(directory, run)
        main_path = "manuscript/" + workspace.main_tex.relative_to(workspace.source_root).as_posix()
        task = (f"\n\nRead only the paper snapshot under manuscript/. Main document: {main_path}. "
                f"Target venue: {venue or 'unspecified'}. Write your complete review in the required format. "
                "Output only the review.")
        if briefing == "1":
            task += " A briefing/ folder contains source-verified summaries; you may read it. Label the review briefed."
        prompts = {n: re.sub(r"\A---\r?\n.*?\r?\n---\r?\n", "", personas[n], count=1, flags=re.DOTALL)
                   + task for n in names}
        return execute(directory, run, snapshot, prompts, executable, args.jobs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("round", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reviewers", help="comma-separated full reviewer persona names")
    parser.add_argument("--jobs", type=int, default=1, help="maximum concurrent reviewers (default: 1)")
    args = parser.parse_args()
    if args.round < 1 or args.jobs < 1:
        parser.error("round and --jobs must be positive integers")
    root = Path.cwd().resolve()
    parent = root / "state/reviews"
    try:
        if not (root / "state").is_dir():
            raise RoundError("Run from the paper workspace root (state/ not found)")
        parent.mkdir(parents=True, exist_ok=True)
        with round_lock(parent / f".round-{args.round}.lock"):
            return run_panel(args, root, parent / f"round-{args.round}")
    except (RoundError, WorkspaceError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
