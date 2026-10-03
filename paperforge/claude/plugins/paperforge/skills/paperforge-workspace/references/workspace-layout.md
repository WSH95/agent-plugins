# Confirmed paper files

Use this when adopting a nonstandard layout or changing which files belong to
an existing paper. `state/workspace.json` is optional for the conventional
`manuscript/main.tex` + `manuscript/refs.bib` layout. It is author-owned state:
reuse an existing mapping and preserve it on re-adoption or refresh.

Inspect the project and show the author a short table: purpose → existing path.
Include the main document, all bibliographies, sections, figures, and local
styles/macros needed to read or build the paper. Get confirmation once, then save:

```json
{
  "main_tex": "paper.tex",
  "bibliographies": ["library.bib"],
  "paper_paths": ["chapters", "figures", "localstyle.sty"]
}
```

- All three fields are required. Paths are relative to the workspace root.
- `main_tex` names one existing `.tex` file; `bibliographies` lists existing
  `.bib` files (an empty list is allowed for a paper without a bibliography).
- `paper_paths` lists additional files or directories, recursively. An empty
  list is valid for a single-file paper. Main and bibliography files are included
  automatically. List exact paths, not globs or the entire workspace (`.`).
- Use regular files inside the workspace. Private `state/`, `evidence/`, and
  agent/git directories do not belong in the paper bundle. Keep lab notes outside
  the selected directories. Build debris and the main document's generated PDF
  are omitted from directory expansion; figure PDFs remain included.

Run `python3 scripts/workspace.py show` to validate and inspect the expanded
inventory. Correct missing or ambiguous paths with the author before checking,
exporting context, building, or reviewing. Record the confirmed mapping in
`state/decisions.md` and point to it in the adopted-repository note in
`state/project.md`. The existing constitution's adopted-layout rule applies.

Workflow paths such as `manuscript/sections/` and `manuscript/refs.bib` then refer
to their mapped counterparts. Work in the existing files. When an outline adds
a file inside an approved directory, it is included automatically; changes to
the main document, bibliography list, or selected directories need an updated
confirmed mapping. This is a file inventory, not a LaTeX dependency parser.

Direct commands, including with an author-owned Makefile:

```bash
python3 scripts/check_paper.py
python3 scripts/context_packet.py --section introduction
python3 scripts/workspace.py pdf
python3 scripts/workspace.py clean
```

The shipped Makefile delegates to these commands. For older workspaces missing
the resolver, refresh `scripts/` from the updated toolkit first, keeping backups;
refresh the Makefile only if it is the shipped one. Do not replace an author's
custom build rules to enable Paperforge checks.
