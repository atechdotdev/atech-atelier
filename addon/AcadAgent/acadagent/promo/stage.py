"""Promo stages: the world the product stands in. Each environment is a
dict of light colours, a sky and a procedural floor, drawn per pixel
(the floor is the ray's hit on the plane under the product, so it is in
true perspective under any camera and the product's shadow falls on it).

No FreeCAD, no Qt.
"""
import math

import numpy as np

# The names the director may choose (director.py lists them to Claude).
ENVIRONMENTS = {
    "studio": "seamless light-grey photo studio sweep - clean product shot",
    "desk": "warm wooden desk top, cosy lamp light - desk gadgets, clocks, lamps",
    "night": "midnight blue, stars, a moon glow - night lights, alarm clocks, sleep",
    "garden": "sunny terracotta patio tiles, green bokeh - planters, weather, outdoors",
    "neon": "synthwave: magenta grid floor, purple sky, striped sun - games, arcade, music",
    "blueprint": "engineering blueprint grid - tools, brackets, robots, technical builds",
    "kitchen": "white marble counter, bright morning light - home, pets, kitchen",
    "workshop": "concrete floor, cool daylight, hazard stripe - vehicles, rovers, tanks",
    "sunset": "golden-hour gradient, warm rim light - speakers, lamps, lifestyle",
}

_BASE = {
    "key": (-0.45, -0.65, 0.85), "key_color": (1.0, 1.0, 1.0),
    "sky_light": (1.0, 1.0, 1.02), "ground_light": (0.78, 0.78, 0.78), "ambient": 0.46,
    "fill": (0.7, 0.3, 0.35), "fill_color": (0.85, 0.9, 1.0),
    "rim": 0.14, "rim_color": (1, 1, 1), "spec": 0.28,
    "ink": (0.10, 0.11, 0.13), "ink_strength": 0.55,
    "sky_top": (0.95, 0.95, 0.96), "sky_bot": (0.86, 0.87, 0.89),
    "floor": "sweep", "floor_color": (0.88, 0.88, 0.90), "fog": (0.90, 0.90, 0.92),
    "shadow": 0.34, "text": (0.08, 0.09, 0.11), "panel": (1, 1, 1),
    "accent": (0.16, 0.74, 0.62), "contrast": 1.0, "saturation": 1.0, "vignette": 0.18,
    "sky_fx": None,
}

