"""atech_geom - the measurements Studio and check.py both judge a build by.

One copy, used on both sides of the sandbox:
    check.py   (the headless child and the agent's ./check)
    build.py   (Studio, after the build is in the document)
so the agent's self-check and Studio's gate can never disagree about what an
overlap or a fragment is.

Everything here MEASURES a shape; nothing asserts. A value that cannot be
measured is None, never a plausible substitute.

    tight(shape)            optimalBoundingBox (Shape.BoundBox is a loose
                            bound on curved bodies)
    fragments(shape)        a stray little solid next to the real body
    overlaps(items, ...)    bodies that intersect and were not meant to
    floating(items)         a body that touches nothing else
    holes(shape)            diameters of holes/bores (blind cavities excluded)
    bores(shape)            every concave cylinder: diameter, blind, cavity;
                            round channels open along their length (R170);
                            the walls each one crosses (R181); a container's
                            mouth is a cavity, not a hole (R183)
    wall_crossings(shape)   holes drilled through more than one wall (R181)
    below_desk(parts, req)  a product the request stands on a desk reaching
                            below z = 0 (R177)
    read_intent / intent_problems
                            intent.json vs the build - ONE implementation
                            for ./check and Studio (PRD S30)
    intent_changed(ws)      intent.json edited since the turn's first check
                            ("INTENT CHANGED", S37)
    intent_record / intent_guard
                            the record taken before model.py runs, read-only,
                            put back if model.py deletes or rewrites it (R135)
    start_turn / read_turn  Studio's turn file: the user's turn may change
                            intent.json, a fix turn may not except to a
                            value from the user's message (R151)
    request_size(request)   the one overall size a user's message gives
                            (R168: measured over all parts together)
    face_open(...)          per seated module, the share of rays from its
                            working face that leave the product (R152)
    socket_face(mesh, ...)  a connector's mouth direction, measured from
                            the module mesh (R164)
    thin_walls(parts)       the thinnest wall a sampled, time-capped ray
                            probe measures (R154)
    containers(parts, ...)  a part named pot / cup / planter must be open
                            from above (R169)
    rect_notches(shape, w)  open rectangular notches w wide - intent
                            "slots" with "w_mm" (R191)
    hold_probe(parts, ...)  the held object intent "holds" declares can
                            reach its seat straight from outside (R192)
    solid_lids(parts)       a lid / cover / cap that is a solid plug (S58)
    motion_probe(parts, ..) a part intent "motion" declares turning about
                            an axis, swept through its range: the first
                            angle it hits another part (R202)
    mates_probe(parts, ..)  the reference object intent "mates" declares
                            (a pegboard) built and tested against the
                            part: only pegs in their holes may enter (R213)
    joint_probe(parts, ..)  a part that only touches the others - no lip,
                            plug, hook or screw reaching into them (R212)
    channel_wraps(shape)    each round channel's wrap angle, summed as the
                            benchmark sums it (S62)
    side_walls(values)      the side walls' measured thickness (R194)
    tess_slow(shape)        tessellating it would take seconds: the
                            tessellation probes leave it out, say so (R129)
    points_inside / distance / touching
                            point-in-solid and gaps that stay fast on heavy
                            (mesh-derived) solids: sampled there, said so (R129)
    margins(parts, atech)   each board/module's outline margin to the part
                            around it, per side (R141)
    atech_layout(...)       the agent's parts vs the Atech board and modules:
                            resting on the desk (with the exact Z shift,
                            R126), containment, orientation (S36); parts
                            far from the board are not judged (R114)
    fingerprint(shape)      a cheap identity for "did this body change?"
                            (geometry hash, not BREP text - see there)
    record_view(code)       AST rewrite: X.ViewObject.attr = v -> recorded,
                            so a headless build keeps the colours it set

FreeCAD is imported inside the functions: importing this module costs nothing
and works under plain Python (for the code rewrite).
"""
import ast
import hashlib

MIN_OVERLAP_MM3 = 0.01      # below this, "overlap" is contact noise (PRD S18)
FRAGMENT_RATIO = 0.10       # smallest disjoint solid < 10 % of the largest
FLOAT_GAP_MM = 0.5          # farther than this from every other body
MAX_PAIRS_OBJECTS = 30      # pairwise checks are O(n^2): cap the inputs
MESH_SAMPLES = 1500         # mesh points tested against a solid, at most
HEAVY_SAMPLES = 600         # ... against a heavy (mesh-derived) solid: its
                            # tessellation alone costs 0.55-0.75 s (MEASURED
                            # R129: tessellate, exportStl, MeshPart and per-face
                            # all >= 0.55 s on 16 069 faces, GIL held), so the
                            # samples after it must stay cheap
FP_BREP_FACES = 500         # BREP-hash a shape only below this face count

# R129: OCCT's per-point and distance queries scale with the face count.
# MEASURED 2026-09-25 on a solid made from the 14-port board mesh (16 069
# planar faces): isInside 0.30 s PER POINT (1 500 samples = 7.5 min - the
# dogfood harness's 10-minute stall), distToShape 1.48 s, common 1.0-1.6 s.
# Above HEAVY_FACES a shape is judged on its tessellation with numpy
# instead (ray-parity inside test, point-to-triangle distance), reported as
# sampled - never as an exact volume or distance.
HEAVY_FACES = 2000
# R129 floor, MEASURED 2026-09-25 (load average 5.4, board + button,
# speaker, light modules + the 16 069-face board solid + a case): a cold
# overlaps() takes 0.86-0.96 s, warm 0.17-0.18 s. Most of it is ONE OCCT
# tessellate() of the board solid: 0.56-0.78 s wall (3-6 CPU-s over its
# threads, GIL held), whatever the deflection (0.56 s at 10 mm). Every
# other route to its triangles is no cheaper: getFaces 0.53 s, MeshPart
# 1.1 s, exportStl >= 0.55 s, and walking .Faces alone costs 0.21 s. That
# tessellation is the floor of a cold check with a mesh-derived solid; it
# is cached per shape (_TESS) so it is paid once per process. distToShape
# is never called on a heavy shape, nor on a face of many loops
# (DIST_LOOPS_MAX) - there only section() (2.1 s on a 2 304-hole plate
# lying under a lid: that plate's floor; 0.14 s at 400 holes).
TOUCH_MM = 0.01             # sampled surfaces this close are in contact
FRAG_APART_MM = 1.0         # a heavy pair sampled farther apart than this is
                            # disjoint; between TOUCH_MM and this: cannot tell


# ----------------------------------------------------------------- basics
def _cached(store, shape, make, size=16):
    """make(shape), kept per shape (hashCode, then isSame: the entry holds
    the shape, so its hashCode cannot be reused while the entry lives)."""
    try:
        key = shape.hashCode()
    except Exception:                                   # noqa: BLE001
        return make(shape)
    hit = store.get(key)
    if hit is not None and hit[0].isSame(shape):
        return hit[1]
    val = make(shape)
    if len(store) >= size:
        store.clear()
    store[key] = (shape, val)
    return val


def _optimal(shape):
    try:
        return shape.optimalBoundingBox(True, False)
    except Exception:                                   # noqa: BLE001
        return shape.BoundBox


_TIGHT = {}                 # hashCode -> (shape, tight box)
_BOUND = {}                 # hashCode -> (shape, BoundBox)


def tight(shape):
    """Tight axis-aligned box. Falls back to BoundBox only if OCCT refuses.
    Cached per shape and handed out as a copy (R129: 10 ms a call on the
    16 069-face board solid, asked several times per check)."""
    import FreeCAD as App
    return App.BoundBox(_cached(_TIGHT, shape, _optimal))


def _bound(shape):
    """shape.BoundBox, cached per shape (3 ms a call on the board solid)."""
    import FreeCAD as App
    return App.BoundBox(_cached(_BOUND, shape, lambda s: s.BoundBox))


def dims(shape):
    bb = tight(shape)
    return [round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3)]


def _bb_gap(a, b):
    """Distance between two BoundBoxes (0 when they touch or intersect)."""
    dx = max(0.0, max(a.XMin, b.XMin) - min(a.XMax, b.XMax))
    dy = max(0.0, max(a.YMin, b.YMin) - min(a.YMax, b.YMax))
    dz = max(0.0, max(a.ZMin, b.ZMin) - min(a.ZMax, b.ZMax))
    return (dx * dx + dy * dy + dz * dz) ** 0.5


# ------------------------------------------------- heavy shapes (R129)
def n_faces(shape):
    """Face count without building a Python object per face (len(Faces)
    took 0.24 s on the 16 069-face board solid)."""
    try:
        return int(shape.countElement("Face"))
    except Exception:                                   # noqa: BLE001
        try:
            return len(shape.Faces)
        except Exception:                               # noqa: BLE001
            return 0


_HEAVY = {}                 # hashCode -> (shape kept alive, verdict)
HEAVY_SAMPLE = 64           # faces looked at to call a shape mesh-like


