"""Promo overlays drawn on each finished frame with PIL: the title, chapter
labels, step captions, landing rings, confetti, a progress line and the end
card. Sizes are fractions of the frame height, so any resolution works.
"""
import glob
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import render

_FACES = {}
# (path, ttc index) per weight, best first; any that loads wins
_CANDIDATES = {
    "heavy": [("/System/Library/Fonts/Avenir Next.ttc", 8), ("/System/Library/Fonts/Avenir Next.ttc", 0),
              ("/System/Library/Fonts/HelveticaNeue.ttc", 1), ("DejaVuSans-Bold.ttf", 0)],
    "bold": [("/System/Library/Fonts/Avenir Next.ttc", 2), ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
             ("DejaVuSans-Bold.ttf", 0)],
    "regular": [("/System/Library/Fonts/Avenir Next.ttc", 5), ("/System/Library/Fonts/HelveticaNeue.ttc", 0),
                ("DejaVuSans.ttf", 0)],
}


def _find(name):
    """A font file: an absolute path as it is, else `name` in the usual
    folders (the app bundle's fonts/, matplotlib's, the system's)."""
    if os.path.isabs(name):
        return name if os.path.isfile(name) else None
    roots = [os.path.join(sys.prefix, "fonts"),
             os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(sys.executable or ""))),
                          "fonts"),
             "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/TTF", "/usr/share/fonts/dejavu"]
    roots += glob.glob(os.path.join(sys.prefix, "lib", "python3*", "site-packages", "matplotlib",
                                    "mpl-data", "fonts", "ttf"))
    for r in roots:
        p = os.path.join(r, name)
        if os.path.isfile(p):
            return p
    return None


def font(weight, px):
    key = (weight, int(px))
    if key in _FACES:
        return _FACES[key]
    f = None
    for path, idx in _CANDIDATES.get(weight, []):
        p = _find(path)
        if not p:
            continue
        try:
            f = ImageFont.truetype(p, int(px), index=idx)
            break
        except OSError:
            continue
    if f is None:
        try:
            f = ImageFont.load_default(size=int(px))
        except TypeError:
            f = ImageFont.load_default()
    _FACES[key] = f
    return f


def _rgb(c, a=1.0):
    return tuple(int(max(0, min(1, x)) * 255) for x in c[:3]) + (int(max(0, min(1, a)) * 255),)


def _text(d, xy, text, f, fill, shadow=None, anchor="ls"):
    if shadow is not None:
        d.text((xy[0] + 2, xy[1] + 2), text, font=f, fill=shadow, anchor=anchor)
    d.text(xy, text, font=f, fill=fill, anchor=anchor)