_ENV = {
    "studio": {},
    "desk": {
        "key_color": (1.0, 0.93, 0.82), "sky_light": (1.0, 0.95, 0.88),
        "ground_light": (0.80, 0.66, 0.52), "fill_color": (0.95, 0.85, 0.75),
        "sky_top": (0.93, 0.86, 0.76), "sky_bot": (0.78, 0.66, 0.53),
        "floor": "wood", "floor_color": (0.60, 0.40, 0.24), "fog": (0.76, 0.63, 0.50),
        "shadow": 0.40, "accent": (0.93, 0.55, 0.22), "vignette": 0.30,
        "sky_fx": "dust",
    },
    "night": {
        "key": (-0.45, -0.60, 0.70), "key_color": (0.85, 0.90, 1.0),
        "sky_light": (0.70, 0.76, 1.0), "ground_light": (0.35, 0.36, 0.50), "ambient": 0.55,
        "fill_color": (0.55, 0.45, 0.95), "rim": 0.45, "rim_color": (0.55, 0.75, 1.0),
        "ink": (0.02, 0.03, 0.08), "ink_strength": 0.45,
        "sky_top": (0.02, 0.03, 0.10), "sky_bot": (0.09, 0.12, 0.28),
        "floor": "slate", "floor_color": (0.10, 0.12, 0.20), "fog": (0.08, 0.10, 0.22),
        "shadow": 0.55, "text": (0.92, 0.94, 1.0), "panel": (0.05, 0.07, 0.16),
        "accent": (0.55, 0.75, 1.0), "vignette": 0.40, "sky_fx": "stars",
    },
    "garden": {
        "key_color": (1.0, 0.97, 0.88), "sky_light": (0.92, 1.0, 0.92),
        "ground_light": (0.85, 0.62, 0.48),
        "sky_top": (0.80, 0.92, 0.78), "sky_bot": (0.56, 0.75, 0.50),
        "floor": "tiles", "floor_color": (0.78, 0.47, 0.32), "fog": (0.66, 0.78, 0.58),
        "shadow": 0.38, "accent": (0.35, 0.70, 0.30), "vignette": 0.25, "sky_fx": "bokeh",
        "saturation": 1.08,
    },
    "neon": {
        "key": (0.35, -0.55, 0.75), "key_color": (1.0, 0.80, 0.95),
        "sky_light": (0.75, 0.55, 1.0), "ground_light": (0.55, 0.15, 0.55), "ambient": 0.40,
        "fill": (0.8, 0.5, 0.2), "fill_color": (0.20, 0.95, 1.0),
        "rim": 0.55, "rim_color": (0.25, 0.95, 1.0), "spec": 0.35,
        "ink": (0.05, 0.01, 0.10), "ink_strength": 0.5,
        "sky_top": (0.06, 0.01, 0.16), "sky_bot": (0.42, 0.06, 0.40),
        "floor": "grid", "floor_color": (0.05, 0.01, 0.10), "fog": (0.38, 0.05, 0.36),
        "shadow": 0.6, "text": (1.0, 0.95, 1.0), "panel": (0.08, 0.02, 0.16),
        "accent": (1.0, 0.25, 0.75), "grid": (1.0, 0.25, 0.75), "vignette": 0.35,
        "sky_fx": "sun", "saturation": 1.12,
    },
    "blueprint": {
        "key_color": (0.95, 0.98, 1.0), "sky_light": (0.85, 0.92, 1.0),
        "ground_light": (0.45, 0.58, 0.80), "fill_color": (0.75, 0.85, 1.0),
        "rim": 0.25, "rim_color": (0.75, 0.88, 1.0), "ink": (0.02, 0.08, 0.20),
        "sky_top": (0.07, 0.20, 0.42), "sky_bot": (0.12, 0.32, 0.60),
        "floor": "blueprint", "floor_color": (0.10, 0.30, 0.58), "fog": (0.11, 0.30, 0.56),
        "shadow": 0.45, "text": (0.95, 0.97, 1.0), "panel": (0.05, 0.16, 0.36),
        "accent": (0.98, 0.80, 0.25), "vignette": 0.30,
    },
    "kitchen": {
        "key_color": (1.0, 0.99, 0.96), "sky_light": (1.0, 1.0, 1.0), "ambient": 0.52,
        "ground_light": (0.86, 0.86, 0.86), "sky_top": (0.97, 0.97, 0.95),
        "sky_bot": (0.88, 0.90, 0.90), "floor": "marble", "floor_color": (0.94, 0.94, 0.93),
        "fog": (0.93, 0.94, 0.93), "shadow": 0.30, "accent": (0.20, 0.62, 0.86),
        "vignette": 0.15, "contrast": 1.04,
    },
    "workshop": {
        "key": (-0.35, -0.55, 0.85), "key_color": (0.95, 0.98, 1.0),
        "sky_light": (0.88, 0.93, 1.0), "ground_light": (0.55, 0.56, 0.58),
        "sky_top": (0.30, 0.33, 0.37), "sky_bot": (0.55, 0.57, 0.60),
        "floor": "concrete", "floor_color": (0.56, 0.57, 0.58), "fog": (0.50, 0.52, 0.55),
        "shadow": 0.45, "text": (0.98, 0.98, 0.98), "panel": (0.12, 0.13, 0.15),
        "accent": (1.0, 0.76, 0.10), "vignette": 0.35, "contrast": 1.05,
    },
    "sunset": {
        "key": (0.55, -0.60, 0.45), "key_color": (1.0, 0.82, 0.62),
        "sky_light": (1.0, 0.85, 0.75), "ground_light": (0.70, 0.50, 0.50), "ambient": 0.52,
        "fill_color": (0.65, 0.55, 0.95), "rim": 0.40, "rim_color": (1.0, 0.70, 0.40),
        "sky_top": (0.30, 0.22, 0.45), "sky_bot": (0.98, 0.62, 0.40),
        "floor": "sand", "floor_color": (0.80, 0.58, 0.46), "fog": (0.92, 0.60, 0.46),
        "shadow": 0.42, "text": (1.0, 0.97, 0.94), "panel": (0.22, 0.12, 0.22),
        "accent": (1.0, 0.55, 0.30), "vignette": 0.32, "saturation": 1.06,
    },
}


