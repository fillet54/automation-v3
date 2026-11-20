# Vendored libraries

Copied in whole, so `pip install` of automation-v3 needs no sibling
checkout. Change them where they come from, then copy them in again;
don't edit them here.

## paper_ui

The engineering tools' shared look (stylesheet, Jinja components, Flask
glue, the "paper" Sphinx theme, IBM Plex fonts), from the paper-ui
repository at commit `35b3cc1`. Its third-party material is listed in
`paper_ui/NOTICE.md`.

Imported as `automationv3.vendor.paper_ui`. Its Flask blueprint is still
named `paper_ui` (static files at `/paper-ui/static`), and Sphinx gets its
"paper" theme from the extension `automationv3.vendor.paper_ui.sphinx`
(docs/conf.py lists it) rather than from an installed package's entry
point.

To update it from a paper-ui checkout beside this one:

```sh
rsync -a --delete --exclude __pycache__ --exclude NOTICE.md \
    ../paper-ui/src/paper_ui/ automationv3/vendor/paper_ui/
git -C ../paper-ui rev-parse --short HEAD   # the commit, for the line above
```

and bring `paper_ui/NOTICE.md` up to date with paper-ui's own if its
third-party material changed.

## mermaid_diag

Build-time Mermaid 12 diagrams (the docs' `.. mermaid::`), from the
mermaid-diag repository at commit `251f605`. Its third-party material
(Mermaid, mermaidx's headless DOM, IBM Plex) is listed in
`mermaid_diag/NOTICE.md`.

Imported as `automationv3.vendor.mermaid_diag`; docs/conf.py loads the
extension `automationv3.vendor.mermaid_diag.sphinx`. It runs Mermaid in
Node (22.12 or later) when that's on PATH, otherwise in QuickJS, which
needs `quickjs-ng` (the `docs` extra).

To update it from a mermaid-diag checkout beside this one:

```sh
rsync -a --delete --exclude __pycache__ --exclude NOTICE.md \
    ../mermaid-diag/src/mermaid_diag/ automationv3/vendor/mermaid_diag/
git -C ../mermaid-diag rev-parse --short HEAD   # the commit, for the line above
```

and bring `mermaid_diag/NOTICE.md` up to date with mermaid-diag's own if
its third-party material changed.