def draw(img, plan, st, env, spec, W, H):
    """img: uint8 HxWx3 -> PIL RGB with this frame's overlays."""
    base = Image.fromarray(img).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    u = H / 100.0                                      # 1 % of the height
    text_c = env.get("text", (0.08, 0.09, 0.11))
    accent = plan.accent
    title = str(spec.get("title") or "Your design")[:48]
    tagline = str(spec.get("tagline") or "")[:90]
    # --- flash
    if st.get("flash"):
        d.rectangle((0, 0, W, H), fill=(255, 255, 255, int(255 * st["flash"])))
    # --- landing rings (projected part centres)
    for ctr, x in st.get("rings") or []:
        px, py, _dd = render.project_px(st["cam"], plan.scene, W, H, np.asarray(ctr)[None])
        r = (2.5 + 9 * x) * u
        a = (1 - x) * 0.8
        d.ellipse((px[0] - r, py[0] - r * 0.6, px[0] + r, py[0] + r * 0.6),
                  outline=_rgb(accent, a), width=max(2, int(0.5 * u)))
    # --- title (hero)
    a = st.get("title") or 0.0
    if a > 0:
        slide = (1 - a) * 6 * u
        x0 = 6 * u - slide
        _text(d, (x0, H - 15 * u), title, font("heavy", 9 * u), _rgb(text_c, a))
        if tagline:
            _text(d, (x0 + 0.3 * u, H - 9 * u), tagline, font("regular", 3.6 * u),
                  _rgb(text_c, 0.85 * a))
        d.rectangle((x0, H - 25.5 * u, x0 + 7 * u * a, H - 24.7 * u), fill=_rgb(accent, a))
    # --- chapter label (top left)
    ch = st.get("chapter")
    if ch and ch[0] and ch[1] > 0:
        name, a = ch
        names = [s.chapter for s in plan.steps if s.chapter]
        num = names.index(name) + 1 if name in names else 1
        f = font("bold", 3.0 * u)
        d.rectangle((5 * u, 6 * u, 5.6 * u, 10.6 * u), fill=_rgb(accent, a))
        _text(d, (7 * u, 9.6 * u), "%02d   %s" % (num, name.upper()), f, _rgb(text_c, a))
    # --- step caption (lower third)
    step = st.get("step")
    if step:
        i, s, a_in = step[0], step[1], step[2]
        a = a_in
        f1, f2, f3 = font("bold", 4.6 * u), font("regular", 2.8 * u), font("bold", 2.4 * u)
        y = H - 9 * u
        x = 6 * u + (1 - a) * 3 * u
        panel = env.get("panel", (1, 1, 1))
        tw = max(d.textlength(s.title, font=f1), d.textlength(s.sub or "", font=f2)) + 6 * u
        d.rounded_rectangle((x - 2.2 * u, y - 7.8 * u, x + tw, y + 3.2 * u if s.sub else y + 1.6 * u),
                            radius=int(1.2 * u), fill=_rgb(panel, 0.72 * a))
        d.rectangle((x - 2.2 * u, y - 7.8 * u, x - 1.6 * u, y + 3.2 * u if s.sub else y + 1.6 * u),
                    fill=_rgb(accent, a))
        _text(d, (x, y - 2.6 * u), s.title, f1, _rgb(text_c, a))
        if s.sub:
            _text(d, (x, y + 1.0 * u), s.sub, f2, _rgb(text_c, 0.8 * a))
        # step counter, right
        cnt = "%02d / %02d" % (i + 1, len(plan.steps))
        _text(d, (W - 6 * u, y + 1.0 * u), cnt, f3, _rgb(text_c, 0.75 * a), anchor="rs")
    prog = st.get("progress")
    if prog is not None:
        d.rectangle((0, H - 0.6 * u, W * prog, H), fill=_rgb(accent, 0.95))
    # --- confetti
    c = st.get("confetti")
    if c is not None and c >= 0:
        _confetti(d, plan, c, W, H, u)
    # --- end card
    e = st.get("end") or 0.0
    if e > 0:
        panel = env.get("panel", (1, 1, 1))
        band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(band)
        bd.rectangle((0, H - 33 * u, W, H), fill=_rgb(panel, 0.78 * e))
        band = band.filter(ImageFilter.GaussianBlur(3 * u))
        layer = Image.alpha_composite(band, layer)
        d = ImageDraw.Draw(layer)
        ft = font("heavy", 8.5 * u)
        y = H - 17 * u + (1 - e) * 4 * u
        _text(d, (W / 2, y), title, ft, _rgb(text_c, e), anchor="ms")
        if tagline:
            _text(d, (W / 2, y + 5.6 * u), tagline, font("regular", 3.4 * u), _rgb(text_c, 0.85 * e),
                  anchor="ms")
        mk = "DESIGNED WITH ATECH AI CAD"
        fm = font("bold", 2.2 * u)
        _text(d, (W / 2, H - 3.6 * u), mk, fm, _rgb(text_c, 0.65 * e), anchor="ms")
        wl = d.textlength(title, font=ft)
        d.rectangle((W / 2 - wl / 2, y + 1.6 * u, W / 2 - wl / 2 + wl * e, y + 2.1 * u),
                    fill=_rgb(accent, e))
    out = Image.alpha_composite(base, layer)
    return out.convert("RGB")


def _confetti(d, plan, c, W, H, u):
    """A burst from the bottom corners, in the product's own colours."""
    rng = np.random.default_rng(5)
    n = 140
    cols = [tuple(x) for x in plan.scene.colors if max(x) - min(x) > 0.12] or []
    cols = (cols + [tuple(plan.accent), (1.0, 0.85, 0.3), (1.0, 1.0, 1.0)])
    side = rng.random(n) < 0.5
    x0 = np.where(side, 0.04 * W, 0.96 * W)
    vx = (rng.random(n) * 0.35 + 0.08) * W * np.where(side, 1, -1)
    vy = -(rng.random(n) * 0.55 + 0.75) * H
    g = 1.25 * H
    x = x0 + vx * c
    y = H * 1.02 + vy * c + 0.5 * g * c * c
    spin = rng.random(n) * 12 + c * (rng.random(n) * 14 - 7)
    a = max(0.0, 1 - c / 2.4)
    if a <= 0:
        return
    s = (0.5 + rng.random(n)) * 0.9 * u
    for i in range(n):
        if not (-20 < x[i] < W + 20 and -20 < y[i] < H + 20):
            continue
        col = cols[i % len(cols)]
        w = s[i] * (0.4 + 0.6 * abs(math.cos(spin[i])))
        h = s[i] * 0.55
        ca, sa = math.cos(spin[i] * 0.7), math.sin(spin[i] * 0.7)
        pts = [(x[i] + ca * dx - sa * dy, y[i] + sa * dx + ca * dy)
               for dx, dy in ((-w, -h), (w, -h), (w, h), (-w, h))]
        d.polygon(pts, fill=_rgb(col, a))