def environment(name, accent=None):
    """The environment dict for `name` (unknown: studio), with an optional
    accent colour (r, g, b) 0..1 over its own."""
    env = dict(_BASE)
    env.update(_ENV.get(name) or {})
    env["name"] = name if name in _ENV else "studio"
    if accent is not None:
        env["accent"] = tuple(float(c) for c in accent)[:3]
    return env


# ---------------------------------------------------------------- noise
def _hash(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)).astype(np.float64) / 4294967295.0


def vnoise(x, y, seed=0):
    """Smooth value noise in 0..1 (float arrays)."""
    x0, y0 = np.floor(x), np.floor(y)
    fx, fy = x - x0, y - y0
    ix, iy = x0.astype(np.int64), y0.astype(np.int64)
    ux, uy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = _hash(ix, iy, seed), _hash(ix + 1, iy, seed)
    c, d = _hash(ix, iy + 1, seed), _hash(ix + 1, iy + 1, seed)
    return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy


def fbm(x, y, octaves=4, seed=0):
    out, amp, tot = 0.0, 0.5, 0.0
    for o in range(octaves):
        out = out + amp * vnoise(x, y, seed + o)
        tot += amp
        x, y, amp = x * 2.03, y * 2.03, amp * 0.5
    return out / tot


def _line(u, width):
    """1 on a grid line (u in cell units), soft over `width`."""
    f = np.abs(u - np.round(u))
    return np.clip(1 - f / max(width, 1e-6), 0, 1)


# ---------------------------------------------------------------- floors
def floor_rgb(env, gx, gy, R):
    """Floor colour at world (gx, gy) mm; R the product's radius."""
    kind = env["floor"]
    base = np.asarray(env["floor_color"], float)
    shape = gx.shape + (3,)
    if kind == "wood":
        pw = R * 0.42                                  # plank width
        row = np.floor(gy / pw)
        off = _hash(row.astype(np.int64), 7, 3) * 3 * R
        seg = np.floor((gx + off) / (R * 2.4))
        tint = 0.82 + 0.3 * _hash(row.astype(np.int64), seg.astype(np.int64), 5)
        grain = fbm((gx + off) / (R * 0.9), gy / (R * 0.05), 3, 11)
        rings = 0.5 + 0.5 * np.sin(grain * 18.0)
        c = base * (tint * (0.88 + 0.16 * rings))[..., None]
        gap = np.maximum(_line(gy / pw, 0.025), _line((gx + off) / (R * 2.4), 0.006))
        return c * (1 - 0.55 * gap[..., None])
    if kind == "tiles":
        ts = R * 0.55
        u, v = gx / ts, gy / ts
        tint = 0.86 + 0.24 * _hash(np.floor(u).astype(np.int64), np.floor(v).astype(np.int64), 9)
        mott = 0.92 + 0.12 * fbm(gx / (R * 0.12), gy / (R * 0.12), 3, 2)
        c = base * (tint * mott)[..., None]
        grout = np.maximum(_line(u, 0.035), _line(v, 0.035))
        return c * (1 - grout[..., None]) + np.array([0.86, 0.82, 0.74]) * grout[..., None]
    if kind == "marble":
        n = fbm(gx / (R * 0.7), gy / (R * 0.7), 5, 21)
        vein = np.abs(np.sin((gx + gy * 0.6) / (R * 0.35) + n * 9.0)) ** 0.22
        c = base * (0.985 + 0.03 * n)[..., None]
        return c * (0.80 + 0.20 * vein)[..., None] + np.array([0.02, 0.02, 0.025]) * (1 - vein)[..., None]
    if kind == "concrete":
        n = fbm(gx / (R * 0.25), gy / (R * 0.25), 5, 31)
        sp = (vnoise(gx / (R * 0.012), gy / (R * 0.012), 4) > 0.86) * 0.06
        c = base * (0.86 + 0.24 * n - sp)[..., None]
        seam = np.maximum(_line(gx / (R * 3.0), 0.004), _line(gy / (R * 3.0), 0.004))
        # a hazard stripe band crossing behind the product
        band = (gy > R * 1.35) & (gy < R * 1.6)
        stripe = (np.floor((gx + gy) / (R * 0.18)) % 2 == 0)
        haz = np.where(stripe, 0, 1)[..., None] * np.array([0.95, 0.72, 0.08]) \
            + np.where(stripe, 1, 0)[..., None] * np.array([0.08, 0.08, 0.09])
        c = np.where(band[..., None], haz * 0.85, c)
        return c * (1 - 0.35 * seam[..., None])
    if kind == "grid":
        gs = R * 0.45
        ln = np.maximum(_line(gx / gs, 0.04), _line(gy / gs, 0.04))
        c = np.broadcast_to(base, shape).copy()
        neon = np.asarray(env.get("grid") or env["accent"], float)
        return c + ln[..., None] * neon * 1.15
    if kind == "blueprint":
        fine = np.maximum(_line(gx / (R * 0.1), 0.05), _line(gy / (R * 0.1), 0.05))
        major = np.maximum(_line(gx / (R * 0.5), 0.02), _line(gy / (R * 0.5), 0.02))
        c = np.broadcast_to(base, shape).copy()
        return c + (0.10 * fine + 0.38 * major)[..., None] * np.array([0.85, 0.92, 1.0])
    if kind == "slate":
        n = fbm(gx / (R * 0.3), gy / (R * 0.3), 4, 41)
        return base * (0.85 + 0.3 * n)[..., None] * np.ones(3)
    if kind == "sand":
        n = fbm(gx / (R * 0.5), gy / (R * 0.08), 4, 51)
        ripple = 0.5 + 0.5 * np.sin(gy / (R * 0.07) + n * 6)
        return base * (0.88 + 0.08 * ripple + 0.08 * n)[..., None]
    # studio sweep
    return np.broadcast_to(base, shape).copy()


