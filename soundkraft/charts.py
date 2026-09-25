"""Server-rendered SVG line charts for the dashboard (no JavaScript chart library needed).

Colours come from CSS custom properties (see app.css) so light/dark themes swap in one place.
"""

from __future__ import annotations

from html import escape


def line_chart(points: list[tuple[str, float]], width: int = 640, height: int = 240,
               band: tuple[float, float] | None = None, y_range: tuple[float, float] = (0, 100),
               label: str = "Index", compact: bool = False) -> str:
    """Single-series line chart. `points` is [(x label, value)]. `band` shades a reference range."""
    if not points:
        return '<p class="muted">No sessions yet.</p>'
    pad_l, pad_r, pad_t, pad_b = (8, 8, 8, 8) if compact else (40, 56, 14, 30)
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    lo, hi = y_range

    def x(i: int) -> float:
        return pad_l + (w / 2 if len(points) == 1 else i * w / (len(points) - 1))

    def y(v: float) -> float:
        return pad_t + h - (min(max(v, lo), hi) - lo) / (hi - lo) * h

    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="{escape(label)} over {len(points)} sessions" preserveAspectRatio="xMidYMid meet">']
    if not compact:
        for tick in range(int(lo), int(hi) + 1, 25):
            ty = y(tick)
            out.append(f'<line class="grid" x1="{pad_l}" x2="{pad_l + w}" y1="{ty:.1f}" y2="{ty:.1f}"/>')
            out.append(f'<text class="axis" x="{pad_l - 6}" y="{ty + 4:.1f}" text-anchor="end">{tick}</text>')
    if band:
        b_top, b_bot = y(band[1]), y(band[0])
        out.append(f'<rect class="band" x="{pad_l}" y="{b_top:.1f}" width="{w}" height="{b_bot - b_top:.1f}">'
                   f'<title>Usual range (baseline ± 1 SD): {band[0]:.0f}–{band[1]:.0f}</title></rect>')
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(points))
    out.append(f'<path class="line" d="{path}"/>')
    r = 3 if compact else 4
    for i, (xl, v) in enumerate(points):
        out.append(f'<g class="pt"><circle class="hit" cx="{x(i):.1f}" cy="{y(v):.1f}" r="12"/>'
                   f'<circle class="dot" cx="{x(i):.1f}" cy="{y(v):.1f}" r="{r}"/>'
                   f'<title>{escape(xl)}: {label} {v:.1f}</title></g>')
    if not compact:
        lx, lv = x(len(points) - 1), points[-1][1]
        out.append(f'<text class="value" x="{lx + 8:.1f}" y="{y(lv) + 4:.1f}">{lv:.0f}</text>')
        first, last = points[0][0], points[-1][0]
        out.append(f'<text class="axis" x="{pad_l}" y="{height - 8}">{escape(first)}</text>')
        if len(points) > 1:
            out.append(f'<text class="axis" x="{pad_l + w}" y="{height - 8}" text-anchor="end">{escape(last)}</text>')
    out.append("</svg>")
    return "".join(out)
