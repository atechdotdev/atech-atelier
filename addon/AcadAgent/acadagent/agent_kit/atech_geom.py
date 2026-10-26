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
                            working face that leave the product (R152);
                            the face is the module's own, in world (R240)
    enclosure(...)          per Atech module, how much of it is inside the
                            product's body (R241)
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
    face_open_problems      R270: a placed module that must be open, sealed,
                            fails (quality mode); floors per kind (screen
                            active area, ToF aperture, sound share)
    thin_wall_problems      R270: a wall under 0.6 mm, re-measured exactly
                            (wall_exact), proud details excused
    through_intended        R270: intent.json "through_holes"
    screw_pilots(parts)     R270: the pilot each screw ends in vs its size
    board_retention(...)    R270: some part within 0.5 mm of the board
    use_check_cache / save_check_cache
                            R270: unchanged pairs' overlap results kept in
                            the workspace between ./check runs
    archetype_problems(...) R440: the request's archetype measured on owner
                            images (ARCHETYPE_GATES: handheld screen region
                            and grips, robot face window, speaker height and
                            grille, vehicle length and wheels, lamp height
                            and light, clock display, fan guard)
    fastening(parts, code)  R441: housing parts that meet, joined by a screw
                            through both, a snap / clip or a pin - or not
    cable_holders(...)      R442: a cabled module held on two sides or more
    confirm_mesh_overlap    R443: a sampled overlap's exact volume, the same
                            on every run
    thread_engagement       R444: a screw's overlap with the 0.85 d pilot it
                            bites in is its thread, not an overlap
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
MAX_PAIRS_OBJECTS = 120     # pairwise checks are O(n^2): cap the inputs
                            # (R250: was 30 - a 38-part toy car lost its last 8
                            # parts; boxes are compared first, see check.py
                            # OVERLAP_CAP and test_kit_round12 timings)
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
BOX_CACHE = 256             # R250: boxes kept (a box is a few floats)
_BOUND = {}                 # hashCode -> (shape, BoundBox)


def tight(shape):
    """Tight axis-aligned box. Falls back to BoundBox only if OCCT refuses.
    Cached per shape and handed out as a copy (R129: 10 ms a call on the
    16 069-face board solid, asked several times per check)."""
    import FreeCAD as App
    # R250: 256 entries - at 16 a 31-part product cleared the store on every
    # pass, and floating() alone re-measured boxes for 4 s on toy_car
    return App.BoundBox(_cached(_TIGHT, shape, _optimal, size=BOX_CACHE))


def _bound(shape):
    """shape.BoundBox, cached per shape (3 ms a call on the board solid)."""
    import FreeCAD as App
    return App.BoundBox(_cached(_BOUND, shape, lambda s: s.BoundBox, size=BOX_CACHE))


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
TESS_CACHE = 128            # R250: shapes kept (101 tessellations, 3.9 s, on
                            # toy_car's 31 parts when 16 were kept)
EXACT_POINTS = 200          # fewer points than this on a light shape: all exact
EXACT_WORK = 6000           # R250: ... and points x faces under this


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
        if len(_TESS) >= TESS_CACHE:   # R250: was 16 - a 31-part car re-tessellated
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
    if len(_PREP) >= TESS_CACHE:
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
    # R250: few points on a shape of few faces - OCCT exact per point; many
    # points or many faces (90 points x a 403-face tyre: 1.1 s, 12 ms a
    # point) - parity, with OCCT only for the points near the surface below
    if not is_heavy and ((len(vecs) < EXACT_POINTS
                          and len(vecs) * n_faces(shape) < EXACT_WORK)
                         or tess_slow(shape)):
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


# R443 (round 1): the sampled overlap test (a mesh, or a heavy shape)
# gave the speaker's microphone a PASS on one run and "12 of 1458 points
# inside" on the next - a few surface points 0.01-0.02 mm deep, found or
# not as the sample set fell. A sampled hit on under CONFIRM_SHARE of its
# points is now CONFIRMED before it is reported: an exact boolean common
# volume for two shapes, else exact signed depths (OCCT's classification
# and distToShape into the solid, parity and point-triangle distance into
# the mesh) at the corners of deterministic triangles (the mesh's own, a
# fresh tessellation of a COPY of the solid - never the triangulation an
# earlier stage left on it), integrated linearly over each triangle into
# a volume. Reported only over MIN_OVERLAP_MM3, like any boolean overlap.
CONFIRM_SHARE = 0.05
CONFIRM_POINTS = 1500       # samples per side tested exactly, at most
CONFIRM_DEPTHS = 300        # inside points whose exact depth is measured, at most


def _stride(P, cap):
    return P[::max(1, -(-len(P) // cap))] if len(P) > cap else P


def _pos_integral(T, S):
    """Sum over triangles T (m,3,3) of the integral of max(0, s) - s linear
    over each triangle, S (m,3) its values at the corners (closed form)."""
    import numpy as np
    if not len(T):
        return 0.0
    A = 0.5 * np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)
    S = np.sort(S, axis=1)[:, ::-1]                  # a >= b >= c
    a, b, c = S[:, 0], S[:, 1], S[:, 2]
    out = np.zeros(len(T))
    allp = c >= 0
    out[allp] = A[allp] * (a + b + c)[allp] / 3.0
    one = (a > 0) & (b <= 0)
    den = (a - b) * (a - c)
    out[one] = A[one] * a[one] ** 3 / (3.0 * np.where(den[one] > 1e-15, den[one], 1e-15))
    two = (b > 0) & (c < 0)
    den2 = (c - a) * (c - b)
    neg = A[two] * c[two] ** 3 / (3.0 * np.where(den2[two] > 1e-15, den2[two], 1e-15))
    out[two] = A[two] * (a + b + c)[two] / 3.0 - neg
    return float(np.maximum(out, 0.0).sum())


def _fresh_tess(shape):
    """(points, facets) of a fresh tessellation of a copy of `shape` (the
    copy carries no triangulation, so the result does not depend on what
    meshed the shape before)."""
    import numpy as np
    try:
        c = shape.copy(True, False)
    except TypeError:
        c = shape.copy()
    pts, fac = c.tessellate(_deflection(shape))
    P = np.array([(p.x, p.y, p.z) for p in pts], dtype=float).reshape(-1, 3)
    F = np.array(fac, dtype=int).reshape(-1, 3)
    return P, F


def _exact_depths(solid, Q):
    """Exact distance of each point to the boundary of `solid` -
    distToShape against the faces near the points only."""
    import numpy as np
    import FreeCAD as App
    import Part
    lo, hi = Q.min(axis=0) - 1.0, Q.max(axis=0) + 1.0
    faces = []
    for f in solid.Faces:
        b = f.BoundBox
        if b.XMax >= lo[0] and b.XMin <= hi[0] and b.YMax >= lo[1] and b.YMin <= hi[1] \
                and b.ZMax >= lo[2] and b.ZMin <= hi[2]:
            faces.append(f)
    comp = Part.makeCompound(faces or solid.Faces)
    out = np.zeros(len(Q))
    for i, q in enumerate(Q):
        try:
            out[i] = comp.distToShape(Part.Vertex(App.Vector(*q)))[0]
        except Exception:                               # noqa: BLE001
            out[i] = 0.0
    return out


def _side_volume(P, F, lo, hi, inside_of, depth_of):
    """R443: the volume between one body's surface (P, F) and the other's,
    over the triangles with a corner inside the other: the signed depth
    (inside +, outside -) integrated linearly over each triangle. None
    when too many corners would need an exact depth (a big overlap)."""
    import numpy as np
    inb = np.nonzero(np.all((P >= lo) & (P <= hi), axis=1))[0]
    if not len(inb):
        return 0.0
    if len(inb) > CONFIRM_POINTS:
        inb = _stride(inb, CONFIRM_POINTS)
    ins = np.zeros(len(P), dtype=bool)
    ins[inb] = inside_of(P[inb])
    tri = np.nonzero(ins[F].any(axis=1))[0]
    if not len(tri):
        return 0.0
    vid = np.unique(F[tri])
    if len(vid) > CONFIRM_DEPTHS:
        return None
    dep = np.zeros(len(P))
    dep[vid] = depth_of(P[vid])
    sgn = np.where(ins, 1.0, -1.0)
    Ft = F[tri]
    return _pos_integral(P[Ft], (dep * sgn)[Ft])


def confirm_mesh_overlap(solid, mesh, tol=0.01):
    """R443: the overlap volume (mm3) of a solid and a mesh from exact
    depths - deterministic for the same geometry. The mesh's own
    triangles with a corner inside the solid (OCCT's exact
    classification), their corners' signed depths exact (distToShape),
    integrated over each triangle; and the same for a fresh tessellation
    of a copy of the solid against the mesh (parity, point-triangle
    distance - exact on a polyhedron). Both sides seeing it: their mean;
    one side: that one. A big overlap (more corners than CONFIRM_DEPTHS)
    is returned as inf (it is real)."""
    import numpy as np
    import FreeCAD as App
    sb, mb = tight(solid), mesh.BoundBox
    lo = np.array([max(sb.XMin, mb.XMin), max(sb.YMin, mb.YMin), max(sb.ZMin, mb.ZMin)]) - 1.0
    hi = np.array([min(sb.XMax, mb.XMax), min(sb.YMax, mb.YMax), min(sb.ZMax, mb.ZMax)]) + 1.0
    if np.any(lo > hi):
        return 0.0
    pts, fac = mesh.Topology
    MP = np.array([(p.x, p.y, p.z) for p in pts], dtype=float).reshape(-1, 3)
    MF = np.array(fac, dtype=int).reshape(-1, 3)
    if not len(MF):
        return 0.0
    MT = MP[MF]

    def in_solid(Q):
        return np.array([bool(solid.isInside(App.Vector(*q), tol, False)) for q in Q])
    v1 = _side_volume(MP, MF, lo, hi, in_solid, lambda Q: _exact_depths(solid, Q))
    SP, SF = _fresh_tess(solid)
    v2 = 0.0
    if len(SF):
        def in_mesh(Q):
            ins = _parity_inside(Q, MT)
            d = _pt_tri_dist(Q, MT, limit=tol)
            return ins & ~np.isfinite(d)
        v2 = _side_volume(SP, SF, lo, hi, in_mesh, lambda Q: _pt_tri_dist(Q, MT))
    if v1 is None or v2 is None:
        return float("inf")
    if v1 > 0 and v2 > 0:
        return 0.5 * (v1 + v2)
    return max(v1, v2)


def confirm_shape_overlap(a, b):
    """R443: the exact common volume of two shapes (mm3), or None when the
    boolean fails."""
    try:
        return float(a.common(b).Volume)
    except Exception:                                   # noqa: BLE001
        return None


def overlaps(items, intended=(), min_volume=MIN_OVERLAP_MM3,
             cap=MAX_PAIRS_OBJECTS, confirm=None):
    """Pairwise intersections between bodies.

    items: dicts {"name", "label", "shape" (Part.Shape) or "mesh" (Mesh.Mesh,
    already in world coordinates) , "role" (AtechRole or None)}.
    Two Atech parts (board, modules) are never compared with each other:
    atech_ports.check owns that. Returns (list of hits, note or None).
    A hit is {"a", "b", "volume_mm3"} or {"a", "b", "mesh_points_inside",
    "mesh_points_tested"} (a mesh, or a heavy shape judged on sampled
    surface points - R129: one boolean with the board solid costs 1-1.6 s).
    Boxes are the TIGHT ones: a loose BoundBox sent bodies 0.3 mm apart
    into a boolean. confirm (R443; default: quality mode): a sampled hit
    on under CONFIRM_SHARE of its points is confirmed by an exact volume
    before it is reported - fast mode keeps the sampled verdict."""
    if confirm is None:
        confirm = quality_mode()
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
    fps = {}
    store = _pair_store()                               # R270: {} without a workspace

    def fp(it):
        k = id(it)
        if k not in fps:
            fps[k] = item_fingerprint(it)
        return fps[k]
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
            # R270: an unchanged pair (both fingerprints, both labels) is
            # not measured again - the boolean is most of a repeat ./check
            key = None
            if store is not None:
                fa, fb = fp(a), fp(b)
                if fa is None or fb is None:
                    store["nofp"] = store.get("nofp", 0) + 1
                else:
                    key = _pair_key("overlap", a["label"], fa, b["label"], fb, min_volume,
                                    "exact" if confirm else "sampled")
                    if key in store["data"]:
                        store["hits"] += 1
                        if store["data"][key]:
                            hits.append(dict(store["data"][key]))
                        continue
            n0 = len(hits)
            try:
                if a.get("shape") is not None and b.get("shape") is not None:
                    if not a["shape"].Solids or not b["shape"].Solids:
                        continue
                    if heavy(a["shape"]) or heavy(b["shape"]):
                        n_in, n_t = _shape_points_inside(a["shape"], b["shape"])
                        if n_in:
                            hit = {"a": a["label"], "b": b["label"],
                                   "mesh_points_inside": n_in, "mesh_points_tested": n_t}
                            if confirm and n_in < CONFIRM_SHARE * n_t:
                                # R443: a few points - the exact volume decides
                                v = confirm_shape_overlap(a["shape"], b["shape"])
                                if v is not None:
                                    hit = dict(hit, volume_mm3=round(v, 3),
                                               confirmed="exact boolean") \
                                        if v > min_volume else None
                            if hit:
                                hits.append(hit)
                        if key is None:
                            continue
                        store["data"][key] = hits[-1] if len(hits) > n0 else None
                        store["dirty"] = True
                        store["miss"] = store.get("miss", 0) + 1
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
                    hit = None
                    if n_in:
                        hit = {"a": a["label"], "b": b["label"],
                               "mesh_points_inside": n_in, "mesh_points_tested": n_t}
                        if at is not None:
                            hit["at"] = at
                        if confirm and n_in < CONFIRM_SHARE * n_t:
                            # R443: a few sampled points - their exact depths
                            # decide (deterministic: the same geometry, the
                            # same verdict on every run)
                            try:
                                v = confirm_mesh_overlap(solid["shape"], mesh_item["mesh"])
                            except Exception:           # noqa: BLE001
                                v = None
                            if v is not None and v == float("inf"):
                                hit["confirmed"] = "exact depths (too many to sum: real)"
                            elif v is not None:
                                hit = dict(hit, volume_mm3=round(v, 3),
                                           confirmed="exact depths") \
                                    if v > min_volume else None
                    if hit:
                        hits.append(hit)
            except Exception:                           # noqa: BLE001
                continue
            if key is not None:
                store["data"][key] = hits[-1] if len(hits) > n0 else None
                store["dirty"] = True
                store["miss"] = store.get("miss", 0) + 1
    return hits, note


# ------------------------------------------------- repeat-check cache (R270)
# R270 (round 1: ./check took 141-225 s on spline shells, and every fix
# round paid it again): the pairwise results of unchanged bodies are kept
# in the workspace between ./check runs, keyed by both bodies' geometry
# fingerprints and labels. check.py turns it on (use_check_cache); Studio's
# own build never reads it. A changed body changes its fingerprint, so a
# stale entry is never read; the file is capped and rewritten whole.
CHECK_CACHE = ".atech_check_cache.json"
CHECK_CACHE_MAX = 4000              # entries kept, at most
CHECK_CACHE_VERSION = 2              # R443: 2 - sampled overlaps confirmed
_CACHE = [None]                     # {"path", "data", "dirty", "hits"} or None


def use_check_cache(workspace):
    """R270: read the workspace's pair cache (check.py, once per run)."""
    import json
    import os
    _CACHE[0] = None
    if not workspace or not os.path.isdir(workspace):
        return None
    path = os.path.join(workspace, CHECK_CACHE)
    data = {}
    raw = _read_regular(path)
    if raw is not None:
        try:
            got = json.loads(raw.decode("utf-8"))
            if isinstance(got, dict) and got.get("v") == CHECK_CACHE_VERSION \
                    and isinstance(got.get("pairs"), dict):
                data = got["pairs"]
        except (ValueError, UnicodeDecodeError):
            data = {}
    _CACHE[0] = {"path": path, "data": data, "dirty": False, "hits": 0}
    return _CACHE[0]


def check_cache_stats():
    """R270: {"entries", "hits", "miss", "nofp"} of this run's pair cache."""
    c = _CACHE[0]
    if c is None:
        return None
    return {"entries": len(c["data"]), "hits": c["hits"], "miss": c.get("miss", 0),
            "nofp": c.get("nofp", 0)}


def save_check_cache():
    """R270: write the pair cache back (only when something was added).
    Never raises; returns the number of cache hits of this run."""
    import json
    import os
    c = _CACHE[0]
    if c is None:
        return 0
    if c["dirty"]:
        data = c["data"]
        if len(data) > CHECK_CACHE_MAX:
            data = dict(list(data.items())[-CHECK_CACHE_MAX:])
        try:
            if os.path.islink(c["path"]):
                os.unlink(c["path"])
            tmp = c["path"] + ".tmp"
            body = json.dumps({"v": CHECK_CACHE_VERSION, "pairs": data}, default=float)
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(body)
            os.replace(tmp, c["path"])
        except (OSError, TypeError, ValueError):
            pass
    return c["hits"]


def _pair_store():
    return _CACHE[0]


def _pair_key(kind, la, fa, lb, fb, *extra):
    return hashlib.sha1(repr((kind, la, fa, lb, fb) + tuple(extra)).encode()).hexdigest()


CACHE_GRID_MM = 0.02         # face boxes quantised to this in the cache key


def cache_fingerprint(shape):
    """R270: the repeat-check cache's identity of a shape: topology counts,
    box, placement and a hash over EVERY face (surface type, edge count,
    the face's box on a CACHE_GRID_MM grid) - no volume, area, centre of
    mass or vertex. MEASURED on the round-1 smart speaker, the same model
    run twice: volumes 1-6 mm3 apart (OCCT's integration on B-splines) and
    a spline seam's vertices 0.07 mm apart, the face boxes within 0.001 -
    fingerprint() keyed all 32 pairs anew (0 hits). Every face counts: a
    hole moved inside a 3000-face shell changes its face's box."""
    def q(x):
        return int(round(x / CACHE_GRID_MM))
    try:
        bb = shape.BoundBox
        pl = shape.Placement
        parts = []
        for f in shape.Faces:
            fb = f.BoundBox
            parts.append("%s %d %d %d %d %d %d %d" % (
                type(f.Surface).__name__, len(f.Edges), q(fb.XMin), q(fb.YMin),
                q(fb.ZMin), q(fb.XMax), q(fb.YMax), q(fb.ZMax)))
        return (len(shape.Solids), len(shape.Faces), len(shape.Edges),
                tuple(q(x) for x in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)),
                tuple(round(x, 5) for x in tuple(pl.Base) + tuple(pl.Rotation.Q)),
                hashlib.sha1("\n".join(sorted(parts)).encode()).hexdigest())
    except Exception:                                   # noqa: BLE001
        return None


def item_fingerprint(it):
    """R270: cache_fingerprint() of an item's shape, or of its mesh
    (points, facets, box) - the identity the repeat-check cache keys on."""
    try:
        if it.get("shape") is not None:
            return cache_fingerprint(it["shape"])
        m = it.get("mesh")
        if m is None:
            return None
        bb = m.BoundBox
        return ("mesh", int(m.CountPoints), int(m.CountFacets),
                tuple(round(x, 4) for x in (bb.XMin, bb.YMin, bb.ZMin,
                                            bb.XMax, bb.YMax, bb.ZMax)),
                round(float(getattr(m, "Area", 0.0) or 0.0), 3))
    except Exception:                                   # noqa: BLE001
        return None


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
    if "volume_mm3" in hit and hit.get("confirmed"):
        return "%s and %s overlap by %s mm3 (%d of %d sampled points inside, confirmed: %s%s)" % (
            hit["a"], hit["b"], hit["volume_mm3"], hit.get("mesh_points_inside", 0),
            hit.get("mesh_points_tested", 0), hit["confirmed"],
            "; around (%s)" % ", ".join("%.1f" % c for c in hit["at"]) if hit.get("at") else "")
    if "volume_mm3" in hit:
        return "%s and %s overlap by %s mm3" % (hit["a"], hit["b"], hit["volume_mm3"])
    return "%s and %s intersect (%d of %d sampled mesh points inside%s)" % (
        hit["a"], hit["b"], hit["mesh_points_inside"], hit["mesh_points_tested"],
        "; around (%s)" % ", ".join("%.1f" % c for c in hit["at"])
        if hit.get("at") else "")


# --------------------------------------------------------------- floating
# R250: floating() on examples/toy_car.py (31 shapes) took 73-85 s, nearly
# all of it in 59 distToShape calls against the 758-face body shell (2-6 s
# each), and a full ./check went over quality mode's 180 s. Three cuts,
# none of which changes a verdict (test_kit_round12.FloatingFast):
#   * a pair is measured once, and a pair found within `gap` clears BOTH
#     bodies (the distance is symmetric);
#   * of a body's box-near neighbours the cheapest is measured first (any
#     one within `gap` clears it), not the one whose box is nearest (the
#     shell's box holds every part: box gap 0, cost 5 s);
#   * a light pair is measured on its NEAR faces only (_near_distance): the
#     faces of each whose box comes within `gap` of the other. The face
#     pair that realises a distance <= gap always survives that cut, so a
#     distance <= gap is exact and "> gap" is an exact verdict.
# FLOAT_BUDGET_S bounds what is left: a body not measured in time is never
# accused (floating is a warning; an unmeasured body is not reported).
FLOAT_BUDGET_S = 45.0
FLOAT_NEAR_FACES = 24       # a light pair with fewer faces in all: distToShape
_FACE_BOXES = {}            # hashCode -> (shape kept alive, [(face, box)])


def _face_boxes(shape):
    return _cached(_FACE_BOXES, shape,
                   lambda s: [(f, f.BoundBox) for f in s.Faces], size=64)


def _box_of_faces(pairs):
    import FreeCAD as App
    bb = App.BoundBox()
    for _f, b in pairs:
        bb.add(b)
    return bb


def _inside_either(a, b):
    """True when a vertex of one solid lies inside the other (distToShape
    reads a body wholly inside another as distance 0; faces alone do not)."""
    for s, o in ((a, b), (b, a)):
        vs = s.Vertexes
        if vs and o.Solids and points_inside(o, [vs[0].Point], 1e-6)[0]:
            return True
    return False


def _near_distance(a, b, gap):
    """R250: (d, trimmed) for a LIGHT pair. d <= gap: the exact distance
    (trimmed False). d > gap: certainly farther than `gap`; d itself is
    then only an upper bound when trimmed is True (faces were left out).
    Faces are kept when their box is within `gap` of the other side's
    kept faces, repeated until nothing more drops (a face pair <= gap
    apart is never dropped: its boxes are <= gap apart)."""
    import Part
    pad = gap + 1e-6
    fa, fb = _face_boxes(a), _face_boxes(b)
    ba, bb = tight(a), tight(b)
    trimmed = False
    for _round in range(4):
        nb = [p for p in fb if _bb_gap(p[1], ba) <= pad]
        na = [p for p in fa if _bb_gap(p[1], bb) <= pad]
        if len(na) == len(fa) and len(nb) == len(fb):
            break
        trimmed = True
        fa, fb = na, nb
        if not fa or not fb:
            break
        ba, bb = _box_of_faces(fa), _box_of_faces(fb)
    if not fa or not fb:
        return (0.0, False) if _inside_either(a, b) else (float("inf"), True)
    if not trimmed:
        return a.distToShape(b)[0], False
    d = Part.makeCompound([p[0] for p in fa]).distToShape(
        Part.makeCompound([p[0] for p in fb]))[0]
    if d > gap and _inside_either(a, b):
        return 0.0, False
    return d, d > gap


def _float_distance(a, b, gap):
    """(d, exact, trimmed) for floating(): distance() for a heavy pair or a
    face of many loops, else _near_distance on a big enough pair."""
    na, nb = n_faces(a), n_faces(b)
    if not na or not nb or na + nb < FLOAT_NEAR_FACES \
            or heavy(a) or heavy(b) or _loop_heavy(a) or _loop_heavy(b):
        d, ex = distance(a, b, limit=gap)
        return d, ex, False
    d, trimmed = _near_distance(a, b, gap)
    return d, True, trimmed


def floating(items, gap=FLOAT_GAP_MM, cap=MAX_PAIRS_OBJECTS, contacts=(),
             skip=(), budget=FLOAT_BUDGET_S):
    """Bodies farther than `gap` from every other body. Only meaningful for
    something meant to be one assembly (a desk stand 30 mm below the desk);
    separate parts laid out apart are legitimately 'floating', so this is a
    warning, never a failure. Returns [{"label", "gap_mm", "exact"}]:
    exact=False means gap_mm is a lower bound (boxes apart). A distance to
    a heavy shape is sampled (R129), an upper bound: it can clear a body
    of floating, never accuse it.
    R250: `contacts` - (label, label) pairs already known to touch (the
    overlap stage's hits): never measured again. `skip` - labels never
    reported (they still count as neighbours). `budget` - seconds; a body
    not settled by then is not reported (see FLOAT_BUDGET_S)."""
    import time
    t0 = time.time()
    items = [it for it in items[:cap] if it.get("shape") is not None]
    if len(items) < 2:
        return []
    n = len(items)
    boxes = [tight(it["shape"]) for it in items]
    faces = [n_faces(it["shape"]) for it in items]
    by_label = {}
    for k, it in enumerate(items):
        by_label.setdefault(it["label"], []).append(k)
    known = {}                  # (i, j), i < j -> (d, exact, trimmed) or None
    for la, lb in contacts or ():
        for i in by_label.get(la, ()):
            for j in by_label.get(lb, ()):
                if i != j:
                    known[(min(i, j), max(i, j))] = (0.0, True, False)
    settled = [False] * n       # a neighbour within gap, or cannot accuse
    skip = set(skip or ())
    out = []

    def measure(i, j):
        key = (min(i, j), max(i, j))
        if key in known:
            return known[key]
        if time.time() - t0 > budget:
            return "late"
        try:
            r = _float_distance(items[key[0]]["shape"], items[key[1]]["shape"], gap)
        except Exception:                               # noqa: BLE001
            r = None
        known[key] = r
        return r

    for i in range(n):
        if settled[i] or items[i]["label"] in skip:
            continue
        cands = sorted((_bb_gap(boxes[i], boxes[j]), j) for j in range(n) if j != i)
        near = [j for g, j in cands if g <= gap]
        if not near:
            out.append({"label": items[i]["label"], "gap_mm": round(cands[0][0], 2),
                        "exact": False})        # a lower bound: boxes are apart
            continue
        near.sort(key=lambda j: ((min(i, j), max(i, j)) not in known, faces[j]))
        accuse, far = True, []
        for j in near:
            r = measure(i, j)
            if r is None or r == "late":
                accuse = False          # could not tell: never accuse
                break
            d, ex, trimmed = r
            if d is None or (not ex and d > gap):
                # judged by contact only, or a sampled upper bound: never
                # accuse (R129)
                accuse = False
                break
            if d <= gap:
                settled[j] = True       # the distance is symmetric
                accuse = False
                break
            far.append((j, d, trimmed))
        settled[i] = True
        if not accuse:
            continue
        # floating: report the exact smallest distance, as before R250 (a
        # trimmed measure is only an upper bound - re-measured in full)
        best, exact = None, True
        for j, d, trimmed in far:
            if trimmed:
                if time.time() - t0 > budget:
                    d, exact = gap, False       # certainly farther than gap
                else:
                    try:
                        d = items[i]["shape"].distToShape(items[j]["shape"])[0]
                    except Exception:                   # noqa: BLE001
                        d, exact = gap, False
            best = d if best is None else min(best, d)
        out.append({"label": items[i]["label"], "gap_mm": round(best, 2), "exact": exact})
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


def _body_box(m):
    """R241: a module's mesh box without what stands proud of its case
    along a working face (a motor shaft, a USB-C shell): those go through
    the wall by design, so they do not 'stick out of the case'."""
    import numpy as np
    box = _mesh_box(m["mesh"])
    try:
        wd = working_dirs(*_module_meta(m))
        if wd is None:
            return box
        P = _mesh_points(m["mesh"])
        mask, _f = _proud_split(P, wd["faces"])
        if mask is None or mask.all():
            return box
        Q = P[~mask]
        return [float(v) for v in np.concatenate([Q.min(axis=0), Q.max(axis=0)])]
    except Exception:                                   # noqa: BLE001
        return box


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
                      case), every module must be inside it too (its box
                      without a shaft or socket shell standing proud of it,
                      R241)
      enclosure       R241: each module against the body itself
                      (enclosure): outside it, sticking out of it, or
                      against an open side fails; its working face may look
                      out through an opening, flush with it
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
                out = _outside(_body_box(m), case)
                side = max(out, key=out.get)
                if out[side] > INSIDE_TOL_MM:
                    problems.append("%s sticks %.1f mm out of the case on %s: "
                                    "grow the case or move the module inside"
                                    % (m["label"], out[side], side))
        # R241: each module against the body itself, not the parts' box
        # (see enclosure). A ribbon cable is no body: left out even when
        # the caller passed it (build.layout_check does).
        body = [p for p in parts if not getattr(
            _doc_object(None, p.get("label")), "AtechCableModule", None)]
        try:
            rows = enclosure(body, board, modules)
        except Exception as exc:                        # noqa: BLE001
            rows = []
            facts["enclosure_error"] = repr(exc)[-300:]
        facts["enclosure"] = rows
        boxed_out = [m["label"] for m in modules if any(
            p.startswith(m["label"] + " sticks ") for p in problems)]
        for line in enclosure_problems(rows):
            # the box test already named it: one line per module is enough
            if not any(line.startswith(lb + " ") for lb in boxed_out):
                problems.append(line)
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