# ---------------------------------------------------------------- sky
def _sky(env, Ws, Hs, t):
    gy = np.linspace(0, 1, Hs)[:, None, None]
    top, bot = np.asarray(env["sky_top"], float), np.asarray(env["sky_bot"], float)
    img = np.empty((Hs, Ws, 3))
    img[:] = top * (1 - gy) + bot * gy
    fx = env.get("sky_fx")
    if fx == "stars":
        rng = np.random.default_rng(7)
        n = int(Ws * Hs / 2600)
        xs, ys = rng.random(n) * Ws, rng.random(n) ** 1.6 * Hs * 0.8
        b = rng.random(n)
        tw = 0.55 + 0.45 * np.sin(t * (1.5 + 3 * rng.random(n)) + rng.random(n) * 6.3)
        xi = np.clip(xs.astype(int), 0, Ws - 1)
        yi = np.clip(ys.astype(int), 0, Hs - 1)
        for dx, dy, k in ((0, 0, 1.0), (1, 0, 0.5), (0, 1, 0.5), (-1, 0, 0.4), (0, -1, 0.4)):
            img[np.clip(yi + dy, 0, Hs - 1), np.clip(xi + dx, 0, Ws - 1)] += \
                (k * b * tw)[:, None] * np.array([0.9, 0.93, 1.0])
        # moon glow, upper right
        yy, xx = np.mgrid[0:Hs, 0:Ws]
        d = np.hypot(xx - Ws * 0.82, yy - Hs * 0.16) / (0.06 * Hs)
        img += (np.clip(1 - d, 0, 1) ** 0.5 * 0.85)[..., None] * np.array([0.95, 0.95, 0.85])
        img += (np.exp(-d * 0.35) * 0.18)[..., None] * np.array([0.6, 0.7, 1.0])
    elif fx == "sun":
        yy, xx = np.mgrid[0:Hs, 0:Ws]
        cx, cy, r = Ws * 0.5, Hs * 0.42, Hs * 0.24
        d = np.hypot(xx - cx, yy - cy)
        disc = d < r
        hf = (yy - (cy - r)) / (2 * r)
        stripes = (np.sin(hf * 26 * math.pi) > (hf * 2.2 - 1.2)) | (hf < 0.5)
        sun = np.array([1.0, 0.85, 0.30]) * (1 - hf)[..., None] + np.array([1.0, 0.25, 0.55]) * hf[..., None]
        m = disc & stripes
        img[m] = sun[m]
        img += (np.exp(-np.maximum(d - r, 0) / (0.25 * Hs)) * 0.25)[..., None] * np.array([1.0, 0.3, 0.6])
    elif fx == "bokeh":
        rng = np.random.default_rng(3)
        yy, xx = np.mgrid[0:Hs, 0:Ws]
        for _ in range(16):
            cx = rng.random() * Ws + math.sin(t * 0.4 + rng.random() * 6) * 0.02 * Ws
            cy = rng.random() * Hs * 0.55
            r = (0.03 + 0.07 * rng.random()) * Hs
            d = np.hypot(xx - cx, yy - cy) / r
            col = np.array([0.95, 1.0, 0.75]) if rng.random() < 0.5 else np.array([0.75, 0.95, 0.65])
            img += (np.clip((1 - d) * 4, 0, 1) * 0.10)[..., None] * col
    elif fx == "dust":
        # a soft window light from the upper left
        yy, xx = np.mgrid[0:Hs, 0:Ws]
        beam = np.clip(1 - np.abs((xx - Ws * 0.2) - (yy - Hs * 0.0) * 0.6) / (0.25 * Ws), 0, 1)
        img += (beam ** 2 * 0.10 * (1 - yy / Hs))[..., None] * np.array([1.0, 0.9, 0.7])
    return img


