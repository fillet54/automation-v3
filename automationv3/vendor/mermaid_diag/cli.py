"""Render Mermaid diagrams to SVG, PNG or PDF, with no browser.

Usage:
  mermaid-diag [options] INPUT...
  mermaid-diag --info
  mermaid-diag (-h | --help | -V | --version)

Examples:
  mermaid-diag flow.mmd                    # flow.svg next to it, following light and dark mode
  mermaid-diag flow.mmd -o flow.png        # format from the extension (svg, png, pdf)
  mermaid-diag *.mmd -d out -f pdf         # many diagrams into a folder
  cat flow.mmd | mermaid-diag - -o -       # stdin to stdout

Arguments:
  INPUT  Mermaid files, or - for stdin.

Options:
  -o FILE, --output FILE    Output file (one input), or - for stdout; default: INPUT
                            with the format's extension.
  -d DIR, --outdir DIR      Folder for the outputs (many inputs).
  -f FMT, --format FMT      Output format: svg, png or pdf (default: from -o, else svg).
  -t THEME, --theme THEME   auto: an SVG that follows light and dark mode (SVG default);
                            light or dark: one palette (PNG and PDF default to light).
  -c FILE, --config FILE    JSON file of Mermaid config to merge over the defaults.
  --layout NAME             Layout engine: elk (default), dagre, ...
  --theme-attribute ATTR    Root element attribute that forces a mode, e.g.
                            <html data-theme="dark"> [default: data-theme].
  --fonts MODE              SVG: embed the fonts it uses, or leave them to the page
                            (embed, none) [default: embed].
  --scale FACTOR            PNG/PDF resolution multiplier (default 2 / 3).
  -b COLOR, --background COLOR
                            PNG/PDF background colour (default transparent; 'paper'
                            for the theme's own).
  -e NAME, --engine NAME    JavaScript engine: auto, node or quickjs.
  --timeout SECONDS         Seconds one diagram may take.
  -q, --quiet               No progress messages.
  --info                    Show versions and engines, then exit.
  -h, --help                Show this help.
  -V, --version             Show the version.

Environment:
  MERMAID_DIAG_ENGINE (auto, node, quickjs), MERMAID_DIAG_NODE (path to node),
  MERMAID_DIAG_TIMEOUT (seconds).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

from docopt import DocoptExit, docopt

from . import MERMAID_VERSION, RenderError, __version__
from .api import diagram_id, picture_svg, render, render_mode

FORMATS = ("svg", "png", "pdf")
CHOICES = {
    "--format": FORMATS,
    "--theme": ("auto", "light", "dark"),
    "--fonts": ("embed", "none"),
    "--engine": ("auto", "node", "quickjs"),
}


class UsageError(Exception):
    """A bad command line: reported with the usage line, exit status 2."""


# Python 3.14 argparse's colours: \x1b[1;34m is bold blue, \x1b[36m cyan, and so on.
_HEADING, _PROG, _RESET = "\x1b[1;34m", "\x1b[1;35m", "\x1b[0m"
_SUMMARY = {"long": "\x1b[36m", "short": "\x1b[32m", "label": "\x1b[33m"}  # in the usage lines
_DETAIL = {"long": "\x1b[1;36m", "short": "\x1b[1;32m", "label": "\x1b[1;33m"}  # in the option list
_TOKEN = re.compile(r"(?<![\w-])(?P<long>--[\w-]+)|(?<![\w-])(?P<short>-\w)\b|\b(?P<label>[A-Z]{2,})\b")


def can_colorize(file) -> bool:
    """Colour only for a terminal, honouring PYTHON_COLORS, NO_COLOR, FORCE_COLOR and TERM=dumb like Python does."""
    if os.environ.get("PYTHON_COLORS") in ("0", "1"):
        return os.environ["PYTHON_COLORS"] == "1"
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("TERM") == "dumb":
        return False
    try:
        return file.isatty()
    except (AttributeError, ValueError):
        return False


def _paint_tokens(text: str, colours: dict[str, str]) -> str:
    return _TOKEN.sub(lambda m: f"{colours[m.lastgroup]}{m.group()}{_RESET}", text)


def colorize_help(text: str) -> str:
    """The docopt help text with argparse-style colours: headings, the program name, options and placeholders."""
    out, section = [], ""
    for line in text.splitlines():
        if re.fullmatch(r"[A-Z][\w ]*:", line):
            section = line[:-1].lower()
            out.append(f"{_HEADING}{line}{_RESET}")
            continue
        if section in ("usage", "examples") and (m := re.match(r"(.*?)(mermaid-diag)(.*)", line)):
            before, prog, rest = m.groups()
            if section == "usage":
                rest = _paint_tokens(rest, _SUMMARY)
            line = f"{before}{_PROG}{prog}{_RESET}{rest}"
        elif (m := re.match(r"( {1,4})(%s\S*(?: \S+)*)(.*)" % {"options": "-", "arguments": "[A-Z]"}.get(section, "$^"),
                            line)):  # an option or argument name, not a wrapped description line
            indent, names, rest = m.groups()
            line = indent + _paint_tokens(names, _DETAIL) + rest
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _usage() -> str:
    usage = __doc__[__doc__.index("Usage:"):__doc__.index("\n\n", __doc__.index("Usage:"))]
    return colorize_help(usage) if can_colorize(sys.stderr) else usage


def parse_args(argv: list[str] | None = None) -> SimpleNamespace:
    """The command line as attributes (inputs, output, outdir, format, ...); --help and --version exit."""
    args = sys.argv[1:] if argv is None else argv
    before_dashes = args[:args.index("--")] if "--" in args else args
    if "-h" in before_dashes or "--help" in before_dashes:
        print(colorize_help(__doc__) if can_colorize(sys.stdout) else __doc__, end="")
        sys.exit(0)
    raw = docopt(__doc__, args, default_help=False, version=f"mermaid-diag {__version__} (Mermaid {MERMAID_VERSION})")
    for opt, allowed in CHOICES.items():
        if raw[opt] is not None and raw[opt] not in allowed:
            raise UsageError(f"{opt} must be one of {', '.join(allowed)} (not {raw[opt]!r})")
    for opt in ("--scale", "--timeout"):
        if raw[opt] is not None:
            try:
                raw[opt] = float(raw[opt])
            except ValueError:
                raise UsageError(f"{opt} takes a number (not {raw[opt]!r})") from None
    return SimpleNamespace(
        inputs=raw["INPUT"],
        **{k.lstrip("-").replace("-", "_"): v for k, v in raw.items() if k.startswith("--")},
    )


def _info() -> int:
    from .engines import available_engines
    print(f"mermaid-diag {__version__}")
    print(f"Mermaid {MERMAID_VERSION}")
    for name, state in available_engines().items():
        print(f"engine {name}: {state}")
    try:
        import novasvg  # noqa: F401
        print("PNG/PDF: available (novasvg)")
    except ImportError:
        print("PNG/PDF: unavailable (pip install mermaid-diag[png])")
    from . import cjk
    print(f"CJK/emoji glyphs for PNG/PDF: {cjk.describe()}")
    return 0


def convert(source: str, fmt: str, args: SimpleNamespace, config: dict) -> bytes:
    theme = args.theme or ("auto" if fmt == "svg" else "light")
    common = dict(config=config, engine=args.engine, timeout=args.timeout)
    if fmt == "svg":
        if theme == "auto":
            svg = render(source, theme_attribute=args.theme_attribute, **common).svg
        else:
            svg = render_mode(source, theme, **common)
        if args.fonts == "embed":
            from .assets import embed_fonts
            svg = embed_fonts(svg)
        return svg.encode("utf-8")
    if theme == "auto":
        theme = "light"
    svg = picture_svg(source, theme, **common)
    background = args.background
    if background == "paper":
        from .theme import PALETTES
        background = PALETTES[theme]["paper"]
    from .raster import to_pdf, to_png
    if fmt == "png":
        return to_png(svg, args.scale or 2.0, background)
    return to_pdf(svg, args.scale or 3.0, background)


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(parse_args(argv))
    except DocoptExit:
        print(_usage(), file=sys.stderr)
        return 2
    except UsageError as e:
        print(_usage(), file=sys.stderr)
        print(f"mermaid-diag: {e}", file=sys.stderr)
        return 2


def _run(args: SimpleNamespace) -> int:
    if args.info:
        return _info()
    if args.output and len(args.inputs) > 1:
        raise UsageError("-o takes one input; use -d for many")

    config: dict = {}
    if args.config:
        try:
            config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise UsageError(f"can't read the config {args.config}: {e}") from None
    if args.layout:
        config["layout"] = args.layout

    fmt = args.format
    if not fmt and args.output and args.output != "-":
        ext = Path(args.output).suffix.lower().lstrip(".")
        fmt = ext if ext in FORMATS else None
        if not fmt:
            raise UsageError(f"can't tell the format from {args.output}; use -f")
    fmt = fmt or "svg"

    failures = 0
    for name in args.inputs:
        try:
            source = sys.stdin.read() if name == "-" else Path(name).read_text(encoding="utf-8")
        except OSError as e:
            print(f"{name}: {e.strerror or e}", file=sys.stderr)
            failures += 1
            continue
        try:
            data = convert(source, fmt, args, config)
        except RenderError as e:
            print(f"{name}: {e}", file=sys.stderr)
            failures += 1
            continue
        except Exception as e:  # noqa: BLE001 -- e.g. PNG without novasvg, a picture too large
            print(f"{name}: {e}", file=sys.stderr)
            failures += 1
            continue
        if args.output == "-" or (name == "-" and not args.output and not args.outdir):
            try:
                sys.stdout.buffer.write(data)
                sys.stdout.flush()
            except BrokenPipeError:  # e.g. piped into head
                import os
                os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
                return 0
            continue
        if args.output:
            out = Path(args.output)
        else:
            stem = Path(name).stem if name != "-" else diagram_id(source)
            folder = Path(args.outdir) if args.outdir else (Path(name).parent if name != "-" else Path("."))
            out = folder / f"{stem}.{fmt}"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        if not args.quiet:
            print(f"{name} -> {out}", file=sys.stderr)
    from .engines import close_engines
    close_engines()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