def _doc_object(name=None, label=None):
    """R240: the FreeCAD object of the active document by Name (or Label),
    or None - for callers that pass only {"label", "name", "mesh"} (check.py
    _layout and build.layout_check before R240)."""
    try:
        import FreeCAD
        doc = FreeCAD.ActiveDocument
    except Exception:                                   # noqa: BLE001
        return None
    if doc is None:
        return None
    o = doc.getObject(name) if name else None
    if o is None and label:
        try:
            hits = doc.getObjectsByLabel(label)
        except Exception:                               # noqa: BLE001
            hits = []
        o = hits[0] if hits else None
    return o


def _module_meta(m):
    """R240: (library module name, its X, Y, Z in world) of a module item.
    Taken from the item ("module", "axes") when the caller gave them, else
    read off the document object it names (AtechModule, Placement)."""
    name, axes = m.get("module"), m.get("axes")
    if name and axes:
        return str(name), axes
    o = _doc_object(m.get("name"), m.get("label"))
    if o is not None:
        name = name or (str(getattr(o, "AtechModule", "") or "") or None)
        if not axes:
            try:
                import FreeCAD
                r = o.Placement.Rotation
                axes = [list(r.multVec(FreeCAD.Vector(*e)))
                        for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
            except Exception:                           # noqa: BLE001
                axes = None
    return name, axes


def working_dirs(module_name, axes):
    """R240: a module's working faces in WORLD space, from the library's
    measured frame (atech_ports.measure_module: r along the row, u away
    from the board, d the slide axis; its "faces" - the side a socket or a
    shaft stands proud of, else +u) rotated by the module's own axes. Not
    the board's normal: a module cabled elsewhere (module_placement
    face=...) faces wherever its placement turned it, and a DC motor works
    along its shaft.

    Returns {"up": unit [x, y, z] (+u in world), "faces": [{"word",
    "dir", "proud_mm"}]} or None when the library or the axes are not
    there (the caller falls back to the board normal, as before R240)."""
    import numpy as np
    if not module_name or not axes:
        return None
    try:
        import atech_ports
        feat = atech_ports.measure_module(str(module_name))
    except Exception:                                   # noqa: BLE001
        return None
    A = np.asarray(axes, dtype=float).reshape(3, 3)     # rows: local X, Y, Z in world

    def world(v):
        w = A.T @ np.asarray(v, dtype=float)
        return w / (np.linalg.norm(w) or 1.0)
    faces = []
    for f in feat.get("faces") or ():
        faces.append({"word": f.get("word"), "dir": world(f["local"]),
                      "proud_mm": f.get("proud_mm")})
    return {"up": world(feat["u"]), "faces": faces}


def _proud_split(P, faces):
    """R240: the points of a module that stand proud of its case along a
    working face that has a proud part (a USB-C shell, a motor shaft):
    (mask of those points, the face) for the most proud face, or (None,
    None)."""
    import numpy as np
    best = None
    for f in faces or ():
        if f.get("proud_mm") and (best is None or f["proud_mm"] > best["proud_mm"]):
            best = f
    if best is None:
        return None, None
    s = P @ best["dir"]
    return s > s.max() - float(best["proud_mm"]) + SOCKET_REACH_MM, best


# R250: what may stand in front of a working face without closing it.
# (a) A see-through part - recorded view Transparency >= SEE_THROUGH_PCT
#     (cad.transparency: glass 60, smoked 50, frosted 35; LEDs 20 stay
#     opaque) - passes the rays of an OPTICAL module only: light shines and
#     a screen or a distance sensor sees through a lens, a window or a
#     diffuser. A button cannot be pressed, a speaker or a microphone heard,
#     a temperature sensor ventilated or a plug put in through glass, so a
#     transparent case still seals those.
# (b) A declared cover - intent.json "covers": {"Cap_Plus": "button_p2",
#     "Light_Ring": ["light_p1", "light_p6"]} (part label -> module label or
#     labels): a key cap over a button, a lens or a light pipe over a light.
#     It passes that module's rays only, and only when it really sits in
#     front of that module's working face: a ray from the face meets it
#     within COVER_MM of the face (otherwise a problem - the declaration
#     cannot excuse a wall elsewhere).
SEE_THROUGH_PCT = 30
SEE_THROUGH_MODULES = ("light", "screen", "distance_sensor")
COVER_MM = 3.0
COVERS = "covers"           # the intent.json key
FACE_GRID_FINE = 41         # R250: the grid of a face sealed on FACE_GRID
# R250: a planar face with more than TESS_LOOPS_MAX loops (a 148-hole
# speaker grille) is no longer left out of the probe: its loops are
# discretised into 2-D polygons and a ray crosses it where an even-odd
# point-in-face test puts the crossing inside the material. MEASURED
# 2026-10-20: see test_kit_round12.R250ManyHoleFace (timing printed).
HOLED_DEFLECTION_MM = 0.05  # polygon of a hole's edge: within this of the arc
_VIEW_STORE = [None]        # the last view_recorder's store (check.py's _run)
_HOLED = {}                 # hashCode -> (shape kept alive, (T, planes))


def part_transparency(part, views=None):
    """R250: the view Transparency (0..100) recorded for a face_open part,
    or 0. Looked up in order: part["transparency"], part["view"]
    ["Transparency"], views[label or name]["Transparency"], the document
    object's real ViewObject (GUI), the last view_recorder's store (check.py
    headless: obj.ViewObject.Transparency = ... is recorded there)."""
    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    if part.get("transparency") is not None:
        return num(part["transparency"]) or 0.0
    v = (part.get("view") or {}).get("Transparency")
    if v is not None:
        return num(v) or 0.0
    for key in (part.get("label"), part.get("name")):
        if views and key in views:
            v = (views[key] or {}).get("Transparency")
            if v is not None:
                return num(v) or 0.0
    o = _doc_object(part.get("name"), part.get("label"))
    if o is None:
        return 0.0
    vo = getattr(o, "ViewObject", None)
    if vo is not None:
        return num(getattr(vo, "Transparency", 0)) or 0.0
    store = _VIEW_STORE[0]
    if store:
        v = (store.get(getattr(o, "Name", "")) or {}).get("Transparency")
        return num(v) or 0.0
    return 0.0


def sanitize_covers(value):
    """R250: intent.json "covers" -> ({part label: [module labels]},
    [problems]). Absent -> ({}, [])."""
    if value is None:
        return {}, []
    if not isinstance(value, dict):
        return {}, ['intent.json "covers" must be an object {part label: module '
                    'label or [module labels]}, e.g. {"Cap_Plus": "button_p2"}']
    out, bad = {}, []
    for part, mods in value.items():
        if isinstance(mods, str):
            mods = [mods]
        if (not isinstance(part, str) or not isinstance(mods, list) or not mods
                or not all(isinstance(m, str) and m for m in mods)):
            bad.append('intent.json "covers": %r -> %r is not a part label -> module '
                       'label (or a list of them)' % (part, mods))
            continue
        out[part] = list(mods)
    return out, bad


def _intent_covers():
    """R250: "covers" of the workspace's intent.json when the caller passed
    none - ./check's workspace is its script's folder (ATECH_CHECK_SCRIPT,
    else the current directory). ({}, []) when there is no intent."""
    import os
    script = os.environ.get("ATECH_CHECK_SCRIPT")
    ws = os.path.dirname(os.path.abspath(script)) if script else os.getcwd()
    intent, _bad = read_intent(ws)
    return sanitize_covers((intent or {}).get(COVERS))


def _holed_face(face, deflection=HOLED_DEFLECTION_MM):
    """R250: a planar face as {"o", "n", "u", "v", "seg" (k, 2, 2) 2-D loop
    segments in (u, v)}, or None when it is not planar."""
    import numpy as np
    try:
        surf = face.Surface
        if type(surf).__name__ != "Plane":
            return None
        n = np.array(tuple(face.normalAt(0, 0)), dtype=float)
        o = np.array(tuple(face.Vertexes[0].Point), dtype=float)
    except Exception:                                   # noqa: BLE001
        return None
    B = _basis(n)
    segs = []
    for w in face.Wires:
        try:
            pts = w.discretize(Deflection=deflection)
        except Exception:                               # noqa: BLE001
            return None
        P = np.array([tuple(p) for p in pts], dtype=float)
        if len(P) < 2:
            continue
        P = np.vstack([P, P[:1]])
        uv = np.stack([(P - o) @ B[0], (P - o) @ B[1]], axis=1)
        segs.append(np.stack([uv[:-1], uv[1:]], axis=1))
    if not segs:
        return None
    return {"o": o, "n": B[2], "u": B[0], "v": B[1], "seg": np.concatenate(segs)}


def _tess_holed(shape):
    """R250: (triangles (m,3,3), [planar holed faces]) of a shape that
    _tess refuses (tess_slow): every face of up to TESS_LOOPS_MAX loops
    tessellated on its own, every planar face with more loops as a
    _holed_face. Raises SlowToTessellate when such a face is not planar."""
    import numpy as np
    try:
        key = shape.hashCode()
    except Exception:                                   # noqa: BLE001
        key = None
    hit = _HOLED.get(key) if key is not None else None
    if hit is not None and hit[0].isSame(shape):
        return hit[1]
    dfl = _deflection(shape)
    tris, planes = [], []
    for f in shape.Faces:
        if len(f.Wires) > TESS_LOOPS_MAX:
            h = _holed_face(f)
            if h is None:
                raise SlowToTessellate("a curved face with %d boundary loops"
                                       % len(f.Wires))
            planes.append(h)
            continue
        pts, fac = f.tessellate(dfl)
        if not fac:
            continue
        P = np.array([(p.x, p.y, p.z) for p in pts], dtype=float).reshape(-1, 3)
        tris.append(P[np.array(fac, dtype=int).reshape(-1, 3)])
    T = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
    if key is not None:
        if len(_HOLED) >= 8:
            _HOLED.clear()
        _HOLED[key] = (shape, (T, planes))
    return T, planes


def _cast_holed(planes, Q, d, far=None, eps=1e-4):
    """R250: first hit of the rays Q + s*d, eps < s <= far, on the material
    of planar holed faces (even-odd test against every loop: inside the
    outer loop and outside every hole). Returns (s (n,), face index (n,))
    like _cast."""
    import numpy as np
    n = len(Q)
    dist = np.full(n, np.inf)
    idx = np.full(n, -1, dtype=int)
    d = np.asarray(d, dtype=float)
    d = d / np.linalg.norm(d)
    top = np.inf if far is None else float(far)
    for k, h in enumerate(planes):
        dn = float(d @ h["n"])
        if abs(dn) < 1e-9:
            continue
        s = ((h["o"] - Q) @ h["n"]) / dn
        ok = (s > eps) & (s <= top) & (s < dist)
        if not ok.any():
            continue
        ii = np.nonzero(ok)[0]
        X = Q[ii] + s[ii, None] * d - h["o"]
        pu, pv = X @ h["u"], X @ h["v"]
        a, b = h["seg"][:, 0], h["seg"][:, 1]
        ay, by = a[:, 1][None, :], b[:, 1][None, :]
        straddle = (ay > pv[:, None]) != (by > pv[:, None])
        dy = np.where(by == ay, 1.0, by - ay)
        xc = a[:, 0][None, :] + (pv[:, None] - ay) * (b[:, 0] - a[:, 0])[None, :] / dy
        inside = (np.sum(straddle & (pu[:, None] < xc), axis=1) % 2) == 1
        got = ii[inside]
        dist[got] = s[got]
        idx[got] = k
    return dist, idx


def _cover_gap(T, planes, FP, B, grid_q, d):
    """R250: how far in front of a module's working face a cover is: the
    smallest (hit - face) distance of rays from the face's grid, started at
    the back of the module (so a cap resting ON the face is met at 0), on
    the cover's own surface alone. None when no ray meets it."""
    import numpy as np
    pd = FP @ B[2]
    back = float(pd.max() - pd.min()) + 1.0
    Q = grid_q - (back + FACE_LIFT_MM) * B[2]
    best = np.inf
    if len(T):
        s, _i = _cast(T, Q, d, far=back + FACE_LIFT_MM + COVER_MM + 50.0)
        best = min(best, float(s.min()))
    if planes:
        s, _i = _cast_holed(planes, Q, d, far=back + FACE_LIFT_MM + COVER_MM + 50.0)
        best = min(best, float(s.min()))
    if not np.isfinite(best):
        return None
    return round(best - back - FACE_LIFT_MM, 2)


def face_open(parts, board, modules, far=FACE_FAR_MM, grid=FACE_GRID,
              views=None, covers=None):
    """R152 (D60: a "window over the light" cut in the end lid, the light's
    face 0/169 rays open, reported as success): per seated module, the
    fraction of a grid of rays from its working face, along its outward
    normal, that get out of the product without meeting one of its parts.

    parts    [{"label", "shape", "name" (optional), "transparency" or
             "view" (optional: the recorded view props)}]  the agent's parts
    board    {"label", "mesh"}
    modules  [{"label", "name", "module", "mesh", "axes" (optional: the
             module's X, Y, Z in world)}]
    views    (R250, optional) {part label or Name: {"Transparency": ...}}:
             check.py's recorded view props; without it see
             part_transparency's fallbacks
    covers   (R250, optional) intent.json "covers" {part label: module
             label or [labels]}; None: read from ./check's workspace
             intent.json
    The working face (R164, R240): the module's own measured "up" (the
    library frame, working_dirs) rotated by its axes - for a seated module
    that is the board's normal, for a cabled one wherever module_placement
    turned it; for a USB-C socket the connector mouth, measured from the
    mesh (socket_face) - no mouth found: not judged ("face": None); for a
    DC motor its shaft ("face": "shaft", reported, never judged). Without
    the library or the axes, the board's normal, as before R240. Only the product's parts (product_parts) block a ray - an
    unrelated part elsewhere in the document is not in front of anything.
    R250: a see-through part (SEE_THROUGH_PCT) does not block an optical
    module (SEE_THROUGH_MODULES); a declared cover does not block its
    module when it sits within COVER_MM in front of the face (else the row
    carries a "cover_problems" line); a planar face with too many holes to
    tessellate is cast against exactly (_cast_holed). A part still too slow
    (a curved holed face) is left out and named in "unmeasured".
    Returns [{"label", "module", "kind", "face", "open", "rays",
    "open_pct", "normal", "blocked_by", "unmeasured", "see_through",
    "covered_by", "cover_problems", "near"}]; blocked_by: the part most
    blocked rays meet first; see_through / covered_by: the parts the rays
    were let through; near: the parts rays meet within COVER_MM. The first row also carries "covers_unmatched": problems for
    declared covers naming no part or no module."""
    import numpy as np
    if board is None or not modules:
        return []
    _tilt, bn = board_tilt(board["mesh"])
    if bn is None:
        return []
    bn = np.array(bn, dtype=float)
    if covers is None:
        covers, cover_bad = _intent_covers()
    else:
        covers, cover_bad = sanitize_covers(covers)
    BP = _mesh_points(board["mesh"])
    bc = BP.mean(axis=0)
    atech = [_mesh_box(board["mesh"])] + [_mesh_box(m["mesh"]) for m in modules]
    boxed = [_shape_box(p["shape"]) for p in parts]
    mine = sorted(product_parts(boxed, atech))
    tris, owner, unmeasured = [], [], []
    planes, plane_own = [], []
    for i in mine:
        try:
            _P, T = _tess(parts[i]["shape"])
        except SlowToTessellate:
            try:
                T, hp = _tess_holed(parts[i]["shape"])     # R250
            except Exception:                           # noqa: BLE001
                unmeasured.append(parts[i]["label"])
                continue
            planes += hp
            plane_own += [i] * len(hp)
        except Exception:                               # noqa: BLE001
            continue
        if len(T):
            tris.append(T)
            owner.append(np.full(len(T), i))
    T = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
    own = np.concatenate(owner) if owner else np.zeros(0, dtype=int)
    plane_own = np.array(plane_own, dtype=int)
    tl, th = (T.min(axis=1), T.max(axis=1)) if len(T) else (None, None)
    clear = {i for i in mine if part_transparency(parts[i], views) >= SEE_THROUGH_PCT}
    by_label = {}
    for i in mine:
        by_label.setdefault(parts[i]["label"], i)
    all_labels = {p["label"] for p in parts}
    mod_labels = {m["label"] for m in modules}
    for pl, mls in sorted(covers.items()):
        if pl not in all_labels:
            cover_bad.append('intent.json "covers" names %s, which is no part of the '
                             'build' % pl)
        elif pl not in by_label:
            cover_bad.append('intent.json "covers" names %s, which is not part of the '
                             'product (nowhere near the board or a module)' % pl)
        for ml in mls:
            if ml not in mod_labels:
                cover_bad.append('intent.json "covers": %s -> %s, which is no Atech '
                                 'module of the build (modules: %s)' % (
                                     pl, ml, ", ".join(sorted(mod_labels))))
    out = []
    for m in modules:
        P = _mesh_points(m["mesh"])
        if not len(P):
            continue
        kind = module_kind(m.get("module"))
        face = FACE_OF.get(kind, "top")
        mname, maxes = _module_meta(m)
        wd = working_dirs(mname, maxes)
        if wd is not None:
            # R240: the module's OWN working face in world (cabled modules
            # face wherever module_placement turned them). MEASURED on the
            # test_kit_round12 car: a cabled distance_sensor facing -Y behind
            # a 12 x 8 window in the front wall read 0 of 169 rays along +Z
            # ("sealed in", a correct design failed); now 45 of 169 along -Y.
            # The dc_motor read +Z (26 of 169); now its shaft, -X.
            up = wd["up"]
            mask, pf = _proud_split(P, wd["faces"])
            if face == "socket":
                d, FP = socket_face(m["mesh"], up, maxes)
                if d is None:
                    kind, face = None, None
                    d, FP = up, P
                else:
                    d = np.array(d, dtype=float)
            elif kind is None and pf is not None and mask.any():
                # a DC motor: its shaft, along the shaft (reported, not judged)
                face, d, FP = "shaft", pf["dir"], P[mask]
            else:
                d, FP = up, P
        elif face == "socket":
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

        def axis(lo, hi, k=grid):
            inset = min(FACE_INSET_MM, 0.25 * (hi - lo))
            lo, hi = lo + inset, hi - inset
            return np.linspace(lo, hi, k) if hi > lo else np.array([(lo + hi) / 2.0])
        gu, gv = np.meshgrid(axis(pu.min(), pu.max()), axis(pv.min(), pv.max()))
        G = gu.reshape(-1, 1) * B[0] + gv.reshape(-1, 1) * B[1]
        Q = G + (pd.max() + FACE_LIFT_MM) * B[2]
        # R250: the parts this module's rays pass through
        through = set(clear) if str(mname or m.get("module") or "") in SEE_THROUGH_MODULES \
            else set()
        covered, cprob = [], []
        for pl, mls in sorted(covers.items()):
            if m["label"] not in mls or pl not in by_label:
                continue
            ci = by_label[pl]
            cT, cpl = _tris_of(T, own, planes, plane_own, ci)
            gap = _cover_gap(cT, cpl, FP, B, G + pd.max() * B[2], d)
            if gap is None or gap > COVER_MM:
                cprob.append(
                    "%s is declared in intent.json \"covers\" as the cover of %s, but it "
                    "is not in front of its %s: %s. A cover (key cap, lens, light pipe) "
                    "must sit within %g mm in front of that face - move it there or "
                    "take it out of \"covers\"" % (
                        pl, m["label"], face_text({"face": face, "normal": d}),
                        "no ray from the face meets it" if gap is None
                        else "the nearest is %.2f mm off the face" % gap, COVER_MM))
            else:
                through.add(ci)
                covered.append(pl)
        if through:
            kt = ~np.isin(own, sorted(through))
            kp = ~np.isin(plane_own, sorted(through)) if len(plane_own) else plane_own > 0
            Tm, ownm = T[kt], own[kt]
            tlm, thm = (tl[kt], th[kt]) if tl is not None else (None, None)
            plm = [h for h, k in zip(planes, kp) if k]
            pom = plane_own[kp] if len(plane_own) else plane_own
        else:
            Tm, ownm, tlm, thm, plm, pom = T, own, tl, th, planes, plane_own
        def cast(Q):
            dist, idx = _cast(Tm, Q, d, far=far, tri_lo=tlm, tri_hi=thm)
            hit_own = np.where(idx >= 0, ownm[np.maximum(idx, 0)] if len(ownm) else -1, -1)
            if plm:
                pdist, pidx = _cast_holed(plm, Q, d, far=far)
                nearer = pdist < dist
                dist = np.where(nearer, pdist, dist)
                hit_own = np.where(nearer, pom[np.maximum(pidx, 0)], hit_own)
            return dist, hit_own
        dist, hit_own = cast(Q)
        if not np.isinf(dist).any() and grid < FACE_GRID_FINE and kind:
            # R250: sealed on the coarse grid - a pin-hole grille (1.2 mm
            # holes over a microphone) can sit between its rays, so a finer
            # grid has the last word before "sealed in" (still sealed: the
            # coarse grid's row stands)
            fu, fv = np.meshgrid(axis(pu.min(), pu.max(), FACE_GRID_FINE),
                                 axis(pv.min(), pv.max(), FACE_GRID_FINE))
            QF = (fu.reshape(-1, 1) * B[0] + fv.reshape(-1, 1) * B[1]
                  + (pd.max() + FACE_LIFT_MM) * B[2])
            fd, fh = cast(QF)
            if np.isinf(fd).any():
                Q, dist, hit_own = QF, fd, fh
        n_open = int(np.isinf(dist).sum())
        # R270: what each kind needs open, measured over its OWN zone
        # (open_need): the screen's active area, the ToF's aperture, a
        # sound module's share on the fine grid
        mod = str(mname or m.get("module") or "").strip().lower()
        need = {}
        if kind and n_open:
            cu, cv = 0.5 * (pu.min() + pu.max()), 0.5 * (pv.min() + pv.max())
            long_u = (pu.max() - pu.min()) >= (pv.max() - pv.min())
            lift = (pd.max() + FACE_LIFT_MM) * B[2]

            def rect_open(w, h, cell=1.0):
                # open share of a w x h rectangle centred on the face
                # (w along the face's longer side), on ~cell mm cells
                if not long_u:
                    w, h = h, w
                ku, kv = max(3, int(round(w / cell))), max(3, int(round(h / cell)))
                ru = cu - w / 2.0 + (np.arange(ku) + 0.5) * w / ku
                rv = cv - h / 2.0 + (np.arange(kv) + 0.5) * h / kv
                gu2, gv2 = np.meshgrid(ru, rv)
                QR = gu2.reshape(-1, 1) * B[0] + gv2.reshape(-1, 1) * B[1] + lift
                rd, _rh = cast(QR)
                return round(100.0 * float(np.isinf(rd).sum()) / len(QR), 1)
            if mod == "screen":
                need["active_pct"] = rect_open(*SCREEN_ACTIVE_MM)
            elif mod == "distance_sensor":
                w, h = TOF_APERTURE_MM
                a = rect_open(w, h, 0.5)
                # the aperture may lie either way across a square face
                need["aperture_pct"] = max(a, rect_open(h, w, 0.5)) if a < 100 else a
            elif mod == "microphone":
                need["zone_pct"] = rect_open(MIC_ZONE_MM[0], MIC_ZONE_MM[1], 0.4)
            elif mod in SOUND_MIN_PCT and 100.0 * n_open / len(Q) < SOUND_MIN_PCT[mod] \
                    and len(Q) < FACE_GRID_FINE ** 2:
                # a pin-hole grille can fall between the coarse rays: the
                # share is taken on the fine grid before it is judged
                fu, fv = np.meshgrid(axis(pu.min(), pu.max(), FACE_GRID_FINE),
                                     axis(pv.min(), pv.max(), FACE_GRID_FINE))
                QF = fu.reshape(-1, 1) * B[0] + fv.reshape(-1, 1) * B[1] + lift
                fd, _fh = cast(QF)
                need["fine_pct"] = round(100.0 * float(np.isinf(fd).sum()) / len(QF), 1)
        # R250: parts met within COVER_MM of the face - the candidates for a
        # "covers" declaration the sealed-in line suggests
        # (cast from the back of the module: a key cap resting 0.1 mm over
        # the face holds the start of a ray lifted FACE_LIFT_MM)
        near = []
        if n_open == 0 and kind:
            back = float(pd.max() - pd.min()) + 1.0
            bd, bo = cast(G + (pd.min() - 1.0) * B[2])
            close = bo[(bo >= 0) & (bd - back <= COVER_MM)]
            near = sorted({parts[int(i)]["label"] for i in close
                           if not parts[int(i)].get("cable")})     # R270
        blocked = None
        hit = hit_own[hit_own >= 0]
        if len(hit):
            vals, counts = np.unique(hit, return_counts=True)
            blocked = parts[int(vals[counts.argmax()])]["label"]
        out.append({"label": m["label"], "module": m.get("module"),
                    "kind": kind, "face": face, "open": n_open,
                    "rays": len(Q), "open_pct": round(100.0 * n_open / len(Q), 1),
                    "normal": [round(float(x), 3) for x in d],
                    "blocked_by": blocked, "unmeasured": list(unmeasured),
                    "see_through": sorted(parts[i]["label"] for i in through
                                          if i in clear and parts[i]["label"] not in covered),
                    "covered_by": covered, "cover_problems": cprob, "near": near})
        out[-1].update(need)                            # R270
        out[-1]["face_mm"] = [round(float(pu.max() - pu.min()), 2),
                              round(float(pv.max() - pv.min()), 2)]
    if out:
        out[0]["covers_unmatched"] = cover_bad
    return out


def _tris_of(T, own, planes, plane_own, i):
    """R250: (triangles, holed planes) of part index i."""
    tri = T[own == i] if len(own) else T[:0]
    pl = [h for h, k in zip(planes, plane_own) if k == i]
    return tri, pl


def normal_text(n):
    """[0, 0.999, 0.01] -> '+Y'; a tilted normal -> '(0.26, 0.97, 0.00)'."""
    k = max(range(3), key=lambda i: abs(n[i]))
    if abs(abs(n[k]) - 1.0) < 0.02:
        return ("+" if n[k] > 0 else "-") + "XYZ"[k]
    return "(%.2f, %.2f, %.2f)" % tuple(n)


FACE_WORDS = {"top": "working face", "socket": "socket mouth", "shaft": "shaft"}   # R240: shaft


def face_text(row):
    """'working face (+Y)' / 'socket mouth (-X)' for a face_open row."""
    return "%s (%s)" % (FACE_WORDS.get(row.get("face") or "top", "working face"),
                        normal_text(row["normal"]))


# R270 (round-1 showcase, 2026-10-20): "a toy car" names no light, ToF,
# button or USB-C, so its sealed headlights, blind ToF, buried horn button
# and walled-in USB-C were only WARNINGs and the turn ended on CHECK PASS.
# In quality mode a module the agent PLACED whose kind needs an opening is
# a PROBLEM when sealed, named or not (an orientation or temperature module
# keeps the old rule); fast mode keeps the request-named rule. Each kind
# also has a floor of what must be open (MEASURED module data:
# reference/ATECH_PRODUCTS.md):
PLACED_OPEN = ("light", "distance_sensor", "screen", "button", "speaker",
               "microphone", "usbc")
SCREEN_ACTIVE_MM = (25.6, 13.5)     # the screen module's active area, centred
SCREEN_MIN_PCT = 90.0               # ...this share of it seen through the window
TOF_APERTURE_MM = (10.0, 6.0)       # the ToF needs an open aperture this big
TOF_MIN_PCT = 85.0                  # ...this share of it open (centred), on
                                    # 0.5 mm cells: examples/toy_car.py's
                                    # 6.6 mm grille slot reads 90 % on 1 mm
                                    # cells (a row lost to a 0.8 mm offset)
SOUND_MIN_PCT = {"microphone": 3.0, "speaker": 3.0}   # % of the face's rays
# The microphone's working area is its MEMS port mid-plate ("no explicit
# port in the mesh", ATECH_PRODUCTS.md), not its 39.5 x 19.5 board: its
# share is taken over this zone centred on the face (0.4 mm cells). The
# catalogue's 7-hole grille (d 7, holes 1.2) opens ~5 % of it, ~1 % of the
# whole plate; a stray gap at the plate's edge opens none of it.
MIC_ZONE_MM = (12.0, 12.0)
MODE_ENV = "ATECH_PROMPT_MODE"


def quality_mode():
    """R270: True unless $ATECH_PROMPT_MODE says "fast" (Studio's default
    is quality: build.quality_mode)."""
    import os
    return (os.environ.get(MODE_ENV) or "").strip().lower() != "fast"


def _open_floor(r):
    """R270: the floor line for a face_open row that is open but below
    what its kind needs (or None)."""
    mod = str(r.get("module") or "").strip().lower()
    where = face_text(r)
    if mod == "screen" and r.get("active_pct") is not None \
            and r["active_pct"] < SCREEN_MIN_PCT:
        return ("%s (a screen): the window shows only %g %% of its %g x %g mm active "
                "area (rays from its %s; needs >= %g %%). Open a window of at least "
                "%g x %g mm centred on the screen (a recessed bezel 0.8-1.5 mm round "
                "it), or put a clear lens (cad.transparency 'glass' / 'smoked') "
                "in it" % (r["label"], r["active_pct"], SCREEN_ACTIVE_MM[0],
                           SCREEN_ACTIVE_MM[1], where, SCREEN_MIN_PCT,
                           SCREEN_ACTIVE_MM[0] + 1.5, SCREEN_ACTIVE_MM[1] + 1.5))
    if mod == "distance_sensor" and r.get("aperture_pct") is not None \
            and r["aperture_pct"] < TOF_MIN_PCT:
        return ("%s (a ToF distance sensor): only %g %% of the %g x %g mm aperture "
                "centred on its %s is open (needs >= %g %%) - the sensor cannot see "
                "past the wall. Cut an OPEN aperture of at least %g x %g mm (no "
                "glass) centred in front of it, e.g. a grille slot 6.6 x 23" % (
                    r["label"], r["aperture_pct"], TOF_APERTURE_MM[0],
                    TOF_APERTURE_MM[1], where, TOF_MIN_PCT, TOF_APERTURE_MM[0],
                    TOF_APERTURE_MM[1]))
    if mod in SOUND_MIN_PCT:
        zone = mod == "microphone" and r.get("zone_pct") is not None
        pct = r["zone_pct"] if zone else r.get("fine_pct", r.get("open_pct"))
        if pct is not None and pct < SOUND_MIN_PCT[mod]:
            return ("%s (a %s): only %g %% of the rays from %s get out (needs >= "
                    "%g %%) - it cannot %s through that. Open more of the wall in "
                    "front of it: cad.speaker_grille(wall, centre, normal, d, ...) with a "
                    "larger d or holes, or a slot pattern over the module" % (
                        r["label"], mod, pct,
                        "the middle %g x %g mm of its %s (the mic port)" % (
                            MIC_ZONE_MM[0], MIC_ZONE_MM[1], where) if zone
                        else "its " + where, SOUND_MIN_PCT[mod],
                        "be heard" if mod == "speaker" else "hear"))
    return None


def face_open_problems(rows, request, mode=None):
    """(problems, warnings) from face_open rows. A module whose kind needs
    an opening, 0 % open: R270 quality mode (mode None: quality_mode()) -
    a PROBLEM for every module the agent placed of a PLACED_OPEN kind,
    whether or not the request names it; an intent.json "covers" entry
    (covered_by) exempts it. Other kinds (temperature sensor) and fast mode:
    a problem when the request names the kind, a warning when there is no
    request to read (the kind alone cannot say the user wanted it seen). A
    USB-C socket is judged along its mouth (R164): a slot over the module's
    cover does not let a plug in. R270, quality mode: an open but too small
    opening (_open_floor: screen active area, ToF aperture, sound share) is
    a PROBLEM too. R250: every cover_problems / covers_unmatched line of
    the rows is a problem (a declared cover that is not in front of its
    module's face, or names nothing)."""
    quality = quality_mode() if mode is None else (str(mode).lower() != "fast")
    problems, warnings = [], []
    for r in rows:
        # R250: a declared cover that is no cover always fails
        problems += list(r.get("covers_unmatched") or ())
        problems += list(r.get("cover_problems") or ())
    for r in rows:
        if not r["kind"]:
            continue
        mod = str(r.get("module") or "").strip().lower()
        placed = quality and mod in PLACED_OPEN and not r.get("covered_by")
        if r["open"] > 0:
            if placed:
                floor = _open_floor(r)
                if floor:
                    problems.append(floor)
            continue
        named = request_names(r["kind"], request)
        fix = ("Cut the opening in front of the socket mouth (%s), not over the "
               "module's cover" % normal_text(r["normal"])
               if r.get("face") == "socket"
               else "Cut the opening in front of that face, not elsewhere")
        if r.get("near") and r.get("face") != "socket":
            # R250: a part right on the face may be its key cap / lens
            fix += ("; or, if %s is this module's key cap, lens or light pipe, "
                    "declare it in intent.json: \"covers\": {%s} (it must sit within "
                    "%g mm in front of the face)" % (
                        " / ".join(r["near"]), ", ".join(
                            "\"%s\": \"%s\"" % (n, r["label"]) for n in r["near"]),
                        COVER_MM))
        line = ("%s (a %s) is sealed in: 0 of %d rays from its %s get out of the "
                "product within %g mm%s. %s" % (
                    r["label"], r["kind"], r["rays"], face_text(r),
                    FACE_FAR_MM, " - %s is in the way" % r["blocked_by"]
                    if r["blocked_by"] else "", fix))
        if named:
            problems.append(line + " (the request asks for a %s)" % r["kind"])
        elif placed:
            # R270: placed, so it is part of the product - a blind sensor,
            # an unlit light or an unreachable socket is a defect
            what = {"usbc": "a USB-C socket no plug can reach",
                    "button": "a button no finger can press",
                    "light": "a light nobody can see", "screen": "a screen nobody can see",
                    "speaker": "a speaker nobody can hear",
                    "microphone": "a microphone that cannot hear",
                    "distance_sensor": "a distance sensor that cannot see out"}[mod]
            problems.append(line + " (you placed it: %s is a defect, asked for or not "
                            "- open it, or take the module out)" % what)
        elif named is None:
            warnings.append(line)
    return problems, warnings


# ----------------------------------------------- module enclosure (R241)
# R241 (showcase baseline, 2026-10-19): the box-only containment test
# (atech_layout: every module inside the union BOX of the parts, and only
# when the board is inside it) cannot see a module that sits outside the
# body but inside the box of all parts - beside a case, under a far-out
# wheel or antenna, poking up through a window - and it never ran at all
# when the board stuck out of that box. So each module is now probed on its
# own: rays from a sample of its mesh points along its six axis directions
# against the product's parts. A point is OUTSIDE when two of its rays at
# right angles (other than along a working face) leave the product without
# meeting a part; a module that sees out one way past every part, the board
# and the other modules, over ENCLOSE_SIDE_PCT of it, sits against an open
# side. The working face may look out (an opening in front of it) and a
# point within ENCLOSE_FLUSH_MM of that face may see out sideways (a face
# flush with the opening); a USB-C shell or a motor shaft that stands proud
# of the module's case is left out (it goes through the wall by design).
ENCLOSE_FAR_MM = 2000.0     # a ray that meets no part within this is out
ENCLOSE_POINTS = 240        # mesh points sampled per module, at most
ENCLOSE_FLUSH_MM = 0.5      # a working face this far proud of the opening is "flush"
ENCLOSE_OUT_PCT = 5.0       # more of the module's points outside -> not inside
ENCLOSE_SIDE_PCT = 90.0     # this share seeing out one (non-working) way -> open
                            # side. MEASURED: an open end 98-100 %, an open top
                            # 100 %; test_agent_kit's nightlight light beside a
                            # 7 x 15 vent in the end lid 56 % (a hole beside a
                            # module is no open side)
ENCLOSE_SKEW = (0.0017, 0.0023, 0.0031)  # off-axis tilt: no ray runs exactly
                                         # along a wall's plane or an edge
ENCLOSE_DIRS = ("+X", "+Y", "+Z", "-X", "-Y", "-Z")


def _mesh_tris(mesh):
    """(m,3,3) world triangles of a Mesh (Feature.Mesh is world already)."""
    import numpy as np
    try:
        pts, fac = mesh.Topology
    except Exception:                                   # noqa: BLE001
        return np.zeros((0, 3, 3))
    if not len(fac):
        return np.zeros((0, 3, 3))
    P = np.array([(p.x, p.y, p.z) for p in pts], dtype=float).reshape(-1, 3)
    return P[np.array(fac, dtype=int).reshape(-1, 3)]


def _voxel_pick(P, cap):
    """At most `cap` points of P spread over it (one per voxel, the voxel
    doubled until few enough)."""
    import numpy as np
    if len(P) <= cap:
        return P
    h = max(float(np.ptp(P, axis=0).max()) / 40.0, 0.5)
    while True:
        k = np.floor((P - P.min(axis=0)) / h).astype(np.int64)
        _u, idx = np.unique(k, axis=0, return_index=True)
        if len(idx) <= cap:
            return P[np.sort(idx)]
        h *= 1.5


def _dir_name(v):
    """'+X' ... '-Z' of the world axis nearest v."""
    k = max(range(3), key=lambda i: abs(v[i]))
    return ("+" if v[k] > 0 else "-") + "XYZ"[k]


def enclosure(parts, board, modules, far=ENCLOSE_FAR_MM, cap=ENCLOSE_POINTS):
    """R241: per Atech module, how much of it lies inside the product.

    parts    [{"label", "shape"}]  the agent's DESIGNED parts (no cables:
             a ribbon encloses nothing)
    board    {"label", "mesh"}
    modules  [{"label", "name", "mesh", "module"?, "axes"?}] - module and
             axes are read off the document object when not given
    Only the product's parts (product_parts) count. Returns [{"label",
    "module", "points", "judged", "outside", "outside_pct", "escape_pct"
    {dir: pct of points whose ray that way meets no part}, "side_pct"
    {dir: ... nor the board or another module}, "allowed" [dir], "out_box"
    [6] | None}] - nothing when there
    is no part (a hardware-only draft is not judged). A planar face with
    too many holes to tessellate is cast against exactly (R250, _cast_holed);
    a part still too slow is left out; the rows name it in "unmeasured"."""
    import numpy as np
    if board is None or not modules or not parts:
        return []
    atech = [_mesh_box(board["mesh"])] + [_mesh_box(m["mesh"]) for m in modules]
    boxed = [_shape_box(p["shape"]) for p in parts]
    mine = sorted(product_parts(boxed, atech))
    tris, unmeasured, planes = [], [], []
    for i in mine:
        try:
            _P, T = _tess(parts[i]["shape"])
        except SlowToTessellate:
            # R250: a one-piece case with a 169-hole grille was left out
            # whole, and every module read "OUTSIDE the product" (MEASURED,
            # test_kit_round12 PANEL: 156 of 156 points of the light);
            # its planar holed faces are cast against exactly now
            try:
                T, hp = _tess_holed(parts[i]["shape"])
            except Exception:                           # noqa: BLE001
                unmeasured.append(parts[i]["label"])
                continue
            planes += hp
        except Exception:                               # noqa: BLE001
            continue
        if len(T):
            tris.append(T)
    if not tris and not planes:
        return []
    T = np.concatenate(tris) if tris else np.zeros((0, 3, 3))
    tl, th = (T.min(axis=1), T.max(axis=1)) if len(T) else (None, None)
    # the board and the other modules shield a module's side (an opening
    # far across the product, in line with it, is no open side of it)
    meshes = [board["mesh"]] + [m["mesh"] for m in modules]
    mt = [_mesh_tris(x) for x in meshes]
    MT = np.concatenate(mt) if mt else np.zeros((0, 3, 3))
    mown = np.concatenate([np.full(len(t), i) for i, t in enumerate(mt)]) if mt \
        else np.zeros(0, dtype=int)
    _tilt, bn = board_tilt(board["mesh"])
    bc = _mesh_points(board["mesh"]).mean(axis=0)
    skew = np.asarray(ENCLOSE_SKEW, dtype=float)
    out = []
    for mi, m in enumerate(modules):
        P = _mesh_points(m["mesh"])
        if not len(P):
            continue
        mname, maxes = _module_meta(m)
        wd = working_dirs(mname, maxes)
        if maxes:
            A = np.asarray(maxes, dtype=float).reshape(3, 3)
        else:
            A = np.eye(3)
        dirs = [A[k] for k in range(3)] + [-A[k] for k in range(3)]
        if wd is not None:
            faces = [f["dir"] for f in wd["faces"]] or [wd["up"]]
            mask, _pf = _proud_split(P, wd["faces"])
            if mask is not None:
                P = P[~mask]
        elif bn is not None:
            s = float(np.dot(P.mean(axis=0) - bc, bn))
            faces = [np.asarray(bn, dtype=float) * (1.0 if s >= 0 else -1.0)]
        else:
            faces = []
        allowed = [any(float(np.dot(d, f)) > 0.9 for f in faces) for d in dirs]
        Q = _voxel_pick(P, cap)
        flush = np.zeros(len(Q), dtype=bool)
        for f in faces:
            s = Q @ np.asarray(f, dtype=float)
            flush |= s >= s.max() - ENCLOSE_FLUSH_MM
        E = np.zeros((len(Q), 6), dtype=bool)      # past every part
        S = np.zeros((len(Q), 6), dtype=bool)      # ... and every other Atech mesh
        others = MT[mown != mi + 1]
        for k, d in enumerate(dirs):
            if allowed[k]:
                continue
            dd = d + skew
            dist, _idx = _cast(T, Q, dd, far=far, tri_lo=tl, tri_hi=th)
            if planes:
                dist = np.minimum(dist, _cast_holed(planes, Q, dd, far=far)[0])
            E[:, k] = np.isinf(dist)
            esc = np.nonzero(E[:, k])[0]
            if len(esc):
                d2, _i2 = _cast(others, Q[esc], dd, far=far)
                S[esc, k] = np.isinf(d2)
        J = ~flush
        nj = int(J.sum())
        # outside: it sees out two ways at right angles (beside the body,
        # or above its surface). Only two OPPOSITE ways (both ends of an
        # open tube) is an open side, judged below - not "outside"
        # (MEASURED: examples/atech_case.py, open at both X ends, read
        # "OUTSIDE" with any-two-ways)
        perp = np.zeros(len(Q), dtype=bool)
        for a in range(6):
            for b in range(a + 1, 6):
                if b != a + 3:
                    perp |= E[:, a] & E[:, b]
        outside = J & perp
        n_out = int(outside.sum())
        side, escape = {}, {}
        for k, d in enumerate(dirs):
            if not allowed[k] and nj:
                side[_dir_name(d)] = round(100.0 * float(S[J, k].sum()) / nj, 1)
                escape[_dir_name(d)] = round(100.0 * float(E[J, k].sum()) / nj, 1)
        ob = None
        if n_out:
            O = Q[outside]
            ob = [round(float(v), 2) for v in list(O.min(axis=0)) + list(O.max(axis=0))]
        out.append({"label": m["label"], "module": mname, "points": len(Q),
                    "judged": nj, "outside": n_out,
                    "outside_pct": round(100.0 * n_out / nj, 1) if nj else 0.0,
                    "side_pct": side, "escape_pct": escape,
                    "allowed": [_dir_name(d) for k, d in enumerate(dirs)
                                if allowed[k]],
                    "out_box": ob, "unmeasured": list(unmeasured)})
    return out


def enclosure_problems(rows):
    """R241: problem lines from enclosure rows. A module with more than
    ENCLOSE_OUT_PCT of its points outside the product is outside it (all
    of it) or sticks out of it; one that sees out ENCLOSE_SIDE_PCT or more
    one way other than its working face sits against an open side.
    INTENDED_OVERLAPS never excuses this (an overlap declaration says
    nothing about where the module is)."""
    problems = []
    for r in rows:
        if not r["judged"]:
            continue
        work = ("its working face (%s) may look out through an opening, flush "
                "with it" % ", ".join(r["allowed"]) if r["allowed"]
                else "it has no working face to show")
        if r["outside_pct"] > ENCLOSE_OUT_PCT:
            esc = r.get("escape_pct") or r["side_pct"]
            ways = sorted(esc, key=lambda k: -esc[k])
            ways = [w for w in ways if esc[w] > 0][:3]
            b = r["out_box"]
            where = (" (the outside part spans x %.1f..%.1f, y %.1f..%.1f, z %.1f..%.1f)"
                     % (b[0], b[3], b[1], b[4], b[2], b[5])) if b else ""
            if r["outside_pct"] >= 90.0:
                what = "is OUTSIDE the product"
            else:
                what = "sticks out of the product's body"
            problems.append(
                "%s %s: %d of %d sampled points of it see out of the product "
                "toward %s past no part%s. Every Atech module must be inside "
                "the body - %s, nothing else of it may stick out. Grow or reshape "
                "the body around it, or move the module inside"
                % (r["label"], what, r["outside"], r["judged"], ", ".join(ways) or "?",
                   where, work))
            continue
        for w, pct in sorted(r["side_pct"].items(), key=lambda t: -t[1]):
            if pct >= ENCLOSE_SIDE_PCT:
                problems.append(
                    "%s is not enclosed on its %s side: %.0f %% of it sees out "
                    "that way past no part (an open end, or an opening that is "
                    "not in front of its working face). Close that side - %s"
                    % (r["label"], w, pct, work))
                break
    return problems


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
               probe=WALL_PROBE_MM, seed=0, per_part_seed=False):
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
    the wall. R270: per_part_seed - each part's samples drawn from its own
    `seed` (a part's result then does not depend on the parts before it,
    so it can be cached per part); a part the time cap cut short carries
    "partial": True."""
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
        if per_part_seed:
            rng = np.random.default_rng(seed)
        cut_short = False
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
        best = (np.inf, None, None)
        done = 0
        side = []
        for gi in order:
            if time.time() - t0 > budget_s:
                complete = False
                cut_short = True
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
                        best = (float(dd[k]), C[sel][got][par][k], d)   # R270: + dir
            done += len(sel)
        total += done
        if best[1] is not None:
            rows.append({"label": p["label"], "mm": round(best[0], 2),
                         "at": [round(float(x), 2) for x in best[1]],
                         "dir": [round(float(x), 4) for x in best[2]],
                         "samples": done})
        else:
            rows.append({"label": p["label"], "mm": None, "at": None, "samples": done})
        sw = side_walls(side)
        if sw:
            rows[-1]["side"] = sw
        if cut_short:
            rows[-1]["partial"] = True                  # R270
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
    store = _pair_store()                               # R270: repeat-check cache
    fps = {}

    def fp(i):
        if i not in fps:
            fps[i] = cache_fingerprint(parts[i]["shape"])
        return fps[i]

    def contact(i, j):
        """(touch True/False/None, depth: None = they share volume)"""
        key = (min(i, j), max(i, j))
        if key not in pair and store is not None:
            fa, fb = fp(key[0]), fp(key[1])
            if fa is not None and fb is not None:
                ck = _pair_key("joint", parts[key[0]]["label"], fa,
                               parts[key[1]]["label"], fb)
                got = store["data"].get(ck)
                if isinstance(got, list) and len(got) == 2:
                    store["hits"] += 1
                    pair[key] = (got[0], got[1])
                    return pair[key]
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
            if store is not None and fp(key[0]) is not None and fp(key[1]) is not None:
                store["data"][_pair_key("joint", parts[key[0]]["label"], fp(key[0]),
                                        parts[key[1]]["label"], fp(key[1]))] = [t, d]
                store["dirty"] = True
                store["miss"] = store.get("miss", 0) + 1
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


# --------------------------------------------- R270 checker gates (WS3)
# Round 1 (2026-10-20) ended turns on CHECK PASS with a 0.28 mm wall, a
# 52 mm wheel-well bore through both walls of the body, screws whose pilot
# was the screw's own diameter and a board nothing held. Each is now a
# PROBLEM in quality mode (quality_mode()), measured here.
WALL_PROBLEM_MM = 0.6       # a confirmed wall under this fails (FDM: 1.5 lines)
WALL_EXACT_STEP = 0.01      # exact re-measure: point-in-solid every 0.01 mm
WALL_EXACT_SPAN = 1.2       # ...over this much of the ray


def wall_exact(shape, at, d, span=WALL_EXACT_SPAN, step=WALL_EXACT_STEP):
    """R270: the wall thickness at a thin_walls() spot measured on the
    exact shape (not its tessellation): the first run of material along
    unit `d` from 0.05 mm before `at`, point-in-solid every `step` mm.
    None when no material is found; `span` when the run does not end
    within it (thick there)."""
    import numpy as np
    a = np.asarray(at, dtype=float)
    dd = np.asarray(d, dtype=float)
    dd = dd / (np.linalg.norm(dd) or 1.0)
    t = np.arange(-0.05, span + step / 2, step)
    pts = [tuple(a + dd * x) for x in t]
    inside = np.asarray(points_inside(shape, pts, 1e-4), dtype=bool)
    idx = np.nonzero(inside)[0]
    if not len(idx):
        return None
    i0 = idx[0]
    out = np.nonzero(~inside[i0:])[0]
    if not len(out):
        return round(float(span), 2)
    j = i0 + out[0]

    def edge(lo, hi, lo_in):
        # bisect the boundary between t=lo and t=hi (lo_in: lo is inside)
        for _k in range(7):
            mid = 0.5 * (lo + hi)
            if bool(points_inside(shape, [tuple(a + dd * mid)], 1e-4)[0]) == lo_in:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)
    t_in = edge(t[i0 - 1], t[i0], False) if i0 > 0 else t[0]
    t_out = edge(t[j - 1], t[j], True)
    return round(float(t_out - t_in), 2)


DETAIL_EDGE_MM = 1.5        # a free edge this close beside a thin run...
DETAIL_BASE_MM = 1.2        # ...and material this thick along the ray just
                            # past it: a proud detail (an embossed letter's
                            # stroke, a fin) on a thicker base, not a wall


def _run_along(shape, m, u, reach, step=0.05):
    """Distance from m along unit u to where material ends (reach: none)."""
    import numpy as np
    t = np.arange(step, reach + step / 2, step)
    ins = np.asarray(points_inside(shape, [tuple(m + u * x) for x in t], 1e-4), dtype=bool)
    out = np.nonzero(~ins)[0]
    return float(t[out[0]]) if len(out) else float(reach)


def wall_is_detail(shape, at, d, t):
    """R270: True when the thin run at `at` along `d` (t mm) is a proud
    detail - a raised letter's stroke, a fin, a rib - not a wall: across
    the run, a free edge lies within DETAIL_EDGE_MM one way (the top of the
    stroke), and DETAIL_BASE_MM the other way the material is thick along
    `d` (the base it stands on). A wall thinned by a cut stays thin past
    its edge, so it is still a wall. MEASURED on examples/toy_car.py: the
    embossed "4x4" (0.5 mm proud, strokes 0.55 wide) read as a 0.55 mm
    wall; the round-1 toy car's 0.27 mm sliver stays a wall."""
    import math
    import numpy as np
    a = np.asarray(at, dtype=float)
    dd = np.asarray(d, dtype=float)
    dd = dd / (np.linalg.norm(dd) or 1.0)
    m = a + dd * (0.5 * t)
    if not points_inside(shape, [tuple(m)], 1e-4)[0]:
        return False
    B = _basis(dd)
    best = None
    for k in range(8):
        ang = 2 * math.pi * k / 8
        u = math.cos(ang) * B[0] + math.sin(ang) * B[1]
        e = _run_along(shape, m, u, DETAIL_EDGE_MM)
        if best is None or e < best[0]:
            best = (e, u)
    if best is None or best[0] >= DETAIL_EDGE_MM:
        return False
    m2 = m - best[1] * (best[0] + DETAIL_BASE_MM)
    if not points_inside(shape, [tuple(m2)], 1e-4)[0]:
        return False
    run = _run_along(shape, m2, dd, 3.0) + _run_along(shape, m2, -dd, 3.0)
    return run >= 2.0 * DETAIL_BASE_MM


