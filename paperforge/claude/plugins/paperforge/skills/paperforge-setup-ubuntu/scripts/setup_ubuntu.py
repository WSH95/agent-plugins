"""Inspect/configure an explicitly requested local Ubuntu LaTeX environment."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile

import vscode_settings

SCRIPTS = Path(__file__).resolve().parent
PACKAGES = ("latexmk", "texlive-latex-extra", "texlive-fonts-recommended",
            "texlive-science", "texlive-xetex", "biber", "poppler-utils", "python3")
TEX_TOOLS = ("latexmk", "pdflatex", "xelatex", "biber")
EXTENSION = "James-Yu.latex-workshop"


def os_release():
    path = Path("/etc/os-release")
    data = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                parts = shlex.split(value)
                data[key] = parts[0] if parts else ""
    return data


def is_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


def settings_path():
    portable = os.environ.get("VSCODE_PORTABLE")
    if portable:
        return Path(portable) / "user-data/User/settings.json"
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return config / "Code/User/settings.json"


class Host:
    def __init__(self, settings):
        self.settings = Path(settings)

    def which(self, name):
        return shutil.which(name)

    def run(self, args, timeout=90):
        return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, timeout=timeout, check=False)

    def inspect(self):
        release = os_release()
        result = {"os": release, "supported": release.get("ID") == "ubuntu",
                  "settings": str(self.settings), "packages": {}, "missing_packages": [],
                  "tools": {}, "conflicts": [], "code": self.which("code"),
                  "extension": None, "alternative_editors": {},
                  "desktop": bool(os.environ.get("DISPLAY") or
                                                     os.environ.get("WAYLAND_DISPLAY"))}
        if not result["supported"]:
            return result
        for name in ("code-insiders", "codium"):
            path = self.which(name)
            if path:
                result["alternative_editors"][name] = path
        if not self.which("dpkg-query"):
            raise RuntimeError("Ubuntu dpkg-query is unavailable")
        for name in PACKAGES:
            proc = self.run(["dpkg-query", "-W", "-f=${Status}\t${Version}\n", name])
            installed = proc.returncode == 0 and proc.stdout.startswith("install ok installed\t")
            result["packages"][name] = proc.stdout.strip().split("\t")[-1] if installed else None
            if not installed:
                result["missing_packages"].append(name)
        for name in TEX_TOOLS:
            path = self.which(name)
            if path:
                if Path(os.path.realpath(path)).parent not in (
                        Path(os.path.realpath("/usr/bin")), Path(os.path.realpath("/bin"))):
                    result["conflicts"].append("TeX tool outside Ubuntu system paths: " + path)
                proc = self.run([path, "-v" if name == "latexmk" else "--version"])
                result["tools"][name] = {"path": path, "version": proc.stdout.splitlines()[:2],
                                         "ok": proc.returncode == 0}
        code = result["code"]
        if code:
            if "remote-cli" in code or ".vscode-server" in code:
                result["conflicts"].append("Use a local desktop Code CLI, not a remote server CLI")
            proc = self.run([code, "--version"])
            result["code_version"] = proc.stdout.splitlines()[:3]
            proc = self.run([code, "--list-extensions", "--show-versions"])
            if proc.returncode:
                raise RuntimeError("Cannot inspect Code extensions: " + proc.stderr.strip())
            for line in proc.stdout.splitlines():
                if line.lower().split("@")[0] == EXTENSION.lower():
                    result["extension"] = line.strip()
        return result

    def privileged(self, args, log):
        proc = subprocess.run(["bash", str(SCRIPTS / "privileged.sh"), str(log)] + args,
                              check=False)
        if proc.returncode:
            raise RuntimeError("Package installation/authentication failed (exit %d); see %s" %
                               (proc.returncode, log))

    def install(self, run_dir):
        state = self.inspect()
        if not state["supported"]:
            raise RuntimeError("Installation supports Ubuntu only")
        if is_root():
            raise RuntimeError("Run setup as the desktop user; only package operations use sudo")
        if state["conflicts"]:
            raise RuntimeError("; ".join(state["conflicts"]))
        if not state["code"] and state["alternative_editors"]:
            raise RuntimeError("An alternative Code editor is installed (%s); explicitly adapt it "
                               "or request stable Code before continuing" %
                               ", ".join(state["alternative_editors"]))
        vscode_settings.validate_path(self.settings)
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        missing = state["missing_packages"]
        if missing or not state["code"]:
            args = ["bash", str(SCRIPTS / "apt-install.sh")]
            if not state["code"]:
                args.append("--vscode")
            self.privileged(args + missing, run_dir / "packages.log")
        state = self.inspect()
        if state["missing_packages"] or not state["code"]:
            raise RuntimeError("Required tools remain missing after installation")
        if state["conflicts"]:
            raise RuntimeError("; ".join(state["conflicts"]))
        if not state["extension"]:
            proc = self.run([state["code"], "--install-extension", EXTENSION], timeout=300)
            (run_dir / "extension.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
            if proc.returncode:
                raise RuntimeError("LaTeX Workshop installation failed; see extension.log")
            state = self.inspect()
            if not state["extension"]:
                raise RuntimeError("LaTeX Workshop is still missing after installation")
        state["settings_update"] = vscode_settings.configure(self.settings)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", choices=("check", "install", "verify"), default="check")
    parser.add_argument("--settings", type=Path, default=settings_path(),
                        help="explicit default-profile settings target (JSONC)")
    parser.add_argument("--run-dir", type=Path, help="new directory for logs and verification samples")
    args = parser.parse_args()
    host = Host(args.settings)
    if args.action == "check":
        state = host.inspect()
        try:
            vscode_settings.validate_path(args.settings)
            state["settings_valid"] = True
        except (ValueError, OSError) as error:
            state["settings_valid"] = False
            state["settings_error"] = str(error)
        print(json.dumps(state, indent=2))
        return 0
    if args.run_dir:
        args.run_dir.mkdir(parents=True, exist_ok=False)
        run_dir = args.run_dir.resolve()
    else:
        run_dir = Path(tempfile.mkdtemp(prefix="paperforge-ubuntu-setup-"))
    report = {"action": args.action, "run_dir": str(run_dir), "status": "failed"}
    print("Setup logs/sample: " + str(run_dir), flush=True)
    try:
        if args.action == "install":
            report["host"] = host.install(run_dir)
        else:
            from verify_latex import verify
            report["host"] = host.inspect()
            if not report["host"]["supported"]:
                raise RuntimeError("Verification supports Ubuntu only")
            report["verification"] = verify(run_dir)
        report["status"] = "passed"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
        if (run_dir / "verification.json").is_file():
            report["verification"] = json.loads((run_dir / "verification.json").read_text(encoding="utf-8"))
    (run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print("Setup error: " + str(error), file=sys.stderr)
        sys.exit(1)
