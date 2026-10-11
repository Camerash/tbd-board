"""Make the TBoarD icon files (SVG) from geometric letter strokes. No fonts, no dependencies.

Run from the repository root:  python3 tools/make_icons.py
Writes docs/media/{logo,wordmark,icon}-{light,dark}.svg and skills/tbd-board/assets/icon.svg.
PNG copies come from tools/make_media.mjs.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
LIGHT = {"accent": "#2f5d8a", "muted": "#56635c", "paper": "#ffffff"}
DARK = {"accent": "#8ab6e8", "muted": "#a2b0a8", "paper": "#141917"}


# Each glyph returns (centre-line paths, advance width). Cap top y=20, baseline y=120,
# x-height top y=50. The strokes have butt caps; w is the stroke width.
def T(x, w):
    h = w / 2
    return [f"M{x},{20+h} H{x+80}", f"M{x+40},20 V120"], 80


def B(x, w):
    h, m = w / 2, 68
    r1, r2 = (m - (20 + h)) / 2, (120 - h - m) / 2
    b1, b2 = x + 76 - h - r1, x + 82 - h - r2
    return [f"M{x+h},20 V120",
            f"M{x+h},{20+h} H{b1} A{r1} {r1} 0 0 1 {b1},{m} H{x+h}",
            f"M{x+h},{m} H{b2} A{r2} {r2} 0 0 1 {b2},{120-h} H{x+h}"], 82


def D(x, w):
    h = w / 2
    R = 50 - h
    dx = x + 88 - h - R
    return [f"M{x+h},20 V120", f"M{x+h},{20+h} H{dx} A{R} {R} 0 0 1 {dx},{120-h} H{x+h}"], 88


def o(x, w):
    r, c = 35 - w / 2, x + 35
    return [f"M{c-r},85 A{r} {r} 0 1 0 {c+r},85 A{r} {r} 0 1 0 {c-r},85"], 70


def a(x, w):
    return o(x, w)[0] + [f"M{x+70-w/2},50 V120"], 70


def r(x, w):
    h, R = w / 2, 24
    return [f"M{x+h},50 V120", f"M{x+h},{50+h+R} A{R} {R} 0 0 1 {x+h+R},{50+h} H{x+44}"], 44


def stroke(paths, color, w):
    return f'<path d="{" ".join(paths)}" fill="none" stroke="{color}" stroke-width="{w}"/>'


def svg(width, height, label, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" '
            f'width="{width:g}" height="{height:g}" role="img" aria-label="{label}">{body}</svg>\n')


def wordmark(pal):
    """TBoarD: T, B, D heavy in the accent colour; "oar" light and muted."""
    parts, x = [], 10
    seq = [(T, "accent", 20, 10), (B, "accent", 20, 12), (o, "muted", 11, 9),
           (a, "muted", 11, 9), (r, "muted", 11, 10), (D, "accent", 20, 0)]
    for fn, colour, w, gap in seq:
        paths, width = fn(x, w)
        parts.append(stroke(paths, pal[colour], w))
        x += width + gap
    return x + 10, "".join(parts)


def mark(pal):
    """2x2 tiles: T, B, D, and a filled tile with a check mark (the decision)."""
    m, gap, sw, s = 8, 12, 12, 0.66
    outer = (256 - 2 * m - gap) / 2
    parts = []
    for fn, ox, oy in ((T, m, m), (B, m + outer + gap, m), (D, m, m + outer + gap)):
        paths, width = fn(0, 26)
        parts.append(f'<rect x="{ox + sw/2:g}" y="{oy + sw/2:g}" width="{outer - sw:g}" height="{outer - sw:g}" '
                     f'rx="24" fill="none" stroke="{pal["accent"]}" stroke-width="{sw}"/>')
        parts.append(f'<g transform="translate({ox + (outer - width*s)/2:g},{oy + outer/2 - 70*s:g}) scale({s})">'
                     f'{stroke(paths, pal["accent"], 26)}</g>')
    cx = m + outer + gap
    c = cx + outer / 2
    parts.append(f'<rect x="{cx:g}" y="{cx:g}" width="{outer:g}" height="{outer:g}" rx="30" fill="{pal["accent"]}"/>')
    parts.append(f'<path d="M{c-30:g},{c+2:g} L{c-9:g},{c+23:g} L{c+31:g},{c-21:g}" fill="none" stroke="{pal["paper"]}" '
                 f'stroke-width="20" stroke-linecap="round" stroke-linejoin="round"/>')
    return "".join(parts)


def main():
    media = ROOT / "docs" / "media"
    media.mkdir(parents=True, exist_ok=True)
    for theme, pal in (("light", LIGHT), ("dark", DARK)):
        width, word = wordmark(pal)
        (media / f"wordmark-{theme}.svg").write_text(svg(width, 140, "TBoarD", word))
        (media / f"icon-{theme}.svg").write_text(svg(256, 256, "TBD Board", mark(pal)))
        lockup = (f'<g transform="scale({140/256:g})">{mark(pal)}</g>'
                  f'<g transform="translate(154,0)">{word}</g>')
        (media / f"logo-{theme}.svg").write_text(svg(154 + width, 140, "TBoarD", lockup))
    (ROOT / "skills" / "tbd-board" / "assets" / "icon.svg").write_text(svg(256, 256, "TBD Board", mark(LIGHT)))
    print("ok: wrote the icon files to docs/media and skills/tbd-board/assets")


if __name__ == "__main__":
    main()