def thin_wall_problems(walls, shapes, floor=WALL_PROBLEM_MM):
    """R270: PROBLEM lines for thin_walls() rows under `floor`, each
    re-measured on the exact shape first (wall_exact) - a tessellation
    chord on a fillet is not a wall. `shapes`: {label: shape}. Returns
    (problems, confirmed rows [{"label", "mm", "exact_mm", "at"}])."""
    problems, rows = [], []
    for r in (walls or {}).get("parts") or ():
        if r.get("mm") is None or r["mm"] >= floor or r["label"] not in shapes:
            continue
        exact = r["mm"]
        if r.get("dir") is not None and r.get("at") is not None:
            try:
                e = wall_exact(shapes[r["label"]], r["at"], r["dir"])
            except Exception:                           # noqa: BLE001
                e = None
            if e is not None:
                exact = e
        if exact >= floor:
            continue
        try:
            detail = r.get("dir") is not None and wall_is_detail(
                shapes[r["label"]], r["at"], r["dir"], exact)
        except Exception:                               # noqa: BLE001
            detail = False
        rows.append({"label": r["label"], "mm": r["mm"], "exact_mm": exact,
                     "at": r["at"], "detail": bool(detail)})
        if detail:
            continue
        problems.append(
            "%s: a wall only %.2f mm thick near (%s) - under %.1f mm it does not "
            "print (it is less than 2 extrusion lines) and breaks in the hand. "
            "Thicken the wall there (>= %.1f mm, 1.6+ for a shell), or move the "
            "cut, groove or pocket that thins it" % (
                r["label"], exact, ", ".join("%.1f" % v for v in r["at"]), floor,
                WALL_FLOOR_MM))
    return problems, rows


