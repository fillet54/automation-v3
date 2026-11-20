"""PNG and PDF from a rendered (light, literal-colour) SVG, with novasvg: ``pip install mermaid-diag[png]``.

novasvg draws with the same IBM Plex files the text was measured with. The PDF is one page the size of the
diagram holding the picture at `scale` times its CSS-pixel size (novasvg has no vector PDF output).
"""

from __future__ import annotations

import zlib
from functools import lru_cache
from pathlib import Path

FONTS = Path(__file__).resolve().parent / "fonts"

# novasvg knows a face only as regular/bold and upright/italic.
_FACES = [
    ("IBM Plex Sans", False, False, "IBMPlexSans-Regular.ttf"),
    ("IBM Plex Sans", True, False, "IBMPlexSans-Bold.ttf"),
    ("IBM Plex Sans", False, True, "IBMPlexSans-Italic.ttf"),
    ("IBM Plex Mono", False, False, "IBMPlexMono-Regular.ttf"),
    ("IBM Plex Mono", True, False, "IBMPlexMono-SemiBold.ttf"),
    ("IBM Plex Serif", False, False, "IBMPlexSerif-Regular.ttf"),
    ("IBM Plex Serif", True, False, "IBMPlexSerif-SemiBold.ttf"),
]


class RasterUnavailable(RuntimeError):
    """novasvg isn't installed: PNG and PDF output need ``pip install mermaid-diag[png]``."""


@lru_cache(maxsize=1)
def _novasvg():
    try:
        import novasvg
        import novasvg.fonts as fonts
    except ImportError:
        raise RasterUnavailable("PNG and PDF output need novasvg: pip install mermaid-diag[png]") from None
    for family, bold, italic, name in _FACES:
        fonts.add_font_face_from_file(family, bold, italic, str(FONTS / name))
    from . import cjk
    cjk.register_with_novasvg(fonts)
    return novasvg


def to_bitmap(svg: str, scale: float = 2.0, background: str | None = None):
    novasvg = _novasvg()
    doc = novasvg.Document.load_from_data(svg)
    width, height = max(1, round(doc.width * scale)), max(1, round(doc.height * scale))
    if width * height > 400_000_000:
        raise ValueError(f"the diagram is too large for a picture ({width}x{height} px at scale {scale:g})")
    bg = 0
    if background:
        text = background.strip()
        color = novasvg.Color.from_hash(text) if text.startswith("#") else novasvg.Color.from_name(text.lower())
        bg = color.to_int()
    bitmap = doc.render_to_bitmap(width, height, bg)
    if bitmap.is_null():
        raise ValueError(f"novasvg could not make a {width}x{height} px picture")
    return bitmap, doc.width, doc.height


def to_png(svg: str, scale: float = 2.0, background: str | None = None) -> bytes:
    bitmap, _, _ = to_bitmap(svg, scale, background)
    return bitmap.to_bytes("png")


def to_pdf(svg: str, scale: float = 3.0, background: str | None = None) -> bytes:
    bitmap, css_w, css_h = to_bitmap(svg, scale, background)
    converted = bitmap.convert_to_rgba()
    if converted is not None:
        bitmap = converted
    raw = bitmap.tobytes()
    w, h, stride = bitmap.width, bitmap.height, bitmap.stride
    if stride != w * 4:
        raw = b"".join(raw[y * stride:y * stride + w * 4] for y in range(h))
    return _pdf(w, h, css_w * 0.75, css_h * 0.75, zlib.compress(_rgb(raw), 6), zlib.compress(raw[3::4], 6))


def _rgb(row: bytes) -> bytes:
    out = bytearray(len(row) // 4 * 3)
    out[0::3], out[1::3], out[2::3] = row[0::4], row[1::4], row[2::4]
    return bytes(out)


def _pdf(w: int, h: int, page_w: float, page_h: float, rgb: bytes, alpha: bytes) -> bytes:
    content = f"q {page_w:.3f} 0 0 {page_h:.3f} 0 0 cm /Im0 Do Q".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w:.3f} {page_h:.3f}] "
        f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 6 0 R >>".encode(),
        (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB /BitsPerComponent 8 "
         f"/Filter /FlateDecode /SMask 5 0 R /Length {len(rgb)} >>\nstream\n").encode() + rgb + b"\nendstream",
        (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceGray /BitsPerComponent 8 "
         f"/Filter /FlateDecode /Length {len(alpha)} >>\nstream\n").encode() + alpha + b"\nendstream",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)

