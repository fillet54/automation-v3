"""Specs as pages: each spec version built by Sphinx, once

A spec version's source tree is written out from the database and built
with Sphinx's dirhtml builder, using this package's configuration,
extension and theme (sphinx/), whose pages are JSON, in a separate process so its directives never meet
the importer's. The build is kept under the cache folder by the spec
version and RENDERER, so it is built on first view and never again;
changing how specs render means bumping RENDERER.

Each page comes back as {"title", "body", "prev", "next"}, for the
server to show in the site's own page.
"""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RENDERER = "3"
CONF = Path(__file__).resolve().parent / "sphinx"
PACKAGE_ROOT = Path(__file__).resolve().parents[3]


class RenderError(Exception):
    pass


def available():
    """Whether Sphinx is installed (it's the "docs" extra)"""
    return importlib.util.find_spec("sphinx") is not None


def build(conn, spec_version, cache):
    """The folder holding the build of `spec_version`, building it first
    if it isn't in `cache` yet. Raises RenderError if Sphinx is missing or
    the build fails."""
    out = Path(cache) / f"{spec_version}-r{RENDERER}"
    if (out / "nav.json").is_file():
        return out
    if not available():
        raise RenderError("Sphinx isn't installed: install it with pip install -e \".[docs]\"")
    row = conn.execute("SELECT tree FROM spec_versions WHERE hash = ?", (spec_version,)).fetchone()
    if row is None:
        raise RenderError(f"no spec version {spec_version}")
    Path(cache).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="build-", dir=cache))
    try:
        src = work / "src"
        for path, blob in json.loads(row["tree"]).items():
            target = src / path
            target.parent.mkdir(parents=True, exist_ok=True)
            content = conn.execute("SELECT content FROM blobs WHERE hash = ?", (blob,)).fetchone()
            target.write_bytes(content[0])
        env = {**os.environ,
               "PYTHONPATH": os.pathsep.join(filter(None, [str(PACKAGE_ROOT),
                                                           os.environ.get("PYTHONPATH")]))}
        result = subprocess.run(
            [sys.executable, "-m", "sphinx", "-b", "dirhtml", "-q", "-c", str(CONF),
             "-d", str(work / "doctrees"), str(src), str(work / "out")],
            capture_output=True, text=True, env=env)
        if result.returncode != 0 or not (work / "out" / "nav.json").is_file():
            raise RenderError("The spec didn't build:\n" + (result.stderr or result.stdout))
        try:
            os.replace(work / "out", out)
        except OSError:
            if not (out / "nav.json").is_file():  # not another build finishing first
                raise
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


def page(out, doc):
    """Document `doc` of a build ({"title", "body", "prev", "next"}), or None"""
    path = Path(out) / "index.html" if doc == "index" else Path(out) / doc / "index.html"
    if ".." in Path(doc).parts or doc.startswith("_") or not path.is_file():
        return None
    return json.loads(path.read_text())


def nav(out):
    return json.loads((Path(out) / "nav.json").read_text())