def heavy(shape):
    """True when OCCT's point / distance queries on `shape` are slow AND
    its tessellation is cheap: over HEAVY_FACES faces, sampled faces all
    planar with at most 4 edges (a solid made from a mesh).

    MEASURED 2026-09-25 (R129 review): a 100x100x10 plate with 2 200 small
    round holes (2 211 faces) tessellates in 113-117 s where common() with
    a pin takes 0.2 s and isInside 38 ms/point - a many-faced B-rep stays
    on OCCT; only the mesh-like shape goes to the numpy route."""
    try:
        key = shape.hashCode()
    except Exception:                                   # noqa: BLE001
        key = None
    hit = _HEAVY.get(key) if key is not None else None
    if hit is not None and hit[0].isSame(shape):
        return hit[1]                   # (countElement is 1.4 ms on 16 k faces,
                                        # and heavy() is asked dozens of times)
    n = n_faces(shape)
    if n <= HEAVY_FACES:
        verdict = False
        if key is not None:
            if len(_HEAVY) >= 64:
                _HEAVY.clear()
            _HEAVY[key] = (shape, verdict)
        return verdict
    verdict = True
    try:
        for i in range(HEAVY_SAMPLE):
            f = shape.getElement("Face%d" % (1 + i * n // HEAVY_SAMPLE))
            if not isinstance(f.Surface, _plane_type()) or len(f.Edges) > 4:
                verdict = False
                break
    except Exception:                                   # noqa: BLE001
        verdict = False                 # cannot tell: stay exact (OCCT)
    if key is not None:
        if len(_HEAVY) >= 64:
            _HEAVY.clear()
        _HEAVY[key] = (shape, verdict)
    return verdict


def _plane_type():
    import Part
    return Part.Plane


_TESS = {}                  # hashCode -> (shape kept alive, points, triangles)
EXACT_POINTS = 200          # fewer points than this on a light shape: all exact


def _deflection(shape):
    """Linear deflection of _tess: the tessellation is within this of the
    true surface."""
    return max(0.02, 1e-3 * max(_bound(shape).DiagonalLength, 1.0))


# R129: OCCT meshes a planar face with many inner loops in time that grows
# with the square of the loops. MEASURED 2026-09-25, a 100 x 100 x 10 plate
# with k round holes through one face, tessellate(_deflection): 0.07 s
# (k = 25), 0.59 s (100), 2.3 s (225), 5.7 s (400), 22 s (900) - and the
# 2 304-hole plate of the R129 test 37 s inside the wall probe. The GIL is
# held throughout (MEASURED), so no thread can stop it. Above this many
# loops on one face the tessellation-based probes leave the shape out and
# say so; OCCT's exact queries still judge it.
TESS_LOOPS_MAX = 120
# R129: distToShape on such a face grows the same way. MEASURED 2026-09-25,
# the plate above (k holes) against a 100 x 100 lid lying ON it (contact,
# the worst case): 0.04 s (k = 25), 0.74 s (100), 5.1 s (225), 27 s (400);
# with the lid 0.3 mm above it the 2 304-hole plate took 537 s. Above this
# many loops on one face, distance() judges contact only, with section()
# (0.14 s at k = 400, 2.1 s at k = 2 304 - that plate's floor).
DIST_LOOPS_MAX = 60
_LOOPS = {}                 # hashCode -> (shape kept alive, loops)


class SlowToTessellate(Exception):
    """The shape has a face whose tessellation would take seconds."""


def busiest_face_loops(shape):
    """The most boundary loops (outer + holes) on any one face of `shape`.
    1 for a heavy mesh-like shape (triangles and quads by definition)."""
    if heavy(shape):
        return 1
    try:
        key = shape.hashCode()
    except Exception:                                   # noqa: BLE001
        key = None
    hit = _LOOPS.get(key) if key is not None else None
    if hit is not None and hit[0].isSame(shape):
        return hit[1]
    try:
        n = max([len(f.Wires) for f in shape.Faces] or [0])
    except Exception:                                   # noqa: BLE001
        n = 0
    if key is not None:
        if len(_LOOPS) >= 64:
            _LOOPS.clear()
        _LOOPS[key] = (shape, n)
    return n


def tess_slow(shape):
    """True when tessellating `shape` would take seconds (see TESS_LOOPS_MAX)."""
    return busiest_face_loops(shape) > TESS_LOOPS_MAX


def _tess(shape):
    """(points (n,3), triangles (m,3,3)) numpy arrays of `shape`'s surface.
    Cached per shape: tessellating the board solid costs 0.6-0.9 s. The
    cache holds the shape itself, so its hashCode cannot be reused by a
    new shape while the entry lives. Raises SlowToTessellate for a shape
    with a face of more than TESS_LOOPS_MAX loops (R129)."""
    import numpy as np
    try:
        key = shape.hashCode()
    except Exception:                                   # noqa: BLE001
        key = None
    hit = _TESS.get(key) if key is not None else None
    if hit is not None and hit[0].isSame(shape):
        return hit[1], hit[2]
    if tess_slow(shape):
        raise SlowToTessellate("a face with %d boundary loops (holes) would take "
                               "seconds to tessellate" % busiest_face_loops(shape))
    pts, faces = shape.tessellate(_deflection(shape))
    P = np.array([(p.x, p.y, p.z) for p in pts], dtype=float).reshape(-1, 3)
    F = np.array(faces, dtype=int).reshape(-1, 3)
    T = P[F] if len(F) else np.zeros((0, 3, 3))
    if key is not None:
        if len(_TESS) >= 16:
            _TESS.clear()
        _TESS[key] = (shape, P, T)
    return P, T


def _samples(shape, step=0.5, cap=20000):
    """Surface sample points: the tessellation's vertices, plus points
    along the edges of a light shape (its big faces have few vertices, and
    an edge passing close to another body is where two bodies meet)."""
    import numpy as np
    try:
        P, _T = _tess(shape)
    except SlowToTessellate:
        P = np.zeros((0, 3))            # the edge samples below still cover it
    if heavy(shape):
        return P
    extra = []
    try:
        for e in shape.Edges:
            n = int(min(200, max(2, e.Length / step)))
            extra.extend((p.x, p.y, p.z) for p in e.discretize(n))
    except Exception:                                   # noqa: BLE001
        pass
    if extra:
        P = np.vstack([P, np.array(extra, dtype=float)])
    if len(P) > cap:
        P = P[::int(len(P) // cap) + 1]
    return P


def _box_of(P, pad=0.0):
    return P.min(axis=0) - pad, P.max(axis=0) + pad


def _pt_tri_dist(Q, T, limit=None, chunk=16):
    """Distance from each point in Q (n,3) to the nearest triangle of T
    (m,3,3); inf where no triangle is within `limit`. Exact point-triangle
    distance (projection inside the triangle, else the nearest edge)."""
    import numpy as np
    out = np.full(len(Q), np.inf)
    if not len(Q) or not len(T):
        return out

    def prep():
        A, B, C = T[:, 0], T[:, 1], T[:, 2]
        AB, AC = B - A, C - A
        N = np.cross(AB, AC)
        d00 = (AB * AB).sum(1)
        d01 = (AB * AC).sum(1)
        d11 = (AC * AC).sum(1)
        return (T.min(axis=1), T.max(axis=1), A, AB, AC, N,
                np.linalg.norm(N, axis=1), d00, d01, d11, d00 * d11 - d01 * d01)
    tmin, tmax, A, AB, AC, N, nlen, d00, d01, d11, den = _prepared(T, "dist", prep)
    pad = np.inf if limit is None else float(limit)
    order = _cell_order(Q, chunk)
    for s in range(0, len(Q), chunk):
        idx = order[s:s + chunk]
        p = Q[idx]
        if limit is None:
            sel = np.ones(len(T), dtype=bool)
        else:
            lo, hi = p.min(axis=0) - pad, p.max(axis=0) + pad
            sel = np.all((tmax >= lo) & (tmin <= hi), axis=1)
            if not sel.any():
                continue
        a, ab, ac = A[sel], AB[sel], AC[sel]
        n, nl, dd = N[sel], nlen[sel], den[sel]
        ap = p[:, None, :] - a[None]
        d20 = (ap * ab[None]).sum(2)
        d21 = (ap * ac[None]).sum(2)
        ok = dd > 1e-18
        with np.errstate(divide="ignore", invalid="ignore"):
            v = np.where(ok, (d11[sel] * d20 - d01[sel] * d21) / dd, -1.0)
            w = np.where(ok, (d00[sel] * d21 - d01[sel] * d20) / dd, -1.0)
            plane = np.abs((ap * n[None]).sum(2)) / np.where(nl > 0, nl, 1.0)
        inside = (v >= 0) & (w >= 0) & (v + w <= 1) & ok
        best = np.where(inside, plane, np.inf)
        for p0, e in ((a, ab), (a, ac), (a + ab, ac - ab)):
            ee = (e * e).sum(1)
            rel = p[:, None, :] - p0[None]
            with np.errstate(divide="ignore", invalid="ignore"):
                t = np.clip(np.where(ee > 0, (rel * e[None]).sum(2) / ee, 0.0), 0.0, 1.0)
            dvec = rel - t[..., None] * e[None]
            best = np.minimum(best, np.sqrt((dvec * dvec).sum(2)))
        m = best.min(axis=1)
        if limit is not None:
            m = np.where(m <= pad, m, np.inf)
        out[idx] = m
    return out


_PREP = {}                  # (id(T), kind) -> (T kept alive, data)


def _prepared(T, kind, make):
    """make(), the per-triangle arrays a probe derives from T, kept per
    triangle array (R129: the board solid's 16 069 triangles were rotated
    into each ray's frame again for every module tested against it). The
    entry holds T, so its id cannot be reused while the entry lives."""
    k = (id(T), kind)
    hit = _PREP.get(k)
    if hit is not None and hit[0] is T:
        return hit[1]
    val = make()
    if len(_PREP) >= 32:
        _PREP.clear()
    _PREP[k] = (T, val)
    return val


def _cell_order(Q, chunk):
    """An order of the points Q (n,2) or (n,3) in which each run of `chunk`
    points lies in one small 2D cell (of the two coordinates the points
    spread most along, for 3D points), so a chunk's box
    meets few triangles. R129: a strip sorted on x alone spans the whole
    part in y - MEASURED on the board-mesh solid (16 069 triangles), the
    board's own 1 638 points against it took 0.39 s that way."""
    import numpy as np
    n = len(Q)
    if n <= chunk:
        return np.arange(n)
    q = np.asarray(Q)
    span = np.ptp(q, axis=0)
    if q.shape[1] > 2:                  # the two axes the points spread along
        keep = np.argsort(-span)[:2]
        q, span = q[:, keep], span[keep]
    cell = max(float(span.max()) / max(1.0, (n / float(chunk)) ** 0.5), 1e-6)
    return np.lexsort((q[:, 1], q[:, 0], np.floor(q[:, 1] / cell),
                       np.floor(q[:, 0] / cell)))


_RAYS = ((0.1234, 0.2718, 1.0), (-0.3141, 0.1577, 1.0), (0.2071, -0.3893, -1.0))


def _basis(d):
    import numpy as np
    d = np.array(d, dtype=float)
    d /= np.linalg.norm(d)
    a = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    return np.stack([u, np.cross(d, u), d])


def _parity_inside(Q, T, chunk=32):
    """Bool (n,): point inside the closed triangle surface T, by the
    majority of three skew rays' crossing parity (a ray grazing an edge
    can miscount; three independent ones out-vote it)."""
    import numpy as np
    votes = np.zeros(len(Q), dtype=int)
    if not len(Q) or not len(T):
        return votes > 0
    for d in _RAYS:
        Bm = _basis(d)
        q = Q @ Bm.T

        def prep():
            t = T @ Bm.T
            a = t[:, 0]
            e1, e2 = t[:, 1] - a, t[:, 2] - a
            det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
            ok = np.abs(det) > 1e-12
            t = t[ok]
            return a[ok], e1[ok], e2[ok], det[ok], t.min(axis=1), t.max(axis=1)
        a, e1, e2, det, lo, hi = _prepared(T, ("parity", d), prep)
        order = _cell_order(q[:, :2], chunk)
        for s in range(0, len(q), chunk):
            idx = order[s:s + chunk]
            c = q[idx]
            sel = ((hi[:, 0] >= c[:, 0].min()) & (lo[:, 0] <= c[:, 0].max())
                   & (hi[:, 1] >= c[:, 1].min()) & (lo[:, 1] <= c[:, 1].max())
                   & (hi[:, 2] > c[:, 2].min()))
            if not sel.any():
                continue
            A, E1, E2, D = a[sel], e1[sel], e2[sel], det[sel]
            wx = c[:, 0, None] - A[None, :, 0]
            wy = c[:, 1, None] - A[None, :, 1]
            u = (wx * E2[None, :, 1] - wy * E2[None, :, 0]) / D
            v = (E1[None, :, 0] * wy - E1[None, :, 1] * wx) / D
            z = A[None, :, 2] + u * E1[None, :, 2] + v * E2[None, :, 2]
            hit = (u >= 0) & (v >= 0) & (u + v <= 1) & (z > c[:, 2, None])
            votes[idx] += hit.sum(axis=1) % 2
    return votes >= 2


def points_inside(shape, pts, tol=0.01):
    """Bool list: each point (Vector or (x, y, z)) strictly inside `shape`
    by more than `tol` (points on the surface are not inside - the same
    meaning as shape.isInside(p, tol, False)). Exact OCCT query on a light
    shape; ray parity on the tessellation of a heavy one (R129)."""
    import FreeCAD as App
    vecs = [p if isinstance(p, App.Vector) else App.Vector(*p) for p in pts]
    if not vecs:
        return []
    bb = _bound(shape)

    def exact(v):
        try:
            return bool(bb.isInside(v) and shape.isInside(v, tol, False))
        except Exception:                               # noqa: BLE001
            return False
    is_heavy = heavy(shape)
    if not is_heavy and (len(vecs) < EXACT_POINTS or tess_slow(shape)):
        return [exact(v) for v in vecs]
    import numpy as np
    Q = np.array([(v.x, v.y, v.z) for v in vecs], dtype=float)
    res = np.zeros(len(Q), dtype=bool)
    box = np.array([bb.XMin, bb.YMin, bb.ZMin]), np.array([bb.XMax, bb.YMax, bb.ZMax])
    cand = np.nonzero(np.all((Q >= box[0]) & (Q <= box[1]), axis=1))[0]
    if not len(cand):
        return res.tolist()
    _P, T = _tess(shape)
    ins = _parity_inside(Q[cand], T)
    if is_heavy:
        # tessellated surface = the shape (planar mesh faces); a point on
        # it, within tol, is not inside
        idx = cand[ins]
        if len(idx):
            res[idx[_pt_tri_dist(Q[idx], T, limit=tol) > tol]] = True
        return res.tolist()
    # light, many points: parity decides where the tessellation cannot be
    # wrong (farther from it than twice its deflection + tol); OCCT's exact
    # query decides every point nearer the surface
    near = 2.0 * _deflection(shape) + tol
    d = _pt_tri_dist(Q[cand], T, limit=near)
    sure = d > near
    res[cand[sure & ins]] = True
    for k in cand[~sure]:
        res[k] = exact(vecs[k])
    return res.tolist()


def _loop_heavy(shape):
    """True when OCCT's distToShape on `shape` can take seconds: a face with
    more than DIST_LOOPS_MAX boundary loops (see there)."""
    try:
        return busiest_face_loops(shape) > DIST_LOOPS_MAX
    except Exception:                                   # noqa: BLE001
        return False


def _contact(a, b):
    """(d, exact) for a pair where distToShape is too slow (R129): (0.0,
    True) when they touch or intersect (section() finds a shared point, or
    a vertex of one lies inside the other); (None, True) when they are
    certainly apart, by a gap not measured; (None, False) when it could not
    be told. section() on the 400-hole plate under a lid
    lying on it: 0.14 s where distToShape took 27 s."""
    try:
        sec = a.section(b)
        if sec.Vertexes or sec.Edges:
            return 0.0, True
        for s, o in ((a, b), (b, a)):
            vs = s.Vertexes
            if vs and o.Solids and points_inside(o, [vs[0].Point], 1e-6)[0]:
                return 0.0, True        # one inside the other, no contact
    except Exception:                                   # noqa: BLE001
        return None, False
    return None, True


def distance(a, b, limit=None):
    """(d, exact): the gap between two shapes. Exact (distToShape) when both
    are light; for a heavy one the smallest sampled surface-point-to-
    triangle distance, an UPPER bound, exact=False (R129). With `limit`,
    d is inf when nothing was sampled within `limit` of the other body.
    A light shape with a face of many loops (a perforated plate) is judged
    by contact only (_contact): d is 0.0 or None - apart by a gap not
    measured (R129: distToShape took 3.5 s to 537 s on one)."""
    if not heavy(a) and not heavy(b):
        if _loop_heavy(a) or _loop_heavy(b):
            return _contact(a, b)
        return a.distToShape(b)[0], True
    import numpy as np
    pad = np.inf if limit is None else float(limit)
    best = np.inf
    for s, o in ((a, b), (b, a)):
        P = _samples(s)
        try:
            _Po, To = _tess(o)
        except SlowToTessellate:
            continue                    # the other direction still samples it
        if not len(P) or not len(To):
            continue
        if limit is not None:
            lo, hi = _box_of(To.reshape(-1, 3), pad)
            P = P[np.all((P >= lo) & (P <= hi), axis=1)]
        if len(P):
            best = min(best, float(_pt_tri_dist(P, To, limit).min()))
    return best, False


def touching(a, b):
    """True / False / None (cannot tell) - do two solids touch? Exact for
    light shapes; for a heavy pair sampled: <= TOUCH_MM touches, >
    FRAG_APART_MM apart, in between None."""
    try:
        d, exact = distance(a, b, limit=FRAG_APART_MM + 1.0)
    except Exception:                                   # noqa: BLE001
        return None
    if d is None:
        # R129: judged by contact only - no shared point, no vertex inside:
        # apart (section() is exact about contact); unknown when it failed
        return False if exact else None
    if exact:
        return d <= 1e-6
    if d <= TOUCH_MM:
        return True
    # interpenetrating bodies: a sample of one inside the other is contact
    # (edge samples 0.5 mm apart can all sit a little off the other surface)
    try:
        for s, o in ((a, b), (b, a)):
            P = _samples(s)
            if any(points_inside(o, P[::max(1, len(P) // 400)], TOUCH_MM)):
                return True
    except Exception:                                   # noqa: BLE001
        return None
    return False if d > FRAG_APART_MM else None


# -------------------------------------------------------------- fragments
def fragments(shape, ratio=FRAGMENT_RATIO, max_solids=20):
    """A body whose smallest solid is DISJOINT from the rest and smaller than
    `ratio` x the largest: almost always a failed fuse leaving a stray piece
    (PRD R80: 2 233 + 27 423 mm3 shown as one part). A pair of equal
    headlights passes. Returns None, or a dict with the numbers."""
    try:
        solids = list(shape.Solids)
    except Exception:                                   # noqa: BLE001
        return None
    if len(solids) < 2 or len(solids) > max_solids:
        return None
    vols = [s.Volume for s in solids]
    big = max(vols)
    small_i = min(range(len(vols)), key=lambda i: vols[i])
    if big <= 0 or vols[small_i] >= ratio * big:
        return None
    small = solids[small_i]
    for j, other in enumerate(solids):
        if j == small_i:
            continue
        if _bb_gap(small.BoundBox, other.BoundBox) > 1e-6:
            continue
        t = touching(small, other)      # R129: no distToShape on a heavy solid
        if t is None or t:
            return None                 # touching (one part) or cannot tell:
                                        # do not accuse
    return {"smallest_mm3": round(vols[small_i], 3), "largest_mm3": round(big, 3),
            "solids": len(solids)}


# --------------------------------------------------------------- overlaps
def _norm_intended(intended):
    """INTENDED_OVERLAPS -> (set of single names, set of frozenset pairs).

    Accepted: ["Lid"] (Lid may overlap anything), [("Lid", "Box")], or a mix.
    Anything else is ignored rather than guessed at."""
    singles, pairs = set(), set()
    for e in intended or ():
        if isinstance(e, str):
            singles.add(e)
        elif isinstance(e, (list, tuple)) and len(e) == 2 \
                and all(isinstance(x, str) for x in e):
            pairs.add(frozenset(e))
    return singles, pairs


def sanitize_intended(value):
    """Keep only the JSON-safe accepted forms (strings, 2-string lists)."""
    out = []
    for e in value or ():
        if isinstance(e, str):
            out.append(e)
        elif isinstance(e, (list, tuple)) and len(e) == 2 \
                and all(isinstance(x, str) for x in e):
            out.append([e[0], e[1]])
    return out


def _allowed(a, b, singles, pairs):
    ka, kb = {a["name"], a["label"]}, {b["name"], b["label"]}
    if ka & singles or kb & singles:
        return True
    return any(frozenset((x, y)) in pairs for x in ka for y in kb)


def declared(a, b, intended):
    """True when INTENDED_OVERLAPS names the pair a, b (or either alone), by
    name or label - the matching overlaps() uses. R156: for a pair with the
    USER's object this only labels the hit; it never silences it."""
    singles, pairs = _norm_intended(intended)
    return _allowed(a, b, singles, pairs)


def _mesh_points_inside(mesh, placement, solid, limit=MESH_SAMPLES):
    """How many of a mesh's vertices lie strictly inside `solid`.
    Meshes have no boolean volume with a B-rep, so this is a count of
    sampled points, reported as such - never dressed up as a volume.
    R214: only the vertices inside the solid's tight box are sampled - the
    cap of `limit` used to stride over ALL of the board's 28 034 vertices
    (every 19th), so the few under a cap's hook were skipped."""
    import FreeCAD as App
    pts = mesh.Points
    n = len(pts)
    if n == 0:
        return 0, 0
    bb = tight(solid)
    tol = 0.01
    vecs = []
    for p in pts:
        v = App.Vector(p.x, p.y, p.z)
        if placement is not None:
            v = placement.multVec(v)
        if (bb.XMin - tol <= v.x <= bb.XMax + tol and bb.YMin - tol <= v.y <= bb.YMax + tol
                and bb.ZMin - tol <= v.z <= bb.ZMax + tol):
            vecs.append(v)
    if not vecs:
        return 0, 0
    step = max(1, -(-len(vecs) // limit))  # at most `limit` points
    vecs = vecs[::step]
    return sum(points_inside(solid, vecs, 0.01)), len(vecs)


_MESH_T = {}                # id(mesh) -> (mesh kept alive, triangles (m,3,3))


def _mesh_triangles(mesh):
    """(m,3,3) numpy triangles of a world-placed Mesh.Mesh, cached per mesh
    object (the board's 55 472 facets are read once per process)."""
    import numpy as np
    k = id(mesh)
    hit = _MESH_T.get(k)
    if hit is not None and hit[0] is mesh:
        return hit[1]
    pts, facets = mesh.Topology
    P = np.array([(p.x, p.y, p.z) for p in pts], dtype=float).reshape(-1, 3)
    F = np.array(facets, dtype=int).reshape(-1, 3)
    T = P[F] if len(F) and len(P) else np.zeros((0, 3, 3))
    if len(_MESH_T) >= 16:
        _MESH_T.clear()
    _MESH_T[k] = (mesh, T)
    return T


def _solid_in_mesh(solid, mesh, limit=MESH_SAMPLES, tol=TOUCH_MM):
    """(inside, tested, at): surface samples of `solid` (tessellation vertices
    and points every 0.5 mm along its edges) that lie inside the closed
    mesh surface by more than `tol` - ray parity, three skew rays, as for
    a heavy solid (R129). R214: the other direction of _mesh_points_inside.
    A cap's hook running into the board's edge holds no board vertex (the
    board is a few big facets there), but its own edges run through the
    board: D80 End_Cap_L, 26.5 mm3 into the board, was reported clean.
    Only samples inside the mesh's box are tested. A count, never a volume;
    `at` is the mean of the samples found inside (None when none)."""
    import numpy as np
    P = _samples(solid)
    if not len(P):
        return 0, 0, None
    mb = mesh.BoundBox
    lo = np.array([mb.XMin, mb.YMin, mb.ZMin]) + tol
    hi = np.array([mb.XMax, mb.YMax, mb.ZMax]) - tol
    P = P[np.all((P > lo) & (P < hi), axis=1)]
    if not len(P):
        return 0, 0, None
    P = P[::max(1, -(-len(P) // limit))]
    T = _mesh_triangles(mesh)
    if not len(T):
        return 0, 0, None
    ins = _parity_inside(P, T)
    idx = np.nonzero(ins)[0]
    if not len(idx):
        return 0, len(P), None
    idx = idx[_pt_tri_dist(P[idx], T, limit=tol) > tol]
    if not len(idx):
        return 0, len(P), None
    return int(len(idx)), len(P), [round(float(c), 1) for c in P[idx].mean(axis=0)]


def overlaps(items, intended=(), min_volume=MIN_OVERLAP_MM3,
             cap=MAX_PAIRS_OBJECTS):
    """Pairwise intersections between bodies.

    items: dicts {"name", "label", "shape" (Part.Shape) or "mesh" (Mesh.Mesh,
    already in world coordinates) , "role" (AtechRole or None)}.
    Two Atech parts (board, modules) are never compared with each other:
    atech_ports.check owns that. Returns (list of hits, note or None).
    A hit is {"a", "b", "volume_mm3"} or {"a", "b", "mesh_points_inside",
    "mesh_points_tested"} (a mesh, or a heavy shape judged on sampled
    surface points - R129: one boolean with the board solid costs 1-1.6 s).
    Boxes are the TIGHT ones: a loose BoundBox sent bodies 0.3 mm apart
    into a boolean."""
    singles, pairs = _norm_intended(intended)
    note = None
    if len(items) > cap:
        note = "overlap check limited to the first %d of %d bodies" % (cap, len(items))
        items = items[:cap]
    boxes = {}

    def box(it):
        k = id(it)
        if k not in boxes:
            boxes[k] = tight(it["shape"]) if it.get("shape") is not None \
                else it["mesh"].BoundBox
        return boxes[k]
    hits = []
    for i in range(len(items)):
        a = items[i]
        for j in range(i + 1, len(items)):
            b = items[j]
            if a.get("role") and b.get("role"):
                continue
            if _allowed(a, b, singles, pairs):
                continue
            try:
                ba, bb = box(a), box(b)
            except Exception:                           # noqa: BLE001
                continue
            if not ba.intersect(bb):
                continue
            try:
                if a.get("shape") is not None and b.get("shape") is not None:
                    if not a["shape"].Solids or not b["shape"].Solids:
                        continue
                    if heavy(a["shape"]) or heavy(b["shape"]):
                        n_in, n_t = _shape_points_inside(a["shape"], b["shape"])
                        if n_in:
                            hits.append({"a": a["label"], "b": b["label"],
                                         "mesh_points_inside": n_in,
                                         "mesh_points_tested": n_t})
                        continue
                    v = a["shape"].common(b["shape"]).Volume
                    if v > min_volume:
                        hits.append({"a": a["label"], "b": b["label"],
                                     "volume_mm3": round(v, 3)})
                elif a.get("shape") is not None or b.get("shape") is not None:
                    solid, mesh_item = (a, b) if a.get("shape") is not None else (b, a)
                    if not solid["shape"].Solids:
                        continue
                    n_in, n_t = _mesh_points_inside(
                        mesh_item["mesh"], None, solid["shape"],
                        _sample_cap(solid["shape"]))
                    at = None
                    if not n_in:
                        # R214: the solid's own surface inside the mesh
                        n2, t2, at = _solid_in_mesh(
                            solid["shape"], mesh_item["mesh"],
                            HEAVY_SAMPLES if heavy(solid["shape"]) else MESH_SAMPLES)
                        n_in, n_t = n2, n_t + t2
                    if n_in:
                        hits.append({"a": a["label"], "b": b["label"],
                                     "mesh_points_inside": n_in,
                                     "mesh_points_tested": n_t})
                        if at is not None:
                            hits[-1]["at"] = at
            except Exception:                           # noqa: BLE001
                continue
    return hits, note


def _sample_cap(solid):
    """How many points to test against `solid`: fewer on a heavy one (its
    tessellation already cost most of the budget), and few enough for
    OCCT's exact query on one too slow to tessellate (R129)."""
    if heavy(solid):
        return HEAVY_SAMPLES
    if tess_slow(solid):
        return EXACT_POINTS - 1
    return MESH_SAMPLES


def _shape_points_inside(a, b, limit=HEAVY_SAMPLES):
    """(inside, tested): surface samples of each shape strictly inside the
    other, only those in the other's box. For a pair with a heavy shape,
    where one boolean costs over a second (R129). A count, never a volume."""
    import FreeCAD as App
    inside = tested = 0
    for s, o in ((a, b), (b, a)):
        P = _samples(s)
        bb = tight(o)
        P = [p for p in P if bb.isInside(App.Vector(*p))]
        if not P:
            continue
        cap = min(limit, _sample_cap(o))
        P = P[::max(1, -(-len(P) // cap))]
        tested += len(P)
        inside += sum(points_inside(o, P, 0.01))
    return inside, tested


def overlap_text(hit):
    if "volume_mm3" in hit:
        return "%s and %s overlap by %s mm3" % (hit["a"], hit["b"], hit["volume_mm3"])
    return "%s and %s intersect (%d of %d sampled mesh points inside%s)" % (
        hit["a"], hit["b"], hit["mesh_points_inside"], hit["mesh_points_tested"],
        "; around (%s)" % ", ".join("%.1f" % c for c in hit["at"])
        if hit.get("at") else "")


# --------------------------------------------------------------- floating
def floating(items, gap=FLOAT_GAP_MM, cap=MAX_PAIRS_OBJECTS):
    """Bodies farther than `gap` from every other body. Only meaningful for
    something meant to be one assembly (a desk stand 30 mm below the desk);
    separate parts laid out apart are legitimately 'floating', so this is a
    warning, never a failure. Returns [{"label", "gap_mm", "exact"}]:
    exact=False means gap_mm is a lower bound (boxes apart). A distance to
    a heavy shape is sampled (R129), an upper bound: it can clear a body
    of floating, never accuse it."""
    items = [it for it in items[:cap] if it.get("shape") is not None]
    if len(items) < 2:
        return []
    boxes = [tight(it["shape"]) for it in items]
    out = []
    for i, a in enumerate(items):
        best, exact = None, True
        cands = []
        for j, b in enumerate(items):
            if i == j:
                continue
            cands.append((_bb_gap(boxes[i], boxes[j]), j))
        cands.sort(key=lambda t: t[0])
        for g, j in cands:
            if g > gap:
                if best is None:
                    best, exact = g, False      # a lower bound: boxes are apart
                break
            try:
                d, ex = distance(a["shape"], items[j]["shape"], limit=gap)
            except Exception:                           # noqa: BLE001
                best = None
                break
            if d is None:
                # judged by contact only (R129): apart by a gap not
                # measured - it may be under `gap`, so never accuse
                best = None
                break
            if not ex and d > gap:
                # a sampled distance is an upper bound: cannot say it floats
                best = None
                break
            best = d if best is None else min(best, d)
            if best <= gap:
                break
        if best is not None and best > gap:
            out.append({"label": a["label"], "gap_mm": round(best, 2), "exact": exact})
    return out


# ------------------------------------------------------------------ holes
# A blind bore at least this x the part's width across its axis is a cavity
# (MEASURED: a mug 77/85 = 0.91, a planter 80/100 = 0.80), not a hole. At
# 0.5 a Ø3.2 blind screw hole in a Ø6 standoff (0.53) was dropped as a
# "cavity" and a correct part failed its intent (review round 3).
CAVITY_RATIO = 0.7


# R170 (D67): a round channel open along its whole length through a slot
# narrower than its diameter (a push-in cable channel: Ø6 behind a 4.5 mm
# slot is 263 deg of arc) is a CHANNEL, not a hole and not nothing. At least
# this much arc - an obround slot's round end is exactly 180 deg, a fillet 90.
SLOT_ARC_DEG = 200.0


# R183 (D67 jar): a bore at least CAVITY_RATIO of the part's width AT ITS
# OWN HEIGHT that opens into an enclosed space (material further along its
# axis - the floor of the jar below its mouth) is a container's MOUTH, not
# a hole: the jar's Ø47.6 mouth over its Ø56 body cavity was "1 hole". Only
# bores at least MOUTH_PREFILTER of the whole part's width are probed (one
# boolean each), at most MOUTH_PROBES per shape.
MOUTH_PREFILTER = 0.2
MOUTH_PROBES = 16
# R189 (R183 review): how wide a mouth is against the part AT ITS HEIGHT.
# A jar's neck is a thin ring round its mouth (the R183 jar: Ø47.6 in a
# Ø51.6 neck, 0.92); a speaker hole in a closed box's face is a hole with a
# wide plate round it (Ø50 in an 80 x 70 face, 0.71 - over CAVITY_RATIO, so
# it was counted as a mouth and a box with "1 hole" measured 0). Decided: a
# mouth needs at least this share - the ring round it no wider than about
# a tenth of the mouth each side. Whatever the ratio, a bore of the exact
# d_mm intent.json names still counts as that hole (intent_problems).
MOUTH_RATIO = 0.8
BORE_FACES_MAX = 3000       # wall_crossings: more faces than this - not probed


def _bore_groups(shape):
    """Concave cylindrical faces grouped by (radius, axis line): {key:
    {"faces": [(t_lo, t_hi, arc)], "ax", "foot", "k"}} (see bores())."""
    import FreeCAD as App
    import Part
    groups = {}
    if heavy(shape):
        # a mesh-derived solid is all small planar faces: no cylinder to
        # find, and walking its 16 069 faces cost 0.36 s (R129)
        return groups
    for f in shape.Faces:
        s = f.Surface
        if not isinstance(s, Part.Cylinder):
            continue
        try:
            u0, u1, v0, v1 = f.ParameterRange
            um, vm = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
            p = f.valueAt(um, vm)
            n = f.normalAt(um, vm)
            ax = App.Vector(s.Axis)
            ax.normalize()
            c = App.Vector(s.Center)
            d = p - c
            radial = d - ax * d.dot(ax)
            if radial.Length < 1e-9 or n.dot(radial) >= 0:
                continue
            comps = [ax.x, ax.y, ax.z]
            k = max(range(3), key=lambda i: abs(comps[i]))
            if comps[k] < 0:
                ax = ax * -1
            foot = c - ax * c.dot(ax)
            key = (round(s.Radius, 2), round(ax.x, 3), round(ax.y, 3), round(ax.z, 3),
                   round(foot.x, 1), round(foot.y, 1), round(foot.z, 1))
            g = groups.setdefault(key, {"faces": [], "ax": ax, "foot": foot, "k": k})
            ta, tb = f.valueAt(um, v0).dot(ax), f.valueAt(um, v1).dot(ax)
            g["faces"].append((min(ta, tb), max(ta, tb), abs(u1 - u0)))
        except Exception:                               # noqa: BLE001
            continue
    return groups


def _found(shape, groups):
    """[(key, bore)] - each group split into bores along its axis; a bore
    keeps the wall runs it crosses ("walls": [(t_lo, t_hi)])."""
    found = []
    for key, g0 in groups.items():
        for bore in _join_across_air(shape, g0, _runs(g0["faces"])):
            walls = [(min(x[0] for x in run), max(x[1] for x in run)) for run in bore]
            flat = [f for run in bore for f in run]
            # the arc of its fullest wall: a hole through a front wall that
            # also grazes a rib behind it is still a full hole
            arc = max(sum(a for _lo, _hi, a in run) for run in bore)
            found.append((key, {"arc": arc,
                                "t": [x for lo, hi, _a in flat for x in (lo, hi)],
                                "walls": walls, "ax": g0["ax"], "foot": g0["foot"],
                                "k": g0["k"]}))
    return found


def _axis_name(ax):
    """'X' / 'Y' / 'Z' for an axis-aligned direction, else None."""
    comps = (ax.x, ax.y, ax.z)
    k = max(range(3), key=lambda i: abs(comps[i]))
    return "XYZ"[k] if abs(abs(comps[k]) - 1.0) < 1e-6 else None


def _is_mouth(shape, g, dia, lo, hi, size):
    """R183: the bore (t lo..hi on its axis) opens into an enclosed space -
    material lies further along the axis beyond one of its ends (a jar's
    mouth over its body, its floor below) - and is at least MOUTH_RATIO of
    the part's width across its axis AT THAT HEIGHT (R189: a thin neck, not
    a hole in a wide face). Axis-aligned bores
    only; False when it cannot be told. The cheap test first: a bore that
    runs from one face of the part to the other (a gear's bore) has
    nothing beyond it and costs no boolean."""
    import FreeCAD as App
    import Part
    name = _axis_name(g["ax"])
    if name is None or hi - lo <= 1e-6:
        return False
    k = "XYZ".index(name)
    bb = tight(shape)
    full = (bb.XMin, bb.YMin, bb.ZMin)[k], (bb.XMax, bb.YMax, bb.ZMax)[k]
    try:
        r = 0.25 * dia
        beyond = False
        for t0, t1 in ((full[0], lo - 0.05), (hi + 0.05, full[1])):
            if t1 - t0 <= 0.05:
                continue                # the bore reaches the part's face
            probe = Part.makeCylinder(r, t1 - t0, g["foot"] + g["ax"] * t0, g["ax"])
            if shape.common(probe).Volume > 1e-3:
                beyond = True
                break
        if not beyond:
            return False
        # the part's width round the bore: thin slices at a quarter, half
        # and three quarters of its length, the narrowest one (R189: a
        # jar's neck bore runs down past its shoulder, where the body is
        # wider - the neck itself is what rings the mouth)
        widths = []
        th = max(0.05, min(0.5, 0.1 * (hi - lo)))
        for f in (0.25, 0.5, 0.75):
            lo_v = [bb.XMin - 1.0, bb.YMin - 1.0, bb.ZMin - 1.0]
            ext = [bb.XLength + 2.0, bb.YLength + 2.0, bb.ZLength + 2.0]
            lo_v[k], ext[k] = lo + f * (hi - lo) - th / 2.0, th
            sl = shape.common(Part.makeBox(ext[0], ext[1], ext[2], App.Vector(*lo_v)))
            if not sl.Solids:
                continue
            sb = tight(sl)
            widths.append(min((sb.XLength, sb.YLength, sb.ZLength)[i]
                              for i in range(3) if i != k))
        if not widths:
            return False
        return dia >= MOUTH_RATIO * min(widths)
    except Exception:                                   # noqa: BLE001
        return False


def bores(shape, min_arc_deg=330.0, slots=False):
    """Every full concave cylinder of `shape` (drilled holes, bores, round
    pockets): [{"d_mm", "blind", "cavity", "mouth", "walls", "axis",
    "wall_spans"}], sorted by diameter.
    slots=True also returns the round channels open along their length
    (SLOT_ARC_DEG .. min_arc_deg of arc, R170) as {"d_mm", "slot": True,
    "arc_deg", "blind": False, "cavity": False}.

    A cylindrical face is concave when its normal points toward the axis.
    Faces are grouped by (axis line, radius); OCCT often splits one hole into
    two 180 deg faces, so a group whose arcs sum to >= min_arc_deg counts.
    blind: there is material on the axis just past one end of the bore.
    cavity: blind AND at least CAVITY_RATIO of the part's width across the
    axis - the inside of a mug or a cup, not a hole (PRD S30) - or a
    container's mouth (mouth: True, R183: at least MOUTH_RATIO of the
    part's width at its own height, opening into an enclosed space).
    walls: how many walls the bore crosses - a hole drilled through the
    front AND back wall of a hollow case is ONE bore (coaxial runs across
    air stay one) crossing 2 walls (R181); wall_spans gives each wall's
    extent along the axis (mm, on the X / Y / Z named in "axis", or on the
    axis direction when it is not one of those).
    (Same grouping as tests/eval/fc_build.py, written again: this module
    ships to users and must not import from tests.)"""
    import math
    groups = _bore_groups(shape)
    try:
        size = dims(shape)
    except Exception:                                   # noqa: BLE001
        size = None
    out = []
    # One (axis, radius) group can hold SEVERAL bores: two blind bores of
    # one diameter drilled from both ends of a shaft coupler share the axis
    # and the radius (R114). Faces are split into runs along the axis -
    # faces whose spans overlap or touch are one bore (OCCT's two 180 deg
    # halves of one hole share a span). Runs separated by MATERIAL on the
    # axis are separate bores; runs separated by AIR (one hole drilled
    # through both walls of a hollow part, a pin through a clevis) stay one.
    probes = 0
    for key, g in _found(shape, groups):
        if g["arc"] < math.radians(min_arc_deg):
            if slots and g["arc"] >= math.radians(SLOT_ARC_DEG):
                out.append({"d_mm": round(2 * key[0], 2), "blind": False,
                            "cavity": False, "slot": True,
                            "arc_deg": round(math.degrees(g["arc"]), 1)})
            continue
        dia = round(2 * key[0], 2)
        blind = False
        lo, hi = min(g["t"]), max(g["t"])
        try:
            eps = max(0.05, 0.01 * dia)
            for t in (lo - eps, hi + eps):
                if points_inside(shape, [g["foot"] + g["ax"] * t], 1e-3)[0]:
                    blind = True
        except Exception:                               # noqa: BLE001
            blind = False
        cavity = mouth = False
        if size:
            across = [size[i] for i in range(3) if i != g["k"]]
            if blind:
                cavity = dia >= CAVITY_RATIO * min(across)
            elif dia >= MOUTH_PREFILTER * min(across) and probes < MOUTH_PROBES:
                probes += 1
                mouth = _is_mouth(shape, g, dia, lo, hi, size)
        out.append({"d_mm": dia, "blind": blind, "cavity": cavity or mouth,
                    "mouth": mouth, "walls": len(g["walls"]),
                    "axis": _axis_name(g["ax"]) or [round(c, 4) for c in g["ax"]],
                    "at": [round(c, 3) for c in g["foot"]],
                    "wall_spans": [[round(a, 3), round(b, 3)] for a, b in g["walls"]]})
    return sorted(out, key=lambda b: b["d_mm"])


# S62 (eval r9 cable_clip): an entry slot cut the full 6.4 mm bore width
# left an open U-trough - 180 deg of wrap, nothing retains the cable - and
# every check passed. ./check now prints each round channel's wrap, summed
# the way the benchmark sums it (tests/eval/fc_build.py _holes: concave
# cylinder faces grouped by radius and axis line, arcs added up). A pushed-
# in load is held from CHANNEL_HOLD_DEG (the benchmark's bores(>=240deg)).
CHANNEL_MIN_DEG = 120.0     # below: a fillet (90) or a shallow scallop
CHANNEL_HOLD_DEG = 240.0
CHANNEL_FULL_DEG = 330.0    # from here it is a bore (bores() min_arc_deg)
CHANNEL_WORDS = ("clip", "clamp", "holder", "hold", "cable", "wire", "cord",
                 "tube", "pipe", "hose", "rod", "pen", "grip", "snap", "cradle")


def channel_wraps(shape):
    """Round channels of `shape` that are not closed bores: concave
    cylinders wrapping CHANNEL_MIN_DEG .. CHANNEL_FULL_DEG about one axis
    line -> [{"d_mm", "wrap_deg", "axis", "at", "span"}], sorted by
    diameter. The two round ends of one obround slot (180 deg each, facing
    each other across the slot) are a slot, not channels, and are left out.
    Heavy (mesh-derived) shapes have no cylinders: []."""
    import math
    import FreeCAD as App
    import Part
    if heavy(shape):
        return []
    groups = {}
    for f in shape.Faces:
        s = f.Surface
        if not isinstance(s, Part.Cylinder):
            continue
        try:
            u0, u1, v0, v1 = f.ParameterRange
            um, vm = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
            p, n = f.valueAt(um, vm), f.normalAt(um, vm)
            ax = App.Vector(s.Axis)
            ax.normalize()
            c = App.Vector(s.Center)
            d = p - c
            radial = d - ax * d.dot(ax)
            if radial.Length < 1e-9 or n.dot(radial) >= 0:
                continue                                # convex
            comps = [ax.x, ax.y, ax.z]
            k = max(range(3), key=lambda i: abs(comps[i]))
            if comps[k] < 0:
                ax = ax * -1
            foot = c - ax * c.dot(ax)
            key = (round(s.Radius, 2), round(ax.x, 3), round(ax.y, 3), round(ax.z, 3),
                   round(foot.x, 1), round(foot.y, 1), round(foot.z, 1))
            arc = abs(u1 - u0)
            g = groups.setdefault(key, {"arc": 0.0, "mid": App.Vector(), "ax": ax,
                                        "foot": foot, "t": []})
            g["arc"] += arc
            r = App.Vector(radial)
            r.normalize()
            g["mid"] = g["mid"] + r * arc
            g["t"] += [f.valueAt(um, v).dot(ax) for v in (v0, v1)]
        except Exception:                               # noqa: BLE001
            continue
    lo, hi = math.radians(CHANNEL_MIN_DEG), math.radians(CHANNEL_FULL_DEG)
    cand = {k: g for k, g in groups.items() if lo <= g["arc"] < hi}
    slot_ends = set()
    for ka, a in cand.items():
        for kb, b in cand.items():
            if kb <= ka or ka[:4] != kb[:4]:
                continue
            if abs(a["arc"] - math.pi) > 0.05 or abs(b["arc"] - math.pi) > 0.05:
                continue
            off = b["foot"] - a["foot"]
            if off.Length < 1e-3 or a["mid"].Length < 1e-9 or b["mid"].Length < 1e-9:
                continue
            u = App.Vector(off)
            u.normalize()
            ma, mb = App.Vector(a["mid"]), App.Vector(b["mid"])
            ma.normalize()
            mb.normalize()
            if ma.dot(u) < -0.9 and mb.dot(u) > 0.9:
                slot_ends.update((ka, kb))              # a slot's two round ends
    out = []
    for key, g in cand.items():
        if key in slot_ends:
            continue
        out.append({"d_mm": round(2 * key[0], 2),
                    "wrap_deg": round(math.degrees(g["arc"]), 1),
                    "axis": _axis_name(g["ax"]) or [round(c, 4) for c in g["ax"]],
                    "at": [round(c, 3) + 0.0 for c in g["foot"]],
                    "span": [round(min(g["t"]), 3) + 0.0, round(max(g["t"]), 3) + 0.0]})
    return sorted(out, key=lambda c: (c["d_mm"], c["wrap_deg"]))


def channel_text(label, c):
    """The CHANNEL line for one channel."""
    ax = c["axis"] if isinstance(c["axis"], str) else "(%s)" % ", ".join(
        "%g" % v for v in c["axis"])
    return ("%s: a %g mm round channel along %s wraps %g deg (%s %g .. %g)" % (
        label, c["d_mm"], ax, c["wrap_deg"],
        ax.lower() if isinstance(c["axis"], str) else "t", c["span"][0], c["span"][1]))


def holds_something(request, labels):
    """True when the request or a part's label names a clip, holder, cable
    and the like - a part whose round channel must hold what goes in."""
    import re
    text = " ".join([request or ""] + list(labels or ())).lower()
    words = set(re.findall(r"[a-z]+", text.replace("_", " ")))
    return any(w in words or w + "s" in words for w in CHANNEL_WORDS)


def wall_crossings(shape, request=None):
    """R181 (D69): bores of `shape` that cross more than one wall - one
    hole drilled through the front wall AND the wall behind it (and so a
    count of 2 holes that is really 4 openings). [{"d_mm", "axis", "at",
    "wall_spans"}]; [] for a heavy (mesh-like) shape or one of more than
    BORE_FACES_MAX faces (not probed), and when the request itself asks for
    a hole through both walls ("through both walls", "all the way
    through"). Cheap: points_inside only between coaxial runs."""
    import re
    import math
    if request and re.search(r"\bboth (?:walls|sides|ends)\b|all the way through|"
                             r"right through|straight through|\bclevis\b",
                             str(request).lower()):
        return []
    try:
        if heavy(shape) or n_faces(shape) > BORE_FACES_MAX:
            return []
    except Exception:                                   # noqa: BLE001
        return []
    out = []
    groups = {k: g for k, g in _bore_groups(shape).items()
              if len(_runs(g["faces"])) > 1}
    for key, g in _found(shape, groups):
        if len(g["walls"]) < 2 or g["arc"] < math.radians(330.0):
            continue
        out.append({"d_mm": round(2 * key[0], 2),
                    "axis": _axis_name(g["ax"]) or [round(c, 4) for c in g["ax"]],
                    "at": [round(c, 3) for c in g["foot"]],
                    "wall_spans": [[round(a, 3), round(b, 3)] for a, b in g["walls"]]})
    return out


def wall_crossing_text(label, b):
    """One line for a bore crossing several walls, naming each wall (the
    one at the - end and the one at the + end of its axis)."""
    ax = b["axis"]
    if isinstance(ax, str):
        k = "XYZ".index(ax)
        where = ", ".join("%s %.2f" % ("xyz"[i], b["at"][i]) for i in range(3) if i != k)
        spans = b["wall_spans"]
        names = []
        for i, (lo, hi) in enumerate(spans):
            side = ("-%s wall" % ax if i == 0 else "+%s wall" % ax
                    if i == len(spans) - 1 else "inner wall")
            names.append("the %s (%s %.2f .. %.2f)" % (side, ax.lower(), lo, hi))
        return ("%s: the diameter %g mm hole along %s at (%s) goes through %d walls, "
                "%s: it opens every one of them. If only the wall you drilled into "
                "should be open, drill it with cad.hole(..., through=\"wall\") (it "
                "stops at the first wall); a hole meant to pass through them all is "
                "fine as it is" % (label, b["d_mm"], ax, where, len(spans),
                                   ", ".join(names[:-1]) + " and " + names[-1]))
    return ("%s: the diameter %g mm hole along %s goes through %d walls (at %s along "
            "its axis). If only the wall you drilled into should be open, drill it "
            "with cad.hole(..., through=\"wall\")" % (
                label, b["d_mm"], ax, len(b["wall_spans"]),
                ", ".join("%.2f .. %.2f" % (lo, hi) for lo, hi in b["wall_spans"])))


def _join_across_air(shape, g, runs):
    """Group consecutive runs whose gap is air on the axis (see bores()):
    [[run, run, ...], ...] - one list per bore, one run per wall it
    crosses."""
    out = []
    for run in runs:
        if out:
            a = max(hi for _lo, hi, _x in out[-1][-1])
            b = min(lo for lo, _hi, _x in run)
            try:
                solid_between = points_inside(
                    shape, [g["foot"] + g["ax"] * (0.5 * (a + b))], 1e-3)[0]
            except Exception:                           # noqa: BLE001
                solid_between = False
            if not solid_between:
                out[-1].append(list(run))
                continue
        out.append([list(run)])
    return out


def _runs(faces, gap=1e-3):
    """[(lo, hi, arc), ...] -> lists of faces whose axial spans overlap or
    touch (within `gap` mm): one list per separate bore along the axis."""
    runs = []
    for lo, hi, arc in sorted(faces):
        if runs and lo <= runs[-1][0] + gap:
            runs[-1][0] = max(runs[-1][0], hi)
            runs[-1][1].append((lo, hi, arc))
        else:
            runs.append([hi, [(lo, hi, arc)]])
    return [r[1] for r in runs]


def holes(shape, min_arc_deg=330.0):
    """Diameters of the holes and bores of `shape`, sorted - every full
    concave cylinder except blind cavities (see bores())."""
    return [b["d_mm"] for b in bores(shape, min_arc_deg) if not b["cavity"]]


def cavities(shape, min_arc_deg=330.0):
    """Diameters of blind round cavities (a mug's inside), sorted."""
    return [b["d_mm"] for b in bores(shape, min_arc_deg) if b["cavity"]]


# ----------------------------------------------------------------- intent
INTENT = "intent.json"
# R170: the line after an intent miss - the SAME words as Studio's own
# fix message (build.INTENT_FIX_RULE, compared by a test), so ./check and
# Studio word one miss the same way. It asks which side is wrong; it never
# orders the geometry to bend to a count the measurement cannot see.
INTENT_RULE = (
    "For each intent miss above, decide which side is wrong. If the part does "
    "not yet do what the user asked, change model.py. If it does and the "
    "measurement cannot see the feature (a slot or a channel open along its "
    "length is not counted as a hole), do not add, close or reshape anything "
    "to satisfy the count: keep the design and say in your reply what was "
    "measured - and never edit intent.json to match a measurement. The user's "
    "message wins over intent.json: where they disagree, set intent.json to "
    "the user's value")


def read_intent(workspace):
    """(intent dict or None, [problems]) for <workspace>/intent.json. A
    symbolic link is refused (Studio reads it unsandboxed)."""
    import json
    import os
    path = os.path.join(workspace or "", INTENT)
    if not workspace or not os.path.lexists(path):
        return None, []
    if os.path.islink(path) or not os.path.isfile(path):
        return None, ["%s must be a regular file" % INTENT]
    try:
        with open(path, encoding="utf-8-sig") as fh:
            intent = json.load(fh)
        if not isinstance(intent, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        return None, ["%s is unreadable (%s): fix it or delete it" % (INTENT, exc)]
    return intent, []


INTENT_FIRST = ".intent_first.json"   # intent.json as this turn first saw it
INTENT_CHANGED = "INTENT CHANGED"


def _read_regular(path):
    """Bytes of a regular, non-link file; None when absent or not one."""
    import os
    if not os.path.isfile(path) or os.path.islink(path):
        return None
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _canon(data):
    """intent.json bytes -> a comparable form (key order and whitespace do
    not count; unparseable text compares as text)."""
    import json
    if data is None:
        return None
    try:
        return json.dumps(json.loads(data.decode("utf-8-sig")), sort_keys=True)
    except (ValueError, UnicodeDecodeError):
        return data.strip()


# R151 (D59, D57): the intent guard must never outrank the user. Studio
# says which kind of turn this is in TURN (start_turn, written read-only
# when the turn starts):
#   a USER turn   intent.json is the agent's to change (the user's message
#                 is the authority); ./check only refuses a model.py that
#                 writes intent.json itself while it runs (R135)
#   a FIX turn    Studio's own auto-fix message: intent.json is frozen as it
#                 stood when the fix turn started (S37) - except that a value
#                 the USER's message contains is always accepted
# No TURN file (a Studio from before R151): the old rule - frozen from the
# turn's first check - with the new wording.
TURN = ".atech_turn.json"


def read_turn(workspace):
    """The turn marker {"fix": bool, "request": str} or None (absent,
    unreadable, or not a regular file)."""
    import json
    import os
    if not workspace:
        return None
    data = _read_regular(os.path.join(workspace, TURN))
    if data is None:
        return None
    try:
        turn = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(turn, dict):
        return None
    return {"fix": bool(turn.get("fix")), "request": str(turn.get("request") or "")}


def start_turn(workspace, request, fix):
    """Studio, when a turn starts (build.prepare_workspace): write TURN.

    A USER turn (fix=False): request = the user's message; the intent record
    is dropped (the agent may change intent.json during the turn).
    A FIX turn (fix=True): the user's message of the turn it fixes is kept
    from the previous TURN (Studio's fix message is not the user's), and
    the record is taken NOW from intent.json - the target Studio judged the
    build by. Returns True when written. Never raises."""
    import json
    import os
    if not workspace or not os.path.isdir(workspace):
        return False
    if fix:
        old = read_turn(workspace)
        request = old["request"] if old else ""
    body = json.dumps({"fix": bool(fix), "request": str(request or "")},
                      ensure_ascii=False).encode("utf-8")
    try:
        for name in (TURN, INTENT_FIRST):
            p = os.path.join(workspace, name)
            if os.path.lexists(p):
                if os.path.isdir(p) and not os.path.islink(p):
                    import shutil
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.unlink(p)
        _write_record(os.path.join(workspace, TURN), body)
        if fix:
            cur = _read_regular(os.path.join(workspace, INTENT))
            if cur is not None:
                _write_record(os.path.join(workspace, INTENT_FIRST), cur)
    except OSError:
        return False
    return True


def request_numbers(text):
    """Every number the user's message gives, in mm as well as written:
    "80 x 50 x 30" -> 80, 50, 30; "2,5" -> 2.5 (and 2, 5); "3 cm" -> 3, 30;
    "2 in" / '2"' -> 2, 50.8."""
    import re
    out = []
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(cm|mm|in(?:ch(?:es)?)?\b|\")?",
                         str(text or "").lower()):
        raw, unit = m.group(1), m.group(2) or ""
        vals = [float(raw.replace(",", "."))]
        if "," in raw:
            vals += [float(x) for x in raw.split(",")]
        out.extend(vals)
        if unit == "cm":
            out.extend(v * 10.0 for v in vals)
        elif unit.startswith("in") or unit == '"':
            out.extend(v * 25.4 for v in vals)
    return out


def _leaves(obj, path=""):
    """{path: value} of a JSON value's leaves; a list of numbers is one leaf
    (compared as a multiset: size_mm [80, 50, 30] == [30, 80, 50] + order)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            out.update(_leaves(v, "%s/%s" % (path, k)))
        return out
    if isinstance(obj, list) and obj and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in obj):
        return {path: ("nums", sorted(float(x) for x in obj))}
    if isinstance(obj, list):
        out = {}
        for i, v in enumerate(obj):
            out.update(_leaves(v, "%s[%d]" % (path, i)))
        return out
    return {path: obj}


def _in_request(value, nums, text):
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return any(abs(float(value) - n) <= max(0.01, 1e-6 * abs(n)) for n in nums)
    if isinstance(value, str):
        return bool(value.strip()) and value.strip().lower() in str(text or "").lower()
    return False


def user_values_only(first, cur, request):
    """R151: True when every value intent.json changed from `first` to `cur`
    (bytes) is one the user's message gives - such an edit follows the user
    and is always accepted. A removed key, a changed flag or a value the
    message does not contain -> False. A new or changed tolerance_mm only
    when the message speaks of a tolerance."""
    import json
    import re
    try:
        a = _leaves(json.loads(first.decode("utf-8-sig")))
        b = _leaves(json.loads(cur.decode("utf-8-sig")))
    except (ValueError, UnicodeDecodeError, AttributeError):
        return False
    nums = request_numbers(request)
    if not nums and not str(request or "").strip():
        return False
    if set(a) - set(b):
        return False                    # a key was removed
    loose = re.search(r"toleran|\u00b1|\+/-|\+-", str(request or "").lower())
    for path, new in b.items():
        old = a.get(path)
        if old == new:
            continue
        if path.rsplit("/", 1)[-1] == "tolerance_mm" and not loose:
            # a looser tolerance is not a target the user gave, even when
            # its number is in the message (the size's 30 as +-30 mm)
            return False
        if isinstance(new, tuple) and new[0] == "nums":
            if isinstance(old, tuple) and len(new[1]) < len(old[1]):
                return False            # a target number was dropped
            rest = list(old[1]) if isinstance(old, tuple) else []
            added = []
            for x in new[1]:
                hit = next((i for i, y in enumerate(rest) if abs(x - y) <= 1e-9), None)
                if hit is None:
                    added.append(x)
                else:
                    rest.pop(hit)
            if not all(_in_request(x, nums, request) for x in added):
                return False
        elif not _in_request(new, nums, request):
            return False
    return True


def _shown(data):
    s = data.decode("utf-8", "replace").strip().replace("\n", " ")
    return s if len(s) <= 300 else s[:297] + "..."


def _replace_record(snap, data):
    import os
    try:
        if os.path.lexists(snap):
            os.unlink(snap)
        if data is not None:
            _write_record(snap, data)
    except OSError:
        pass


def intent_changed(workspace, record=False):
    """S37 / R151: may intent.json have moved? Returns None, or a problem
    line starting with INTENT CHANGED. Never raises.

    record=True is check.py (the agent's ./check and Studio's sandboxed
    build), called AFTER model.py ran - the record was taken just before
    (intent_record); record=False is Studio comparing after its build.
      USER turn  record=False: None (the agent may change intent.json in
                 its own turn). record=True: a difference means model.py
                 wrote intent.json while it ran - refused.
      FIX turn   frozen since the fix turn started; an edit whose changed
                 values all appear in the user's message is accepted (and
                 becomes the record).
      no TURN    the pre-R151 rule: frozen from the turn's first check."""
    import os
    if not workspace:
        return None
    snap = os.path.join(workspace, INTENT_FIRST)
    cur = _read_regular(os.path.join(workspace, INTENT))
    turn = read_turn(workspace)
    if turn is not None and not turn["fix"]:
        if not record:
            return None
        first = _read_regular(snap)
        if _canon(first) == _canon(cur):
            return None
        return ("%s: model.py %s intent.json while it ran. Write intent.json "
                "yourself (the user's message wins over it); model.py only "
                "builds the part" % (INTENT_CHANGED,
                                     "deleted" if cur is None else "wrote"))
    try:
        if not os.path.lexists(snap):
            if record and cur is not None:
                _write_record(snap, cur)
            return None
    except OSError:
        return None
    first = _read_regular(snap)
    if first is None or _canon(first) == _canon(cur):
        return None
    if turn is not None and cur is not None and user_values_only(
            first, cur, turn["request"]):
        if record:
            _replace_record(snap, cur)
        return None
    how = "was deleted" if cur is None else "was edited"
    if turn is not None:
        return ("%s: intent.json %s during Atelier's fix turn. A fix turn repairs "
                "model.py against the target the build was judged by (%s): put "
                "intent.json back to that. Only a value from the user's own "
                "message may replace it - the user's message wins over "
                "intent.json, and such values are accepted"
                % (INTENT_CHANGED, how, _shown(first)))
    return ("%s: intent.json %s since this turn's first check (it was: %s). If "
            "you changed it to match a measurement, put it back and change "
            "model.py. If the user's message asks for the new value, the user "
            "wins: keep it and tell the user this check could not confirm the "
            "change" % (INTENT_CHANGED, how, _shown(first)))


def _write_record(snap, data):
    """Create the record READ-ONLY (0444): the agent's Write/Edit tools
    cannot overwrite it (R135). Studio's new_turn still unlinks it - the
    folder is writable."""
    import os
    fd = os.open(snap, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o444)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def intent_record(workspace, record=True):
    """The turn's intent record (bytes) as it stands BEFORE model.py runs;
    with record=True the first check of a turn creates it here, so model.py
    cannot write intent.json or plant a record ahead of it. In a USER turn
    (R151) the record is re-taken at every check: it only has to catch
    model.py writing intent.json during this run. None when there is no
    intent.json yet."""
    import os
    if not workspace:
        return None
    snap = os.path.join(workspace, INTENT_FIRST)
    turn = read_turn(workspace)
    if record and turn is not None and not turn["fix"]:
        cur = _read_regular(os.path.join(workspace, INTENT))
        if _read_regular(snap) != cur or (cur is None and os.path.lexists(snap)):
            _replace_record(snap, cur)
        return _read_regular(snap)
    if record and not os.path.lexists(snap):
        cur = _read_regular(os.path.join(workspace, INTENT))
        if cur is not None:
            try:
                _write_record(snap, cur)
            except OSError:
                return None
    return _read_regular(snap)


def intent_guard(workspace, before):
    """R135: model.py runs with the workspace writable, so it could delete
    or rewrite the record (and the next check would record afresh). Given
    the record as it was before model.py ran, put it back if it moved and
    return an INTENT CHANGED problem; None when untouched. Never raises."""
    import os
    if not workspace:
        return None
    snap = os.path.join(workspace, INTENT_FIRST)
    now = _read_regular(snap)
    if before is None:
        # no record before the run: one there now was planted by model.py -
        # drop it, so the record is taken from intent.json itself
        try:
            if now is not None:
                os.unlink(snap)
        except OSError:
            pass
        return None
    if now == before:
        return None
    try:
        if os.path.lexists(snap):
            if os.path.isdir(snap) and not os.path.islink(snap):
                return ("%s: model.py replaced %s with a folder - remove it; "
                        "model.py must not touch the intent record" % (INTENT_CHANGED, INTENT_FIRST))
            os.unlink(snap)
        _write_record(snap, before)
    except OSError:
        pass
    return ("%s: model.py %s %s, this turn's record of intent.json (put back). "
            "model.py builds the part; it must not touch intent.json or its record"
            % (INTENT_CHANGED, "deleted" if now is None else "rewrote", INTENT_FIRST))


# R168 (D65): the size the user's message gives for the WHOLE product. A
# triple "80 x 50 x 30" is the product's outside size unless the words
# around it say it is something else's (a board it holds, a cavity, a
# window): then it is not an overall size and is not compared.
_TRIPLE = (r"(\d+(?:[.,]\d+)?)\s*(?:mm|cm)?\s*(?:x|×|\*|by)\s*"
           r"(\d+(?:[.,]\d+)?)\s*(?:mm|cm)?\s*(?:x|×|\*|by)\s*"
           r"(\d+(?:[.,]\d+)?)\s*(mm|cm|inch(?:es)?\b|in\b(?!\s+[a-z])|\")?")
# A bare "in" is inches only where no word follows it: "80 x 50 x 30 in PLA"
# is 30 mm in PLA, not 762 mm (adversarial review, round 7).
# A triple with no unit that counts things ("a 2 x 3 x 4 grid of cubes", a
# "4 x 4 x 2" brick in studs) is not a size in mm.
_COUNT_AFTER = r"^\s*(?:grid|array|matrix|pattern|stack|studs?\b|of\b|lego|blocks?\b|cubes?\b)"
_NOT_OVERALL = (r"\binside\b", r"\binner\b", r"\binternal", r"\binterior", r"cavity",
                r"pocket", r"compartment", r"opening", r"window", r"cut-?out",
                r"\bholes?\b", r"\bslots?\b", r"\bboard\b", r"\bpcb\b", r"(?<![-\w])fits?\b",
                r"\bto fit\b", r"\bholds?\b", r"\bfor (?:a|an|my|the)\b",
                r"battery", r"\bmodule", r"\bphone\b", r"\bscreen\b", r"\bdisplay\b",
                r"raspberry", r"\bpi\b", r"arduino", r"\besp32\b")
_OVERALL = (r"\boutside\b", r"\bouter\b", r"\boverall\b", r"\bexternal", r"\btotal\b",
            r"\boutline\b")


def request_size(request):
    """(sizes largest first, the words matched) when the user's message
    gives ONE overall size "A x B x C" (mm, cm or in); None when it gives
    none or several different ones. A triple the words around it tie to
    something else ("for a 85 x 56 x 20 board", "inside 80 x 50 x 30") is
    not an overall size and is skipped - unless "outside" / "overall" /
    "external" stand right next to it."""
    import re
    text = str(request or "")
    low = text.lower()
    found = []
    for m in re.finditer(_TRIPLE, low):
        unit = m.group(4) or ""
        scale = 10.0 if unit == "cm" else 25.4 if unit.startswith("in") or unit == '"' else 1.0
        if scale == 1.0 and re.search(r"\d\s*cm", m.group(0)):
            scale = 10.0
        vals = sorted((float(m.group(i).replace(",", ".")) * scale for i in (1, 2, 3)),
                      reverse=True)
        if not m.group(4) and not re.search(r"\d\s*(?:mm|cm)", m.group(0)) and \
                re.search(_COUNT_AFTER, low[m.end():m.end() + 20]):
            continue                    # a count of things, not a size
        near = low[max(0, m.start() - 40):m.end() + 30]
        close = low[max(0, m.start() - 15):m.end() + 20]
        if not any(re.search(p, close) for p in _OVERALL) and \
                any(re.search(p, near) for p in _NOT_OVERALL):
            continue                    # a size of something else: not judged
        if not any(all(abs(a - b) < 1e-6 for a, b in zip(vals, f[0])) for f in found):
            found.append((vals, text[m.start():m.end()].strip()))
    return found[0] if len(found) == 1 else None


def _size_misses(want, shapes, labels, tol, source, pairs=False):
    """Problem lines for the union tight box of `shapes` against `want`
    (three sizes, largest first), each naming the axis, where it runs and
    the part at each end (S52: one edit, not a fix/check/fix loop)."""
    import Part
    bb = tight(Part.makeCompound(shapes))
    lens = [round(bb.XLength, 3), round(bb.YLength, 3), round(bb.ZLength, 3)]
    lo = (bb.XMin, bb.YMin, bb.ZMin)
    hi = (bb.XMax, bb.YMax, bb.ZMax)
    axes = sorted(range(3), key=lambda i: -lens[i])
    pairing = ", ".join("%g -> %s" % (w, "XYZ"[k]) for w, k in zip(want, axes))
    boxes = None
    out = []
    for w, k in zip(want, axes):
        m = lens[k]
        t = tol if tol is not None else max(1.0, 0.02 * w)
        if abs(m - w) <= t:
            continue
        if boxes is None:
            boxes = []
            for s in shapes:
                try:
                    boxes.append(tight(s))
                except Exception:                       # noqa: BLE001
                    boxes.append(None)
        ends = ""
        if labels and len(labels) == len(shapes) and len(shapes) > 1:
            def at(end):
                val = (lo if end == "lo" else hi)[k]
                who = []
                for lab, b in zip(labels, boxes):
                    if b is None:
                        continue
                    v = (b.XMin, b.YMin, b.ZMin)[k] if end == "lo" else (b.XMax, b.YMax, b.ZMax)[k]
                    if abs(v - val) <= 0.01:
                        who.append(lab)
                return ", ".join(who[:3]) or "?"
            word = {0: ("-X", "+X"), 1: ("-Y", "+Y"), 2: ("bottom", "top")}[k]
            ends = ": %s sets the %s end (%.2f), %s the %s end (%.2f)" % (
                at("hi"), word[1], hi[k] + 0.0, at("lo"), word[0], lo[k] + 0.0)
        # S44: say WHICH extent it is and where it runs - the round-5 miss
        # (phone stand 75.34 vs 80) was a part reaching z = -4.65
        line = ("%s: %s %g mm, Atelier measured %g mm (%g mm %s) - the %s extent, "
                "%.2f .. %.2f mm%s. Change that extent by %g mm (sizes pair "
                "with the measured extents largest first: %s)" % (
                    source[0], source[1], w, round(m, 2), round(abs(m - w), 2),
                    "short" if m < w else "over", "XYZ"[k], lo[k] + 0.0, hi[k] + 0.0,
                    ends, round(abs(m - w), 2), pairing))
        out.append((w, k, line) if pairs else line)
    return out


# S54 / R183: the words by which a user's message names holes or slots.
# "screw-top" (a jar) and "screw on" name a thread, not a hole.
STATED_WORDS = {
    "holes": r"\b(?:holes?\b|bores?\b|bored\b|drill\w*|through-holes?\b|perforat\w*|"
             r"bolt(?:s|ed|ing)?\b|m\d+(?:\.\d+)?|"
             r"screws?\b(?!\s*-?\s*(?:top|cap|lid|thread|on\b)))",
    "slots": r"\b(?:slots?|slotted|channels?|grooves?)\b",
}
NOT_STATED = (" - a NOTE, not a failure: the user's message names no %s, so this "
              "count is a target you set yourself (intent.json records what the "
              "user's message states). Keep the design if it does what was asked")


SIZE_NOT_STATED = (" - a NOTE, not a failure: %g mm is not a size the user's message "
                   "gives, so it is your own estimate (intent.json records what the "
                   "user's message states). Keep the design if it does what was asked")


def request_states(request, kind):
    """True when the user's message names `kind` ("holes" / "slots") at all
    (S54): only then is a count of them a target from the request. Either
    word counts for both - "three 6 mm cable channels" is where an agent's
    hole count of 3 comes from (R170), so its miss stays a PROBLEM."""
    import re
    low = str(request or "").lower()
    return any(re.search(STATED_WORDS[k], low) for k in STATED_WORDS)


def _count_spec(spec, key):
    """(count, d or None) of an intent {"count": n, "d_mm": d}; raises
    TypeError / ValueError when malformed."""
    n = int(spec["count"])
    d = spec.get("d_mm")
    return n, (None if d is None else float(d))


def intent_problems(intent, shapes, request=None, labels=None, notes=None):
    """Compare an intent dict (what the agent designed to) with the built
    shapes. Returns problem strings; a mismatch is reported, never
    'corrected'. ONE implementation for ./check and Studio (PRD S30).

    request  the user's message (Studio's turn file): when intent.json has
             no top-level size_mm (per-part sizes, or none), an overall size
             the message gives is measured over ALL the shapes together (R168)
    labels   the shapes' labels, to name the part at each end of a size
             miss (S52)
    notes    a list to receive non-blocking notes (R170: round channels
             open along their length counted as the intended holes; S54 /
             R183: a hole or slot count missed where the request - when
             given - names no holes / slots at all)"""
    if not shapes:
        return []
    out = []
    intent = intent or {}
    tol = intent.get("tolerance_mm")
    try:
        tol = None if tol is None else abs(float(tol))
    except (TypeError, ValueError):
        out.append("%s tolerance_mm must be a number" % INTENT)
        tol = None
    size = intent.get("size_mm")
    want = None
    demoted = []                        # [(axis, note)]: size misses made NOTEs
    stated = set()                      # axes a size_mm PROBLEM already names
    if size is not None:
        try:
            want = sorted((float(x) for x in size), reverse=True)
            if len(want) != 3:
                raise ValueError
        except (TypeError, ValueError):
            out.append("%s size_mm must be three numbers" % INTENT)
            want = None
        if want:
            nums = None if request is None else request_numbers(request)
            for w, k, line in _size_misses(want, shapes, labels, tol,
                                           ("overall size", "you intended"), pairs=True):
                # S54: a size the user's message never gives is the agent's
                # own estimate (a mug's 138 mm with its handle, a clip's
                # 8.2 mm depth) - a NOTE; a size the user gave stays a PROBLEM
                if nums is not None and not _in_request(w, nums, request):
                    demoted.append((k, line + SIZE_NOT_STATED % w))
                else:
                    stated.add(k)
                    out.append(line)
    # R168: only when intent.json gives no overall size_mm of its own (it
    # split the product per part, or gave none). A top-level size_mm is the
    # agent's reading of the request, which the user's turn may still
    # correct (R151) - that comparison stays with the line above.
    # S54: ...and when a size_mm miss was only a NOTE (a number the message
    # never gives), the size the message does give is still measured
    asked = request_size(request) if size is None or demoted else None
    judged = set()
    if asked:
        for _w, k, line in _size_misses(
                asked[0], shapes, labels, tol,
                ("overall size from the request (\"%s\", measured over all parts "
                 "together)" % asked[1], "the user asked for"), pairs=True):
            judged.add(k)
            if k not in stated:
                out.append(line)
    # R189 (S54 review): one extent, one report - a demoted NOTE on an axis
    # the request's own size already fails on would say the same miss twice
    if notes is not None:
        notes.extend(line for k, line in demoted if k not in judged)
    hl = intent.get("holes")
    sl = intent.get("slots")

    def miss(kind, line):
        # R183 / S54: a count the user's message never states is the
        # agent's own target - a NOTE, never a PROBLEM (the agent fought
        # 18 of 29 failed previews over intent it invented, eval r7)
        if request is not None and not request_states(request, kind):
            if notes is not None:
                notes.append(line + NOT_STATED % kind)
        else:
            out.append(line)
    found, cav, chan = [], [], []
    entries = [sl] if isinstance(sl, dict) else sl if isinstance(sl, list) else []
    if sl is not None and (not entries or not all(isinstance(e, dict) for e in entries)):
        out.append(SLOTS_FORM % INTENT)
        entries = []
    round_entries = [e for e in entries if "w_mm" not in e]
    if (isinstance(hl, dict) and hl.get("count") is not None) or round_entries:
        for i, s in enumerate(shapes):
            for b in bores(s, slots=True):
                if labels is not None and i < len(labels):
                    b["part"] = labels[i]
                (chan if b.get("slot") else cav if b["cavity"] else found).append(b)
    near = lambda d, want_d: abs(d - want_d) <= max(0.2, 0.03 * want_d)  # noqa: E731
    reserved = []
    for sl in entries:
        if "w_mm" in sl:
            # R191 (D74): rectangular notches - never a count miss (a NOTE)
            try:
                n_sl = int(sl["count"])
                w_sl = float(sl["w_mm"])
                dep = sl.get("depth_mm")
                dep = None if dep is None else float(dep)
                if n_sl < 0 or w_sl <= 0 or (dep is not None and dep <= 0):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                out.append(SLOTS_FORM % INTENT)
                continue
            line = _rect_slot_line(shapes, n_sl, w_sl, dep)
            if line and notes is not None:
                notes.append(line)
            continue
        try:
            n_sl, d_sl = _count_spec(sl, "slots")
            mine = [b for b in chan if d_sl is None or near(b["d_mm"], d_sl)]
            reserved = reserved + mine
            if len(mine) != n_sl:
                rect = [] if d_sl is None else _rect_notches_all(shapes, d_sl)
                if rect and len(mine) + len(rect) == n_sl:
                    # R191: "d_mm" on rectangular notches - the count is
                    # there, measured as notches: a NOTE, never a miss
                    if notes is not None:
                        notes.append(
                            "slots: you intended %d x diameter %g mm round channel(s); "
                            "Atelier found %d round channel(s) and %d open rectangular "
                            "notch(es) %g mm wide (%s) - counted as the intended slots. "
                            "For a rectangular notch say so in intent.json: \"slots\": "
                            "{\"count\": %d, \"w_mm\": %g} (d_mm is a round channel's "
                            "diameter)" % (n_sl, d_sl, len(mine), len(rect), d_sl,
                                          _notch_text(rect), n_sl, d_sl))
                    continue
                miss("slots", "slots: you intended %d x %s round channel(s) open along "
                           "their length, Atelier found %d (channels found: %s%s)" % (
                               n_sl, "diameter %g mm" % d_sl if d_sl else "any diameter",
                               len(mine), _chan_text(chan) or "none",
                               "; open rectangular notches %g mm wide: %s" % (
                                   d_sl, _notch_text(rect)) if rect else ""))
        except (KeyError, TypeError, ValueError):
            out.append(SLOTS_FORM % INTENT)
    if isinstance(hl, dict) and hl.get("count") is not None:
        try:
            n_want, d_want = _count_spec(hl, "holes")
            free = [b for b in chan if b not in reserved]
            fd = sorted(b["d_mm"] for b in found)
            if d_want is not None:
                # A bore of exactly the intended diameter is one of the
                # intended holes even when it is blind and wide for its part.
                n_got = len([b for b in found + cav if near(b["d_mm"], d_want)])
                ch = [b for b in free if near(b["d_mm"], d_want)]
                what = "%d x diameter %g mm" % (n_want, d_want)
            else:
                n_got, ch, what = len(found), free, "%d" % n_want
            other_d = (d_want is not None and n_got != n_want and request is not None
                       and len(found) == n_want
                       and not _in_request(d_want, request_numbers(request), request))
            if other_d:
                # S54: the count is right and only a diameter the user never
                # gave differs (the nightlight's M3 holes: 3.2 declared, 2.5
                # tapped) - the agent's own choice, a NOTE
                if notes is not None:
                    notes.append(
                        "holes: you intended %s; Atelier found %d closed hole(s) of "
                        "diameter %s - the count matches, and %g mm is not a diameter "
                        "the user's message gives (a NOTE, not a failure): keep the "
                        "diameter the part needs (a tapped hole is smaller than a "
                        "clearance hole) and say which one you cut"
                        % (what, len(found), fd, d_want))
            elif n_got != n_want and ch and n_got + len(ch) == n_want:
                # R170 (D67): the channels ARE the holes' count - a note,
                # never a demand to close them
                if notes is not None:
                    notes.append(
                        "holes: you intended %s; Atelier found %d closed hole(s) and "
                        "%d round channel(s) open along their length (%s) - counted "
                        "as the intended holes. If they are meant as slots, say so "
                        "in intent.json (\"slots\": {\"count\": %d, \"d_mm\": %g}); "
                        "if they must be closed holes, the geometry is what is wrong"
                        % (what, n_got, len(ch), _chan_text(ch), len(ch), ch[0]["d_mm"]))
            elif n_got != n_want and n_got + _coaxial_extra(
                    found if d_want is None else
                    [b for b in found + cav if near(b["d_mm"], d_want)]) == n_want:
                # S65: the knuckles' openings ARE the count (a hinge pin hole
                # through a box's two knuckles + the lid's one) - a NOTE,
                # as R170's channels: never a demand to drill more
                if notes is not None:
                    notes.append(
                        "holes: you intended %s; Atelier found %d hole(s)%s - counted "
                        "as the intended holes (a NOTE, not a failure)" % (
                            what, n_got, coaxial_text(
                                found if d_want is None else
                                [b for b in found + cav if near(b["d_mm"], d_want)],
                                n_want)))
            elif n_got != n_want:
                counted = found if d_want is None else [
                    b for b in found + cav if near(b["d_mm"], d_want)]
                miss("holes", "holes: you intended %s, Atelier found %d (all closed hole "
                     "diameters found: %s%s%s)%s" % (
                         what, n_got, fd or "none",
                         "; round channels open along their length (slots), "
                         "not holes: %s" % _chan_text(free) if free else "",
                         "; %s, not counted: %s" % (
                             "blind cavities and container mouths" if any(
                                 b.get("mouth") for b in cav) else "blind cavities",
                             sorted(b["d_mm"] for b in cav)) if cav else "",
                         coaxial_text(counted, n_want)))
        except (KeyError, TypeError, ValueError):
            out.append("%s holes must be {\"count\": n, \"d_mm\": d}" % INTENT)
    if intent.get("single_body") is True:
        n_bodies = len(shapes)
        n_solids = sum(len(s.Solids) for s in shapes)
        if n_bodies != 1 or n_solids != 1:
            out.append("single body: you intended one solid, Atelier found %d "
                       "object(s) with %d solid(s)" % (n_bodies, n_solids))
    return out


def _coaxial_extra(found):
    """Openings beyond the first of each counted bore (S65)."""
    return sum(max(0, (b.get("walls") or 1) - 1) for b in found)


def coaxial_text(found, n_want=None):
    """S65 (eval r10 hinged_box_lid): how coaxial bores were counted. One
    bore on one axis through several walls or knuckles of ONE body - a pin
    hole through a box's two outer hinge knuckles - is ONE hole crossing
    that many walls (bores(): runs across air stay one, as a hole drilled
    through a case's front and back wall, R181). Bodies are counted
    separately: the lid's middle knuckle is its own hole. '' when no
    counted bore crosses more than one wall."""
    multi = [b for b in found if (b.get("walls") or 1) > 1]
    if not multi:
        return ""
    rows = []
    for b in multi:
        rows.append("%sdiameter %g mm along %s through %d walls/knuckles (1 hole, %d "
                    "openings)" % ("%s: " % b["part"] if b.get("part") else "",
                                   b["d_mm"], b.get("axis"), b["walls"], b["walls"]))
    extra = _coaxial_extra(multi)
    line = ("; coaxial bores are counted ONCE per body and axis - a bore through "
            "several walls or knuckles of one body is one hole, a bore in another "
            "body is another: %s" % "; ".join(rows))
    n_got = len(found)
    if n_want is not None and n_got + extra == n_want:
        line += (" - counted per knuckle (per opening) that is %d, your intended "
                 "count" % n_want)
    return line


def _chan_text(chan):
    """'3 x diameter 6 mm (263 deg of arc)' for round channels."""
    if not chan:
        return ""
    by = {}
    for b in chan:
        by.setdefault(b["d_mm"], []).append(b["arc_deg"])
    return ", ".join("%d x diameter %g mm (%g deg of arc)" % (len(a), d, min(a))
                     for d, a in sorted(by.items()))


# R191 (D74): rectangular notches. The S6-3 toothbrush holder (80 x 30 x
# 20, four 14 mm notches 15 deep from the front, vol 31200.0 exact) was
# declared {"count": 4, "d_mm": 14} and measured as round channels: found 0,
# two fix turns, a red "build still fails" on a correct part.
SLOTS_FORM = ('%s slots must be {"count": n, "d_mm": d} (round channels open along '
              'their length) or {"count": n, "w_mm": w} (open rectangular notches, '
              'optional "depth_mm"), or a list of those')
NOTCH_FACES_MAX = 400       # planar faces looked at, at most (else not measured)
NOTCH_MIN_MM = 0.5          # the two walls must face each other over this much
NOTCH_AIR = 0.02            # share of the gap that may be material (a chamfer)
NOTCH_OPEN = 0.05           # ... of the space from the gap out past the part


def _axis_planes(shape):
    """[(k, sign, c, (lo_u, hi_u, lo_v, hi_v))] - the planar faces of `shape`
    whose outward normal is +/- axis k, at coordinate c, with their extent
    on the two other axes. None when there are too many faces to look at."""
    import Part
    if heavy(shape) or n_faces(shape) > NOTCH_FACES_MAX:
        return None
    out = []
    for f in shape.Faces:
        if not isinstance(f.Surface, Part.Plane):
            continue
        try:
            u0, u1, v0, v1 = f.ParameterRange
            n = f.normalAt(0.5 * (u0 + u1), 0.5 * (v0 + v1))
        except Exception:                               # noqa: BLE001
            continue
        comps = (n.x, n.y, n.z)
        k = max(range(3), key=lambda i: abs(comps[i]))
        if abs(abs(comps[k]) - 1.0) > 1e-6:
            continue
        bb = f.BoundBox
        lo, hi = (bb.XMin, bb.YMin, bb.ZMin), (bb.XMax, bb.YMax, bb.ZMax)
        u, v = [i for i in range(3) if i != k]
        out.append((k, 1 if comps[k] > 0 else -1, 0.5 * (lo[k] + hi[k]),
                    (lo[u], hi[u], lo[v], hi[v])))
    return out


def _box(lo, hi):
    import FreeCAD as App
    import Part
    return Part.makeBox(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], App.Vector(*lo))


def _air(shape, lo, hi, share):
    """True when at most `share` of the box lo..hi is `shape`'s material."""
    vol = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])
    if vol <= 1e-9:
        return True
    return shape.common(_box(lo, hi)).Volume <= share * vol


def rect_notches(shape, w, depth=None, tol=None):
    """R191: the open rectangular notches of `shape` that are `w` mm wide:
    two planar walls facing each other across a gap of w (their outward
    normals point at each other, axis-aligned), air between them, and the
    gap open to the outside past at least one side of the part. Walls split
    into several faces are one notch. [{"w_mm", "axis", "walls": [a, b],
    "span": [[lo, hi] x3], "open": ["-Y", "+Z", ...], "depth_mm"}], or None
    when it cannot be measured (a mesh-like or many-faced shape).

    depth_mm: the notch's extent along an axis it is open at ONE end of
    (15 deep from the front: open at -Y, closed at +Y); None when it is
    open at both ends of every axis. With `depth`, only notches of that
    depth (within tol) are returned."""
    planes = _axis_planes(shape)
    if planes is None:
        return None
    tol = max(0.1, 0.02 * w) if tol is None else tol
    bb = tight(shape)
    blo = (bb.XMin - 1.0, bb.YMin - 1.0, bb.ZMin - 1.0)
    bhi = (bb.XMax + 1.0, bb.YMax + 1.0, bb.ZMax + 1.0)
    groups = {}
    for ka, sa, ca, ra in planes:
        if sa < 0:
            continue
        for kb, sb, cb, rb in planes:
            if kb != ka or sb > 0 or abs((cb - ca) - w) > tol:
                continue
            ov = (max(ra[0], rb[0]), min(ra[1], rb[1]), max(ra[2], rb[2]), min(ra[3], rb[3]))
            if ov[1] - ov[0] < NOTCH_MIN_MM or ov[3] - ov[2] < NOTCH_MIN_MM:
                continue
            key = (ka, round(ca, 3), round(cb, 3))
            groups.setdefault(key, []).append(list(ov))
    out = []
    for (k, ca, cb), rects in sorted(groups.items()):
        # walls split into several faces: touching rectangles are one gap
        merged = []
        for r in sorted(rects):
            for m in merged:
                if r[0] <= m[1] + 1e-6 and r[1] >= m[0] - 1e-6 and \
                        r[2] <= m[3] + 1e-6 and r[3] >= m[2] - 1e-6:
                    m[:] = [min(m[0], r[0]), max(m[1], r[1]), min(m[2], r[2]), max(m[3], r[3])]
                    break
            else:
                merged.append(list(r))
        u, v = [i for i in range(3) if i != k]
        for r in merged:
            lo, hi = [0.0] * 3, [0.0] * 3
            lo[k], hi[k] = ca, cb
            lo[u], hi[u], lo[v], hi[v] = r[0], r[1], r[2], r[3]
            try:
                if not _air(shape, lo, hi, NOTCH_AIR):
                    continue
                opens = {}
                for i in (u, v):
                    for side in (-1, 1):
                        a, b = list(lo), list(hi)
                        if side < 0:
                            a[i], b[i] = blo[i], lo[i]
                        else:
                            a[i], b[i] = hi[i], bhi[i]
                        opens[(i, side)] = _air(shape, a, b, NOTCH_OPEN)
            except Exception:                           # noqa: BLE001
                continue
            if not any(opens.values()):
                continue                # a closed pocket, not a notch
            depths = [hi[i] - lo[i] for i in (u, v)
                      if opens[(i, -1)] != opens[(i, 1)]]
            d_mm = round(max(depths), 3) if depths else None
            if depth is not None and not any(
                    abs(hi[i] - lo[i] - depth) <= max(0.2, 0.02 * depth) for i in (u, v)):
                continue
            out.append({"w_mm": round(cb - ca, 3), "axis": "XYZ"[k],
                        "walls": [round(ca, 3), round(cb, 3)],
                        "span": [[round(lo[i], 3), round(hi[i], 3)] for i in range(3)],
                        "open": ["%s%s" % ("-" if sd < 0 else "+", "XYZ"[i])
                                 for (i, sd), ok in sorted(opens.items()) if ok],
                        "depth_mm": d_mm})
    return out


def _rect_notches_all(shapes, w, depth=None):
    """rect_notches over several shapes; None when any could not be measured."""
    out = []
    for s in shapes:
        try:
            got = rect_notches(s, w, depth)
        except Exception:                               # noqa: BLE001
            got = None
        if got is None:
            return None
        out.extend(got)
    return out


def _notch_text(notches):
    """'4 x 14 mm wide, 15 deep (x 4.8 .. 18.8, x 23.6 .. 37.6, ...)'."""
    if not notches:
        return "none"
    by = {}
    for n in notches:
        by.setdefault((n["w_mm"], n["depth_mm"]), []).append(n)
    parts = []
    for (w, d), ns in sorted(by.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        where = ", ".join("%s %g .. %g" % (n["axis"].lower(), n["walls"][0], n["walls"][1])
                          for n in ns[:6]) + (", ..." if len(ns) > 6 else "")
        parts.append("%d x %g mm wide%s (%s)" % (
            len(ns), w, ", %g deep" % d if d is not None else "", where))
    return "; ".join(parts)


def _rect_slot_line(shapes, n, w, depth=None):
    """R191: None when `n` open rectangular notches `w` wide (and `depth`
    deep, when given) are measured; else a NOTE line - CANNOT DETERMINE,
    never a count miss (the probe sees axis-aligned planar walls only)."""
    got = _rect_notches_all(shapes, w, depth)
    what = "%d open rectangular notch(es) %g mm wide%s" % (
        n, w, " and %g mm deep" % depth if depth is not None else "")
    if got is None:
        return ("slots: you intended %s - CANNOT DETERMINE (a NOTE, not a failure): "
                "the part has too many faces to measure its notches. Look at "
                "check.png and say in your reply what you cut" % what)
    if len(got) == n:
        return None
    anyw = _rect_notches_all(shapes, w) if depth is not None else got
    return ("slots: you intended %s; Atelier measured %d (%s%s) - CANNOT DETERMINE "
            "(a NOTE, not a failure): the probe sees notches between two flat, "
            "axis-aligned walls only. If the part has the notches the user asked "
            "for, keep it and say what was measured; if a notch is missing, add it"
            % (what, len(got), _notch_text(got),
               "; %g mm wide at any depth: %s" % (w, _notch_text(anyw))
               if depth is not None and anyw is not None else ""))


# ------------------------------------------------------------ Atech layout
DESK_TOL_MM = 0.05          # below z=0 by more than this = below the desk;
                            # a product whose lowest point is above z=0 by
                            # more than this floats over the desk (R126)
PRODUCT_GAP_MM = 10.0       # a part within this of the board, a module or a
                            # part already in the product belongs to it (a
                            # lid laid out beside its case); farther away it
                            # is an unrelated part of the document (R114)
INSIDE_TOL_MM = 0.5         # a module may poke out of the case box this much
UPRIGHT_TOL_DEG = 30.0      # board plane within this of vertical = upright
FLAT_TOL_DEG = 30.0         # ... within this of horizontal = flat


def _mesh_box(mesh):
    bb = mesh.BoundBox
    return [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax]


def _shape_box(shape):
    bb = tight(shape)
    return [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax]


def _union(boxes):
    return [min(b[i] for b in boxes) for i in range(3)] + \
        [max(b[i] for b in boxes) for i in range(3, 6)]


def _outside(inner, outer):
    """How far box `inner` sticks out of box `outer`, per side (mm)."""
    names = ("-x", "-y", "-z", "+x", "+y", "+z")
    out = {}
    for k in range(3):
        out[names[k]] = outer[k] - inner[k]
        out[names[k + 3]] = inner[k + 3] - outer[k + 3]
    return out


def board_tilt(mesh):
    """(degrees of the board's plane from vertical - 0 upright, 90 flat -,
    unit normal) from its world mesh points: the normal is the least-
    variance principal axis of the point cloud (the board is a plate)."""
    import math
    import numpy as np
    P = np.array([[p.x, p.y, p.z] for p in mesh.Points], dtype=float)
    if len(P) < 3:
        return None, None
    C = np.cov((P - P.mean(axis=0)).T)
    w, V = np.linalg.eigh(C)
    n = V[:, 0]
    n = n / (np.linalg.norm(n) or 1.0)
    tilt = math.degrees(math.asin(min(1.0, abs(float(n[2])))))
    return tilt, [round(float(x), 4) for x in n]


def atech_layout(parts, board, modules, intent=None, intended=()):
    """S36: the agent's own parts against the Atech board and its seated
    modules. Seated parts are Mesh features (no .Shape): their mesh box is
    the proxy for containment and height.

    parts    [{"label", "shape"}]   the agent's bodies
    board    {"label", "mesh"} or None
    modules  [{"label", "name", "mesh"}]
    intent   intent.json dict; "board": "upright" | "flat" is checked
    intended INTENDED_OVERLAPS: a single label listed there may also stick
             out of the case

    Returns (problems, facts). Checks, each a plain line:
      the desk        once the agent has a part in the PRODUCT (board,
                      modules and the parts that belong to them - see
                      product_parts), the product rests on z = 0: its
                      lowest point below it or floating above it fails with
                      the exact Z translation that fixes it (R126)
      containment     when the product's parts' box holds the board (a
                      case), every module must be inside it too
      orientation     the board's plane vs intent "board"
    Parts far from the board (an unrelated bracket in the same document)
    are not the product and are not judged here (R114).
    Overlap of parts with seated modules is atech_geom.overlaps' job."""
    problems, facts = [], {}
    if board is None:
        return problems, facts
    singles, _pairs = _norm_intended(intended)
    atech = [(board["label"], _mesh_box(board["mesh"]))] + \
        [(m["label"], _mesh_box(m["mesh"])) for m in modules]
    boxed = [(p, _shape_box(p["shape"])) for p in parts]
    mine = product_parts([b for _p, b in boxed], [b for _l, b in atech])
    parts = [boxed[i][0] for i in mine]
    facts["unrelated_parts"] = [boxed[i][0]["label"] for i in range(len(boxed))
                                if i not in mine]
    everything = [(p["label"], _shape_box(p["shape"])) for p in parts] + atech
    problems.extend(_desk_problems(everything, bool(parts), facts))
    tilt, normal = board_tilt(board["mesh"])
    facts["board_tilt_from_vertical_deg"] = None if tilt is None else round(tilt, 2)
    facts["board_normal"] = normal
    want = (intent or {}).get("board")
    if want is not None and tilt is not None:
        w = str(want).strip().lower()
        if w == "upright" and tilt > UPRIGHT_TOL_DEG:
            problems.append("%s lies %.0f deg from upright (intent.json board: "
                            "upright): rotate the board so it stands on an edge"
                            % (board["label"], tilt))
        elif w == "flat" and tilt < 90.0 - FLAT_TOL_DEG:
            problems.append("%s stands %.0f deg from flat (intent.json board: "
                            "flat): lay it down" % (board["label"], 90.0 - tilt))
        elif w not in ("upright", "flat"):
            problems.append("intent.json board must be \"upright\" or \"flat\"")
    if parts:
        facts["margins"], facts["margins_all"] = margins(
            parts, [(board["label"], _mesh_box(board["mesh"]))]
            + [(m["label"], _mesh_box(m["mesh"])) for m in modules])
        case = _union([_shape_box(p["shape"]) for p in parts])
        facts["case_box_mm"] = [round(v, 2) for v in case]
        held = max(_outside(_mesh_box(board["mesh"]), case).values())
        facts["board_outside_case_mm"] = round(held, 2)
        if held <= INSIDE_TOL_MM:
            for m in modules:
                if {m.get("label"), m.get("name")} & singles:
                    continue
                out = _outside(_mesh_box(m["mesh"]), case)
                side = max(out, key=out.get)
                if out[side] > INSIDE_TOL_MM:
                    problems.append("%s sticks %.1f mm out of the case on %s: "
                                    "grow the case or move the module inside"
                                    % (m["label"], out[side], side))
    return problems, facts


SIDES = ("-x", "+x", "-y", "+y", "-z", "+z")


def _margin(inner, outer):
    """Per side, how far box `inner` sits inside box `outer` (mm; negative =
    sticks out that far)."""
    return {"-x": inner[0] - outer[0], "+x": outer[3] - inner[3],
            "-y": inner[1] - outer[1], "+y": outer[4] - inner[4],
            "-z": inner[2] - outer[2], "+z": outer[5] - inner[5]}


def margins(parts, atech):
    """R141 (D53: an edit reply claimed "6 mm margin all round"; the bottom
    margin was 0 mm): each Atech item's MEASURED outline margin to the part
    that encloses it, per side.

    parts  [{"label", "shape"}]   the product's parts
    atech  [(label, box)]         the board and each seated module (mesh box)
    The enclosing part is the one the item sticks out of least (then the
    one whose box overlaps it most). Box to box - the part's outline, not
    its inner wall. Returns ([{"label", "part", "mm": {side: mm}}],
    [{"part", "items", "mm"}]: the board and modules together, per part)."""
    boxed = [(p["label"], _shape_box(p["shape"])) for p in parts]
    if not boxed:
        return [], []
    rows, groups = [], {}
    for label, box in atech:
        def score(pb):
            m = _margin(box, pb)
            lap = 1.0
            for k in range(3):
                lap *= max(0.0, min(box[k + 3], pb[k + 3]) - max(box[k], pb[k]))
            return (sum(min(0.0, v) for v in m.values()), lap)
        name, pb = max(boxed, key=lambda t: score(t[1]))
        rows.append({"label": label, "part": name,
                     "mm": {k: round(v, 2) + 0.0 for k, v in _margin(box, pb).items()}})
        groups.setdefault(name, (pb, []))[1].append((label, box))
    alls = []
    for name, (pb, items) in groups.items():
        u = _union([b for _l, b in items])
        alls.append({"part": name, "items": [l for l, _b in items],
                     "mm": {k: round(v, 2) + 0.0 for k, v in _margin(u, pb).items()}})
    return rows, alls


def margin_text(mm):
    # round first: -0.04 printed "%.1f" reads "-0.0" (sticks out by nothing)
    return " ".join("%s %.1f" % (k.upper(), round(mm[k], 1) + 0.0) for k in SIDES)


def _gap(a, b):
    """Distance between two [xmin, ymin, zmin, xmax, ymax, zmax] boxes."""
    d = [max(0.0, max(a[k], b[k]) - min(a[k + 3], b[k + 3])) for k in range(3)]
    return (d[0] ** 2 + d[1] ** 2 + d[2] ** 2) ** 0.5


def product_parts(part_boxes, atech_boxes, gap=PRODUCT_GAP_MM):
    """Indices of the parts that belong to the Atech product: every part
    within `gap` mm (box to box) of the board, a module, or a part already
    in the product - grown until nothing more joins. A box is a bound, so
    this can only ever include too much, never drop a part that touches."""
    inside = set()
    frontier = list(atech_boxes)
    while frontier:
        nxt = []
        for i, pb in enumerate(part_boxes):
            if i not in inside and any(_gap(pb, fb) <= gap for fb in frontier):
                inside.add(i)
                nxt.append(pb)
        frontier = nxt
    return inside


# R177: a request whose product stands on a desk / table / floor. Words
# that put it anywhere else (clamped to a desk EDGE, hung on a hook or a
# wall, mounted under a shelf) take the rule away: there z = 0 is not the
# surface it rests on.
DESK_WORDS = (r"\b(?:desks?|table|tabletop|floor|shelf|counter(?:top)?|stands?|"
              r"standing|sits? on|rests? on|stood)\b")
DESK_NOT = (r"\b(?:clamps?|clamping|clamped|clips?|clipped|hooks?|hangs?|hanging|hung|"
            r"mount(?:s|ed|ing)?|brackets?|under(?:neath)?|edge|wall|ceiling)\b")


# A part may dip below z = 0 by up to one FDM first layer: the slicer seats
# it on the bed with the base still inside the first layer. MEASURED: the
# round-6 phone stand's leaning backrest corner reaches z = -0.10 mm (a
# passing design); the round-7 clock stand's wedge reached -18.99 mm.
DESK_BELOW_MM = 0.2


def stands_on_desk(request):
    """True when the user's message puts the product ON a desk, table,
    floor or shelf (or calls it a stand) - and nothing in it hangs or
    clamps it elsewhere (R177)."""
    import re
    low = str(request or "").lower()
    return bool(re.search(DESK_WORDS, low)) and not re.search(DESK_NOT, low)


def below_desk(parts, request, tol=DESK_BELOW_MM):
    """R177: for a request that stands the product on a desk / table /
    floor (stands_on_desk), the agent's parts must not reach below z = 0:
    the eval-r7 stand cut a wedge under the clock and reached z = -18.99 mm
    while ./check passed. parts: [{"label", "shape"}] - the agent's own
    bodies (never the user's objects). Returns (problems, facts)."""
    if not parts or not stands_on_desk(request):
        return [], {}
    low = []
    for p in parts:
        try:
            low.append((tight(p["shape"]).ZMin, p["label"]))
        except Exception:                               # noqa: BLE001
            continue
    if not low:
        return [], {}
    zmin = min(z for z, _l in low)
    facts = {"z_min_mm": round(zmin, 3)}
    if zmin >= -tol:
        return [], facts
    who = [l for z, l in sorted(low) if z < -tol]
    names = ", ".join("%s (z min %.2f mm)" % (l, z) for z, l in sorted(low) if z < -tol)
    return ["%s below the desk: the request stands the product on a desk / table / "
            "floor (z = 0), and %s reaches z = %.2f mm. Nothing may go below z = 0: "
            "raise the design by %.2f mm in Z (every part together, so the lowest "
            "point is exactly z = 0), or reshape what hangs below it"
            % (names, who[0], zmin, -zmin)], facts


def _desk_problems(everything, has_parts, facts):
    """The product must rest on the desk (z = 0). One line, with the exact
    translation: "move the design up" made a fix turn lift an alarm clock
    to z_min = 0.6 mm and leave it floating (dogfood D51, R126).
    Only once the agent has a part in the product: a board the user placed,
    in a document where the agent builds something unrelated, is not the
    agent's to move (R114)."""
    if not everything or not has_parts:
        return []
    zmin = min(box[2] for _label, box in everything)
    lowest = [label for label, box in everything if box[2] <= zmin + DESK_TOL_MM]
    facts["product_z_min_mm"] = round(zmin, 3)
    who = ", ".join(lowest[:4]) + (" ..." if len(lowest) > 4 else "")
    if zmin < -DESK_TOL_MM:
        return ["the design reaches z = %.2f mm (lowest: %s), below the desk "
                "(z = 0): translate the whole design (the board Placement "
                "and every part) by +%.2f mm in Z so the lowest point is "
                "exactly z = 0 - not more" % (zmin, who, -zmin)]
    if zmin > DESK_TOL_MM:
        return ["the design floats %.2f mm above the desk (lowest: %s at z = "
                "%.2f mm): translate the whole design (the board Placement "
                "and every part) by -%.2f mm in Z so the lowest point is "
                "exactly z = 0" % (zmin, who, zmin, zmin)]
    return []


# ------------------------------------------------------ rays (R152, R154)
def _cast(T, Q, d, far=None, eps=1e-4, chunk=64, tri_lo=None, tri_hi=None):
    """First hit of the rays Q + s*d, eps < s <= far, on the triangles T
    (m,3,3). Returns (s (n,) - inf where nothing is hit -, triangle index
    (n,) - -1 there). tri_lo/tri_hi: T's per-triangle world boxes, when the
    caller has them (skips triangles nowhere near the rays)."""
    import numpy as np
    n = len(Q)
    dist = np.full(n, np.inf)
    idx = np.full(n, -1, dtype=int)
    if not n or not len(T):
        return dist, idx
    d = np.asarray(d, dtype=float)
    d = d / np.linalg.norm(d)
    keep = np.arange(len(T))
    if far is not None and np.isfinite(far):
        lo = np.minimum(Q, Q + d * far).min(axis=0) - 1e-6
        hi = np.maximum(Q, Q + d * far).max(axis=0) + 1e-6
        tl = T.min(axis=1) if tri_lo is None else tri_lo
        th = T.max(axis=1) if tri_hi is None else tri_hi
        keep = np.nonzero(np.all((th >= lo) & (tl <= hi), axis=1))[0]
        if not len(keep):
            return dist, idx
    Bm = _basis(d)
    q = Q @ Bm.T
    t = T[keep] @ Bm.T
    a = t[:, 0]
    e1, e2 = t[:, 1] - a, t[:, 2] - a
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    ok = np.abs(det) > 1e-12
    keep, a, e1, e2, det, t = keep[ok], a[ok], e1[ok], e2[ok], det[ok], t[ok]
    if not len(keep):
        return dist, idx
    lo, hi = t.min(axis=1), t.max(axis=1)
    top = np.inf if far is None else float(far)
    # chunks of nearby rays (2D cells across the ray direction), so each
    # chunk's box meets few triangles; a strip sorted on x alone spans the
    # whole part in y (MEASURED on the round-5 mug: 49 k triangles)
    span = np.ptp(q[:, :2], axis=0) if n > 1 else np.zeros(2)
    cell = max(float(span.max()) / max(1.0, (n / float(chunk)) ** 0.5), 1e-6)
    order = np.lexsort((q[:, 1], np.floor(q[:, 0] / cell), np.floor(q[:, 1] / cell)))
    for s in range(0, n, chunk):
        ii = order[s:s + chunk]
        c = q[ii]
        sel = ((hi[:, 0] >= c[:, 0].min()) & (lo[:, 0] <= c[:, 0].max())
               & (hi[:, 1] >= c[:, 1].min()) & (lo[:, 1] <= c[:, 1].max())
               & (hi[:, 2] > c[:, 2].min() + eps) & (lo[:, 2] <= c[:, 2].max() + top))
        if not sel.any():
            continue
        A, E1, E2, D = a[sel], e1[sel], e2[sel], det[sel]
        wx = c[:, 0, None] - A[None, :, 0]
        wy = c[:, 1, None] - A[None, :, 1]
        u = (wx * E2[None, :, 1] - wy * E2[None, :, 0]) / D
        v = (E1[None, :, 0] * wy - E1[None, :, 1] * wx) / D
        z = A[None, :, 2] + u * E1[None, :, 2] + v * E2[None, :, 2] - c[:, 2, None]
        hit = (u >= 0) & (v >= 0) & (u + v <= 1) & (z > eps) & (z <= top)
        z = np.where(hit, z, np.inf)
        k = z.argmin(axis=1)
        best = z[np.arange(len(ii)), k]
        got = np.isfinite(best)
        dist[ii[got]] = best[got]
        idx[ii[got]] = keep[np.nonzero(sel)[0][k[got]]]
    return dist, idx


# ----------------------------------------------- face open probe (R152)
FACE_FAR_MM = 200.0         # a ray that meets no part within this is open
FACE_GRID = 13              # rays per side of the module's face (13 x 13)
FACE_INSET_MM = 1.0         # grid kept this far inside the face's outline
FACE_LIFT_MM = 0.2          # rays start this far off the module's face
# Module kinds whose working face needs a way out of the product (D60, D64),
# by the library's module name. Anything else (orientation, dc_motor, knob,
# n20_wheel) is reported as a line, never judged.
OPEN_KINDS = {"light": "light", "screen": "screen", "button": "button",
              "speaker": "speaker", "distance_sensor": "sensor",
              "temp_humidity": "sensor", "microphone": "sensor",
              "usbc": "USB-C socket"}
# How each kind's working face is found in its mesh (R164, D64). "top": the
# module's side away from the board (a light, a screen, a button face the
# way the components do). "socket": the connector mouth - the mesh part
# that alone makes the module's extreme in a direction along the board
# (MEASURED 2026-09-25, usbc on port 1: a 8.26 x 3.5 x 10 mm shell whose
# end is the module's -X extreme, 0.25 mm past the module board; port 11:
# the same at +X). A plug goes in along that direction, not through the
# cover over the module.
FACE_OF = {"USB-C socket": "socket"}
# words by which a request names a kind (regular expressions, lower case)
KIND_WORDS = {
    # "lightweight", "highlight" and "pressure" name no light or button
    "light": (r"(?<!high)light(?!weight)", r"\blamp", r"\bleds?\b", r"\bglow",
              r"\billuminat"),
    "screen": (r"screen", r"display", r"\boled", r"\blcd"),
    "button": (r"button", r"\bpush", r"\bpress(?!ure)", r"doorbell"),
    "speaker": (r"speaker", r"\bsound", r"\bbeep", r"\bbuzz", r"\bchime", r"\baudio",
                r"\balarm", r"doorbell"),
    "sensor": (r"sensor", r"temperature", r"humidity", r"\bthermo", r"weather",
               r"distance", r"\brange", r"proximity", r"micro(?:phone)?\b",
               r"\bmic\b", r"\bvoice"),
    # the plug has to go in: named when the request speaks of USB, a plug,
    # a charging or power port
    "USB-C socket": (r"\busb", r"\bplug\b", r"\bcharg(?:e|er|ing)\b",
                     r"power (?:port|socket|jack|input|cable|lead)"),
}
SOCKET_REACH_MM = 0.05      # a part within this of the module's extreme makes it
SOCKET_MIN_MM = 0.1         # the socket must stand this far past the module body


def module_kind(module_name):
    """'light' / 'screen' / 'button' / 'speaker' / 'sensor' /
    'USB-C socket', or None."""
    return OPEN_KINDS.get(str(module_name or "").strip().lower())


def request_names(kind, request):
    """True when the request text names a module of `kind`; None when there
    is no request to read (cannot tell)."""
    import re
    if request is None:
        return None
    text = str(request).lower()
    return any(re.search(p, text) for p in KIND_WORDS.get(kind, ()))


def _mesh_points(mesh):
    import numpy as np
    return np.array([[p.x, p.y, p.z] for p in mesh.Points], dtype=float).reshape(-1, 3)


def socket_face(mesh, board_normal, axes=None):
    """R164: the direction a module's connector mouth faces, MEASURED from
    its mesh - (unit direction [x, y, z], (n,3) points of the socket) or
    (None, None) when no part of the mesh stands out that way.

    board_normal  the board's unit normal (world)
    axes          the module's own axes in world (its Placement's rotated
                  X, Y, Z); world X, Y, Z when not given
    Candidates are the module axes along the board (within 60 deg of its
    plane), both senses. In a direction, the parts of the mesh that reach
    the module's extreme (within SOCKET_REACH_MM) are the socket when the
    module's biggest part (its body) is not among them and they stand at
    least SOCKET_MIN_MM past it. The direction where they stand out most
    wins. Pure measurement: no module is named here, so atech_ports'
    API card can use the same function (R165)."""
    import numpy as np
    try:
        comps = [_mesh_points(c) for c in mesh.getSeparateComponents()]
    except Exception:                                   # noqa: BLE001
        return None, None
    comps = [c for c in comps if len(c)]
    if len(comps) < 2:
        return None, None
    bn = np.asarray(board_normal, dtype=float)
    bn = bn / (np.linalg.norm(bn) or 1.0)
    vols = [float(np.prod(np.maximum(c.max(0) - c.min(0), 1e-6))) for c in comps]
    body = int(np.argmax(vols))
    axes = [np.array(a, dtype=float) for a in (axes or ((1, 0, 0), (0, 1, 0), (0, 0, 1)))]
    best = (SOCKET_MIN_MM, None, None)
    for a in axes:
        a = a / (np.linalg.norm(a) or 1.0)
        if abs(float(a @ bn)) > 0.5:
            continue                    # across the board: not along it
        for d in (a, -a):
            reach = [float((c @ d).max()) for c in comps]
            top = max(reach)
            at = [i for i, r in enumerate(reach) if r >= top - SOCKET_REACH_MM]
            if body in at:
                continue
            past = top - reach[body]
            if past > best[0]:
                best = (past, d, np.concatenate([comps[i] for i in at]))
    if best[1] is None:
        return None, None
    return [round(float(x), 4) for x in best[1]], best[2]


def face_open(parts, board, modules, far=FACE_FAR_MM, grid=FACE_GRID):
    """R152 (D60: a "window over the light" cut in the end lid, the light's
    face 0/169 rays open, reported as success): per seated module, the
    fraction of a grid of rays from its working face, along its outward
    normal, that get out of the product without meeting one of its parts.

    parts    [{"label", "shape"}]    the agent's parts
    board    {"label", "mesh"}
    modules  [{"label", "name", "module", "mesh", "axes" (optional: the
             module's X, Y, Z in world)}]
    The working face (R164): for most kinds the module's face away from the
    board, along the board's normal (a module lies flat on the board,
    components outward); for a USB-C socket the connector mouth, measured
    from the mesh (socket_face) - no mouth found: not judged ("face":
    None). Only the product's parts (product_parts) block a ray - an
    unrelated part elsewhere in the document is not in front of anything.
    A part too slow to tessellate (tess_slow) is left out and named in
    "unmeasured". Returns [{"label", "module", "kind", "face", "open",
    "rays", "open_pct", "normal", "blocked_by", "unmeasured"}]; blocked_by:
    the part most blocked rays meet first."""
    import numpy as np
    if board is None or not modules:
        return []
    _tilt, bn = board_tilt(board["mesh"])
    if bn is None:
        return []
    bn = np.array(bn, dtype=float)
    BP = _mesh_points(board["mesh"])
    bc = BP.mean(axis=0)
    atech = [_mesh_box(board["mesh"])] + [_mesh_box(m["mesh"]) for m in modules]
    boxed = [_shape_box(p["shape"]) for p in parts]
    mine = sorted(product_parts(boxed, atech))
    tris, owner, unmeasured = [], [], []
    for i in mine:
        try:
            _P, T = _tess(parts[i]["shape"])
        except SlowToTessellate:
            unmeasured.append(parts[i]["label"])
            continue
        except Exception:                               # noqa: BLE001
            continue
        if len(T):
            tris.append(T)
            owner.append(np.full(len(T), i))
    T = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
    own = np.concatenate(owner) if owner else np.zeros(0, dtype=int)
    tl, th = (T.min(axis=1), T.max(axis=1)) if len(T) else (None, None)
    out = []
    for m in modules:
        P = _mesh_points(m["mesh"])
        if not len(P):
            continue
        kind = module_kind(m.get("module"))
        face = FACE_OF.get(kind, "top")
        if face == "socket":
            d, FP = socket_face(m["mesh"], bn, m.get("axes"))
            if d is None:
                # no mouth measured: reported, never judged
                kind, face = None, None
                s = float(np.dot(P.mean(axis=0) - bc, bn))
                d, FP = (bn if s >= 0 else -bn), P
            else:
                d = np.array(d, dtype=float)
        else:
            s = float(np.dot(P.mean(axis=0) - bc, bn))
            d, FP = (bn if s >= 0 else -bn), P
        B = _basis(d)
        pu, pv, pd = FP @ B[0], FP @ B[1], FP @ B[2]

        def axis(lo, hi):
            inset = min(FACE_INSET_MM, 0.25 * (hi - lo))
            lo, hi = lo + inset, hi - inset
            return np.linspace(lo, hi, grid) if hi > lo else np.array([(lo + hi) / 2.0])
        gu, gv = np.meshgrid(axis(pu.min(), pu.max()), axis(pv.min(), pv.max()))
        Q = (gu.reshape(-1, 1) * B[0] + gv.reshape(-1, 1) * B[1]
             + (pd.max() + FACE_LIFT_MM) * B[2])
        dist, idx = _cast(T, Q, d, far=far, tri_lo=tl, tri_hi=th)
        n_open = int(np.isinf(dist).sum())
        blocked = None
        hit = idx[idx >= 0]
        if len(hit):
            vals, counts = np.unique(own[hit], return_counts=True)
            blocked = parts[int(vals[counts.argmax()])]["label"]
        out.append({"label": m["label"], "module": m.get("module"),
                    "kind": kind, "face": face, "open": n_open,
                    "rays": len(Q), "open_pct": round(100.0 * n_open / len(Q), 1),
                    "normal": [round(float(x), 3) for x in d],
                    "blocked_by": blocked, "unmeasured": list(unmeasured)})
    return out


def normal_text(n):
    """[0, 0.999, 0.01] -> '+Y'; a tilted normal -> '(0.26, 0.97, 0.00)'."""
    k = max(range(3), key=lambda i: abs(n[i]))
    if abs(abs(n[k]) - 1.0) < 0.02:
        return ("+" if n[k] > 0 else "-") + "XYZ"[k]
    return "(%.2f, %.2f, %.2f)" % tuple(n)


FACE_WORDS = {"top": "working face", "socket": "socket mouth"}


def face_text(row):
    """'working face (+Y)' / 'socket mouth (-X)' for a face_open row."""
    return "%s (%s)" % (FACE_WORDS.get(row.get("face") or "top", "working face"),
                        normal_text(row["normal"]))


def face_open_problems(rows, request):
    """(problems, warnings) from face_open rows: a module whose kind needs
    an opening, 0 % open, named by the request -> a problem; with no
    request to read -> a warning (the kind alone cannot say the user wanted
    it seen - a sealed temperature sensor may be deliberate). A USB-C
    socket is judged along its mouth (R164): a slot over the module's
    cover does not let a plug in."""
    problems, warnings = [], []
    for r in rows:
        if not r["kind"] or r["open"] > 0:
            continue
        named = request_names(r["kind"], request)
        fix = ("Cut the opening in front of the socket mouth (%s), not over the "
               "module's cover" % normal_text(r["normal"])
               if r.get("face") == "socket"
               else "Cut the opening in front of that face, not elsewhere")
        line = ("%s (a %s) is sealed in: 0 of %d rays from its %s get out of the "
                "product within %g mm%s. %s" % (
                    r["label"], r["kind"], r["rays"], face_text(r),
                    FACE_FAR_MM, " - %s is in the way" % r["blocked_by"]
                    if r["blocked_by"] else "", fix))
        if named:
            problems.append(line + " (the request asks for a %s)" % r["kind"])
        elif named is None:
            warnings.append(line)
    return problems, warnings


# ------------------------------------------------- minimum wall (R154)
WALL_FLOOR_MM = 0.8         # FDM: 2 perimeters x 0.4 mm nozzle
WALL_PROBE_MM = 6.0         # rays stop here: a wall thicker is "thick"
WALL_BUDGET_S = 0.5         # time cap of the whole probe (MEASURED on the
                            # 12 round-5 outputs: 0.02-0.8 s uncapped, the mug
                            # (49 k triangles) the slowest)
WALL_SAMPLES = 3000         # surface samples over all parts, at most
WALL_PARALLEL = 0.766       # exit face within 40 deg of anti-parallel. At 25
                            # deg (0.9) the D62 jar lid read 0.81 mm: its grip
                            # flutes meet the thread groove's V flank ~32 deg
                            # off parallel, so the 0.10 mm slivers where they
                            # break through were skipped. MEASURED on the 12
                            # round-6 outputs: no new reading under 1.5 mm at
                            # 40 deg; a 64 deg thread V (120 deg between its
                            # flank normals) is still no wall
WALL_BIN = 5.0              # normals grouped on a 1/5 grid (~11 deg; the
                            # ray error is under 1 %, the parallel test uses
                            # each sample's own normal)


# R194 (D63 keycap): the side walls' thickness as measured - normal to the
# wall, which on a tapered wall is not the horizontal offset the model used
# (stated 1.2, measured 1.41 normal / 1.46 horizontal on a 14 deg taper).
WALL_SIDE_NZ = 0.5          # a side wall: |normal z| at most this (60 deg)
WALL_SIDE_GAP = 0.05        # thicknesses further apart than this (mm, or 3 %)
                            # are different walls
WALL_SIDE_MIN = 8           # samples a side wall needs to be reported


def side_walls(values):
    """{"mm", "lo", "hi", "samples", "all": [min, max], "share"} of the side-
    wall thicknesses the wall probe measured: sorted, split where two
    neighbours differ by more than WALL_SIDE_GAP (3 % above 1.7 mm), and the
    group with the most samples (area-weighted) is THE side wall - lo..hi its
    range, mm its median. A wall that thickens steadily (a conical bore
    in a straight jar) stays one group and reports its whole range. None
    under WALL_SIDE_MIN samples."""
    vals = sorted(values)
    if len(vals) < WALL_SIDE_MIN:
        return None
    groups = [[vals[0]]]
    for a, b in zip(vals, vals[1:]):
        if b - a > max(WALL_SIDE_GAP, 0.03 * a):
            groups.append([])
        groups[-1].append(b)
    g = max(groups, key=len)
    if len(g) < WALL_SIDE_MIN:
        return None
    return {"mm": round(g[len(g) // 2], 2), "lo": round(g[0], 2), "hi": round(g[-1], 2),
            "samples": len(g), "share": round(len(g) / float(len(vals)), 2),
            "all": [round(vals[0], 2), round(vals[-1], 2)]}


def thin_walls(parts, budget_s=WALL_BUDGET_S, samples=WALL_SAMPLES,
               probe=WALL_PROBE_MM, seed=0):
    """R154 (D62: a jar lid's grip flutes left 0.4 mm over the thread
    groove, unseen): the thinnest wall a cheap probe can MEASURE.

    Samples points on each part's surface (area-weighted over its
    tessellation), casts a ray from each straight into the material and
    takes the distance to where it leaves - but only where it leaves
    through a face roughly PARALLEL to the one it entered (within 40 deg):
    two walls facing each other. The tapering flank of a thread, a knife
    edge or a chamfer is not a wall and is skipped. Rays stop at `probe` mm.
    Time-capped: an unfinished probe says so (complete=False).

    A sampled lower-quality measurement: the thinnest wall it FOUND, never
    a proof there is none thinner; tessellation limits it to about the
    deflection (_deflection). Returns {"parts": [{"label", "mm", "at",
    "samples", "side"}], "min": that row or None, "samples", "seconds",
    "complete"}; "side" (R194, when measured) is side_walls() of the rays
    from the part's side faces: the side walls' own thickness, normal to
    the wall."""
    import time
    import numpy as np
    t0 = time.time()
    rng = np.random.default_rng(seed)
    per = max(50, int(samples / max(1, len(parts))))
    rows, total, complete = [], 0, True
    for p in parts:
        if time.time() - t0 > budget_s:
            complete = False
            break
        try:
            _P, T = _tess(p["shape"])
        except SlowToTessellate as exc:
            rows.append({"label": p["label"], "mm": None, "at": None, "samples": 0,
                         "skipped": str(exc)})
            continue
        except Exception:                               # noqa: BLE001
            continue
        if not len(T):
            continue
        N = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
        area = np.linalg.norm(N, axis=1)
        good = area > 1e-12
        if not good.any():
            continue
        Nu = np.zeros_like(N)
        Nu[good] = N[good] / area[good, None]
        cand = np.nonzero(good)[0]
        # area-weighted, with replacement: a box is 12 big triangles, and
        # each gets as many points as its share of the area
        cand = rng.choice(cand, size=per, replace=True, p=area[cand] / area[cand].sum())
        # a random point inside each chosen triangle (not the centroid:
        # centroids of a fan all line up on one spoke)
        r1, r2 = rng.random(len(cand)), rng.random(len(cand))
        flip = r1 + r2 > 1
        r1[flip], r2[flip] = 1 - r1[flip], 1 - r2[flip]
        Tc = T[cand]
        C = Tc[:, 0] + r1[:, None] * (Tc[:, 1] - Tc[:, 0]) + r2[:, None] * (Tc[:, 2] - Tc[:, 0])
        Nc = Nu[cand]
        tl, th = T.min(axis=1), T.max(axis=1)
        keys = np.round(Nc * WALL_BIN).astype(int)
        _u, grp = np.unique(keys, axis=0, return_inverse=True)
        grp = np.asarray(grp).reshape(-1)
        order = np.argsort(-np.bincount(grp))
        best = (np.inf, None)
        done = 0
        side = []
        for gi in order:
            if time.time() - t0 > budget_s:
                complete = False
                break
            sel = np.nonzero(grp == gi)[0]
            d = -Nc[sel].mean(axis=0)
            ln = np.linalg.norm(d)
            if ln < 1e-9:
                continue
            d = d / ln
            dist, idx = _cast(T, C[sel], d, far=probe, eps=1e-3, tri_lo=tl, tri_hi=th)
            got = idx >= 0
            if got.any():
                par = (Nu[idx[got]] * Nc[sel][got]).sum(axis=1) < -WALL_PARALLEL
                dd = dist[got][par]
                # R194: side walls (normal within 60 deg of horizontal)
                up = np.abs(Nc[sel][got][par][:, 2]) <= WALL_SIDE_NZ
                if up.any():
                    # ...that stand at least as tall as they are thick at the
                    # wall's middle: the bars between a flat lid's vent slots
                    # (4.5 wide in a 3 mm plate) are not side walls
                    mid = C[sel][got][par][up] + d[None, :] * (dd[up][:, None] / 2.0)
                    tall = np.zeros(len(mid))
                    for sz in (1.0, -1.0):
                        dz, _i = _cast(T, mid, np.array([0.0, 0.0, sz]), far=probe,
                                       eps=1e-6, tri_lo=tl, tri_hi=th)
                        tall = tall + dz
                    side.extend(float(x) for x in dd[up][tall >= dd[up]])
                if len(dd):
                    k = int(dd.argmin())
                    if dd[k] < best[0]:
                        best = (float(dd[k]), C[sel][got][par][k])
            done += len(sel)
        total += done
        if best[1] is not None:
            rows.append({"label": p["label"], "mm": round(best[0], 2),
                         "at": [round(float(x), 2) for x in best[1]],
                         "samples": done})
        else:
            rows.append({"label": p["label"], "mm": None, "at": None, "samples": done})
        sw = side_walls(side)
        if sw:
            rows[-1]["side"] = sw
    found = [r for r in rows if r["mm"] is not None]
    return {"parts": rows, "min": min(found, key=lambda r: r["mm"]) if found else None,
            "samples": total, "seconds": round(time.time() - t0, 3),
            "complete": complete}


# ------------------------------------------------ open container (R169)
# D66: a planter's inner pot closed on top by a solid Ø105.6 x 4 disc, and
# the agent, looking at check.png, reported "rim seats flush". A part whose
# name says it holds things from above must let a ray down its middle reach
# well into it. Names (label words, lower case):
CONTAINER_WORDS = ("pot", "pots", "planter", "cup", "mug", "bowl", "vase", "bucket",
                   "container", "tray", "bin", "basket", "tumbler", "jar", "pitcher",
                   "beaker", "caddy", "canister")
# ...and names that may or may not be an open container (a box can be a
# closed enclosure, a reservoir a closed tank): a WARNING, never a problem
CONTAINER_MAYBE = ("box", "holder", "reservoir", "organizer", "organiser", "tank")
CONTAINER_NOT = ("lid", "lids", "cap", "cover", "top", "plug", "stopper", "handle",
                 "base", "stand", "saucer", "suction",
                 # "Pot_Knob" is a potentiometer's knob, not a flower pot
                 "knob", "dial", "shaft", "button", "wiper")
CONTAINER_GRID = 7          # rays per side, over the middle of the footprint
CONTAINER_MIDDLE = 0.6      # ...this share of the part's width and depth
CONTAINER_DEPTH = 0.5       # open: some ray gets this share of the height deep


def _words(label):
    """'Inner_Pot' / 'innerPot2' -> ['inner', 'pot', '2']."""
    import re
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", str(label or ""))
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]


def container_kind(label):
    """'container' (the name says it holds things from above), 'maybe', or
    None - from the label's words; a lid, cap or handle is none."""
    w = set(_words(label))
    if w & set(CONTAINER_NOT):
        return None
    if w & set(CONTAINER_WORDS):
        return "container"
    if w & set(CONTAINER_MAYBE):
        return "maybe"
    return None


CONTAINER_SHARE = 0.25      # ...and at least this share of the rays that hit
# above first, then the sides. Never from below: MEASURED on the D66 pot,
# rays up through its 6 drainage slots and wick hole reached the cap 58 mm
# in - a pot is not filled through its drain.
OPEN_SIDES = ((2, 1), (1, -1), (1, 1), (0, -1), (0, 1))


def container_open(shape, grid=CONTAINER_GRID):
    """R169: can anything get into `shape`? Rays go straight in through the
    middle of its box (CONTAINER_MIDDLE of the two other extents), from
    above first, then from each side - never from below. {"open", "side",
    "depth_mm", "height_mm", "blocked_z", "rays"}: open when, from some
    side, at least CONTAINER_SHARE of the rays get CONTAINER_DEPTH of the
    part's extent that way deep (a few rays through small holes do not
    open it) - a pot opens upward, a hex wall planter lying on its side
    opens to the front (round 6). Rays that meet nothing (past the part, a
    drain hole) say nothing and are not counted. When closed, depth_mm /
    height_mm / blocked_z are from above: where the middle ray meets the
    material first and leaves it again (the cap). Raises SlowToTessellate
    like _tess."""
    import numpy as np
    bb = tight(shape)
    lo = np.array([bb.XMin, bb.YMin, bb.ZMin])
    hi = np.array([bb.XMax, bb.YMax, bb.ZMax])
    _P, T = _tess(shape)
    first = None
    for k, sign in OPEN_SIDES:
        u, v = [i for i in range(3) if i != k]
        c = (lo + hi) / 2.0
        L = float(hi[k] - lo[k])
        gu, gv = np.meshgrid(
            np.linspace(c[u] - CONTAINER_MIDDLE * (hi[u] - lo[u]) / 2.0,
                        c[u] + CONTAINER_MIDDLE * (hi[u] - lo[u]) / 2.0, grid),
            np.linspace(c[v] - CONTAINER_MIDDLE * (hi[v] - lo[v]) / 2.0,
                        c[v] + CONTAINER_MIDDLE * (hi[v] - lo[v]) / 2.0, grid))
        Q = np.zeros((gu.size, 3))
        Q[:, u], Q[:, v] = gu.ravel(), gv.ravel()
        face = hi[k] if sign > 0 else lo[k]
        Q[:, k] = face + sign * 1.0             # 1 mm outside that side
        into = np.zeros(3)
        into[k] = -sign
        dist, _idx = _cast(T, Q, into, far=L + 2.0)
        hit = np.isfinite(dist)
        deep = (dist[hit] - 1.0) if hit.any() else np.array([L])
        best = float(deep.max())
        share = float((deep >= CONTAINER_DEPTH * L).mean())
        res = {"open": share >= CONTAINER_SHARE,
               "side": ("+" if sign > 0 else "-") + "XYZ"[k],
               "depth_mm": round(best, 2), "height_mm": round(L, 2),
               "blocked_z": None, "rays": int(hit.sum())}
        if res["open"]:
            return res
        if first is None:
            # from above: where the middle ray that hit enters and leaves
            near = np.where(hit, (Q[:, u] - c[u]) ** 2 + (Q[:, v] - c[v]) ** 2, np.inf)
            mid = int(np.argmin(near))
            if np.isfinite(near[mid]):
                z_in = float(Q[mid, k] + into[k] * dist[mid])
                start = Q[mid:mid + 1].copy()
                start[0, k] = z_in + into[k] * 1e-3
                d2, _i2 = _cast(T, start, into, far=L + 2.0)
                z_out = (z_in + into[k] * (1e-3 + float(d2[0])) if np.isfinite(d2[0])
                         else float(lo[k]))
                res["blocked_z"] = [round(min(z_in, z_out), 2) + 0.0,
                                    round(max(z_in, z_out), 2) + 0.0]
            else:
                res["blocked_z"] = [round(float(lo[k]), 2), round(float(hi[k]), 2)]
            first = res
    first["side"] = None
    return first


CLOSED_WORDS = r"\b(closed|sealed|lidded|capped|enclosed)\b"


def containers(parts, intent=None, request=None, atech=False):
    """R169: the container-open probe over the agent's parts. Returns
    (rows, problems, warnings). A part named as a container (container_kind)
    that no ray down its middle gets half-way into is a PROBLEM naming the
    z range that blocks it - a WARNING when the name is ambiguous ("box"),
    when the request or intent says closed/sealed, or when only the
    request/intent (not the part's name) says container. With an Atech
    board (atech=True) ambiguous names are not judged (a case is closed)."""
    import re
    text = " ".join(str(x or "") for x in ((intent or {}).get("description"), request))
    closed = bool(re.search(CLOSED_WORDS, text.lower()))
    kinds = [container_kind(p["label"]) for p in parts]
    if not any(kinds) and len(parts) == 1 and \
            set(_words(text)) & set(CONTAINER_WORDS) and \
            container_kind(parts[0]["label"]) is None and \
            not set(_words(parts[0]["label"])) & set(CONTAINER_NOT):
        kinds = ["from the request"]
    rows, problems, warnings = [], [], []
    for p, kind in zip(parts, kinds):
        if kind is None or (kind == "maybe" and atech):
            continue
        try:
            r = container_open(p["shape"])
        except SlowToTessellate as exc:
            rows.append({"label": p["label"], "kind": kind, "open": None,
                         "skipped": str(exc)})
            continue
        except Exception:                               # noqa: BLE001
            continue
        r.update(label=p["label"], kind=kind)
        rows.append(r)
        if r["open"]:
            continue
        line = ("%s is closed from above: rays straight down the middle of it stop "
                "at z %.2f .. %.2f mm (solid there), at most %.2f of its %.2f mm "
                "height deep, and no side lets them in either - nothing can go in. "
                "If it is meant to hold something, open the top (a ring or rim, "
                "not a disc)" % (
                    p["label"], r["blocked_z"][0], r["blocked_z"][1], r["depth_mm"],
                    r["height_mm"]))
        if kind == "container" and not closed:
            problems.append(line + " (its name says it is a container)")
        else:
            warnings.append(line)
    return rows, problems, warnings


# ------------------------------------------------ solid lid plug (S58)
# eval r8 snap_box: the Lid was a solid 80 x 60 x 11 plug (49 088 mm3, 93 %
# of its box, heavier than the 32 735 mm3 box body) and ./check passed it
# four times; the r7 lid (a plate and a ring lip) fills 38 %.
LID_WORDS = ("lid", "lids", "cover", "covers", "cap", "caps")
LID_FILL = 0.85             # a lid filling more of its tight box than this
LID_PLATE_MM = 6.0          # ...and thicker than this (a flat plate is fine)


def solid_lids(parts, wall_mm=None):
    """S58: parts named lid / cover / cap that fill more than LID_FILL of
    their tight box and are thicker than max(LID_PLATE_MM, 2 x wall_mm) -
    a solid plug where a lid is usually a plate with a ring lip. Returns
    (rows, notes); a NOTE, never a failure (a solid cap can be meant)."""
    try:
        floor = max(LID_PLATE_MM, 2.0 * float(wall_mm)) if wall_mm else LID_PLATE_MM
    except (TypeError, ValueError):
        floor = LID_PLATE_MM
    rows, notes = [], []
    for p in parts:
        if not set(_words(p["label"])) & set(LID_WORDS):
            continue
        try:
            bb = tight(p["shape"])
            box = bb.XLength * bb.YLength * bb.ZLength
            vol = p["shape"].Volume
        except Exception:                               # noqa: BLE001
            continue
        if box <= 1e-9:
            continue
        dims = sorted([bb.XLength, bb.YLength, bb.ZLength])
        fill = vol / box
        row = {"label": p["label"], "fill": round(fill, 3), "volume_mm3": round(vol, 1),
               "box_mm3": round(box, 1), "thin_mm": round(dims[0], 2)}
        rows.append(row)
        if fill > LID_FILL and dims[0] >= floor:
            row["solid"] = True
            notes.append(
                "%s fills %d %% of its %s mm box (%s of %s mm3): a solid plug, not a "
                "plate with a lip (a NOTE, not a failure). A lid's lip is a RING - a "
                "wall-thick frame (outer box minus inner box) that fits inside the "
                "opening; keep the solid only if the user asked for one" % (
                    p["label"], int(round(100 * fill)),
                    " x ".join("%g" % round(x, 2) for x in (bb.XLength, bb.YLength, bb.ZLength)),
                    "{:,.0f}".format(vol), "{:,.0f}".format(box)))
    return rows, notes


# ---------------------------------------- held object's way in (R192)
# D73: a phone tripod mount walled its 75 x 9 mm pocket on all four sides
# and its 2 mm lips left a 5 mm mouth - the 9 mm phone could not get in,
# and every check passed. intent.json may declare the held object:
#     "holds": {"size_mm": [75, 9, 30], "enters": "+Z"}
# size_mm is the object's X, Y, Z as it sits in the part; enters (optional)
# is the side it goes in from (+Z = from above). The probe below looks for
# a straight way in from outside to where the object sits.
HOLDS = "holds"
HOLD_CELLS = 60000          # voxels over a part's box, at most
HOLD_MIN_CELLS = 3          # the object's smallest side spans at least this
HOLD_CLEAR_MM = 0.2         # footprint shrunk by this each side (a clearance)
HOLD_PARTS = 4              # parts looked at, largest box first
HOLD_BUDGET_S = 4.0         # the whole probe; a part not reached is not judged
HOLD_DIRS = ("+Z", "-Y", "+Y", "-X", "+X", "-Z")
HOLD_FORM = ('%s holds must be {"size_mm": [x, y, z], "enters": "+Z"} (the held '
             'object\'s X, Y, Z as it sits in the part; enters, optional, is the side '
             'it goes in from: +Z = from above)')


def read_holds(intent):
    """(size [x, y, z], enters "+Z" or None) of intent.json "holds"; None
    when there is none; raises ValueError when it is malformed."""
    h = (intent or {}).get(HOLDS)
    if h is None:
        return None
    if not isinstance(h, dict):
        raise ValueError
    size = [float(x) for x in h["size_mm"]]
    if len(size) != 3 or min(size) <= 0:
        raise ValueError
    enters = h.get("enters")
    if enters is not None:
        enters = str(enters).strip().upper()
        if enters in ("X", "Y", "Z"):
            enters = "+" + enters
        if enters not in HOLD_DIRS:
            raise ValueError
    return size, enters


def _occupancy(shape, h):
    """(occ bool (nx, ny, nz), lo corner of cell 0, h): voxels of `shape`'s
    tight box plus one air cell each side, filled by ray parity on its
    tessellation (_parity_inside)."""
    import numpy as np
    bb = tight(shape)
    blo = np.array([bb.XMin, bb.YMin, bb.ZMin])
    bhi = np.array([bb.XMax, bb.YMax, bb.ZMax])
    n = np.maximum(1, np.ceil((bhi - blo) / h - 1e-9).astype(int)) + 2
    lo = (blo + bhi) / 2.0 - n * h / 2.0
    axes = [lo[i] + (np.arange(n[i]) + 0.5) * h for i in range(3)]
    X, Y, Z = np.meshgrid(*axes, indexing="ij")
    Q = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    occ = np.zeros(len(Q), dtype=bool)
    inb = np.all((Q >= blo) & (Q <= bhi), axis=1)
    _P, T = _tess(shape)
    if inb.any():
        occ[inb] = _parity_inside(Q[inb], T)
    return occ.reshape(tuple(n)), lo, T


def _rsum(P, du, dv):
    """Sums of every du x dv rectangle (all positions, every layer) from the
    2D prefix sums P (Nu+1, Nv+1, Nt)."""
    return P[du:, dv:] - P[:-du, dv:] - P[du:, :-dv] + P[:-du, :-dv]


def _sweep(occ, h, k, sign, foot, length, extent):
    """One way in: the object (footprint `foot` = (nu, nv) cells across
    axis k, `length` mm along it) goes in from the `sign` side of axis k.
    Per footprint position: how deep it gets straight in from outside
    before material stops it (reach), whether it is held there (material
    at its sides, or stopped by a floor and touching a side), and the
    longest free stretch BEHIND the first stop (a seat it cannot reach).
    Returns {"ok", "hidden", "ok_at", "hidden_at", "need"} with positions
    as (a, b, t_first, t_run_lo, t_run_hi) in the flipped grid."""
    import numpy as np
    A = np.moveaxis(occ, k, -1)
    if sign > 0:
        A = A[:, :, ::-1]
    Nu, Nv, Nt = A.shape
    nu, nv = min(foot[0], Nu), min(foot[1], Nv)
    P = np.zeros((Nu + 1, Nv + 1, Nt), dtype=np.int32)
    P[1:, 1:] = A.cumsum(0).cumsum(1)
    W = _rsum(P, nu, nv)
    blocked = W > 0
    first = np.where(blocked.any(-1), blocked.argmax(-1), Nt)
    reach = np.clip(first - 1, 0, Nt - 2) * h
    # the longest free stretch after the first stop, and where it ends
    run = np.zeros(first.shape, dtype=int)
    best = np.zeros(first.shape, dtype=int)
    end = np.zeros(first.shape, dtype=int)
    seen = np.zeros(first.shape, dtype=bool)
    for t in range(Nt - 1):             # the far air cell is not a seat
        b = blocked[..., t]
        seen |= b
        run = np.where(b, 0, run + 1)
        better = seen & ~b & (run > best)
        best = np.where(better, run, best)
        end = np.where(better, t, end)
    # material beside the footprint along the reached path: 4 sides
    S1 = np.pad(_rsum(P, 1, nv), ((1, 1), (0, 0), (0, 0)))
    S2 = np.pad(_rsum(P, nu, 1), ((0, 0), (1, 1), (0, 0)))
    Wu, Wv = W.shape[0], W.shape[1]
    sides = np.zeros(first.shape, dtype=int)
    last = np.clip(first - 1, 0, Nt - 1)[..., None]
    for S in (S1[0:Wu], S1[nu + 1:nu + 1 + Wu], S2[:, 0:Wv], S2[:, nv + 1:nv + 1 + Wv]):
        C = S.cumsum(-1)
        got = np.take_along_axis(C, last, -1)[..., 0] - C[..., 0]
        sides += (got > 0).astype(int)
    stopped = first < Nt - 1
    held = (sides >= 2) | (stopped & (sides >= 1))
    need = 0.5 * min(length, extent)
    ok = (reach >= need - h) & held
    hidden = (reach < need - h) & (best * h >= need - h)

    def pick(mask, score):
        idx = np.argwhere(mask)
        if not len(idx):
            return None
        s = score[mask]
        top = idx[s >= s.max()]
        c = top.mean(axis=0)
        a, b = top[int(np.argmin(((top - c) ** 2).sum(axis=1)))]
        return (int(a), int(b), int(first[a, b]), int(end[a, b] - best[a, b] + 1),
                int(end[a, b]))
    return {"ok": bool(ok.any()), "hidden": bool(hidden.any()), "need": need,
            "ok_at": pick(ok, reach), "hidden_at": pick(hidden, best),
            "shape": (Nu, Nv, Nt), "foot": (nu, nv)}


def _mouth(shape, T, k, uv, centre, ts):
    """Exact free widths across the way in at the points `centre` (u, v)
    and k in `ts` (world): per point, rays from it along -u/+u and -v/+v
    on the tessellation. [(t, width_u, width_v)] - 0 where the point is in
    material, inf where a ray meets nothing."""
    import numpy as np
    pts = []
    for t in ts:
        p = [0.0, 0.0, 0.0]
        p[k], p[uv[0]], p[uv[1]] = t, centre[0], centre[1]
        pts.append(p)
    if not pts:
        return []
    inside = points_inside(shape, pts, 1e-3)
    Q = np.array(pts, dtype=float)
    widths = []
    for axis in uv:
        tot = np.zeros(len(Q))
        for sgn in (-1.0, 1.0):
            d = np.zeros(3)
            d[axis] = sgn
            dist, _i = _cast(T, Q, d, eps=1e-6)
            tot = tot + dist
        widths.append(tot)
    return [(float(ts[i]), 0.0 if inside[i] else float(widths[0][i]),
             0.0 if inside[i] else float(widths[1][i])) for i in range(len(pts))]


def _hold_part(shape, size, enters, t_end):
    """The way-in probe on one part: every side for the declared
    orientation (size = X, Y, Z), then the other orientations. Returns a
    dict: "ways" [(orientation, dir, sweep, geometry)] that let it in,
    "blocked" the best seat it cannot reach (declared first), or
    {"skipped": why}."""
    import itertools
    import time
    import numpy as np
    bb = tight(shape)
    ext = [bb.XLength, bb.YLength, bb.ZLength]
    vol = max(1e-9, (ext[0] + 1) * (ext[1] + 1) * (ext[2] + 1))
    h = max((vol / HOLD_CELLS) ** (1.0 / 3.0), 0.05)
    if min(size) < HOLD_MIN_CELLS * h:
        return {"skipped": "the object's %g mm side is too small for the part's size "
                           "at this resolution (%.2f mm voxels)" % (min(size), h)}
    occ, lo, T = _occupancy(shape, h)
    orients = [tuple(size)] + [p for p in itertools.permutations(size) if p != tuple(size)]
    seen = set()
    ways, blocked = [], []
    for oi, dims in enumerate(orients):
        if dims in seen:
            continue
        seen.add(dims)
        order = ([enters] if enters else []) + [d for d in HOLD_DIRS if d != enters]
        for dname in order:
            if time.time() > t_end:
                return {"ways": ways, "blocked": blocked, "h": h, "timed_out": True,
                        "lo": lo, "T": T, "occ": occ.shape}
            k, sign = "XYZ".index(dname[1]), (1 if dname[0] == "+" else -1)
            u, v = [i for i in range(3) if i != k]
            foot = tuple(max(1, int(np.floor((dims[i] - 2 * HOLD_CLEAR_MM) / h + 1e-9)))
                         for i in (u, v))
            sw = _sweep(occ, h, k, sign, foot, dims[k], ext[k])
            geo = {"k": k, "sign": sign, "uv": (u, v), "dims": dims, "dir": dname,
                   "declared": oi == 0 and (enters is None or dname == enters)}
            if sw["ok"]:
                ways.append((oi, dname, sw, geo))
            elif sw["hidden"]:
                blocked.append((oi, dname, sw, geo))
        if ways and ways[0][0] == 0:
            break                       # the declared orientation gets in
    return {"ways": ways, "blocked": blocked, "h": h, "lo": lo, "T": T,
            "occ": occ.shape}


def _world(res, geo, sw, at):
    """World (centre u, centre v) of a footprint position, and a function
    giving the k coordinate of a flipped-grid layer."""
    h, lo, n = res["h"], res["lo"], res["occ"]
    k, (u, v), sign = geo["k"], geo["uv"], geo["sign"]
    fu, fv = sw["foot"]
    cu = lo[u] + (at[0] + fu / 2.0) * h
    cv = lo[v] + (at[1] + fv / 2.0) * h

    def layer(t):
        i = n[k] - 1 - t if sign > 0 else t
        return float(lo[k] + (i + 0.5) * h)
    return (float(cu), float(cv)), layer


def hold_probe(parts, intent, budget_s=HOLD_BUDGET_S):
    """R192 (D73): can the held object intent.json "holds" declares get to
    where it sits? Per part (largest box first): the object's box, shrunk by
    HOLD_CLEAR_MM a side, is pushed straight in from each side of the part;
    it gets in when it reaches half its own length (or half the part) deep
    and has material beside it there. A seat behind a narrower mouth - room
    for it that it cannot reach - is what D73 was.

    Returns (row or None, problems, warnings, notes). A PROBLEM only when no
    side and no orientation lets it in AND the exact mouth (rays on the
    tessellation, at the middle of the way in) is narrower than the object;
    a WARNING when the side intent.json names is blocked but another one is
    open, or when no part has room for it at all; a NOTE when the voxel
    probe and the exact mouth disagree (CANNOT DETERMINE)."""
    import time
    try:
        got = read_holds(intent)
    except (KeyError, TypeError, ValueError):
        return None, [HOLD_FORM % INTENT], [], []
    if got is None or not parts:
        return None, [], [], []
    size, enters = got
    t0 = time.time()
    t_end = t0 + budget_s
    order = sorted(parts, key=lambda p: -_box_volume(p["shape"]))[:HOLD_PARTS]
    obj = " x ".join("%g" % x for x in size)
    row = {"size_mm": size, "enters": enters, "parts": []}
    results = []
    for p in order:
        if time.time() > t_end:
            row["parts"].append({"label": p["label"], "skipped": "time cap"})
            continue
        try:
            res = _hold_part(p["shape"], size, enters, t_end)
        except SlowToTessellate as exc:
            res = {"skipped": str(exc)}
        except Exception as exc:                        # noqa: BLE001
            res = {"skipped": "could not run: %s" % exc}
        results.append((p, res))
    row["seconds"] = round(time.time() - t0, 3)
    problems, warnings, notes = [], [], []
    good = [(p, r) for p, r in results if r.get("ways")]
    for p, r in results:
        if r.get("skipped"):
            row["parts"].append({"label": p["label"], "skipped": r["skipped"]})
    if good:
        # declared orientation and side first, then declared orientation
        def rank(item):
            p, r = item
            oi, dname, _sw, geo = r["ways"][0]
            return (0 if geo["declared"] else 1, oi)
        good.sort(key=rank)
        p, r = good[0]
        oi, dname, sw, geo = r["ways"][0]
        way = _way_facts(p, r, sw, geo, "ok_at")
        row.update(way=way, label=p["label"], verdict="PASS")
        # the voxel footprint is up to a cell narrower than the object: the
        # exact mouth decides whether it truly clears (a mouth 8 mm across
        # for a 9 mm object passed the voxels - a snap fit at best)
        m = way.get("mouth")
        du, dv = (geo["dims"][i] for i in geo["uv"])
        if m is not None and (m[1] < du - 0.05 or m[2] < dv - 0.05):
            row["verdict"] = "TIGHT"
            warnings.append(
                "%s: the held object (holds %s mm) goes in from %s only through a "
                "mouth narrower than itself - %s. It gets in only if the part flexes "
                "(a snap fit): say so in your reply, or widen the mouth" % (
                    p["label"], obj, dname, _mouth_text(way)))
        if enters and not geo["declared"]:
            blk = next((b for b in r["blocked"] if b[3]["declared"]), None)
            said = ""
            if blk is not None:
                bf = _way_facts(p, r, blk[2], blk[3], "hidden_at")
                said = " (%s)" % _mouth_text(bf)
            warnings.append(
                "%s: the held object (holds %s mm) cannot go in from %s as intent.json "
                "says%s; it does go in from %s%s. Say in your reply which way it goes "
                "in, or open the side you meant" % (
                    p["label"], obj, enters, said, dname,
                    "" if oi == 0 else " turned to %s mm (X x Y x Z)" % " x ".join(
                        "%g" % x for x in geo["dims"])))
        return row, problems, warnings, notes
    blocked = [(p, r, b) for p, r in results for b in r.get("blocked") or []]
    unjudged = [p["label"] for p, r in results if r.get("skipped") or r.get("timed_out")] + [
        p["label"] for p in order if not any(q is p for q, _r in results)]
    if not blocked:
        if unjudged:
            row["verdict"] = "CANNOT DETERMINE"
            notes.append(
                "holds: CANNOT DETERMINE (a NOTE, not a pass) whether the held object "
                "(%s mm) can reach its seat: %s not probed (%s). Look at check.png and "
                "say in your reply how it goes in" % (
                    obj, ", ".join(unjudged), "; ".join(
                        "%s: %s" % (q["label"], q["skipped"]) for q in row["parts"]
                        if q.get("skipped")) or "time cap"))
        elif results:
            row["verdict"] = "NO SEAT"
            warnings.append(
                "holds: no part has room for the held object (%s mm, the X x Y x Z it "
                "sits in): it fits nowhere, whichever way it is turned. Check the "
                "size in intent.json against the part's pocket" % obj)
        return row, problems, warnings, notes
    blocked.sort(key=lambda x: (0 if x[2][3]["declared"] else 1, x[2][0]))
    p, r, (oi, dname, sw, geo) = blocked[0]
    bf = _way_facts(p, r, sw, geo, "hidden_at")
    row.update(blocked=bf, label=p["label"])
    fu, fv = (geo["dims"][i] - 2 * HOLD_CLEAR_MM for i in geo["uv"])
    m = bf.get("mouth")
    line = ("%s: the held object (holds %s mm) cannot reach its seat - %s. There is "
            "room for it behind that (%s), but no side lets it in, whichever way it "
            "is turned. Leave it a way in: an open end or top, or a mouth at least as "
            "wide as the object plus clearance" % (
                p["label"], obj, _mouth_text(bf), bf["seat"]))
    if m is not None and m[1] >= fu - 0.05 and m[2] >= fv - 0.05:
        row["verdict"] = "CANNOT DETERMINE"
        notes.append(line + " - CANNOT DETERMINE (a NOTE): the mouth measured on the "
                     "way in is not narrower than the object, so something off its "
                     "middle stops it; look at check.png")
    elif r.get("timed_out"):
        # the time cap stopped the probe before every side and turn of this
        # part was tried: "no side lets it in" is not measured
        row["verdict"] = "CANNOT DETERMINE"
        notes.append(line + " - CANNOT DETERMINE (a NOTE): the probe hit its time cap "
                     "before trying every side; look at check.png")
    else:
        row["verdict"] = "BLOCKED"
        problems.append(line)
    return row, problems, warnings, notes


def _box_volume(shape):
    try:
        bb = tight(shape)
        return bb.XLength * bb.YLength * bb.ZLength
    except Exception:                                   # noqa: BLE001
        return 0.0


def _way_facts(p, r, sw, geo, which):
    """Measured facts of one way in (which="ok_at") or of the stop in
    front of an unreachable seat (which="hidden_at"): the side, the stop,
    the exact mouth (narrowest free widths at the footprint's middle)."""
    at = sw[which]
    (cu, cv), layer = _world(r, geo, sw, at)
    k, (u, v), h = geo["k"], geo["uv"], r["h"]
    a, b, first, run_lo, run_hi = at
    if which == "ok_at":
        ts = list(range(1, max(2, first)))
    else:
        ts = list(range(max(1, first), max(first + 1, run_lo)))
    if len(ts) > 30:
        ts = [ts[int(i * (len(ts) - 1) / 29.0)] for i in range(30)]
    shape = p["shape"]
    rows = _mouth(shape, r["T"], k, (u, v), (cu, cv), [layer(t) for t in ts])
    import numpy as np
    fu, fv = (geo["dims"][i] - 2 * HOLD_CLEAR_MM for i in (u, v))
    out = {"dir": geo["dir"], "axis": "XYZ"[k], "across": "XYZ"[u] + "XYZ"[v],
           "dims": list(geo["dims"]), "at": [round(cu, 2), round(cv, 2)], "stop": None}
    bb = tight(shape)
    lo_b = (bb.XMin, bb.YMin, bb.ZMin)
    hi_b = (bb.XMax, bb.YMax, bb.ZMax)
    sign = geo["sign"]
    # the exact stop: rays straight in over the footprint (7 x 7), nearest hit
    g = np.linspace(-0.5, 0.5, 7)
    Q = np.zeros((49, 3))
    Q[:, u] = cu + np.repeat(g, 7) * fu
    Q[:, v] = cv + np.tile(g, 7) * fv
    start = (hi_b[k] + 1.0) if sign > 0 else (lo_b[k] - 1.0)
    Q[:, k] = start
    d = np.zeros(3)
    d[k] = -sign
    dist, _i = _cast(r["T"], Q, d)
    if np.isfinite(dist).any():
        out["stop"] = round(float(start - sign * dist.min()), 2) + 0.0
    if rows:
        worst = min(rows, key=lambda x: min(x[1] - fu, x[2] - fv))
        out["mouth"] = [round(worst[0], 2), round(worst[1], 2), round(worst[2], 2)]
    if which == "hidden_at":
        # the room behind the stop, exact along k through the footprint's middle
        mk = layer(0.5 * (run_lo + run_hi))
        M = Q.copy()
        M[:, k] = mk
        vox = sorted((layer(run_lo) - h / 2.0, layer(run_hi) + h / 2.0))
        span = []
        for j, sgn in enumerate((-1.0, 1.0)):
            dd = np.zeros(3)
            dd[k] = sgn
            dk, _i = _cast(r["T"], M, dd, eps=1e-6)
            span.append(mk + sgn * float(dk.min()) if np.isfinite(dk).any() else vox[j])
        z0, z1 = span
        out["seat_span"] = [round(z0, 2) + 0.0, round(z1, 2) + 0.0]
        out["seat"] = "%s %.2f .. %.2f" % ("xyz"[k], z0, z1)
    return out


def _mouth_text(f):
    """'going in from +Z it stops at z 38.00: the mouth there is 75.00 x 5.00
    mm (X x Y) for a 75 x 9 mm object'."""
    u, v = f["across"]
    du, dv = (f["dims"]["XYZ".index(u)], f["dims"]["XYZ".index(v)])
    m = f.get("mouth")
    stop = ("it stops at %s %.2f" % (f["axis"].lower(), f["stop"])
            if f.get("stop") is not None else "it is stopped")
    if m is None:
        return "going in from %s %s" % (f["dir"], stop)
    w = lambda x: "open" if x == float("inf") else "%.2f" % x   # noqa: E731
    return ("going in from %s %s: the narrowest mouth on the way in is %s x %s mm "
            "(%s x %s, at %s %.2f) for a %g x %g mm object" % (
                f["dir"], stop, w(m[1]), w(m[2]), u, v, f["axis"].lower(), m[0], du, dv))


def hold_text(row):
    """The HOLDS line for a passing probe."""
    f = row.get("way") or {}
    m = f.get("mouth")
    u, v = f.get("across", "??")
    w = lambda x: "open" if x == float("inf") else "%.2f" % x   # noqa: E731
    return ("%s: the held object (%s mm) goes in from %s%s" % (
        row.get("label"), " x ".join("%g" % x for x in row["size_mm"]), f.get("dir"),
        ", narrowest mouth on the way in %s x %s mm (%s x %s)" % (w(m[1]), w(m[2]), u, v)
        if m else ""))


# ------------------------------------------------ revolute motion (R202)
# D77: a hinged lid whose pin axis sat 3 mm inside the back face could not
# open - its rear strip swung into the back wall from the first degree
# (10.2 mm3 at 5 deg, 235 at 90) - and every static check passed. intent
# .json may declare a part that turns:
#     "motion": [{"part": "Lid", "axis": [[x, y, z], [dx, dy, dz]],
#                 "range_deg": [0, 90]}]
# the axis point and direction with the part as built (closed); it turns
# by the right-hand rule about the direction through range_deg. The sweep
# rotates a copy in MOTION_STEP_DEG steps and fails at the first angle
# where it shares more than MIN_OVERLAP_MM3 with any other part.
MOTION = "motion"
MOTION_STEP_DEG = 5.0       # <= 10 (R202); D77's lid hit at 5 deg
MOTION_BUDGET_S = 8.0       # the whole sweep; not reached = not judged
MOTION_FORM = ('%s motion must be [{"part": "Lid", "axis": [[x, y, z], [dx, dy, dz]], '
               '"range_deg": [0, 90]}] (the part\'s label, a point on its turning axis '
               'and the axis direction with the part as built; it turns by the right-hand '
               'rule about that direction through range_deg)')


def read_motion(intent):
    """[{"part", "point" (3), "dir" (3, unit), "range" (a, b)}] of intent
    .json "motion"; [] when there is none; ValueError when malformed."""
    import math
    m = (intent or {}).get(MOTION)
    if m is None:
        return []
    if isinstance(m, dict):
        m = [m]
    if not isinstance(m, list) or not m:
        raise ValueError
    out = []
    for e in m:
        if not isinstance(e, dict) or not isinstance(e.get("part"), str):
            raise ValueError
        ax = e["axis"]
        if isinstance(ax, dict):
            ax = [ax["point"], ax["dir"]]
        pt, dr = ([float(x) for x in ax[0]], [float(x) for x in ax[1]])
        rng = [float(x) for x in e["range_deg"]]
        if len(pt) != 3 or len(dr) != 3 or len(rng) != 2 or rng[0] == rng[1]:
            raise ValueError
        if not all(math.isfinite(x) for x in pt + dr + rng):
            raise ValueError                    # nan / inf would crash the sweep
        n = sum(x * x for x in dr) ** 0.5
        if n < 1e-9 or abs(rng[1] - rng[0]) > 360.0:
            raise ValueError
        out.append({"part": e["part"], "point": pt, "dir": [x / n for x in dr],
                    "range": rng})
    return out


def _angles(a, b, step=MOTION_STEP_DEG):
    """a .. b in equal steps of at most `step` (both ends included)."""
    import math
    n = max(1, int(math.ceil(abs(b - a) / step - 1e-9)))
    return [a + (b - a) * i / float(n) for i in range(n + 1)]


def _turned(shape, point, dr, deg):
    import FreeCAD as App
    s = shape.copy()
    if deg:
        s.rotate(App.Vector(*point), App.Vector(*dr), deg)
    return s


def _hit(moving, others, deg, point, dr, boxes):
    """(label, mm3) of the first other part the turned copy overlaps by
    more than MIN_OVERLAP_MM3, or None."""
    s = _turned(moving, point, dr, deg)
    sb = s.BoundBox                 # a bound: may send a clear pair to common()
    for o in others:
        if not sb.intersect(boxes[o["label"]]):
            continue
        v = s.common(o["shape"]).Volume
        if v > MIN_OVERLAP_MM3:
            return o["label"], v
    return None


def motion_probe(parts, intent, intended=(), budget_s=MOTION_BUDGET_S):
    """R202 (D77): sweep each part intent.json "motion" declares about its
    axis through its range and find the first angle where it hits another
    part. parts: [{"label", "shape"}] (and "name", optional). Returns (row
    or None, problems, warnings, notes); row = {"parts": [{"part",
    "verdict" PASS | BLOCKED | CANNOT DETERMINE, "range_deg", "step_deg",
    "positions", "blocked_at", "by", "volume_mm3", "reverse"}]}.

    A PROBLEM names the first blocked angle, the part hit and the shared
    volume, plus whether the part turns clear the other way (a reversed
    axis direction). A part not built yet, a heavy (mesh-derived) shape or
    the time cap: a NOTE (CANNOT DETERMINE), never a pass. Pairs listed in
    INTENDED_OVERLAPS (`intended`) are not compared."""
    import time
    try:
        motions = read_motion(intent)
    except (KeyError, IndexError, TypeError, ValueError):
        return None, [MOTION_FORM % INTENT], [], []
    if not motions:
        return None, [], [], []
    t0 = time.time()
    t_end = t0 + budget_s
    singles, pairs = _norm_intended(intended)
    by = {}
    for p in parts:
        for k in (p.get("name"), p["label"]):
            if k:
                by.setdefault(k, p)
    rows, problems, warnings, notes = [], [], [], []
    for m in motions:
        p = by.get(m["part"])
        a, b = m["range"]
        rng = "%g .. %g deg" % (a, b)
        row = {"part": m["part"], "range_deg": [a, b], "axis": [m["point"], m["dir"]],
               "step_deg": round(abs(b - a) / max(1, len(_angles(a, b)) - 1), 3)}
        rows.append(row)
        if p is None:
            row["verdict"] = "CANNOT DETERMINE"
            notes.append("motion: no part labelled %s to sweep (the parts are: %s) - "
                         "CANNOT DETERMINE until it is built" % (
                             m["part"], ", ".join(sorted({q["label"] for q in parts}))
                             or "none"))
            continue
        row["part"] = p["label"]
        it = {"name": p.get("name") or p["label"], "label": p["label"]}
        others = [o for o in parts if o is not p and not _allowed(
            it, {"name": o.get("name") or o["label"], "label": o["label"]},
            singles, pairs)]
        if heavy(p["shape"]) or any(heavy(o["shape"]) for o in others):
            row["verdict"] = "CANNOT DETERMINE"
            notes.append("motion: %s not swept - a mesh-derived solid has no exact "
                         "boolean volume here (CANNOT DETERMINE)" % p["label"])
            continue
        boxes = {o["label"]: o["shape"].BoundBox for o in others}
        angles = _angles(a, b)
        hit, done = None, 0
        for deg in angles:
            if time.time() > t_end:
                break
            got = _hit(p["shape"], others, deg, m["point"], m["dir"], boxes)
            done += 1
            if got:
                hit = (deg, got[0], got[1])
                break
        row["positions"] = done
        if hit is None and done < len(angles):
            row["verdict"] = "CANNOT DETERMINE"
            notes.append("motion: %s swept %s only up to %g deg (time cap) - CANNOT "
                         "DETERMINE beyond" % (p["label"], rng, angles[done - 1]
                                                if done else a))
            continue
        if hit is None:
            row["verdict"] = "PASS"
            continue
        deg, other, vol = hit
        row.update(verdict="BLOCKED", blocked_at=round(deg, 3) + 0.0, by=other,
                   volume_mm3=round(vol, 3))
        # the other way round: a reversed axis direction, or a hinge that
        # only fails one way
        rev = None
        if deg != a and time.time() < t_end:
            back = _hit(p["shape"], others, a - (deg - a), m["point"], m["dir"], boxes)
            rev = back is None
            row["reverse_clear_at"] = [round(a - (deg - a), 3) + 0.0, rev]
        fix = ("move the axis ON or OUTSIDE the face it swings past (a lid's pin at "
               "or behind the back face's top edge), or cut clearance where it hits")
        if deg == a:
            why = ("it is already in %s %s" % (
                other, "as built (0 deg, the start of its range)" if a == 0 else
                "at %g deg, the start of its range" % a))
            hint = "Start the range where the part sits clear, or " + fix
        else:
            why = "it hits %s at %g deg" % (other, deg)
            hint = fix[0].upper() + fix[1:]
            if rev:
                hint = ("Turned the other way (%g deg) it is clear: if that is the way "
                        "it opens, reverse the axis direction in intent.json; if not, %s"
                        % (a - (deg - a), fix))
        problems.append(
            "motion: %s cannot turn %s about the axis through (%s) along (%s): %s - "
            "%s mm3 shared. %s" % (
                p["label"], rng, ", ".join("%g" % round(x, 3) for x in m["point"]),
                ", ".join("%g" % round(x, 4) for x in m["dir"]), why,
                "{:,.2f}".format(vol), hint))
    return {"parts": rows, "seconds": round(time.time() - t0, 3)}, problems, warnings, notes


def motion_text(r):
    """The MOTION line for a part that turned clear."""
    return ("%s turns %g .. %g deg about its axis clear of every other part "
            "(%d positions, %g deg steps)" % (
                r["part"], r["range_deg"][0], r["range_deg"][1], r.get("positions", 0),
                r["step_deg"]))


# ------------------------------------------------------------ mates (R213)
# D79 (S7 c2n3): a pegboard hook whose pegs and 25.4 mm pitch were right
# but whose 8 x 8 arm root ran 4.9 mm into the 1/4 in board the prompt fully
# specified (125.2 mm3) - nothing placed the board, so nothing could see it.
# intent.json "mates" declares the object the part mounts on; ./check
# builds it and every part must stay out of it - only pegs may pass, inside
# the holes (a peg wider than its hole hits the plate and is reported).
MATES = "mates"
MATE_TOL_MM3 = MIN_OVERLAP_MM3      # shared volume above this fails
MATE_REACH_MM = 0.5                 # a part farther than this from the plate's
                                    # front face does not rest on it (a NOTE)
MATE_HOLES_MAX = 2000               # holes cut in the reference plate, at most
MATES_FORM = ('%s mates must be [{"name": "pegboard", "thickness_mm": 6.35, '
              '"hole_d_mm": 6.35, "pitch_mm": 25.4, "face": "+Y", "hole_at": [x, y, z]}] '
              '(the plate the part mounts on: "face" is the side of its front face that '
              'looks at the part, "hole_at" the centre of one hole ON that front face - '
              'the plate lies behind it; optional "size_mm": [w, h] across the face, '
              'centred on hole_at, else it covers the part with a pitch to spare; '
              'optional "part": the label it is checked against, else every part; '
              'pitch_mm may be [pu, pv] along the face\'s two axes, X before Y before Z)')
_FACES = {"+X": (0, 1), "-X": (0, -1), "+Y": (1, 1), "-Y": (1, -1), "+Z": (2, 1), "-Z": (2, -1)}


def read_mates(intent):
    """[{"name", "t", "d", "pitch" (pu, pv), "k", "s", "at" (3), "size" or
    None, "part" or None}] of intent.json "mates"; [] when there is none;
    ValueError when malformed."""
    import math
    m = (intent or {}).get(MATES)
    if m is None:
        return []
    if isinstance(m, dict):
        m = [m]
    if not isinstance(m, list) or not m:
        raise ValueError
    out = []
    for e in m:
        if not isinstance(e, dict):
            raise ValueError
        if isinstance(e.get("plate"), dict):
            e = dict(e["plate"], **{k: v for k, v in e.items() if k != "plate"})
        face = str(e["face"]).strip().upper()
        if face not in _FACES:
            raise ValueError
        t, d = float(e["thickness_mm"]), float(e["hole_d_mm"])
        p = e["pitch_mm"]
        pitch = [float(x) for x in p] if isinstance(p, (list, tuple)) else [float(p)] * 2
        at = [float(x) for x in e.get("hole_at", e.get("at"))]
        size = e.get("size_mm")
        size = None if size is None else [float(x) for x in size]
        vals = [t, d] + pitch + at + (size or [])
        if (len(pitch) != 2 or len(at) != 3 or (size is not None and len(size) != 2)
                or not all(math.isfinite(x) for x in vals) or t <= 0 or d <= 0
                or min(pitch) <= d or (size is not None and min(size) <= 0)):
            raise ValueError
        part = e.get("part")
        if part is not None and not isinstance(part, str):
            raise ValueError
        k, s = _FACES[face]
        out.append({"name": str(e.get("name") or "mating plate"), "t": t, "d": d,
                    "pitch": pitch, "k": k, "s": s, "face": face, "at": at,
                    "size": size, "part": part})
    return out


def mate_plate(m, around=None):
    """The reference plate of one read_mates() entry as a Part solid, with
    its holes. `around`: a BoundBox the plate must cover (the parts), with
    a pitch to spare each side, when the entry gives no size_mm. Returns
    (plate, holes compound, hole count)."""
    import math
    import FreeCAD as App
    import Part
    k, s, at = m["k"], m["s"], m["at"]
    u, v = [i for i in range(3) if i != k]
    if m["size"] is not None:
        span = [(at[u] - m["size"][0] / 2.0, at[u] + m["size"][0] / 2.0),
                (at[v] - m["size"][1] / 2.0, at[v] + m["size"][1] / 2.0)]
    else:
        lo = (around.XMin, around.YMin, around.ZMin)
        hi = (around.XMax, around.YMax, around.ZMax)
        span = [(min(lo[u], at[u]) - m["pitch"][0], max(hi[u], at[u]) + m["pitch"][0]),
                (min(lo[v], at[v]) - m["pitch"][1], max(hi[v], at[v]) + m["pitch"][1])]
    front = at[k]
    back = front - s * m["t"]
    org, ext = [0.0] * 3, [0.0] * 3
    org[k], ext[k] = min(front, back), m["t"]
    for i, ax in enumerate((u, v)):
        org[ax], ext[ax] = span[i][0], span[i][1] - span[i][0]
    plate = Part.makeBox(ext[0], ext[1], ext[2], App.Vector(*org))
    cols = []
    for i, ax in enumerate((u, v)):
        p = m["pitch"][i]
        n0 = int(math.ceil((span[i][0] + m["d"] / 2.0 - at[ax]) / p))
        n1 = int(math.floor((span[i][1] - m["d"] / 2.0 - at[ax]) / p))
        cols.append([at[ax] + n * p for n in range(n0, n1 + 1)])
    if len(cols[0]) * len(cols[1]) > MATE_HOLES_MAX:
        raise ValueError("more than %d holes" % MATE_HOLES_MAX)
    dr = [0.0] * 3
    dr[k] = 1.0
    cyl = []
    for a in cols[0]:
        for b in cols[1]:
            c = [0.0] * 3
            c[u], c[v], c[k] = a, b, min(front, back) - 1.0
            cyl.append(Part.makeCylinder(m["d"] / 2.0, m["t"] + 2.0, App.Vector(*c),
                                         App.Vector(*dr)))
    holes = Part.makeCompound(cyl)
    if cyl:
        plate = plate.cut(holes)
    return plate, holes, len(cyl)


def mates_probe(parts, intent):
    """R213: each reference object intent.json "mates" declares, built and
    tested against the installed part(s). parts: [{"label", "shape"}].
    Returns (rows, problems, notes). A PROBLEM for every part sharing more
    than MATE_TOL_MM3 with the plate (the pegs in their holes share none),
    naming the volume, how deep it runs in behind the front face and
    where; a NOTE for a part that does not reach the plate's front face."""
    import time
    try:
        mates = read_mates(intent)
    except (KeyError, IndexError, TypeError, ValueError):
        return [], [MATES_FORM % INTENT], []
    rows, problems, notes = [], [], []
    names = "XYZ"
    for m in mates:
        t0 = time.time()
        test = [p for p in parts if m["part"] is None or m["part"] in (
            p["label"], p.get("name"))]
        if not test:
            notes.append("mates: no part labelled %s to test against the %s (the parts "
                         "are: %s) - CANNOT DETERMINE" % (
                             m["part"], m["name"],
                             ", ".join(sorted(p["label"] for p in parts)) or "none"))
            rows.append({"name": m["name"], "verdict": "CANNOT DETERMINE"})
            continue
        around = None
        for p in test:
            b = tight(p["shape"])
            if around is None:
                around = b
            else:
                around.add(b)
        try:
            plate, holes, n_holes = mate_plate(m, around)
        except ValueError as exc:
            problems.append("mates: the %s cannot be built: %s" % (m["name"], exc))
            continue
        k, s = m["k"], m["s"]
        front = m["at"][k]
        row = {"name": m["name"], "face": m["face"], "front_at": front,
               "holes": n_holes, "parts": []}
        rows.append(row)
        for p in test:
            sh = p["shape"]
            r = {"part": p["label"]}
            row["parts"].append(r)
            if heavy(sh):
                r["verdict"] = "CANNOT DETERMINE"
                notes.append("mates: %s not tested against the %s - a mesh-derived "
                             "solid has no exact boolean volume here" % (p["label"],
                                                                          m["name"]))
                continue
            c = sh.common(plate)
            vol = c.Volume
            r["volume_mm3"] = round(vol, 3)
            try:
                pegs = sh.common(holes) if n_holes else None
                r["pegs_in_holes"] = 0 if pegs is None else sum(
                    1 for x in pegs.Solids if x.Volume > MATE_TOL_MM3)
            except Exception:                           # noqa: BLE001
                r["pegs_in_holes"] = None
            if vol > MATE_TOL_MM3:
                cb = tight(c)
                lo = (cb.XMin, cb.YMin, cb.ZMin)[k]
                hi = (cb.XMax, cb.YMax, cb.ZMax)[k]
                depth = front - lo if s > 0 else hi - front
                cm = c.Solids[0].CenterOfMass if len(c.Solids) == 1 else _mean_centre(c)
                r.update(verdict="FAIL", depth_mm=round(depth, 3),
                         at=[round(cm.x, 2), round(cm.y, 2), round(cm.z, 2)],
                         box=[round(x, 2) for x in (cb.XMin, cb.YMin, cb.ZMin,
                                                    cb.XMax, cb.YMax, cb.ZMax)])
                problems.append(
                    "mates: %s runs %.2f mm into the %s - %s mm3 shared with it, around "
                    "(%s) (x %.2f .. %.2f, y %.2f .. %.2f, z %.2f .. %.2f). The %s's "
                    "front face is at %s = %g (it lies behind that, %g mm thick, "
                    "holes diameter %g on a %g x %g grid through (%s)): start the part "
                    "at the front face - only pegs narrower than the holes, in them, "
                    "may pass into it" % (
                        p["label"], depth, m["name"], "{:,.2f}".format(vol),
                        ", ".join("%.1f" % x for x in r["at"]),
                        cb.XMin, cb.XMax, cb.YMin, cb.YMax, cb.ZMin, cb.ZMax,
                        m["name"], names[k].lower(), front, m["t"], m["d"],
                        m["pitch"][0], m["pitch"][1],
                        ", ".join("%g" % x for x in m["at"])))
                continue
            r["verdict"] = "PASS"
            # resting on it: the gap from the part to the plate (a plate of
            # many holes is judged by contact only - d None, apart)
            try:
                d, exact = distance(sh, plate)
            except Exception:                           # noqa: BLE001
                d, exact = None, False
            r["gap_mm"] = None if d is None else round(d, 3)
            if (d is not None and d > MATE_REACH_MM) or (d is None and exact):
                notes.append("mates: %s stays %s off the %s (front face at %s = %g) - "
                             "it does not rest on it" % (
                                 p["label"], "%.2f mm" % d if d is not None else
                                 "clear", m["name"], names[k].lower(), front))
        row["seconds"] = round(time.time() - t0, 3)
    return rows, problems, notes


def _mean_centre(shape):
    """Volume-weighted centre of a compound's solids (a Vector)."""
    import FreeCAD as App
    tot, acc = 0.0, App.Vector(0, 0, 0)
    for x in shape.Solids:
        acc += x.CenterOfMass * x.Volume
        tot += x.Volume
    return acc * (1.0 / tot) if tot > 0 else App.Vector(0, 0, 0)


def mates_text(row):
    """The MATES line for a reference object every tested part clears."""
    ps = row.get("parts") or []
    return ("%s (front face %s, %d holes) built from intent.json: %s" % (
        row["name"], row["face"], row["holes"], "; ".join(
            "%s shares %g mm3 with it%s" % (
                r["part"], r.get("volume_mm3", 0.0),
                "" if r.get("pegs_in_holes") is None else
                ", %d peg(s) in its holes" % r["pegs_in_holes"])
            for r in ps)))


# --------------------------------------------- joint engagement (R212)
# D78 (S7 c1n4 desk clock, c2n4 plant monitor): "push-fit" end caps that
# were flat 2 mm plates only touching the case - distance 0, common 0, no
# lip, plug or hook - passed every check. A part whose every contact with
# the rest is such a touch falls off: it must reach into the part it
# closes - material of one inside the other's outline (a lip or plug in the
# opening, a skirt over the end, snap hooks) at least ENGAGE_MM deep.
ENGAGE_MM = 1.0
ENGAGE_TOUCH_MM = 1e-3      # boxes this close are looked at
PUSH_WORDS = (r"\b(?:push|press|friction|snap|interference)[- ]?(?:fit\w*|on|in)\b",
              r"\bsnaps?\b", r"\bclips? (?:on|in|onto|into)\b")


def declared_push(request, label=""):
    """True when the user's message (or the part's label) calls a joint a
    push / press / snap fit."""
    import re
    text = " ".join(x for x in (request or "", label or "") if x).lower()
    return any(re.search(p, text) for p in PUSH_WORDS)


def _engage_depth(a, b):
    """How far `a`'s material reaches inside `b`'s tight box: the smallest
    side of the box round a ∩ box(b) (0.0 when they share no volume) - a
    lip 3 mm down into a case's opening is 3, a plate lying on its end 0."""
    import FreeCAD as App
    import Part
    bb = tight(b)
    if bb.XLength <= 0 or bb.YLength <= 0 or bb.ZLength <= 0:
        return 0.0
    box = Part.makeBox(bb.XLength, bb.YLength, bb.ZLength,
                       App.Vector(bb.XMin, bb.YMin, bb.ZMin))
    c = a.common(box)
    if c.Volume <= MIN_OVERLAP_MM3:
        return 0.0
    cb = tight(c)
    return min(cb.XLength, cb.YLength, cb.ZLength)


SCREW_AXIS_MM = 0.3         # bores of two parts on one axis line within this
                            # are a screw / pin joint through both


def _screwed(a, b):
    """The number of axis lines on which a bore of `a` and a bore of `b`
    line up (a screw through a lid's clearance hole into a boss's pilot
    hole: the r7 nightlight's screwed Lid, M3 3.2 over 2.5) - a fastened
    joint, not a touch. Diameters may differ; cavities are not bores."""
    ba = [x for x in bores(a) if not x["cavity"]]
    if not ba:
        return 0
    bb = [x for x in bores(b) if not x["cavity"]]
    n = 0
    for x in ba:
        for y in bb:
            if x["axis"] != y["axis"]:
                continue
            gap = sum((p - q) ** 2 for p, q in zip(x["at"], y["at"])) ** 0.5
            if gap <= SCREW_AXIS_MM:
                n += 1
                break
    return n


def joint_probe(parts, request=None, cap=MAX_PAIRS_OBJECTS):
    """R212: every part that touches another part and engages none of the
    parts it touches. parts: [{"label", "shape"}] (the agent's own bodies,
    not the Atech board or modules). Returns (rows, problems, notes).
    rows: [{"part", "touches": [labels], "engaged": label or None,
    "depth_mm", "fastened" (bores lined up through both: screws or pins),
    "only_touches"}]. A part overlapping another (shared volume) is the
    overlap check's; a part touching nothing is floating(), never judged
    here; a heavy (mesh-derived) shape is not judged. A part is not named
    when everything it touches is named already and smaller (the case
    behind two flat end caps: the caps are named)."""
    parts = [p for p in parts[:cap] if p.get("shape") is not None
             and getattr(p["shape"], "Solids", None)]
    if len(parts) < 2:
        return [], [], []
    boxes = [tight(p["shape"]) for p in parts]
    pair = {}

    def contact(i, j):
        """(touch True/False/None, depth: None = they share volume)"""
        key = (min(i, j), max(i, j))
        if key not in pair:
            a, b = parts[key[0]]["shape"], parts[key[1]]["shape"]
            # the booleans first (15-20 ms each on the doorbell's case and
            # cap); distToShape (70 ms there) only for a pair that does not
            # engage - an engaged pair needs no touch test, one that is not
            # in contact at all is floating()'s
            try:
                if a.common(b).Volume > MIN_OVERLAP_MM3:
                    t, d = True, None
                else:
                    d = max(_engage_depth(a, b), _engage_depth(b, a))
                    t = True if d >= ENGAGE_MM else touching(a, b)
                    if t and d < ENGAGE_MM and _screwed(a, b):
                        d = "screwed"
            except Exception:                           # noqa: BLE001
                t, d = None, 0.0
            pair[key] = (t, d)
        return pair[key]
    rows, problems, notes = [], [], []
    for i, p in enumerate(parts):
        if heavy(p["shape"]):
            continue
        touches, engaged, depth, unsure = [], None, 0.0, False
        for j, q in enumerate(parts):
            if i == j or _bb_gap(boxes[i], boxes[j]) > ENGAGE_TOUCH_MM:
                continue
            if heavy(q["shape"]):
                unsure = True
                continue
            t, d = contact(i, j)
            if t is None:
                unsure = True
                continue
            if not t:
                continue
            touches.append(q["label"])
            if d is None or d == "screwed":
                # an overlap (the overlap check's) or screws through both
                engaged, depth = q["label"], d
                break
            if d >= ENGAGE_MM:
                engaged, depth = q["label"], d
                break
            depth = max(depth, d)
        if not touches:
            continue
        row = {"part": p["label"], "touches": touches, "engaged": engaged,
               "depth_mm": round(depth, 3) if isinstance(depth, float) else None}
        if depth == "screwed":
            row["fastened"] = "coaxial bores (screws or pins through both)"
        rows.append(row)
        if engaged is not None:
            continue
        if unsure:
            notes.append("joint: %s only touches %s, and a contact with another part "
                         "could not be measured - CANNOT DETERMINE whether it engages"
                         % (p["label"], ", ".join(touches)))
            continue
        row["only_touches"] = True
        row["_i"], row["_depth"] = i, depth
    # a case touching its two flat end caps only touches too - but the caps
    # are what falls off: a part is not named when everything it touches
    # is named already and smaller than it
    named = {r["part"] for r in rows if r.get("only_touches")}
    vol = {p["label"]: p["shape"].Volume for p in parts}
    for row in rows:
        if not row.get("only_touches"):
            continue
        i, depth = row.pop("_i"), row.pop("_depth")
        p, touches = parts[i], row["touches"]
        if all(t in named and vol.get(t, 0.0) < vol[p["label"]] for t in touches):
            row["only_touches"] = "its parts are named"
            continue
        push = declared_push(request, p["label"])
        problems.append(
            "joint: %s only touches %s - a face touch (0 mm apart, 0 mm3 shared), "
            "nothing of it reaches %g mm or more inside the other's outline (%.2f mm "
            "measured): no lip, plug or hook in the opening, so it falls off%s. Give "
            "it a lip or plug that goes into the opening (0.1-0.2 mm clearance), a "
            "skirt over the end, or snap hooks (cad.snap_fit_pair); or fuse it to %s "
            "if it is one body" % (
                p["label"], " and ".join(touches), ENGAGE_MM, depth or 0.0,
                " - the request calls it a push/snap fit, and a push fit needs "
                "something to push in" if push else "", touches[0]))
    return rows, problems, notes


# ------------------------------------------------------------ fingerprint
def fingerprint(shape):
    """A cheap identity: rounded volume, area, face/vertex counts, the
    BoundBox, the placement, plus - under 500 faces - a hash of every
    face's (surface type, area, centre of mass) and every vertex.
    Equal fingerprints -> the body did not change (PRD S24).

    Not a hash of exportBrepToString(): MEASURED 2026-09-25, the same shape
    exports 'Locations 0' before a recompute and an explicit identity
    location after it, so the BREP text of one unchanged body differs."""
    try:
        bb = shape.BoundBox
        pl = shape.Placement
        fp = (round(shape.Volume, 3), round(shape.Area, 3), len(shape.Faces),
              len(shape.Vertexes),
              tuple(round(x, 4) for x in (bb.XMin, bb.YMin, bb.ZMin,
                                          bb.XMax, bb.YMax, bb.ZMax)),
              tuple(round(x, 6) for x in tuple(pl.Base) + tuple(pl.Rotation.Q)))
        if len(shape.Faces) < FP_BREP_FACES:
            parts = []
            for f in shape.Faces:
                c = f.CenterOfMass
                parts.append("%s %.4f %.4f %.4f %.4f" % (
                    type(f.Surface).__name__, f.Area, c.x, c.y, c.z))
            for v in shape.Vertexes:
                p = v.Point
                parts.append("v %.4f %.4f %.4f" % (p.x, p.y, p.z))
            fp += (hashlib.sha1("\n".join(sorted(parts)).encode()).hexdigest(),)
        return fp
    except Exception:                                   # noqa: BLE001
        return None


# ----------------------------------------------------------- view record
VIEW_FN = "__atech_view__"


class _ViewRewrite(ast.NodeTransformer):
    """X.ViewObject.attr = value   ->   __atech_view__(X, 'attr', value)"""

    def __init__(self):
        super().__init__()
        self.rewritten = 0

    def visit_Assign(self, node):
        self.generic_visit(node)
        if len(node.targets) != 1:
            return node
        t = node.targets[0]
        if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Attribute)
                and t.value.attr == "ViewObject"):
            call = ast.Call(func=ast.Name(VIEW_FN, ast.Load()),
                            args=[t.value.value, ast.Constant(t.attr), node.value],
                            keywords=[])
            self.rewritten += 1
            return ast.copy_location(ast.Expr(call), node)
        return node


def record_view(code, counts=None):
    """The code as an AST with every direct `X.ViewObject.attr = v` turned
    into a recorder call. Line numbers stay the agent's. Headless only: in
    the GUI the real ViewObject exists. `counts` (a dict) gets
    counts["rewritten"] = how many lines were turned into recorder calls."""
    rw = _ViewRewrite()
    tree = rw.visit(ast.parse(code))
    ast.fix_missing_locations(tree)
    if counts is not None:
        counts["rewritten"] = rw.rewritten
    return tree


VIEW_KEYS = ("ShapeColor", "Transparency", "LineColor", "PointColor",
             "DiffuseColor", "Visibility", "DisplayMode", "LineWidth")


def view_recorder(store):
    """The function installed as __atech_view__: keeps JSON-safe values of
    the display properties Studio can carry over, per object Name."""
    def rec(obj, attr, value):
        name = getattr(obj, "Name", None)
        if not name or attr not in VIEW_KEYS:
            return
        store.setdefault(name, {})[attr] = _jsonable(value)
    return rec


def _jsonable(v):
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    try:
        return [float(x) for x in v]
    except Exception:                                   # noqa: BLE001
        return str(v)
