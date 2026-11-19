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