THROUGH_KEY = "through_holes"   # intent.json: bores meant to cross every wall
# Under this diameter a bore through both walls stays a WARNING: a hinge
# pin, an axle or a light-pipe hole is nearly always meant to cross both
# (MEASURED: the R202 hinge fixtures' 2 mm pin bores, R181's 3 mm holes);
# round 1's wheel-well bore was 52 mm, a wrongly drilled vent or window is
# far over this.
THROUGH_PROBLEM_MIN_MM = 6.0


def through_is_problem(intent, label, d_mm):
    """R270: a bore through more than one wall that fails the check -
    THROUGH_PROBLEM_MIN_MM or wider and not listed in "through_holes"."""
    return float(d_mm) >= THROUGH_PROBLEM_MIN_MM and \
        not through_intended(intent, label, d_mm)


def through_intended(intent, label, d_mm, tol=0.15):
    """R270: True when intent.json "through_holes" lists this bore - a part
    label (every through bore of it), a diameter in mm (any part), or
    {"part": label, "d_mm": d} (either key may be left out)."""
    want = (intent or {}).get(THROUGH_KEY) if isinstance(intent, dict) else None
    if want is None:
        return False
    if not isinstance(want, list):
        want = [want]
    for w in want:
        if isinstance(w, str) and w == label:
            return True
        if isinstance(w, (int, float)) and not isinstance(w, bool) \
                and abs(float(w) - float(d_mm)) <= tol:
            return True
        if isinstance(w, dict):
            p_ok = w.get("part") in (None, label)
            d = w.get("d_mm")
            d_ok = d is None or (isinstance(d, (int, float)) and not isinstance(d, bool)
                                 and abs(float(d) - float(d_mm)) <= tol)
            if p_ok and d_ok and (w.get("part") is not None or d is not None):
                return True
    return False


