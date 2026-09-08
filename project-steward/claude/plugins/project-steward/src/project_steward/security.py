"""Secret detection for committed steward files.

`doctor` is the only caller. Risky-command policy lives in the agent
skills, not here: see references/security-model.md.
"""
from __future__ import annotations

import re

SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"ghp_[A-Za-z0-9]{36,}"), "GitHub personal access token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained token"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "API secret key (sk-...)"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"),
     "hard-coded credential assignment"),
]

# Only the generic assignment pattern above may be downgraded when the
# value is an obvious placeholder; structured tokens (AKIA/ghp_/...) never.
_DOWNGRADABLE_LABEL = "hard-coded credential assignment"
PLACEHOLDER_HINT_RE = re.compile(
    r"(?i)(changeme|placeholder|example|sample|dummy|redacted|"
    r"your[-_]|x{4,}|\$\{|<[^>]+>)")

def scan_text_for_secrets(text, origin=""):
    findings = []
    for pattern, label in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            snippet = match.group(0)
            findings.append({
                "origin": origin,
                "label": label,
                "sample": snippet[:6] + "..." if len(snippet) > 9 else "***",
                "placeholder": (label == _DOWNGRADABLE_LABEL
                                and bool(PLACEHOLDER_HINT_RE.search(snippet))),
            })
    return findings
