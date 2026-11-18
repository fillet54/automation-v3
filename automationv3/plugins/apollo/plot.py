"""The descent as an SVG: altitude against downrange, with the throttle
underneath. Drawn by hand, so it needs no plotting library."""

from html import escape

W, H = 720, 420
PAD_L, PAD_R, PAD_T = 64, 16, 36
ALT_H, GAP, THR_H = 230, 40, 80


def _scale(lo, hi, a, b):
    span = (hi - lo) or 1.0
    return lambda v: a + (v - lo) / span * (b - a)


def _ticks(lo, hi, count=5):
    step = (hi - lo) / count if hi > lo else 1.0
    return [lo + i * step for i in range(count + 1)]


def _polyline(points, colour, width=2):
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return (f'<polyline fill="none" stroke="{colour}" stroke-width="{width}" '
            f'stroke-linejoin="round" points="{path}"/>')


def trajectory_svg(rows, title="descent"):
    """rows: [t, x, h, vx, vz, throttle %, program, propellant], one a second"""
    if not rows:
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="60">'
                f'<text x="10" y="30">No trajectory recorded</text></svg>')
    xs = [r[1] / 1000 for r in rows]
    hs = [r[2] / 1000 for r in rows]
    ts = [r[0] for r in rows]
    x0, x1 = min(xs), max(max(xs), 0.0)
    sx = _scale(x0, x1, PAD_L, W - PAD_R)
    sh = _scale(0, max(hs) or 1.0, PAD_T + ALT_H, PAD_T)
    st = _scale(min(ts), max(ts), PAD_L, W - PAD_R)
    top = PAD_T + ALT_H + GAP
    sthr = _scale(0, 100, top + THR_H, top)
    ink, grid, accent, warm = "#1f2933", "#d9dee3", "#2563eb", "#c2410c"
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
           f'height="{H}" font-family="sans-serif" font-size="11" fill="{ink}">',
           f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
           f'<text x="{PAD_L}" y="20" font-size="13" font-weight="600">{escape(title)}: '
           f'altitude against distance to the landing site</text>']
    for v in _ticks(0, max(hs) or 1.0, 4):
        y = sh(v)
        out.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{grid}"/>')
        out.append(f'<text x="{PAD_L - 6}" y="{y + 4:.1f}" text-anchor="end">{v:.1f} km</text>')
    for v in _ticks(x0, x1, 5):
        x = sx(v)
        out.append(f'<text x="{x:.1f}" y="{PAD_T + ALT_H + 14}" text-anchor="middle">'
                   f'{v:.0f} km</text>')
    out.append(_polyline([(sx(x), sh(h)) for x, h in zip(xs, hs)], accent))
    programs = []
    for r, x, h in zip(rows, xs, hs):
        if not programs or programs[-1][0] != r[6]:
            programs.append((r[6], x, h))
    for program, x, h in programs[1:]:
        out.append(f'<circle cx="{sx(x):.1f}" cy="{sh(h):.1f}" r="3" fill="{warm}"/>')
        out.append(f'<text x="{sx(x) + 5:.1f}" y="{sh(h) - 5:.1f}" fill="{warm}">P{program}</text>')
    out.append(f'<text x="{PAD_L}" y="{top - 8}" font-weight="600">Throttle, percent, over '
               f'time ({min(ts):.0f}–{max(ts):.0f} s)</text>')
    for v in (0, 60, 92.5):
        y = sthr(v)
        out.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y:.1f}" y2="{y:.1f}" stroke="{grid}"/>')
        out.append(f'<text x="{PAD_L - 6}" y="{y + 4:.1f}" text-anchor="end">{v:g}%</text>')
    out.append(_polyline([(st(r[0]), sthr(r[5])) for r in rows], ink, 1.5))
    out.append("</svg>")
    return "\n".join(out)
