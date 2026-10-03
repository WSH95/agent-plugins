"""Recognize enabled binary Code repositories in apt's actual source files."""
from __future__ import annotations

from pathlib import Path
import re
import sys

URI = "https://packages.microsoft.com/repos/code"


def has_code_repository(apt_dir):
    apt_dir = Path(apt_dir)
    files = [apt_dir / "sources.list"]
    parts = apt_dir / "sources.list.d"
    if parts.is_dir():
        # Apt ignores backup files and names containing characters outside this set.
        files.extend(p for p in parts.iterdir()
                     if re.fullmatch(r"[A-Za-z0-9_.-]+\.(?:list|sources)", p.name))
    for path in files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".list":
            for line in text.splitlines():
                match = re.match(r"^\s*deb\s+(?:\[[^\]]*\]\s+)?(\S+)", line)
                if match and match.group(1).rstrip("/") == URI:
                    return True
        else:
            for stanza in re.split(r"\n\s*\n", text):
                fields, key = {}, None
                for line in stanza.splitlines():
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue
                    if line[:1].isspace() and key:
                        fields[key] += " " + line.strip()
                    elif ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        fields[key] = value.strip()
                if (fields.get("enabled", "yes").lower() != "no"
                        and "deb" in fields.get("types", "").split()
                        and URI in [u.rstrip("/") for u in fields.get("uris", "").split()]):
                    return True
    return False


if __name__ == "__main__":
    try:
        sys.exit(0 if has_code_repository(Path("/etc/apt")) else 1)
    except (OSError, ValueError) as error:
        print("Cannot inspect apt sources: " + str(error), file=sys.stderr)
        sys.exit(2)
