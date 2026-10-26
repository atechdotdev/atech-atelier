"""atech_form - checked helpers for SCULPTED BODIES (R230).

    import atech_cad as cad      # atech_cad re-exports everything here
    body = cad.profile_body(side, plan, fillet=4)

The kit's boxy helpers (rounded_box, shell) cannot make or hollow a curved
product body (MEASURED, r2 gaps 2-4: cad.shell fails on every lofted,
filleted or tapered body tried). These helpers build the body from 2D
outlines the way a designer sketches it - a side view and a plan view -
and hollow it with a fallback ladder that ends in a rebuilt inset core.

Every helper CHECKS ITS OWN RESULT (valid, one solid, the volume it should
have) and raises cad.CadError with the fix instead of returning a broken
shape. Millimetres and degrees.

OUTLINES (spline_wire, profile_body, revolve_profile, extrude_profile) are
lists of points; a plain point is a smooth spline knot (or a polygon corner
when spline=False). Tagged items change that:
    ('corner', p)       a sharp point: the spline breaks there
    ('line', p)         a straight segment to p (a flat bottom, a cut-off)
    ('arc', mid, end)   a circular arc through mid to end
2D points lie in the named plane ('XZ' -> (x, z)); 3D points are used as is.

ORDER (MEASURED r2 gap 1): fillet the body FIRST (profile_body(fillet=r)),
then hollow, then cut features, then soften only the new edges.

ONE CALL (R270): lower, upper = cad.shell_body(side, plan, wall, split_z,
lip, fillet) builds, hollows and splits a sculpted shell on the fallback
ladders below. NEVER-FAIL (R270, from round 1's ~40 failed checks per
product): profile_body's fillet steps through rungs and at worst returns
the valid unfilleted body with a WARNING; hollow ends in the profile core,
a fitted core and makeThickness; split drops a lip it cannot build
(WARNING, lip=0) and moves a bad plane up to 3 mm; outlines whose spline
wiggles between the knots are faired ("outline not fair" NOTE when that is
not enough); OCCT fillet calls run in a forked child that is killed after
GUARD_S s (a hang or a segfault no longer kills ./check).

atech_cad does `from atech_form import *` at its END, so this file imports
atech_cad lazily (inside functions, _k()) and never at module top: either
import order works (R230).
"""
import math
import os
import time

import FreeCAD as App
import Part

__all__ = [
    "spline_wire", "rounded_rect_wire", "profile_body", "loft",
    "extrude_profile", "hollow", "pipe", "revolve_profile", "mirror",
    "symmetric", "mirror_pair", "split",
]

TOL = 1e-6
_PLANES = {"XZ": ((1, 0, 0), (0, 0, 1)), "XY": ((1, 0, 0), (0, 1, 0)),
           "YZ": ((0, 1, 0), (0, 0, 1))}
_PLANE_NORMAL = {"XZ": (0, 1, 0), "XY": (0, 0, 1), "YZ": (1, 0, 0)}


# ------------------------------------------------------------- internals
def _k():
    """The atech_cad module (lazy: it imports this file at its end)."""
    import atech_cad
    return atech_cad


_T0 = [0.0]


def _tr(label):
    """ATECH_FORM_TRACE=1: print the time since the previous mark."""
    if os.environ.get("ATECH_FORM_TRACE") == "1":
        now = time.time()
        print("  trace %-24s %.2f s" % (label, now - _T0[0]))
        _T0[0] = now


def _err(msg):
    return _k().CadError(msg)


def _V(p):
    return _k().V(p)


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _msg(exc):
    return " ".join(str(exc).split()) or type(exc).__name__


def _plane(plane, what):
    key = str(plane).upper()
    if key not in _PLANES:
        raise _err("%s: plane %r - use 'XZ', 'XY' or 'YZ'" % (what, plane))
    return key


def _to3(p, plane):
    """A 2D point in `plane` or a 3D point -> Vector."""
    if isinstance(p, App.Vector):
        return App.Vector(p)
    p = list(p)
    if len(p) == 3:
        return _V(p)
    if len(p) != 2 or not all(_num(c) for c in p):
        raise _err("outline point %r: give (a, b) in the plane or (x, y, z)" % (p,))
    u, v = _PLANES[plane]
    return _V(u) * float(p[0]) + _V(v) * float(p[1])


def _frame(normal):
    """Two unit vectors (u, v) spanning the plane normal to `normal`, the
    same u/v as rounded_rect_wire uses: Z -> (X, Y), Y -> (X, Z), X -> (Y, Z)."""
    n = _k()._dir(normal, "normal")
    ax = max(range(3), key=lambda i: abs((n.x, n.y, n.z)[i]))
    if abs((n.x, n.y, n.z)[ax]) > 1 - 1e-9:
        return [(App.Vector(0, 1, 0), App.Vector(0, 0, 1)),
                (App.Vector(1, 0, 0), App.Vector(0, 0, 1)),
                (App.Vector(1, 0, 0), App.Vector(0, 1, 0))][ax], n
    ref = App.Vector(0, 0, 1) if abs(n.z) < 0.9 else App.Vector(1, 0, 0)
    u = ref.cross(n)
    u.normalize()
    v = n.cross(u)
    v.normalize()
    return (u, v), n


def _nodes(items, plane, spline, what):
    """Outline items -> [[point, incoming segment, is_break, is_corner]]."""
    if not isinstance(items, (list, tuple)) or len(items) < 2:
        raise _err("%s: give a list of at least 2 outline points" % what)
    nodes = []
    for it in items:
        if isinstance(it, (list, tuple)) and it and isinstance(it[0], str):
            tag = it[0].lower()
            if tag == "line" and len(it) == 2:
                nodes.append([_to3(it[1], plane), "line", True, False])
            elif tag == "corner" and len(it) == 2:
                nodes.append([_to3(it[1], plane), "spline" if spline else "line", True, True])
            elif tag == "arc" and len(it) == 3:
                nodes.append([_to3(it[2], plane), ("arc", _to3(it[1], plane)), True, False])
            else:
                raise _err("%s: item %r - use ('line', p), ('corner', p) or "
                           "('arc', mid, end)" % (what, it))
        else:
            nodes.append([_to3(it, plane), "spline" if spline else "line", not spline, False])
    return nodes


def _params(pts, closed):
    """Centripetal knot parameters (chord length ** 0.5). MEASURED (R230): a
    car plan with flat ends overshoots 12.9 mm with the default chordal
    parameters, 6.6 mm with these; a roof 4.3 -> 3.0 mm."""
    ps = list(pts) + ([pts[0]] if closed else [])
    t = [0.0]
    for p, q in zip(ps, ps[1:]):
        t.append(t[-1] + max((q - p).Length, 1e-9) ** 0.5)
    return t


def _bspline(pts, closed, t0=None, t1=None):
    """A C2 BSpline edge through pts with centripetal parameters (t0 / t1:
    unit end tangents, R270 G1 joins) - FAIRED (R270, see _fair) when it
    swings through inflections its knots do not make.

    Tried and dropped (R230, MEASURED): Catmull-Rom tangents at every knot
    gave a symmetric car plan (+-32.32 mm where this gives -33.09 / +33.34)
    with less sag, but tangent interpolation is only C1, OCCT's 2D offset
    returns NULL on it, and its C2 resample made the body fillet fail at
    r=4 (r=3 used) - so plain global interpolation stays."""
    c = Part.BSplineCurve()
    if not closed and (t0 is not None or t1 is not None) and _G1_ON[0]:
        z = App.Vector()
        c.interpolate(Points=pts, Parameters=_params(pts, closed),
                      Tangents=[t0 or z] + [z] * (len(pts) - 2) + [t1 or z],
                      TangentFlags=[t0 is not None] + [False] * (len(pts) - 2) + [t1 is not None])
    else:
        c.interpolate(Points=pts, PeriodicFlag=bool(closed), Parameters=_params(pts, closed))
    e = _fair(pts, closed, t0, t1, c)
    return e if e is not None else c.toShape()


_G1_ON = [True]


# ------------------------------------------------------------- fairing
# R270 (MEASURED, round 1): global interpolation through every knot makes
# a hand-typed outline oscillate between its knots. The toy car's 22-knot
# side swung through 2 extra inflections (tightest bend 3.5 mm) and its
# 44-knot plan through 8 where the knots turn only 4 times; on those
# outlines every profile_body fillet from r=7 down to 2.1 failed, and the
# shells rendered as lumpy surfaces. A penalised least-squares B-spline
# (2 poles per knot, second differences of the poles penalised: a
# discrete bending energy) with the SMALLEST penalty that leaves no extra
# inflection, within FAIR_TOL of every knot, is fair; at the smallest
# penalty it is the interpolation to within 0.01 mm.
FAIR_MIN_KNOTS = 6      # runs with fewer knots are interpolated as before
FAIR_TOL = 0.25         # mm a knot may move: max(this, 0.3 % of the span) ..
FAIR_TOL_MAX = 0.6      # .. capped here
_FAIR_LAMBDAS = (1e-6, 1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 0.1, 0.3, 1.0, 3.0)
_FAIR_ON = [True]       # the sabotage run turns it off
_FAIR_LOG = []          # [(wiggles, point)] of the runs _wire just built


