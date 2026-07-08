: << 'CMDBLOCK'
@echo off
REM Cross-platform polyglot hook wrapper for the Project Steward plugin.
REM cmd.exe (reached from PowerShell or cmd on Windows) runs this batch
REM section; POSIX shells (Linux/macOS, and Git Bash on Windows) treat the
REM first line as a no-op heredoc that swallows the batch section and run
REM the shell section at the bottom instead.
REM
REM All arguments pass through to the bundled pure-Python launcher at
REM ..\bin\project-steward, then fall back to an installed project-steward
REM console script. Hooks must never break the agent loop: with no Python
REM and no CLI available, exit 0 silently.

REM `call` returns from .cmd/.bat shims (plain invocation never comes
REM back); `if not errorlevel 1` reads the exit code at run time —
REM %ERRORLEVEL% inside a parenthesized block expands at parse time.

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call py -3 "%~dp0..\bin\project-steward" %*
    if not errorlevel 1 exit /b 0
)
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call python "%~dp0..\bin\project-steward" %*
    if not errorlevel 1 exit /b 0
)
where project-steward >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call project-steward %*
    if not errorlevel 1 exit /b 0
)
exit /b 0
CMDBLOCK

# POSIX: prefer the plugin-bundled launcher, then the installed CLI.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER="$SCRIPT_DIR/../bin/project-steward"
for PY in python3 python py; do
    if command -v "$PY" >/dev/null 2>&1; then
        "$PY" "$LAUNCHER" "$@" && exit 0
    fi
done
if command -v project-steward >/dev/null 2>&1; then
    project-steward "$@" && exit 0
fi
exit 0