def through_problem_text(label, b):
    """R270: the wall_crossing line as a PROBLEM, with the way out."""
    return (wall_crossing_text(label, b).replace(
        "; a hole meant to pass through them all is fine as it is", "")
        + ". It is a PROBLEM now: a bore through both walls of a body opens the "
        "far wall too (the 52 mm wheel-well bore of round 1). Cut each side on "
        "its own (through=\"wall\"), or - if it really must cross every wall (an "
        "axle tube) - list it in intent.json: \"%s\": [\"%s\"] or [%g]" % (
            THROUGH_KEY, label, b["d_mm"]))


# Screws (R270). A thread-forming screw needs a pilot under its nominal
# size to bite: ~0.85 d in printed plastic (M2.5 -> 2.1 mm), or a heat-set
# insert pocket (~1.4 d). A pilot of d or more (a tapped-hole size, or the
# clearance hole) holds nothing.
SCREW_RE = r"^screw"            # part labels that are screws (case-insensitive)
SCREW_SIZES = (1.6, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0)
PILOT_RATIO = 0.85              # what to drill for a thread-forming screw
INSERT_RATIO = 1.3              # a pocket this much over d is an insert's


def _cyl_faces(shape):
    for f in shape.Faces:
        s = f.Surface
        if type(s).__name__ == "Cylinder":
            yield f, s


def _screw_axis(shape):
    """(nominal d, axis unit (numpy), a point on it, tip point) of a screw
    part: its narrowest cylinder is the shank (cad.screw: d - 0.1), the
    head is where the part reaches out of it; None when no shank."""
    import numpy as np
    best = None
    for f, s in _cyl_faces(shape):
        if s.Radius < 0.4 or f.Area < 1e-3:
            continue
        if best is None or s.Radius < best[1].Radius - 1e-6:
            best = (f, s)
    if best is None:
        return None
    f, s = best
    ax = np.array(tuple(s.Axis), dtype=float)
    ax /= np.linalg.norm(ax) or 1.0
    c = np.array(tuple(s.Center), dtype=float)
    shank = np.array([tuple(v.Point) for v in f.Vertexes] or [tuple(s.Center)], dtype=float)
    try:
        shank = np.vstack([shank, np.array([tuple(p) for e in f.Edges
                                            for p in e.discretize(8)], dtype=float)])
    except Exception:                                   # noqa: BLE001
        pass
    ts = (shank - c) @ ax
    allp = np.array([tuple(v.Point) for v in shape.Vertexes], dtype=float)
    rel = allp - c
    ta = rel @ ax
    rad = np.linalg.norm(rel - np.outer(ta, ax), axis=1)
    head = ta[rad > s.Radius * 1.3 + 0.2]
    if len(head):
        tip_t = ts.min() if abs(head.mean() - ts.min()) > abs(head.mean() - ts.max()) \
            else ts.max()
    else:
        tip_t = ts.max()
    d = 2.0 * s.Radius + 0.1
    near = min(SCREW_SIZES, key=lambda x: abs(x - d))
    nominal = near if abs(near - d) <= 0.15 else round(2.0 * s.Radius, 2)
    toward_head = -1.0 if tip_t == ts.max() else 1.0
    return nominal, ax, c, c + ax * tip_t, toward_head


def screw_pilots(parts):
    """R270: for each screw part (label ^screw), the pilot it ends in - the
    narrowest concave cylinder of another part, coaxial with its shank,
    around the point 0.5 mm back from its tip. [{"screw", "nominal_mm",
    "pilot_mm", "in", "verdict"}]: verdict "bites" (pilot < d), "insert"
    (pilot >= INSERT_RATIO x d: a heat-set insert pocket), "no bite"
    (d <= pilot < INSERT_RATIO x d), "not judged" (no coaxial bore at the
    tip - a nut, or the shank in solid material, which OVERLAP reports)."""
    import re
    import numpy as np
    import FreeCAD as App
    rows = []
    screws = [p for p in parts if re.search(SCREW_RE, str(p["label"]), re.I)]
    others = [p for p in parts if not re.search(SCREW_RE, str(p["label"]), re.I)]
    for sp in screws:
        try:
            got = _screw_axis(sp["shape"])
        except Exception:                               # noqa: BLE001
            got = None
        if got is None:
            continue
        nominal, ax, c, tip, back = got
        probe = tip + ax * back * 0.5
        pv = App.Vector(*probe)
        best = None
        for op in others:
            sh = op["shape"]
            try:
                bb = tight(sh)
                if not bb.isInside(pv):
                    continue
                for f, s in _cyl_faces(sh):
                    a2 = np.array(tuple(s.Axis), dtype=float)
                    a2 /= np.linalg.norm(a2) or 1.0
                    if abs(float(a2 @ ax)) < 0.999:
                        continue
                    c2 = np.array(tuple(s.Center), dtype=float)
                    rel = probe - c2
                    if np.linalg.norm(rel - (rel @ a2) * a2) > 0.15:
                        continue
                    if s.Radius < 0.3 * nominal or s.Radius > 1.6 * nominal:
                        continue
                    vt = np.array([tuple(v.Point) for v in f.Vertexes], dtype=float)
                    if not len(vt):
                        continue
                    tt = (vt - c2) @ a2
                    pt = rel @ a2
                    if pt < tt.min() - 0.25 or pt > tt.max() + 0.25:
                        continue
                    if best is None or s.Radius < best[0]:
                        best = (s.Radius, op["label"])
            except Exception:                           # noqa: BLE001
                continue
        row = {"screw": sp["label"], "nominal_mm": nominal}
        if best is None:
            row.update(pilot_mm=None, verdict="not judged")
        else:
            pd = round(2.0 * best[0], 2)
            row.update(pilot_mm=pd, **{"in": best[1]})
            row["verdict"] = ("bites" if pd < nominal - 0.02 else
                              "insert" if pd >= INSERT_RATIO * nominal else "no bite")
        rows.append(row)
    return rows


def pilot_text(row):
    d = row["nominal_mm"]
    return ("%s (M%g) ends in a %.2f mm pilot in %s - at or over the screw's own %g mm, "
            "so the thread has nothing to cut into and the screw spins loose. Drill "
            "the pilot %.1f mm (%.2f x d, thread-forming into plastic), or make it a "
            "heat-set insert pocket (~%.1f mm)" % (
                row["screw"], d, row["pilot_mm"], row["in"], d,
                round(PILOT_RATIO * d, 1), PILOT_RATIO, round(1.4 * d + 0.1, 1)))


RETAIN_MM = 0.5             # a part this close to the board holds it


def board_retention(parts, board, gap=RETAIN_MM, samples=4000):
    """R270: what holds the Atech board: designed parts within `gap` mm of
    the board's mesh, sampled on the parts' surface near the board's box.
    {"retained": bool, "above": [labels], "ledge": [labels]} - "above": on
    the side the board's normal points to (its modules' side), "ledge":
    under it. A board nothing comes near floats in the case."""
    import numpy as np
    tilt, bn = board_tilt(board["mesh"])
    BT = _mesh_tris(board["mesh"])
    out = {"retained": False, "above": [], "ledge": []}
    if bn is None or not len(BT):
        out["retained"] = None
        return out
    bn = np.asarray(bn, dtype=float)
    bc = BT.reshape(-1, 3).mean(axis=0)
    lo, hi = BT.reshape(-1, 3).min(axis=0) - gap, BT.reshape(-1, 3).max(axis=0) + gap
    rng = np.random.default_rng(0)
    for p in parts:
        try:
            b = _shape_box(p["shape"])
        except Exception:                               # noqa: BLE001
            continue
        if any(b[k] > hi[k] or b[k + 3] < lo[k] for k in range(3)):
            continue
        try:
            _P, T = _tess(p["shape"])
        except Exception:                               # noqa: BLE001
            continue
        if not len(T):
            continue
        tl, th = T.min(axis=1), T.max(axis=1)
        keep = np.all((th >= lo) & (tl <= hi), axis=1)
        T = T[keep]
        if not len(T):
            continue
        area = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)
        if area.sum() <= 0:
            continue
        n = min(samples, max(200, 4 * len(T)))
        pick = rng.choice(len(T), size=n, replace=True, p=area / area.sum())
        r1, r2 = rng.random(n), rng.random(n)
        flip = r1 + r2 > 1
        r1[flip], r2[flip] = 1 - r1[flip], 1 - r2[flip]
        Tc = T[pick]
        Q = Tc[:, 0] + r1[:, None] * (Tc[:, 1] - Tc[:, 0]) + r2[:, None] * (Tc[:, 2] - Tc[:, 0])
        Q = np.vstack([Q, T.reshape(-1, 3)])
        inb = np.all((Q >= lo) & (Q <= hi), axis=1)
        Q = Q[inb]
        if not len(Q):
            continue
        dist = _pt_tri_dist(Q, BT, limit=gap)
        near = Q[np.isfinite(dist)]
        if not len(near):
            continue
        side = (near - bc) @ bn
        if (side >= 0).any():
            out["above"].append(p["label"])
        if (side < 0).any():
            out["ledge"].append(p["label"])
    out["retained"] = bool(out["above"] or out["ledge"])
    return out


def retention_text(board_label):
    return ("%s: nothing holds the board - no part of yours comes within %g mm of it "
            "(no ledge under its edge, no rib, clip or boss over it), so it rattles "
            "loose in the case. Add a ledge 0.1 mm under the board's long edges and a "
            "rib or a lid boss 0.1-0.3 mm over it (examples/toy_car.py: the board "
            "cradle; desk_robot.py: ledges top and bottom)" % (board_label, RETAIN_MM))


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


def _is_view_target(t):
    return (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Attribute)
            and t.value.attr == "ViewObject")


class _ViewRewrite(ast.NodeTransformer):
    """X.ViewObject.attr = value   ->   __atech_view__(X, 'attr', value)

    R242: also
      a.ViewObject.attr = b.ViewObject.attr = v   (one value, every target
                                                   recorded; a plain target
                                                   assigned as before)
      any other X.ViewObject   ->   __atech_view__(X): a stand-in that
                                   records what is set on it (vo =
                                   o.ViewObject; vo.ShapeColor = c), is
                                   truthy (if o.ViewObject: ...), reads back
                                   what was set, and takes hide()/show()
    The right-hand side is evaluated once, after the line's own calls, as
    Python does (cad.color("rubber") runs, its value is recorded)."""

    def __init__(self):
        super().__init__()
        self.rewritten = 0
        self._tmp = 0

    def _record(self, t, value):
        return ast.Expr(ast.Call(func=ast.Name(VIEW_FN, ast.Load()),
                                 args=[self.visit(t.value.value), ast.Constant(t.attr),
                                       value], keywords=[]))

    def visit_Assign(self, node):
        if not any(_is_view_target(t) for t in node.targets):
            self.generic_visit(node)
            return node
        node.value = self.visit(node.value)
        if len(node.targets) == 1:
            self.rewritten += 1
            return ast.copy_location(self._record(node.targets[0], node.value), node)
        self._tmp += 1
        tmp = "__atech_view_value_%d__" % self._tmp
        out = [ast.Assign(targets=[ast.Name(tmp, ast.Store())], value=node.value)]
        for t in node.targets:
            if _is_view_target(t):
                self.rewritten += 1
                out.append(self._record(t, ast.Name(tmp, ast.Load())))
            else:
                out.append(ast.Assign(targets=[self.visit(t)],
                                      value=ast.Name(tmp, ast.Load())))
        return [ast.copy_location(n, node) for n in out]

    def visit_Attribute(self, node):
        if node.attr == "ViewObject" and isinstance(node.ctx, ast.Load):
            self.rewritten += 1
            return ast.copy_location(ast.Call(
                func=ast.Name(VIEW_FN, ast.Load()), args=[self.visit(node.value)],
                keywords=[]), node)
        self.generic_visit(node)
        return node


def record_view(code, counts=None):
    """The code as an AST with every `X.ViewObject.attr = v` turned into a
    recorder call and every other `X.ViewObject` into a recording stand-in
    (R242, see _ViewRewrite). Line numbers stay the agent's. Headless only:
    in the GUI the real ViewObject exists. `counts` (a dict) gets
    counts["rewritten"] = how many places were rewritten."""
    rw = _ViewRewrite()
    tree = rw.visit(ast.parse(code))
    ast.fix_missing_locations(tree)
    if counts is not None:
        counts["rewritten"] = rw.rewritten
    return tree


VIEW_KEYS = ("ShapeColor", "Transparency", "LineColor", "PointColor",
             "DiffuseColor", "Visibility", "DisplayMode", "LineWidth")
# what a stand-in ViewObject reads back before anything was set (FreeCAD's
# own defaults for a Part::Feature)
VIEW_DEFAULTS = {"ShapeColor": (0.8, 0.8, 0.8, 0.0), "Transparency": 0,
                 "LineColor": (0.098, 0.098, 0.098, 0.0),
                 "PointColor": (0.098, 0.098, 0.098, 0.0), "DiffuseColor": [],
                 "Visibility": True, "DisplayMode": "Flat Lines", "LineWidth": 2.0}
_NOARG = object()


class _NoOp(object):
    """Anything a stand-in ViewObject does not know: callable, attribute
    access and assignment do nothing."""

    def __call__(self, *a, **k):
        return None

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return self

    def __setattr__(self, name, value):
        pass

    def __bool__(self):
        return True


class _ViewStandIn(object):
    """R242: what `X.ViewObject` is headless - see _ViewRewrite."""

    def __init__(self, rec, obj, store):
        object.__setattr__(self, "_rec", rec)
        object.__setattr__(self, "_obj", obj)
        object.__setattr__(self, "_store", store)

    def __setattr__(self, name, value):
        self._rec(self._obj, name, value)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name in ("hide", "show"):
            vis = name == "show"
            return lambda *a, **k: self._rec(self._obj, "Visibility", vis)
        got = self._store.get(getattr(self._obj, "Name", None) or "", {})
        if name in got:
            return got[name]
        if name in VIEW_DEFAULTS:
            return VIEW_DEFAULTS[name]
        return _NoOp()

    def __bool__(self):
        return True


def view_recorder(store):
    """The function installed as __atech_view__: keeps JSON-safe values of
    the display properties Studio can carry over, per object Name. Called
    with the object alone, it returns the object's stand-in ViewObject
    (R242). R250: the store is also kept as the last one made, for
    face_open's see-through parts (part_transparency)."""
    _VIEW_STORE[0] = store

    def rec(obj, attr=_NOARG, value=_NOARG):
        if attr is _NOARG:
            real = getattr(obj, "ViewObject", None)
            return real if real is not None else _ViewStandIn(rec, obj, store)
        name = getattr(obj, "Name", None)
        if not name or attr not in VIEW_KEYS:
            return None
        store.setdefault(name, {})[attr] = _jsonable(value)
        return None
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


# ============================================ R440 archetype gates (WS4)
# R440 (round 1, 2026-10-20): a sealed car, a blank-faced robot, a slab
# speaker and a postage-stamp handheld all ended on CHECK PASS - the
# archetype rules (build.ARCHETYPES) were prompt text and NOTE lines only.
# Each rule a judge scored as fatal is MEASURED here on orthographic owner
# images of the build (review.ortho_image: which body a pixel's ray meets
# first, and where), and is a PROBLEM in quality mode that names the
# number and the fix. Keyed by the user's words in build.ARCHETYPES'
# categories (test_check_gates_r280 holds the two tables equal).
ARCHETYPE_GATES = (
    ("vehicle", ("car", "truck", "tank", "boat", "vehicle", "rover",
                 "buggy", "4x4", "bus", "tractor", "train", "kart"), "vehicle"),
    ("robot or character", ("robot", "character", "pet", "creature",
                            "mascot", "animal", "droid", "buddy"), "robot"),
    ("speaker", ("speaker", "radio", "soundbar", "boombox"), "speaker"),
    ("handheld", ("handheld", "controller", "gamepad", "remote", "console",
                  "game", "pager", "tamagotchi"), "handheld"),
    ("lamp", ("lamp", "lantern", "nightlight", "night light", "desk light"), "lamp"),
    ("clock", ("clock", "alarm", "timer"), "clock"),
    ("fan", ("fan",), "fan"),
    ("weather station", ("weather", "thermometer", "barometer", "station"), None),
)
HANDHELD_SCREEN_MIN = 0.30      # dark screen region / front face, at least
HANDHELD_THICK_MAX_MM = 32.0    # body thickness where held, under
HANDHELD_GRIP_SHARE = 0.30      # the grips: the outer 30 % at each end
ROBOT_WINDOW_MIN_MM = 35.0      # the face window, at least this wide
ROBOT_WINDOW_TOP = 0.45         # ...its centre in the top 45 % of the height
SPEAKER_HEIGHT_MIN = 0.40       # height / footprint (its narrow side)
SPEAKER_GRILLE_MIN = 0.15       # grille open area / the top (or side band)
SPEAKER_BAND_MIN = 0.40         # a side band is at least 40 % of the height
VEHICLE_LENGTH_MIN = 1.5        # length / width
VEHICLE_WHEEL_END = 0.25        # a wheel within 25 % of each end
LAMP_HEIGHT_MIN = 1.6           # height / foot diameter
LAMP_FOOT_SLICE = 0.08          # the foot: the bottom 8 % (>= 2 mm) of the height
CLOCK_DISPLAY_MIN = 0.35        # display / front face
FAN_GUARD_MIN = 0.50            # guard opening / front face
FAN_RECESS_MM = 8.0             # ...a pixel this far behind the front is open
DARK_LUM = 0.30                 # a colour darker than this reads as screen glass
SEE_THROUGH_MIN = 30.0          # % transparency: a lens / smoked glass
ARCH_PX_MIN = 0.35              # mm per pixel, at least
ARCH_PX_N = 420                 # pixels along the longest side, at most
OPEN_DEPTH_MM = 1.5             # a pixel this far under the closed skin is open
OPEN_CLOSE_MM = 3.0             # ...the skin closed over holes this wide (half)
WHEEL_WORDS = ("wheel", "wheels", "tyre", "tyres", "tire", "tires", "track",
               "tracks", "tread", "treads")
