# Host setup details

Install through explicit invocation only. The helper actions are `check`,
`install`, and `verify`; omitted action means `check`. `install` configures the
host; `verify` performs separate compiler tests. The skill runs both in order.
Failures return nonzero; `check` returns an inventory even when tools are missing.
No helper upgrades the whole operating system or removes packages.

Ubuntu dependencies: `latexmk`, `texlive-latex-extra`,
`texlive-fonts-recommended`, `texlive-science`, `texlive-xetex`, `biber`,
`poppler-utils`, and `python3`. The Bash entry point bootstraps missing Python
through the same terminal authentication path. VS Code installation additionally
needs `ca-certificates`, `curl`, and `gpg` and uses Microsoft's signed stable apt
repository. Supported Code package architectures are amd64, arm64, and armhf.
Use versions available on that host; report versions rather than claiming an
exact historical setup was reproduced.

Existing `code` is reused. Settings default to
`${XDG_CONFIG_HOME:-$HOME/.config}/Code/User/settings.json`; portable mode uses
`$VSCODE_PORTABLE/user-data/User/settings.json`. The helper configures the default
profile only. Named profiles, remote Code servers, VSCodium, and Insiders need
an explicit adaptation; do not install a second editor as an accidental fallback.
`--settings` selects a settings file, not a Code extension profile.

Only these user settings are changed: `latex-workshop.latex.autoBuild.run` to
`onFileChange` and `latex-workshop.view.pdf.viewer` to `tab`. JSONC comments,
trailing commas, unrelated values, and existing file permissions are preserved.
Changed existing files get timestamped `.paperforge-backup-...` siblings. Invalid
or duplicate-key JSONC and symlink targets are refused before installation.
An unchanged rerun creates no extra settings backup. Restore a backup only when
requested, after checking for newer user edits.

Authentication goes directly to sudo in a terminal. Logs contain package output,
not the password. Each install/verify action prints a new run directory; keep it
until the user has reviewed its reports and sample. To retain evidence across
reboots, pass `--run-dir` with a new user-owned directory. A failed install keeps
successful package operations; rerun to inspect and complete the missing pieces.
Inspect errors before changing apt repositories or removing conflicting tools.
If an interrupted Code repository creation left a partial key/source pair,
inspect those named files rather than deleting unrelated repository configuration.

Sources: [VS Code on Linux](https://code.visualstudio.com/docs/setup/linux),
[Code CLI](https://code.visualstudio.com/docs/configure/command-line),
[LaTeX Workshop installation](https://github.com/James-Yu/LaTeX-Workshop/wiki/Install).
