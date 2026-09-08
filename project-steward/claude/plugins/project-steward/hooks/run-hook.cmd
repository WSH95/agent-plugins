: << 'CMDBLOCK'
@echo off
REM Cross-platform polyglot hook wrapper for the Project Steward plugin.
REM cmd.exe (reached from PowerShell or cmd on Windows) runs this batch
REM section; POSIX shells (Linux/macOS, and Git Bash on Windows) treat the
REM first line as a no-op heredoc that swallows the batch section and run
REM the shell section at the bottom instead.
REM
REM Each candidate is PROBED with `--probe` before the real run, and the
REM real run happens exactly once. Retrying after the launcher has written
REM to stdout would concatenate two JSON documents and break the agent's
REM hook parser. The probe's own output is discarded; the real run's
REM stderr is left alone so genuine failures stay diagnosable.
REM
REM The probe is what rejects the Microsoft Store `python` alias: `where`
REM finds it, but it prints to stdout and exits non-zero, so it never
REM reaches the real run and never contaminates the hook's stdout.
REM
REM Hooks must never break the agent loop: exit 0 in every case.

REM `call` returns from .cmd/.bat shims (plain invocation never comes
REM back); `if not errorlevel 1` reads the exit code at run time —
REM %ERRORLEVEL% inside a parenthesized block expands at parse time.

where py >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call py -3 "%~dp0..\bin\project-steward" --probe >nul 2>nul
    if not errorlevel 1 (
        call py -3 "%~dp0..\bin\project-steward" %*
        exit /b 0
    )
)
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call python "%~dp0..\bin\project-steward" --probe >nul 2>nul
    if not errorlevel 1 (
        call python "%~dp0..\bin\project-steward" %*
        exit /b 0
    )
)
where project-steward >nul 2>nul
if %ERRORLEVEL% equ 0 (
    call project-steward --probe >nul 2>nul
    if not errorlevel 1 (
        call project-steward %*
        exit /b 0
    )
)
exit /b 0
CMDBLOCK

# POSIX: probe the bundled launcher, then run it exactly once.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCHER="$SCRIPT_DIR/../bin/project-steward"
for PY in python3 python py; do
    command -v "$PY" >/dev/null 2>&1 || continue
    "$PY" "$LAUNCHER" --probe >/dev/null 2>&1 || continue
    "$PY" "$LAUNCHER" "$@"
    exit 0
done
if command -v project-steward >/dev/null 2>&1 \
        && project-steward --probe >/dev/null 2>&1; then
    project-steward "$@"
fi
exit 0
