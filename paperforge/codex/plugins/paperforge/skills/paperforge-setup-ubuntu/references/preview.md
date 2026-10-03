# Observe live preview

Use only the generated `preview-demo` directory, never a user's manuscript.
The helper's `verification.json` distinguishes compiler tests from UI checks;
its continuous rebuild pass is not a visible-refresh pass. Save additional
observations in `preview-observations.md` beside that report, with installed
extension version, focus state, marker, build outcome, viewer outcome, and
log/screenshot paths. Do not relabel a helper field without observed evidence.

1. Open the generated folder in the local VS Code installation with
   `code --new-window "<run-dir>/preview-demo"`, then its `main.tex` and the
   LaTeX Workshop PDF preview. Trust only this known generated sample if VS Code
   requests workspace trust. Inspect the actual extension/compiler output logs.
   Discover current log paths and viewer URLs from that instance; never reuse
   another machine's ports, encoded file URLs, or window numbers.
2. Save the exact bytes of `chapters/introduction.tex` and workspace settings.
   With a source editor active, replace `Paperforge preview baseline.` on disk
   with a unique visible marker. Verify an automatic build completes, the PDF's
   extracted text contains the marker, and the already-open viewer displays it
   without a manual rebuild, reload, or reopen. Restore the source and observe
   the reverse transition.
3. Repeat with the PDF tab active. In LaTeX Workshop 10.19.0 we observed
   `active editor is undefined`, preventing extension builds in this state.
   This is version-specific evidence, not an assumption about future versions.
   Use UI tools if available; a browser attached to the extension's own local
   viewer can check refresh, but does not establish native VS Code focus.
   If focus cannot be controlled/observed, label that part `unverified`.
4. When PDF-active extension builds fail, or to verify the fallback, set this
   sample workspace's `latex-workshop.latex.autoBuild.run` to `never`, wait for
   any current build to finish, and start:

   ```bash
   latexmk -pdf -pvc -view=none -synctex=1 -interaction=nonstopmode -halt-on-error main.tex
   ```

   Run it from the sample directory in an identifiable terminal/process you
   own. Repeat the marker test with the PDF active. One compiler owns the
   outputs at a time: never leave extension auto-build and `-pvc` competing.
   Observe the existing viewer changing; don't infer refresh from timestamps.
5. Restore source bytes while the watcher is still running and confirm the PDF
   returns to baseline. Stop only your watcher and its compiler children, then
   restore the workspace preferences. Check the final source, PDF, and process
   state. Restore preferences/source even after test failures; if rebuilding
   the restored PDF fails, report that instead of leaving a false success.

For actual writing, the user can keep the continuous compiler running in a
terminal while reading the PDF, with extension auto-build disabled for that
workspace. Explain Ctrl+C to stop and restore `onFileChange` when returning to
extension-managed builds. Do not install a background service or change an
existing paper's workspace configuration as part of the host verification.

If UI access is unavailable, complete compiler tests yourself and provide the
generated sample plus the exact unverified steps. A report can say compilation
and continuous rebuilding passed while visible refresh remains unverified.

Sources: [Workshop compilation](https://github.com/James-Yu/LaTeX-Workshop/wiki/Compile),
[Workshop PDF viewer](https://github.com/James-Yu/LaTeX-Workshop/wiki/View).
