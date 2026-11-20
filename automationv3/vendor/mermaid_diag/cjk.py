"""East Asian text and emoji in PNG and PDF output.

HTML and SVG output need nothing here: the reader's browser draws those characters with its own fonts, and the
layout already allows for them (metrics.js sizes them like Noto Sans CJK and Noto Color Emoji).

novasvg, which draws PNGs and PDFs, has no per-character font fallback, and doesn't switch fonts inside HTML labels.
So a diagram with characters the IBM Plex fonts lack is rendered for pictures with SVG-text labels, and every run of
such characters is wrapped in a <tspan> that names a fallback font: "MD CJK" or "MD Emoji".

The fallback fonts come from, in order:

1. MERMAID_DIAG_CJK_FONT / MERMAID_DIAG_EMOJI_FONT (paths),
2. the mermaid-diag-cjk package (``pip install mermaid-diag[cjk]``): Noto Sans CJK SC and Noto Emoji,
3. fonts installed on the system (Noto CJK on Linux; Microsoft YaHei, Malgun Gothic, Segoe UI Emoji on Windows).
"""

from __future__ import annotations

import glob
import json
import os
import re
from functools import lru_cache
from pathlib import Path

FONTS = Path(__file__).resolve().parent / "fonts"
CJK_FAMILY = "MD CJK"
EMOJI_FAMILY = "MD Emoji"

_SYSTEM_CJK = [
    "/usr/share/fonts/**/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/**/NotoSansCJK*-Regular.otf",
    "/usr/share/fonts/**/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/**/wqy-microhei.ttc",
    "/usr/share/fonts/**/wqy-zenhei.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/YuGothR.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/malgun.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]
_SYSTEM_EMOJI = [
    "/usr/share/fonts/**/NotoEmoji-Regular.ttf",
    "/usr/share/fonts/**/NotoEmoji*.ttf",
    "/usr/share/fonts/**/Symbola*.ttf",
    "C:/Windows/Fonts/seguiemj.ttf",
    "C:/Windows/Fonts/seguisym.ttf",
]


def _first(patterns: list[str]) -> str | None:
    for pattern in patterns:
        windows = os.environ.get("WINDIR")
        if windows and pattern.startswith("C:/Windows"):
            pattern = windows.replace("\\", "/") + pattern[len("C:/Windows"):]
        for path in sorted(glob.glob(pattern, recursive=True)):
            if "Color" not in Path(path).name:   # colour bitmap fonts can't be drawn by novasvg
                return path
    return None


@lru_cache(maxsize=1)
def fallback_fonts() -> dict[str, tuple[str, str] | None]:
    """{"cjk": (path, where from) or None, "emoji": ...}."""
    found: dict[str, tuple[str, str] | None] = {"cjk": None, "emoji": None}
    for key, env in (("cjk", "MERMAID_DIAG_CJK_FONT"), ("emoji", "MERMAID_DIAG_EMOJI_FONT")):
        if os.environ.get(env) and Path(os.environ[env]).is_file():
            found[key] = (os.environ[env], env)
    try:
        import mermaid_diag_cjk
        for key, path in mermaid_diag_cjk.FONTS.items():
            if found.get(key) is None and Path(path).is_file():
                found[key] = (str(path), "mermaid-diag-cjk")
    except ImportError:
        pass
    if found["cjk"] is None:
        path = _first(_SYSTEM_CJK)
        found["cjk"] = (path, "system") if path else None
    if found["emoji"] is None:
        path = _first(_SYSTEM_EMOJI)
        found["emoji"] = (path, "system") if path else None
    return found


def describe() -> str:
    parts = []
    for key, value in fallback_fonts().items():
        parts.append(f"{key}: {value[0]} ({value[1]})" if value else f"{key}: none (pip install mermaid-diag[cjk])")
    return "; ".join(parts)


def register_with_novasvg(fonts) -> None:
    for key, family in (("cjk", CJK_FAMILY), ("emoji", EMOJI_FAMILY)):
        found = fallback_fonts()[key]
        if found:
            for bold in (False, True):
                fonts.add_font_face_from_file(family, bold, False, found[0])


@lru_cache(maxsize=1)
def _plex_codepoints() -> frozenset[int]:
    data = json.loads((FONTS / "fonts.json").read_text(encoding="utf-8"))
    cps: set[int] = set()
    for start, values in data["faces"]["sans-400"]["advances"]:
        cps.update(range(start, start + len(values)))
    return frozenset(cps)


def _is_emoji(cp: int) -> bool:
    return (0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF or 0x2300 <= cp <= 0x23FF
            or cp in (0xFE0F, 0x200D) or 0x1F3FB <= cp <= 0x1F3FF or 0xE0020 <= cp <= 0xE007F)


def needs_fallback(text: str) -> bool:
    """Whether the text has characters the Plex fonts lack (beyond spaces and controls)."""
    plex = _plex_codepoints()
    return any(ord(ch) not in plex and not ch.isspace() and ord(ch) >= 0x20 for ch in text)


def _family_for(ch: str) -> str | None:
    cp = ord(ch)
    if cp in _plex_codepoints() or ch.isspace():
        return None
    return EMOJI_FAMILY if _is_emoji(cp) else CJK_FAMILY


def _wrap_text(text: str) -> str:
    out, run, run_family = [], "", None
    for ch in re.findall(r"&[#\w]+;|.", text, re.S):
        if ch.startswith("&") and len(ch) > 1:
            decoded = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}.get(ch)
            family = _family_for(decoded) if decoded else None
        else:
            family = _family_for(ch)
        if family != run_family and run:
            out.append(f'<tspan font-family="{run_family}">{run}</tspan>' if run_family else run)
            run = ""
        run_family = family
        run += ch
    if run:
        out.append(f'<tspan font-family="{run_family}">{run}</tspan>' if run_family else run)
    return "".join(out)


def wrap_runs(svg: str) -> str:
    """Every run of characters Plex lacks, inside <text> elements, wrapped in a <tspan> naming a fallback font."""
    def text_element(m: re.Match) -> str:
        parts = re.split(r"(<[^>]+>)", m[0])
        return "".join(p if p.startswith("<") else _wrap_text(p) for p in parts)
    return re.sub(r"<text\b[^>]*>.*?</text>", text_element, svg, flags=re.S)