def backdrop(env, scene, cam, Ws, Hs, s, ox, oy, shadow, t):
    """Sky + floor (with the product's shadow) for one frame, (Hs, Ws, 3)."""
    img = _sky(env, Ws, Hs, t)
    # pixel rays through the target plane -> the floor z = scene.floor
    yy, xx = np.mgrid[0:Hs, 0:Ws]
    gx = (xx + 0.5 - ox) / s
    gyy = (oy - yy - 0.5) / s
    eye = cam["ctr"] + cam["v"] * cam["dist"]
    Pp = cam["ctr"] + gx[..., None] * cam["r"] + gyy[..., None] * cam["u"]
    D = Pp - eye
    dz = D[..., 2]
    tt = (scene.floor - eye[2]) / np.where(np.abs(dz) < 1e-9, -1e-9, dz)
    hit = (tt > 0) & (dz < 0)
    if not hit.any():
        return img
    G = eye + D[hit] * tt[hit][:, None]
    R = scene.radius
    col = floor_rgb(env, G[:, 0], G[:, 1], R)
    rad = np.linalg.norm((G - scene.centre)[:, :2], axis=1)
    # light pool round the product, falling off into the fog
    pool = np.clip(1 - rad / (R * 5.0), 0, 1)
    col = col * (0.82 + 0.25 * pool)[:, None]
    lit = shadow.lit(G)
    fade = np.clip(1 - rad / (2.2 * R), 0, 1)
    col = col * (1 - (1 - lit) * env["shadow"] * fade)[:, None]
    # contact shadow: a soft dark ellipse right under the product
    lo, hi = scene.min, scene.max
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    ex = np.hypot((G[:, 0] - cx) / max((hi[0] - lo[0]) * 0.62, 1),
                  (G[:, 1] - cy) / max((hi[1] - lo[1]) * 0.62, 1))
    col = col * (1 - 0.22 * np.clip(1 - ex, 0, 1) ** 1.5)[:, None]
    fog = np.clip((rad - R * 1.6) / (R * 5.5), 0, 1) ** 0.8
    fog = np.maximum(fog, np.clip((tt[hit] - 1.25) / 1.6, 0, 1))
    col = col * (1 - fog)[:, None] + np.asarray(env["fog"], float) * fog[:, None]
    img[hit] = col
    # where the floor meets the sky: blend the fog line softly
    return img


def grade(env, img):
    """Colour grade + vignette on the supersampled frame."""
    c = env.get("contrast", 1.0)
    if c != 1.0:
        img = (img - 0.5) * c + 0.5
    s = env.get("saturation", 1.0)
    if s != 1.0:
        g = img.mean(-1, keepdims=True)
        img = g + (img - g) * s
    v = env.get("vignette", 0.0)
    if v:
        H, W = img.shape[:2]
        yy = np.linspace(-1, 1, H)[:, None]
        xx = np.linspace(-1, 1, W)[None]
        r = np.sqrt(xx ** 2 * 0.8 + yy ** 2)
        img = img * (1 - v * np.clip(r - 0.55, 0, 1) ** 1.6)[..., None]
    return img
