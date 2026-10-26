"""atech_detail - finish and detail helpers for model.py (R230+).

    import atech_cad as cad          # atech_cad re-exports everything here
    body = cad.soften(body, 1.5)     # round every edge it can, never a wreck

The bodies come from atech_form; this file puts the product finish on them:
rounded edges, panel lines, grilles, wheels, lettering, colours, screws and
bosses, button caps, lenses, knurls and feet. Same rules as atech_cad:

  * every helper CHECKS its own result (valid, the solid count it expects,
    material really removed or added) and raises cad.CadError with the fix
    instead of returning a broken or invalid shape. soften() is the one
    exception: like fillet_safe it always returns a valid shape (the input
    when nothing could be rounded) and keeps the reason in cad.last_reason().
  * `normal` / `axis` arguments are explicit; nothing is guessed from a bbox.
  * depths are MEASURED with rays along the drilling direction (R230): a
    grille on a curved shell starts each hole just outside the surface it
    meets and stops at the first wall, not the wall behind it.

The measured findings behind each helper are in the R230-R245 comments. All
timings are MEASURED on FreeCAD 1.1.3 (macOS arm64 bundle).
"""
import math
import os
import time

import FreeCAD as App
import Part

# Only these four come from atech_cad at import time: atech_cad does
# `from atech_detail import *` at its END, when they already exist (R230).
# Everything else of atech_cad's is reached through _c() at call time.
from atech_cad import CadError, V, measure, fillet_safe  # noqa: F401

__all__ = [
    "soften", "new_edges", "groove_ring", "groove_outline", "grille",
    "speaker_grille", "wheel", "text", "MATERIALS", "color", "transparency",
    "screw", "screw_boss", "screw_through", "button_cap", "lens",
    "opening_for", "knurl", "foot", "inlay",
]

BACK = 0.5          # cutters start this far OUTSIDE the surface they enter
RIM_GAP = 0.1       # wheel(): the rim's radius under the tyre bead (R238)
ON_SURFACE = 1.5    # `center` / `at` must be this close to the surface the
                    # rays meet: a reversed normal drills the far face (R236)
TOL = 1e-6


def _c():
    """The atech_cad module (imported lazily: it imports this file)."""
    import atech_cad
    return atech_cad


def _dir(d, what="axis"):
    return _c()._dir(d, what)


def _num(x, what, lo=None, strict=True):
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise CadError("%s must be a number, got %r" % (what, x))
    if lo is not None and (v <= lo if strict else v < lo):
        raise CadError("%s must be %s %g, got %g" % (what, ">" if strict else ">=", lo, v))
    return v


def _valid(shape, what, solids=None):
    return _c()._check(shape, what, solids)


def _single(shape):
    return shape.Solids[0] if len(shape.Solids) == 1 else shape


def _frame(n, up=None):
    """(u, v, n): an orthonormal frame with n the given direction; v is `up`
    made perpendicular to n (default +Z, or +Y when n is vertical), u = v x n
    (so for a viewer looking back along -n, u is to the right)."""
    n = _dir(n, "normal")
    if up is None:
        up = V((0, 1, 0)) if abs(n.z) > 0.99 else V((0, 0, 1))
    else:
        up = _dir(up, "up")
        if abs(up.dot(n)) > 0.99:
            up = V((0, 1, 0)) if abs(n.z) > 0.99 else V((0, 0, 1))
    v = up - n * up.dot(n)
    v.normalize()
    u = v.cross(n)
    u.normalize()
    return u, v, n


def _to_world(shape, origin, u, v, n):
    """A copy of a shape built in local XYZ, placed with X->u, Y->v, Z->n at origin."""
    m = App.Matrix(u.x, v.x, n.x, 0, u.y, v.y, n.y, 0, u.z, v.z, n.z, 0, 0, 0, 0, 1)
    out = shape.copy()
    out.Placement = App.Placement(V(origin), App.Rotation(m)).multiply(out.Placement)
    return out


# ------------------------------------------------------------------- rays
def _rays(shape, origins, d, length):
    """Material runs along unit `d` from each origin: one list of sorted
    (t_in, t_out) per origin, t in mm from the origin. ONE boolean of the
    shape with all the segments (R231, MEASURED: 100 segments through a
    hollow box 0.009 s), each resulting edge mapped back to its segment by
    its position across `d`."""
    if not origins:
        return []
    a = d.cross(V((1, 0, 0)))
    if a.Length < 1e-6:
        a = d.cross(V((0, 1, 0)))
    a.normalize()
    b = d.cross(a)
    snapped, keys = [], {}
    for i, o in enumerate(origins):
        o = V(o)
        ca, cb = o.dot(a), o.dot(b)
        o = o + a * (round(ca, 3) - ca) + b * (round(cb, 3) - cb)
        snapped.append(o)
        keys.setdefault((round(o.dot(a), 3), round(o.dot(b), 3)), []).append(i)
    segs = [Part.LineSegment(o, o + d * length).toShape() for o in snapped]
    runs = [[] for _ in origins]
    try:
        edges = shape.common(segs).Edges
    except Exception:                                   # noqa: BLE001
        edges = []
        for s in segs:
            try:
                edges.extend(shape.common(s).Edges)
            except Exception:                           # noqa: BLE001
                pass
    for e in edges:
        if e.Length <= 1e-6:
            continue
        p = e.valueAt(0.5 * (e.FirstParameter + e.LastParameter))
        for i in keys.get((round(p.dot(a), 3), round(p.dot(b), 3)), ()):
            ts = sorted((x.Point - snapped[i]).dot(d) for x in e.Vertexes)
            runs[i].append((ts[0], ts[-1]))
    out = []
    for rl in runs:
        rl.sort()
        merged = []
        for lo, hi in rl:
            if merged and lo <= merged[-1][1] + 1e-6:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        out.append(merged)
    return out


def _span(shape):
    return shape.BoundBox.DiagonalLength + 2.0


# ------------------------------------------------------------- soften
def _mid(e):
    return e.valueAt(0.5 * (e.FirstParameter + e.LastParameter))


def _face_normal(f, p):
    u, v = f.Surface.parameter(p)
    return f.normalAt(u, v)


def _is_smooth(shape, e, deg=2.0):
    """True for a seam or a tangent-continuous edge (nothing to round: a
    fillet on it fails - every fillet's own boundary edge is one, R232)."""
    try:
        faces = shape.ancestorsOfType(e, Part.Face)
    except Exception:                                   # noqa: BLE001
        return False
    uniq = []
    for f in faces:
        if not any(f.isSame(g) for g in uniq):
            uniq.append(f)
    if len(uniq) < 2:
        return True                                     # seam / free edge
    try:
        p = _mid(e)
        n1, n2 = _face_normal(uniq[0], p), _face_normal(uniq[1], p)
        return n1.dot(n2) > math.cos(math.radians(deg))
    except Exception:                                   # noqa: BLE001
        return False


def _fillet_ok(before, res, what):
    """None when `res` is a believable fillet of `before`, else why not.
    MEASURED (r2 gap 1): OCCT returns an INVALID shape without raising
    (window edges r=1.5 on a 2 mm wall), so each rung checks validity, the
    solid count, the volume change and that the part did not grow."""
    if res is None or res.isNull():
        return "%s: empty result" % what
    if not res.isValid():
        return "%s: result was INVALID" % what
    if len(res.Solids) != len(before.Solids):
        return "%s: solid count changed %d -> %d" % (
            what, len(before.Solids), len(res.Solids))
    v0, v1 = before.Volume, res.Volume
    if v1 <= TOL or abs(v1 - v0) > 0.3 * v0:
        return "%s: volume went %.1f -> %.1f mm3, not a fillet" % (what, v0, v1)
    # the plain BoundBox first (cheap); only when it says "grew" are both
    # measured tight - optimalBoundingBox costs 0.4 s on a softened rim
    # (MEASURED R232), and a sphere's plain box is loose
    if _grew(before.BoundBox, res.BoundBox) and _grew(
            _tight_of(before), _new_faces_box(res, before)):
        return "%s: the result grew outside the part's box" % what
    return None


_SLOWEST = [0.0]        # the slowest makeFillet of the current soften()


_TIGHT = {}


def _tight_of(shape):
    """optimalBoundingBox, cached for the shape soften() keeps retrying."""
    k = id(shape)
    hit = _TIGHT.get(k)
    if hit is None or hit[0] is not shape:
        if len(_TIGHT) > 8:
            _TIGHT.clear()
        hit = _TIGHT[k] = (shape, _c()._tight_bbox(shape))
    return hit[1]


def _new_faces_box(res, before):
    """Tight box of the faces `res` has that `before` had not (the fillet
    faces and the faces they trimmed) - a few faces, not the whole part."""
    old = {}
    for f in before.Faces:
        old.setdefault(f.hashCode(), []).append(f)
    new = [f for f in res.Faces if not any(f.isSame(o) for o in old.get(f.hashCode(), ()))]
    if not new:
        return _tight_of(before)
    return _c()._tight_bbox(Part.makeCompound(new))


def _grew(b0, b1):
    tol = 0.02 + 1e-4 * b0.DiagonalLength
    return (b1.XMin < b0.XMin - tol or b1.YMin < b0.YMin - tol or b1.ZMin < b0.ZMin - tol
            or b1.XMax > b0.XMax + tol or b1.YMax > b0.YMax + tol
            or b1.ZMax > b0.ZMax + tol)


def _try_fillet(cur, es, rr):
    what = "fillet r=%g on %d edges" % (rr, len(es))
    t = time.time()
    try:
        return _try_fillet_timed(cur, es, rr, what)
    finally:
        _SLOWEST[0] = max(_SLOWEST[0], time.time() - t)


def _try_fillet_timed(cur, es, rr, what):
    # R270: run in a forked child, killed after atech_form.GUARD_S - one
    # makeFillet on the round-1 toy car ran 126 s inside soften (MEASURED)
    # and another segfaulted freecadcmd
    res, why = _form()._guarded(lambda: cur.makeFillet(rr, es))
    if res is None:
        return None, "%s failed: %s" % (what, " ".join(str(why).split())[:120])
    why = _fillet_ok(cur, res, what)
    return (None, why) if why else (_single(res), None)


class _Desc(object):
    """A target edge remembered by geometry, so it can be found again after
    other edges were rounded (a fillet replaces every edge it touches)."""
    __slots__ = ("edge", "mid", "length")

    def __init__(self, e):
        self.edge = e           # the input's own edge (a copy would not
                                # "belong to the shape" in makeFillet)
        self.mid = _mid(e)
        self.length = e.Length


def _find(cur_edges, boxes, desc, tol=1e-4):
    p = desc.mid
    vp = None
    for e, bb in zip(cur_edges, boxes):
        if not (bb[0] - tol <= p.x <= bb[3] + tol and bb[1] - tol <= p.y <= bb[4] + tol
                and bb[2] - tol <= p.z <= bb[5] + tol):
            continue
        try:
            vp = vp or Part.Vertex(p)
            if e.distToShape(vp)[0] > tol:
                continue
            if desc.edge.distToShape(Part.Vertex(_mid(e)))[0] > tol:
                continue
            return e
        except Exception:                               # noqa: BLE001
            continue
    return None


def _boxes(edges):
    out = []
    for e in edges:
        b = e.BoundBox
        out.append((b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax))
    return out