WHEEL_NOT = ("arch", "arches", "well", "wells", "fender", "fenders", "guard",
             "flare", "flares", "cover", "spare", "hub", "cap", "trim")
DIAL_WORDS = ("dial", "display", "clockface", "lcd", "screen")
ROTOR_WORDS = ("blade", "blades", "rotor", "impeller", "propeller", "fan")
DIFFUSER_WORDS = ("shade", "globe", "diffuser", "lens", "lampshade", "bulb", "window")


def archetype_of(request):
    """R440: (label, gate key) of the ARCHETYPE_GATES row whose words the
    user's message uses - the first row in table order, as
    build._archetype_of - or (None, None)."""
    import re
    low = (request or "").lower()
    for label, words, gate in ARCHETYPE_GATES:
        if any(re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(w), low) for w in words):
            return label, gate
    return None, None


def _tokens(label):
    import re
    return [t for t in re.split(r"[^a-z]+", str(label or "").lower()) if t]


def _rgb(part):
    """The part's chosen colour (view ShapeColor, or "color"), or None."""
    c = (part.get("view") or {}).get("ShapeColor")
    if c is None:
        c = part.get("color")
    try:
        return tuple(float(x) for x in tuple(c)[:3]) if c is not None else None
    except (TypeError, ValueError):
        return None


def _lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


ARCH_LOOPS_MAX = 2500          # R440: a face of more holes is left out (said so)


def _tess_anyway(shape):
    """Triangles of a shape _tess refuses (a face of many holes), or None."""
    import numpy as np
    try:
        pts, faces = shape.tessellate(_deflection(shape))
    except Exception:                                   # noqa: BLE001
        return None
    P = np.array([(p.x, p.y, p.z) for p in pts], dtype=float).reshape(-1, 3)
    F = np.array(faces, dtype=int).reshape(-1, 3)
    return P[F] if len(F) else None


def _arch_scene(parts, mods):
    """The build as one triangle soup for the owner images: designed
    parts (ribbon cables kept, flagged), the board and the modules.
    {"T", "O", "objs": [{"label", "kind", "module", "dark", "see", "rgb",
    "P" (its points)}], "box": (lo, hi) of the designed bodies, "skipped"}."""
    import numpy as np
    objs, Ts, Os, skipped = [], [], [], []
    for p in parts:
        sh = p.get("shape")
        if sh is None:
            continue
        try:
            P, T = _tess(sh)
        except SlowToTessellate:
            # R440: a grille plate is exactly what the speaker gate looks
            # at; review.png tessellates it anyway (OCCT keeps the
            # triangulation on the shape, so the sheet reuses this one)
            T = _tess_anyway(sh) if busiest_face_loops(sh) <= ARCH_LOOPS_MAX else None
            if T is None:
                skipped.append(p.get("label"))
                continue
        except Exception:                               # noqa: BLE001
            continue
        if not len(T):
            continue
        rgb = _rgb(p)
        tr = part_transparency(p)
        k = len(objs)
        objs.append({"label": p.get("label"), "kind": "cable" if p.get("cable") else "part",
                     "module": None, "rgb": rgb, "transparency": tr,
                     "dark": rgb is not None and _lum(rgb) < DARK_LUM,
                     "see": tr >= SEE_THROUGH_MIN, "P": T.reshape(-1, 3)})
        Ts.append(T)
        Os.append(np.full(len(T), k))
    for m in mods:
        if m.get("mesh") is None:
            continue
        T = _mesh_tris(m["mesh"])
        if not len(T):
            continue
        k = len(objs)
        role = m.get("role") or "module"
        objs.append({"label": m.get("label"), "kind": "board" if role == "board" else "module",
                     "name": m.get("name"), "module": m.get("module"), "axes": m.get("axes"),
                     "rgb": None, "transparency": 0.0,
                     "dark": str(m.get("module") or "") == "screen", "see": False,
                     "P": T.reshape(-1, 3)})
        Ts.append(T)
        Os.append(np.full(len(T), k))
    if not Ts:
        return None
    body = [o["P"] for o in objs if o["kind"] == "part"]
    if not body:
        return None
    B = np.vstack(body)
    return {"T": np.concatenate(Ts), "O": np.concatenate(Os), "objs": objs,
            "box": (B.min(axis=0), B.max(axis=0)), "skipped": skipped, "_img": {}}


def _arch_image(sc, v, up=(0.0, 0.0, 1.0), back=False):
    """The owner image of the scene seen from v (cached per direction)."""
    import numpy as np
    import review
    key = (tuple(round(float(x), 4) for x in v), tuple(up), back)
    if key in sc["_img"]:
        return sc["_img"][key]
    r, u, _v = review.ortho_frame(v, up)
    lo, hi = sc["box"]
    C = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1])
                  for z in (lo[2], hi[2])])
    xs, ys = C @ r, C @ u
    span = max(xs.max() - xs.min(), ys.max() - ys.min(), 1.0)
    px = max(ARCH_PX_MIN, span / ARCH_PX_N)
    img = review.ortho_image(sc["T"], sc["O"], v, up, px,
                             (xs.min(), ys.min()), (xs.max(), ys.max()), back=back)
    sc["_img"][key] = img
    return img


def _to_px(img, P):
    """Pixel (col, row) of world points P (n,3) in `img`."""
    import numpy as np
    r, u, _v = img["frame"]
    x0, y0 = img["lo"]
    P = np.asarray(P, float).reshape(-1, 3)
    return (np.floor((P @ r - x0) / img["px"]).astype(int),
            np.floor((P @ u - y0) / img["px"]).astype(int))


def _px_world(img, rows, cols):
    """World points of pixel centres on the picture plane (depth 0)."""
    import numpy as np
    r, u, _v = img["frame"]
    x0, y0 = img["lo"]
    x = x0 + (np.asarray(cols) + 0.5) * img["px"]
    y = y0 + (np.asarray(rows) + 0.5) * img["px"]
    return np.outer(x, r) + np.outer(y, u)


def _shift(A, s, axis, fill):
    import numpy as np
    out = np.full_like(A, fill)
    if s > 0:
        sl_o = [slice(None)] * 2
        sl_i = [slice(None)] * 2
        sl_o[axis], sl_i[axis] = slice(s, None), slice(None, -s)
        out[tuple(sl_o)] = A[tuple(sl_i)]
    elif s < 0:
        sl_o = [slice(None)] * 2
        sl_i = [slice(None)] * 2
        sl_o[axis], sl_i[axis] = slice(None, s), slice(-s, None)
        out[tuple(sl_o)] = A[tuple(sl_i)]
    else:
        out[...] = A
    return out


def _filter(A, k, op, fill):
    """Separable square (2k+1) max / min filter (op np.maximum / minimum)."""
    out = A
    for axis in (0, 1):
        acc = out.copy()
        for s in range(1, k + 1):
            acc = op(acc, _shift(out, s, axis, fill))
            acc = op(acc, _shift(out, -s, axis, fill))
        out = acc
    return out


def _flood(mask, seeds):
    """The 4-connected parts of `mask` that hold a seed pixel."""
    import numpy as np
    try:
        from scipy import ndimage
        lab, _n = ndimage.label(mask)
        ids = np.unique(lab[seeds & mask])
        ids = ids[ids > 0]
        return np.isin(lab, ids)
    except Exception:                                   # noqa: BLE001
        pass
    cur = seeds & mask
    for _i in range(4 * sum(mask.shape)):
        nxt = cur.copy()
        nxt[1:, :] |= cur[:-1, :]
        nxt[:-1, :] |= cur[1:, :]
        nxt[:, 1:] |= cur[:, :-1]
        nxt[:, :-1] |= cur[:, 1:]
        nxt &= mask
        if (nxt == cur).all():
            break
        cur = nxt
    return cur


def _ids(sc, test):
    import numpy as np
    return np.array([i for i, o in enumerate(sc["objs"]) if test(o)], dtype=int)


def _open_mask(sc, img, extra=()):
    """R440: the pixels of `img` that look INTO the product: the first hit
    is an Atech part (the ray passed the shell), a part named in `extra`,
    or a surface more than OPEN_DEPTH_MM under the skin closed over holes
    up to 2 x OPEN_CLOSE_MM wide (a grille hole, a slot)."""
    import numpy as np
    own, dep = img["owner"], img["depth"]
    sil = own >= 0
    inner = _ids(sc, lambda o: o["kind"] in ("board", "module", "cable")
                 or o["label"] in extra)
    k = max(1, int(round(OPEN_CLOSE_MM / img["px"])))
    D = np.where(sil, dep, -1e9)
    clo = _filter(_filter(D, k, np.maximum, -1e9), k, np.minimum, -1e9)
    deep = sil & (clo > -1e8) & (clo - D > OPEN_DEPTH_MM)
    return sil & (np.isin(own, inner) | deep)


def _module_dir(m, word=None):
    """A module's working direction in world (unit numpy) - its face named
    `word` (a DC motor's "shaft"), else its +u (away from the board)."""
    import numpy as np
    wd = working_dirs(m.get("module"), m.get("axes"))
    if not wd:
        return None
    faces = list(wd.get("faces") or ())
    words = (word,) if isinstance(word, str) else tuple(word or ())
    for f in faces:
        if words and f.get("word") in words:
            return np.asarray(f["dir"], float)
    if words:
        # R440: the library names a DC motor's proud face "out", not
        # "shaft" - the face that stands proud is the working one
        proud = [f for f in faces if (f.get("proud_mm") or 0) > 0]
        if proud:
            return np.asarray(max(proud, key=lambda f: f["proud_mm"])["dir"], float)
    return np.asarray(wd["up"], float)


def _screen_patch(sc, img, k):
    """R440: the dark screen region round screen object k in `img`: the
    4-connected dark / see-through / screen pixels that hold the screen's
    own footprint (cover glass + bezel mask + the screen itself)."""
    import numpy as np
    own = img["owner"]
    darkish = _ids(sc, lambda o: o["dark"] or o["see"])
    mask = np.isin(own, darkish) | (own == k)
    c, r = _to_px(img, sc["objs"][k]["P"])
    H, W = own.shape
    seeds = np.zeros_like(mask)
    c0, c1 = max(0, c.min()), min(W - 1, c.max())
    r0, r1 = max(0, r.min()), min(H - 1, r.max())
    if c0 <= c1 and r0 <= r1:
        seeds[r0:r1 + 1, c0:c1 + 1] = True
    return _flood(mask, seeds & mask)


def _area(mask, img):
    return float(mask.sum()) * img["px"] ** 2


def _extent_mm(img, mask, axis_vec):
    """Extent of `mask`'s pixels along a world direction (mm)."""
    import numpy as np
    rows, cols = np.nonzero(mask)
    if not len(rows):
        return 0.0, None
    W = _px_world(img, rows, cols) @ np.asarray(axis_vec, float)
    return float(W.max() - W.min() + img["px"]), W


def _horizontal(v):
    import numpy as np
    h = np.cross([0.0, 0.0, 1.0], v)
    n = np.linalg.norm(h)
    return h / n if n > 1e-6 else np.array([1.0, 0.0, 0.0])


def _screens(sc):
    return [i for i, o in enumerate(sc["objs"]) if o["kind"] == "module"
            and str(o.get("module") or "") == "screen"]


def _front_of(sc, k):
    """View direction (toward the viewer) of the screen object k."""
    o = sc["objs"][k]
    return _module_dir({"module": o["module"], "axes": o.get("axes")})


def _gate_screen_share(sc, need, what, fix):
    """(facts, problem or None, note) - the dark screen region's share of
    the front face; None facts when there is no screen to measure."""
    scr = _screens(sc)
    if not scr:
        return None, None, "no screen module - the %s share is not measured" % what
    k = scr[0]
    v = _front_of(sc, k)
    if v is None:
        return None, None, "the screen's facing is unknown - not measured"
    img = _arch_image(sc, v, _up_for(v))
    sil = img["owner"] >= 0
    patch = _screen_patch(sc, img, k)
    face, pa = _area(sil, img), _area(patch, img)
    share = pa / face if face > 0 else 0.0
    facts = {"screen": sc["objs"][k]["label"], "screen_region_mm2": round(pa),
             "front_mm2": round(face), "screen_share": round(share, 3),
             "front": [round(float(x), 3) for x in v]}
    if share >= need:
        return facts, None, "%s %d %% of the front face (>= %d %%)" % (
            what, round(100 * share), round(100 * need))
    want = need * face
    w, _W = _extent_mm(img, sil, img["frame"][0])
    h, _H = _extent_mm(img, sil, img["frame"][1])
    aspect = (w / h) if h > 0 else 1.6
    ww = (want * aspect) ** 0.5
    return facts, ("%s round %s is %d %% of the front face (%.0f of %.0f mm2, seen "
                   "from %s) - under %d %%, it reads as a postage stamp. %s: at least "
                   "%.0f mm2, e.g. %.0f x %.0f mm" % (
                       what, sc["objs"][k]["label"], round(100 * share), pa, face,
                       _dir_name(v), round(100 * need), fix, want, ww, want / ww)), None


def _up_for(v):
    import numpy as np
    return (0.0, 1.0, 0.0) if abs(float(np.asarray(v)[2])) > 0.8 else (0.0, 0.0, 1.0)


def _gate_handheld(sc, request):
    import numpy as np
    out = {"problems": [], "notes": [], "facts": {}}
    facts, bad, ok = _gate_screen_share(
        sc, HANDHELD_SCREEN_MIN, "the dark screen region (cover glass + black bezel mask)",
        "Grow the cover glass and its black printed bezel mask over the face (a "
        "handheld's screen glass is 40 % of the front) - the mask may run past the "
        "window, the window stays over the active area")
    if facts:
        out["facts"].update(facts)
    (out["problems"].append(bad) if bad else out["notes"].append(ok))
    # thickness where held: the outer HANDHELD_GRIP_SHARE at each end of
    # the long side of the face
    v = np.asarray(facts["front"]) if facts else None
    if v is None:
        lo, hi = sc["box"]
        k = int(np.argmin(hi - lo))
        v = np.eye(3)[k]
    up = _up_for(v)
    fr = _arch_image(sc, v, up)
    bk = _arch_image(sc, v, up, back=True)
    sil = (fr["owner"] >= 0) & (bk["owner"] >= 0)
    th = np.where(sil, fr["depth"] - bk["depth"], np.nan)
    rows, cols = np.nonzero(sil)
    if not len(rows):
        return out
    long_c = np.ptp(cols) >= np.ptp(rows)
    t = cols if long_c else rows
    a, b = t.min(), t.max()
    g = HANDHELD_GRIP_SHARE * (b - a)
    ends = []
    for sel in (t <= a + g, t >= b - g):
        vals = th[rows[sel], cols[sel]]
        vals = vals[np.isfinite(vals)]
        if len(vals):
            ends.append(float(np.median(vals)))
    if not ends:
        return out
    held = max(ends)
    out["facts"]["held_thickness_mm"] = round(held, 1)
    if held >= HANDHELD_THICK_MAX_MM:
        out["problems"].append(
            "the body is %.1f mm thick where held (the median over the grips, the outer "
            "%d %% at each end) - %g mm or more and the hands cannot close round it, it "
            "reads as a brick. Thin the grips to 20-28 mm: bring the back in toward the "
            "board, crown the back and taper the grip bellies" % (
                held, round(100 * HANDHELD_GRIP_SHARE), HANDHELD_THICK_MAX_MM))
    else:
        out["notes"].append("%.0f mm thick where held (< %g mm)" % (held, HANDHELD_THICK_MAX_MM))
    return out


def _gate_robot(sc, request):
    import numpy as np
    out = {"problems": [], "notes": [], "facts": {}}
    scr = _screens(sc)
    if not scr:
        out["notes"].append("no screen module - the face window is not measured (a robot's "
                            "face reads blank without screen eyes or lights)")
        return out
    k = scr[0]
    v = _front_of(sc, k)
    if v is None:
        out["notes"].append("the screen's facing is unknown - not measured")
        return out
    img = _arch_image(sc, v, _up_for(v))
    patch = _screen_patch(sc, img, k)
    hz = _horizontal(v)
    width, Wp = _extent_mm(img, patch, hz)
    lo, hi = sc["box"]
    H = float(hi[2] - lo[2]) or 1.0
    rows, cols = np.nonzero(patch)
    cz = float(_px_world(img, rows, cols)[:, 2].mean()) if len(rows) else None
    # an upright view: the picture's u is world z, so a pixel's height is
    # its row; a face looking up has no height on the picture - use the
    # screen's own centre
    if cz is None or abs(float(v[2])) > 0.8:
        cz = float(sc["objs"][k]["P"][:, 2].mean())
    frac = (cz - float(lo[2])) / H
    out["facts"].update({"screen": sc["objs"][k]["label"], "window_mm": round(width, 1),
                         "window_height_frac": round(frac, 3)})
    if width < ROBOT_WINDOW_MIN_MM:
        out["problems"].append(
            "the face window round %s is %.0f mm wide - under %g mm the robot reads "
            "blank-faced. Make the screen's smoked visor (and its black mask) %g mm "
            "wide or more across the head: the screen is the eyes" % (
                sc["objs"][k]["label"], width, ROBOT_WINDOW_MIN_MM, ROBOT_WINDOW_MIN_MM))
    if frac < 1.0 - ROBOT_WINDOW_TOP:
        out["problems"].append(
            "the face window round %s sits %d %% up the robot's %.0f mm height - a "
            "face sits in the head, the top %d %%. Move the screen up into the head "
            "(its centre %.0f mm above the desk or higher), or make the head bigger "
            "(40 %% of the height)" % (
                sc["objs"][k]["label"], round(100 * frac), H, round(100 * ROBOT_WINDOW_TOP),
                float(lo[2]) + (1.0 - ROBOT_WINDOW_TOP) * H))
    if not out["problems"]:
        out["notes"].append("face window %.0f mm wide (>= %g), %d %% up (top %d %%)" % (
            width, ROBOT_WINDOW_MIN_MM, round(100 * frac), round(100 * ROBOT_WINDOW_TOP)))
    return out


def _side_band(sc, img, opn, H):
    """Open share of a side view over the band of rows its open pixels
    span (at least SPEAKER_BAND_MIN of the height)."""
    import numpy as np
    sil = img["owner"] >= 0
    rows, _c = np.nonzero(opn)
    if not len(rows):
        return 0.0
    r0, r1 = rows.min(), rows.max()
    need = int(np.ceil(SPEAKER_BAND_MIN * H / img["px"]))
    if r1 - r0 + 1 < need:
        mid = (r0 + r1) // 2
        r0, r1 = mid - need // 2, mid - need // 2 + need - 1
    band = np.zeros_like(sil)
    band[max(0, r0):max(0, r1 + 1), :] = True
    reg = sil & band
    return float((opn & reg).sum()) / max(1.0, float(reg.sum()))


