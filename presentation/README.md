# The automation-v3 decks

Two reveal.js presentations:

- `overview.html`, the short one: the problem, from line-based scripts to
  forms (typed arguments, `def`, `defn`), scripts and runs as rendered in
  the app (each page whole, then cropped up close), and organizing tests
  by requirements.
- `index.html`, the detailed one: the concepts (scripts, blocks,
refs, UUTs, environments, variations, preconditions, outcomes, run
identity) and the main workflows in the app (the workspace and editor, the
console, scratch runs, requirements, queuing, reports, runs, requirement
changes and suspects, deployment).

Open either file in a browser. It loads reveal.js and the IBM Plex fonts
from CDNs, so it needs a network connection; everything else is in this
folder. Keys: arrows to move, **S** for speaker notes, **F** for full
screen, **Esc** for the overview.

`img/` holds screenshots of `automation-v3 demo`, and `descent.svg`, a
trajectory a landing run attached. The `ov-*` crops were taken with the
page zoomed (`document.documentElement.style.zoom`) so they stay sharp on
a slide. To refresh them, run the demo and take
them again at the same names.
