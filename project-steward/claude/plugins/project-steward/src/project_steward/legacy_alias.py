"""Deprecated `projectforge` console alias: warn and delegate."""
from __future__ import annotations

import sys

from .cli import main as steward_main


def main(argv=None):
    sys.stderr.write(
        "warning: `projectforge` is deprecated; the tool is now "
        "`project-steward`. Delegating...\n"
    )
    return steward_main(argv)


if __name__ == "__main__":
    sys.exit(main())