def _chains(edges):
    """Tangent-continuous chains of edges (OCCT rounds a chain as one, so a
    chain is never split between attempts), longest chain first."""
    parent = list(range(len(edges)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    ends = {}
    for i, e in enumerate(edges):
        try:
            for par, sign in ((e.FirstParameter, 1.0), (e.LastParameter, -1.0)):
                p = e.valueAt(par)
                t = e.tangentAt(par) * sign
                key = (round(p.x, 3), round(p.y, 3), round(p.z, 3))
                ends.setdefault(key, []).append((i, t))
        except Exception:                               # noqa: BLE001
            continue
    for lst in ends.values():
        for k in range(len(lst)):
            for m in range(k + 1, len(lst)):
                (i, ti), (j, tj) = lst[k], lst[m]
                if ti.Length > 1e-9 and tj.Length > 1e-9 and \
                        ti.dot(tj) / (ti.Length * tj.Length) < -math.cos(math.radians(10)):
                    parent[root(i)] = root(j)
    groups = {}
    for i in range(len(edges)):
        groups.setdefault(root(i), []).append(i)
    out = sorted(groups.values(), key=lambda g: -sum(edges[i].Length for i in g))
    return out


def soften(shape, r, edges=None, min_r=0.3, ladder=(1, 0.6, 0.35), budget_s=8):
    """Round edges with radius r (None = every sharp edge) with a fallback ladder and partial success; returns a valid shape, the reason in cad.last_reason().

    Order of attempts (R232, MEASURED r2 gap 1): all edges at r, then at
    each ladder step (r * 0.6, r * 0.35, never below min_r); then the edges
    still sharp are split in halves again and again (tangent chains kept
    together, longest first) and each part tried down the same ladder, so
    one edge that cannot be rounded no longer blocks the other 68. Seam and
    tangent edges (a fillet's own boundary) are skipped: rounding them is
    what makes "fillet every edge" fail on a filleted body.

    Prints "soften: N/M edges rounded ...". The result is never invalid:
    when nothing could be rounded it is the input, unchanged. budget_s caps
    the search time (one OCCT call cannot be interrupted).

    Order matters more than radius: soften the outer body FIRST, then cut
    the features, then soften only the edges the cuts made:
        body = cad.soften(body, 4)
        cut = cad.cut(body, arches)
        body = cad.soften(cut, 1, cad.new_edges(cut, body))
    """
    t0 = time.time()
    cad = _c()
    r, edges = cad._edge_args("soften", r, edges)
    min_r = _num(min_r, "soften: min_r", 0.0)
    _valid(shape, "soften: input")
    if not shape.Solids:
        raise CadError("soften: the input has no solid")
    targets = cad._pick_edges(shape, edges)
    cand, smooth = [], 0
    for e in targets:
        if e.isNull() or getattr(e, "Degenerated", False) or e.Length < 1e-4:
            continue
        if _is_smooth(shape, e):
            smooth += 1
            continue
        cand.append(e)
    radii = []
    for f in ladder:
        rr = round(r * float(f), 4)
        if rr >= min_r - 1e-9 and rr not in radii and rr > 0:
            radii.append(rr)
    if not radii:
        radii = [r]
    radii.sort(reverse=True)

    def done(cur, msg, reason):
        cad._LAST_REASON[0] = reason
        print("soften: %s (%.2f s)" % (msg, time.time() - t0))
        return _single(cur)

    if not cand:
        return done(shape, "no sharp edge to round (%d smooth or seam edges skipped)"
                    % smooth, "soften: no sharp edges selected")
    M = len(cand)
    last = None
    _SLOWEST[0] = 0.0

    def out_of_time():
        # the next attempt may take as long as the slowest one so far
        return time.time() - t0 + _SLOWEST[0] > budget_s
    for rr in radii:
        res, last = _try_fillet(shape, cand, rr)
        if res is not None:
            return done(res, "%d/%d edges rounded at r=%g" % (M, M, rr), None)
        if out_of_time():
            break
    # partial: bisect the chains, each part down the ladder
    descs = [_Desc(e) for e in cand]
    chains = _chains(cand)
    cur = shape
    per_r = {}
    pending = [[descs[i] for i in ch] for ch in chains]
    for rr in radii:
        if not pending or out_of_time():
            break
        stack = [pending]
        failed = []
        while stack:
            if out_of_time():
                for gs in stack:
                    failed.extend(gs)
                break
            gs = stack.pop()
            flat = [d for ch in gs for d in ch]
            if cur is shape:
                es = [d.edge for d in flat]
                found = list(flat)
            else:
                ce = cur.Edges
                bx = _boxes(ce)
                es, found = [], []
                for d in flat:
                    e = _find(ce, bx, d)
                    if e is not None:          # else: swallowed by a neighbour's fillet
                        es.append(e)
                        found.append(d)
            if not es:
                continue
            res, why = _try_fillet(cur, es, rr)
            last = why or last
            if res is not None:
                cur = res
                per_r[rr] = per_r.get(rr, 0) + len(es)
                continue
            if len(gs) == 1:
                failed.append(gs[0])
                continue
            half = len(gs) // 2
            stack.append(gs[half:])
            stack.append(gs[:half])
        pending = failed
    n_done = sum(per_r.values())
    left = M - n_done
    detail = ", ".join("%d at r=%g" % (per_r[k], k) for k in sorted(per_r, reverse=True))
    if n_done == 0:
        return done(shape, "0/%d edges rounded - kept unchanged (%s)" % (M, last),
                    "soften: no edge could be rounded at r=%s: %s" % (
                        "/".join("%g" % x for x in radii), last))
    reason = None
    if left:
        reason = ("soften: %d of %d edges stayed sharp (smallest radius tried %g; "
                  "last failure: %s). Round them before the cut that made them, "
                  "or pass those edges with a smaller r." % (left, M, radii[-1], last))
    return done(cur, "%d/%d edges rounded (%s)%s" % (
        n_done, M, detail, ", %d left sharp" % left if left else ""), reason)


def new_edges(after, before):
    """The edges of `after` that `before` did not have: the edges a cut or fuse created, ready for cad.soften(after, r, cad.new_edges(after, before)).

    An old edge a cut only shortened still counts as old (its middle lies
    on the old edge). MEASURED (R233): boolean results keep untouched edges
    as the same sub-shapes, so most are recognised without any geometry."""
    old = {}
    for e in before.Edges:
        old.setdefault(e.hashCode(), []).append(e)
    bx = _boxes(before.Edges)
    bedges = before.Edges
    out = []
    for e in after.Edges:
        if getattr(e, "Degenerated", False):
            continue
        if any(e.isSame(o) for o in old.get(e.hashCode(), ())):
            continue
        p = _mid(e)
        vp = Part.Vertex(p)
        hit = False
        for oe, b in zip(bedges, bx):
            if b[0] - 1e-4 <= p.x <= b[3] + 1e-4 and b[1] - 1e-4 <= p.y <= b[4] + 1e-4 \
                    and b[2] - 1e-4 <= p.z <= b[5] + 1e-4:
                try:
                    if oe.distToShape(vp)[0] < 1e-4:
                        hit = True
                        break
                except Exception:                       # noqa: BLE001
                    continue
        if not hit:
            out.append(e)
    return out


# ------------------------------------------------------------ panel lines
def _loop_face(w):
    try:
        if not w.isClosed():
            return None
        return Part.Face(w)
    except Exception:                                   # noqa: BLE001
        return None


def _form():
    """atech_form (lazy, like _c(): its offsets and refit are shared)."""
    import atech_form
    return atech_form


def _offset_loop(w, d):
    """The closed planar wire `w` offset by d (d < 0 shrinks it), as a VALID
    Face, or None. R250 (MEASURED): Part.Face(wire.makeOffset2D(..)) of a
    slice through a spline body came back INVALID (29 OffsetCurve edges,
    isValid() False) on the toy-car body, and the groove cut with it
    removed nothing. Tried in order: the face's own offset, the same on the
    wire refit as one BSpline per smooth run (atech_form._refit), then a
    0.25 mm polygon of it."""
    form = _form()
    cands = []
    for mk in (lambda: Part.Face(w), lambda: Part.Face(form._refit(w)),
               lambda: Part.Face(Part.makePolygon(
                   w.discretize(Distance=0.25)[:-1] + [w.discretize(Distance=0.25)[0]]))):
        try:
            f0 = mk()
            if f0.isValid() and f0.Area > TOL:
                cands.append(f0)
        except Exception:                               # noqa: BLE001
            continue
    for f0 in cands:
        try:
            f = form._offset_face(f0, d, "offset")
        except Exception:                               # noqa: BLE001
            continue
        if f.isValid() and ((d < 0 and f.Area < f0.Area - TOL) or (d > 0 and f.Area > f0.Area + TOL)):
            return f
    return None


def _inset(w, d):
    """A closed planar wire offset INWARD by d as a valid Face, or None
    (MEASURED R234: one car section's -d offset went outward; R250: and
    came back invalid - see _offset_loop)."""
    return _offset_loop(w, -abs(d))


def _outset(w, d):
    return _offset_loop(w, abs(d))


def _clip(shape, region):
    """shape's part inside `region` (one boolean with a small solid), or the
    shape itself when that fails. R250 (MEASURED, toy-car shell with
    fillet faces of up to 886 poles): rays 2.2 s and isInside 0.16 s per
    point on the whole shell; on its clip 0.12 s and 0.01 s."""
    if region is None:
        return shape
    try:
        loc = shape.common(region)
        if not loc.isNull() and loc.isValid() and loc.Solids:
            return loc
    except Exception:                                   # noqa: BLE001
        pass
    return shape


def _cut_probed(shape, tools, probes, what, region=None):
    """shape minus tools, PROVEN by points: `probes` are material before the
    cut and must be air after it (classified on the clip to `region`, which
    must hold every tool and probe). R250 (MEASURED on the toy-car body): the
    volume test (cad.cut's "removed nothing") is wrong on big spline
    bodies - Shape.Volume of the grooved car came out 0.05 .. 34 mm3 under
    the input for the same 38.4 mm3 groove, run to run, while rays showed
    the groove cut 0.5 deep. Raises when no probe turned to air."""
    res = shape.cut(tools if len(tools) > 1 else tools[0])
    _valid(res, what, solids=len(shape.Solids))
    before = _clip(shape, region)
    live = [p for p in probes if before.isInside(p, 1e-6, False)]
    if not live:
        return res
    after = _clip(res, region)
    if not any(not after.isInside(p, 1e-6, True) for p in live):
        raise CadError("%s: the cut left the surface untouched at all %d probe points (an "
                       "OCCT boolean failure on this surface) - try a slightly different "
                       "`at`/outline, or w/depth" % (what, len(live)))
    return res


def groove_ring(shape, axis, at, w=0.6, depth=0.5):
    """Cut a panel-line groove w wide and depth deep round the body where the plane normal to `axis` at `at` crosses it (a belt line, a split line).

    at: a coordinate along `axis` (a number) or a point on the plane. The
    groove follows the outline of that section, offset inward by `depth` in
    the section plane (R234, MEASURED: car body 0.22 s, rounded box 0.01 s).
    A hollow body's wall is measured in the section: a depth that would
    break through to the inside raises and says the wall thickness. Works
    on spline bodies, hollow ones and split halves (R250)."""
    a = _dir(axis)
    w = _num(w, "groove_ring: w", 0)
    depth = _num(depth, "groove_ring: depth", 0)
    _valid(shape, "groove_ring: input")
    if isinstance(at, (int, float)):
        d0 = float(at)
    else:
        d0 = V(at).dot(a)
    try:
        wires = shape.slice(a, d0)
    except Exception as exc:                            # noqa: BLE001
        raise CadError("groove_ring: the plane at %g along %s does not cut the body (%s)"
                       % (d0, tuple(round(c, 3) for c in a), exc))
    faces = [(f, wr) for wr in wires for f in [_loop_face(wr)] if f is not None]
    if not faces:
        raise CadError("groove_ring: the plane at %g along %s misses the body - put "
                       "`at` inside its extent" % (d0, tuple(round(c, 3) for c in a)))
    # outer loops = loops not inside another loop; inner loops = cavities
    outer, inner = [], []
    for i, (f, wr) in enumerate(faces):
        inside = False
        for j, (g, _w) in enumerate(faces):
            if i != j and g.Area > f.Area and g.isInside(wr.Vertexes[0].Point, 1e-6, True):
                inside = True
                break
        (inner if inside else outer).append((f, wr))
    tools, probes = [], []
    for f, wr in outer:
        core = _inset(wr, depth)
        if core is None:
            raise CadError("groove_ring: the section is too small for a %g mm deep "
                           "groove (its inward offset vanished)" % depth)
        big = _outset(wr, 2.0) or f
        for g, _wr in inner:
            if f.isInside(_wr.Vertexes[0].Point, 1e-6, True):
                lost = g.Area - core.common(g).Area
                if lost > 1e-3:
                    wall = min(g.distToShape(wr)[0], 99)
                    raise CadError(
                        "groove_ring: a %g mm deep groove breaks through the %.2f mm "
                        "wall at this section. Use depth <= %.2f (wall - 0.5)."
                        % (depth, wall, max(0.1, wall - 0.5)))
        ring = big.cut(core)
        prism = ring.extrude(a * w)
        prism.translate(a * (-w / 2.0))
        tools.append(prism)
        # probes: half way between the outline and the groove's floor
        cw = core.OuterWire
        for q in wr.discretize(Number=13)[:-1]:
            try:
                qq = cw.distToShape(Part.Vertex(q))[1][0][0]
                probes.append(q + (qq - q) * 0.5)
            except Exception:                           # noqa: BLE001
                pass
    # probes on the whole body: 13 points 0.02 s each here, where a clip
    # to a slab round the plane cost 0.4-0.6 s per shape (MEASURED R250)
    return _cut_probed(shape, tools, probes, "groove_ring")


def _outline_wire(outline_pts, u, v, n):
    """The outline as a closed wire in the plane through the origin normal
    to n: 2D points are (u, v) coordinates, 3D points and wires are
    projected along n."""
    if isinstance(outline_pts, Part.Shape):
        if not outline_pts.Wires:
            raise CadError("groove_outline: the outline shape has no wire")
        w = outline_pts.Wires[0].copy()
        if not w.isClosed():
            raise CadError("groove_outline: the outline must be closed")
        k = w.Vertexes[0].Point.dot(n)
        w.translate(n * -k)
        return w
    pts = []
    for p in outline_pts:
        p = list(p)
        if len(p) == 2:
            pts.append(u * float(p[0]) + v * float(p[1]))
        else:
            pp = V(p)
            pts.append(pp - n * pp.dot(n))
    if len(pts) < 3:
        raise CadError("groove_outline: need >= 3 outline points")
    if (pts[0] - pts[-1]).Length > 1e-9:
        pts.append(pts[0])
    return Part.makePolygon(pts)


_VIEW_UV = {"x": ((0, 1, 0), (0, 0, 1)), "y": ((1, 0, 0), (0, 0, 1)),
            "z": ((1, 0, 0), (0, 1, 0))}


def groove_outline(shape, outline_pts, view='+Y', w=0.6, depth=0.5, both_sides=True):
    """Cut a panel line (a door, hatch or lid seam) w wide and depth deep along a closed outline drawn as seen from `view`, following the curved surface.

    outline_pts: 2D points in the view's drawing plane - view X or Y: (x, z)
    or (y, z) world coordinates; view Z: (x, y) - or 3D points / a closed
    Part.Wire (cad.spline_wire(...)) whose `view` coordinate is ignored.
    The band round the outline is extruded along the view and kept only
    within `depth` of the surface facing the viewer (R235: the body and a
    copy moved `depth` inward along the view, so no 3D offset - MEASURED, a
    3D offset core failed after 6.4 s). both_sides=True also cuts the same
    outline on the opposite side (a car's left and right doors). Raises when
    the depth would break through the wall it is measured on."""
    _valid(shape, "groove_outline: input")
    w = _num(w, "groove_outline: w", 0)
    depth = _num(depth, "groove_outline: depth", 0)
    n = _dir(view, "view")
    k = max(range(3), key=lambda i: abs((n.x, n.y, n.z)[i]))
    if abs(abs((n.x, n.y, n.z)[k]) - 1) < 1e-9:
        ua, va = _VIEW_UV["xyz"[k]]
        u, v = V(ua), V(va)
    else:
        u, v, n = _frame(n)
    wire = _outline_wire(outline_pts, u, v, n)
    try:
        band = _outset(wire, w / 2.0).cut(_inset(wire, w / 2.0))
    except Exception:                                   # noqa: BLE001
        raise CadError("groove_outline: could not offset the outline by w/2 = %g - "
                       "an outline with a corner tighter than that, or one that "
                       "crosses itself" % (w / 2.0))
    bb = shape.BoundBox
    L = bb.DiagonalLength + 4.0
    c = bb.Center.dot(n)
    sides = [n, n * -1] if both_sides else [n]
    # R250: ONE band prism through the whole body and ONE common with it
    # (the slow boolean on a spline shell, ~1.5 s on the toy car), split
    # per side at the body's middle (small booleans); the halves each keep
    # only the layer `depth` under the surface facing their viewer.
    prism = band.extrude(n * (2 * L))
    prism.translate(n * (c - L))
    region = None
    fat = _outset(wire, w / 2.0 + 1.0)
    if fat is not None:
        region = fat.extrude(n * (2 * L))
        region.translate(n * (c - L))
    loc = _clip(shape, region)
    A_all = prism.common(loc)
    tools, probes = [], []
    for d in sides:
        lo = c if d.dot(n) > 0 else c - L
        half = band.extrude(n * L)
        half.translate(n * lo)
        A = A_all.common(half)
        if A.Volume <= TOL:
            continue
        deep = A.copy()
        deep.translate(d * -depth)
        tool = A.cut(deep)
        if tool.Volume <= TOL:
            continue
        probes += _wall_check(loc, wire, d, depth, n, "groove_outline")
        tools.append(tool)
    if not tools:
        raise CadError("groove_outline: the outline misses the body as seen from %s - "
                       "check the points are in that view's (horizontal, vertical) "
                       "world coordinates" % view)
    # R250 (MEASURED, view='-Y' on the toy-car shell): the cut was right
    # (rays: 0.5 mm deeper) but cad.cut's volume test said "removed
    # nothing" - the result is proven with probe points instead
    return _cut_probed(shape, tools, probes, "groove_outline",
                       region=region if loc is not shape else None)


def _wall_check(shape, wire, d, depth, n, what):
    """Raise when `depth` would break through the first wall seen along -d
    at sampled points of the outline (R235); returns probe points half the
    depth under the surface there (R250: _cut_probed proves the cut)."""
    pts = []
    es = wire.Edges
    for e in es[:: max(1, len(es) // 8)]:
        pts.append(_mid(e))
    bb = shape.BoundBox
    L = bb.DiagonalLength + 4.0
    c = bb.Center
    origins = [p - n * p.dot(n) + n * c.dot(n) + d * (L / 2.0) for p in pts]
    walls, probes = [], []
    for o, runs in zip(origins, _rays(shape, origins, d * -1, L)):
        if runs:
            walls.append(runs[0][1] - runs[0][0])
            probes.append(o - d * (runs[0][0] + 0.5 * min(depth, runs[0][1] - runs[0][0])))
    if walls:
        wmin = min(walls)
        if depth > wmin - 0.4:
            raise CadError("%s: a %g mm deep groove breaks (nearly) through the %.2f mm "
                           "wall. Use depth <= %.2f." % (what, depth, wmin,
                                                         max(0.1, wmin - 0.5)))
    return probes


# ---------------------------------------------------------------- grilles
def _hex_face(af):
    R = af / math.sqrt(3.0)
    pts = [V((R * math.cos(math.radians(90 + 60 * k)), R * math.sin(math.radians(90 + 60 * k)), 0))
           for k in range(6)]
    return Part.Face(Part.makePolygon(pts + [pts[0]]))


def _slot_face(width, length):
    """Obround in local XY, long along Y, centred at the origin."""
    if length <= width + 1e-6:
        return Part.Face(Part.Wire(Part.makeCircle(width / 2.0)))
    r = width / 2.0
    hl = length / 2.0 - r
    e = [Part.LineSegment(V((r, -hl, 0)), V((r, hl, 0))).toShape(),
         Part.ArcOfCircle(V((r, hl, 0)), V((0, hl + r, 0)), V((-r, hl, 0))).toShape(),
         Part.LineSegment(V((-r, hl, 0)), V((-r, -hl, 0))).toShape(),
         Part.ArcOfCircle(V((-r, -hl, 0)), V((0, -hl - r, 0)), V((r, -hl, 0))).toShape()]
    return Part.Face(Part.Wire(e))


def _area_fit(size):
    """('rect', w, h) or ('round', d)."""
    if isinstance(size, (int, float)):
        return ("round", float(size))
    s = list(size)
    if len(s) == 1:
        return ("round", float(s[0]))
    return ("rect", float(s[0]), float(s[1]))


def _layout(kind, area, hole, pitch, margin):
    """[(a, b, face_local, samples)] hole footprints in the grille plane."""
    out = []
    if area[0] == "rect":
        hw, hh = area[1] / 2.0 - margin, area[2] / 2.0 - margin

        def fits(a, b, ra, rb):
            return abs(a) + ra <= hw + 1e-9 and abs(b) + rb <= hh + 1e-9
        ext = max(hw, hh)
    else:
        R = area[1] / 2.0 - margin

        def fits(a, b, ra, rb):
            return math.hypot(a, b) + max(ra, rb) <= R + 1e-9
        ext = R
    if ext <= 0:
        raise CadError("grille: the margin %g leaves no area" % margin)
    if kind in ("hex", "round"):
        face = _hex_face(hole) if kind == "hex" else Part.Face(Part.Wire(Part.makeCircle(hole / 2.0)))
        rad = hole / math.sqrt(3.0) if kind == "hex" else hole / 2.0
        dy = pitch * math.sqrt(3.0) / 2.0
        nj = int(ext / dy) + 2
        ni = int(ext / pitch) + 2
        for j in range(-nj, nj + 1):
            off = pitch / 2.0 if j % 2 else 0.0
            for i in range(-ni, ni + 1):
                a, b = i * pitch + off, j * dy
                if fits(a, b, rad if kind == "round" else hole / 2.0, rad):
                    out.append((a, b, face, rad))
    elif kind == "slot":
        r = hole / 2.0
        ni = int(ext / pitch) + 2
        for i in range(-ni, ni + 1):
            a = i * pitch
            if area[0] == "rect":
                if abs(a) + r > hw + 1e-9:
                    continue
                half = hh
            else:
                if abs(a) + r > R:
                    continue
                half = math.sqrt(max(0.0, (R - 0.0) ** 2 - (abs(a) + r) ** 2))
            length = 2.0 * half
            if length < 2.0 * hole:
                continue
            out.append((a, 0.0, _slot_face(hole, length), (r, half)))
    elif kind == "radial":
        rad = hole / 2.0
        face = Part.Face(Part.Wire(Part.makeCircle(rad)))
        if fits(0, 0, rad, rad):
            out.append((0.0, 0.0, face, rad))
        k = 1
        while k * pitch - rad <= ext:
            rr = k * pitch
            m = max(6, int(round(2 * math.pi * rr / pitch)))
            for i in range(m):
                t = 2 * math.pi * i / m + (math.pi / m if k % 2 else 0.0)
                a, b = rr * math.cos(t), rr * math.sin(t)
                if fits(a, b, rad, rad):
                    out.append((a, b, face, rad))
            k += 1
    else:
        raise CadError("grille: kind must be 'hex', 'slot', 'round' or 'radial', got %r" % kind)
    return out


_FOOT_AREA = [[]]      # footprint areas of the last _drill_pattern's holes


def _drill_pattern(shape, center, normal, holes, through, what):
    """Cut every footprint along -normal, each one measured with rays at its
    centre and rim: from BACK outside the surface it meets to the first
    wall's exit (through='wall'), every wall (True) or a blind depth."""
    c0 = V(center)
    u, v, n = _frame(normal)
    d = n * -1
    ext = max([math.hypot(a, b) + (s if isinstance(s, float) else max(s)) for a, b, _f, s in holes] + [1.0])
    H = ext + 3.0
    L = _span(shape) + H + (V(center) - shape.BoundBox.Center).Length
    origins, owners = [], []
    for k, (a, b, _f, s) in enumerate(holes):
        base = c0 + u * a + v * b + n * H
        if isinstance(s, tuple):            # slot: along its length
            ra, half = s
            pts = [(0, 0), (0, half - ra), (0, -(half - ra)), (ra * 0.9, 0), (-ra * 0.9, 0),
                   (0, 0.5 * (half - ra)), (0, -0.5 * (half - ra))]
        else:
            pts = [(0, 0)] + [(0.9 * s * math.cos(t), 0.9 * s * math.sin(t))
                              for t in (0, math.pi / 2, math.pi, 1.5 * math.pi)]
        for pa, pb in pts:
            origins.append(base + u * pa + v * pb)
            owners.append(k)
    runs = _rays(shape, origins + [c0 + n * H], d, L)
    centre = [r for r in runs.pop() if r[1] > 1e-6]
    if centre and abs(H - centre[0][0]) > ON_SURFACE:
        raise CadError("%s: `center` is %.2f mm from the surface the holes would enter "
                       "along -normal - put `center` ON the surface and point `normal` OUT "
                       "of it (toward the viewer)" % (what, abs(H - centre[0][0])))
    per = {}
    for k, rl in zip(owners, runs):
        per.setdefault(k, []).append(rl)
    tools, skipped, buried = [], 0, 0
    _FOOT_AREA[0] = []
    for k, (a, b, face, s) in enumerate(holes):
        lines = [rl for rl in per.get(k, []) if rl]
        if not lines or len(lines) < len(per.get(k, [])):
            skipped += 1                    # (part of) the hole is off the part
            continue
        if any(rl[0][0] < 1e-6 for rl in lines):
            buried += 1
            continue
        t_in = min(rl[0][0] for rl in lines)
        if through == "wall":
            t_out = max(rl[0][1] for rl in lines)
            nxt = [lo for rl in lines for lo, _hi in rl if lo > t_out + 1e-6]
            over = BACK if not nxt else min(BACK, 0.5 * (min(nxt) - t_out))
            if nxt and min(nxt) <= max(rl[0][1] for rl in lines):
                raise CadError("%s: the wall behind is closer than the near wall is "
                               "thick here - use through=True or a smaller area" % what)
            end = t_out + over
        elif through is True:
            end = max(rl[-1][1] for rl in lines) + BACK
        else:
            end = t_in + float(through)
        start = t_in - BACK
        prism = face.extrude(V((0, 0, -(end - start))))
        top = c0 + u * a + v * b + n * (H - start)
        tools.append(_to_world(prism, top, u, v, n))
        _FOOT_AREA[0].append(face.Area)
    if buried:
        raise CadError("%s: %d hole(s) start inside material - `normal` must point OUT "
                       "of the surface, toward the viewer" % (what, buried))
    if not tools:
        raise CadError("%s: no hole lands on the part - check `center` (on the "
                       "surface) and `normal` (out of it)" % what)
    return tools, skipped


def grille(shape, center, normal, size, kind='hex', hole=3, pitch=4.5, margin=2, through='wall'):
    """Cut a vent grille of hex, slot, round or radial holes in the area `size` = (w, h) or a diameter, centred at `center` on the surface, drilled along -normal.

    `normal` points OUT of the surface (toward the viewer); the area's
    width runs horizontally (along +Y x normal, or X on a top face). hole
    = hex across-flats / round diameter / slot width; pitch = centre
    spacing (>= hole + 0.6 mm web). Holes that would cross the margin are
    dropped, never clipped into slivers. through='wall' stops each hole at
    the first wall (a shell), True drills every wall, a number is a blind
    depth. Every hole is measured by rays, so it follows a curved shell.

    One cad.cut with a list (R236, MEASURED: 150 hexes 0.35 s, 400 0.96 s;
    one extruded compound of hex faces took 61 s and was invalid - never).
    Prints the hole count and the open-area percentage."""
    t0 = time.time()
    _valid(shape, "grille: input")
    hole = _num(hole, "grille: hole", 0)
    pitch = _num(pitch, "grille: pitch", 0)
    margin = _num(margin, "grille: margin", 0, strict=False)
    if through not in ("wall", True) and not isinstance(through, (int, float)):
        raise CadError("grille: through must be 'wall', True or a depth in mm")
    if kind != "slot" and pitch < hole + 0.6 - 1e-9:
        raise CadError("grille: pitch %g leaves a web under 0.6 mm between %g mm holes - "
                       "use pitch >= %g" % (pitch, hole, hole + 0.6))
    if kind == "slot" and pitch < hole + 0.6 - 1e-9:
        raise CadError("grille: slot pitch %g leaves a web under 0.6 mm - use pitch >= %g"
                       % (pitch, hole + 0.6))
    area = _area_fit(size)
    holes = _layout(kind, area, hole, pitch, margin)
    if not holes:
        raise CadError("grille: no %g mm hole fits the area %s with margin %g" % (
            hole, size, margin))
    tools, skipped = _drill_pattern(shape, center, normal, holes, through, "grille")
    res = _c().cut(shape, tools)
    _valid(res, "grille", solids=len(shape.Solids))
    kept = len(tools)
    tot = sum(_FOOT_AREA[0])
    whole = area[1] * area[2] if area[0] == "rect" else math.pi * area[1] ** 2 / 4.0
    open_area = 100.0 * tot / whole
    print("grille: %d %s holes (hole %g, pitch %g)%s, open area %.0f%% of the %s area, %.2f s"
          % (kept, kind, hole, pitch, ", %d off the part skipped" % skipped if skipped else "",
             open_area, ("%g x %g mm" % (area[1], area[2])) if area[0] == "rect"
             else "d %g mm" % area[1], time.time() - t0))
    return res


def speaker_grille(shape, center, normal, d, ring_pitch=2.5, hole=1.4, through='wall'):
    """Cut a round speaker grille of diameter d: one centre hole and concentric rings of round holes ring_pitch apart, drilled along -normal.

    Same rules as grille(): `normal` points out of the surface, each hole is
    measured by rays (a curved shell is fine), through='wall' stops at the
    first wall. Holes on ring k are spaced about ring_pitch apart, every
    other ring turned half a step (R237, MEASURED: 91 holes 0.10 s)."""
    t0 = time.time()
    _valid(shape, "speaker_grille: input")
    d = _num(d, "speaker_grille: d", 0)
    ring_pitch = _num(ring_pitch, "speaker_grille: ring_pitch", 0)
    hole = _num(hole, "speaker_grille: hole", 0)
    if ring_pitch < hole + 0.5 - 1e-9:
        raise CadError("speaker_grille: ring_pitch %g leaves a web under 0.5 mm between "
                       "%g mm holes - use ring_pitch >= %g" % (ring_pitch, hole, hole + 0.5))
    holes = _layout("radial", ("round", d), hole, ring_pitch, 0.0)
    if not holes:
        raise CadError("speaker_grille: no %g mm hole fits a %g mm grille" % (hole, d))
    tools, _skipped = _drill_pattern(shape, center, normal, holes, through, "speaker_grille")
    res = _c().cut(shape, tools)
    _valid(res, "speaker_grille", solids=len(shape.Solids))
    pct = 100.0 * sum(_FOOT_AREA[0]) / (math.pi * d * d / 4.0)
    rings = int((d / 2.0 - hole / 2.0) / ring_pitch)
    print("speaker_grille: %d holes on %d rings, open area %.0f%% of d %g mm, %.2f s"
          % (len(tools), rings, pct, d, time.time() - t0))
    return res


# ------------------------------------------------------------------ wheels
def _revolve_face(face):
    res = face.revolve(V((0, 0, 0)), V((0, 0, 1)), 360)
    if res.ShapeType != "Solid" and not res.Solids:
        res = Part.Solid(Part.Shell(res.Faces))
    elif res.ShapeType != "Solid":
        res = res.Solids[0]
    if res.Volume < 0:
        res.reverse()
    return res


def _arc(c, rad, a0, a1):
    """A 3-point arc in the XZ plane (x = radius, z) round centre c."""
    def pt(a):
        return V((c[0] + rad * math.cos(a), 0, c[1] + rad * math.sin(a)))
    return Part.Arc(pt(a0), pt(0.5 * (a0 + a1)), pt(a1)).toShape()


def _tyre(R, ri, hw):
    """A tyre about Z from the bead (radius ri) to R, width 2*hw: a crown
    arc, shoulder arcs, flat sidewalls and rounded beads, every one an ARC,
    so the tyre is tori, planes and a cylinder (R238, MEASURED: tread
    booleans on the old spline-revolved tyre were 2-3x slower)."""
    H = R - ri
    Rc = max(2.0 * hw, 1.2 * H)                 # crown radius
    rs = min(0.42 * H, 0.55 * hw)               # shoulder radius
    rb = min(0.2 * H, 0.25 * hw)                # bead radius
    cc = (R - Rc, 0.0)
    cx = R - Rc + math.sqrt((Rc - rs) ** 2 - (hw - rs) ** 2)
    if cx < ri + rb + 0.2:
        raise CadError("wheel: the tyre is too thin for its width - a larger d or a "
                       "smaller rim_d")
    es = []
    for sg in (-1.0, 1.0):
        cs = (cx, sg * (hw - rs))
        # tangent point of shoulder and crown, on the line of centres
        ang = math.atan2(cs[1] - cc[1], cs[0] - cc[0])
        es.append((sg, cs, ang))
    lo, hi = es[0], es[1]
    edges = []
    # bead (cylinder), lower bead round, lower sidewall, lower shoulder,
    # crown, upper shoulder, upper sidewall, upper bead round
    edges.append(Part.LineSegment(V((ri, 0, hw - rb)), V((ri, 0, -hw + rb))).toShape())
    edges.append(_arc((ri + rb, -hw + rb), rb, math.pi, 1.5 * math.pi))
    edges.append(Part.LineSegment(V((ri + rb, 0, -hw)), V((cx, 0, -hw))).toShape())
    edges.append(_arc(lo[1], rs, 1.5 * math.pi, 2 * math.pi + lo[2]))
    edges.append(_arc(cc, Rc, lo[2], hi[2]))
    edges.append(_arc(hi[1], rs, hi[2], 0.5 * math.pi))
    edges.append(Part.LineSegment(V((cx, 0, hw)), V((ri + rb, 0, hw))).toShape())
    edges.append(_arc((ri + rb, hw - rb), rb, 0.5 * math.pi, math.pi))
    try:
        face = Part.Face(Part.Wire(Part.__sortEdges__(edges)))
    except Exception as exc:                            # noqa: BLE001
        raise CadError("wheel: the tyre profile did not close (%s)" % exc)
    return _revolve_face(face)


def wheel(d, width, rim_d=None, spokes=5, spoke_style='window', tread='block', tread_n=40,
          hub_d=None, bore=None, axis='+Y', at=(0, 0, 0)):
    """A wheel of diameter d as {"tyre", "rim", "cap"}: separate solids (rubber, metal, chrome) that do not overlap, centred at `at`, the cap facing `axis`.

    tyre  spline balloon profile; tread 'block' (cross grooves + a centre
          groove), 'chevron' (V grooves), 'rib' (3 rings) or None; tread_n
          grooves round it
    rim   barrel + front face with `spokes` filleted windows
          (spoke_style='window') or open bars ('bar'), a raised hub with
          lug recesses, softened; rim_d defaults to 0.62 * d
    cap   a domed centre cap seated in a pocket of the hub (0.05 mm clear);
          the rim is 0.1 mm inside the tyre bead
    bore  an axle hole through the rim hub (the cap covers it).

    Colour them: obj.ViewObject.ShapeColor = cad.color("rubber") ... (R238,
    MEASURED: 40 tread grooves 1.06 s, 5-window rim + fillets 0.22 s)."""
    t0 = time.time()
    cad = _c()
    d = _num(d, "wheel: d", 0)
    width = _num(width, "wheel: width", 0)
    R = d / 2.0
    hw = width / 2.0
    rim_d = 0.62 * d if rim_d is None else _num(rim_d, "wheel: rim_d", 0)
    ri = rim_d / 2.0
    if ri > R - 1.0:
        raise CadError("wheel: rim_d %g leaves under 1 mm of tyre on d %g - use rim_d <= %g"
                       % (rim_d, d, d - 2.0))
    hub_d = max(0.3 * rim_d, 4.0) if hub_d is None else _num(hub_d, "wheel: hub_d", 0)
    hr = hub_d / 2.0
    if bore is not None and _num(bore, "wheel: bore", 0) >= hub_d - 1.0:
        raise CadError("wheel: bore %g needs hub_d >= %g" % (bore, bore + 1.0))
    if hr > ri - 2.0:
        raise CadError("wheel: hub_d %g does not fit inside rim_d %g - use hub_d <= %g"
                       % (hub_d, rim_d, rim_d - 4.0))
    if spoke_style not in ("window", "bar"):
        raise CadError("wheel: spoke_style must be 'window' or 'bar'")
    if tread not in ("block", "chevron", "rib", None):
        raise CadError("wheel: tread must be 'block', 'chevron', 'rib' or None")
    spokes = int(spokes)
    if spokes < 3:
        raise CadError("wheel: spokes must be >= 3")

    # ---- tyre (local: axis +Z, centred at the origin)
    tyre = _tyre(R, ri, hw)
    H = R - ri
    if tread:
        depth = max(0.4, min(1.5, 0.04 * d, 0.25 * H))
        n = max(8, int(tread_n))
        pitch = 2 * math.pi * R / n
        gw = max(0.4, 0.32 * pitch)
        tools = []
        if tread in ("block", "rib"):
            zs = [0.0] if tread == "block" else [-0.45 * hw, 0.0, 0.45 * hw]
            rw = max(0.5, 0.08 * width) if tread == "block" else max(0.5, 0.07 * width)
            for z in zs:
                ring = Part.makeCylinder(R + 1, rw, V((0, 0, z - rw / 2))).cut(
                    Part.makeCylinder(R - depth, rw + 2, V((0, 0, z - rw / 2 - 1))))
                tools.append(ring)
        if tread == "block":
            g = Part.makeBox(depth + 1.0, gw, width + 2, V((R - depth, -gw / 2, -hw - 1)))
            tools += cad.polar_pattern(g, n)
        elif tread == "chevron":
            for sgn in (1, -1):
                g = Part.makeBox(depth + 1.0, gw, hw + 1.5,
                                 V((R - depth, -gw / 2, 0 if sgn > 0 else -hw - 1.5)))
                g.rotate(V((R, 0, 0)), V((1, 0, 0)), 28 * sgn)
                tools += cad.polar_pattern(g, n)
        # tread edges stay sharp, as moulded: MEASURED (R238) rounding the
        # 894 edges of a 40-groove block tread fails at every radius (22 s)
        tyre = cad.cut(tyre, tools)
    # ---- rim
    ro = ri - RIM_GAP
    rw = 0.84 * hw
    lip = max(0.8, min(2.0, 0.08 * ri))
    face_t = max(1.2, min(3.0, 0.22 * width))
    rim = Part.makeCylinder(ro, 2 * rw, V((0, 0, -rw)))
    rim = cad.cut(rim, Part.makeCylinder(ro - lip, 2 * rw - face_t + 1.0,
                                         V((0, 0, -rw - 1.0))))
    dish = min(0.6, 0.3 * face_t)
    if spoke_style == "window":
        rin, rout = hr + max(1.0, 0.1 * ri), ro - lip - max(0.6, 0.06 * ri)
        if rout - rin < 1.5:
            raise CadError("wheel: no room for spoke windows between hub_d %g and rim_d %g"
                           % (hub_d, rim_d))
        sw = max(1.2, 0.16 * ri)
        half = math.pi / spokes
        ai = half - (sw / 2.0) / rin
        ao = half - (sw / 2.0) / rout
        if ai <= 0.05:
            raise CadError("wheel: %d spokes do not fit round a %g mm hub - fewer spokes "
                           "or a larger hub_d" % (spokes, hub_d))
        p1 = V((rin * math.cos(-ai), rin * math.sin(-ai), 0))
        p2 = V((rout * math.cos(-ao), rout * math.sin(-ao), 0))
        p3 = V((rout * math.cos(ao), rout * math.sin(ao), 0))
        p4 = V((rin * math.cos(ai), rin * math.sin(ai), 0))
        wire = Part.Wire([Part.LineSegment(p1, p2).toShape(),
                          Part.ArcOfCircle(p2, V((rout, 0, 0)), p3).toShape(),
                          Part.LineSegment(p3, p4).toShape(),
                          Part.ArcOfCircle(p4, V((rin, 0, 0)), p1).toShape()])
        win = Part.Face(wire).extrude(V((0, 0, face_t + 4)))
        win.translate(V((0, 0, rw - face_t - 2)))
        win = fillet_safe(win, min(1.0, 0.22 * (rout - rin), 0.3 * sw),
                          [e for e in win.Edges if isinstance(e.Curve, Part.Line)
                           and abs((e.Vertexes[1].Point - e.Vertexes[0].Point).normalize().z) > 0.99])
        rim = cad.cut(rim, cad.polar_pattern(win, spokes, (0, 0, 1), (0, 0, 0), 360))
        rim = cad.cut(rim, Part.makeCylinder(ro - lip, dish + 1, V((0, 0, rw - dish))))
    else:
        rim = cad.cut(rim, Part.makeCylinder(ro - lip, face_t + 2, V((0, 0, rw - face_t - 1))))
        sw = max(1.2, 0.14 * ri)
        bar = Part.makeBox(ro - lip + 0.5 - (hr - 0.5), sw, face_t * 0.8,
                           V((hr - 0.5, -sw / 2, rw - face_t * 0.8 - dish)))
        rim = cad.fuse_one([rim] + cad.polar_pattern(bar, spokes))
    proud = 0.6
    hub = Part.makeCylinder(hr, rw * 2 + proud, V((0, 0, -rw)))
    rim = cad.fuse_one(rim, hub)
    # R238: soften the rim body FIRST, then cut the pocket, lugs and bore and
    # soften only their new edges (MEASURED: everything at once fails on a
    # lug/pocket pair and the ladder took 3.9 s for 93/94 edges)
    rr = min(0.6, 0.25 * face_t, 0.4 * lip)
    # not the barrel's outer edges: they sit under the tyre bead, and
    # MEASURED (R238) toroidal fillets there broke tyre.common(rim) - it
    # returned the whole rim (1748 mm3) for parts 0.05 mm apart
    rim = soften(rim, rr, lambda e: not (isinstance(e.Curve, Part.Circle)
                                         and e.Curve.Radius > ro - 0.5 * lip), budget_s=3)
    body = rim
    cap_r = max(1.0, hr - max(0.6, 0.18 * hr))
    pocket = 0.8
    top = rw + proud
    tools = [Part.makeCylinder(cap_r + 0.1, pocket + 1, V((0, 0, top - pocket)))]
    if hr - cap_r >= 1.2 and hr >= 3.0:
        lr = min(0.45, 0.3 * (hr - cap_r))
        lug = Part.makeCylinder(lr, 0.5 + 1, V(((cap_r + hr) / 2.0, 0, top - 0.5)))
        tools += cad.polar_pattern(lug, spokes)
    if bore:
        tools.append(Part.makeCylinder(float(bore) / 2.0, 4 * rw + 4, V((0, 0, -2 * rw - 2))))
    rim = cad.cut(rim, tools)
    rim = soften(rim, min(0.2, 0.5 * rr), new_edges(rim, body), min_r=0.1, budget_s=2)
    # ---- cap: in the pocket, 0.05 clear of its floor and wall
    cap_h = pocket - 0.05
    dome = min(0.5 * cap_r, 0.25 * cap_r + 0.3)
    cap = _domed_cyl(cap_r, cap_h + dome, dome)
    cap.translate(V((0, 0, top - pocket + 0.05)))
    cap = soften(cap, min(0.3, 0.2 * cap_r), budget_s=1)
    out = {}
    a = _dir(axis)
    rot = App.Rotation(V((0, 0, 1)), a)
    for k, s in (("tyre", tyre), ("rim", rim), ("cap", cap)):
        s = _single(s)
        s.Placement = App.Placement(V(at), rot).multiply(s.Placement)
        _valid(s, "wheel %s" % k, solids=1)
        out[k] = s
    for x, y in (("tyre", "rim"), ("rim", "cap"), ("tyre", "cap")):
        ov = out[x].common(out[y]).Volume
        if ov > 1e-3:
            raise CadError("wheel: %s and %s overlap by %.3f mm3 (internal error)" % (x, y, ov))
    print("wheel: d %g x %g, %s tread x %d, %d %s spokes, %.2f s" % (
        d, width, tread, tread_n if tread else 0, spokes, spoke_style, time.time() - t0))
    return out


def _domed_cyl(r, h, dome):
    """Cylinder r x h on z=0 with a spherical dome of height `dome` at the top."""
    if dome <= 1e-6:
        return Part.makeCylinder(r, h)
    if dome > r:
        dome = r
    body = Part.makeCylinder(r, h - dome)
    Rs = (r * r + dome * dome) / (2.0 * dome)
    sph = Part.makeSphere(Rs, V((0, 0, h - Rs)))
    capz0 = h - dome - min(0.5, 0.5 * (h - dome)) if h - dome > 1e-6 else 0.0
    top = Part.makeCylinder(r, h - capz0 + 1, V((0, 0, capz0))).common(sph)
    if h - dome <= 1e-6:
        return _single(top)
    return _c().fuse_one(body, top)


# -------------------------------------------------------------------- text
_FONT_CANDS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
               "/usr/share/fonts/dejavu/DejaVuSans.ttf",
               "/usr/share/fonts/TTF/DejaVuSans.ttf")


def _font(font):
    if font:
        if not os.path.isfile(font):
            raise CadError("text: font %r not found" % font)
        return font
    cands = list(_FONT_CANDS)
    try:
        cands.insert(0, os.path.join(App.getHomePath(), "fonts", "DejaVuSans.ttf"))
    except Exception:                                   # noqa: BLE001
        pass
    for c in cands:
        if os.path.isfile(c) and os.access(c, os.R_OK):
            return c
    raise CadError("text: no font found - pass font='/path/to/font.ttf'")


def text(shape, text, at, normal, size, depth=0.6, mode='emboss', up=(0, 0, 1), halign='center', font=None):
    """Emboss (raise) or deboss (sink) lettering `size` mm high into the surface at `at`, read from the `normal` side, following a curved surface.

    at: the centre of the text ON the surface (halign 'left' / 'right' puts
    the start / end there); normal points OUT of the surface toward the
    reader; up is the reading up direction (default +Z; +Y on a top face).
    Raised letters are sunk 0.4 mm into the body so they fuse into ONE
    solid; on a curved surface both modes use the body moved along the
    normal, so the letters keep their depth everywhere (R239, MEASURED:
    'ATECH' 8 mm 0.07 s, on a cylinder 0.24 s). Keep size >= 3 mm."""
    t0 = time.time()
    cad = _c()
    _valid(shape, "text: input")
    if not str(text).strip():
        raise CadError("text: empty text")
    size = _num(size, "text: size", 0)
    depth = _num(depth, "text: depth", 0)
    if size < 1.5:
        raise CadError("text: size %g mm is too small to build reliably - use >= 3" % size)
    if mode not in ("emboss", "deboss"):
        raise CadError("text: mode must be 'emboss' or 'deboss'")
    if halign not in ("center", "left", "right"):
        raise CadError("text: halign must be 'center', 'left' or 'right'")
    fpath = _font(font)
    try:
        wires = [w for ch in Part.makeWireString(str(text), fpath, size) for w in ch]
        letters = Part.makeFace(wires, "Part::FaceMakerBullseye")
    except Exception as exc:                            # noqa: BLE001
        raise CadError("text: could not build the letters (%s)" % exc)
    lb = letters.BoundBox
    x0 = {"center": lb.Center.x, "left": lb.XMin, "right": lb.XMax}[halign]
    letters.translate(V((-x0, -lb.Center.y, 0)))
    u, v, n = _frame(normal, up)
    p0 = V(at)
    lb = letters.BoundBox
    # surface height over the letters' footprint, measured along -n
    samp = [(x, y) for x in (lb.XMin, lb.Center.x, lb.XMax) for y in (lb.YMin, 0.0, lb.YMax)]
    H = lb.DiagonalLength + 5.0
    origins = [p0 + u * x + v * y + n * H for x, y in samp]
    runs = _rays(shape, origins, n * -1, H + _span(shape))
    hits = [H - rl[0][0] for rl in runs if rl]
    if not hits or len(hits) < len(samp):
        raise CadError("text: the letters run off the surface at `at` (only %d of %d "
                       "sample points meet it) - smaller size, or move `at`"
                       % (len(hits), len(samp)))
    if any(rl[0][0] < 1e-6 for rl in runs if rl):
        raise CadError("text: there is material in front of the surface - `normal` must "
                       "point OUT of the surface toward the reader")
    mid = runs[samp.index((lb.Center.x, 0.0))]
    if mid and abs(H - mid[0][0]) > ON_SURFACE:
        raise CadError("text: `at` is %.2f mm from the surface the letters would meet along "
                       "-normal - put `at` ON the surface and point `normal` OUT of it, "
                       "toward the reader" % abs(H - mid[0][0]))
    walls = [rl[0][1] - rl[0][0] for rl in runs if rl]
    h_lo, h_hi = min(hits), max(hits)
    sink = 0.4
    if mode == "deboss" and depth > min(walls) - 0.4:
        raise CadError("text: a %g mm deboss breaks (nearly) through the %.2f mm wall - "
                       "use depth <= %.2f" % (depth, min(walls), max(0.1, min(walls) - 0.5)))
    lo = h_lo - (depth if mode == "deboss" else sink) - 0.5
    hi = h_hi + depth + 0.5
    prism = letters.extrude(V((0, 0, hi - lo)))
    prism.translate(V((0, 0, lo)))
    prism = _to_world(prism, p0, u, v, n)
    if mode == "emboss":
        up_shape = shape.copy()
        up_shape.translate(n * depth)
        down = shape.copy()
        down.translate(n * -sink)
        raised = prism.common(up_shape).cut(down)
        if raised.Volume <= TOL:
            raise CadError("text: the letters did not meet the surface")
        res = cad.fuse_one(shape, raised)
    else:
        down = shape.copy()
        down.translate(n * -depth)
        tool = prism.cut(down)
        res = cad.cut(shape, tool)
    _valid(res, "text", solids=len(shape.Solids))
    print("text: %r %s, %g mm high, %d letters' faces, %.2f s"
          % (str(text), mode + "ed", size, len(letters.Faces), time.time() - t0))
    return res


# ----------------------------------------------------------------- colours
# R240: named product materials. The ViewObject recorder in check.py only
# captures DIRECT assignments in model.py, so a helper cannot colour a body;
# model.py writes   obj.ViewObject.ShapeColor = cad.color("rubber")
# and, for glass / smoked / LED, obj.ViewObject.Transparency = cad.transparency("glass")
# (MEASURED: both are recorded with the evaluated value).
MATERIALS = {
    "rubber":       {"ShapeColor": (0.10, 0.10, 0.11), "Transparency": 0},
    "glass":        {"ShapeColor": (0.62, 0.78, 0.88), "Transparency": 60},
    "chrome":       {"ShapeColor": (0.82, 0.84, 0.87), "Transparency": 0},
    "matte_white":  {"ShapeColor": (0.93, 0.93, 0.91), "Transparency": 0},
    "matte_black":  {"ShapeColor": (0.13, 0.13, 0.14), "Transparency": 0},
    "satin_grey":   {"ShapeColor": (0.56, 0.58, 0.61), "Transparency": 0},
    "graphite":     {"ShapeColor": (0.27, 0.28, 0.30), "Transparency": 0},
    "signal_red":   {"ShapeColor": (0.80, 0.11, 0.10), "Transparency": 0},
    "toy_yellow":   {"ShapeColor": (0.98, 0.78, 0.10), "Transparency": 0},
    "toy_blue":     {"ShapeColor": (0.12, 0.42, 0.86), "Transparency": 0},
    "toy_green":    {"ShapeColor": (0.20, 0.66, 0.32), "Transparency": 0},
    "orange":       {"ShapeColor": (0.96, 0.46, 0.10), "Transparency": 0},
    "mint":         {"ShapeColor": (0.62, 0.88, 0.78), "Transparency": 0},
    "sky":          {"ShapeColor": (0.55, 0.78, 0.95), "Transparency": 0},
    "coral":        {"ShapeColor": (0.98, 0.50, 0.45), "Transparency": 0},
    "cream":        {"ShapeColor": (0.96, 0.92, 0.82), "Transparency": 0},
    "led_white":    {"ShapeColor": (1.00, 1.00, 0.96), "Transparency": 20},
    "led_red":      {"ShapeColor": (1.00, 0.18, 0.15), "Transparency": 20},
    "led_green":    {"ShapeColor": (0.25, 1.00, 0.40), "Transparency": 20},
    "led_blue":     {"ShapeColor": (0.25, 0.55, 1.00), "Transparency": 20},
    "smoked":       {"ShapeColor": (0.20, 0.22, 0.25), "Transparency": 50},
    "frosted":      {"ShapeColor": (0.92, 0.94, 0.96), "Transparency": 35},
    "wood":         {"ShapeColor": (0.70, 0.52, 0.33), "Transparency": 0},
    "brushed_alu":  {"ShapeColor": (0.72, 0.74, 0.76), "Transparency": 0},
    "brass":        {"ShapeColor": (0.78, 0.64, 0.30), "Transparency": 0},
    "copper":       {"ShapeColor": (0.78, 0.45, 0.30), "Transparency": 0},
    "soft_touch":   {"ShapeColor": (0.25, 0.26, 0.28), "Transparency": 0},
}


def _material(name, what):
    key = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    if key not in MATERIALS:
        raise CadError("%s: unknown material %r - one of: %s" % (
            what, name, ", ".join(sorted(MATERIALS))))
    return MATERIALS[key]


def color(name):
    """The (r, g, b) floats 0..1 for a material name from cad.MATERIALS (rubber, glass, chrome, toy_yellow), a '#rrggbb' string or a 0..255 tuple.

    Write it as a direct assignment in model.py, which Studio records and
    applies:  obj.ViewObject.ShapeColor = cad.color("rubber")"""
    if isinstance(name, str) and name.strip().startswith("#"):
        h = name.strip()[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            raise CadError("color: %r is not '#rrggbb'" % name)
        try:
            return tuple(round(int(h[i:i + 2], 16) / 255.0, 4) for i in (0, 2, 4))
        except ValueError:
            raise CadError("color: %r is not '#rrggbb'" % name)
    if isinstance(name, (tuple, list)):
        if len(name) < 3:
            raise CadError("color: need (r, g, b)")
        vals = [float(x) for x in name[:3]]
        if max(vals) > 1.0:
            vals = [x / 255.0 for x in vals]
        if min(vals) < 0 or max(vals) > 1.0:
            raise CadError("color: components must be 0..1 or 0..255")
        return tuple(round(x, 4) for x in vals)
    return tuple(_material(name, "color")["ShapeColor"])


def transparency(name):
    """The Transparency (0..100 int) for a named material: glass 60, smoked 50, frosted 35, LEDs 20, everything else 0.

    obj.ViewObject.Transparency = cad.transparency("glass")"""
    return int(_material(name, "transparency")["Transparency"])


# ----------------------------------------------------------------- screws
# ISO 4762 socket / ISO 7380 button / ISO 10642 countersunk / ISO 7045 pan:
# head diameter dk, head height k, hex key s; clearance hole (medium).
_SCREWS = {
    "M2":   {"d": 2.0, "socket": (3.8, 2.0, 1.5), "button": (3.5, 1.3, 1.3),
             "csk": (3.8, 1.2), "pan": (4.0, 1.6), "clear": 2.4},
    "M2.5": {"d": 2.5, "socket": (4.5, 2.5, 2.0), "button": (4.7, 1.5, 1.5),
             "csk": (4.7, 1.5), "pan": (5.0, 2.0), "clear": 2.9},
    "M3":   {"d": 3.0, "socket": (5.5, 3.0, 2.5), "button": (5.7, 1.65, 2.0),
             "csk": (6.0, 1.7), "pan": (5.6, 2.4), "clear": 3.4},
    "M4":   {"d": 4.0, "socket": (7.0, 4.0, 3.0), "button": (7.6, 2.2, 2.5),
             "csk": (8.0, 2.3), "pan": (8.0, 3.1), "clear": 4.5},
    "M5":   {"d": 5.0, "socket": (8.5, 5.0, 4.0), "button": (9.5, 2.75, 3.0),
             "csk": (10.0, 2.8), "pan": (9.5, 3.7), "clear": 5.5},
    "M6":   {"d": 6.0, "socket": (10.0, 6.0, 5.0), "button": (10.5, 3.3, 4.0),
             "csk": (12.0, 3.3), "pan": (12.0, 4.6), "clear": 6.6},
}


def _size(size, what):
    key = str(size).strip().upper()
    if key not in _SCREWS:
        raise CadError("%s: size %r - one of %s" % (what, size, ", ".join(_SCREWS)))
    return _SCREWS[key]


def _hex_prism(s, h, z0):
    R = s / math.sqrt(3.0)
    pts = [V((R * math.cos(math.radians(60 * k)), R * math.sin(math.radians(60 * k)), z0))
           for k in range(6)]
    return Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V((0, 0, h)))


def _cross(d, depth, ztop):
    w = max(0.35, 0.18 * d)
    L = 0.75 * d
    a = Part.makeBox(L, w, depth + 1, V((-L / 2, -w / 2, ztop - depth)))
    b = Part.makeBox(w, L, depth + 1, V((-w / 2, -L / 2, ztop - depth)))
    return [a, b]


def screw(kind='socket', size='M3', length=8, at=(0, 0, 0), axis='-Z'):
    """A visible screw: head on the surface at `at`, shank `length` mm along `axis` (the driving direction), its shank 0.1 mm undersize so it never overlaps its hole.

    kind: 'socket' (ISO 4762, hex key), 'button' (ISO 7380), 'csk_phillips'
    (ISO 10642 head, its top flush at `at`; length includes the head) or
    'pan_phillips' (ISO 7045). Sizes M2 .. M6. A separate body: colour it
    cad.color("chrome") or "matte_black" (R241, MEASURED: 0.01-0.02 s)."""
    cad = _c()
    sz = _size(size, "screw")
    d = sz["d"]
    length = _num(length, "screw: length", 0)
    ds = d - 0.1
    if kind == "socket":
        dk, k, s = sz["socket"]
        head = Part.makeCylinder(dk / 2, k)
        head = fillet_safe(head, 0.08 * dk, [e for e in head.Edges if e.BoundBox.ZMin > k - 1e-6])
        head = cad.cut(head, _hex_prism(s, 0.6 * k + 1, k - 0.6 * k))
        head_z0 = 0.0
    elif kind == "button":
        dk, k, s = sz["button"]
        head = _domed_cyl(dk / 2, k, 0.6 * k)
        head = cad.cut(head, _hex_prism(s, 0.55 * k + 2, k - 0.55 * k))
        head_z0 = 0.0
    elif kind == "pan_phillips":
        dk, k = sz["pan"]
        head = _domed_cyl(dk / 2, k, 0.35 * k)
        head = cad.cut(head, _cross(dk, 0.45 * k, k))
        head_z0 = 0.0
    elif kind == "csk_phillips":
        dk, k = sz["csk"]
        head = Part.makeCone(d / 2 - 0.05, dk / 2, (dk - d) / 2.0, V((0, 0, -(dk - d) / 2.0)))
        k = (dk - d) / 2.0
        head = cad.cut(head, _cross(dk, 0.5 * k + 0.4, 0.0))
        head_z0 = -k
        length = length - k
        if length <= 0:
            raise CadError("screw: a countersunk M%g screw is at least %g mm long"
                           % (d, k + 1))
    else:
        raise CadError("screw: kind must be 'socket', 'button', 'csk_phillips' or "
                       "'pan_phillips'")
    shank = Part.makeCylinder(ds / 2, length + 0.3, V((0, 0, head_z0 - length)))
    shank = _c().chamfer_safe(shank, 0.15 * d, [e for e in shank.Edges
                                                if e.BoundBox.ZMax < head_z0 - length + 1e-6])
    body = cad.fuse_one(head, shank)
    a = _dir(axis)
    body.Placement = App.Placement(V(at), App.Rotation(V((0, 0, -1)), a)).multiply(body.Placement)
    _valid(body, "screw", solids=1)
    return _single(body)


def _first_run(shape, p, a, what=None):
    """The material runs (t_in, t_out) along `a` from point p, t > 0 only."""
    L = _span(shape) + (V(p) - shape.BoundBox.Center).Length
    rl = _rays(shape, [V(p)], a, L)[0]
    rl = [r for r in rl if r[1] > 1e-6]
    return rl


def _floor_under_rim(case, p, a, od, t_in, sink, u, v):
    """(t_in, sink) for the column: the floor measured under its RIM too.
    On a sloped roof a column cut to the floor at its axis pokes its rim
    out through the outer surface (MEASURED R242: 4 x 0.011 mm3 outside a
    toy shell's roof). Only the same floor, sloped, counts - not another
    wall the rim happens to graze."""
    rim = [p + (u * math.cos(2 * math.pi * k / 8) + v * math.sin(2 * math.pi * k / 8)) * (0.49 * od)
           for k in range(8)]
    t_axis = t_in
    for rl in _rays(case, rim, a, _span(case) + (p - case.BoundBox.Center).Length):
        rl = [r for r in rl if r[1] > 1e-6]
        if rl and t_axis - 0.5 * od < rl[0][0] < t_in and rl[0][0] > 1e-3:
            t_in, sink = rl[0][0], min(0.5, 0.5 * (rl[0][1] - rl[0][0]))
    return t_in, sink


def _gusset(case, p, a, dd, t_in, sink, gh, gt, reach):
    """One triangular gusset from the boss axis out along dd, its base sunk
    into the floor MEASURED at both ends (a curved roof or floor is not a
    plane), lengthened into a wall it meets within reach; None when no
    length keeps both base corners in material."""
    o = p + a * (t_in - 0.5 * gh)
    rl = [r for r in _rays(case, [o], dd, 1.5 * reach + 2.0)[0] if r[1] > 1e-6]
    wall = bool(rl and rl[0][0] < 1.5 * reach)
    gl = rl[0][0] + min(0.5, 0.5 * (rl[0][1] - rl[0][0])) if wall else reach
    wall_in = rl[0][0] if wall else None
    for _try in range(3):
        end = p + dd * gl
        # the floor just inside the wall (or the end): from inside the wall
        # itself the ray would start in material
        probe = p + dd * ((wall_in if wall else gl) - min(0.3, 0.05 * gl))
        fr = _first_run(case, probe, a)
        if fr and abs(fr[0][0] - t_in) <= 0.5 * gh:
            t_f = fr[0][0]
            sink_f = min(0.5, 0.5 * (fr[0][1] - fr[0][0]))
            q0 = p + a * (t_in - gh)
            q1 = end + a * (t_f - (0.5 * gh if wall else 0.15 * gh))
            q2 = end + a * (t_f + sink_f)
            q3 = p + a * (t_in + sink)
            inner = probe + a * (t_f + 0.5 * sink_f)
            if case.isInside(inner, 1e-6, True):
                side = dd.cross(a)
                side.normalize()
                g = Part.Face(Part.makePolygon([q0, q1, q2, q3, q0])).extrude(side * gt)
                g.translate(side * (-gt / 2))
                return g
        wall = False
        gl *= 0.7
    return None


RIB_LEN_D = 2.0     # R250: gussets reach at most max(2, RIB_LEN_D x d) out


def _ribs(ribs, what):
    try:
        n = int(ribs or 0)
    except (TypeError, ValueError):
        raise CadError("%s: ribs is a count (0 = no gussets), got %r" % (what, ribs))
    if n < 0 or n != float(ribs or 0):
        raise CadError("%s: ribs is a whole count >= 0 (0 = no gussets), got %r" % (what, ribs))
    return n


PILOT_D = {1.6: 1.3, 2.0: 1.7, 2.5: 2.1, 3.0: 2.5, 4.0: 3.4, 5.0: 4.2, 6.0: 5.1}


def pilot_d(d):
    """R444: the thread-forming pilot of an M`d` screw into plastic, about
    0.85 x d (atech_fit's "pilot" row: M2 1.7, M2.5 2.1, M3 2.5)."""
    d = float(d)
    for k, v in PILOT_D.items():
        if abs(k - d) < 1e-6:
            return v
    return round(0.85 * d, 1)


def pilot_depth(d, reach):
    """How deep screw_boss() drills its pilot: the reach, at most 4 d + 1."""
    return min(reach, 4.0 * d + 1.0)


def screw_boss(case, at, axis='-Z', size='M3', h=None, ribs=4, rib_len=None):
    """Fuse a screw boss into `case`: a column from `at` (its top, in air) along `axis` down to the floor it stands on, gussets, a pilot hole and a lead-in.

    The height is MEASURED along `axis` from `at` to the first material
    (the floor); h, when given, must reach it. OD = 2.2 x d; the pilot is
    the THREAD-FORMING pilot, about 0.85 x d (M2 1.7, M2.5 2.1, M3 2.5 -
    pilot_d; R444: a pilot of d gave the thread nothing to cut), so
    cad.screw's shank reaches into the boss wall: ./check reads that as
    the thread's engagement, not an overlap. ribs = gussets round the base (0 = none),
    each lengthened into a wall it meets within reach (R242); rib_len =
    how far they reach out from the column, at most max(2, 2 d) by default
    (R250: on a 30 mm column they reached 12 mm and hit a speaker)."""
    cad = _c()
    sz = _size(size, "screw_boss")
    d = sz["d"]
    a = _dir(axis)
    p = V(at)
    _valid(case, "screw_boss: input")
    if case.isInside(p, 1e-6, True):
        raise CadError("screw_boss: `at` is inside material - `at` is the boss TOP, in "
                       "the case's air, and `axis` points down to the floor it stands on")
    runs = _first_run(case, p, a, "screw_boss")
    if not runs:
        raise CadError("screw_boss: nothing below `at` along `axis` - `axis` points from "
                       "the boss top toward the floor ('-Z' for a floor below)")
    t_in, t_out = runs[0]
    floor_t = t_out - t_in
    sink = min(0.5, 0.5 * floor_t)
    if h is not None:
        h = _num(h, "screw_boss: h", 0)
        if h < t_in - 1e-6:
            raise CadError("screw_boss: h=%g does not reach the floor %.2f mm below `at` - "
                           "leave h=None to measure it" % (h, t_in))
    od = 2.2 * d
    u, v, _n = _frame(a)
    t_in, sink = _floor_under_rim(case, p, a, od, t_in, sink, u, v)
    L = t_in + sink
    boss = Part.makeCylinder(od / 2, L, p, a)
    parts = [boss]
    nrib = _ribs(ribs, "screw_boss")
    if nrib:
        gh = min(0.6 * t_in, 3.0 * d + 4.0)
        gt = max(1.0, 0.35 * d)
        # R250: the reach grew with the column (0.8 x its gusset height,
        # MEASURED 12 mm out on a long M3 column) - capped
        cap = max(2.0, RIB_LEN_D * d) if rib_len is None else _num(rib_len, "screw_boss: rib_len", 0)
        reach = od / 2 + min(max(2.0, 0.8 * gh), cap)
        dirs = [u * math.cos(2 * math.pi * k / nrib) + v * math.sin(2 * math.pi * k / nrib)
                for k in range(nrib)]
        for dd in dirs:
            g = _gusset(case, p, a, dd, t_in, sink, gh, gt, reach)
            if g is not None:
                parts.append(g)
    # booleans may raise the tolerances of their ARGUMENTS' sub-shapes in
    # place: MEASURED (R242) a failed second boss left the caller's case -
    # and the shape it was cut from - classifying a far point as inside.
    # Work on a deep copy so a failure never damages what was passed in.
    res = cad.fuse_one([case.copy()] + parts)
    # a blind pilot 4 d deep at most: one run all the way to a CURVED roof
    # ends on that surface and the countersink came back INVALID (R242)
    # R444: the thread-forming pilot (0.85 d), with a lead-in to d + 0.8
    res = cad.countersink(res, p, a, pilot_d(d), d + 0.8, 90.0, depth=pilot_depth(d, t_in))
    _valid(res, "screw_boss", solids=len(case.Solids))
    return res


def _infer_axis(lid, case, p):
    best = None
    for k in ("-Z", "+Z", "-X", "+X", "-Y", "+Y"):
        a = _dir(k)
        try:
            if lid.isInside(p - a * 0.3, 1e-6, True) or not lid.isInside(p + a * 0.3, 1e-6, True):
                continue
        except Exception:                               # noqa: BLE001
            continue
        rl = _first_run(case, p, a, "screw_through")
        if rl:
            if best is None or rl[0][0] < best[1]:
                best = (a, rl[0][0])
    if best is None:
        raise CadError("screw_through: `at` must be ON the lid's outer face, with the "
                       "case behind the lid along one axis")
    return best[0]


def screw_through(lid, case, at, size='M3', ribs=4, rib_len=None):
    """Matched screw fixing from ONE point on the lid's outer face: a countersink through the lid and a screw boss in the case under it; returns (lid, case).

    The axis is found from the geometry (into the lid, toward the case).
    The boss top sits 0.1 mm under the lid; the countersink fits
    cad.screw('csk_phillips', size, ...) with its head flush at `at` - the
    matching call, with its length, is printed (R243). ribs / rib_len: the
    boss's gussets, as screw_boss (ribs=0: a plain column, R250)."""
    sz = _size(size, "screw_through")
    d = sz["d"]
    p = V(at)
    _valid(lid, "screw_through: lid")
    _valid(case, "screw_through: case")
    a = _infer_axis(lid, case, p)
    lrun = _first_run(lid, p - a * BACK, a, "screw_through")
    if not lrun:
        raise CadError("screw_through: no lid material at `at`")
    lid_t = lrun[0][1] - BACK
    dk, _k = sz["csk"]
    kcone = (dk + 0.2 - sz["clear"]) / 2.0
    if lid_t < kcone + 0.4:
        raise CadError("screw_through: the lid is %.2f mm thick here, too thin for an %s "
                       "countersunk head (needs %.1f) - thicken the lid locally or use a "
                       "smaller size" % (lid_t, size, kcone + 0.4))
    lid2 = _c().countersink(lid, p, a, sz["clear"], dk + 0.2, 90.0, through="wall")
    # R506: the boss top 0.1 mm over the lid's inner face under the WHOLE
    # boss, not only at its axis - on a crowned or ramped lid the inner
    # face rises under the rim and the column's end sat in it (MEASURED:
    # the handheld at LENGTH 290, 0.26 mm3 of Front in Back)
    u, v, _n = _frame(a)
    inner = lid_t
    for rr in (0.25 * 2.2 * d, 0.5 * 2.2 * d + 0.1):
        for k in range(8):
            q = p + (u * math.cos(2 * math.pi * k / 8) + v * math.sin(2 * math.pi * k / 8)) * rr
            run = _first_run(lid, q - a * BACK, a)
            if run and run[0][0] - BACK < 3.0:
                inner = max(inner, run[0][1] - BACK)
    top = p + a * (inner + 0.1)
    case2 = screw_boss(case, top, a, size, ribs=ribs, rib_len=rib_len)
    rl = _first_run(case, top, a, "screw_through")
    reach = rl[0][0] if rl else 6.0
    # the tip stays 0.3 mm short of the pilot's bottom
    length = int(min(inner + 0.85 * reach, inner + 0.1 + pilot_depth(d, reach) - 0.3))
    print("screw_through: fits cad.screw('csk_phillips', '%s', length=%d, at=%s, axis=%s)"
          % (size, length, tuple(round(c, 3) for c in p), tuple(round(c, 3) for c in a)))
    return lid2, case2


# ------------------------------------------------------- caps, lenses, feet
def button_cap(d_or_wh, height, dome=0.5, flange=1.0, stem_d=None, at=(0, 0, 0), axis='+Z'):
    """A push-button cap `height` mm tall from its base at `at` to the top of its dome, pointing along `axis`: round (d) or rectangular ((w, h)), with a retaining flange.

    flange: how far the 0.8 mm thick base flange sticks out each side
    (keeps the cap in the case; 0 = none). stem_d: a stem of that diameter
    2 mm long below `at` down to the switch plunger. Cut the case opening
    with cad.opening_for(case, cap) (R244, MEASURED 0.01 s)."""
    cad = _c()
    height = _num(height, "button_cap: height", 0)
    dome = _num(dome, "button_cap: dome", 0, strict=False)
    flange = _num(flange, "button_cap: flange", 0, strict=False)
    ft = 0.8 if flange > 0 else 0.0
    if height <= ft + dome + 0.3:
        raise CadError("button_cap: height %g must exceed flange 0.8 + dome %g + 0.3"
                       % (height, dome))
    if isinstance(d_or_wh, (int, float)):
        r = _num(d_or_wh, "button_cap: d", 0) / 2.0
        if dome > r:
            raise CadError("button_cap: dome %g is more than the radius %g" % (dome, r))
        body = _domed_cyl(r, height, dome)
        body = soften(body, min(0.5, 0.12 * r), budget_s=1)
        if flange > 0:
            body = cad.fuse_one(body, Part.makeCylinder(r + flange, ft))
    else:
        w, hh = [float(x) for x in list(d_or_wh)[:2]]
        rc = min(0.2 * min(w, hh), 2.0)
        body = cad.rounded_box(w, hh, height, rc, at=(-w / 2, -hh / 2, 0))
        if dome > 1e-6:
            c = math.hypot(w, hh)
            Rs = (c * c / 4 + dome * dome) / (2 * dome)
            sph = Part.makeSphere(Rs, V((0, 0, height - Rs)))
            keep = Part.makeBox(w + 2, hh + 2, height - dome + 1e-3, V((-w / 2 - 1, -hh / 2 - 1, 0)))
            body = cad.fuse_one(body.common(sph.fuse(keep)))
        body = soften(body, min(0.5, 0.1 * min(w, hh)),
                      [e for e in body.Edges if e.BoundBox.ZMin > height - dome - 0.6], budget_s=2)
        if flange > 0:
            body = cad.fuse_one(body, cad.rounded_box(w + 2 * flange, hh + 2 * flange, ft,
                                                      rc + flange,
                                                      at=(-w / 2 - flange, -hh / 2 - flange, 0)))
    if stem_d:
        body = cad.fuse_one(body, Part.makeCylinder(float(stem_d) / 2, 2.0 + 0.3, V((0, 0, -2.0))))
    a = _dir(axis)
    body = _single(body)
    body.Placement = App.Placement(V(at), App.Rotation(V((0, 0, 1)), a)).multiply(body.Placement)
    _valid(body, "button_cap", solids=1)
    _remember_axis(body, a)
    return body


def lens(d, h, dome=0.8, at=(0, 0, 0), axis='+Z'):
    """A round lens or light-pipe cap d across, h tall from its base at `at` to the top of a spherical dome `dome` high, pointing along `axis`.

    Colour it cad.color("glass") / ("led_white") with cad.transparency(...)
    and cut its window with cad.opening_for(case, lens)."""
    d = _num(d, "lens: d", 0)
    h = _num(h, "lens: h", 0)
    dome = _num(dome, "lens: dome", 0, strict=False)
    if dome > d / 2.0:
        raise CadError("lens: dome %g is more than the radius %g" % (dome, d / 2.0))
    if dome > h:
        raise CadError("lens: dome %g is taller than h %g" % (dome, h))
    body = _single(_domed_cyl(d / 2.0, h, dome))
    a = _dir(axis)
    body.Placement = App.Placement(V(at), App.Rotation(V((0, 0, 1)), a)).multiply(body.Placement)
    _valid(body, "lens", solids=1)
    _remember_axis(body, a)
    return body


INLAY_CLEAR = 0.1       # R270: the insert's gap all round its pocket (press fit)
INLAY_FLANGE_T = 0.8    # R270: the flange plate behind the wall


def _outline_face(outline, what):
    """A planar Face from a Face, a closed Wire or 3D outline points."""
    if isinstance(outline, Part.Face):
        f = outline
    elif isinstance(outline, Part.Wire):
        if not outline.isClosed():
            raise CadError("%s: the outline wire is not closed" % what)
        f = Part.Face(outline)
    elif isinstance(outline, (list, tuple)):
        f = Part.Face(_form().spline_wire(list(outline), closed=True))
    else:
        raise CadError("%s: outline is a Face, a closed Wire or a list of 3D points "
                       "(cad.spline_wire(pts, plane=...) moved onto the surface)" % what)
    if f.isNull() or not f.isValid() or f.Area <= TOL:
        raise CadError("%s: the outline is not one flat closed loop" % what)
    try:
        if f.findPlane() is None and not isinstance(f.Surface, Part.Plane):
            raise CadError("%s: the outline is not flat" % what)
    except CadError:
        raise
    except Exception:                                   # noqa: BLE001
        pass
    return f


def inlay(shape, outline, depth=None, flange=0.8):
    """Cut a pocket of any outline (a heart lens, a logo light) into the wall under it; returns (shape, insert), the insert 0.1 mm clear with a flange behind the wall.

    lid, heart = cad.inlay(lid, cad.spline_wire(HEART, plane="XZ")
                                     .translated(V(0, y_face, 0)), flange=1)
    The outline lies on (within 1.5 mm of) the surface; the side facing
    out is found by rays. depth=None goes through the wall there
    (measured, its deepest point); a given depth is a blind pocket when
    the wall is thicker. A through pocket's insert carries a `flange` mm
    wide plate 0.8 thick against the inner face, so it cannot be pushed
    out. Offsets are cusp-safe (a heart's notch, R270): the outline's
    2D offset falls back to a re-filleted polygon. Checked: the insert is
    one valid solid that does not overlap the cut shape (R270)."""
    what = "inlay"
    cad = _c()
    form = _form()
    _valid(shape, "inlay: shape")
    flange = _num(flange, "inlay: flange", 0, strict=False)
    f = _outline_face(outline, what)
    n = V(f.normalAt(*[0.5 * (a + b) for a, b in zip(f.ParameterRange[0::2],
                                                       f.ParameterRange[1::2])]))
    n.normalize()
    c = form._face_point(f)
    L = _span(shape)
    pts = [c] + [q for e in f.OuterWire.Edges
                 for q in e.discretize(max(3, int(e.Length / 2.0) + 1))]
    best = None
    for a in (n, n * -1):
        runs = [[r for r in rr if r[1] > 1e-6] for rr in _rays(shape, [p + a * 3.0 for p in pts],
                                                               a * -1, 3.0 + L)]
        firsts = [rr[0] for rr in runs if rr]
        if len(firsts) < 0.8 * len(pts):
            continue
        t_in = min(r[0] for r in firsts) - 3.0
        if t_in < -ON_SURFACE or (best is not None and abs(t_in) >= abs(best[1])):
            continue
        best = (a, t_in, firsts, runs)
    if best is None:
        raise CadError("inlay: no wall under the outline - put the outline on the "
                       "surface (within %g mm), facing out" % ON_SURFACE)
    out, t_in, firsts, runs = best
    wall_out = max(r[1] for r in firsts) - 3.0          # deepest exit, from the plane
    nxt = [rr[1][0] - 3.0 for rr in runs if len(rr) > 1]
    through = depth is None
    if through:
        depth = wall_out
    depth = _num(depth, "inlay: depth", 0)
    if depth >= wall_out - 1e-6:
        through = True
    reach = wall_out + 0.3 if through else depth
    if nxt and reach > min(nxt) - 0.2:
        raise CadError("inlay: a second wall starts %.2f mm behind the outline - the "
                       "pocket would reach it; move the outline" % min(nxt))
    tool = f.copy()
    tool.translate(out * BACK)
    tool = tool.extrude(out * -(reach + BACK))
    res = cad.cut(shape, tool)
    fi = form._offset2d(f, -INLAY_CLEAR, "inlay insert")
    stem_len = (wall_out + 0.1) if through else depth
    insert = fi.extrude(out * -stem_len)
    if through and flange > 0:
        fl = form._offset2d(f, flange, "inlay flange")
        z = wall_out
        for _k in range(12):
            plate = fl.copy()
            plate.translate(out * -z)
            plate = plate.extrude(out * -INLAY_FLANGE_T)
            if plate.common(res).Volume <= 1e-3:
                break
            z += 0.5
        else:
            raise CadError("inlay: the flange meets the inner wall wherever it goes - "
                           "use a smaller flange")
        if z > wall_out + 1e-6:
            print("inlay NOTE: the inner face is not flat under the flange - it stands "
                  "%.2f mm off the deepest point" % (z - wall_out))
            stem = fi.copy()
            stem.translate(out * -(stem_len - 0.1))
            insert = cad.fuse_one(insert, stem.extrude(out * -(z - wall_out + 0.3)))
        plate = fl.copy()
        plate.translate(out * -z)             # ON the inner face; the stem reaches
        insert = cad.fuse_one(insert, plate.extrude(out * -INLAY_FLANGE_T))   # 0.1 in
    elif flange > 0:
        print("inlay NOTE: a blind %.2f mm pocket (the wall is %.2f mm) - no flange" % (
            depth, wall_out))
    insert = _single(insert)
    _valid(insert, "inlay: insert", solids=1)
    hit = insert.common(res).Volume
    if hit > 1e-3:
        raise CadError("inlay: the insert overlaps the wall by %.3f mm3 - the outline is "
                       "not on the surface or the wall is uneven there" % hit)
    _remember_axis(insert, out)
    print("inlay: %s pocket %.2f mm, insert %.0f mm3%s" % (
        "through" if through else "blind", reach if not through else wall_out,
        insert.Volume, ", flange %g mm" % flange if through and flange > 0 else ""))
    return res, insert


def foot(d, h, style='dome', at=(0, 0, 0)):
    """A rubber foot d across and h tall, its flat top at `at` pressed to the case bottom, hanging down (-Z); 'dome' has a rounded tread, 'cylinder' a small chamfer.

    A separate body touching the case (colour it cad.color("rubber"))."""
    d = _num(d, "foot: d", 0)
    h = _num(h, "foot: h", 0)
    r = d / 2.0
    body = Part.makeCylinder(r, h, V((0, 0, -h)))
    bottom = [e for e in body.Edges if e.BoundBox.ZMax < -h + 1e-6]
    if style == "dome":
        rr = min(0.6 * h, 0.45 * r)
        body = fillet_safe(body, rr, bottom)
    elif style == "cylinder":
        body = _c().chamfer_safe(body, min(0.3 * h, 0.15 * r, 0.6), bottom)
    else:
        raise CadError("foot: style must be 'dome' or 'cylinder'")
    body = _single(body)
    body.translate(V(at))
    _valid(body, "foot", solids=1)
    return body


# -------------------------------------------------------------- openings
def _silhouette(part, a, t_lo, t_hi, origin):
    """The part's outline seen along `a`: the union of its sections between
    t_lo and t_hi (distances along a from origin), as a face in the plane
    through origin normal to a."""
    faces = []
    bb = part.BoundBox
    lo_all = min((V(p) - origin).dot(a) for p in (
        V((x, y, z)) for x in (bb.XMin, bb.XMax) for y in (bb.YMin, bb.YMax) for z in (bb.ZMin, bb.ZMax)))
    hi_all = max((V(p) - origin).dot(a) for p in (
        V((x, y, z)) for x in (bb.XMin, bb.XMax) for y in (bb.YMin, bb.YMax) for z in (bb.ZMin, bb.ZMax)))
    lo, hi = max(t_lo, lo_all), min(t_hi, hi_all)
    if hi - lo < 1e-3:
        lo, hi = lo_all, hi_all
    k = 9
    for i in range(k):
        t = lo + (hi - lo) * (i + 0.5) / k
        try:
            ws = part.slice(a, origin.dot(a) + t)
        except Exception:                               # noqa: BLE001
            continue
        for w in ws:
            f = _loop_face(w)
            if f is None:
                continue
            f.translate(a * -(origin.dot(a) + t - origin.dot(a)))
            faces.append(f)
    if not faces:
        return None
    big = faces[0]
    for f in faces[1:]:
        try:
            big = big.fuse(f)
        except Exception:                               # noqa: BLE001
            pass
    try:
        big = big.removeSplitter()
    except Exception:                                   # noqa: BLE001
        pass
    outs = []
    for f in big.Faces:
        try:
            outs.append(Part.Face(f.OuterWire))
        except Exception:                               # noqa: BLE001
            outs.append(f)
    return outs


def _still_meets(part, wall):
    """mm3 of `part` inside `wall` (opening_for's gate)."""
    return part.common(wall).Volume


# R250: the direction each cap / lens was built to look out along, keyed
# by its exact geometry, so opening_for(case, cap) needs no axis= (a moved
# or fused copy is a new shape and falls back to the module / ray rules)
_MADE_AXIS = {}


def _shape_key(shape):
    try:
        bb = shape.BoundBox
        return (len(shape.Faces), round(shape.Volume, 4)) + tuple(
            round(x, 4) for x in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    except Exception:                                   # noqa: BLE001
        return None


def _remember_axis(shape, a):
    if len(_MADE_AXIS) > 512:
        _MADE_AXIS.clear()
    k = _shape_key(shape)
    if k is not None:
        _MADE_AXIS[k] = V(a)


def _module_axis(obj):
    """(world direction, words) of a seated or cabled module's working face
    - the one a part stands proud of (a socket, a shaft), else "up" - from
    atech_ports.working_faces with the object's own Placement; (None, None)
    for anything else or without the library (R250)."""
    name = getattr(obj, "AtechModule", None)
    pl = getattr(obj, "Placement", None)
    if not name or pl is None:
        return None, None
    try:
        import atech_ports
        faces = atech_ports.working_faces(str(name), pl)
    except Exception:                                   # noqa: BLE001
        return None, None
    if not faces:
        return None, None
    f = max(faces, key=lambda x: x.get("proud_mm") or 0.0)
    w = V(f["world"])
    if w.Length < 1e-9:
        return None, None
    w.normalize()
    return w, "the %s module's working face (%s)" % (name, f.get("word"))


def _one_wall(firsts, nxt_by_ray, hi, a, what):
    """R250 (through='wall' semantics): the rays across the part's outline
    must all cross ONE wall - their first runs alike in length (a curved or
    sloped wall makes them longer, a run ALONG a wall makes one 10x longer:
    the toy car's nose, 1593 mm3 cut where the opening is 229) - and no ray
    may meet a second wall before the cut ends."""
    lens = sorted(r[1] - r[0] for r in firsts)
    med = lens[len(lens) // 2]
    if lens[-1] > 2.5 * med + 1.5:
        raise CadError("%s: along %s the outline runs %.1f mm inside material where the "
                       "wall is %.1f mm thick - a wall or rib standing along that axis: the "
                       "cut would be a channel, not one opening through one wall. Pass "
                       "axis= the direction the part looks out along, or move the part clear "
                       "of the rib" % (what, tuple(round(x, 3) for x in a), lens[-1], med))
    if nxt_by_ray and min(nxt_by_ray) < hi - 1e-6:
        raise CadError("%s: along %s a second wall starts %.2f mm in, before the first one "
                       "ends - the opening would cut both. Pass axis= or move the part"
                       % (what, tuple(round(x, 3) for x in a), min(nxt_by_ray)))


OPEN_REACH = 20.0       # R270: opening_for's local region: the part's box + this (mm)
_LOCAL_ON = [True]      # R270: the sabotage run measures on the whole wall


def opening_for(wall, part_or_bbox, clearance=0.2, chamfer=0.3, axis=None):
    """Cut the opening in `wall` that a cap, lens or module passes through: its MEASURED outline plus `clearance`, through the wall in front of it, edge chamfered.

    part_or_bbox: a shape (cad.button_cap, cad.lens), a seated module or
    any object with a Shape or Mesh, or an App.BoundBox. axis: the
    direction from the part out through the wall; None takes a module's
    measured working face (atech_ports), the axis a cap or lens was built
    along, else the nearest wall along +-X/Y/Z that covers the whole outline
    (R250). Only the part's portion that reaches into the wall sets the
    outline (a cap's flange stays inside). Always ONE wall: a cut that
    would run along a wall or reach a second one raises. Checked: the
    part's outline then passes the wall without touching it (R245)."""
    cad = _c()
    _valid(wall, "opening_for: wall")
    clearance = _num(clearance, "opening_for: clearance", 0, strict=False)
    if isinstance(part_or_bbox, App.BoundBox):
        bb = App.BoundBox(part_or_bbox)
        part = Part.makeBox(bb.XLength, bb.YLength, bb.ZLength, V((bb.XMin, bb.YMin, bb.ZMin)))
    elif isinstance(part_or_bbox, Part.Shape):
        part = part_or_bbox
    else:
        mesh = getattr(part_or_bbox, "Mesh", None)
        sh = getattr(part_or_bbox, "Shape", None)
        if sh is not None and not sh.isNull() and sh.Solids:
            part = sh
        elif mesh is not None:
            bb = cad.bound_of(part_or_bbox)
            part = Part.makeBox(bb.XLength, bb.YLength, bb.ZLength, V((bb.XMin, bb.YMin, bb.ZMin)))
        else:
            raise CadError("opening_for: part_or_bbox must be a shape, an object with a "
                           "Shape or Mesh, or an App.BoundBox")
    pb = _c()._tight_bbox(part)
    corners = [V((x, y, z)) for x in (pb.XMin, pb.XMax) for y in (pb.YMin, pb.YMax)
               for z in (pb.ZMin, pb.ZMax)]

    def behind(a):
        # rays start 1 mm BEHIND the part (R245): a lens poking through the
        # wall has its centre inside the wall, its back end in the air
        lo_ = min((p - pb.Center).dot(a) for p in corners)
        return pb.Center + a * (lo_ - 1.0)
    L = _span(wall) + (pb.Center - wall.BoundBox.Center).Length + pb.DiagonalLength
    # R270 (MEASURED, round 1: 36-46 s builds; here 22.0 of 23.4 s were the
    # rays on a 28-face spline shell): the rays run against the wall's
    # LOCAL region - its common with the part's box grown OPEN_REACH mm -
    # and only when a ray reaches that region's edge are they re-run on
    # the whole wall. The cut itself is still made on the whole wall.
    grow = max(OPEN_REACH, 0.6 * pb.DiagonalLength)
    region = Part.makeBox(pb.XLength + 2 * grow, pb.YLength + 2 * grow, pb.ZLength + 2 * grow,
                          V((pb.XMin - grow, pb.YMin - grow, pb.ZMin - grow)))
    local = _clip(wall, region) if _LOCAL_ON[0] else wall
    how = "axis="
    if axis is None:
        a, how = _module_axis(part_or_bbox)
        if a is None:
            a = _MADE_AXIS.get(_shape_key(part))
            how = "the axis it was built along" if a is not None else None
        if a is None:
            try:
                a = _scan_axis(local, part, pb, corners, behind, L)
            except CadError:
                if local is wall:
                    raise
                a = _scan_axis(wall, part, pb, corners, behind, L)
            how = "the nearest wall"
    else:
        a = _dir(axis)
    c = behind(a)
    bound = region.BoundBox

    def inside_runs(origins, runs):
        # every run must END before the local region does (else the clip
        # cut it short and it is not the wall's real exit)
        for o, rr in zip(origins, runs):
            if not rr:
                continue
            q = o + a * (rr[0][1] + 0.05)
            if not (bound.XMin + 1e-3 < q.x < bound.XMax - 1e-3 and bound.YMin + 1e-3 < q.y
                    < bound.YMax - 1e-3 and bound.ZMin + 1e-3 < q.z < bound.ZMax - 1e-3):
                return False
        return True
    rl = [r for r in _rays(local, [c], a, L)[0] if r[1] > 1e-6]
    if local is not wall and not (rl and inside_runs([c], [rl])):
        local = wall
        rl = [r for r in _rays(wall, [c], a, L)[0] if r[1] > 1e-6]
    if not rl:
        raise CadError("opening_for: the wall is not in front of the part along %s (%s)"
                       % (tuple(round(x, 3) for x in a), how))
    t_in = rl[0][0]
    if t_in < -1e-6:
        raise CadError("opening_for: the part's back end is inside the wall - `axis` must "
                       "point from the part OUT through the wall")
    sil = _silhouette(part, a, t_in, t_in + 1e9, c)
    if not sil:
        raise CadError("opening_for: could not measure the part's outline")
    # the wall's span over the whole outline, from rays at its corners
    pts = [c]
    for f in sil:
        for e in f.OuterWire.Edges:         # a circle has ONE vertex: sample it
            for q in e.discretize(max(2, int(e.Length / 1.5) + 1)):
                pts.append(q - a * (q - c).dot(a))
    runs = [[r for r in rr if r[1] > 1e-6] for rr in _rays(local, pts, a, L)]
    if local is not wall and not inside_runs(pts, runs):
        runs = [[r for r in rr if r[1] > 1e-6] for rr in _rays(wall, pts, a, L)]
    firsts = [rr[0] for rr in runs if rr]
    if any(r[0] < -1e-6 for r in firsts):
        raise CadError("opening_for: along %s (%s) part of the outline starts inside "
                       "material - the part already sits in a wall there. Pass axis= the "
                       "direction it looks out along" % (tuple(round(x, 3) for x in a), how))
    lo = min(r[0] for r in firsts) - BACK
    hi = max(r[1] for r in firsts)
    nxt = [r[0] for rr in runs for r in rr[1:]]
    _one_wall(firsts, nxt, hi, a, "opening_for")
    hi += BACK if not nxt else min(BACK, 0.5 * (min(nxt) - hi))
    tools = []
    for f in sil:
        if clearance > 0:
            try:
                g = f.makeOffset2D(clearance, 0, False, False, False)
                if g.Area < f.Area:
                    g = f.makeOffset2D(-clearance, 0, False, False, False)
                f = g if isinstance(g, Part.Face) else Part.Face(g)
            except Exception as exc:                    # noqa: BLE001
                raise CadError("opening_for: could not add the %g clearance to the outline "
                               "(%s)" % (clearance, exc))
        pr = f.extrude(a * (hi - lo))
        pr.translate(a * lo)
        tools.append(pr)
    before = wall
    res = cad.cut(wall, tools)
    # gate: the part itself no longer meets the wall (R245)
    hit = _still_meets(part, res)
    if hit > 1e-3:
        raise CadError("opening_for: the part still overlaps the wall by %.3f mm3 after the "
                       "cut - it meets the wall outside the opening (a flange in the wall?) "
                       "or `axis` is not its direction out through the wall" % hit)
    if chamfer and chamfer > 0:
        mid = 0.5 * (min(r[0] for r in firsts) + max(r[1] for r in firsts))
        es = [e for e in new_edges(res, before) if (_mid(e) - c).dot(a) > mid]
        if es:
            r2 = _c().chamfer_safe(res, float(chamfer), es)
            if r2 is not res and r2.isValid() and len(r2.Solids) == len(res.Solids):
                res = r2
    _valid(res, "opening_for", solids=len(wall.Solids))
    if axis is None:
        print("opening_for: axis %s (%s)" % (tuple(round(x, 3) for x in a), how))
    return res


def _scan_axis(wall, part, pb, corners, behind, L):
    """The +-X/Y/Z direction to the nearest wall in front of the part that
    covers its whole outline as ONE wall (R250): rays at the centre and 8
    points of the part's box cross-section must each meet that wall first,
    from air, with first runs alike in length (_one_wall), and the part's
    centre of mass may not be past the wall (R245)."""
    try:
        cm = part.CenterOfMass if hasattr(part, "CenterOfMass") else pb.Center
    except Exception:                                   # noqa: BLE001
        cm = pb.Center
    best = None
    for k in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
        a = _dir(k)
        o = behind(a)
        u, v, _n = _frame(a)
        hu = 0.45 * max((p - pb.Center).dot(u) for p in corners)
        hv = 0.45 * max((p - pb.Center).dot(v) for p in corners)
        origins = [o + u * (i * hu) + v * (j * hv) for i in (-1, 0, 1) for j in (-1, 0, 1)]
        runs = [[r for r in rr if r[1] > 1e-6] for rr in _rays(wall, origins, a, L)]
        if not all(runs) or any(rr[0][0] <= 0 for rr in runs):
            continue
        firsts = [rr[0] for rr in runs]
        if (cm - o).dot(a) > max(r[1] for r in firsts):
            continue
        try:
            _one_wall(firsts, [], 1e18, a, "opening_for")
        except CadError:
            continue
        t_near = sorted(r[0] for r in firsts)[len(firsts) // 2]
        if best is None or t_near < best[1]:
            best = (a, t_near)
    if best is None:
        raise CadError("opening_for: no single wall in front of the whole part along "
                       "+-X/Y/Z - pass axis=")
    return best[0]


# ------------------------------------------------------------------ knurl
def knurl(shape, axis, center, r, z0, z1, n=60, kind='straight', depth=0.4):
    """Knurl the cylindrical surface of radius r round `axis` through `center`, from z0 to z1 along the axis, with n V grooves round it (straight, rings or diamond).

    'straight' grooves run along the axis, 'rings' go round it at the same
    pitch, 'diamond' is both: never helices (R245, MEASURED: a helical
    diamond knurl took 2.7 s and gave 7 solids; 60 straight grooves 0.24 s).
    r is checked against the measured surface; depth < half the pitch."""
    t0 = time.time()
    cad = _c()
    _valid(shape, "knurl: input")
    a = _dir(axis)
    c = V(center)
    r = _num(r, "knurl: r", 0)
    depth = _num(depth, "knurl: depth", 0)
    z0, z1 = float(z0), float(z1)
    if z1 <= z0:
        raise CadError("knurl: z1 must be > z0 (positions along the axis from center)")
    n = int(n)
    if n < 6:
        raise CadError("knurl: n must be >= 6")
    if kind not in ("straight", "rings", "diamond"):
        raise CadError("knurl: kind must be 'straight', 'rings' or 'diamond'")
    pitch = 2 * math.pi * r / n
    if depth > 0.5 * pitch:
        raise CadError("knurl: depth %g is over half the %.2f mm pitch - use depth <= %.2f "
                       "or a smaller n" % (depth, pitch, 0.5 * pitch))
    u, v, _a = _frame(a)
    probe = c + a * (0.5 * (z0 + z1)) + u * (r + 3.0)
    rl = [x for x in _rays(shape, [probe], u * -1, 2 * r + 6)[0] if x[1] > 1e-6]
    if not rl or abs((r + 3.0 - rl[0][0]) - r) > 0.25:
        got = (r + 3.0 - rl[0][0]) if rl else None
        raise CadError("knurl: the surface at that height is %s, not r=%g - pass the "
                       "measured radius" % ("missing" if got is None else "r=%.2f" % got, r))
    half = depth + 0.6
    tools = []
    if kind in ("straight", "diamond"):
        tri = Part.Face(Part.makePolygon([V((r - depth, 0, 0)), V((r + 0.6, -half, 0)),
                                          V((r + 0.6, half, 0)), V((r - depth, 0, 0))]))
        g = tri.extrude(V((0, 0, z1 - z0)))
        g.translate(V((0, 0, z0)))
        tools += cad.polar_pattern(g, n)
    if kind in ("rings", "diamond"):
        m = int((z1 - z0) / pitch)
        if m < 1:
            raise CadError("knurl: the band %g mm is shorter than one ring pitch %.2f"
                           % (z1 - z0, pitch))
        span = m * pitch
        zs = [z0 + 0.5 * (z1 - z0 - span) + pitch * (i + 0.5) for i in range(m)]
        for z in zs:
            tri = Part.Face(Part.makePolygon([V((r - depth, 0, z)), V((r + 0.6, 0, z - half)),
                                              V((r + 0.6, 0, z + half)), V((r - depth, 0, z))]))
            tools.append(_revolve_face(tri))
    placed = [_to_world(t, c, u, v, a) for t in tools]
    res = cad.cut(shape, placed)
    _valid(res, "knurl", solids=len(shape.Solids))
    print("knurl: %s, %d cutters, pitch %.2f, %.2f s" % (kind, len(placed), pitch,
                                                          time.time() - t0))
    return res


def _register():
    """R230: when atech_detail is imported BEFORE atech_cad, atech_cad's
    `from atech_detail import *` runs while this file is still half
    loaded and gets none of these names; hand them over now (only names
    atech_cad does not already have)."""
    import sys
    m = sys.modules.get("atech_cad")
    if m is None:
        return
    g = globals()
    for name in __all__:
        if not hasattr(m, name):
            setattr(m, name, g[name])
    all_ = getattr(m, "__all__", None)
    if isinstance(all_, list):
        all_.extend(n for n in __all__ if n not in all_)


_register()