def _plane_normal(pts):
    """Unit normal of the plane the points lie in, or None (3D path)."""
    c = App.Vector()
    for p in pts:
        c = c + p
    c = c * (1.0 / len(pts))
    n = None
    for i in range(len(pts)):
        a = pts[i] - c
        for j in range(i + 1, min(len(pts), i + 1 + len(pts) // 2 + 1)):
            m = a.cross(pts[j] - c)
            if m.Length > 1e-6 and (n is None or m.Length > n.Length):
                n = m
    if n is None:
        return None
    n.normalize()
    span = max((p - c).Length for p in pts)
    if any(abs((p - c).dot(n)) > 1e-6 * max(span, 1.0) for p in pts):
        return None
    return n


def _poly_flips(pts, closed, n):
    """Turning-direction changes of the knot polygon (the inflections the
    designer drew); turns under 0.5 deg do not count."""
    k = len(pts)
    sg = []
    rng = range(k) if closed else range(1, k - 1)
    for i in rng:
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % k]
        u, v = b - a, c - b
        if u.Length < 1e-9 or v.Length < 1e-9:
            continue
        s = u.cross(v).dot(n) / (u.Length * v.Length)
        if abs(s) > math.sin(math.radians(0.5)):
            sg.append(1 if s > 0 else -1)
    return _count_flips(sg, closed)


def _count_flips(sg, closed):
    if not sg:
        return 0
    f = sum(1 for a, b in zip(sg, sg[1:]) if a != b)
    if closed and sg[0] != sg[-1]:
        f += 1
    return f


def _curve_flips(c, u0, u1, n, closed, samples):
    """(sign changes of the signed curvature, where the extra ones are)."""
    ks = []
    for i in range(samples):
        u = u0 + (u1 - u0) * (i + 0.5) / samples
        try:
            _p, d1, d2 = c.getD2(u)
        except Exception:                               # noqa: BLE001
            continue
        if d1.Length < 1e-12:
            continue
        ks.append((d1.cross(d2).dot(n) / d1.Length ** 3, u))
    if not ks:
        return 0, None
    kmax = max(abs(k) for k, _u in ks)
    span = max(c.value(u0).distanceToPoint(c.value(0.5 * (u0 + u1))), 1.0)
    eps = max(0.02 * kmax, 1.0 / (40.0 * span))
    sg, at = [], None
    for k, u in ks:
        if abs(k) < eps:
            continue
        s = 1 if k > 0 else -1
        if sg and s != sg[-1] and at is None:
            at = u
        sg.append(s)
    return _count_flips(sg, closed), at


def _fair_fit(P, t, closed, m, lam, t0=None, t1=None):
    """Penalised least-squares cubic B-spline with m poles (numpy)."""
    import numpy as np
    k = len(P)
    if closed:
        N = np.zeros((k, m))
        for r, tt in enumerate(t):
            x = (tt % 1.0) * m
            j = int(math.floor(x))
            u = x - j
            w = ((1 - u) ** 3 / 6.0, (3 * u ** 3 - 6 * u ** 2 + 4) / 6.0,
                 (-3 * u ** 3 + 3 * u ** 2 + 3 * u + 1) / 6.0, u ** 3 / 6.0)
            for q in range(4):
                N[r, (j + q) % m] += w[q]
        D = np.zeros((m, m))
        for i in range(m):
            D[i, (i - 1) % m] += 1.0
            D[i, i] -= 2.0
            D[i, (i + 1) % m] += 1.0
        A = np.vstack([N, math.sqrt(lam) * D])
        B = np.vstack([P, np.zeros((m, 3))])
        C = np.linalg.lstsq(A, B, rcond=None)[0]
        c = Part.BSplineCurve()
        c.buildFromPolesMultsKnots([App.Vector(*map(float, x)) for x in C], [1] * (m + 1),
                                   [i / float(m) for i in range(m + 1)], True, 3)
        return c
    nk = m - 2
    kn = [0.0] * 3 + [i / float(nk - 1) for i in range(nk)] + [1.0] * 3
    N = np.zeros((k, m))
    for r, tt in enumerate(t):
        tt = min(max(float(tt), 0.0), 1.0)
        if tt >= 1.0:
            N[r, m - 1] = 1.0
            continue
        s = max(i for i in range(len(kn) - 1) if kn[i] <= tt < kn[i + 1])
        b = [0.0] * (len(kn) - 1)
        b[s] = 1.0
        for d in range(1, 4):
            nb = [0.0] * (len(kn) - 1 - d)
            for i in range(len(nb)):
                v = 0.0
                if kn[i + d] > kn[i]:
                    v += (tt - kn[i]) / (kn[i + d] - kn[i]) * b[i]
                if kn[i + d + 1] > kn[i + 1]:
                    v += (kn[i + d + 1] - tt) / (kn[i + d + 1] - kn[i + 1]) * b[i + 1]
                nb[i] = v
            b = nb
        N[r, :] = b[:m]
    D = np.zeros((m - 2, m))
    for i in range(m - 2):
        D[i, i], D[i, i + 1], D[i, i + 2] = 1.0, -2.0, 1.0
    # poles as an affine map of the unknowns u: the end knots stay exactly
    # where they are (corners, line joins); a tangent end (R270 G1 join)
    # puts the 2nd pole on the tangent ray, one unknown (its distance)
    g = np.zeros((m, 3))
    cols = []
    g[0], g[m - 1] = P[0], P[-1]
    fixed = {0: None, m - 1: None}
    if t0 is not None:
        g[1] = P[0]
        fixed[1] = ("ray", np.array([t0.x, t0.y, t0.z]))
    if t1 is not None:
        g[m - 2] = P[-1]
        fixed[m - 2] = ("ray", -np.array([t1.x, t1.y, t1.z]))
    for i in range(m):
        if i in fixed:
            if fixed[i] is not None:
                cols.append((i, None, fixed[i][1]))
            continue
        for dim in range(3):
            cols.append((i, dim, None))
    G = np.zeros((3 * m, len(cols)))
    for j, (i, dim, ray) in enumerate(cols):
        if ray is None:
            G[3 * i + dim, j] = 1.0
        else:
            G[3 * i:3 * i + 3, j] = ray
    gv = g.reshape(-1)
    I3 = np.eye(3)
    NN, DD = np.kron(N, I3), np.kron(D, I3)
    A = np.vstack([NN @ G, math.sqrt(lam) * (DD @ G)])
    B = np.concatenate([P.reshape(-1) - NN @ gv, -math.sqrt(lam) * (DD @ gv)])
    u = np.linalg.lstsq(A, B, rcond=None)[0]
    C = (gv + G @ u).reshape(m, 3)
    if (t0 is not None and (C[1] - C[0]) @ np.array([t0.x, t0.y, t0.z]) <= 1e-9) or (
            t1 is not None and (C[-1] - C[-2]) @ np.array([t1.x, t1.y, t1.z]) <= 1e-9):
        raise ValueError("the tangent end turned back")
    c = Part.BSplineCurve()
    c.buildFromPolesMultsKnots([App.Vector(*map(float, x)) for x in C],
                               [4] + [1] * (nk - 2) + [4], kn[3:-3], False, 3)
    return c


def _fair(pts, closed, t0=None, t1=None, interp=None):
    """A faired BSpline edge for the knots `pts`, or None to keep the
    interpolation `interp`: it is kept when it is already fair (no
    inflection the knot polygon does not make - every existing outline
    that was fair builds exactly as before), for fewer than
    FAIR_MIN_KNOTS knots, a 3D path, no numpy, or when no fit within
    tolerance has fewer wiggles. Logs (extra inflections, where) to
    _FAIR_LOG (R270)."""
    if len(pts) < FAIR_MIN_KNOTS:
        return None
    n = _plane_normal(pts)
    if n is None:
        return None
    want = _poly_flips(pts, closed, n)
    samples = max(240, 10 * len(pts))
    w_i, at_i = (0, None)
    if interp is not None:
        f_i, at_i = _curve_flips(interp, interp.FirstParameter, interp.LastParameter, n,
                                 closed, samples)
        w_i = max(0, f_i - want)
        if w_i == 0:
            return None
    if not _FAIR_ON[0]:
        if w_i:
            _FAIR_LOG.append((w_i, interp.value(at_i) if at_i is not None else pts[0]))
        return None
    try:
        import numpy as np
    except Exception:                                   # noqa: BLE001
        return None
    span = max((p - q).Length for p in pts for q in pts[::max(1, len(pts) // 8)])
    tol = min(FAIR_TOL_MAX, max(FAIR_TOL, 0.003 * span))
    t = _params(pts, closed)
    t = [x / t[-1] for x in t]
    if closed:
        t = t[:-1]
    P = np.array([[p.x, p.y, p.z] for p in pts])
    m = min(max(2 * len(pts), 8), 160)
    best = None
    for lam in _FAIR_LAMBDAS:
        try:
            c = _fair_fit(P, t, closed, m, lam, t0, t1)
        except Exception:                               # noqa: BLE001
            break
        dev = max(p.distanceToPoint(c.value(c.parameter(p))) for p in pts)
        if dev > tol:
            break
        flips, at = _curve_flips(c, c.FirstParameter, c.LastParameter, n, closed, samples)
        best = (c, max(0, flips - want), at)
        if flips <= want:
            break
    if best is None or (interp is not None and best[1] >= w_i):
        if w_i:
            _FAIR_LOG.append((w_i, interp.value(at_i) if at_i is not None else pts[0]))
        return None
    c, extra, at = best
    if closed:
        # the loop starts at the first knot (loft sections keep their seams)
        u = c.parameter(pts[0])
        e = c.toShape(u, u + (c.LastParameter - c.FirstParameter))
    else:
        e = c.toShape()
    if extra:
        _FAIR_LOG.append((extra, c.value(at) if at is not None else pts[0]))
    return e


def _seg_edges(nodes, closed, what):
    n = len(nodes)
    if closed and n > 1 and (nodes[-1][0] - nodes[0][0]).Length < 1e-9:
        last = nodes.pop()                  # a repeated first point closes it
        nodes[0][1] = last[1]
        nodes[0][2] = nodes[0][2] or last[2]
        nodes[0][3] = nodes[0][3] or last[3]
        n -= 1
    brk = [nd[2] or nd[1] != "spline" for nd in nodes]
    for i in range(n):
        if nodes[i][1] != "spline" and (closed or i > 0):
            brk[i - 1] = True
    if not closed:
        brk[0] = brk[-1] = True
    pts = [nd[0] for nd in nodes]
    if closed and not any(brk):
        if n < 3:
            raise _err("%s: a closed spline needs at least 3 points" % what)
        return [_bspline(pts, True)]
    if closed:
        s = brk.index(True)
        nodes = nodes[s:] + nodes[:s]
        brk = brk[s:] + brk[:s]
        pts = [nd[0] for nd in nodes]
    end = n if closed else n - 1
    edges, run = [], [pts[0]]

    def flush(run):
        if len(run) == 2:
            if (run[1] - run[0]).Length < 1e-9:
                raise _err("%s: two outline points coincide at %s" % (what, run[0]))
            edges.append(Part.makeLine(run[0], run[1]))
        elif len(run) > 2:
            edges.append(("spline", list(run)))     # built below (R270 G1 ends)
    for j in range(1, end + 1):
        p, seg = pts[j % n], nodes[j % n][1]
        if seg == "spline":
            run.append(p)
            if brk[j % n] or j == end:
                flush(run)
                run = [p]
        else:
            flush(run)
            a = pts[(j - 1) % n]
            if (p - a).Length < 1e-9:
                raise _err("%s: two outline points coincide at %s" % (what, p))
            if seg == "line":
                edges.append(Part.makeLine(a, p))
            else:
                try:
                    edges.append(Part.Arc(a, seg[1], p).toShape())
                except Exception as exc:                # noqa: BLE001
                    raise _err("%s: arc %s -> %s -> %s is not a circle (%s) - the "
                               "three points must not lie on one line"
                               % (what, a, seg[1], p, _msg(exc)))
            run = [p]
    corners = [nd[0] for nd in nodes if nd[3]]
    m = len(edges)
    for i, e in enumerate(edges):
        if not isinstance(e, tuple):
            continue
        run = e[1]
        prv = edges[i - 1] if (closed or i > 0) and m > 1 else None
        nxt = edges[(i + 1) % m] if (closed or i < m - 1) and m > 1 else None
        t0 = _g1(prv, run[0], run[1] - run[0], corners, True)
        t1 = _g1(nxt, run[-1], run[-1] - run[-2], corners, False)
        try:
            edges[i] = _bspline(run, False, t0, t1)
        except Exception as exc:                        # noqa: BLE001
            raise _err("%s: cannot fit a spline through %d points (%s) - "
                       "remove repeated points" % (what, len(run), _msg(exc)))
    return edges


G1_DEG = 30.0       # R270: a spline meeting a line within this joins tangent


def _g1(nb, p, natural, corners, before):
    """The tangent a spline run must have at p where it meets the straight
    segment nb (before or after it), or None: only for a soft join (under
    G1_DEG, not a ('corner', p)). R270 (MEASURED, round-1 toy car): the
    floor line meeting the tail spline at 10 deg left a crease no fillet
    could round, and every fillet touching it failed."""
    if not _G1_ON[0] or nb is None or isinstance(nb, tuple) or not isinstance(
            getattr(nb, "Curve", None), Part.Line):
        return None
    if any((p - c).Length < 1e-9 for c in corners) or natural.Length < 1e-9:
        return None
    a, b = nb.Vertexes[0].Point, nb.Vertexes[-1].Point
    if before:
        d = (p - a) if (b - p).Length < 1e-9 else (p - b)
    else:
        d = (b - p) if (a - p).Length < 1e-9 else (a - p)
    if d.Length < 1e-9 or d.getAngle(natural) > math.radians(G1_DEG):
        return None
    d.normalize()
    return d


def _wire(items, closed, plane, spline, what):
    if isinstance(items, Part.Shape):
        w = items if isinstance(items, Part.Wire) else (
            items.OuterWire if isinstance(items, Part.Face) else Part.Wire(items.Edges))
        if closed and not w.isClosed():
            raise _err("%s: the wire given is not closed" % what)
        return w
    nodes = _nodes(items, plane, spline, what)
    del _FAIR_LOG[:]
    w = Part.Wire(_seg_edges(nodes, closed, what))
    if closed and not w.isClosed():
        raise _err("%s: the outline does not close" % what)
    _overshoot(w, [nd[0] for nd in nodes], what)
    if _FAIR_LOG:
        # R270: the agent fixes the knots (the surface renders lumpy)
        n = sum(x[0] for x in _FAIR_LOG)
        p = _FAIR_LOG[0][1]
        print("%s NOTE: outline not fair: %d wiggles (curvature sign flips the "
              "knots do not make) near (%.1f, %.1f, %.1f) - the surface will look "
              "lumpy there: move those knots onto one smooth curve, use fewer, or "
              "('line', p) for a straight run" % (what, n, p.x, p.y, p.z))
        del _FAIR_LOG[:]
    return w


def _overshoot(w, pts, what):
    """Print one NOTE when the curve bulges past its own points' box (a
    spline swinging below z=0 under a body, MEASURED r2 gap 2 pitfall)."""
    try:
        bb = w.BoundBox
    except Exception:                                   # noqa: BLE001
        return
    lo = [min(getattr(p, a) for p in pts) for a in "xyz"]
    hi = [max(getattr(p, a) for p in pts) for a in "xyz"]
    got_lo, got_hi = (bb.XMin, bb.YMin, bb.ZMin), (bb.XMax, bb.YMax, bb.ZMax)
    out = []
    for i, a in enumerate("XYZ"):
        span = max(hi[i] - lo[i], 1.0)
        for d, side in ((lo[i] - got_lo[i], "-"), (got_hi[i] - hi[i], "+")):
            if d > max(0.3, 0.02 * span):
                out.append("%.1f mm past %s%s" % (d, side, a))
    if out:
        print("%s NOTE: the spline swings %s of your points - add knots there "
              "or use ('corner', p) / ('line', p)" % (what, ", ".join(out)))


def _face(outline, plane, spline, what):
    if isinstance(outline, Part.Face):
        f = outline
    else:
        w = _wire(outline, True, plane, spline, what)
        try:
            f = Part.Face(w)
        except Exception as exc:                        # noqa: BLE001
            raise _err("%s: the outline is not one flat closed loop (%s)" % (what, _msg(exc)))
    if f.isNull() or not f.isValid() or f.Area <= TOL:
        raise _err("%s: the outline crosses itself or has no area - reorder the "
                   "points so they go once round the shape" % what)
    return f


def _normal(face):
    u0, u1, v0, v1 = face.ParameterRange
    return face.normalAt(0.5 * (u0 + u1), 0.5 * (v0 + v1))


def _offset_face(face, d, what, join=0):
    """`face` with its outline moved by d (d < 0 shrinks it), checked.
    Face.makeOffset2D, not the wire's: Part.Face(wire.makeOffset2D(...)) of a
    spline + line outline comes back INVALID (MEASURED R230)."""
    a0 = face.Area
    for s in (1.0, -1.0):
        try:
            f = face.makeOffset2D(s * d, join)
            f = _remerge(f.Faces[0], face) if len(f.Faces) == 1 else None
        except Exception as exc:                        # noqa: BLE001
            if s < 0:
                raise _err("%s: offsetting the outline by %g mm failed (%s) - it "
                           "is thinner than that somewhere" % (what, d, _msg(exc)))
            continue
        if f is not None and f.isValid() and (
                (d < 0 and f.Area < a0) or (d > 0 and f.Area > a0)):
            return f
    raise _err("%s: offsetting the outline by %g mm did not %s it (or split it "
               "in two: it is thinner than %g mm somewhere)" % (
                   what, d, "shrink" if d < 0 else "grow", 2 * abs(d)))


# R270: a cusp-safe 2D offset. Round 1 (MEASURED): makeOffset2D on an
# outline with a cusp (a heart lens's notch, a section where a wall turns
# back) self-intersects and returns NULL; split's lip raised "offsetting
# the outline by -0.98 mm failed" at every plane through the desk robot's
# torso. Tried in order: join=2 (intersection), join=0 (arcs), then the
# outline as a 0.25 mm polygon offset with arcs (each cusp becomes a
# vertex and is re-filleted by the arc), refit as smooth BSpline runs
# between the corners that remain.
CUSP_DEG = 35.0         # a turn sharper than this within ~0.6 mm stays a corner
_OFFSET_OFF = set()     # 'join2', 'join0', 'polygon': switched off (sabotage)


def _offset2d(face, d, what):
    """`face` (one planar loop) offset by d (d < 0 shrinks), never
    self-intersecting: join=2, join=0, then the polygon fallback; a valid
    Face or CadError."""
    errs = []
    for join in (2, 0):
        if "join%d" % join in _OFFSET_OFF:
            continue
        try:
            return _offset_face(face, d, what, join=join)
        except Exception as exc:                        # noqa: BLE001
            errs.append("join=%d: %s" % (join, str(exc).split(" - ")[0][:90]))
    if "polygon" not in _OFFSET_OFF:
        f = _offset_polygon(face, d)
        if f is not None:
            print("%s NOTE: offsetting the outline by %g mm crossed itself (a cusp) - "
                  "rebuilt from a 0.25 mm polygon, the cusps re-filleted (R270)" % (what, d))
            return f
        errs.append("polygon: no valid single loop")
    raise _err("%s: offsetting the outline by %g mm failed (%s) - it is thinner than "
               "%g mm somewhere" % (what, d, "; ".join(errs), 2 * abs(d)))


def _offset_polygon(face, d):
    try:
        w = face.OuterWire
        pts = w.discretize(Distance=0.25)
        if (pts[0] - pts[-1]).Length < 1e-6:
            pts = pts[:-1]
        poly = Part.Face(Part.makePolygon(pts + [pts[0]]))
        if not poly.isValid():
            return None
        a0 = poly.Area
        f = None
        for s in (1.0, -1.0):
            try:
                g = poly.makeOffset2D(s * d, 0)
            except Exception:                           # noqa: BLE001
                continue
            fs = sorted(g.Faces, key=lambda x: -x.Area)
            if not fs or (len(fs) > 1 and fs[1].Area > 0.02 * fs[0].Area):
                continue
            if (d < 0 and fs[0].Area < a0) or (d > 0 and fs[0].Area > a0):
                f = fs[0]
                break
        if f is None:
            return None
        res = Part.Face(_corner_loop(f.OuterWire.discretize(Distance=0.2)))
        if not res.isValid() or abs(res.Area - f.Area) > 0.02 * f.Area:
            return None
        return res
    except Exception:                                   # noqa: BLE001
        return None


def _corner_loop(dense):
    """A closed wire through a dense closed point loop: smooth BSpline runs
    between the points where it turns more than CUSP_DEG within ~0.6 mm."""
    if (dense[0] - dense[-1]).Length < 1e-6:
        dense = dense[:-1]
    n = len(dense)
    k = 3
    turn = []
    for i in range(n):
        a = dense[i] - dense[i - k]
        b = dense[(i + k) % n] - dense[i]
        turn.append(0.0 if a.Length < 1e-9 or b.Length < 1e-9 else math.degrees(a.getAngle(b)))
    corners = []
    for i in range(n):
        if turn[i] > CUSP_DEG and turn[i] >= max(turn[(i + j) % n] for j in range(-k, k + 1)):
            if not corners or i - corners[-1] > 2 * k:
                corners.append(i)
    if len(corners) > 1 and corners[0] + n - corners[-1] <= 2 * k:
        corners.pop()
    if not corners:
        return _loop(dense)
    edges = []
    for j, c0 in enumerate(corners):
        c1 = corners[(j + 1) % len(corners)]
        run = [dense[(c0 + i) % n] for i in range(((c1 - c0) % n or n) + 1)]
        sub = run[::5]
        if (sub[-1] - run[-1]).Length > 1e-9:
            if len(sub) > 1 and (sub[-1] - run[-1]).Length < 0.5:
                sub[-1] = run[-1]
            else:
                sub.append(run[-1])
        if len(sub) == 2:
            edges.append(Part.makeLine(sub[0], sub[1]))
        else:
            c = Part.BSplineCurve()
            c.interpolate(sub)
            edges.append(c.toShape())
    return Part.Wire(edges)


def _remerge(off, orig):
    """An offset face with each smooth run of curve pieces refit as ONE
    BSpline. MEASURED (R230): makeOffset2D cuts a one-edge spline plan into
    14 OffsetCurve edges, so the inset core had 80 faces where the body has
    17, and the core cut + wall measure took 2.3 s; refit, the faces match
    the body's (max deviation 0.006 mm)."""
    if len(off.OuterWire.Edges) <= len(orig.OuterWire.Edges):
        return off
    w = _refit(off.OuterWire)
    try:
        f = Part.Face(w)
    except Exception:                                   # noqa: BLE001
        return off
    # 0.5 %: on a 380 mm loop the refit sat 0.03 mm out on average (0.13 %)
    if not f.isValid() or abs(f.Area - off.Area) > 5e-3 * off.Area:
        return off
    return f


def _loop(dense):
    """A smooth closed Part.Wire (one periodic BSpline) through a dense
    closed point loop, resampled ~2.5 mm apart from a canonical start."""
    k0 = min(range(len(dense)), key=lambda i: (round(dense[i].x, 6), round(dense[i].y, 6),
                                                round(dense[i].z, 6)))
    dense = dense[k0:] + dense[:k0] + [dense[k0]]
    cum = [0.0]
    for p, q in zip(dense, dense[1:]):
        cum.append(cum[-1] + (q - p).Length)
    m = int(min(200, max(48, cum[-1] / 2.5)))
    pts, j = [], 0
    for i in range(m):
        s = cum[-1] * i / m
        while cum[j + 1] < s:
            j += 1
        seg = cum[j + 1] - cum[j]
        a = 0.0 if seg <= 0 else (s - cum[j]) / seg
        pts.append(dense[j] + (dense[j + 1] - dense[j]) * a)
    c = Part.BSplineCurve()
    c.interpolate(pts, PeriodicFlag=True)
    return Part.Wire([c.toShape()])


def _refit(wire, kink_deg=5.0):
    """`wire` with every smooth run of curved edges (no kink over kink_deg
    between them) refit as one BSpline through points ~2 mm apart; lines
    and arcs kept. A slice or an offset of spline faces comes back in many
    pieces, and every piece becomes a face in the solids built from it."""
    edges = list(wire.OrderedEdges)
    if len(edges) < 2:
        return wire

    def curved(e):
        return not isinstance(e.Curve, (Part.Line, Part.Circle))

    def kink(a, b):
        # travel directions at the shared vertex, whatever each edge's own
        # orientation (OrderedEdges does not flip them)
        best = None
        for ia, va in enumerate((a.Vertexes[0].Point, a.Vertexes[-1].Point)):
            for ib, vb in enumerate((b.Vertexes[0].Point, b.Vertexes[-1].Point)):
                d = (va - vb).Length
                if best is None or d < best[0]:
                    best = (d, ia, ib)
        d, ia, ib = best
        if d > 1e-4:
            return True                     # not joined: keep the break
        ra, rb = a.ParameterRange, b.ParameterRange
        ta = a.tangentAt(ra[1]) if ia == 1 else -a.tangentAt(ra[0])
        tb = b.tangentAt(rb[0]) if ib == 0 else -b.tangentAt(rb[1])
        return ta.Length < 1e-12 or tb.Length < 1e-12 or \
            ta.getAngle(tb) > math.radians(kink_deg)
    n = len(edges)
    closed = wire.isClosed()
    brk = [not closed and i == 0 for i in range(n)]
    for i in range(n):
        a, b = edges[i - 1], edges[i]
        if (i > 0 or closed) and (not curved(a) or not curved(b) or kink(a, b)):
            brk[i] = True
    if not any(brk):
        # a closed smooth loop: resample ~2.5 mm apart from a CANONICAL start
        # (the lowest-x, then lowest-y point), so the refit does not depend
        # on where OCCT happened to split the offset this time (MEASURED
        # R230: starting at its first edge, the same plan came out 7990.4 ..
        # 7996.8 mm2 run to run and the inset cores 163 516 .. 154 057 mm3)
        return _loop(Part.Wire(edges).discretize(Number=1201)[:-1])
    k = brk.index(True)
    edges = edges[k:] + edges[:k]
    brk = brk[k:] + brk[:k]
    out, run = [], []

    def flush():
        if len(run) == 1:
            out.append(run[0])
        elif run:
            w = Part.Wire(run)
            pts = w.discretize(Number=int(min(200, max(16, w.Length / 2.0))))
            c = Part.BSplineCurve()
            c.interpolate(pts)
            out.append(c.toShape())
        del run[:]
    for e, bk in zip(edges, brk):
        if bk:
            flush()
        if curved(e):
            run.append(e)
        else:
            flush()
            out.append(e)
    flush()
    try:
        w = Part.Wire(out)
        return w if w.isClosed() == closed else wire
    except Exception:                                   # noqa: BLE001
        return wire


def _clean(s):
    """A shell that should be a solid made one; NO removeSplitter: on a
    filleted spline body it merged faces into a SELF-INTERSECTING solid
    (volume 163 471 -> 163 643 mm3, BOPAlgo SelfIntersect - MEASURED R230)
    that every later cut then treated as outside the body."""
    if not s.isNull() and not s.Solids and s.Shells:
        try:
            s = Part.Solid(Part.Shell(s.Shells[0].Faces))
        except Exception:                               # noqa: BLE001
            pass
    return s


def _solid(s, what):
    s = _clean(s)
    _k()._check(s, what, solids=1)
    if s.Volume <= TOL:
        raise _err("%s: produced a zero-volume solid" % what)
    return s.Solids[0]


def _fillet_ladder(body, r, what, ratios=(1.0, 0.75, 0.5, 0.3), pick=None):
    """All (or the picked) edges at r, else at the next smaller rung;
    checked; returns (shape, r used)."""
    v0 = body.Volume
    edges = [e for e in body.Edges if pick is None or pick(e)]
    if not edges:
        return body, r
    last = None
    for k in ratios:
        rr = r * k
        res, why = _guarded(lambda: body.makeFillet(rr, edges))     # R270
        if res is None:
            last = why
            continue
        if (res.isValid() and len(res.Solids) == 1
                and 0.6 * v0 < res.Volume < v0 + TOL):
            return res.Solids[0], rr
        last = "result invalid"
    raise _err("%s: fillet r=%g failed on all edges down to r=%g (%s) - the "
               "outline has a bend tighter than that: use a smaller fillet or "
               "smoother outline points" % (what, r, r * ratios[-1], last))


def _no_bulge(body, bb, what):
    """`body` trimmed back to the box `bb` of the unfilleted body. A fillet
    only ever removes material outside it (concave fillets add it inside),
    yet OCCT's approximated fillet surfaces can bulge out: MEASURED (R230)
    4.4 mm3 down to z = -0.63 under the toy-car nose with fillet=4 - a body
    poking under the desk. Only trims when the tight box grew."""
    # no triangulation: whether a mesh is cached changed the answer run to
    # run (MEASURED R230: the same core came out 163 559 or 163 676 mm3)
    got = body.optimalBoundingBox(False, False)
    grew = max(bb.XMin - got.XMin, got.XMax - bb.XMax, bb.YMin - got.YMin,
               got.YMax - bb.YMax, bb.ZMin - got.ZMin, got.ZMax - bb.ZMax)
    if grew <= 1e-3:
        return body
    box = Part.makeBox(bb.XLength, bb.YLength, bb.ZLength,
                       App.Vector(bb.XMin, bb.YMin, bb.ZMin))
    res = _clean(body.common(box))
    if res.isNull() or not res.isValid() or len(res.Solids) != 1:
        return body
    return res.Solids[0]


def _elementary(shape):
    """Only planes, cylinders, cones, spheres, tori: offsets behave."""
    ok = (Part.Plane, Part.Cylinder, Part.Cone, Part.Sphere, Part.Toroid)
    return all(isinstance(f.Surface, ok) for f in shape.Faces)


def _gap(a, b):
    """Smallest distance between shapes a and b, robust: distToShape now
    and then answers 0.00 for two disjoint spline shells or wires (MEASURED
    R230: 1 run in 3 of the same car split/hollow). A zero is re-asked the
    other way round, then checked by sampling points of a against b."""
    d = a.distToShape(b)[0]
    if d > 1e-6:
        return d
    d = b.distToShape(a)[0]
    if d > 1e-6:
        return d
    pts = []
    for e in a.Edges:
        pts.extend(e.discretize(24))
    for f in a.Faces:
        u0, u1, v0, v1 = f.ParameterRange
        for i in range(1, 12):
            for j in range(1, 12):
                p = f.valueAt(u0 + (u1 - u0) * i / 12.0, v0 + (v1 - v0) * j / 12.0)
                pts.append(p)
    if not pts:
        return d
    return min(Part.Vertex(p).distToShape(b)[0] for p in pts)


def _min_wall(res, shape, open_faces, t):
    """(min wall, min rim) MEASURED: the inner faces of `res` to the outer
    skin of `shape` (its faces minus the opened ones). The rim is the band
    within t of an opening, where a core cut drops straight through the
    floor and an inward-sloping wall comes out thinner (MEASURED R230:
    0.95 mm on a t=2 car nose) - reported, not judged. None when not
    measurable."""
    try:
        full = Part.makeCompound(shape.Faces)
        skin = Part.makeCompound([f for f in shape.Faces
                                  if not any(f.isSame(o) for o in open_faces)])
        size = shape.BoundBox.DiagonalLength
        planes = [(_k()._outward(shape, o, _normal(o)), o.CenterOfMass)
                  for o in open_faces]
        inner, band = [], []
        for f in res.Faces:
            # judged against the FULL skin: the rim left round an opening
            # lies in the opened face, it is not an inner face (R230)
            u0, u1, v0, v1 = f.ParameterRange
            p = f.valueAt(0.5 * (u0 + u1), 0.5 * (v0 + v1))
            if Part.Vertex(p).distToShape(full)[0] <= 1e-5 * size + 1e-6:
                continue
            near = False
            for n, c in planes:
                ds = [(v.Point - c).dot(n) for v in f.Vertexes] or [-1e9]
                if min(ds) > -t - 1e-3:
                    near = True
            (band if near else inner).append(f)
        out = []
        for group in (inner, band):
            if not group:
                out.append(None)
                continue
            out.append(_gap(Part.makeCompound(group), skin))
        return out[0], out[1]
    except Exception:                                   # noqa: BLE001
        return None, None


# -------------------------------------------------------------- outlines
def spline_wire(points, closed=True, plane="XZ"):
    """A smooth BSpline Part.Wire through 2D points in `plane` (or 3D points),
    closed by default; ('line', p), ('corner', p) and ('arc', mid, end) items
    add sharp bits.

    side = cad.spline_wire([(0, 4), (6, 16), (60, 32), (140, 18),
                            ('corner', (142, 4)), ('line', (2, 0))])
    A closed outline with no tagged item is one periodic spline (no seam
    kink). Prints a NOTE when the curve swings > 0.3 mm outside its points.
    """
    plane = _plane(plane, "spline_wire")
    return _wire(points, bool(closed), plane, True, "spline_wire")


def rounded_rect_wire(w, h, r, center=(0, 0, 0), normal="Z"):
    """A w x h rectangle Part.Wire with corner radius r, centred on `center`,
    lying across `normal`; always 8 edges (4 when r=0) so loft sections match.

    Axes: normal Z -> w along X, h along Y; Y -> w along X, h along Z;
    X -> w along Y, h along Z. r up to min(w, h)/2 (kept 0.01 mm under it
    so the straight edges never vanish). Every wire starts at the same
    corner, so lofted sections never twist.
    """
    if not (_num(w) and _num(h) and _num(r)) or w <= 0 or h <= 0 or r < 0:
        raise _err("rounded_rect_wire: w, h must be > 0 and r >= 0")
    half = min(w, h) / 2.0
    if r > half + 1e-9:
        raise _err("rounded_rect_wire: r=%g is more than half of min(w, h)=%g - "
                   "use r <= %g" % (r, min(w, h), half))
    r = min(float(r), half - 0.01) if r > 0 else 0.0
    (u, v), n = _frame(normal)
    c = _V(center)
    a, b = w / 2.0, h / 2.0

    def P(x, y):
        return c + u * x + v * y
    if r <= 0:
        return Part.makePolygon([P(a, -b), P(a, b), P(-a, b), P(-a, -b), P(a, -b)])
    k = r * (1 - math.sqrt(0.5))
    edges = [
        Part.makeLine(P(a, -b + r), P(a, b - r)),
        Part.Arc(P(a, b - r), P(a - k, b - k), P(a - r, b)).toShape(),
        Part.makeLine(P(a - r, b), P(-a + r, b)),
        Part.Arc(P(-a + r, b), P(-a + k, b - k), P(-a, b - r)).toShape(),
        Part.makeLine(P(-a, b - r), P(-a, -b + r)),
        Part.Arc(P(-a, -b + r), P(-a + k, -b + k), P(-a + r, -b)).toShape(),
        Part.makeLine(P(-a + r, -b), P(a - r, -b)),
        Part.Arc(P(a - r, -b), P(a - k, -b + k), P(a, -b + r)).toShape(),
    ]
    return Part.Wire(edges)


# ----------------------------------------------------------------- bodies
CORE_MIN_R = 0.5    # R250: an inset core's fillet under this stays sharp
TANGENT_GAP = 2.0   # R270: see _clear_tangent_ends
TANGENT_NEAR = 1.0  # R270: ends closer than this (mm) count as tangent
_TANGENT_ON = [True]


def _end_kind(face, sign):
    """('smooth' | 'corner' | 'flat', x) of the outline's end along sign*X:
    a smooth extremum inside a curve, a vertex, or a straight edge."""
    best = None
    for e in face.OuterWire.Edges:
        for p in e.discretize(Number=max(24, int(e.Length / 0.5))):
            if best is None or sign * p.x > sign * best[0].x:
                best = (p, e)
    p, e = best
    if isinstance(e.Curve, Part.Line) and abs(e.Vertexes[0].Point.x - e.Vertexes[-1].Point.x) < 1e-6:
        return "flat", p.x
    for v in face.OuterWire.Vertexes:
        if (v.Point - p).Length < 0.6 and len(face.OuterWire.Edges) > 1:
            return "corner", p.x
    return "smooth", p.x


def _clear_tangent_ends(sf, pf, what):
    """R270 (MEASURED, round-1 toy car): when the side and the plan outline
    both END in a smooth curve at (almost) the same x - a nose rounded in
    both views - the two extrusions meet tangentially there; their common
    carries a degenerate 12.5 mm edge at the tail, and every fillet from
    r=7 down failed (r=5 SEGFAULTED freecadcmd). The plan is stretched
    along X (affine, < 2 % here) so it ends TANGENT_GAP past the side's
    end there: the side's nose then shapes the end, the plan crossing it
    cleanly. Returns the plan face (unchanged when no end is tangent)."""
    if not _TANGENT_ON[0]:
        return pf
    sb, pb = sf.BoundBox, pf.BoundBox
    lo, hi = pb.XMin, pb.XMax
    moved = []
    for sign in (-1, 1):
        ks, xs = _end_kind(sf, sign)
        kp, xp = _end_kind(pf, sign)
        if ks != "smooth" or kp != "smooth" or abs(xs - xp) >= TANGENT_NEAR:
            continue
        want = xs + sign * TANGENT_GAP
        if sign < 0:
            lo = pb.XMin - (xp - want)
        else:
            hi = pb.XMax + (want - xp)
        moved.append("%s end %.2f -> %.2f" % ("-X" if sign < 0 else "+X", xp, want))
    if not moved:
        return pf
    s = (hi - lo) / pb.XLength
    m = App.Matrix()
    m.scale(s, 1.0, 1.0)
    # the WIRE is stretched and a planar face rebuilt on it: a stretched
    # face comes back on a BSpline SURFACE, its volume integrals 0.8 % off
    # and its flat bottom no longer "flat" (MEASURED R270)
    w = pf.OuterWire.copy()
    w.translate(App.Vector(-pb.XMin, 0, 0))
    w = w.transformGeometry(m)
    w.translate(App.Vector(lo, 0, 0))
    f = Part.Face(Part.Wire(w.Edges) if not isinstance(w, Part.Wire) else w)
    if not f.isValid():
        return pf
    print("%s NOTE: the side and plan outlines end tangent to each other (both "
          "rounded at the same x) - the plan is stretched %.1f %% along X so its "
          "end clears the side's by %g mm (%s); end one outline %g mm past the "
          "other to keep your exact plan (R270)" % (
              what, 100.0 * (s - 1.0), TANGENT_GAP, ", ".join(moved), TANGENT_GAP))
    return f


# R270: profile_body's fillet ladder. Round 1 (MEASURED): ~15 profile_body
# fillet failures across the products, r=7 down to 0.3, each one a failed
# ./check and a rewrite. The rungs, in order, each checked (valid, one
# solid, 60-100 % of the volume):
#   all       every edge at r in one call (the R230 behaviour)
#   sharp     the same without the SOFT creases: edges whose faces meet
#             within SOFT_DEG everywhere (the car's chin and tail joins,
#             10-12 deg) - a fillet there cannot be built and nothing
#             needs rounding
#   split     the vertical edges at r, then every edge still sharp; then
#             the other order (one big makeFillet fails where two work)
#   shrink    r x 0.75, r x 0.5
#   soften    atech_detail.soften(top edges, r / 2): its own ladder, edge
#             by edge, partial success kept
#   unfilleted  the valid unfilleted body, with a WARNING - never a raise
#             while a valid body exists
SOFT_DEG = 20.0
FILLET_BUDGET_S = 25.0      # makeFillet rungs stop after this (s)
FILLET_RUNGS = ("all", "sharp", "split", "shrink", "soften", "unfilleted")
_FILLET_OFF = set()         # rungs switched off (sabotage runs)
_FILLET_ONLY = [None]       # tests isolate one rung: a tuple of names
_FILLET_USED = [None]       # the rung the last _fillet_body used


def _rung_on(name):
    return name not in _FILLET_OFF and (_FILLET_ONLY[0] is None or name in _FILLET_ONLY[0])


def _dihedrals(body, e, n=5):
    """Angles (deg) between the normals of the two faces meeting at edge e,
    at n points along it; [] for a seam or a free edge."""
    try:
        fs = []
        for f in body.ancestorsOfType(e, Part.Face):
            if not any(f.isSame(g) for g in fs):
                fs.append(f)
        if len(fs) < 2:
            return []
        a, b = e.ParameterRange
        out = []
        for i in range(n):
            p = e.valueAt(a + (b - a) * (i + 0.5) / n)
            n1 = fs[0].normalAt(*fs[0].Surface.parameter(p))
            n2 = fs[1].normalAt(*fs[1].Surface.parameter(p))
            out.append(math.degrees(n1.getAngle(n2)))
        return out
    except Exception:                                   # noqa: BLE001
        return []


def _soft(body, e):
    d = _dihedrals(body, e)
    return bool(d) and max(d) < SOFT_DEG


def _vertical(e):
    bb = e.BoundBox
    return bb.ZLength > 2.0 * max(bb.XLength, bb.YLength, 1e-6)


# R270: one OCCT call run in a forked child, killed after a time limit.
# MEASURED (round-1 toy car outlines): a single makeFillet ran 126 s (soften,
# 4 edges, r=3.5) and 178-219 s inside the R230 ladder before failing, and
# one at r=5 SEGFAULTED freecadcmd - the whole ./check died with no message.
# Headless only (a GUI process is never forked); without fork, in-process.
# ONLY for makeFillet / makeOffsetShape / makeThickness: a boolean or a
# tessellation in the child deadlocks on OCCT's thread pool once the parent
# has used it (MEASURED: cut and tessellate killed at 5 s, these three not).
GUARD_S = 12.0
_GUARD_ON = [True]


def _guard_ok():
    return (_GUARD_ON[0] and hasattr(os, "fork") and not getattr(App, "GuiUp", False)
            and os.environ.get("ATECH_FORM_NOFORK") != "1")


def _guarded(fn, timeout=None):
    """(shape, None) or (None, why): fn() -> Part.Shape run in a forked
    child (the result comes back as BREP text); a hang past `timeout` s is
    killed, a crash reported, an exception's text returned."""
    import select
    import signal
    timeout = GUARD_S if timeout is None else timeout
    if not _guard_ok():
        try:
            return fn(), None
        except Exception as exc:                        # noqa: BLE001
            return None, _msg(exc)
    try:
        r, w = os.pipe()
        pid = os.fork()
    except OSError:
        _GUARD_ON[0] = False
        return _guarded(fn, timeout)
    if pid == 0:                                        # the child
        try:
            os.close(r)
            try:
                res = fn()
                data = b"OK" + res.exportBrepToString().encode()
            except BaseException as exc:                # noqa: BLE001
                data = b"EX" + _msg(exc).encode()
            with os.fdopen(w, "wb") as fh:
                fh.write(data)
        finally:
            os._exit(0)
    os.close(w)
    chunks, t0, why = [], time.time(), None
    with os.fdopen(r, "rb") as fh:
        fd = fh.fileno()
        while True:
            left = timeout - (time.time() - t0)
            if left <= 0:
                why = "killed after %g s (OCCT hang)" % timeout
                break
            ready, _w, _x = select.select([fd], [], [], left)
            if not ready:
                continue
            b = os.read(fd, 1 << 20)
            if not b:
                break
            chunks.append(b)
    if why:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        _p, st = os.waitpid(pid, 0)
    except OSError:
        st = 0
    if why:
        return None, why
    data = b"".join(chunks)
    if data[:2] == b"EX":
        return None, data[2:].decode("utf-8", "replace")
    if data[:2] != b"OK":
        return None, "the OCCT call crashed (signal %d)" % (st & 0x7f)
    s = Part.Shape()
    s.importBrepFromString(data[2:].decode())
    return s, None


def _try_fillet(base, r, edges, v0):
    """(filleted solid, None) or (None, why)."""
    if not edges:
        return None, "no edges"
    t0 = time.time()
    res, why = _guarded(lambda: base.makeFillet(r, edges))
    if os.environ.get("ATECH_FORM_TRACE") == "1":
        print("  fillet r=%g on %d edges: %.2f s %s" % (r, len(edges), time.time() - t0,
                                                       why or "ok"))
    if res is None:
        return None, why
    if res.isNull() or not res.isValid() or len(res.Solids) != 1:
        return None, "result invalid"
    if not 0.6 * v0 < res.Volume < v0 + TOL:
        return None, "volume %.0f of %.0f" % (res.Volume, v0)
    return res.Solids[0], None


def _fillet_rungs(base, r, pick, finish, core, t0):
    """The makeFillet rungs on `base` (picked edges); each result passes
    finish() (None = reject). Returns (shape, rung, r) or (None, why, r)."""
    v0 = base.Volume
    last = "?"

    def go(res):
        return None if res is None else finish(res)
    cand = [e for e in base.Edges if pick(e)]
    hard = [e for e in cand if not _soft(base, e)]
    tried_all = False
    if _rung_on("all"):
        tried_all = True
        res, why = _try_fillet(base, r, cand, v0)
        res = go(res)
        if res is not None:
            return res, "all", r
        last = why or "result rejected"
    if _rung_on("sharp") and hard and not (tried_all and len(hard) == len(cand)):
        res, why = _try_fillet(base, r, hard, v0)
        res = go(res)
        if res is not None:
            return res, "sharp", r
        last = why or "result rejected"
    if core:
        return None, last, r
    if _rung_on("split") and time.time() - t0 < FILLET_BUDGET_S:
        vert = [e for e in hard if _vertical(e)]
        rest = [e for e in hard if not _vertical(e)]
        for first in (vert, rest):
            if not first or len(first) == len(hard):
                continue
            a, why = _try_fillet(base, r, first, v0)
            if a is None:
                last = why
                continue
            more = [e for e in a.Edges if pick(e) and not _soft(a, e)]
            b, why = _try_fillet(a, r, more, v0) if more else (a, None)
            b = go(b)
            if b is not None:
                return b, "split", r
            last = why or "result rejected"
    if _rung_on("shrink"):
        for k in (0.75, 0.5):
            if time.time() - t0 > FILLET_BUDGET_S:
                last += " (time budget %g s spent)" % FILLET_BUDGET_S
                break
            res, why = _try_fillet(base, r * k, hard or cand, v0)
            res = go(res)
            if res is not None:
                return res, "shrink", r * k
            last = why or "result rejected"
    return None, last, r


def _graze_hint(body):
    """' - ...' advice when an edge's faces meet almost tangent along part
    of it (where every fillet fails), else ''. R270 (MEASURED, round-1 toy
    car): the top edge ran from 90 deg along the sides to 9-12 deg where
    the side's rounded nose crossed the plan's rounded nose."""
    worst = None
    for e in body.Edges:
        a, b = e.ParameterRange
        d = _dihedrals(body, e, 9)
        if not d or max(d) < SOFT_DEG or min(d) >= SOFT_DEG:
            continue
        i = min(range(len(d)), key=lambda k: d[k])
        if worst is None or d[i] < worst[0]:
            worst = (d[i], e.valueAt(a + (b - a) * (i + 0.5) / len(d)))
    if worst is None:
        return ""
    p = worst[1]
    return (" - the faces meet at only %.0f deg near (%.1f, %.1f, %.1f): there the "
            "side and plan outlines cross almost tangent. End one outline >= 10 mm past "
            "the other there, or give the side a ('corner', p) where the nose starts"
            % (worst[0], p.x, p.y, p.z))


def _extended(body, r, what):
    """(body extended r + 1 below its flat bottom, the cut-back box, z of
    the extension's bottom) for the sharp-bottom fillet."""
    bb = _k()._tight_bbox(body)            # BoundBox is loose on splines
    z0 = bb.ZMin
    bot = _k().faces_at(body, "-Z")
    if not bot or abs(bot[0].BoundBox.ZMax - z0) > 1e-6:
        raise _err("%s: fillet=(r, r_bottom) needs a flat bottom - end the side "
                   "outline with ('line', p) along z = its lowest point" % what)
    d = r + 1.0
    big = _clean(body.fuse([f.extrude(App.Vector(0, 0, -d)) for f in bot]).removeSplitter())
    if len(big.Solids) != 1:
        raise _err("%s: extending the bottom for the fillet failed" % what)
    keep = Part.makeBox(bb.XLength + 20, bb.YLength + 20, bb.ZLength + 10,
                        App.Vector(bb.XMin - 10, bb.YMin - 10, z0))
    return big.Solids[0], keep, z0 - d


def _fillet_body(body, r_top, r_bot, z0, what, core=False):
    """profile_body's fillet: every edge at r_top, the bottom ones (z0) at
    r_bot when that is smaller (0 = sharp); radii <= 0.05 skip. The R270
    ladder above; core=True (an inset core) tries only all/sharp, then
    stays unfilleted (R250). Never raises while `body` is valid, unless
    the 'unfilleted' rung is switched off."""
    t0 = time.time()
    _FILLET_USED[0] = None
    if r_top <= 0.05:
        return body
    v_body = body.Volume
    sharp_bottom = r_bot < r_top
    last = "?"
    res = rung = None
    used = r_top
    if sharp_bottom:
        try:
            big, keep, zb = _extended(body, r_top, what)
        except _k().CadError as exc:
            big, last = None, str(exc)
        if big is not None:
            def finish(f):
                try:
                    c = _clean(f.common(keep))
                except Exception:                       # noqa: BLE001
                    return None
                if c.isValid() and len(c.Solids) == 1 and c.Volume > 0.6 * v_body:
                    return c.Solids[0]
                return None
            res, rung, used = _fillet_rungs(big, r_top, lambda e: e.BoundBox.ZMax > zb + 1e-6,
                                            finish, core, t0)
            if res is None:
                last = rung
    else:
        res, rung, used = _fillet_rungs(body, r_top, lambda e: True, lambda f: f, core, t0)
        if res is None:
            last = rung
    if res is not None:
        if used < r_top - 1e-9:
            print("profile_body: fillet r=%g did not fit, used r=%g" % (r_top, used))
        elif rung not in ("all",):
            print("profile_body NOTE: fillet r=%g worked on the '%s' rung (R270)" % (r_top, rung))
    if res is None and not core and _rung_on("soften"):
        import atech_detail
        pick = [e for e in body.Edges if e.BoundBox.ZMax > z0 + 1e-6 or not sharp_bottom]
        pick = [e for e in pick if not _soft(body, e)]
        r_s = 0.5 * r_top
        try:
            s = atech_detail.soften(body, r_s, pick, budget_s=8)
        except Exception as exc:                        # noqa: BLE001
            s, last = None, _msg(exc)
        if s is not None and s.isValid() and len(s.Solids) == 1 and (
                abs(s.Volume - v_body) > 1e-6 * v_body):
            res, rung = s.Solids[0], "soften"
            print("profile_body WARNING: fillet r=%g failed (%s); the top edges were "
                  "softened at r<=%g instead (R270)%s" % (
                      r_top, last, r_s, _graze_hint(body) or " - smoother outline knots "
                      "let the full fillet fit"))
    if res is None:
        if not _rung_on("unfilleted"):
            raise _err("%s: fillet r=%g failed on every rung (%s) - the outline has a "
                       "bend tighter than that: use a smaller fillet or smoother "
                       "outline points" % (what, r_top, last))
        _FILLET_USED[0] = "unfilleted"
        if not core:
            print("profile_body WARNING: fillet r=%g failed on every rung (%s) - the "
                  "body is returned UNFILLETED (R270). Round it with cad.soften(body, "
                  "r, edges) or use smoother outlines / a smaller fillet%s" % (
                      r_top, last, _graze_hint(body)))
        else:
            print("profile_body NOTE: inset core left unfilleted (%s)" % last[:120])
        return body
    _FILLET_USED[0] = rung
    body = res
    if sharp_bottom and r_bot > 0.05:
        try:
            body, _u = _fillet_ladder(body, r_bot, what, pick=lambda e:
                                      e.BoundBox.ZMax <= z0 + 1e-6)
        except _k().CadError as exc:
            print("profile_body WARNING: the bottom fillet r=%g failed (%s) - the "
                  "bottom edges stay sharp (R270)" % (r_bot, str(exc).split(" - ")[0][:120]))
    return body


def profile_body(side, plan, spline=True, fillet=None, at=(0, 0, 0), inset=0.0):
    """A sculpted body: side outline (XZ) extruded across, common with plan
    outline (XY) extruded up; fillet=r or (r, r_bottom) rounds it first;
    inset=t gives its core.

    side = [(0, 6), (4, 15), (52, 31), (92, 32), (140, 18),
            ('corner', (143, 8)), ('line', (140, 0)), ('line', (3, 0))]
    plan = [(0, -23), (30, -30), (110, -30), (143, -24), (143, 24), ...]
    body = cad.profile_body(side, plan, fillet=4)
    shell = cad.hollow(body, 2, core=lambda t: cad.profile_body(
        side, plan, fillet=4, inset=t))
    side (x = length, z = height) / plan (x = length, y = width): point
    lists (module doc: ('line', p) for a flat bottom) or closed wires/faces
    in those planes. inset shrinks both outlines and the fillet by `inset`:
    the exact inward offset, hollow()'s core. fillet=(r, 0) keeps the
    bottom edges sharp, needed to open the bottom (a rounded rim leaves a
    knife edge). A fillet that does not fit goes down the R270 ladder
    (soft creases skipped, vertical edges then the rest, 75/50 %, soften at
    r/2) and at worst the valid UNFILLETED body comes back with a WARNING
    - never a raise; a fillet bulging past the unfilleted box (OCCT does:
    0.63 mm under the car nose) is trimmed back. Side and plan ending
    tangent at the same x get the plan stretched TANGENT_GAP past (NOTE).
    `at` moves the result. MEASURED (R230): the 143 x 62 x 34 car above,
    0.6 s.
    """
    what = "profile_body"
    _tr("profile_body start")
    sf = _face(side, "XZ", spline, what + " side")
    pf = _face(plan, "XY", spline, what + " plan")
    if abs(_normal(sf).y) < 1 - 1e-6:
        raise _err("profile_body: the side outline must lie in the XZ plane "
                   "(points as (x, z))")
    if abs(_normal(pf).z) < 1 - 1e-6:
        raise _err("profile_body: the plan outline must lie in the XY plane "
                   "(points as (x, y))")
    if inset:
        if inset < 0:
            raise _err("profile_body: inset must be >= 0")
        sf = _offset_face(sf, -inset, what + " side inset")
        pf = _offset_face(pf, -inset, what + " plan inset")
    pf = _clear_tangent_ends(sf, pf, what)      # R270
    _tr("profile faces/insets")
    sb, pb = sf.BoundBox, pf.BoundBox
    if min(sb.XMax, pb.XMax) - max(sb.XMin, pb.XMin) <= 0.1:
        raise _err("profile_body: the side outline (x %.1f..%.1f) and the plan "
                   "outline (x %.1f..%.1f) do not overlap along X - both give the "
                   "length along X" % (sb.XMin, sb.XMax, pb.XMin, pb.XMax))
    s = sf.copy()
    s.translate(App.Vector(0, pb.YMin - 1.0 - sb.YMin, 0))
    s = s.extrude(App.Vector(0, pb.YLength + 2.0, 0))
    p = pf.copy()
    p.translate(App.Vector(0, 0, sb.ZMin - 1.0 - pb.ZMin))
    p = p.extrude(App.Vector(0, 0, sb.ZLength + 2.0))
    body = _clean(s.common(p))
    if body.isNull() or not body.isValid() or len(body.Solids) != 1:
        n = 0 if body.isNull() else len(body.Solids)
        raise _err("profile_body: side x plan gave %s - the plan must cover the "
                   "side outline's whole length (or the outlines leave %d "
                   "separate pieces)" % ("an invalid shape" if n == 1 else
                                         "%d solids" % n, n))
    body = body.Solids[0]
    _tr("profile common")
    raw_bb = body.optimalBoundingBox(False, False)
    _tr("profile raw bbox")
    if fillet:
        if isinstance(fillet, (tuple, list)):
            if len(fillet) != 2:
                raise _err("profile_body: fillet is r or (r, r_bottom)")
            r_top, r_bot = float(fillet[0]), float(fillet[1])
        else:
            r_top = r_bot = float(fillet)
        ins = float(inset or 0.0)
        r_top, r_bot = r_top - ins, r_bot - ins     # the inset core's radii
        if ins:
            # R250 (MEASURED): on an inset core a fillet of the offset
            # outlines under ~0.5 mm came back INVALID at every rung (car,
            # fillet=2.1 inset=2 -> r=0.1; a soap bar fillet=3 inset=2 ->
            # r=1 down to 0.3) and hollow() lost its exact core. A core
            # radius that small is left sharp: the wall at that edge is
            # then R - sqrt(2) (R - t) >= t - 0.21 mm, and hollow()
            # measures it.
            r_top = r_top if r_top >= CORE_MIN_R else 0.0
            r_bot = r_bot if r_bot >= CORE_MIN_R else 0.0
        z0 = raw_bb.ZMin                         # tight: BoundBox is loose
        try:
            body = _fillet_body(body, r_top, r_bot, z0, what, core=bool(ins))
        except _k().CadError as exc:
            if not ins:
                raise
            # R250: the core only - a sharp inset core is still inside the
            # body, a missing one fails hollow() altogether
            print("profile_body NOTE: inset=%g core left unfilleted (%s)" % (
                ins, str(exc).split(" - ")[0][:120]))
        _tr("profile fillet")
        if not inset:
            # not on an inset core: trimming its bulge leaves tiny edges on
            # its bottom (BOPAlgo TooSmallEdge) that broke the opening cut;
            # the bulge only thins the wall there and hollow() measures it
            body = _no_bulge(body, raw_bb, what)
        _tr("profile no_bulge")
    if tuple(_V(at)) != (0.0, 0.0, 0.0):
        body = body.copy()
        body.translate(_V(at))
    body = _solid(body, what)
    if not inset:
        # R270: hollow() rebuilds this body's exact core from the outlines
        _remember_profile(body, dict(side=side, plan=plan, spline=spline,
                                     fillet=fillet, at=at))
    return body


# R270: the outlines each profile_body result was built from, keyed by its
# geometry (a copy or a moved copy is a different key: then hollow() falls
# back to its other rungs)
_PROFILES = {}


def _shape_key(shape):
    try:
        bb = shape.BoundBox
        return (len(shape.Faces), round(shape.Volume, 3)) + tuple(
            round(x, 3) for x in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    except Exception:                                   # noqa: BLE001
        return None


def _remember_profile(body, args):
    if len(_PROFILES) > 256:
        _PROFILES.clear()
    k = _shape_key(body)
    if k is not None:
        _PROFILES[k] = args


def loft(sections, ruled=False, closed=False, solid=True):
    """A loft through closed section wires (rounded_rect_wire, spline_wire,
    circles) in order, checked: equal edge counts, no twist, one valid solid.

    body = cad.loft([cad.rounded_rect_wire(50, 18, 6, (0, 0, 14), 'X'),
                     cad.rounded_rect_wire(64, 30, 9, (60, 0, 17), 'X')])
    A point (x, y, z) is allowed as the first or last section (an apex).
    MEASURED (r2 gap 3): 5 rounded sections 0.00 s.
    """
    what = "loft"
    if len(sections) < 2:
        raise _err("loft: give at least 2 sections")
    shapes = []
    for i, s in enumerate(sections):
        if isinstance(s, Part.Face):
            s = s.OuterWire
        elif isinstance(s, Part.Edge):
            s = Part.Wire([s])
        elif isinstance(s, (App.Vector, tuple, list)) and len(s) == 3 and all(
                _num(c) for c in s):
            if i not in (0, len(sections) - 1):
                raise _err("loft: a point section is only allowed first or last")
            shapes.append(Part.Vertex(_V(s)))
            continue
        elif not isinstance(s, Part.Wire):
            raise _err("loft: section %d is a %s - give wires, faces or circle "
                       "edges" % (i, type(s).__name__))
        if not s.isClosed() and solid:
            raise _err("loft: section %d is not closed" % i)
        shapes.append(s)
    wires = [(i, w) for i, w in enumerate(shapes) if isinstance(w, Part.Wire)]
    counts = [len(w.Edges) for _i, w in wires]
    if len(set(counts)) > 1:
        raise _err("loft: the sections have %s edges - every section needs the "
                   "same count or the loft twists or fails. Build them all the "
                   "same way (rounded_rect_wire with r > 0 for each)" % counts)
    for (i, a), (j, b) in zip(wires, wires[1:]):
        try:
            ca, cb = a.CenterOfMass, b.CenterOfMass
            da = a.Vertexes[0].Point - ca
            db = b.Vertexes[0].Point - cb
            if da.Length > 1e-6 and db.Length > 1e-6 and da.getAngle(db) > math.radians(100):
                raise _err("loft: sections %d and %d start on opposite sides - "
                           "the loft would twist. Start every section at the "
                           "same corner" % (i, j))
            na, nb = _normal(Part.Face(a)), _normal(Part.Face(b))
            ax = cb - ca
            if ax.Length > 1e-6 and na.dot(ax) * nb.dot(ax) < 0:
                raise _err("loft: sections %d and %d run in opposite directions "
                           "(one clockwise) - the loft would twist. Reverse one" % (i, j))
        except _k().CadError:
            raise
        except Exception:                               # noqa: BLE001
            pass
    try:
        res = Part.makeLoft(shapes, bool(solid), bool(ruled), bool(closed))
    except Exception as exc:                            # noqa: BLE001
        raise _err("loft: FreeCAD could not loft these sections (%s)" % _msg(exc))
    if not solid:
        _k()._check(res, what)
        return res
    return _solid(res, what)


def extrude_profile(wire_or_points, height, taper_deg=0, direction="+Z"):
    """Extrude a closed outline (wire, face, or 2D points in the plane across
    `direction`) by height, with an optional draft taper_deg (> 0 narrows the
    far end).

    MEASURED (r2 gap 3): a taper is a ruled loft to the 2D offset outline,
    0.00 s (a Part::Extrusion with TaperAngle hung > 100 s - never use it).
    Points: Z -> (x, y), Y -> (x, z), X -> (y, z); plain points are polygon
    corners, ('arc', mid, end) arcs; pass cad.spline_wire(...) for curves.
    """
    what = "extrude_profile"
    if not _num(height) or height <= 0:
        raise _err("extrude_profile: height must be > 0 (flip `direction` instead)")
    (u, v), d = _frame(direction)
    if isinstance(wire_or_points, Part.Shape):
        f = _face(wire_or_points, "XY", False, what)
    else:
        pts = [p if (isinstance(p, (tuple, list)) and p and isinstance(p[0], str))
               or len(p) == 3 else u * float(p[0]) + v * float(p[1])
               for p in wire_or_points]
        pts = [tuple(p) if isinstance(p, App.Vector) else p for p in pts]
        f = _face(pts, "XY", False, what)
    vec = d * float(height)
    if not taper_deg:
        return _solid(f.extrude(vec), what)
    if abs(abs(_normal(f).dot(d)) - 1) > 1e-6:
        raise _err("extrude_profile: a taper needs the outline square to "
                   "`direction` - it is tilted")
    if abs(taper_deg) >= 60:
        raise _err("extrude_profile: taper_deg must be under 60")
    off = float(height) * math.tan(math.radians(taper_deg))
    top = _offset_face(f, -off, what + " taper", join=2)
    if len(top.OuterWire.Edges) != len(f.OuterWire.Edges):
        raise _err("extrude_profile: a %g deg taper over %g mm closes up part of "
                   "the outline (%d edges -> %d) - use a smaller taper or a lower "
                   "height" % (taper_deg, height, len(f.OuterWire.Edges),
                               len(top.OuterWire.Edges)))
    tw = top.OuterWire.copy()
    tw.translate(vec)
    res = _solid(Part.makeLoft([f.OuterWire, tw], True, True), what)
    lo, hi = sorted((f.Area, top.Area))
    if not (lo * height * 0.999 <= res.Volume <= hi * height * 1.001):
        raise _err("extrude_profile: the taper built %.1f mm3, outside the %.1f.."
                   "%.1f mm3 its end areas allow - nothing returned"
                   % (res.Volume, lo * height, hi * height))
    return res


# ---------------------------------------------------------------- hollow
def _open_list(shape, open_faces):
    faces = []
    for f in open_faces or ():
        if isinstance(f, str):
            got = _k().faces_at(shape, f)
            if not got:
                raise _err("hollow: the body has no flat face facing %s to open "
                           "- flatten that side (('line', p) in the outline)" % f)
            faces.extend(got)
        elif isinstance(f, Part.Face):
            faces.append(f)
        else:
            raise _err("hollow: open_faces holds faces or directions like '-Z'")
    return faces


def _flat(f):
    """Planar face - also a plane that transformGeometry turned into a
    BSpline surface (the scaled core, MEASURED R230)."""
    if isinstance(f.Surface, Part.Plane):
        return True
    try:
        return f.findPlane() is not None
    except Exception:                                   # noqa: BLE001
        return False


def _floor_tools(shape, faces, t):
    """Through-floor cutters made from the OPEN FACES themselves (clean
    outlines): each shrunk t + 0.01, from 0.5 mm outside to 0.3 mm past
    the floor. The fallback when the core's own end faces will not cut."""
    tools = []
    for of in faces:
        n = _k()._outward(shape, of, _normal(of))
        g = _offset_face(of, -(t + 0.01), "hollow opening")
        g.translate(n * 0.5)
        tools.append(g.extrude(n * -(t + 0.8)))
    return tools


def _void(shape, c, t, v0, extra=(), open_floor=0.0, alt=(), faces=()):
    """(shape with the core `c` cut out as a sealed cavity, min wall, rim);
    ValueError when the core is not strictly inside, the wall is under
    t / 2, or the core's volume is not what a t wall leaves.

    A REAL cut (R230, MEASURED): a solid built from the outer shell plus
    the reversed core shell skips the boolean (0.2 s against 1.5-3 s), but
    later booleans on it are not safe: the bottom opening cut through the
    car's floor left the floor in place (valid, 7472 mm2 of floor), and
    with other cores a split's lower half came out 0 solids. The volume
    test catches a wrong core (a 145 019 mm3 one where 163 597 was due).
    """
    removed = v0 - c.Volume
    ta = t * shape.Area
    if not 0.5 * ta < removed < 1.05 * ta:
        raise ValueError("the core leaves %.0f mm3 of wall where a %g mm skin "
                         "is about %.0f" % (removed, t, ta))
    mw = _gap(c.Shells[0], shape.Shells[0])
    if mw < 0.5 * t:
        raise ValueError("min wall %.2f mm < half of t" % mw)
    if not shape.isInside(c.Vertexes[0].Point, 1e-6, False):
        raise ValueError("the core is outside the body")
    # Openings, in order: the core cut, then cutters made from the open
    # faces (`alt`: clean outlines, and the rim keeps its full t - MEASURED
    # R230 1.97 mm at the car nose where the core's own faces gave 0.96);
    # one cut of the core with its end faces (`extra`); the core, then
    # those. The inset core OCCT builds varies run to run (163 719 ..
    # 163 832 mm3) and with some of them the `extra` cuts left the floor
    why = "?"
    closed = None
    for attempt in range(3 if extra else 2):
        try:
            if not extra:
                res = _clean(shape.cut(c))
            elif attempt == 1:
                res = _clean(shape.cut([c] + list(extra)))
            else:                   # the core, then the openings
                if closed is None:
                    closed = _clean(shape.cut(c))
                res = _clean(closed.cut(list(alt if attempt == 0 else extra)))
        except Exception as exc:                        # noqa: BLE001
            why = _msg(exc)
            continue
        if res.isNull() or not res.isValid() or len(res.Solids) != 1:
            why = "the core cut is invalid"
            continue
        # what is left must be the t skin (`removed` = v0 - core); with
        # the openings, at least half their floor less
        left = res.Volume
        # R270: 1 % of the body, not 0.2 %: OCCT's Volume of an inset
        # spline core is itself that far off (MEASURED: the round-1 car's
        # t=5 profile core 876 356 mm3, its cut removed 869 235 - a valid
        # cavity; a mesh of the result agreed with neither). A core that
        # did not cut is still caught (it removes ~0 or a whole wall more)
        if extra:
            bad = left > removed - 0.5 * open_floor + VOL_RTOL * v0
        else:
            bad = abs(left - removed) > VOL_RTOL * v0
        if bad:
            why = "the core cut removed %.0f mm3, the core is %.0f" % (v0 - left, c.Volume)
            continue
        if not faces:
            return res.Solids[0], mw, None
        # R250 (MEASURED, the toy car's hardtop: a sloped windscreen over
        # an open bottom): the open-face cutters (`alt`, attempt 0) reach
        # t in from the rim everywhere, and where the wall above slopes
        # inward they cut 0.22 mm from its outer skin. The volume test
        # cannot see it (they removed 451 mm3 MORE floor, not less); the
        # measured wall can - so a thin result moves on to the next
        # attempt (the core's own end faces: 1.77 mm) instead of failing
        # the whole rung.
        mw_a, rim = _min_wall(res.Solids[0], shape, faces, t)
        if mw_a is not None and mw_a < 0.5 * t:
            why = "min wall %.2f mm < half of t (opening cut %d)" % (mw_a, attempt)
            continue
        return res.Solids[0], mw_a, rim
    raise ValueError(why)


def _open_end_area(core, shape, of):
    """Area of the core's flat faces looking out through open face `of`."""
    n = _k()._outward(shape, of, _normal(of))
    return sum(f.Area for f in core.Faces if _flat(f)
               and _k()._outward(core, f, _normal(f)).dot(n) > 1 - 1e-6)


def _open_tools(shape, core, faces, t):
    """For each open face: the core's flat faces looking out of it, 0.01 mm
    smaller, from 0.5 mm inside the core out through the opening. Smaller,
    so no tool face lies ON a core face: unshrunk, the cut came out invalid
    on the car every run (MEASURED R230); the 0.01 mm step it leaves inside
    the rim is invisible. (A core whose bulge was trimmed carried tiny
    edges that made this offset BOP-broken - cores are not trimmed.)"""
    span = shape.BoundBox.DiagonalLength + t + 1.0
    tools = []
    for of in faces:
        n = _k()._outward(shape, of, _normal(of))
        ends = [f for f in core.Faces if _flat(f)
                and _k()._outward(core, f, _normal(f)).dot(n) > 1 - 1e-6]
        if not ends:
            raise _err("no flat core face behind the opening")
        for f in ends:
            try:
                g = _offset_face(f, -0.01, "hollow opening")
            except _k().CadError:
                g = f.copy()
            g.translate(n * -0.5)
            tools.append(g.extrude(n * (span + 0.5)))
    return tools


VOL_RTOL = 1e-2             # R270: see _void
THICK_GUARD_S = 30.0        # R270: a makeThickness taking longer is killed
FIT_STEPS = (1.0, 1.2, 1.45, 1.75, 2.1, 2.6, 3.2)    # R270: fitted core scale steps (x t)
_HOLLOW_OFF = set()         # R270: rungs switched off (sabotage runs)
_HOLLOW_ONLY = [None]       # R270: tests isolate rungs: a tuple of names


def hollow(shape, t, open_faces=(), core=None):
    """Hollow a solid to wall t (open_faces like ['-Z']; core=lambda t:
    cad.profile_body(..., inset=t) for curved bodies); prints the rung used
    and the min wall.

    Rungs, in order: core(t) - the caller's exact inset body; the profile
    core (a profile_body result: its own outlines at inset=t, R270);
    makeThickness join 2, join 0 (plain surfaces; LAST on spline bodies,
    where it ran 100-185 s, R270); OCCT's offset core (plain surfaces
    only: it ran > 50 s on a filleted spline body); a scaled core (uneven
    walls); the fitted core (scaled until the measured wall is >= t,
    R270). Every rung is checked: one valid solid, the volume a t skin
    leaves (not the fitted core), measured wall >= t / 2; the one that
    worked is printed as a NOTE. An opened face with ROUNDED rim edges raises (knife edge):
    use profile_body(fillet=(r, 0)) or hollow closed and split().
    MEASURED (R230) on the 143 mm car, t=2: closed 1.8-3.6 s, open bottom
    5.2 s (up to 8 s on a fallback cut); thinnest wall 1.4 mm where three
    fillets meet under the nose (OCCT's fillet bulge on the core).
    """
    what = "hollow(t=%g)" % t
    if not _num(t) or t <= 0:
        raise _err("hollow: t must be > 0")
    _k()._check(shape, "hollow: input", solids=1)
    shape = shape.Solids[0]
    faces = _open_list(shape, open_faces)
    try:
        _k()._shell_limit(shape, t, faces)
    except AttributeError:
        pass
    except _k().CadError as exc:
        raise _err(str(exc).replace("shell(", "hollow(", 1))
    v0 = shape.Volume
    open_area = sum(f.Area for f in faces)

    def thick(join):
        # R270: the offset runs guarded (102.7 s and 184.8 s on the round-1
        # robot torso); the cut stays here - a boolean in a forked child
        # deadlocks on OCCT's thread pool (MEASURED: killed at 5 s)
        if faces:
            run = lambda: shape.makeThickness(faces, -t, 1e-3, False, False, 0, join)  # noqa: E731
        else:
            run = lambda: shape.makeOffsetShape(-t, 1e-3, False, False, 0, join)  # noqa: E731
        res, why = _guarded(run, THICK_GUARD_S)
        if res is None:
            raise ValueError(why)
        return res if faces else shape.cut(res)

    def offset_core():
        last = None
        for join in (0, 2):
            try:
                c = _clean(shape.makeOffsetShape(-t, 1e-3, False, False, 0, join))
                _k()._check(c, "core", solids=1)
                return c.Solids[0]
            except Exception as exc:                    # noqa: BLE001
                last = exc
        raise last

    def given_core():
        c = core(t)
        _k()._check(c, "core(t)", solids=1)
        return c.Solids[0]         # inside? checked by volume below (cheap)

    def scaled_core():
        bb = shape.BoundBox
        cen = bb.Center
        m = App.Matrix()
        m.scale(*[(L - 2 * t) / L for L in (bb.XLength, bb.YLength, bb.ZLength)])
        c = shape.copy()
        c.translate(-cen)
        c = c.transformGeometry(m)
        c.translate(cen)
        return _solid(c, "scaled core")

    prof = _PROFILES.get(_shape_key(shape))

    def profile_core():
        # R270 (a): the body came from profile_body - its exact core is
        # the same outlines with inset=t, rebuilt here (no core= needed)
        a = prof
        return profile_body(a["side"], a["plan"], spline=a["spline"], fillet=a["fillet"],
                            at=a["at"], inset=t)

    def fitted():
        # R270 (b): a copy scaled about the tight box centre, shrunk until
        # the MEASURED wall is >= t everywhere; walls come out uneven (up
        # to k t), so no skin-volume test - only: valid, one solid, sealed
        # core strictly inside, every opening reaching the cavity
        bb = _k()._tight_bbox(shape)
        cen = bb.Center
        best = None
        for k in FIT_STEPS:
            fs = [(L - 2 * t * k) / L for L in (bb.XLength, bb.YLength, bb.ZLength)]
            if min(fs) < 0.15:
                break
            m = App.Matrix()
            m.scale(*fs)
            cc = shape.copy()
            cc.translate(-cen)
            cc = cc.transformGeometry(m)
            cc.translate(cen)
            try:
                cc = _solid(cc, "fitted core")
            except Exception:                           # noqa: BLE001
                continue
            if not shape.isInside(cc.Vertexes[0].Point, 1e-6, False):
                continue
            g = _gap(cc.Shells[0], shape.Shells[0])
            if best is None or g > best[1] + 1e-6:
                best = (cc, g)
            if g >= 0.999 * t:
                break
        # a body that is not round (a car's cabin over its bonnet: best
        # 0.74 mm for t=2, MEASURED) never reaches t by scaling - the
        # thickest-walled scale is kept when it holds half of t (an
        # erosion by moved copies was tried: OCCT's common of a spline
        # body with its own copy moved along X came back EMPTY)
        if best is None or best[1] < 0.5 * t:
            raise ValueError("no scale leaves half of a %g mm wall%s" % (
                t, "" if best is None else " (best %.2f mm)" % best[1]))
        c, gap = best
        res = _clean(shape.cut(c))
        # topology, not Volume: OCCT's Volume of a transformGeometry'd
        # (scaled) spline core is up to 15 % off (MEASURED R270)
        if res.isNull() or not res.isValid() or len(res.Solids) != 1 or len(res.Shells) != 2:
            raise ValueError("the fitted core cut did not leave one sealed cavity")
        if faces:
            tools, probes = [], []
            for of in faces:
                n = _k()._outward(shape, of, _normal(of))
                g = _offset2d(of, -(t + 0.01), "hollow opening")
                deep = c.distToShape(of)[0] + 0.6
                probes.append(_face_point(g) - n * (0.5 * deep))
                g.translate(n * 0.5)
                tools.append(g.extrude(n * -(deep + 0.5)))
            res = _clean(res.cut(tools))
            if res.isNull() or not res.isValid() or len(res.Solids) != 1:
                raise ValueError("the opening cut through the fitted wall is invalid")
            if any(res.isInside(p, 1e-6, True) for p in probes):
                raise ValueError("the openings did not reach the cavity")
        print("hollow NOTE: fitted core: scaled about the box centre, measured wall "
              "%.2f mm (asked %g); walls come out uneven (R270)" % (gap, t))
        return res

    # Order (R230, MEASURED on the toy-car body): the caller's exact core
    # first (0.7 s, never hangs), then makeThickness (exact, 0.1-0.3 s when
    # it works), and OCCT's own 3D offset core last: on a filleted spline
    # body that one ran > 50 s without an answer, so it is tried on
    # elementary surfaces (planes, cylinders, cones, spheres, tori) only.
    # R270 (MEASURED, round-1 desk robot: a 40-knot lofted pebble torso):
    # makeThickness join=2 102.7 s and join=0 184.8 s, both failing, before
    # the scaled core worked - on a body with spline surfaces it now runs
    # LAST, after the cores (the profile core, the fitted core) that answer
    # in seconds.
    rungs = []
    if core is not None:
        if not callable(core):
            raise _err("hollow: core must be a callable t -> inset body")
        rungs.append(("core(t)", None, given_core))
    if prof is not None:
        rungs.append(("profile core", None, profile_core))
    elem = _elementary(shape)
    thick_rungs = [("makeThickness join=2", lambda: thick(2), None),
                   ("makeThickness join=0", lambda: thick(0), None)]
    if elem:
        rungs += thick_rungs
    if faces and elem:
        rungs.append(("offset core", None, offset_core))
    rungs.append(("scaled core", None, scaled_core))
    rungs.append(("fitted core", fitted, None))
    if not elem:
        rungs += thick_rungs
    rungs = [r for r in rungs if r[0] not in _HOLLOW_OFF
             and (_HOLLOW_ONLY[0] is None or r[0] in _HOLLOW_ONLY[0])]
    knife = faces and any(_rounded_rim(shape, f, e) for f in faces for e in f.Edges)
    log = []
    t_all = time.time()
    trace = os.environ.get("ATECH_FORM_TRACE") == "1"
    for name, direct, mk in rungs:
        t0 = time.time()
        if trace:
            print("hollow: trying %s" % name)
        if knife and (mk is not None or name == "fitted core"):
            # a core cut straight through a rounded rim always leaves a
            # knife edge: refuse at once (the scaled core alone took 5 s
            # to find that out on the car, MEASURED R230)
            log.append("%s skipped (rounded rim)" % name)
            continue
        try:
            mw = rim = None
            if direct is not None:
                res = direct()
            else:
                # core strictly inside (measured gap) -> sealed cavity,
                # then the openings cut through the floor
                _tr("hollow start")
                c = mk()
                _tr("hollow core built")
                extra = _open_tools(shape, c, faces, t) if faces else ()
                # the openings must remove at least half the floor under
                # the core's flat ends (t x their area): a cut that "worked"
                # but left the floor in place passed the old test (R230)
                floor = t * sum(_open_end_area(c, shape, f) for f in faces)
                alt = _floor_tools(shape, faces, t) if faces else ()
                res, mw, rim = _void(shape, c, t, v0, extra, floor, alt, faces)
                _tr("hollow core cut")
            res = _clean(res)
            if res.isNull() or not res.isValid() or len(res.Solids) != 1:
                raise ValueError("invalid result" if res.isNull() or not res.isValid()
                                 else "%d solids" % len(res.Solids))
            res = res.Solids[0]
            if not (TOL < res.Volume < v0 - TOL):
                raise ValueError("did not get hollow")
            if direct is None:
                wall = (v0 - res.Volume) - c.Volume
                if wall < -0.01 * c.Volume:
                    raise ValueError("the core pokes out of the body")
                if wall > 1.05 * t * open_area + 1e-3 * v0:
                    raise ValueError("the opening cut breaches the side walls")
            if mw is None:
                mw, rim = _min_wall(res, shape, faces, t)
                _tr("hollow min wall")
            if mw is not None and mw < 0.5 * t:
                raise ValueError("min wall %.2f mm < half of t" % mw)
        except Exception as exc:                        # noqa: BLE001
            log.append("%s failed %.2f s (%s)" % (name, time.time() - t0, _msg(exc)[:80]))
            continue
        print("hollow NOTE: %s worked (%.2f s%s), min wall %s mm (asked %g)%s" % (
            name, time.time() - t_all, "; " + "; ".join(log) if log else "",
            "?" if mw is None else "%.2f" % mw, t,
            "" if rim is None else ", rim at the opening %.2f mm" % rim))
        return res
    hint = (" The opened face meets ROUNDED edges, so its rim would be a knife "
            "edge: keep those edges sharp (profile_body(fillet=(r, 0)) for an "
            "open bottom), or hollow closed and cad.split() the body." if knife else "")
    raise _err("%s: every rung failed: %s.%s Pass core=lambda t: "
               "cad.profile_body(..., inset=t) (the exact core), or a thinner "
               "wall" % (what, "; ".join(log), hint))


def _rounded_rim(shape, face, edge):
    """True when the face across `edge` from `face` is tangent to it (a
    fillet runs into the opening)."""
    try:
        for g in shape.ancestorsOfType(edge, Part.Face):
            if g.isSame(face):
                continue
            p = edge.valueAt(0.5 * sum(edge.ParameterRange))
            u, v = g.Surface.parameter(p)
            return abs(g.normalAt(u, v).dot(_normal(face))) > 0.99
    except Exception:                                   # noqa: BLE001
        return False
    return False


# ------------------------------------------------------------------ sweeps
def _min_bend(path):
    rmin = float("inf")
    for e in path.Edges:
        if isinstance(e.Curve, Part.Line):
            continue
        a, b = e.ParameterRange
        for i in range(61):
            try:
                k = e.curvatureAt(a + (b - a) * i / 60.0)
            except Exception:                           # noqa: BLE001
                continue
            if k > 1e-12:
                rmin = min(rmin, 1.0 / k)
    return rmin


def pipe(path_pts, r=None, profile=None, spline=True, frenet=False, caps="round"):
    """A tube of radius r (or a closed `profile`) swept along a path through 3D
    points (spline by default) or along a wire, checked against pi r^2 L.

    handle = cad.pipe([(0, 0, 0), (10, 0, 15), (40, 0, 20), (60, 0, 0)], r=3)
    profile: a wire placed at the path start, or 2D points in the plane
    square to the start tangent. caps='round' adds a ball on each open end
    (round profile only). frenet=True for helices. Raises when r is not
    under the path's tightest bend radius (the sweep would cross itself).
    """
    what = "pipe"
    if isinstance(path_pts, Part.Shape):
        path = path_pts if isinstance(path_pts, Part.Wire) else Part.Wire(path_pts.Edges)
    else:
        pts = [_V(p) for p in path_pts]
        if len(pts) < 2:
            raise _err("pipe: the path needs at least 2 points")
        if spline and len(pts) > 2:
            c = Part.BSplineCurve()
            c.interpolate(pts)
            path = Part.Wire([c.toShape()])
        else:
            path = Part.makePolygon(pts)
    e0 = path.OrderedEdges[0] if hasattr(path, "OrderedEdges") else path.Edges[0]
    p0 = path.OrderedVertexes[0].Point
    a, b = e0.ParameterRange
    tan = e0.tangentAt(a)
    if (e0.valueAt(a) - p0).Length > (e0.valueAt(b) - p0).Length:
        tan = -e0.tangentAt(b)
    if profile is None:
        if not _num(r) or r <= 0:
            raise _err("pipe: give r > 0 or a profile")
        rb = _min_bend(path)
        if r >= 0.95 * rb:
            raise _err("pipe: r=%g is not under the path's tightest bend radius "
                       "%.2f mm - the tube would cross itself. Use r < %.2f or "
                       "spread the path points" % (r, rb, 0.9 * rb))
        prof = Part.Wire([Part.makeCircle(float(r), p0, tan)])
    elif isinstance(profile, Part.Shape):
        prof = profile.OuterWire if isinstance(profile, Part.Face) else (
            profile if isinstance(profile, Part.Wire) else Part.Wire(profile.Edges))
    else:
        (u, v), _n = _frame(tan)
        pts = [tuple(p0 + u * float(q[0]) + v * float(q[1])) for q in profile]
        prof = _wire(pts, True, "XY", False, "pipe profile")
    transition = 0 if spline else 2
    try:
        res = path.makePipeShell([prof], True, bool(frenet), transition)
    except Exception as exc:                            # noqa: BLE001
        raise _err("pipe: the sweep failed (%s) - smooth the path or use a "
                   "smaller profile" % _msg(exc))
    res = _solid(res, what)
    if profile is None:
        want = math.pi * r * r * path.Length
        if abs(res.Volume - want) > 0.03 * want + 1e-3:
            raise _err("pipe: the tube is %.1f mm3 where pi r^2 L = %.1f - it "
                       "crosses itself. Use a smaller r or a gentler path"
                       % (res.Volume, want))
        if caps == "round" and not path.isClosed():
            p1 = path.OrderedVertexes[-1].Point
            res = _k().fuse_one(res, Part.makeSphere(float(r), p0),
                                Part.makeSphere(float(r), p1))
    elif caps not in ("round", "flat"):
        raise _err("pipe: caps is 'round' or 'flat'")
    return res


def revolve_profile(points_xz, angle=360, spline=False, axis="Z", at=(0, 0, 0)):
    """Revolve a closed (radius, height) profile about `axis` through `at`;
    points may include ('arc', mid, end) and ('line', p), spline=True smooths
    plain points.

    cad.revolve_profile([(0, 0), (12, 0), ('arc', (14, 2), (12, 4)), (0, 4)])
    Radial direction: +X for axes Z and Y, +Y for axis X. Every radius must
    be >= 0 (the profile may touch the axis, never cross it).
    """
    what = "revolve_profile"
    ax = _k()._dir(axis, "axis")
    k = max(range(3), key=lambda i: abs((ax.x, ax.y, ax.z)[i]))
    radial = App.Vector(0, 1, 0) if k == 0 else App.Vector(1, 0, 0)
    if abs(radial.dot(ax)) > 1e-9:
        radial = radial - ax * radial.dot(ax)
        radial.normalize()
    items = []
    for p in points_xz:
        if isinstance(p, (tuple, list)) and p and isinstance(p[0], str):
            items.append((p[0],) + tuple(tuple(radial * q[0] + ax * q[1]) for q in p[1:]))
        else:
            items.append(tuple(radial * float(p[0]) + ax * float(p[1])))
    f = _face(items, "XZ", spline, what)
    lo = min(radial.dot(vx.Point) for vx in f.Vertexes)
    try:
        lo = min(lo, min(radial.dot(f.OuterWire.discretize(200)[i])
                         for i in range(200)))
    except Exception:                                   # noqa: BLE001
        pass
    if lo < -1e-6:
        raise _err("revolve_profile: the profile reaches radius %.3f < 0 - it "
                   "crosses the axis. Keep every radius >= 0" % lo)
    if not _num(angle) or not 0 < angle <= 360:
        raise _err("revolve_profile: angle must be in (0, 360]")
    f.translate(_V(at))
    res = f.revolve(_V(at), ax, float(angle))
    return _solid(res, what)


# ---------------------------------------------------------------- symmetry
def _mplane(plane, what):
    if isinstance(plane, str):
        return _V(_PLANE_NORMAL[_plane(plane, what)])
    return _k()._dir(plane, "plane normal")


def mirror(shape, plane="XZ", through=(0, 0, 0)):
    """A mirrored copy of `shape` in the plane 'XZ' (flips Y), 'XY' (flips Z),
    'YZ' (flips X) or one with a given normal vector, through the point
    `through`."""
    res = shape.mirror(_V(through), _mplane(plane, "mirror"))
    _k()._check(res, "mirror")
    return _one(res)


def _one(s):
    return s.Solids[0] if len(s.Solids) == 1 else s


def symmetric(shape, plane="XZ", through=(0, 0, 0)):
    """One solid: `shape` fused with its mirror image - model one half crossing
    the plane by 0.5 mm, get the whole symmetric body."""
    m = mirror(shape, plane, through)
    try:
        return _k().fuse_one(shape, m)
    except _k().CadError as exc:
        raise _err("symmetric: %s. The half must CROSS the mirror plane by "
                   ">= 0.5 mm (not stop on it or short of it)" % exc)


def mirror_pair(shape, plane="XZ", through=(0, 0, 0)):
    """(shape, its mirror) as two separate bodies, for left/right parts like
    lights and mirrors; raises when the two overlap."""
    m = mirror(shape, plane, through)
    try:
        ov = shape.common(m).Volume
    except Exception:                                   # noqa: BLE001
        ov = 0.0
    if ov > 1e-3:
        raise _err("mirror_pair: the part and its mirror overlap by %.2f mm3 - "
                   "it crosses the mirror plane. Move it off the plane, or use "
                   "cad.symmetric() for one body" % ov)
    return shape.copy(), m


# ------------------------------------------------------------------- split
def _common2d(a, b):
    """The overlap of two coplanar one-loop faces as one smooth face, or
    None. Done on 0.5 mm polygons and refit: the exact common of two
    200-pole spline faces took 1.5 s (MEASURED R230), the polygons 0.1 s;
    the refit sits within ~0.01 mm. Skipped (a returned as is) when every
    sampled point of a's outline is inside b."""
    try:
        if all(b.isInside(p, 1e-6, True) for p in a.OuterWire.discretize(Number=120)):
            return a
        polys = []
        for f in (a, b):
            pts = f.OuterWire.discretize(Distance=0.5)
            if (pts[0] - pts[-1]).Length > 1e-9:
                pts.append(pts[0])
            polys.append(Part.Face(Part.makePolygon(pts)))
        c = polys[0].common(polys[1])
        fs = sorted(c.Faces, key=lambda f: -f.Area)
        if not fs or (len(fs) > 1 and fs[1].Area > 0.02 * fs[0].Area):
            return None
        f = Part.Face(_loop(fs[0].OuterWire.discretize(Distance=0.25)[:-1]))
        return f if f.isValid() and f.Area > 0.5 * min(a.Area, b.Area) else None
    except Exception:                                   # noqa: BLE001
        return None


def _split_plane(body, n, at, half):
    """(lower, upper) of `body` cut by the plane n . p = at: ONE general
    split (BOPTools.SplitAPI, 0.45 s on the car shell where two commons
    took 0.75 s, MEASURED R230), the two commons as the fallback."""
    try:
        import BOPTools.SplitAPI as SA
        bb = body.BoundBox
        big = bb.DiagonalLength + 10.0
        (u, v), _n = _frame(n)
        c = bb.Center - n * (bb.Center.dot(n) - at)
        pl = Part.Face(Part.makePolygon([c + (u * x + v * y) * big for x, y in
                                         ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))]))
        lo, up = [], []
        # on a COPY: a general split may raise the input's tolerances
        for p in SA.slice(body.copy(), [pl], "Split").Solids:
            (lo if p.CenterOfMass.dot(n) < at else up).append(p)
        if len(lo) == 1 and len(up) == 1:
            return lo[0], up[0]
    except Exception:                                   # noqa: BLE001
        pass
    return _clean(body.common(half(-1))), _clean(body.common(half(+1)))


def split(body, plane_axis="Z", at=None, lip=0.0, clearance=0.2):
    """Split a (hollow) body at plane_axis = at into (lower, upper), each one
    solid; lip > 0 raises an inner-half-wall lip on lower that keys into a
    matching groove in upper.

    chassis, shell = cad.split(hollow_body, 'Z', at=12, lip=2)
    at=None splits at the middle. The lip is the inner half of the measured
    wall (the upper keeps >= 0.9 mm of skin) plus 1 mm standing into the
    cavity, kept inside the outer skin up to its top; the upper's groove
    leaves `clearance` all round. MEASURED (R230) on the 143 mm car shell:
    0.6 s without a lip, 3.8-5.7 s with one. R270: a lip that cannot be
    built (a solid section, a wall under 1.3 mm + clearance, an outline
    that falls apart) prints a WARNING and splits with lip=0; a plane that
    gives an invalid half is moved up to 3 mm (printed NOTE).
    """
    what = "split"
    key = str(plane_axis).strip().upper().lstrip("+-")
    if key not in ("X", "Y", "Z"):
        raise _err("split: plane_axis is 'X', 'Y' or 'Z'")
    k = "XYZ".index(key)
    n = App.Vector(*[1.0 if i == k else 0.0 for i in range(3)])
    _k()._check(body, "split: input", solids=1)
    body = body.Solids[0]
    # R270: the TIGHT box - BoundBox is loose on splines, and a plane inside
    # the loose box but past the body gave "the lower part is 0 solids"
    bb = _k()._tight_bbox(body)
    lo_b = (bb.XMin, bb.YMin, bb.ZMin)[k]
    hi_b = (bb.XMax, bb.YMax, bb.ZMax)[k]
    if at is None:
        at = 0.5 * (lo_b + hi_b)
    if not lo_b + 0.1 < at < hi_b - 0.1:
        raise _err("split: at=%g is outside the body (%s %.2f..%.2f)" % (at, key, lo_b, hi_b))
    if lip and (lip < 0 or clearance < 0):
        raise _err("split: lip and clearance must be >= 0")
    if not lip:
        return _split_nudge(body, key, k, n, at, clearance, lo_b, hi_b)
    # R250 (MEASURED, the toy-car tub split at its floor's inner face
    # z = 9.5 with a lip): "almost no room for a lip" there and "section is
    # solid" 0.01 below it - the plane lies ON (or just inside) a wall's
    # flat face. Split 0.01 mm into the cavity instead, said out loud.
    near = _nudged(body, n, at)
    if near is not None and abs(near - at) <= 0.0101:
        print("split NOTE: %s=%g lies on a flat wall face - split at %s=%g, 0.01 mm "
              "into the cavity (R250)" % (key, at, key, near))
        at = near
    try:
        return _split_at(body, key, k, n, at, lip, clearance)
    except _k().CadError as exc:
        first = exc
    alt = _nudged(body, n, at)
    if alt is not None:
        print("split NOTE: the section at %s=%g is not a hollow ring - %g mm off a wall's "
              "flat face; split at %s=%g, 0.01 mm into the cavity (R250)"
              % (key, at, abs(alt - at), key, alt))
        try:
            return _split_at(body, key, k, n, alt, lip, clearance)
        except _k().CadError as exc:
            first = exc
    # R270 (MEASURED, round 1: ~14 split failures - "section is solid" on
    # the toy car at Z=11.5, "wall 0.96 mm - too thin for a lip" and "lower
    # part invalid" on the desk robot): a lip that cannot be built no
    # longer costs the turn - the halves are split WITHOUT it, said loudly
    if "lip0" in _SPLIT_OFF:
        raise first
    print("split WARNING: no lip at %s=%g (%s) - split WITHOUT a lip (lip=0) instead "
          "(R270). For a lip: hollow first, split where the wall is >= %.1f mm, "
          "0.3-1 mm inside the cavity" % (key, at, str(first).split(" - ")[0][7:160],
                                         1.3 + clearance))
    return _split_nudge(body, key, k, n, at, clearance, lo_b, hi_b)


SPLIT_NUDGE = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 3.0)    # R270: mm, both ways
_SPLIT_OFF = set()      # 'lip0', 'nudge3': R270 fallbacks switched off (sabotage)


def _split_nudge(body, key, k, n, at, clearance, lo_b, hi_b):
    """A plain split at `at`; when the plane gives an invalid or missing
    half (it grazes a seam or a tangent face: the desk robot's torso at
    Y=2.2, MEASURED), the plane moved up to 3 mm either way (R270)."""
    try:
        return _split_at(body, key, k, n, at, 0.0, clearance)
    except _k().CadError as exc:
        first = exc
    if "nudge3" in _SPLIT_OFF:
        raise first
    for d in SPLIT_NUDGE:
        for a in (at + d, at - d):
            if not lo_b + 0.3 < a < hi_b - 0.3:
                continue
            try:
                res = _split_at(body, key, k, n, a, 0.0, clearance)
            except _k().CadError:
                continue
            print("split NOTE: the plane %s=%g gave %s; split at %s=%g instead (%+g mm, "
                  "R270)" % (key, at, str(first).split(" - ")[0][7:100], key, a, a - at))
            return res
    raise first


SHELL_MIN_WALL = 0.8     # R270: ./check's FDM floor


def shell_body(side, plan, wall, split_z=None, lip=1.2, fillet=None):
    """A sculpted two-part shell in ONE call: profile_body(side, plan, fillet), hollowed to `wall`, split at split_z into (lower, upper) with a lip.

    lower, upper = cad.shell_body(SIDE, PLAN, 2.0, split_z=12, fillet=(6, 0))
    Every step on its R270 fallback ladder: the fillet steps down (or is
    left off, WARNING), the hollow uses the exact inset core and then the
    fitted core, a lip that cannot be built falls back to lip=0
    (WARNING), a plane giving an invalid half moves up to 3 mm (NOTE).
    split_z=None splits at mid height. Returns two valid single solids,
    their walls measured >= 0.8 mm, or raises ONE CadError that says
    which step failed and what to change (R270).
    """
    what = "shell_body"
    if not _num(wall) or wall <= 0:
        raise _err("shell_body: wall must be > 0 (mm)")
    t0 = time.time()
    step = "profile_body"
    try:
        body = profile_body(side, plan, fillet=fillet)
        step = "hollow"
        shell = hollow(body, wall, core=lambda t: profile_body(side, plan, fillet=fillet,
                                                               inset=t))
        mw = _gap(shell.Shells[1], shell.Shells[0]) if len(shell.Shells) == 2 else None
        if mw is not None and mw < SHELL_MIN_WALL:
            raise _err("the measured wall is %.2f mm, under the %.1f mm a print needs - "
                       "use wall >= %.1f or smoother outlines" % (
                           mw, SHELL_MIN_WALL, wall + SHELL_MIN_WALL - mw))
        step = "split"
        lower, upper = split(shell, "Z", at=split_z, lip=lip)
    except _k().CadError as exc:
        raise _err("shell_body: the %s step failed - %s" % (step, exc))
    for name, s in (("lower", lower), ("upper", upper)):
        if s.isNull() or not s.isValid() or len(s.Solids) != 1:
            raise _err("shell_body: the %s part is not one valid solid - move split_z "
                       "into the cavity" % name)
    print("shell_body: wall %s mm, lower %.0f mm3 + upper %.0f mm3 (%.1f s)" % (
        "?" if mw is None else "%.2f" % mw, lower.Volume, upper.Volume, time.time() - t0))
    return lower, upper


__all__ += ["shell_body"]   # R270 (the R230 card above is frozen by tests)


def _face_point(f):
    """A point ON face f (its parameter centre lies in a ring face's hole)."""
    u0, u1, v0, v1 = f.ParameterRange
    p = f.valueAt(0.5 * (u0 + u1), 0.5 * (v0 + v1))
    try:
        if f.isInside(p, 1e-6, True):
            return p
        pts, tris = f.tessellate(1.0)
        a, b, c = (pts[i] for i in tris[0])
        return (a + b + c) * (1.0 / 3.0)
    except Exception:                                   # noqa: BLE001
        return p


def _nudged(body, n, at, reach=0.3):
    """R250: the split coordinate 0.01 mm off the flat face perpendicular to
    n that lies within `reach` of `at`, on its open (cavity) side; None
    when there is no such face or `at` is already there."""
    best = None
    for f in body.Faces:
        if not _flat(f):
            continue
        try:
            nf = _normal(f)
        except Exception:                               # noqa: BLE001
            continue
        if abs(abs(nf.dot(n)) - 1) > 1e-6:
            continue
        p = _face_point(f)
        d = p.dot(n) - at
        if abs(d) > reach or (best is not None and abs(d) >= abs(best[0])):
            continue
        out = nf if not body.isInside(p + nf * 0.01, 1e-6, False) else nf * -1
        best = (d, p.dot(n) + 0.01 * (1.0 if out.dot(n) > 0 else -1.0))
    if best is None or abs(best[1] - at) < 1e-9:
        return None
    return best[1]


def _split_at(body, key, k, n, at, lip, clearance):
    """split() at one plane; raises CadError like split()."""
    bb = body.BoundBox
    big = bb.DiagonalLength + 10.0
    org = bb.Center - n * (bb.Center.dot(n) - at)

    def half(sign):
        base = org - App.Vector(big, big, big) + n * (big if sign > 0 else 0.0)
        size = [2 * big] * 3
        size[k] = big
        return Part.makeBox(size[0], size[1], size[2], base)
    _tr("split start")
    lower = upper = None
    if not lip:
        lower, upper = _split_plane(body, n, at, half)
        _tr("split plane")
    else:
        if lip < 0 or clearance < 0:
            raise _err("split: lip and clearance must be >= 0")
        lower, upper = _split_plane(body, n, at, half)
        _tr("split plane")
        # the section is lower's own flat top - no slice needed (0.45 s)
        cap = [f for f in lower.Faces if _flat(f) and abs(f.CenterOfMass.dot(n) - at) < 1e-6
               and abs(abs(_normal(f).dot(n)) - 1) < 1e-6]
        wires = [w for f in cap for w in f.Wires]
        if len(wires) < 2:
            raise _err("split: the section at %s=%g is solid - a lip needs a "
                       "hollow body (cad.hollow first) or lip=0" % (key, at))
        wires = [_refit(w) for w in wires]      # R230: 1 edge, not dozens
        outer = max(wires, key=lambda w: Part.Face(w).Area)
        inner = [w for w in wires if not w.isSame(outer)]
        wall = min(_gap(w, outer) for w in inner)
        # the lip's outer face sits half a wall in, but at least 0.9 mm +
        # clearance in: the upper's skin beside the groove must print
        # (>= 0.8 mm, ./check's FDM floor - MEASURED R230: half of a 2 mm
        # wall less 0.2 clearance left 0.72 mm, flagged)
        half_w = max(wall / 2.0, min(wall - 0.4, 0.9 + clearance))
        if wall - half_w < 0.3 or half_w - clearance < 0.5:
            raise _err("split: the wall at the split is %.2f mm - too thin for a "
                       "lip with %.2f mm clearance (needs >= %.1f). Use a thicker "
                       "wall or lip=0" % (wall, clearance, 1.3 + clearance))
        # The lip and the groove stay half a wall inside the outer skin at
        # the split AND at the lip's top (a wall sloping inward above the
        # split never shows them).
        top = upper.slice(n, float(at) + lip + clearance)
        _tr("top slice")
        outs = [Part.Face(outer)]
        if top:
            ot = _refit(max(top, key=lambda w: Part.Face(w).Area))
            f_top = Part.Face(ot)
            f_top.translate(n * -(lip + clearance))
            outs.append(f_top)
        lipf = groove = None
        for f in outs:
            lf = _offset2d(f, -half_w, "split lip")             # R270
            g = _offset2d(f, -(half_w - clearance), "split groove")
            if lipf is None:
                lipf, groove = lf, g
                continue
            lc, gc = _common2d(lipf, lf), _common2d(groove, g)
            if lc is None or gc is None:
                print("split NOTE: could not intersect the lip outline with the "
                      "wall above the split - the lip follows the split plane only")
                continue
            lipf, groove = lc, gc
        # two near-tangent outlines leave crumbs when intersected: keep the
        # big face, refuse only a real second piece (> 2 % of it)
        picked = []
        for shp in (lipf, groove):
            fs = sorted(shp.Faces, key=lambda f: -f.Area)
            if not fs or (len(fs) > 1 and fs[1].Area > 0.02 * fs[0].Area):
                raise _err("split: the lip outline at %s=%g falls apart in pieces "
                           "(the wall turns sharply there) - move `at` or use lip=0"
                           % (key, at))
            picked.append(fs[0])
        lipf, groove = picked
        _tr("lip/groove outlines")
        # The lip's inner side stands 1 mm INTO the cavity, not on the inner
        # wall (R230, MEASURED): a lip face ON the inner wall fused INVALID;
        # 0.05 mm off it, the lip came out 0.24 mm thin where the wall slopes
        # (./check flags it) and a 2D opening to drop that sliver took 28 s.
        # Standing proud of the wall it is >= 1 mm wide wherever it exists.
        ring = lipf
        for w in inner:
            ring = ring.cut(_offset2d(Part.Face(w), -1.0, "split lip"))
        _tr("ring")
        rf = ring.Faces
        if not rf or sum(f.Area for f in rf) < 0.1 * sum(f.Area for f in cap):
            raise _err("split: almost no room for a lip at %s=%g (the wall turns "
                       "sharply there) - move `at` or use lip=0" % (key, at))
        _tr("2d lip+groove")
        tools = []
        for f in rf:
            f = f.copy()
            f.translate(n * -0.3)
            tools.append(f.extrude(n * (lip + 0.3)))
        # MEASURED (R230) on the car shell: this fuse 1.2 s and the groove
        # cut 1.4 s; the 3D alternatives tried were slower (one common with
        # a lip prism 5.5 s, one stepped-sheet general split 10.8 s - and
        # that one damaged its input's tolerances)
        fused = _clean(lower.fuse(tools))      # no removeSplitter (see _clean)
        if fused.isNull() or not fused.isValid() or len(fused.Solids) != 1:
            raise _err("split: fusing the lip onto the lower part failed at %s=%g - "
                       "move `at` or use lip=0" % (key, at))
        lower = fused.Solids[0]
        _tr("lip fuse")
        gp = groove.copy()
        gp.translate(n * -0.5)
        upper = _clean(upper.cut(gp.extrude(n * (lip + clearance + 0.5))))
        _tr("groove cut")
    for name, s in (("lower", lower), ("upper", upper)):
        if s.isNull() or not s.isValid() or len(s.Solids) != 1:
            raise _err("split: the %s part is %s at %s=%g - move `at` so the "
                       "plane cuts the body into one lower and one upper piece"
                       % (name, "invalid" if s.isNull() or not s.isValid()
                          else "%d separate solids" % len(s.Solids), key, at))
    return lower.Solids[0], upper.Solids[0]