def _gate_speaker(sc, request):
    import numpy as np
    out = {"problems": [], "notes": [], "facts": {}}
    lo, hi = sc["box"]
    H = float(hi[2] - lo[2])
    foot = float(min(hi[0] - lo[0], hi[1] - lo[1])) or 1.0
    ratio = H / foot
    out["facts"]["height_ratio"] = round(ratio, 3)
    if ratio < SPEAKER_HEIGHT_MIN:
        out["problems"].append(
            "the speaker is %.0f mm tall on a %.0f mm footprint (%.2f x) - under %.1f x "
            "it is a slab. Make it %.0f mm tall or more (a column or a deep puck), or "
            "narrow the footprint" % (H, foot, ratio, SPEAKER_HEIGHT_MIN,
                                      np.ceil(SPEAKER_HEIGHT_MIN * foot)))
    top = _arch_image(sc, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
    opn = _open_mask(sc, top)
    sil = top["owner"] >= 0
    top_share = float(opn.sum()) / max(1.0, float(sil.sum()))
    side_share, side_dir = 0.0, None
    for v in ((0, -1, 0), (1, 0, 0), (0, 1, 0), (-1, 0, 0)):
        img = _arch_image(sc, v)
        s = _side_band(sc, img, _open_mask(sc, img), H)
        if s > side_share:
            side_share, side_dir = s, v
    out["facts"].update({"grille_top_share": round(top_share, 3),
                         "grille_side_share": round(side_share, 3)})
    best = max(top_share, side_share)
    if best < SPEAKER_GRILLE_MIN:
        out["problems"].append(
            "the grille's open area is %d %% of the top (%d %% of the best side band) - "
            "under %d %% the speaker reads as a closed box with a few pin holes. Make the "
            "grille the hero: holes or slots over %d %% of the top (cad.speaker_grille / "
            "cad.grille over most of it, 2-3 mm holes at 3.5-4.5 mm pitch) or a "
            "perforated band round the side" % (
                round(100 * top_share), round(100 * side_share),
                round(100 * SPEAKER_GRILLE_MIN), round(100 * SPEAKER_GRILLE_MIN)))
    if not out["problems"]:
        out["notes"].append("%.2f x tall, grille %d %% open (%s)" % (
            ratio, round(100 * best), "top" if top_share >= side_share
            else "side " + _dir_name(side_dir)))
    return out


def _wheels(parts, z0, H):
    rows = []
    for p in parts:
        tk = _tokens(p.get("label"))
        if not any(t in WHEEL_WORDS for t in tk) or any(t in WHEEL_NOT for t in tk):
            continue
        try:
            bb = tight(p["shape"])
        except Exception:                               # noqa: BLE001
            continue
        if bb.ZMin > z0 + max(2.0, 0.12 * H):           # not on the ground (a spare)
            continue
        rows.append((p["label"], bb))
    return rows


def _gate_vehicle(sc, request, parts):
    import re
    out = {"problems": [], "notes": [], "facts": {}}
    lo, hi = sc["box"]
    dx, dy = float(hi[0] - lo[0]), float(hi[1] - lo[1])
    k = 0 if dx >= dy else 1
    L, Wd = max(dx, dy), min(dx, dy) or 1.0
    ratio = L / Wd
    out["facts"]["length_ratio"] = round(ratio, 3)
    if ratio < VEHICLE_LENGTH_MIN:
        out["problems"].append(
            "the vehicle is %.0f mm long and %.0f mm wide (%.2f x) - under %.1f x it "
            "reads as a box on wheels. Stretch it to %.0f mm or more (a nose and a "
            "tail past the wheels) or narrow the body" % (
                L, Wd, ratio, VEHICLE_LENGTH_MIN, VEHICLE_LENGTH_MIN * Wd))
    body = [p for p in parts if not p.get("cable") and p.get("shape") is not None]
    whl = _wheels(body, float(lo[2]), float(hi[2] - lo[2]))
    if not whl:
        if re.search(r"\b(boat|ship|yacht|hovercraft)\b", (request or "").lower()):
            out["notes"].append("a boat: no wheels expected")
        else:
            out["problems"].append(
                "no wheel or track on the ground - nothing labelled Wheel_*, Tyre_* or "
                "Track_* reaches the desk. A vehicle stands on its wheels: four at the "
                "corners (two tracks for a tank), labelled so")
        return out
    a0 = float(lo[k])
    pos = []
    front = rear = False
    for label, bb in whl:
        mn, mx = (bb.XMin, bb.XMax) if k == 0 else (bb.YMin, bb.YMax)
        t0, t1 = (mn - a0) / L, (mx - a0) / L
        if t1 - t0 >= 0.5:                              # a track runs the length
            front |= t0 <= VEHICLE_WHEEL_END
            rear |= t1 >= 1.0 - VEHICLE_WHEEL_END
        else:
            c = 0.5 * (t0 + t1)
            front |= c <= VEHICLE_WHEEL_END
            rear |= c >= 1.0 - VEHICLE_WHEEL_END
        pos.append(round(0.5 * (t0 + t1), 3))
    out["facts"]["wheel_positions"] = sorted(pos)
    if not (front and rear):
        out["problems"].append(
            "the wheels sit at %s of the length (0 = one end, 1 = the other) - a wheel "
            "within %d %% of %s is missing: the stance reads wrong. Put the axles near the "
            "ends (overhangs of 10-20 %% of the length)" % (
                ", ".join("%.2f" % x for x in sorted(pos)), round(100 * VEHICLE_WHEEL_END),
                "each end" if not (front or rear) else "one end"))
    if not out["problems"]:
        out["notes"].append("%.2f x long, wheels at %s" % (
            ratio, ", ".join("%.2f" % x for x in sorted(pos))))
    return out


def _gate_lamp(sc, request, parts):
    import numpy as np
    out = {"problems": [], "notes": [], "facts": {}}
    lo, hi = sc["box"]
    H = float(hi[2] - lo[2])
    P = np.vstack([o["P"] for o in sc["objs"] if o["kind"] == "part"])
    low = P[P[:, 2] <= lo[2] + max(2.0, LAMP_FOOT_SLICE * H)]
    foot = float(max(np.ptp(low[:, 0]), np.ptp(low[:, 1]))) if len(low) else 0.0
    ratio = H / foot if foot > 0 else 0.0
    out["facts"].update({"height_ratio": round(ratio, 3), "foot_mm": round(foot, 1)})
    if foot > 0 and ratio < LAMP_HEIGHT_MIN:
        out["problems"].append(
            "the lamp is %.0f mm tall on a %.0f mm foot (%.2f x) - under %.1f x it reads "
            "as a jar. Raise the light on a stem or column to %.0f mm or more, or "
            "narrow the foot" % (H, foot, ratio, LAMP_HEIGHT_MIN, LAMP_HEIGHT_MIN * foot))
    top = lo[2] + 2.0 * H / 3.0
    lit = []
    for o in sc["objs"]:
        glow = (o["kind"] == "module" and str(o.get("module") or "") == "light") or (
            o["kind"] == "part" and (o["see"] or any(t in DIFFUSER_WORDS
                                                     for t in _tokens(o["label"]))))
        if glow and float(o["P"][:, 2].mean()) >= top:
            lit.append(o["label"])
    out["facts"]["light_top"] = lit
    if not lit:
        out["problems"].append(
            "no light in the top third (above %.0f mm): no light module, shade or "
            "diffuser sits there - a lamp's light is high in its head. Put the shade "
            "/ globe (see-through, over a cabled light) at the top" % top)
    if not out["problems"]:
        out["notes"].append("%.2f x tall, light high (%s)" % (ratio, ", ".join(lit[:3])))
    return out


def _gate_clock(sc, request, parts):
    import numpy as np
    out = {"problems": [], "notes": [], "facts": {}}
    if _screens(sc):
        facts, bad, ok = _gate_screen_share(
            sc, CLOCK_DISPLAY_MIN, "the display (the screen behind its glass and mask)",
            "Make the display the hero: a smoked lens and black mask over half the front, "
            "the screen centred in it")
        out["facts"].update(facts or {})
        (out["problems"].append(bad) if bad else out["notes"].append(ok))
        return out
    dial = _ids(sc, lambda o: o["kind"] == "part"
                and any(t in DIAL_WORDS for t in _tokens(o["label"])))
    if not len(dial):
        out["notes"].append("no screen module and no part labelled Dial / Display - the "
                            "display share is not measured")
        return out
    best, bdir = 0.0, None
    for v in ((0, -1, 0), (1, 0, 0), (0, 1, 0), (-1, 0, 0)):
        img = _arch_image(sc, v)
        sil = img["owner"] >= 0
        s = float(np.isin(img["owner"], dial).sum()) / max(1.0, float(sil.sum()))
        if s > best:
            best, bdir = s, v
    out["facts"]["dial_share"] = round(best, 3)
    if best < CLOCK_DISPLAY_MIN:
        out["problems"].append(
            "the dial is %d %% of the front face - under %d %% the clock reads as a box "
            "with a label. Make the dial / display face half the front" % (
                round(100 * best), round(100 * CLOCK_DISPLAY_MIN)))
    else:
        out["notes"].append("dial %d %% of the front (%s)" % (round(100 * best), _dir_name(bdir)))
    return out


def _fan_front(sc, img, sil, rot):
    """R504: the guard's front - the nearest depth over the ROTOR's own
    footprint in `img` (its points' pixel box), not over the whole
    silhouette: a desk fan's foot stands forward of the guard, and with the
    global front every pixel of a SOLID guard read as "far behind the
    front", i.e. open (MEASURED: a fully closed guard scored 91 %). Without
    a rotor (or none of it in the picture): the whole silhouette's front."""
    import numpy as np
    dep = img["depth"]
    if not sil.any():
        return 0.0
    H, W = sil.shape
    box = np.zeros_like(sil)
    for o in sc["objs"]:
        if o["kind"] != "part" or o["label"] not in rot or not len(o["P"]):
            continue
        c, r = _to_px(img, o["P"])
        c0, c1 = max(0, int(c.min())), min(W - 1, int(c.max()))
        r0, r1 = max(0, int(r.min())), min(H - 1, int(r.max()))
        if c0 <= c1 and r0 <= r1:
            box[r0:r1 + 1, c0:c1 + 1] = True
    m = box & sil
    return float(dep[m].max()) if m.any() else float(dep[sil].max())


def _gate_fan(sc, request, parts):
    import numpy as np
    out = {"problems": [], "notes": [], "facts": {}}
    rot = tuple(o["label"] for o in sc["objs"] if o["kind"] == "part"
                and any(t in ROTOR_WORDS for t in _tokens(o["label"])))
    motors = [o for o in sc["objs"] if o["kind"] == "module"
              and str(o.get("module") or "") == "dc_motor"]
    dirs = []
    if motors:
        d = _module_dir({"module": motors[0]["module"], "axes": motors[0].get("axes")},
                        ("shaft", "out"))
        if d is not None:
            dirs = [tuple(d)]                           # the blades: along the shaft
    dirs = dirs or [(0, -1, 0), (1, 0, 0), (0, 1, 0), (-1, 0, 0)]
    best, bdir = 0.0, None
    for v in dirs:
        img = _arch_image(sc, v, _up_for(v))
        sil = img["owner"] >= 0
        opn = _open_mask(sc, img, rot)
        # a guard's wide gaps show the rotor's chamber far behind the face:
        # deeper than FAN_RECESS_MM under the front is open too
        dep = img["depth"]
        front = _fan_front(sc, img, sil, rot)
        opn |= sil & (dep < front - FAN_RECESS_MM)
        k = max(1, int(round(OPEN_CLOSE_MM / img["px"])))
        o8 = opn.astype(float)
        guard = _filter(_filter(o8, k, np.maximum, 0.0), k, np.minimum, 0.0) > 0.5
        s = float((guard & sil).sum()) / max(1.0, float(sil.sum()))
        if s > best:
            best, bdir = s, v
    out["facts"]["guard_share"] = round(best, 3)
    if best < FAN_GUARD_MIN:
        out["problems"].append(
            "the guard opening is %d %% of the front face - under %d %% the fan reads as "
            "a box with vents. Make the rotor's guard (open bars over the blades) %d %% "
            "of the front or more, on a slimmer stand" % (
                round(100 * best), round(100 * FAN_GUARD_MIN), round(100 * FAN_GUARD_MIN)))
    else:
        out["notes"].append("guard opening %d %% of the front (%s)" % (
            round(100 * best), _dir_name(bdir)))
    return out


def archetype_problems(parts, mods, request, mode=None):
    """R440: the measured archetype gates for the user's request.

    parts: the agent's bodies [{"label", "shape", "view" (recorded view
    props), "cable": bool}]; mods: the Atech meshes [{"label", "name",
    "mesh", "module", "axes", "role"}]. Returns {"archetype", "facts",
    "problems", "warnings", "notes", "misses"}. R500: "problems" is ALWAYS
    empty - the gates judge style, not function, and never block a design.
    R600 (the user, 2026-10-26: "it overfits too much to be a box now"):
    "warnings" is ALWAYS empty too - a miss is one plain NOTE line (quality
    mode: "a design note, not a gate"; fast mode: "not judged"), so the
    agent is never pulled toward the numbers; "misses" lists them for
    callers that want them. An archetype with no measured gate (weather
    station) or a request naming none: nothing."""
    label, gate = archetype_of(request)
    res = {"archetype": label, "facts": {}, "problems": [], "warnings": [], "notes": [],
           "misses": []}
    if label is None:
        return res
    if gate is None:
        res["notes"].append("ARCHETYPE %s: no measured gate - judge it on review.png" % label)
        return res
    sc = _arch_scene(parts, mods)
    if sc is None:
        res["notes"].append("ARCHETYPE %s: nothing to measure" % label)
        return res
    fn = {"handheld": _gate_handheld, "robot": _gate_robot, "speaker": _gate_speaker}
    if gate in fn:
        got = fn[gate](sc, request)
    else:
        got = {"vehicle": _gate_vehicle, "lamp": _gate_lamp, "clock": _gate_clock,
               "fan": _gate_fan}[gate](sc, request, parts)
    res["facts"] = got["facts"]
    if sc["skipped"]:
        res["facts"]["not_drawn"] = sc["skipped"]
    head = "ARCHETYPE %s: " % label
    quality = quality_mode() if mode is None else mode == "quality"
    # R500 (lead decision): the archetype gates judge STYLE, not function -
    # they never block a design. R600: nor do they warn - every mode gets
    # one NOTE line; "problems" and "warnings" stay empty.
    res["warnings"] = []
    res["misses"] = [head + p for p in got["problems"]]
    if got["problems"]:
        tail = (" (a design note, not a gate)" if quality else
                " (fast mode: not judged)")
    else:
        tail = " - the archetype's silhouette and hero pass"
    res["notes"] = [head + "; ".join(got["problems"] + got["notes"]) + tail]
    return res


# ================================== R441 fastening / R442 holders (WS4)
# R441 (round 1): the toy car's body sat on its chassis and its hardtop on
# the body with nothing holding either - a lip locates a part, it does not
# hold it. Every pair of HOUSING parts that meet must be joined by a
# fastener that reaches both: a screw, a pin, a snap or clip - or the
# part is captured between two parts that are.
HOUSING_DIAG = 0.35         # a housing part's box diagonal / the product's, at least
MEET_MM = 0.3               # two parts this close meet
FASTENER_REACH_MM = 1.0     # a fastener this close to both parts joins them
                            # (a screw shank in a clearance or insert bore)
FASTENER_WORDS = ("screw", "screws", "bolt", "bolts", "pin", "pins", "dowel", "dowels",
                  "rivet", "rivets", "peg", "pegs", "clip", "clips", "snap", "snaps",
                  "latch", "latches", "catch", "catches", "hook", "hooks", "magnet",
                  "magnets", "nut", "nuts", "hinge", "hinges", "axle", "standoff")
SNAP_CALLS = ("snap_fit_pair(", "snap_fit_cantilever(")
NEAR_SAMPLES = 6000         # surface points per part side, at most


def _tris(shape):
    """Triangles of a shape (the slow-to-tessellate ones too, when they
    stay under ARCH_LOOPS_MAX), or an empty array."""
    import numpy as np
    try:
        return _tess(shape)[1]
    except SlowToTessellate:
        if busiest_face_loops(shape) <= ARCH_LOOPS_MAX:
            T = _tess_anyway(shape)
            if T is not None:
                return T
    except Exception:                                   # noqa: BLE001
        pass
    return np.zeros((0, 3, 3))


def _in_box(T, lo, hi):
    import numpy as np
    if not len(T):
        return T
    return T[np.all((T.max(axis=1) >= lo) & (T.min(axis=1) <= hi), axis=1)]


def _surface_points(T):
    """Vertices and centroids of triangles T (n,3)."""
    import numpy as np
    if not len(T):
        return np.zeros((0, 3))
    P = np.vstack([T.reshape(-1, 3), T.mean(axis=1)])
    P = np.unique(np.round(P, 4), axis=0)
    if len(P) > NEAR_SAMPLES:
        P = P[::-(-len(P) // NEAR_SAMPLES)]
    return P


def near_mm(a, b, reach, Ta=None, Tb=None):
    """R441: the gap between two bodies' surfaces, MEASURED on their
    tessellations (within each other's box + reach; vertices and triangle
    centroids of each against the other's triangles), or inf when it is
    more than `reach`. a / b: Part shapes (or None with Ta / Tb given)."""
    import numpy as np
    Ta = _tris(a) if Ta is None else Ta
    Tb = _tris(b) if Tb is None else Tb
    if not len(Ta) or not len(Tb):
        return float("inf")
    la, ha = Ta.reshape(-1, 3).min(axis=0), Ta.reshape(-1, 3).max(axis=0)
    lb, hb = Tb.reshape(-1, 3).min(axis=0), Tb.reshape(-1, 3).max(axis=0)
    if np.any(la > hb + reach) or np.any(lb > ha + reach):
        return float("inf")
    best = float("inf")
    sides = []
    for S, O, lo, hi in ((Ta, Tb, lb, hb), (Tb, Ta, la, ha)):
        P = _surface_points(_in_box(S, lo - reach, hi + reach))
        Oc = _in_box(O, P.min(axis=0) - reach, P.max(axis=0) + reach) if len(P) else O[:0]
        if len(P) and len(Oc):
            sides.append((P, Oc))
    # a coarse pass first: most pairs that meet show it on a few points
    for stride in (16, 1):
        for P, Oc in sides:
            d = _pt_tri_dist(P[::stride], Oc, limit=reach)
            if len(d) and np.isfinite(d).any():
                best = min(best, float(d[np.isfinite(d)].min()))
        if best <= reach and stride > 1:
            return best
    return best


def contact_points(Ta, Tb, reach):
    """R441: the surface points of each of two triangle sets within
    `reach` of the other (n,3) - where two parts meet."""
    import numpy as np
    out = []
    for S, O in ((Ta, Tb), (Tb, Ta)):
        if not len(S) or not len(O):
            continue
        lo = O.reshape(-1, 3).min(axis=0) - reach
        hi = O.reshape(-1, 3).max(axis=0) + reach
        P = _surface_points(_in_box(S, lo, hi))
        if not len(P):
            continue
        Oc = _in_box(O, P.min(axis=0) - reach, P.max(axis=0) + reach)
        d = _pt_tri_dist(P, Oc, limit=reach)
        out.append(P[np.isfinite(d)])
    return np.vstack(out) if out else np.zeros((0, 3))


def _cyl_convex(f, s):
    """True when cylinder face f bulges out (a pin), False for a bore."""
    import numpy as np
    try:
        u0, u1, v0, v1 = f.ParameterRange
        u, v = 0.5 * (u0 + u1), 0.5 * (v0 + v1)
        p = np.array(tuple(f.valueAt(u, v)), dtype=float)
        n = np.array(tuple(f.normalAt(u, v)), dtype=float)
    except Exception:                                   # noqa: BLE001
        return None
    ax = np.array(tuple(s.Axis), dtype=float)
    ax /= np.linalg.norm(ax) or 1.0
    rel = p - np.array(tuple(s.Center), dtype=float)
    rad = rel - (rel @ ax) * ax
    return bool(n @ rad > 0)


PIN_CLEAR_MM = 0.3          # a pin this much under its hole still locates
PIN_ENGAGE_MM = 1.0         # ...and runs this far along it
PIN_ARC_DEG = 330.0         # a round pin / bore, not a lip's rounded corner
PIN_R_MAX = 4.0             # a pin is a dowel (<= 8 mm); a round lip is no pin


def pinned(a, b):
    """R441: True when a pin of one part (a round convex cylinder, r 0.5 -
    PIN_R_MAX mm)
    stands in a bore of the other on its axis (the bore at most
    PIN_CLEAR_MM bigger, PIN_ENGAGE_MM of length shared) - a dowel, a
    hinge pin or a peg moulded on, through the other's hole."""
    import math
    import numpy as np

    def cyls(shape, convex):
        """Round pins / bores: coaxial faces of one radius whose arcs sum
        to PIN_ARC_DEG or more (a lip's rounded corner is a quarter arc)."""
        rows = []
        for f, s in _cyl_faces(shape):
            if not 0.5 <= s.Radius <= PIN_R_MAX or _cyl_convex(f, s) is not convex:
                continue
            ax = np.array(tuple(s.Axis), dtype=float)
            ax /= np.linalg.norm(ax) or 1.0
            c = np.array(tuple(s.Center), dtype=float)
            vt = np.array([tuple(v.Point) for v in f.Vertexes] or [tuple(s.Center)], dtype=float)
            t = (vt - c) @ ax
            try:
                u0, u1 = f.ParameterRange[:2]
                arc = math.degrees(abs(u1 - u0))
            except Exception:                           # noqa: BLE001
                arc = 0.0
            for g in rows:
                rel = c - g[2]
                if abs(g[0] - s.Radius) < 1e-3 and abs(float(ax @ g[1])) > 0.9999 and \
                        np.linalg.norm(rel - (rel @ g[1]) * g[1]) < 1e-3:
                    k = float(rel @ g[1])
                    g[3] = min(g[3], t.min() + k)
                    g[4] = max(g[4], t.max() + k)
                    g[5] += arc
                    break
            else:
                rows.append([s.Radius, ax, c, t.min(), t.max(), arc])
        return [tuple(g[:5]) for g in rows if g[5] >= PIN_ARC_DEG]
    for x, y in ((a, b), (b, a)):
        pins, holes = cyls(x, True), cyls(y, False)
        for r, ax, c, t0, t1 in pins:
            for r2, ax2, c2, u0, u1 in holes:
                if abs(float(ax @ ax2)) < 0.999 or not (r - 0.05 <= r2 <= r + PIN_CLEAR_MM):
                    continue
                rel = c2 - c
                if np.linalg.norm(rel - (rel @ ax) * ax) > 0.15:
                    continue
                k = float(rel @ ax)
                s0, s1 = sorted((u0 * float(ax @ ax2) + k, u1 * float(ax @ ax2) + k))
                if min(t1, s1) - max(t0, s0) >= PIN_ENGAGE_MM:
                    return True
    return False


def _is_fastener(label):
    import re
    return bool(re.search(SCREW_RE, str(label or ""), re.I)) or any(
        t in FASTENER_WORDS for t in _tokens(label))


TRIM_WORDS = ("foot", "feet", "gasket", "seal", "trim", "badge", "bezel", "lens",
              "lenses", "glass", "window", "windows", "windscreen", "windshield",
              "mask", "visor", "cap", "caps", "button", "buttons", "key", "keys",
              "knob", "grille", "ring", "gallery", "finial", "pipe", "led", "light",
              "lights", "logo", "label", "tyre", "rim", "insert", "liner", "pad",
              "pads", "bumper", "plunger", "antenna", "ear", "ears", "arm", "arms")
INSERT_INSIDE = 0.9         # an insert: this share of its box inside another's
INSERT_VOLUME = 0.25        # ...and under this share of that part's volume


def _box_inside_share(a, b):
    """Share of box a's volume inside box b."""
    x = max(0.0, min(a.XMax, b.XMax) - max(a.XMin, b.XMin))
    y = max(0.0, min(a.YMax, b.YMax) - max(a.YMin, b.YMin))
    z = max(0.0, min(a.ZMax, b.ZMax) - max(a.ZMin, b.ZMin))
    va = a.XLength * a.YLength * a.ZLength
    return (x * y * z) / va if va > 0 else 0.0


def housing_parts(parts):
    """R441: (housing, big, boxes) of a build. BIG: not a cable, a
    fastener or a wheel, box diagonal >= HOUSING_DIAG of the product's.
    HOUSING - the shells, halves, chassis and lids that make up its body:
    a big part that is not see-through (a lens / glass is an insert), not
    a trim piece by label (bezel, cap, foot, gasket ...) and not an INSERT
    (its box INSERT_INSIDE inside another big part's, and under
    INSERT_VOLUME of its volume)."""
    body = [p for p in parts if p.get("shape") is not None and not p.get("cable")]
    boxes, vols = {}, {}
    for p in body:
        try:
            boxes[p["label"]] = tight(p["shape"])
            vols[p["label"]] = float(p["shape"].Volume)
        except Exception:                               # noqa: BLE001
            pass
    if not boxes:
        return [], [], boxes
    allb = None
    for bb in boxes.values():
        allb = bb if allb is None else allb.united(bb)
    diag = allb.DiagonalLength or 1.0
    big = [p for p in body if p["label"] in boxes and not _is_fastener(p["label"])
           and not any(t in WHEEL_WORDS for t in _tokens(p["label"]))
           and boxes[p["label"]].DiagonalLength >= HOUSING_DIAG * diag]
    out = []
    for p in big:
        la = p["label"]
        if any(t in TRIM_WORDS for t in _tokens(la)) or part_transparency(p) >= SEE_THROUGH_MIN:
            continue
        insert = any(q["label"] != la and _box_inside_share(boxes[la], boxes[q["label"]])
                     >= INSERT_INSIDE and vols[la] < INSERT_VOLUME * vols[q["label"]]
                     for q in big)
        if not insert:
            out.append(p)
    return out, big, boxes


def _bored_on_axis(shape, point, d, tol=0.3):
    """R505: True when `shape` has a round bore (a concave cylinder face) on
    the line (point, d) - a hinge knuckle's pin bore on the declared axis."""
    import numpy as np
    p0 = np.asarray(point, float)
    u = np.asarray(d, float)
    u = u / (np.linalg.norm(u) or 1.0)
    for f, s in _cyl_faces(shape):
        if s.Radius > PIN_R_MAX or _cyl_convex(f, s) is not False:
            continue
        ax = np.array(tuple(s.Axis), dtype=float)
        ax /= np.linalg.norm(ax) or 1.0
        if abs(float(ax @ u)) < 0.999:
            continue
        rel = np.array(tuple(s.Center), dtype=float) - p0
        if np.linalg.norm(rel - (rel @ u) * u) <= tol:
            return True
    return False


def fastening(parts, code="", cap=40, motions=()):
    """R441: housing parts that meet and that nothing joins.

    parts: the agent's bodies [{"label", "shape", "cable", "view"}]
    (housing_parts picks the housing and the big parts). A pair of big
    parts that meets (MEET_MM) is JOINED when a fastener part (a screw /
    pin / clip ... label) comes within FASTENER_REACH_MM of both, or bores
    of both line up (a screw or pin path through both, as joint_probe), or
    model.py calls cad.snap_fit_pair (one call excuses one pair), or a pin
    of one stands in a bore of the other (pinned). Bores in line with no
    screw in them join nothing. Joined parts form groups; a connected set
    of other parts that meets a group on OPPOSITE sides is clamped in its
    stack (a shell between a base and a top screwed together). R505: a part
    intent.json "motion" declares (read_motion rows in `motions`) is joined
    to a part it meets when BOTH carry a bore on its axis - the hinge's
    knuckles (cad.pin_hinge: the pin is bought, not modelled). Every pair
    of HOUSING parts that meets across two groups is loose. Returns {"housing", "joined": [[a, b, how]],
    "loose": [{"part", "meets"}]}."""
    housing, big, boxes = housing_parts(parts)
    big = big[:cap]
    hl = {p["label"] for p in housing}
    out = {"housing": [p["label"] for p in housing], "joined": [], "loose": []}
    if len(housing) < 2:
        return out
    body = [p for p in parts if p.get("shape") is not None and not p.get("cable")]
    fasteners = [p for p in body if p["label"] in boxes and _is_fastener(p["label"])]
    T = {p["label"]: _tris(p["shape"]) for p in big + fasteners}
    dfl = {p["label"]: _deflection(p["shape"]) for p in big + fasteners}

    def close(a, b, reach):
        if _bb_gap(boxes[a], boxes[b]) > reach:
            return False
        r = reach + dfl[a] + dfl[b]
        return near_mm(None, None, r, T[a], T[b]) <= r
    meets = [(a["label"], b["label"]) for i, a in enumerate(big)
             for b in big[i + 1:] if close(a["label"], b["label"], MEET_MM)]
    reach = {}
    for f in fasteners:
        for h in big:
            if close(f["label"], h["label"], FASTENER_REACH_MM):
                reach.setdefault(f["label"], set()).add(h["label"])
    shape_of = {p["label"]: p["shape"] for p in big}
    snaps = sum((code or "").count(c) for c in SNAP_CALLS)
    group = {h: frozenset([h]) for h in shape_of}

    def merge(a, b):
        g = group[a] | group[b]
        for x in g:
            group[x] = g
    for (a, b) in meets:
        how = next(("%s through both" % f for f, hs in sorted(reach.items())
                    if a in hs and b in hs), None)
        if how is None:
            try:
                if pinned(shape_of[a], shape_of[b]):
                    how = "a pin of one in a bore of the other"
            except Exception:                           # noqa: BLE001
                pass
        if how is None:
            for m in motions or ():
                if m.get("part") not in (a, b):
                    continue
                try:
                    if _bored_on_axis(shape_of[a], m["point"], m["dir"]) and \
                            _bored_on_axis(shape_of[b], m["point"], m["dir"]):
                        how = "a hinge: both bored on %s's declared motion axis" % m["part"]
                        break
                except Exception:                       # noqa: BLE001
                    pass
        if how is None and snaps > 0 and a in hl and b in hl:
            snaps -= 1
            how = "cad.snap_fit_pair in model.py (taken as this pair's snaps)"
        if how:
            out["joined"].append([a, b, how])
            merge(a, b)
    # captured: the parts of one group G and a connected set C of others
    # that meets G on OPPOSITE sides (a shell between a base and a top
    # screwed together, a ring stacked on it) are clamped in one stack
    rch = MEET_MM + 2 * max(dfl.values() or [0.0])
    where = {}
    for (a, b) in meets:
        P = contact_points(T[a], T[b], rch)
        if len(P):
            where[(a, b)] = where[(b, a)] = P.mean(axis=0)
    grew = True
    while grew:
        grew = False
        for g in sorted({group[h] for h in shape_of}, key=lambda x: sorted(x)):
            rest = [h for h in shape_of if h not in g]
            comp = {h: frozenset([h]) for h in rest}
            for (a, b) in meets:
                if a in comp and b in comp and comp[a] != comp[b]:
                    m = comp[a] | comp[b]
                    for x in m:
                        comp[x] = m
            for c in {comp[h] for h in rest}:
                pts = [where[(a, b)] for (a, b) in meets if (a in c and b in g)
                       or (b in c and a in g) if (a, b) in where]
                if len(pts) < 2:
                    continue
                import numpy as np
                cb = None
                for h in c:
                    cb = boxes[h] if cb is None else cb.united(boxes[h])
                ctr = np.array([cb.Center.x, cb.Center.y, cb.Center.z])
                half = np.maximum(np.array([cb.XLength, cb.YLength, cb.ZLength]) / 2, 1e-6)
                q = (np.array(pts) - ctr) / half
                k = np.abs(q).argmax(axis=1)
                sides = {(int(kk), bool(q[i, kk] > 0)) for i, kk in enumerate(k)}
                if any((kk, not sg) in sides for kk, sg in sides):
                    merge(next(iter(g)), next(iter(c)))
                    grew = True
                    break
            if grew:
                break
    vol = {h: boxes[h].XLength * boxes[h].YLength * boxes[h].ZLength for h in shape_of}
    seen = set()
    for (a, b) in meets:
        if a not in hl or b not in hl or group[a] == group[b]:
            continue
        # name the smaller side's part: that is what lifts off
        small, other = (a, b) if vol[a] <= vol[b] else (b, a)
        key = frozenset([group[a], group[b]])
        if key in seen:
            continue
        seen.add(key)
        out["loose"].append({"part": small, "meets": [other]})
    return out


def fastening_text(row):
    other = row["meets"][0]
    return ("fastening: %s meets %s but nothing joins them - no screw through both, no "
            "snap or clip, no pin (a lip or a ledge only locates it: it lifts off). Add "
            "2-4 screws through %s into bosses on %s (cad.screw_boss + cad.screw: the "
            "boss drills the 0.85 x d thread-forming pilot), snap hooks "
            "(cad.snap_fit_pair(%s, %s)), or a pin through both" % (
                row["part"], " and ".join(row["meets"]), row["part"], other, other,
                row["part"]))


# R442 (round 1): cabled modules hung on their ribbons - a light behind a
# lens with nothing behind it, a sensor floating in the nose. A seated
# module is held by the board (board_retention); a CABLED one needs its
# own holder: material within HOLDER_MM on two sides or more, or a part
# named as a cradle / holder / clip round it.
HOLDER_MM = 0.5
HOLDER_WORDS = ("cradle", "cradles", "holder", "holders", "clip", "clips", "bracket",
                "brackets", "mount", "mounts", "pocket", "socket", "sleeve", "carrier")
SIDE_NAMES = ("-X", "+X", "-Y", "+Y", "-Z", "+Z")
HOLDER_STEP_MM = 1.0        # contact points every 1 mm over a part's faces
HOLDER_EDGE = 0.2           # a point this near a box edge faces no one side


def _dense_points(T, step, cap=40000):
    """Points over triangles T every `step` mm (barycentric grid per
    triangle, its corners included) - deterministic."""
    import numpy as np
    if not len(T):
        return np.zeros((0, 3))
    e = np.max(np.linalg.norm(T - np.roll(T, 1, axis=1), axis=2), axis=1)
    out = [T.reshape(-1, 3)]
    for n in np.unique(np.clip(np.ceil(e / step).astype(int), 1, 40)):
        if n < 2:
            continue
        sel = T[np.ceil(e / step).clip(1, 40).astype(int) == n]
        ij = [(i, j) for i in range(n + 1) for j in range(n + 1 - i)]
        W = np.array([(i / n, j / n, 1 - (i + j) / n) for i, j in ij])
        out.append((W[None, :, :, None] * sel[:, None, :, :]).sum(axis=2).reshape(-1, 3))
    P = np.vstack(out)
    return P[::-(-len(P) // cap)] if len(P) > cap else P


def cable_holders(parts, mods, cabled):
    """R442: per cabled module, the sides of it some part comes within
    HOLDER_MM of. parts: the agent's bodies [{"label", "shape", "cable"}];
    mods: the module meshes [{"label", "name", "mesh", "axes"}]; cabled:
    the module Names a ribbon cable serves. Sides are the module's own
    (its axes: local -X ... +Z). Returns [{"module", "sides": {side:
    [labels]}, "cradle": label or None, "held": bool}]."""
    import numpy as np
    rows = []
    body = [p for p in parts if p.get("shape") is not None and not p.get("cable")]
    for m in mods:
        if m.get("name") not in cabled or m.get("mesh") is None:
            continue
        MT = _mesh_tris(m["mesh"])
        if not len(MT):
            continue
        MP = np.unique(np.round(MT.reshape(-1, 3), 4), axis=0)
        A = np.asarray(m.get("axes") or np.eye(3), float).reshape(3, 3)
        c = 0.5 * (MP.min(axis=0) + MP.max(axis=0))
        loc = (MP - c) @ A.T
        half = np.maximum(np.abs(loc).max(axis=0), 1e-6)
        c = c + A.T @ (0.5 * (loc.max(axis=0) + loc.min(axis=0)))
        half = np.maximum(0.5 * (loc.max(axis=0) - loc.min(axis=0)), 1e-6)
        lo, hi = MP.min(axis=0) - HOLDER_MM, MP.max(axis=0) + HOLDER_MM
        sides, cradle = {}, None
        for p in body:
            T = _in_box(_tris(p["shape"]), lo - 1.0, hi + 1.0)
            if not len(T):
                continue
            tol = _deflection(p["shape"])
            near = []
            dm = _pt_tri_dist(MP, T, limit=HOLDER_MM + tol)
            near.append(MP[np.isfinite(dm)])
            PP = _dense_points(T, HOLDER_STEP_MM)
            PP = PP[np.all((PP >= lo) & (PP <= hi), axis=1)]
            if len(PP):
                dp = _pt_tri_dist(PP, _in_box(MT, lo - 1.0, hi + 1.0), limit=HOLDER_MM + tol)
                near.append(PP[np.isfinite(dp)])
            Q = np.vstack(near)
            if not len(Q):
                continue
            if any(t in HOLDER_WORDS for t in _tokens(p["label"])):
                cradle = cradle or p["label"]
            # the side of the module's box a contact point faces; a point
            # near an edge or a corner (two sides nearly as far out) is
            # nobody's - a lens in front reaches round the front's edges
            q = ((Q - c) @ A.T) / half
            aq = np.abs(q)
            order = np.sort(aq, axis=1)
            sure = order[:, -1] - order[:, -2] > HOLDER_EDGE
            k = aq.argmax(axis=1)
            for kk, sg in set(zip(k[sure].tolist(), (q[np.arange(len(q)), k] > 0)[sure].tolist())):
                sides.setdefault(SIDE_NAMES[2 * kk + int(sg)], []).append(p["label"])
        rows.append({"module": m["label"], "sides": {s: sorted(set(v)) for s, v in sides.items()},
                     "cradle": cradle, "held": bool(cradle) or len(sides) >= 2})
    return rows


def holder_text(row):
    got = ", ".join("%s %s" % (s, "/".join(v)) for s, v in sorted(row["sides"].items()))
    return ("holder: %s is cabled and held on %d side%s only (%s) - nothing else comes "
            "within %g mm of it, so it hangs on its ribbon and rattles. Give it a holder: "
            "ribs or a pocket 0.1-0.3 mm off on two opposite sides (one behind it, "
            "against the lens or wall in front), or a cradle / clip part round it" % (
                row["module"], len(row["sides"]), "" if len(row["sides"]) == 1 else "s",
                got or "nothing at all", HOLDER_MM))


# ============================== R444 thread engagement (WS4)
# R444: cad.screw_boss drills the thread-forming pilot (0.85 x d), so a
# cad.screw (shank d - 0.1) in it shares the thread's annulus with the
# boss - that is the thread biting, not an overlap. An OVERLAP between a
# screw and the part its pilot bites in, no bigger than the annulus over
# the screw's length (x 1.2), is excused; anything bigger (the head in the
# wall, the screw through a rib) is still reported.
THREAD_SLACK = 1.2


def _coaxial_pilot(screw, part):
    """(nominal d, narrowest pilot diameter) - the narrowest concave
    cylinder of `part` on the screw's axis that is under d (the
    thread-forming pilot it bites in, anywhere along the screw), or None."""
    import numpy as np
    got = _screw_axis(screw)
    if got is None:
        return None
    nominal, ax, c, _tip, _back = got
    best = None
    for f, s in _cyl_faces(part):
        a2 = np.array(tuple(s.Axis), dtype=float)
        a2 /= np.linalg.norm(a2) or 1.0
        if abs(float(a2 @ ax)) < 0.999:
            continue
        rel = np.array(tuple(s.Center), dtype=float) - c
        if np.linalg.norm(rel - (rel @ ax) * ax) > 0.15:
            continue
        dd = 2.0 * s.Radius
        if dd < 0.6 * nominal or dd >= nominal - 0.02:
            continue
        if best is None or dd < best:
            best = dd
    return None if best is None else (nominal, round(best, 3))


def thread_engagement(hits, parts):
    """R444: (hits kept, hits excused) - excused: a screw's overlap with a
    part that has a pilot under d on the screw's axis (the thread-forming
    pilot, wherever along the screw - below a heat-set insert pocket too),
    no bigger than the thread annulus pi/4 (d^2 - pilot^2) x the screw's
    length (x THREAD_SLACK)."""
    import math
    import re
    if not hits:
        return hits, []
    shape_of = {p["label"]: p["shape"] for p in parts if p.get("shape") is not None}
    kept, excused = [], []
    for h in hits:
        v = h.get("volume_mm3")
        sa = re.search(SCREW_RE, str(h["a"]), re.I)
        sb = re.search(SCREW_RE, str(h["b"]), re.I)
        if v is None or bool(sa) == bool(sb):
            kept.append(h)
            continue
        scr, oth = (h["a"], h["b"]) if sa else (h["b"], h["a"])
        try:
            got = _coaxial_pilot(shape_of[scr], shape_of[oth])
            bb = tight(shape_of[scr])
        except Exception:                               # noqa: BLE001
            got = None
        if got is None:
            kept.append(h)
            continue
        d, pd = got
        L = max(bb.XLength, bb.YLength, bb.ZLength)
        cap = math.pi / 4.0 * max(0.0, d * d - pd * pd) * L * THREAD_SLACK
        if v <= cap:
            excused.append(dict(h, thread_cap_mm3=round(cap, 2), pilot_mm=pd))
        else:
            kept.append(h)
    return kept, excused
