"""Compile the bundled fixture and verify continuous rebuilds, not UI refresh."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import vscode_settings

FIXTURE = Path(__file__).resolve().parents[1] / "assets/preview-demo"
BASELINE = "Paperforge preview baseline."
MARKER = "Paperforge automatic rebuild verified."


def pdf_text(path):
    proc = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                          timeout=15, check=False)
    if proc.returncode:
        raise RuntimeError("PDF text extraction failed: " + proc.stderr.strip())
    return " ".join(proc.stdout.split())


def check_pdf(directory):
    text = pdf_text(directory / "main.pdf")
    for marker in (BASELINE, "Equation (1.1)", "[1]", "Paperforge Bibliography Fixture"):
        if marker not in text:
            raise RuntimeError("PDF is missing expected content: " + marker)
    sync = directory / "main.synctex.gz"
    if not sync.is_file() or sync.stat().st_size == 0:
        raise RuntimeError("SyncTeX output is missing")
    log = (directory / "main.log").read_text(encoding="utf-8", errors="replace")
    if re.search(r"(?:undefined references|Citation .* undefined|Reference .* undefined|"
                 r"Rerun to get|Please \(re\)run Biber)", log, re.IGNORECASE):
        raise RuntimeError("Unresolved references/citations or a pending rerun in main.log")


def compile_sample(directory, engine, log, timeout=180):
    args = ["latexmk", "-" + engine, "-synctex=1", "-interaction=nonstopmode",
            "-halt-on-error", "main.tex"]
    with log.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(args, cwd=str(directory), stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        finally:
            stop_watcher(process)
    if code:
        raise RuntimeError("%s compilation failed; see %s" % (engine, log))
    check_pdf(directory)


def wait_for(predicate, process, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Continuous compiler exited before the rebuild completed")
        try:
            if predicate():
                return
        except (OSError, RuntimeError, subprocess.SubprocessError):
            # PDF can briefly be absent or incomplete while the compiler writes it.
            pass
        time.sleep(0.25)
    raise RuntimeError("Continuous compilation timed out")


def stop_watcher(process):
    # The process group includes a compiler/Biber child still active on failure.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def continuous_check(sample, log):
    chapter = sample / "chapters/introduction.tex"
    settings = sample / ".vscode/settings.json"
    original, preferences = chapter.read_bytes(), settings.read_bytes()
    process = None
    try:
        # Single build owner while the continuous compiler runs in this fixture.
        configured = vscode_settings.updated(preferences.decode("utf-8"),
                                            {"latex-workshop.latex.autoBuild.run": "never"})
        settings.write_text(configured, encoding="utf-8")
        with log.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(
                ["latexmk", "-e", "$|=1;", "-pdf", "-pvc", "-view=none", "-synctex=1",
                 "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                cwd=str(sample), stdout=stream, stderr=subprocess.STDOUT,
                start_new_session=True)
            wait_for(lambda: "Watching for updated files" in log.read_text(errors="replace"), process)
            chapter.write_bytes(original.replace(BASELINE.encode(), MARKER.encode()))
            wait_for(lambda: MARKER in pdf_text(sample / "main.pdf"), process)
            chapter.write_bytes(original)
            wait_for(lambda: BASELINE in pdf_text(sample / "main.pdf") and
                     MARKER not in pdf_text(sample / "main.pdf"), process)
    finally:
        try:
            if process is not None:
                stop_watcher(process)
        finally:
            chapter.write_bytes(original)
            settings.write_bytes(preferences)


def verify(run_dir):
    run_dir = Path(run_dir)
    report = {"status": "failed", "pdflatex_biber": "unverified",
              "xelatex_biber": "unverified", "continuous_rebuild": "unverified",
              "extension_rebuild_source_active": "unverified",
              "extension_rebuild_pdf_active": "unverified", "visible_refresh": "unverified",
              "test_edits_restored": False, "watcher_running": False}
    sample = run_dir / "preview-demo"
    try:
        missing = [tool for tool in ("latexmk", "pdflatex", "xelatex", "biber", "pdftotext")
                   if not shutil.which(tool)]
        if missing:
            raise RuntimeError("Missing verification tools: " + ", ".join(missing))
        shutil.copytree(FIXTURE, sample)
        xelatex = run_dir / "xelatex-check"
        shutil.copytree(FIXTURE, xelatex)
        compile_sample(sample, "pdf", run_dir / "pdflatex-build.log")
        report["pdflatex_biber"] = "passed"
        compile_sample(xelatex, "xelatex", run_dir / "xelatex-build.log")
        report["xelatex_biber"] = "passed"
        continuous_check(sample, run_dir / "continuous-build.log")
        check_pdf(sample)
        report["continuous_rebuild"] = "passed"
        report["status"] = "passed"
        report["pdf"] = str(sample / "main.pdf")
        report["note"] = "CLI checks passed. Follow references/preview.md to observe editor and viewer behavior."
        return report
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
        raise
    finally:
        if sample.exists():
            report["test_edits_restored"] = all(
                (sample / relative).read_bytes() == (FIXTURE / relative).read_bytes()
                for relative in ("chapters/introduction.tex", ".vscode/settings.json"))
        (run_dir / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
