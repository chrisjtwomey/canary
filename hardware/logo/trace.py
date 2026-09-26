"""The CANARY logo as SVG outlines: for the enclosure, and for the head's panel.

From the drawn logo (canary-source.jpeg) to canary-logo.svg, which
enclosure.py imports: the logo as one white piece glued into the dock's pill
recess. It is drawn for a flat print on a 0.2 mm nozzle: every line at least
--line wide, every gap at least --gap, the letters spaced --spacing further
apart. A second file, canary-logo-screen.svg, is the drawing with none of
that, for the head's splash screen (server/pages/splash.py).

    python3 -m venv .venv && .venv/bin/pip install pillow numpy scipy scikit-image potracer
    .venv/bin/python hardware/logo/trace.py --height 8 --pill 35 9.6

The piece is the pill, --fit smaller all round, as a border --border wide.
The emblem reaches the border at its top and bottom and joins it there; a
line --bar tall under the letters, from the emblem's A to the Y, holds the
rest.
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import potrace
from PIL import Image
from scipy import ndimage as ndi
from skimage.morphology import disk, skeletonize

UP = 3   # trace at 3x the source, for smooth edges


def ink_mask(path: str) -> np.ndarray:
    """The dark strokes of the drawing, at 3x, specks dropped."""
    im = Image.open(path).convert("L")
    im = im.resize((im.width * UP, im.height * UP), Image.LANCZOS)
    a = ndi.gaussian_filter(np.asarray(im).astype(float), 1.2 * UP)
    bg, ink = np.median(a), np.percentile(a, 0.5)
    m = a < (bg + ink) / 2
    lab, n = ndi.label(m)
    sizes = ndi.sum(m, lab, range(1, n + 1))
    m = np.isin(lab, 1 + np.nonzero(sizes > 30 * UP * UP)[0])
    ys, xs = np.nonzero(m)
    pad = 4 * UP
    return m[ys.min() - pad:ys.max() + pad + 1, xs.min() - pad:xs.max() + pad + 1]


def pixels_per_mm(m: np.ndarray, height_mm: float) -> float:
    ys = np.nonzero(m)[0]
    return (ys.max() - ys.min() + 1) / height_mm


def hairline_mm(m: np.ndarray, ppm: float) -> float:
    """The thinnest stroke that is not a taper: the 2nd percentile of widths along the skeleton."""
    dt = ndi.distance_transform_edt(m)
    return float(np.percentile(2 * dt[skeletonize(m)], 2)) / ppm


def space_letters(m: np.ndarray, ppm: float, spacing_mm: float) -> np.ndarray:
    """Each piece after the first moved right, so neighbours sit spacing_mm further apart."""
    lab, n = ndi.label(m)
    order = sorted(range(1, n + 1), key=lambda k: np.nonzero(lab == k)[1].min())
    step = int(round(spacing_mm * ppm))
    wide = np.zeros((m.shape[0], m.shape[1] + step * (n - 1)), bool)
    for i, k in enumerate(order):
        yy, xx = np.nonzero(lab == k)
        wide[yy, xx + i * step] = True
    return wide


def printable(m: np.ndarray, ppm: float, line_mm: float, gap_mm: float) -> np.ndarray:
    """Every stroke at least line_mm wide (an even offset), then every gap at least gap_mm (narrower ones close)."""
    grow = max(0.0, (line_mm - hairline_mm(m, ppm)) / 2) * ppm
    fat = ndi.distance_transform_edt(~m) <= grow if grow > 0 else m.copy()
    return ndi.binary_closing(np.pad(fat, 40), structure=disk(int(round(gap_mm * ppm / 2))))[40:-40, 40:-40]


def to_svg(m: np.ndarray, ppm: float, path: str) -> int:
    """Trace the True pixels of m into one evenodd path, in millimetres. Returns the number of outlines."""
    plist = potrace.Bitmap(~m).trace(turdsize=20, turnpolicy=potrace.POTRACE_TURNPOLICY_MINORITY,
                                     alphamax=1.0, opticurve=True, opttolerance=0.2)
    s = 1.0 / ppm
    f = lambda p: "%.4f %.4f" % (p.x * s, p.y * s)  # noqa: E731
    d = []
    for curve in plist:
        d.append("M " + f(curve.start_point))
        for seg in curve.segments:
            d.append(("L %s L %s" % (f(seg.c), f(seg.end_point))) if seg.is_corner
                     else ("C %s %s %s" % (f(seg.c1), f(seg.c2), f(seg.end_point))))
        d.append("Z")
    w, h = m.shape[1] * s, m.shape[0] * s
    with open(path, "w") as out:
        out.write('<svg xmlns="http://www.w3.org/2000/svg" width="%.3fmm" height="%.3fmm" viewBox="0 0 %.4f %.4f">\n'
                  '<path fill="#000" fill-rule="evenodd" d="%s"/>\n</svg>\n' % (w, h, w, h, " ".join(d)))
    return len(plist)


def runs(row: np.ndarray) -> list[tuple[int, int]]:
    """The first and last column of each stretch of True in row."""
    edges = np.flatnonzero(np.diff(np.concatenate(([0], row.astype(np.int8), [0]))))
    return list(zip(edges[::2], edges[1::2] - 1))


def one_piece(m: np.ndarray, ppm: float, pill_l: float, pill_h: float, fit: float, border: float, bar: float,
              gap: float) -> np.ndarray:
    """The pieces in a border that is the pill, fit smaller all round, with a line under the letters that
    overlaps the highest foot by 0.1 mm. Gaps narrower than gap close, which joins the emblem to the border."""
    ys, xs = np.nonzero(m)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2   # the logo's centre is the pill's
    pad = int(round(pill_h * ppm))
    m = np.pad(m, pad)
    cx, cy = cx + pad, cy + pad
    yy, xx = np.mgrid[0:m.shape[0], 0:m.shape[1]]
    x, y = (xx - cx) / ppm, (yy - cy) / ppm
    def pill(inset: float) -> np.ndarray:
        r = pill_h / 2 - inset
        return (np.abs(x) - (pill_l - pill_h) / 2).clip(0) ** 2 + y ** 2 <= r * r
    outer = pill(fit)
    lab, n = ndi.label(m)
    order = sorted(range(1, n + 1), key=lambda k: np.nonzero(lab == k)[1].min())
    emblem, letters = lab == order[0], [lab == k for k in order[1:]]
    feet = [np.nonzero(p)[0].max() for p in letters]
    top = min(feet) - int(round(0.1 * ppm))
    a_left_leg = runs(emblem[top])[-2]                                # the emblem's last two strokes on that row are the A's legs
    y_foot = letters[-1] & (yy >= feet[-1] - int(round(0.15 * ppm)))
    line = (yy >= top) & (yy < top + int(round(bar * ppm))) & (xx >= a_left_leg[0]) & (xx <= np.nonzero(y_foot)[1].max())
    s = m | (outer & ~pill(fit + border)) | line
    s = ndi.binary_closing(s, structure=disk(int(round(gap * ppm / 2)))) & outer
    ys, xs = np.nonzero(s)
    return s[ys.min() - 4:ys.max() + 5, xs.min() - 4:xs.max() + 5]


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--image", default=os.path.join(here, "canary-source.jpeg"))
    ap.add_argument("--height", type=float, default=8.0, help="the logo's height in mm")
    ap.add_argument("--line", type=float, default=0.3, help="thinnest stroke, mm")
    ap.add_argument("--gap", type=float, default=0.25, help="narrowest gap, mm")
    ap.add_argument("--spacing", type=float, default=0.7, help="extra space between letters, mm")
    ap.add_argument("--pill", type=float, nargs=2, default=(35.0, 9.6), metavar=("L", "H"), help="the recess, mm")
    ap.add_argument("--fit", type=float, default=0.25, help="the piece's clearance to the recess, all round, mm")
    ap.add_argument("--border", type=float, default=0.6, help="the border's width, mm")
    ap.add_argument("--bar", type=float, default=0.45, help="the line under the letters, its height, mm")
    ap.add_argument("--out", default=os.path.dirname(here), help="where the two SVGs go")
    args = ap.parse_args()

    m = ink_mask(args.image)
    ppm = pixels_per_mm(m, args.height)
    print("screen: %d outlines -> canary-logo-screen.svg" % to_svg(m, ppm, os.path.join(args.out, "canary-logo-screen.svg")))
    m = space_letters(m, ppm, args.spacing)
    m = printable(m, ppm, args.line, args.gap)
    print("letters: %.1f x %.1f mm, %d pieces, thinnest stroke %.2f mm" % (m.shape[1] / ppm, args.height,
          ndi.label(m)[1], hairline_mm(m, ppm)))
    m = one_piece(m, ppm, args.pill[0], args.pill[1], args.fit, args.border, args.bar, args.gap)
    n = ndi.label(m)[1]
    if n != 1:
        raise SystemExit("logo: %d pieces, not one" % n)
    print("logo: %.2f x %.2f mm, one piece" % ((m.shape[1] - 8) / ppm, (m.shape[0] - 8) / ppm))
    print("  outlines: %d -> %s" % (to_svg(m, ppm, os.path.join(args.out, "canary-logo.svg")), "canary-logo.svg"))


if __name__ == "__main__":
    main()
