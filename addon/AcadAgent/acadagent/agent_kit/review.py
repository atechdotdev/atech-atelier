"""review - the design-review pictures ./check draws of every build (R230).

check.py calls review.draw(items, out_dir, ...) after model.py ran - on a
pass, on a failed check AND when model.py raised (the objects it made
before the error). It writes, next to check.png:

  review.png          the six-view sheet: 3/4 hero (front-left-above),
                      FRONT, RIGHT, REAR 3/4, LEFT, TOP. The four flat
                      views share ONE drawing scale (they compare), each
                      panel has a scale bar and an axis triad, the footer
                      a legend (label -> colour) and the notes; a red
                      banner says FAILED CHECK or PARTIAL BUILD
  review_inside.png   a cutaway: the agent's bodies cut at the board's
                      plane (the half on the modules' side removed, cut
                      walls hatched), the board, modules and cables whole -
                      to judge how the electronics fit
  review_<label>.png  one close-up per label model.py lists in
                      REVIEW_CLOSEUPS (at most 4): parts in front of it
                      cut away
  check.png           the hero panel alone (the old name, R230 compat)

Colours: what the script chose (the recorded ViewObject.ShapeColor),
else the Atech role colour (board near-black, module graphite, cable
the colour atech_ports.cable() sets), else Studio's PALETTE in Studio's
own order (check.py decides; build._colour is the rule).

Pure numpy + PIL (both in the bundled FreeCAD python); no OpenGL, no GUI.
A real z-buffer (no painter's order), smooth normals inside each B-rep
face, hard creases between faces, key + fill + sky light, a soft shadow
map on the 3/4 views, depth-darkening AO, and image-space outlines
(silhouettes, object boundaries, creases).
"""
import os
import re
import time

import numpy as np

PALETTE = [(0.36, 0.60, 0.86), (0.90, 0.62, 0.30), (0.42, 0.72, 0.50),
           (0.70, 0.52, 0.86), (0.86, 0.44, 0.44), (0.38, 0.76, 0.78),
           (0.84, 0.74, 0.36), (0.62, 0.62, 0.66)]          # = build.PALETTE
DEFAULT = (0.80, 0.80, 0.80)      # FreeCAD's default ShapeColor (one body)
BOARD = (0.16, 0.17, 0.20)        # frame-2.glb "board" (near-black satin), lifted
MODULE = (0.30, 0.31, 0.34)       # module housings: graphite
CABLE = (0.85, 0.85, 0.82)        # = atech_ports.cable()'s own ShapeColor
USER = (0.74, 0.75, 0.78)         # the user's own objects (context)
PROBLEM = (0.95, 0.15, 0.15)
BG_TOP, BG_BOT = np.array([0.97, 0.97, 0.98]), np.array([0.86, 0.87, 0.89])

LINEAR, ANGULAR = 0.0025, 0.25    # finer than the old check.png (0.004 / 0.35)
SPLIT_PX = 64.0                   # R230: no triangle wider than this on screen
MAX_TRIANGLES = 1_500_000         # beyond this the sheet is not drawn
MAX_CLOSEUPS = 4
THREADS = 3                       # MEASURED r3 (18 cores): 3 fastest, 6 slower
EPS = 1e-9


def available():
    """None when numpy and PIL import, else why not (check.py then falls
    back to its old matplotlib render)."""
    try:
        import numpy                                    # noqa: F401
        from PIL import Image, ImageDraw, ImageFont     # noqa: F401
        if os.environ.get("ATECH_REVIEW_SABOTAGE") == "nopil":
            raise ImportError("PIL (ATECH_REVIEW_SABOTAGE, a test)")
    except Exception as exc:                            # noqa: BLE001
        return "numpy/PIL missing: %s" % exc
    return None


def safe_label(label):
    """review_<label>.png: the label as a file-name part."""
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(label)).strip("._") or "part"
    return s[:48]


# ---------------------------------------------------------------- geometry
def _shape_tris(shape):
    """(T Nx3x3, Nrm Nx3x3) with smooth normals inside each B-rep face and
    hard creases between faces."""
    diag = max(shape.BoundBox.DiagonalLength, 1.0)
    tol = diag * LINEAR
    try:
        # sets the shape's triangulation with an ANGULAR limit too, which
        # face.tessellate() below then reuses (curved faces stay smooth)
        import MeshPart
        MeshPart.meshFromShape(Shape=shape, LinearDeflection=tol,
                               AngularDeflection=ANGULAR, Relative=False)
    except Exception:                                   # noqa: BLE001
        pass
    Ts, Ns = [], []
    for f in shape.Faces:
        try:
            pts, faces = f.tessellate(tol)
        except Exception:                               # noqa: BLE001
            continue
        if not pts or not faces:
            continue
        P = np.array([(p.x, p.y, p.z) for p in pts], float)
        F = np.array(faces, int)
        T = P[F]
        fn = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])    # area-weighted
        vn = np.zeros_like(P)
        for j in range(3):
            np.add.at(vn, F[:, j], fn)
        ln = np.linalg.norm(vn, axis=1)
        ln[ln == 0] = 1
        vn /= ln[:, None]
        Ts.append(T)
        Ns.append(vn[F])
    if not Ts:
        return None, None
    return np.concatenate(Ts), np.concatenate(Ns)


def _mesh_tris(mesh):
    pts, faces = mesh.Topology
    if not pts or not faces:
        return None, None
    P = np.array([(p.x, p.y, p.z) for p in pts], float)
    T = P[np.array(faces, int)]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    ln = np.linalg.norm(n, axis=1)
    ln[ln == 0] = 1
    n /= ln[:, None]
    return T, np.repeat(n[:, None, :], 3, axis=1)


def scene_from(items):
    """items: [{"label", "shape"|"mesh", "color", "problem": bool, "kind":
    "body"|"board"|"module"|"cable"|"user"}] -> one scene dict (triangles,
    normals, object ids, colours, bounds)."""
    Ts, Ns, ids, cols, labels, probs, kinds = [], [], [], [], [], [], []
    for it in items:
        try:
            if it.get("shape") is not None:
                T, N = _shape_tris(it["shape"])
            else:
                T, N = _mesh_tris(it["mesh"])
        except Exception:                               # noqa: BLE001
            T = None
        if T is None or not len(T):
            continue
        k = len(labels)
        Ts.append(T)
        Ns.append(N)
        ids.append(np.full(len(T), k, np.int32))
        cols.append(tuple(it.get("color") or DEFAULT)[:3])
        labels.append(str(it.get("label")))
        probs.append(bool(it.get("problem")))
        kinds.append(it.get("kind") or "body")
    if not Ts:
        return None
    T = np.concatenate(Ts)
    P = T.reshape(-1, 3)
    return {"T": T, "N": np.concatenate(Ns), "obj": np.concatenate(ids),
            "colors": np.array(cols, float), "labels": labels, "kinds": kinds,
            "problem": np.array(probs), "min": P.min(0), "max": P.max(0)}


