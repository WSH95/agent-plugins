# Preview sample

This is disposable synthetic content. Open this folder in VS Code, open
`main.tex`, and use **LaTeX Workshop: View LaTeX PDF file**. The chapter source
is `chapters/introduction.tex`; its first sentence is the refresh test marker.

Compilation uses `latexmk -pdf main.tex` (PDFLaTeX and Biber). In a separate
copy of this sample, use `latexmk -xelatex main.tex` to check XeLaTeX and Biber.
The verification helper also checks SyncTeX, bibliography, and equation links.

For reading the PDF while an agent edits source, first set this workspace's
`latex-workshop.latex.autoBuild.run` to `never`, then start in its terminal:

```bash
latexmk -pdf -pvc -view=none -synctex=1 -interaction=nonstopmode -halt-on-error main.tex
```

Keep that terminal running while reading. Stop with Ctrl+C and restore
`onFileChange` when returning to extension-managed builds. Run only one compiler
at a time. The setup verifier stops its own temporary watcher before returning.

To give precise writing feedback, quote the passage, name its section, describe
the desired change, and say what should be preserved. For example: “In Preview
verification, expand the sentence beginning ‘This included chapter’ to explain
why the equation matters. Keep the equation and citation unchanged.”
