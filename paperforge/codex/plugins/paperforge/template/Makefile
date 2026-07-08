# Build and quality targets for the paper workspace.

.PHONY: pdf clean check

pdf:
	@command -v latexmk >/dev/null 2>&1 || { \
	  echo "latexmk not found — install a TeX distribution (e.g. TeX Live) to build the PDF."; \
	  echo "Everything except PDF compilation works without LaTeX: 'make check' is the quality gate."; \
	  exit 1; }
	latexmk -pdf -cd manuscript/main.tex

clean:
	latexmk -C -cd manuscript/main.tex

check:
	python3 scripts/check_paper.py