# ---------------------------------------------------------------- camera
def camera(view, up, ctr, diag, persp=False):
    v = np.asarray(view, float)
    v = v / np.linalg.norm(v)
    up = np.asarray(up, float)
    if abs(float(np.dot(up, v))) > 0.97:
        up = np.array([0.0, 1.0, 0.0]) if abs(v[1]) < 0.9 else np.array([1.0, 0, 0])
    r = np.cross(up, v)
    r /= np.linalg.norm(r)
    u = np.cross(v, r)
    return {"v": v, "r": r, "u": u, "ctr": np.asarray(ctr, float),
            "dist": (2.6 * diag) if persp else None}


def project(cam, P):
    """world (...,3) -> (x, y, depth) with depth larger = nearer."""
    Q = P - cam["ctr"]
    x, y, d = Q @ cam["r"], Q @ cam["u"], Q @ cam["v"]
    if cam["dist"]:
        f = cam["dist"] / np.maximum(cam["dist"] - d, 1e-6)
        x, y = x * f, y * f
    return x, y, d


# ---------------------------------------------------------------- raster
def _bisect(T, N, O, xy, limit, cap=3_000_000):
    """Halve triangles whose longest SCREEN edge exceeds `limit` px (R230:
    a big slanted triangle tests every pixel of its bounding box - MEASURED
    r3: the 1 720-triangle enclosure took 5.1 s, slower than 66 k car
    triangles; perspective views also need it for screen-linear depth)."""
    for _ in range(16):
        e = np.stack([np.linalg.norm(xy[:, 1] - xy[:, 0], axis=1),
                      np.linalg.norm(xy[:, 2] - xy[:, 1], axis=1),
                      np.linalg.norm(xy[:, 0] - xy[:, 2], axis=1)], 1)
        big = e.max(1) > limit
        if not big.any() or len(T) > cap:
            break
        k = e[big].argmax(1)
        idx = np.stack([k, (k + 1) % 3, (k + 2) % 3], 1)[:, :, None]

        def split(A):
            R = np.take_along_axis(A[big], idx, axis=1)
            m = (R[:, 0] + R[:, 1]) / 2
            return np.concatenate([A[~big], np.stack([R[:, 0], m, R[:, 2]], 1),
                                   np.stack([m, R[:, 1], R[:, 2]], 1)])
        T, N, xy = split(T), split(N), split(xy)
        O = np.concatenate([O[~big], O[big], O[big]])
    return T, N, O, xy


def clip_plane(T, N, O, cut_obj, p, n):
    """Cut the triangles of the objects flagged in cut_obj (bool per object)
    by the plane through p with normal n: the part on the +n side goes.
    Triangles of other objects are kept whole. Returns (T, N, O)."""
    n = np.asarray(n, float)
    sel = cut_obj[O]
    keep_T, keep_N, keep_O = [T[~sel]], [N[~sel]], [O[~sel]]
    Tc, Nc, Oc = T[sel], N[sel], O[sel]
    s = (Tc - np.asarray(p, float)) @ n            # (M, 3), > 0 = removed side
    inside = s <= 0
    cnt = inside.sum(1)
    keep_T.append(Tc[cnt == 3])
    keep_N.append(Nc[cnt == 3])
    keep_O.append(Oc[cnt == 3])
    for want in (1, 2):
        m = cnt == want
        if not m.any():
            continue
        # roll so v0 is the odd one out: the one inside (1) / outside (2)
        k = (inside[m] if want == 1 else ~inside[m]).argmax(1)
        idx = np.stack([k, (k + 1) % 3, (k + 2) % 3], 1)
        A = np.take_along_axis(Tc[m], idx[:, :, None], axis=1)
        B = np.take_along_axis(Nc[m], idx[:, :, None], axis=1)
        S = np.take_along_axis(s[m], idx, axis=1)

        def at(i, j, X):
            t = (S[:, i] / np.where(np.abs(S[:, i] - S[:, j]) < EPS, EPS,
                                    S[:, i] - S[:, j]))[:, None]
            return X[:, i] + t * (X[:, j] - X[:, i])
        p01, p02 = at(0, 1, A), at(0, 2, A)
        q01, q02 = at(0, 1, B), at(0, 2, B)
        if want == 1:
            keep_T.append(np.stack([A[:, 0], p01, p02], 1))
            keep_N.append(np.stack([B[:, 0], q01, q02], 1))
            keep_O.append(Oc[m])
        else:
            keep_T += [np.stack([p01, A[:, 1], A[:, 2]], 1),
                       np.stack([p01, A[:, 2], p02], 1)]
            keep_N += [np.stack([q01, B[:, 1], B[:, 2]], 1),
                       np.stack([q01, B[:, 2], q02], 1)]
            keep_O += [Oc[m], Oc[m]]
    return np.concatenate(keep_T), np.concatenate(keep_N), np.concatenate(keep_O)


