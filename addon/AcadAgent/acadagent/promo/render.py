"""Promo frame renderer: review.py's exact z-buffer rasterizer, with parts
that move, a stage (sky, floor, light) per environment, glow and bloom.

No FreeCAD, no Qt: numpy + PIL in the promo job's worker processes.
"""
import math

import numpy as np

import review
import stage

SPLIT_PX = 48.0                    # no screen triangle wider than this (review: 64)
SHADOW_RES = 1024


def rot(axis, deg):
    """3x3 rotation of `deg` degrees about the unit vector `axis`."""
    a = np.asarray(axis, float)
    a = a / max(np.linalg.norm(a), 1e-12)
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    x, y, z = a
    C = 1 - c
    return np.array([[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
                     [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
                     [z * x * C - y * s, z * y * C + x * s, c + z * z * C]])


class Scene(object):
    """The assembled product: per part its triangles (world, assembled),
    normals, colour. Loaded from the job's scene.npz + parts.json."""

    def __init__(self, parts, T, N, starts):
        self.parts = parts                      # dicts from parts.json
        self.T = [T[starts[k]:starts[k + 1]].astype(np.float64) for k in range(len(parts))]
        self.N = [N[starts[k]:starts[k + 1]].astype(np.float64) for k in range(len(parts))]
        P = T.reshape(-1, 3)
        self.min = P.min(0).astype(float)
        self.max = P.max(0).astype(float)
        self.centre = (self.min + self.max) / 2
        self.diag = float(np.linalg.norm(self.max - self.min))
        self.radius = max(self.diag / 2, 1.0)
        self.floor = float(self.min[2])
        self.colors = np.array([p.get("color") or review.DEFAULT for p in parts], float)[:, :3]

    def pose(self, xf):
        """(T, N, O) of every shown part placed by `xf` {k: {"R", "pivot",
        "t", "clip": (point, normal), "hidden"}} (missing k = at home)."""
        Ts, Ns, Os = [], [], []
        for k in range(len(self.parts)):
            x = xf.get(k) or {}
            if x.get("hidden"):
                continue
            T, N = self.T[k], self.N[k]
            R = x.get("R")
            if R is not None:
                pv = np.asarray(x.get("pivot", self.centre), float)
                T = (T - pv) @ R.T + pv
                N = N @ R.T
            t = x.get("t")
            if t is not None:
                T = T + np.asarray(t, float)
            O = np.full(len(T), k, np.int32)
            clip = x.get("clip")
            if clip is not None and len(T):
                T, N, O = review.clip_plane(T, N, O, np.ones(len(self.parts), bool),
                                            clip[0], clip[1])
            if len(T):
                Ts.append(T)
                Ns.append(N)
                Os.append(O)
        if not Ts:
            return np.zeros((0, 3, 3)), np.zeros((0, 3, 3)), np.zeros(0, np.int32)
        return np.concatenate(Ts), np.concatenate(Ns), np.concatenate(Os)


# ---------------------------------------------------------------- camera
def camera(scene, az, el, zoom=1.0, target=None, persp=4.2):
    """Perspective camera orbiting the product: az 0 looks at the front
    (from -Y), positive turns toward the viewer's right side; el above
    the floor, degrees. zoom > 1 is closer."""
    a, e = math.radians(az), math.radians(el)
    v = np.array([-math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)])
    ctr = scene.centre if target is None else np.asarray(target, float)
    cam = review.camera(v, (0, 0, 1), ctr, 1.0, False)
    cam["dist"] = persp * scene.radius
    cam["zoom"] = zoom
    return cam


def _px(cam, scene, W, H):
    """px per mm at the target plane, and the image centre."""
    s = (min(W, H) * 0.5) / (scene.radius * 1.12) * cam.get("zoom", 1.0)
    return s, W / 2.0, H / 2.0 + (0.04 - cam.get("shift", 0.0)) * H


def project_px(cam, scene, W, H, P):
    """World points (...,3) -> pixel x, y (and depth, larger = nearer)."""
    s, ox, oy = _px(cam, scene, W, H)
    x, y, d = review.project(cam, np.asarray(P, float))
    return ox + s * x, oy - s * y, d


# ---------------------------------------------------------------- shadow
class Shadow(object):
    """Key-light depth map over a FIXED box (the assembled product, grown),
    so parts flying in do not change its resolution frame to frame."""

    def __init__(self, scene, T, O, light, res=SHADOW_RES):
        self.cam = review.camera(light, (0, 0, 1) if abs(light[2]) < 0.95 else (0, 1, 0),
                                 scene.centre, 1.0)
        r = scene.radius * 1.6
        self.lo = np.array([-r, -r])
        self.s = (res - 1) / (2 * r)
        self.res = res
        self.bias = scene.diag * 0.006
        if not len(T):
            self.zb = np.full((res, res), -np.inf)
            return
        x, y, d = review.project(self.cam, T)
        xy = np.stack([(x - self.lo[0]) * self.s, (y - self.lo[1]) * self.s], -1)
        T2, _N, _O, xy = review._bisect(T, T, O, xy, review.SPLIT_PX)
        _, _, d = review.project(self.cam, T2)
        _, _, self.zb = review.rasterize(xy, d, res, res)

    lit = review.ShadowMap.lit


# ---------------------------------------------------------------- frame
def render(scene, xf, cam, env, W, H, ss=2, t=0.0, glow=None, shadow=None):
    """One frame: float RGB (H, W, 3) in 0..1.

    xf: part poses (Scene.pose). glow: {k: (r, g, b) emissive}. shadow: a
    Shadow (None: built here from this pose). t: seconds, for the stage's
    own motion (stars, bokeh)."""
    Ws, Hs = W * ss, H * ss
    T, N, O = scene.pose(xf)
    key = np.asarray(env["key"], float)
    key = key / np.linalg.norm(key)
    if shadow is None:
        shadow = Shadow(scene, T, O, key)
    s, ox, oy = _px(cam, scene, Ws, Hs)
    # the stage is smooth: drawn at the output size (MEASURED: half the
    # frame's time at 2x), only the product is supersampled
    img = stage.backdrop(env, scene, cam, W, H, s / ss, ox / ss, oy / ss, shadow, t)
    if ss > 1:
        img = img.repeat(ss, 0).repeat(ss, 1)
    glow_img = np.zeros((Hs, Ws, 3))
    if len(T):
        # perspective: drop what is at or behind the eye
        _, _, d0 = review.project(cam, T)
        keep = (d0 < cam["dist"] * 0.8).all(1)
        T, N, O = T[keep], N[keep], O[keep]
    if len(T):
        x, y, _ = review.project(cam, T)
        xy = np.stack([ox + s * x, oy - s * y], -1)
        T2, N2, O2, xy = review._bisect(T, N, O, xy, SPLIT_PX)
        _, _, d = review.project(cam, T2)
        tid, bc, zb = review.rasterize(xy, d, Ws, Hs)
        fg = tid >= 0
        if fg.any():
            _shade(scene, env, cam, img, glow_img, fg, tid, bc, zb, T2, N2, O2, key, shadow, glow,
                   Ws, Hs)
    # bloom: emissive parts and the stage's own lights
    if glow_img.any():
        r = max(2, int(0.018 * max(Ws, Hs)))
        b = np.stack([review._box_blur(review._box_blur(glow_img[..., c], r), r)
                      for c in range(3)], -1)
        img = img + glow_img * 0.35 + b * 1.1
    img = stage.grade(env, img)
    img = np.clip(img, 0, 1)
    return img.reshape(H, ss, W, ss, 3).mean((1, 3))


def _shade(scene, env, cam, img, glow_img, fg, tid, bc, zb, T2, N2, O2, key, shadow, glow,
           Ws, Hs):
    t = tid[fg]
    w = bc[fg]
    P = np.einsum("nk,nkj->nj", w, T2[t])
    n = np.einsum("nk,nkj->nj", w, N2[t])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-9)[:, None]
    eye = cam["ctr"] + cam["v"] * cam["dist"]
    vd = eye - P
    vd /= np.maximum(np.linalg.norm(vd, axis=1), 1e-9)[:, None]
    flip = np.einsum("ij,ij->i", n, vd) < 0
    n[flip] *= -1
    obj = O2[t]
    alb = scene.colors[obj].copy()
    clear = np.array([float(p.get("transparency") or 0) for p in scene.parts])[obj] / 100.0
    if clear.any():                    # see-through parts: lighter, cooler
        alb = alb * (1 - 0.45 * clear[:, None]) + 0.45 * clear[:, None] * np.array([0.92, 0.96, 1.0])
    lit = shadow.lit(P + n * scene.diag * 0.002)
    ndl = np.clip(n @ key, 0, 1)
    hemi = 0.5 + 0.5 * n[:, 2]
    sky, gnd = np.asarray(env["sky_light"], float), np.asarray(env["ground_light"], float)
    amb = (env.get("ambient", 0.42) * (gnd + (sky - gnd) * hemi[:, None]))
    kc = np.asarray(env["key_color"], float)
    fill = np.asarray(env.get("fill", (0.7, 0.3, 0.35)), float)
    fill = fill / np.linalg.norm(fill)
    fc = np.asarray(env.get("fill_color", (0.85, 0.9, 1.0)), float)
    h = key[None] + vd
    h /= np.maximum(np.linalg.norm(h, axis=1), 1e-9)[:, None]
    spec = env.get("spec", 0.28) * np.clip(np.einsum("ij,ij->i", n, h), 0, 1) ** 56 * lit
    fres = env.get("rim", 0.14) * (1 - np.clip(np.einsum("ij,ij->i", n, vd), 0, 1)) ** 3
    rim_c = np.asarray(env.get("rim_color", (1, 1, 1)), float)
    rgb = alb * (amb + (0.66 * ndl * lit)[:, None] * kc
                 + (0.18 * np.clip(n @ fill, 0, 1))[:, None] * fc) \
        + spec[:, None] * kc + fres[:, None] * rim_c
    if glow:
        em = np.zeros((len(P), 3))
        for k, c in glow.items():
            m = obj == k
            if m.any():
                em[m] = np.asarray(c, float)
        if em.any():
            rgb = rgb + em
            g = np.zeros((Hs, Ws, 3))
            g[fg] = em
            glow_img += g
    # depth-darkening AO, as review.render_view
    zf = np.where(fg, zb, np.nanmin(zb[fg]))
    r = max(2, int(0.012 * max(Ws, Hs)))
    ao = np.clip((review._box_blur(zf, r) - zf) / (0.03 * max(scene.diag, 1e-6)), 0, 1)
    shade = np.zeros((Hs, Ws, 3))
    shade[fg] = rgb
    shade *= (1 - 0.40 * ao)[..., None]
    img[fg] = shade[fg]
    # outlines: object boundaries, depth jumps, creases (review's, softer)
    ink_k = env.get("ink_strength", 0.6)
    if ink_k <= 0:
        return
    oid = np.full((Hs, Ws), -1)
    oid[fg] = obj
    nb = np.zeros((Hs, Ws, 3))
    nb[fg] = n
    line = np.zeros((Hs, Ws))
    jump = 0.012 * scene.diag
    for dy, dx in ((0, 1), (1, 0), (1, 1)):
        a_id, b_id = oid[:Hs - dy, :Ws - dx], oid[dy:, dx:]
        za, zb2 = zf[:Hs - dy, :Ws - dx], zf[dy:, dx:]
        na, nb2 = nb[:Hs - dy, :Ws - dx], nb[dy:, dx:]
        sil = (a_id != b_id) & ((a_id >= 0) | (b_id >= 0))
        dep = (a_id == b_id) & (a_id >= 0) & (np.abs(za - zb2) > jump)
        cre = (a_id == b_id) & (a_id >= 0) & ((na * nb2).sum(-1) < 0.82)
        e = np.maximum(sil * 1.0, np.maximum(dep * 0.9, cre * 0.5))
        line[:Hs - dy, :Ws - dx] = np.maximum(line[:Hs - dy, :Ws - dx], e)
    line = np.maximum.reduce([line, np.roll(line, 1, 1), np.roll(line, 1, 0)])
    ink = np.asarray(env.get("ink", (0.10, 0.11, 0.13)), float)
    a = (ink_k * line)[..., None]
    img *= (1 - a)
    img += ink * a
