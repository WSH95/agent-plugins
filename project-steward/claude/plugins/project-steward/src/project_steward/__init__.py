"""Project Steward: cross-agent project stewardship toolkit.

Durable, repo-resident project memory for Claude Code, Codex, and other
coding agents. Python 3.7+ compatible, standard library only.
"""

__version__ = "0.5.0"
PRODUCT_NAME = "Project Steward"
STATE_DIR_NAME = ".project-steward"
BLOCK_PREFIX = "PROJECT-STEWARD"


class StewardError(Exception):
    """A durable state file could not be read or would be destroyed.

    Raised by CLI-reachable paths only. Hooks never reach these paths, so
    the "hooks never fail loudly" contract is unaffected.
    """