def rasterize(xy, depth, W, H, chunk=3_000_000, zcap=None):
    """Exact z-buffer of screen triangles (N,3,2 px; depth N,3, larger =
    nearer). Returns (tri id HxW, -1 = empty; barycentrics HxWx3; depth HxW).

    Candidates are the pixels of each triangle's own bounding box (bucketed
    by width x height, powers of two); the winner per pixel is one
    np.minimum.at over an int64 key (quantised depth << 26 | triangle id),
    so nothing is sorted; barycentrics are recomputed for winners only."""
    xs, ys = xy[..., 0], xy[..., 1]
    x0 = np.clip(np.floor(xs.min(1)), 0, W - 1).astype(np.int32)
    x1 = np.clip(np.ceil(xs.max(1)), 0, W - 1).astype(np.int32)
    y0 = np.clip(np.floor(ys.min(1)), 0, H - 1).astype(np.int32)
    y1 = np.clip(np.ceil(ys.max(1)), 0, H - 1).astype(np.int32)
    a, b, c = xy[:, 0], xy[:, 1], xy[:, 2]
    area = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    ok = (np.abs(area) > 1e-9) & (xs.max(1) >= 0) & (xs.min(1) < W) \
        & (ys.max(1) >= 0) & (ys.min(1) < H)
    if len(xy) >= 2 ** 26:
        raise ValueError("too many triangles for one view")
    dmin, dmax = (depth.min(), depth.max()) if len(depth) else (0.0, 1.0)
    q = (2 ** 26 - 1) / max(dmax - dmin, 1e-9)
    buf = np.full(W * H, np.iinfo(np.int64).max, np.int64)
    ex = x1 - x0 + 1
    ey = y1 - y0 + 1
    bx = np.ceil(np.log2(np.maximum(ex, 1))).astype(int)
    by = np.ceil(np.log2(np.maximum(ey, 1))).astype(int)
    key = np.where(ok, bx * 64 + by, -1)
    inv = 1.0 / np.where(ok, area, 1.0)
    # R230: each barycentric is a plane over the pixel grid. Per triangle
    # its value at the bounding box's first pixel centre (float64, then an
    # O(1) number) and its x / y steps, so a candidate pixel costs two
    # multiply-adds per weight, not the edge function's six operations.
    X0, Y0 = x0 + 0.5, y0 + 0.5

    def plane(p, r):                  # edge p -> r: w(px, py) = k + px*u + py*v
        u = (p[:, 1] - r[:, 1]) * inv
        v = (r[:, 0] - p[:, 0]) * inv
        k = (p[:, 0] * r[:, 1] - p[:, 1] * r[:, 0]) * inv
        return ((k + X0 * u + Y0 * v).astype(np.float32), u.astype(np.float32),
                v.astype(np.float32))
    c0, u0, v0 = plane(b, c)
    c1, u1, v1 = plane(c, a)
    room_x = (W - x0).astype(np.float32)          # offsets past the image edge
    room_y = (H - y0).astype(np.float32)
    for kk in np.unique(key[key >= 0]):
        sel = np.nonzero(key == kk)[0]
        kx, ky = 1 << int(kk // 64), 1 << int(kk % 64)
        oy, ox = np.mgrid[0:ky, 0:kx]
        ox = ox.ravel().astype(np.float32)[None]
        oy = oy.ravel().astype(np.float32)[None]
        step = max(1, chunk // (kx * ky))
        for s0 in range(0, len(sel), step):
            I = sel[s0:s0 + step]
            w0 = c0[I, None] + u0[I, None] * ox + v0[I, None] * oy
            w1 = c1[I, None] + u1[I, None] * ox + v1[I, None] * oy
            m = (w0 >= -1e-5) & (w1 >= -1e-5) & (w0 + w1 <= 1 + 1e-5)
            if kx > 1:
                m &= ox < room_x[I, None]
            if ky > 1:
                m &= oy < room_y[I, None]
            r_, c_ = np.nonzero(m)
            if not len(r_):
                continue
            ti = I[r_]
            W0, W1 = w0[r_, c_], w1[r_, c_]
            D = depth[ti]
            z = D[:, 2] + W0 * (D[:, 0] - D[:, 2]) + W1 * (D[:, 1] - D[:, 2])
            px = x0[ti].astype(np.int64) + ox[0, c_].astype(np.int64)
            py = y0[ti].astype(np.int64) + oy[0, c_].astype(np.int64)
            if zcap is not None:          # cutaway: drop fragments nearer than the cap
                keep = z <= zcap[ti]
                z, ti, px, py = z[keep], ti[keep], px[keep], py[keep]
            pix = py * W + px
            code = (np.clip((dmax - z) * q, 0, 2 ** 26 - 1).astype(np.int64) << 26) | ti
            np.minimum.at(buf, pix, code)
    hit = buf != np.iinfo(np.int64).max
    tid = np.full(W * H, -1, np.int64)
    tid[hit] = buf[hit] & (2 ** 26 - 1)
    bc = np.zeros((W * H, 3))
    zb = np.full(W * H, -np.inf)
    if hit.any():
        P = np.nonzero(hit)[0]
        fx, fy = P % W + 0.5, P // W + 0.5
        t = tid[hit]
        A, B, C, iv = a[t], b[t], c[t], inv[t]
        w0 = ((B[:, 0] - fx) * (C[:, 1] - fy) - (B[:, 1] - fy) * (C[:, 0] - fx)) * iv
        w1 = ((C[:, 0] - fx) * (A[:, 1] - fy) - (C[:, 1] - fy) * (A[:, 0] - fx)) * iv
        w = np.clip(np.stack([w0, w1, 1 - w0 - w1], 1), 0, 1)
        w /= np.maximum(w.sum(1), 1e-9)[:, None]
        bc[hit] = w
        zb[hit] = (w * depth[t]).sum(1)
    return tid.reshape(H, W), bc.reshape(H, W, 3), zb.reshape(H, W)


def _box_blur(img, r):
    """Separable box blur (r px) of a 2D float image, via cumulative sums."""
    out = img
    for ax in (0, 1):
        p = np.pad(out, [(r + 1, r) if a == ax else (0, 0) for a in (0, 1)], mode="edge")
        c = np.cumsum(p, axis=ax)
        hi = np.take(c, np.arange(2 * r + 1, c.shape[ax]), axis=ax)
        lo = np.take(c, np.arange(0, c.shape[ax] - 2 * r - 1), axis=ax)
        out = (hi - lo) / (2 * r + 1)
    return out


# ---------------------------------------------------------------- shadow
class ShadowMap:
    """Orthographic depth map from the key light, shared by every view."""

    def __init__(self, scene, light, res=1024):
        T = scene["T"]
        self.cam = camera(light, (0, 0, 1) if abs(light[2]) < 0.95 else (0, 1, 0),
                          (scene["min"] + scene["max"]) / 2, 1.0)
        x, y, d = project(self.cam, T)
        diag = float(np.linalg.norm(scene["max"] - scene["min"]))
        self.lo = np.array([x.min(), y.min()]) - 0.02 * diag
        span = max(x.max() - x.min(), y.max() - y.min()) + 0.04 * diag
        self.s = (res - 1) / max(span, 1e-6)
        self.res = res
        xy = np.stack([(x - self.lo[0]) * self.s, (y - self.lo[1]) * self.s], -1)
        T2, _N, _O, xy = _bisect(T, T, scene["obj"], xy, SPLIT_PX)
        _, _, d = project(self.cam, T2)
        _, _, zb = rasterize(xy, d, res, res)
        self.zb = zb
        self.bias = diag * 0.006

    def lit(self, P):
        """fraction lit (0..1, 3x3 PCF) of world points P (...,3)."""
        x, y, d = project(self.cam, P)
        ix = (x - self.lo[0]) * self.s
        iy = (y - self.lo[1]) * self.s
        acc = np.zeros(d.shape)
        for dx in (-1.5, 0, 1.5):
            for dy in (-1.5, 0, 1.5):
                jx = np.clip(np.round(ix + dx).astype(int), 0, self.res - 1)
                jy = np.clip(np.round(iy + dy).astype(int), 0, self.res - 1)
                inside = (ix + dx >= 0) & (ix + dx < self.res) & (iy + dy >= 0) & (iy + dy < self.res)
                occ = self.zb[jy, jx] > d + self.bias
                acc += ~(occ & inside)
        return acc / 9.0


# ---------------------------------------------------------------- one view
KEY = np.array([-0.45, -0.65, 0.85])     # toward the light: front-left-above
KEY /= np.linalg.norm(KEY)
FILL = np.array([0.7, 0.3, 0.35])
FILL /= np.linalg.norm(FILL)


def fit_scale(scene, cam, W, H, margin=0.08):
    x, y, _ = project(cam, scene["T"].reshape(-1, 3)[::7])
    return min(W * (1 - 2 * margin) / max(x.max() - x.min(), 1e-6),
               H * (1 - 2 * margin) / max(y.max() - y.min(), 1e-6))


def render_view(scene, cam, W, H, shadow, ss=2, margin=0.08, fit=None,
                focus=None, scale=None, section=None):
    """RGB float image (H, W, 3), the px-per-mm scale and the offsets.

    shadow None = the key light follows the camera (upper left of the
    viewer), no cast shadows. focus = object index: parts in front of its
    middle depth are cut away (a close-up of a part inside a case).
    section = bool per object: its back faces (a wall seen through a cut)
    are drawn hatched, as a section."""
    Ws, Hs = W * ss, H * ss
    T, N, O = scene["T"], scene["N"], scene["obj"]
    if shadow is None:
        key = -0.45 * cam["r"] + 0.55 * cam["u"] + 0.70 * cam["v"]
        key /= np.linalg.norm(key)
    else:
        key = KEY
    diag = float(np.linalg.norm(scene["max"] - scene["min"]))
    if fit is not None:
        lo, hi = fit
        corners = np.array([[a, b, c] for a in (lo[0], hi[0]) for b in (lo[1], hi[1])
                            for c in (lo[2], hi[2])])
    else:
        corners = T.reshape(-1, 3)[::7]
    cx, cy, _ = project(cam, corners)
    s = min(Ws * (1 - 2 * margin) / max(cx.max() - cx.min(), 1e-6),
            Hs * (1 - 2 * margin) / max(cy.max() - cy.min(), 1e-6))
    if scale is not None:                 # a shared drawing scale (px/mm at 1x)
        s = scale * ss
    ox = Ws / 2 - s * (cx.max() + cx.min()) / 2
    oy = Hs / 2 + s * (cy.max() + cy.min()) / 2

    x, y, _ = project(cam, T)
    xy = np.stack([ox + s * x, oy - s * y], -1)
    T2, N2, O2, xy = _bisect(T, N, O, xy, SPLIT_PX)
    _, _, d = project(cam, T2)
    zcap = None
    if focus is not None:                 # section plane at the part's middle depth
        near = float(np.median(d[O2 == focus]))
        zcap = np.where(O2 == focus, np.inf, near)
    tid, bc, zb = rasterize(xy, d, Ws, Hs, zcap=zcap)
    fg = tid >= 0
    t = tid[fg]
    w = bc[fg]
    P = np.einsum("nk,nkj->nj", w, T2[t])
    n = np.einsum("nk,nkj->nj", w, N2[t])
    n /= np.maximum(np.linalg.norm(n, axis=1), 1e-9)[:, None]
    if cam["dist"]:                       # perspective: toward the eye
        eye = cam["ctr"] + cam["v"] * cam["dist"]
        vd = eye - P
        vd /= np.maximum(np.linalg.norm(vd, axis=1), 1e-9)[:, None]
    else:
        vd = np.broadcast_to(cam["v"], P.shape)
    flip = np.einsum("ij,ij->i", n, vd) < 0
    n[flip] *= -1
    obj = O2[t]
    alb = scene["colors"][obj]
    lit = shadow.lit(P + n * diag * 0.002) if shadow is not None else np.ones(len(P))
    ndl = np.clip(n @ key, 0, 1)
    hemi = 0.5 + 0.5 * n[:, 2]
    amb = (0.42 + 0.20 * hemi)[:, None] * np.array([1.0, 1.0, 1.02])
    h = key[None] + vd
    h /= np.maximum(np.linalg.norm(h, axis=1), 1e-9)[:, None]
    spec = 0.22 * np.clip(np.einsum("ij,ij->i", n, h), 0, 1) ** 48 * lit
    fres = 0.10 * (1 - np.clip(np.einsum("ij,ij->i", n, vd), 0, 1)) ** 3
    rgb = alb * (amb + (0.62 * ndl * lit)[:, None] + (0.16 * np.clip(n @ FILL, 0, 1))[:, None]) \
        + (spec + fres)[:, None]
    if section is not None:               # cut walls: hatched section colour
        sec = flip & section[obj]
        if sec.any():
            py, px = np.nonzero(fg)
            stripe = ((px[sec] + py[sec]) // max(2, ss * 3)) % 3 == 0
            base = alb[sec] * 0.55 + 0.12
            base[stripe] *= 0.55
            rgb[sec] = base
    # --- image buffers
    img = np.empty((Hs, Ws, 3))
    gy = np.linspace(0, 1, Hs)[:, None, None]
    img[:] = BG_TOP * (1 - gy) + BG_BOT * gy
    # ground plane with the contact shadow (views that look down)
    zmin = scene["min"][2]
    if shadow is not None and cam["v"][2] > 0.08:
        yy, xx = np.mgrid[0:Hs, 0:Ws]
        gx, gyy = (xx + 0.5 - ox) / s, (oy - yy - 0.5) / s
        if cam["dist"]:
            eye = cam["ctr"] + cam["v"] * cam["dist"]
            Pp = cam["ctr"] + gx[..., None] * cam["r"] + gyy[..., None] * cam["u"]
            D = Pp - eye
        else:
            Pp = cam["ctr"] + gx[..., None] * cam["r"] + gyy[..., None] * cam["u"] \
                + cam["v"] * diag * 3
            D = np.broadcast_to(-cam["v"], Pp.shape)
        tt = (zmin - Pp[..., 2]) / np.where(np.abs(D[..., 2]) < 1e-9, -1e-9, D[..., 2])
        G = Pp + D * tt[..., None]
        bgm = ~fg & (tt > 0)
        if bgm.any():
            sh = shadow.lit(G[bgm])
            rad = np.linalg.norm((G[bgm] - (scene["min"] + scene["max"]) / 2)[:, :2], axis=1)
            fade = np.clip(1 - rad / (1.4 * diag), 0, 1)
            dark = (1 - sh) * 0.32 * fade
            img[bgm] *= (1 - dark)[:, None]
    # depth-darkening AO: pixels behind their neighbourhood
    zf = np.where(fg, zb, np.nanmin(zb[fg]) if fg.any() else 0)
    r = max(2, int(0.012 * max(Ws, Hs)))
    ao = np.clip((_box_blur(zf, r) - zf) / (0.03 * max(diag, 1e-6)), 0, 1)
    shade_img = np.zeros((Hs, Ws, 3))
    shade_img[fg] = rgb
    shade_img *= (1 - 0.45 * ao)[..., None]
    img[fg] = shade_img[fg]
    # --- outlines: object boundaries, depth jumps, creases
    oid = np.full((Hs, Ws), -1)
    oid[fg] = obj
    nb = np.zeros((Hs, Ws, 3))
    nb[fg] = n
    line = np.zeros((Hs, Ws))
    jump = 0.012 * diag
    for dy, dx in ((0, 1), (1, 0), (1, 1)):
        a_id, b_id = oid[:Hs - dy, :Ws - dx], oid[dy:, dx:]
        za, zb2 = zf[:Hs - dy, :Ws - dx], zf[dy:, dx:]
        na, nb2 = nb[:Hs - dy, :Ws - dx], nb[dy:, dx:]
        sil = (a_id != b_id)
        dep = (a_id == b_id) & (a_id >= 0) & (np.abs(za - zb2) > jump)
        cre = (a_id == b_id) & (a_id >= 0) & ((na * nb2).sum(-1) < 0.82)
        e = np.maximum(sil * 1.0, np.maximum(dep * 0.9, cre * 0.55))
        line[:Hs - dy, :Ws - dx] = np.maximum(line[:Hs - dy, :Ws - dx], e)
    line = np.maximum.reduce([line, np.roll(line, 1, 1), np.roll(line, 1, 0),
                              np.roll(np.roll(line, 1, 0), 1, 1) * 0.8])
    ink = np.array([0.10, 0.11, 0.13])
    img = img * (1 - 0.85 * line[..., None]) + ink * 0.85 * line[..., None]
    # problem parts: a red rim (R230: the guilty parts of a failed check)
    if scene["problem"].any():
        bad = np.zeros((Hs, Ws), bool)
        bad[fg] = scene["problem"][obj]
        rim = bad & (line > 0.5)
        rim |= np.roll(rim, 1, 0) | np.roll(rim, 1, 1)
        rim |= np.roll(rim, 1, 0) | np.roll(rim, 1, 1)
        img[rim] = PROBLEM
    img = np.clip(img, 0, 1)
    img = img.reshape(H, ss, W, ss, 3).mean((1, 3))     # box-filter down
    return img, s / ss


# ---------------------------------------------------------------- sheet
HERO = ("3/4 HERO  front-left-above", (-0.62, -1.0, 0.62), (0, 0, 1), True)
VIEWS = [  # name, toward-the-viewer, up, perspective
    HERO,
    ("FRONT  (from -Y)", (0, -1, 0), (0, 0, 1), False),
    ("RIGHT  (from +X)", (1, 0, 0), (0, 0, 1), False),
    ("REAR 3/4  back-right-above", (0.8, 1.0, 0.55), (0, 0, 1), True),
    ("LEFT  (from -X)", (-1, 0, 0), (0, 0, 1), False),
    ("TOP  (from +Z, +Y up)", (0, 0, 1), (0, 1, 0), False),
]

_FONTS = {}


def _font(size):
    if size not in _FONTS:
        from PIL import ImageFont
        try:
            _FONTS[size] = ImageFont.load_default(size=size)
        except Exception:                               # noqa: BLE001
            _FONTS[size] = ImageFont.load_default()
    return _FONTS[size]


def _nice(mm):
    for v in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000):
        if v >= mm:
            return v
    return 5000


def _annotate(im, name, cam, scale, W, H):
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    d.text((10, 8), name, fill=(40, 42, 48), font=_font(15))
    bar = _nice(0.18 * W / max(scale, 1e-9))
    L = bar * scale
    x1, y1 = W - 14, H - 16
    if L < W * 0.4:
        d.line([(x1 - L, y1), (x1, y1)], fill=(40, 42, 48), width=3)
        for xx in (x1 - L, x1):
            d.line([(xx, y1 - 5), (xx, y1 + 3)], fill=(40, 42, 48), width=2)
        d.text((x1 - L, y1 - 22), "%g mm" % bar, fill=(40, 42, 48), font=_font(13))
    if cam["dist"]:
        d.text((x1 - L, y1 - 38) if L < W * 0.4 else (W - 170, H - 40),
               "perspective: bar is approx.", fill=(110, 110, 118), font=_font(11))
    ox, oy, Lr = 30, H - 30, 22
    for vec, nm, col in (((1, 0, 0), "X", (200, 50, 50)), ((0, 1, 0), "Y", (50, 160, 60)),
                         ((0, 0, 1), "Z", (50, 90, 210))):
        dx, dy = float(np.dot(vec, cam["r"])), float(np.dot(vec, cam["u"]))
        if abs(dx) + abs(dy) < 0.15:
            d.ellipse([ox - 3, oy - 3, ox + 3, oy + 3], outline=col, width=2)
            d.text((ox + 5, oy - 14), nm, fill=col, font=_font(12))
            continue
        d.line([(ox, oy), (ox + Lr * dx, oy - Lr * dy)], fill=col, width=2)
        d.text((ox + 1.4 * Lr * dx - 4, oy - 1.4 * Lr * dy - 7), nm, fill=col, font=_font(12))


def _wrap(text, width):
    out, line = [], ""
    for word in str(text).split():
        if line and len(line) + 1 + len(word) > width:
            out.append(line)
            line = word
        else:
            line = (line + " " + word) if line else word
    if line:
        out.append(line)
    return out or [""]


def _board_plane(scene):
    """(point, unit normal toward the modules) of the board, or None. The
    normal is the board mesh's thinnest principal axis."""
    kinds = scene["kinds"]
    if "board" not in kinds:
        return None
    k = kinds.index("board")
    P = scene["T"][scene["obj"] == k].reshape(-1, 3)
    if len(P) < 4:
        return None
    c = (P.min(0) + P.max(0)) / 2
    Q = P[:: max(1, len(P) // 20000)] - P.mean(0)
    _w, V = np.linalg.eigh(Q.T @ Q)
    n = V[:, 0]
    mods = [i for i, kd in enumerate(kinds) if kd in ("module", "cable")]
    if mods:
        M = scene["T"][np.isin(scene["obj"], mods)].reshape(-1, 3)
        side = float(np.mean((M - c) @ n))
    else:
        side = float(np.mean((P - c) @ n))
    if side < 0:
        n = -n
    return c, n


def _inside_job(scene, W, H, ss):
    """The cutaway: bodies cut at the board plane (no board: the front half
    of everything off, cut at the middle in Y), electronics whole."""
    bodies = np.array([kd in ("body", "user") for kd in scene["kinds"]])
    if not bodies.any():
        return None, "no body to cut"
    plane = _board_plane(scene)
    if plane is None:
        c = (scene["min"] + scene["max"]) / 2
        n = np.array([0.0, -1.0, 0.0])
        where = "cut at the middle (no Atech board), front half removed"
    else:
        c, n = plane
        where = "body cut at the board plane, the modules' side removed"
    T, N, O = clip_plane(scene["T"], scene["N"], scene["obj"], bodies, c, n)
    if not len(T):
        return None, "nothing left after the cut"
    cut = dict(scene, T=T, N=N, obj=O)
    hero = np.array(HERO[1], float)
    hero /= np.linalg.norm(hero)
    perp = hero - np.dot(hero, n) * n
    if np.linalg.norm(perp) < 1e-3:
        perp = np.array([1.0, 0, 0]) - n[0] * n
    perp /= np.linalg.norm(perp)
    v = n + 0.6 * perp
    if v[2] < 0.25 and abs(n[2]) < 0.9:   # keep a little of the top in view
        v = v + np.array([0, 0, 0.45])
    v /= np.linalg.norm(v)
    diag = float(np.linalg.norm(scene["max"] - scene["min"]))
    cam = camera(v, (0, 0, 1), (scene["min"] + scene["max"]) / 2, diag, True)
    img, scale = render_view(cut, cam, W, H, None, ss=ss, section=bodies)
    return (img, scale, cam, "INSIDE  %s (cut walls hatched)" % where), None


def _closeup_job(scene, k, W, H, ss, shadow):
    m = scene["obj"] == k
    P = scene["T"][m].reshape(-1, 3)
    lo, hi = P.min(0), P.max(0)
    c_all = (scene["min"] + scene["max"]) / 2
    c = (lo + hi) / 2
    out = c - c_all                      # look from outside, slightly above
    out[2] = max(out[2], 0) + 0.6 * np.linalg.norm(out[:2]) + 1e-3
    if np.linalg.norm(out[:2]) < 1e-3:
        out = np.array([-0.6, -1.0, 0.7])
    view = out / np.linalg.norm(out)
    cam = camera(view, (0, 0, 1), c, float(np.linalg.norm(hi - lo)), True)
    pad = 0.35 * (hi - lo) + 0.02 * np.linalg.norm(scene["max"] - scene["min"])
    img, scale = render_view(scene, cam, W, H, shadow, ss=ss, fit=(lo - pad, hi + pad),
                             focus=k)
    return img, scale, cam, "CLOSE-UP  %s  (parts in front of it cut away)" % scene["labels"][k]


# ------------------------------------------- owner images (R440, WS4)
# R440: the archetype gates (atech_geom.archetype_problems) judge what a
# reviewer SEES from one side: which part is first along each pixel's ray,
# and how deep. The same exact z-buffer as the sheet, orthographic, one
# pixel = `px` mm, no shading.
ORTHO_SPLIT_PX = 24.0


def ortho_frame(v, up):
    """(r, u, v) unit vectors of an orthographic view looking along -v
    (v points toward the viewer), r to the right, u up the picture."""
    v = np.asarray(v, float)
    v = v / (np.linalg.norm(v) or 1.0)
    up = np.asarray(up, float)
    if abs(float(np.dot(up, v))) > 0.97:
        up = np.array([0.0, 1.0, 0.0]) if abs(v[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    r = np.cross(up, v)
    r /= np.linalg.norm(r)
    return r, np.cross(v, r), v


def ortho_image(T, O, v, up, px, lo, hi, back=False):
    """R440: the owner and depth images of triangles T (m,3,3) owned by
    O (m,) seen from v (toward the viewer) with `up` up the picture.

    lo, hi: the picture's (x, y) extent in mm in the frame's r, u axes;
    px: mm per pixel. back=True: the FARTHEST surface per pixel instead of
    the nearest (the back of the product, same pixels). Returns
    {"owner": HxW int (-1 = nothing), "depth": HxW float - the hit's
    coordinate along v (-inf / +inf where nothing), "tri": HxW triangle
    index into T (-1), "frame": (r, u, v), "px", "lo"}."""
    r, u, vv = ortho_frame(v, up)
    W = max(1, int(np.ceil((hi[0] - lo[0]) / px)) + 2)
    H = max(1, int(np.ceil((hi[1] - lo[1]) / px)) + 2)
    owner = np.full((H, W), -1, np.int64)
    tri = np.full((H, W), -1, np.int64)
    depth = np.full((H, W), np.inf if back else -np.inf)
    out = {"owner": owner, "depth": depth, "tri": tri, "frame": (r, u, vv), "px": px,
           "lo": (float(lo[0]) - px, float(lo[1]) - px), "W": W, "H": H}
    if T is None or not len(T):
        return out
    x0, y0 = out["lo"]
    xy = np.stack([(T @ r - x0) / px, (T @ u - y0) / px], axis=-1)
    idx = np.arange(len(T))
    # long screen edges split (the rasterizer tests each triangle's box)
    T2, _N, I2, xy2 = _bisect(T, np.zeros_like(T), idx, xy, ORTHO_SPLIT_PX)
    d = T2 @ vv
    tid, _bc, zb = rasterize(xy2, -d if back else d, W, H)
    hit = tid >= 0
    src = np.where(hit, I2[np.maximum(tid, 0)], -1)
    tri[hit] = src[hit]
    owner[hit] = np.asarray(O)[src[hit]]
    depth[hit] = -zb[hit] if back else zb[hit]
    return out


# ------------------------------------------------- product scorecard (R270)
# R270: what a reviewer counts before looking - NOTE lines, never a
# failure. Round 1's weakest builds were 6-9 parts in one or two colours.
BLOCKOUT_PARTS = 12             # fewer parts than this...
BLOCKOUT_MATERIALS = 3          # ...or fewer chosen colours: a placeholder
DETAIL_CALLS = ("cut", "hole", "counterbore", "countersink", "groove_ring",
                "groove_outline", "grille", "speaker_grille", "text", "knurl",
                "opening_for", "socket_opening")


def detail_calls(code):
    """R270: {call name: call sites} of the kit's exterior-detail calls
    (cuts, grooves, grilles, text) in model.py's source. Call SITES: a
    call in a loop counts once."""
    import ast
    out = {}
    try:
        tree = ast.parse(code or "")
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else \
                f.id if isinstance(f, ast.Name) else None
            if name in DETAIL_CALLS:
                out[name] = out.get(name, 0) + 1
    return out


def _colour_key(c):
    try:
        return tuple(int(round(float(v) * 20)) for v in tuple(c)[:3])
    except Exception:                                   # noqa: BLE001
        return None


def scorecard(items, view_colored=(), face_open=None, whole=None, code=""):
    """R270: {"facts": {...}, "lines": [NOTE text]} for the build.

    items         review items (check._review_items): label, kind, color,
                  shape/mesh
    view_colored  labels whose colour model.py chose (ShapeColor or
                  DiffuseColor recorded); an uncoloured body is drawn in
                  Studio's palette and is no material choice
    face_open     atech_geom.face_open rows (sealed modules, screen window)
    whole         [x, y, z] mm of the whole build
    code          model.py's source (detail_calls)"""
    bodies = [it for it in items if (it.get("kind") or "body") == "body"]
    chosen = {_colour_key(it.get("color")) for it in bodies
              if it.get("label") in set(view_colored)}
    chosen.discard(None)
    calls = detail_calls(code)
    n_detail = sum(calls.values())
    rows = face_open or []
    sealed = [r["label"] for r in rows if r.get("kind") and r.get("open") == 0]
    facts = {"parts": len(bodies), "colours": len(chosen),
             "uncoloured": len([it for it in bodies
                                if it.get("label") not in set(view_colored)]),
             "detail_calls": n_detail, "detail_by_call": calls, "sealed": sealed}
    lines = ["SCORECARD parts %d, chosen colours %d%s, exterior detail calls %d (%s)" % (
        facts["parts"], facts["colours"],
        " (+%d parts left uncoloured)" % facts["uncoloured"] if facts["uncoloured"] else "",
        n_detail, ", ".join("%s %d" % kv for kv in sorted(calls.items())) or "none")]
    lines.append("SCORECARD sealed modules: %s" % (", ".join(sealed) or "none"))
    shapes = {it.get("label"): it.get("shape") for it in bodies}
    for r in rows:
        if str(r.get("module") or "").lower() != "screen" or not r.get("face_mm"):
            continue
        fw, fh = r["face_mm"]
        win = (r.get("open_pct") or 0) / 100.0 * fw * fh
        host = r.get("blocked_by")
        pct = None
        sh = shapes.get(host)
        if sh is not None:
            try:
                bb = sh.BoundBox
                dims = [bb.XLength, bb.YLength, bb.ZLength]
                k = max(range(3), key=lambda i: abs(r["normal"][i]))
                a = 1.0
                for i in range(3):
                    if i != k:
                        a *= dims[i]
                pct = round(100.0 * win / a, 1) if a > 0 else None
            except Exception:                           # noqa: BLE001
                pct = None
        facts.setdefault("screens", []).append({"label": r["label"], "window_mm2": round(win, 1),
                                                "host": host, "window_pct_of_face": pct})
        lines.append("SCORECARD screen %s: window ~%.0f mm2%s" % (
            r["label"], win, " = %.1f %% of %s's face" % (pct, host) if pct is not None
            else ""))
    if whole and len(whole) == 3 and min(whole) > 0:
        w = sorted((float(v) for v in whole), reverse=True)
        facts["aspect"] = [round(v / w[2], 2) for v in w]
        lines.append("SCORECARD overall %s mm, aspect %s : %s : 1 (longest : middle : "
                     "shortest)%s" % (" x ".join("%g" % v for v in whole),
                                      "%.1f" % (w[0] / w[2]), "%.1f" % (w[1] / w[2]),
                                      " - a slab: give it depth, a stance or a sculpted "
                                      "section" if w[2] < 0.3 * w[1] else ""))
    blockout = facts["parts"] < BLOCKOUT_PARTS or facts["colours"] < BLOCKOUT_MATERIALS
    facts["blockout"] = blockout
    if blockout:
        lines.append("BLOCKOUT: this reads as a placeholder (%d parts, %d chosen colours; "
                     "a finished product has >= %d parts in >= %d materials - lenses, key "
                     "caps, feet, trim, screws, a bezel, a grille insert)" % (
                         facts["parts"], facts["colours"], BLOCKOUT_PARTS,
                         BLOCKOUT_MATERIALS))
    return {"facts": facts, "lines": lines}


def _remove(path):
    try:
        if os.path.isfile(path) and not os.path.islink(path):
            os.unlink(path)
    except OSError:
        pass


def clear(out_dir):
    """Remove the review pictures an earlier ./check left (R230: an old
    picture is never mistaken for this build's)."""
    try:
        names = os.listdir(out_dir)
    except OSError:
        return
    for nm in names:
        if nm == "review.png" or (nm.startswith("review_") and nm.endswith(".png")):
            _remove(os.path.join(out_dir, nm))


def draw(items, out_dir, title="", notes=(), banner=None, closeups=(),
         inside=True, hero_path=None, threads=THREADS, W=600, H=450, ss=2,
         big=(960, 720)):
    """Draw the review sheet (+ cutaway, close-ups, hero) into out_dir.

    banner: None, or ("FAILED CHECK" | "PARTIAL BUILD", one-line reason).
    Returns {"sheet", "inside", "closeups": {label: path}, "missing":
    [labels not found], "hero", "seconds", "timings", "triangles"} -
    "sheet" None plus "why" when nothing could be drawn."""
    from PIL import Image, ImageDraw
    t0 = time.time()
    clear(out_dir)
    out = {"sheet": None, "inside": None, "closeups": {}, "missing": [], "hero": None,
           "timings": {}}
    tm = out["timings"]
    scene = scene_from(items)
    tm["tessellate"] = round(time.time() - t0, 2)
    if scene is None:
        out["why"] = "nothing to draw (no shape with triangles)"
        out["seconds"] = round(time.time() - t0, 2)
        return out
    out["triangles"] = int(len(scene["T"]))
    if out["triangles"] > MAX_TRIANGLES:
        out["why"] = "%d triangles: too many to draw" % out["triangles"]
        out["seconds"] = round(time.time() - t0, 2)
        return out
    t1 = time.time()
    shadow = ShadowMap(scene, KEY)
    tm["shadow"] = round(time.time() - t1, 2)
    diag = float(np.linalg.norm(scene["max"] - scene["min"]))
    ctr = (scene["min"] + scene["max"]) / 2
    ortho = min(fit_scale(scene, camera(v, up, ctr, diag), W, H)
                for _, v, up, p in VIEWS if not p)
    wanted = []
    for lab in list(closeups)[:MAX_CLOSEUPS]:
        if lab in scene["labels"]:
            if lab not in [w for w, _ in wanted]:
                wanted.append((lab, scene["labels"].index(lab)))
        else:
            out["missing"].append(lab)
    BW, BH = big

    def job(spec):
        t2 = time.time()
        kind, arg = spec
        try:
            if kind == "view":
                name, v, up, persp = VIEWS[arg]
                cam = camera(v, up, ctr, diag, persp)
                img, scale = render_view(scene, cam, W, H, shadow if persp else None,
                                         ss=ss, scale=None if persp else ortho)
                res = (img, scale, cam, name), None
            elif kind == "inside":
                res = _inside_job(scene, BW, BH, ss)
            else:
                res = _closeup_job(scene, arg[1], BW, BH, ss, shadow), None
        except Exception as exc:                        # noqa: BLE001
            res = None, "%s: %s" % (type(exc).__name__, exc)
        tm["%s_%s" % (kind, arg if kind != "closeup" else arg[0])] = round(time.time() - t2, 2)
        return spec, res
    # the longest jobs first, so none is left running alone at the end
    specs = [("closeup", w) for w in wanted] + ([("inside", 0)] if inside else []) \
        + [("view", k) for k in (0, 3, 5, 1, 2, 4)]
    if threads > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(threads) as ex:
            done = list(ex.map(job, specs))
    else:
        done = [job(s) for s in specs]
    panels, errors = {}, []
    for (kind, arg), (res, why) in done:
        if res is None:
            if why and kind != "inside":
                errors.append("%s %s: %s" % (kind, arg, why))
            elif why:
                out["inside_skipped"] = why
            continue
        img, scale, cam, name = res
        w, h = img.shape[1], img.shape[0]
        im = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
        _annotate(im, name, cam, scale, w, h)
        panels[(kind, arg if kind != "closeup" else arg[0])] = im
    if errors:
        out["errors"] = errors
    # ---- the sheet
    head = 64 + (40 if banner else 0)
    leg_rows = (len(scene["labels"]) + 3) // 4
    note_lines = []
    for nl in notes:
        note_lines += _wrap(nl, 190)
    note_lines = note_lines[:14]
    foot = 14 + 22 * leg_rows + 18 * len(note_lines)
    sheet = Image.new("RGB", (3 * W, head + 2 * H + foot), (250, 250, 251))
    for k in range(len(VIEWS)):
        im = panels.get(("view", k))
        if im is not None:
            sheet.paste(im, ((k % 3) * W, head + (k // 3) * H))
    d = ImageDraw.Draw(sheet)
    y0 = 0
    if banner:
        d.rectangle([0, 0, 3 * W, 38], fill=(178, 28, 28))
        d.text((12, 8), ("%s  -  %s" % banner)[:170], fill=(255, 255, 255), font=_font(20))
        y0 = 40
    size = scene["max"] - scene["min"]
    d.text((12, y0 + 10), title or "Design review", fill=(20, 20, 24), font=_font(22))
    d.text((12, y0 + 38), "overall %.1f x %.1f x %.1f mm (X x Y x Z)   %d parts   "
           "flat views share one scale   drawn %s" % (
               size[0], size[1], size[2], len(scene["labels"]),
               time.strftime("%H:%M:%S")), fill=(70, 72, 80), font=_font(15))
    for k in range(1, 3):
        d.line([(k * W, head), (k * W, head + 2 * H)], fill=(215, 216, 220), width=1)
    d.line([(0, head + H), (3 * W, head + H)], fill=(215, 216, 220), width=1)
    y = head + 2 * H + 8
    for i, (lab, col) in enumerate(zip(scene["labels"], scene["colors"])):
        x = 12 + (i % 4) * (3 * W // 4)
        yy = y + (i // 4) * 22
        c = tuple(int(255 * c) for c in col)
        d.rectangle([x, yy + 2, x + 16, yy + 16], fill=c,
                    outline=(220, 30, 30) if scene["problem"][i] else (60, 60, 60),
                    width=2 if scene["problem"][i] else 1)
        txt = lab + ("  [PROBLEM]" if scene["problem"][i] else "")
        d.text((x + 22, yy), txt[:52], fill=(150, 20, 20) if scene["problem"][i] else (40, 42, 48),
               font=_font(14))
    for j, nline in enumerate(note_lines):
        d.text((12, y + 22 * leg_rows + 18 * j), nline, fill=(150, 20, 20), font=_font(14))
    path = os.path.join(out_dir, "review.png")
    sheet.save(path, compress_level=3)
    out["sheet"] = os.path.abspath(path)
    out["banner"] = banner[0] if banner else None
    out["outlined"] = sorted({lab for lab, bad in zip(scene["labels"], scene["problem"]) if bad})
    if hero_path and ("view", 0) in panels:
        panels[("view", 0)].save(hero_path, compress_level=3)
        out["hero"] = os.path.abspath(hero_path)
    if ("inside", 0) in panels:
        p = os.path.join(out_dir, "review_inside.png")
        _stamp(panels[("inside", 0)], banner)
        panels[("inside", 0)].save(p, compress_level=3)
        out["inside"] = os.path.abspath(p)
        out["inside_cut"] = "board" if _board_plane(scene) is not None else "middle"
    for lab, _k in wanted:
        im = panels.get(("closeup", lab))
        if im is None:
            continue
        p = os.path.join(out_dir, "review_%s.png" % safe_label(lab))
        _stamp(im, banner)
        im.save(p, compress_level=3)
        out["closeups"][lab] = os.path.abspath(p)
    out["seconds"] = round(time.time() - t0, 2)
    return out


def _stamp(im, banner):
    """The banner on a single picture too (a cutaway of a failed build)."""
    if not banner:
        return
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    w = im.size[0]
    d.rectangle([w - 190, 0, w, 30], fill=(178, 28, 28))
    d.text((w - 180, 6), banner[0], fill=(255, 255, 255), font=_font(16))
