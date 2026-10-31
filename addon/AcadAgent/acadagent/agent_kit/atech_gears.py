"""atech_gears - do the gears of a design really mesh? (R740)

./check runs gear_probe on every build. It finds the gears by their
teeth, whatever made them (cad.spur_gear, an imported STEP, a gear fused
into a wheel), and judges each one the way a workshop would:

  * a PAIR of gears (parallel axes, tip circles reaching into each other)
    must share a module, stand at the centre distance their teeth need
    (centre_distance: m*(z1 + z2)/2, more with profile shift; within
    -0.02*m to +0.15*m: printing
    backlash), overlap over at least half the narrower face, and TURN:
    one gear is stepped through a tooth pitch with the other following at
    z1/z2, and the teeth may not share volume at any step. Built out of
    phase but meshing at another phase is a PROBLEM that says how far to
    turn the gear.
  * a gear whose teeth reach into a part that is not a gear (a rack, a
    toothed belt, a chain) must clear it, and that part's teeth must sit
    at the gear's pitch (360/z apart round it).
  * a gear whose teeth face a SMOOTH surface just past its tips drives
    nothing (R740, the RC tank: an 18-tooth sprocket 0.3 mm inside a
    smooth track belt). A PROBLEM.
  * a gear next to other parts that meshes with nothing is a PROBLEM; a
    lone gear (the whole design, or touching nothing) is a NOTE.
  * a gear with a bore that nothing goes through (no shaft, axle or pin)
    is a PROBLEM: it would spin free or fall off.

Returns (rows, problems, notes); rows are one dict a gear and a pair.
Never raises for a part it cannot read: that part is just not a gear.
"""
import math
import time

GEAR_MIN_TEETH = 6
GEAR_MIN_FACES = 12          # curved faces along one axis before a part is looked at
CENTRE_LO, CENTRE_HI = -0.02, 0.15     # centre distance error, in modules
MIN_WIDTH_SHARE = 0.5        # engaged face width / the narrower gear's
SWEEP_STEPS = 8              # steps across one tooth pitch of the driver
PHASES = 12                  # phases of the follower tried when built out of phase
BIND_MM3 = 0.002             # shared tooth volume that counts as binding
SMOOTH_REACH_MM = 1.0        # a surface this close past the tips faces the teeth
BUDGET_S = 20.0


def _vec(v):
    from FreeCAD import Vector
    return Vector(*v) if not isinstance(v, Vector) else Vector(v)


def _ruled_axis(face):
    """The direction a curved face is ruled along (a cylinder, an extruded
    involute), or None. Sampled normals must all be square to it."""
    if face.Surface.__class__.__name__ == "Plane":
        return None
    try:
        u0, u1, v0, v1 = face.ParameterRange
        ns = [face.normalAt(u0 + (u1 - u0) * a, v0 + (v1 - v0) * b)
              for a, b in ((0.2, 0.3), (0.8, 0.7), (0.5, 0.5), (0.3, 0.8))]
    except Exception:                                   # noqa: BLE001
        return None
    d = None
    for i in range(len(ns)):
        for j in range(i + 1, len(ns)):
            c = ns[i].cross(ns[j])
            if c.Length > 0.05:
                d = c.normalize()
                break
        if d is not None:
            break
    if d is None:
        return None
    if any(abs(n.dot(d)) > 0.02 for n in ns):
        return None
    k = max(range(3), key=lambda i: abs(d[i]))
    return d if d[k] > 0 else d.negative()


def _cluster_axes(faces):
    """{axis: [faces]} for the curved faces ruled along each direction."""
    groups = []
    for f in faces:
        d = _ruled_axis(f)
        if d is None:
            continue
        for g in groups:
            if abs(g[0].dot(d)) > 0.9995:
                g[1].append(f)
                break
        else:
            groups.append((d, [f]))
    return groups


def _frame(d):
    """Two unit vectors square to d and to each other."""
    from FreeCAD import Vector
    a = Vector(1, 0, 0) if abs(d.x) < 0.9 else Vector(0, 1, 0)
    u = d.cross(a).normalize()
    return u, d.cross(u).normalize()


def _profile(shape, centre, d, h, r_lo, r_hi, bins=1440):
    """max radius about the axis in each angular bin of the section at
    height h along d, among the points from r_lo to r_hi (None when a bin
    has none)."""
    u, w = _frame(d)
    prof = [None] * bins
    step = min(0.04, 0.5 * 2 * math.pi * max(r_lo, 0.5) / bins)   # finer than a bin at r_lo
    try:
        wires = shape.slice(d, h)
    except Exception:                                   # noqa: BLE001
        return prof
    for wire in wires:
        for e in wire.Edges:
            try:
                pts = e.discretize(Distance=step)
            except Exception:                           # noqa: BLE001
                continue
            for p in pts:
                q = p - centre
                x, y = q.dot(u), q.dot(w)
                r = math.hypot(x, y)
                if r < r_lo or r > r_hi:
                    continue
                k = int((math.atan2(y, x) % (2 * math.pi)) / (2 * math.pi) * bins) % bins
                if prof[k] is None or r > prof[k]:
                    prof[k] = r
    return prof


def _teeth(prof):
    """(z, tip, root, first tooth angle deg) from a radius profile, or None."""
    vals = [r for r in prof if r is not None]
    if len(vals) < 0.9 * len(prof):
        return None
    n = len(prof)
    # fill the odd empty bin from the one before it
    last = vals[-1]
    filled = []
    for r in prof:
        last = r if r is not None else last
        filled.append(last)
    prof = filled
    tip, root = max(vals), min(vals)
    if tip - root < 0.3 or tip - root > 0.6 * tip:
        return None
    mid = (tip + root) / 2.0
    hi = [r > mid for r in prof]
    rises = [k for k in range(n) if hi[k] and not hi[k - 1]]
    z = len(rises)
    if z < GEAR_MIN_TEETH:
        return None
    gaps = [(rises[(i + 1) % z] - rises[i]) % n for i in range(z)]
    mean = n / float(z)
    if max(abs(g - mean) for g in gaps) > 0.12 * mean:
        return None                                     # not evenly spaced: not a gear
    widths = []
    for k in rises:
        j = 0
        while hi[(k + j) % n] and j < n:
            j += 1
        widths.append(j)
    if max(widths) - min(widths) > 0.25 * mean:
        return None
    first = (rises[0] + widths[0] / 2.0) * 360.0 / n    # centre of the first tooth
    return z, tip, root, first


def find_gears(parts):
    """The external spur gears in parts ([{"label", "shape"}]): one dict a
    gear with part, label, centre, axis, z, module, shift, tip, root, pitch
    radius, lo/hi (its face along the axis), tooth (deg of a tooth centre),
    bore (radius or None)."""
    gears = []
    for i, p in enumerate(parts):
        sh = p.get("shape")
        if sh is None or p.get("atech") or not getattr(sh, "Faces", None):
            continue
        if len(sh.Faces) > 4000:
            continue
        for d, faces in _cluster_axes(sh.Faces):
            if len(faces) < GEAR_MIN_FACES:
                continue
            g = _gear_on_axis(sh, d, faces)
            if g:
                g.update(part=i, label=p["label"])
                gears.append(g)
    return gears


def _gear_on_axis(sh, d, faces):
    from FreeCAD import Vector
    cs = [f.CenterOfMass for f in faces]
    c = Vector(0, 0, 0)
    for q in cs:
        c += q
    c = c * (1.0 / len(cs))
    hs = [v.Point.dot(d) for f in faces for v in f.Vertexes]
    lo, hi = min(hs), max(hs)
    if hi - lo < 0.3:
        return None
    c = c - d * (c.dot(d))                              # centre on the axis line
    u, w = _frame(d)
    rs = []
    for f in faces:
        for v in f.Vertexes:
            q = v.Point - c
            rs.append(math.hypot(q.dot(u), q.dot(w)))
    ring = sorted(rs)
    r_hi = ring[-1]
    if r_hi < 1.0:
        return None
    # cheap before the slice: a gear's faces sit on a ring round the axis,
    # all the way round (a shell's walls and holes do not)
    sectors, outer = set(), 0
    for q in cs:
        q = q - c
        x, y = q.dot(u), q.dot(w)
        r = math.hypot(x, y)
        if r > 0.5 * r_hi:
            outer += 1
            sectors.add(int((math.atan2(y, x) % (2 * math.pi)) / (2 * math.pi) * 12) % 12)
            if r > 1.05 * r_hi:
                return None
    if outer < GEAR_MIN_FACES or len(sectors) < 12:
        return None
    # the tooth zone: the outer half of the vertex radii
    r_lo = 0.55 * r_hi
    got = None
    for frac in (0.5, 0.3, 0.7):
        got = _teeth(_profile(sh, c, d, lo + (hi - lo) * frac, r_lo, r_hi * 1.02))
        if got:
            break
    if not got:
        return None
    z, tip, root, first = got
    m = (tip - root) / 2.25
    x = (2.0 * tip / m - z - 2.0) / 2.0
    if abs(x) > 1.2:
        return None                                     # tyre tread or knurl, not involute teeth
    # snap to the nominal module when the tip says the same within 2 %
    m0 = 2.0 * tip / (z + 2.0)
    if abs(m0 - m) < 0.02 * m0:
        m, x = m0, 0.0
    lo_t, hi_t = _tooth_span(faces, d, tip, root, c, u, w)
    bore = None
    for f in sh.Faces:
        s = f.Surface
        if s.__class__.__name__ != "Cylinder":
            continue
        if abs(abs(s.Axis.dot(d)) - 1) > 1e-4:
            continue
        q = s.Center - c
        off = (q - d * q.dot(d)).Length
        if off > 0.05 or s.Radius > root * 0.95:
            continue
        # a hole: the normal points at the axis
        try:
            pt = f.valueAt(*f.ParameterRange[::2])
            n = f.normalAt(*f.ParameterRange[::2])
        except Exception:                               # noqa: BLE001
            continue
        rv = pt - c
        rv = rv - d * rv.dot(d)
        if rv.Length > 1e-6 and n.dot(rv) < 0:
            bore = max(bore or 0.0, s.Radius)
    return {"centre": c, "axis": d, "z": z, "module": round(m, 4), "shift": round(x, 3),
            "tip": tip, "root": root, "pitch_r": m * z / 2.0, "lo": lo_t, "hi": hi_t,
            "tooth": first, "bore": bore}


def _tooth_span(faces, d, tip, root, c, u, w):
    """The axial extent of the faces out in the tooth zone."""
    hs = []
    for f in faces:
        q = f.CenterOfMass - c
        if math.hypot(q.dot(u), q.dot(w)) > root + 0.3 * (tip - root):
            hs.extend(v.Point.dot(d) for v in f.Vertexes)
    if not hs:
        hs = [v.Point.dot(d) for f in faces for v in f.Vertexes]
    return min(hs), max(hs)


def _disc(g, r_out, r_in=0.0, lo=None, hi=None):
    """The solid between radii r_in..r_out about g's axis over lo..hi."""
    import Part
    lo = g["lo"] if lo is None else lo
    hi = g["hi"] if hi is None else hi
    base = g["centre"] + g["axis"] * lo
    s = Part.makeCylinder(r_out, hi - lo, base, g["axis"])
    if r_in > 0:
        s = s.cut(Part.makeCylinder(r_in, hi - lo, base, g["axis"]))
    return s


def _vol(a, b):
    try:
        return a.common(b).Volume
    except Exception:                                   # noqa: BLE001
        return 0.0


def _turned(shape, g, deg):
    s = shape.copy()
    if deg:
        s.rotate(g["centre"], g["axis"], deg)
    return s


def _sweep(sa, ga, sb, gb, phase_b=0.0):
    """Turn a through one tooth pitch, b following; the first angle of a
    (deg) at which the teeth share volume, or None when they never do."""
    step = 360.0 / ga["z"] / SWEEP_STEPS
    ratio = ga["z"] / float(gb["z"])
    same = ga["axis"].dot(gb["axis"]) > 0
    for k in range(SWEEP_STEPS + 1):
        a_deg = k * step
        b_deg = phase_b + (-a_deg * ratio if same else a_deg * ratio)
        if _vol(_turned(sa, ga, a_deg), _turned(sb, gb, b_deg)) > BIND_MM3:
            return a_deg
    return None


def _inv(a):
    return math.tan(a) - a


def centre_distance(m, z1, z2, x_sum=0.0, pressure_angle=20.0):
    """The centre distance two external spur gears run at without
    backlash: m*(z1 + z2)/2 for unshifted gears; with profile shift the
    working pressure angle from inv(aw) = 2*tan(a)*(x1 + x2)/(z1 + z2) + inv(a)."""
    a = math.radians(pressure_angle)
    a0 = m * (z1 + z2) / 2.0
    if abs(x_sum) < 1e-6:
        return a0
    target = 2.0 * math.tan(a) * x_sum / (z1 + z2) + _inv(a)
    lo, hi = 1e-4, 1.5
    for _ in range(80):                                 # inv() rises: bisect
        mid = (lo + hi) / 2.0
        if _inv(mid) < target:
            lo = mid
        else:
            hi = mid
    return a0 * math.cos(a) / math.cos((lo + hi) / 2.0)


def _pair(parts, ga, gb, clipped, budget):
    """One meshing pair: (row, problems)."""
    m = (ga["module"] + gb["module"]) / 2.0
    la, lb = ga["label"], gb["label"]
    row = {"gears": [la, lb], "teeth": [ga["z"], gb["z"]], "module": [ga["module"], gb["module"]],
           "ratio": round(gb["z"] / float(ga["z"]), 3)}
    bad = []
    if abs(ga["module"] - gb["module"]) > 0.03 * m:
        bad.append("gear: %s (module %.2f) and %s (module %.2f) cannot mesh - meshing gears need "
                   "the same module; make both %.2f" % (la, ga["module"], lb, gb["module"],
                                                       max(ga["module"], gb["module"])))
    q = gb["centre"] - ga["centre"]
    a = (q - ga["axis"] * q.dot(ga["axis"])).Length
    a0 = centre_distance(m, ga["z"], gb["z"], ga["shift"] + gb["shift"])
    e = a - a0
    row.update(centre_mm=round(a, 3), centre_needed_mm=round(a0, 3), error_mm=round(e, 3))
    if bad:
        pass                                            # another module: the distance says nothing
    elif e < CENTRE_LO * m:
        bad.append("gear: %s and %s stand %.2f mm apart, %.2f mm too close for %d and %d "
                   "teeth of module %.2f (they need %.2f mm, up to +%.2f for backlash): "
                   "the teeth bind - move them apart" % (la, lb, a, -e, ga["z"], gb["z"], m,
                                                         a0, CENTRE_HI * m))
    elif e > CENTRE_HI * m:
        bad.append("gear: %s and %s stand %.2f mm apart, %.2f mm too far for %d and %d "
                   "teeth of module %.2f (they need %.2f mm, up to +%.2f for backlash): "
                   "the teeth barely engage and skip under load - move them together"
                   % (la, lb, a, e, ga["z"], gb["z"], m, a0, CENTRE_HI * m))
    ha = (ga["lo"], ga["hi"])
    off = gb["centre"].dot(ga["axis"]) - ga["centre"].dot(ga["axis"])
    hb = sorted(((gb["lo"] - gb["centre"].dot(gb["axis"])) * (1 if ga["axis"].dot(gb["axis"]) > 0 else -1),
                 (gb["hi"] - gb["centre"].dot(gb["axis"])) * (1 if ga["axis"].dot(gb["axis"]) > 0 else -1)))
    hb = (hb[0] + ga["centre"].dot(ga["axis"]) + off, hb[1] + ga["centre"].dot(ga["axis"]) + off)
    share = min(ha[1], hb[1]) - max(ha[0], hb[0])
    narrow = min(ha[1] - ha[0], hb[1] - hb[0])
    row["engaged_width_mm"] = round(share, 2)
    if share < MIN_WIDTH_SHARE * narrow:
        bad.append("gear: %s and %s overlap over only %.2f mm of their %.2f mm teeth "
                   "along the axis - line their faces up" % (la, lb, max(0.0, share), narrow))
    if bad or time.time() > budget:
        row["turns"] = None
        return row, bad
    sa, sb = clipped(ga), clipped(gb)
    hit = _sweep(sa, ga, sb, gb)
    if hit is None:
        row["turns"] = True
        return row, bad
    pitch_b = 360.0 / gb["z"]
    for k in range(1, PHASES):
        if time.time() > budget:
            break
        ph = k * pitch_b / PHASES
        if _sweep(sa, ga, sb, gb, ph) is None:
            row["turns"] = False
            row["turn_by_deg"] = round(ph, 2)
            bad.append("gear: the teeth of %s and %s overlap as built (they bind at %.1f deg); "
                       "they mesh when %s is turned %.2f deg about its axis - rotate it by that "
                       "before placing it" % (la, lb, hit, lb, ph))
            return row, bad
    row["turns"] = False
    bad.append("gear: %s and %s bind at every phase (first at %.1f deg of %s): the teeth "
               "cannot turn through each other - check module, tooth count and centre "
               "distance" % (la, lb, hit, la))
    return row, bad


def gear_probe(parts, budget_s=BUDGET_S):
    """See the module docstring. parts: [{"label", "shape", "atech"?}];
    Atech modules (atech=True) are shafts and neighbours, never gears."""
    t0 = time.time()
    budget = t0 + budget_s
    gears = find_gears(parts)
    rows, bad, notes = [], [], []
    if not gears:
        return rows, bad, notes
    cache = {}

    def clipped(g):
        k = id(g)
        if k not in cache:
            cache[k] = parts[g["part"]]["shape"].common(_disc(g, g["tip"] + 0.05))
        return cache[k]

    meshed = set()
    paired = {}                                         # gear -> parts it is judged against as a pair
    for i, ga in enumerate(gears):
        rows.append({"gear": ga["label"], "teeth": ga["z"], "module": ga["module"],
                     "shift": ga["shift"], "tip_d_mm": round(2 * ga["tip"], 2),
                     "bore_d_mm": round(2 * ga["bore"], 2) if ga["bore"] else None})
        for j in range(i + 1, len(gears)):
            gb = gears[j]
            if ga["part"] == gb["part"] or abs(ga["axis"].dot(gb["axis"])) < 0.999:
                continue
            q = gb["centre"] - ga["centre"]
            a = (q - ga["axis"] * q.dot(ga["axis"])).Length
            if a > ga["tip"] + gb["tip"] + 0.5 * max(ga["module"], gb["module"]):
                continue
            if a < 0.5 * min(ga["tip"], gb["tip"]):
                continue                                # coaxial: a compound gear or the far side
            d = ga["axis"]
            sb = sorted((gb["lo"] * d.dot(gb["axis"]), gb["hi"] * d.dot(gb["axis"])))
            if min(ga["hi"], sb[1]) <= max(ga["lo"], sb[0]):
                continue                                # side by side along the axis
            paired.setdefault(i, set()).add(gb["part"])
            paired.setdefault(j, set()).add(ga["part"])
            row, b = _pair(parts, ga, gb, clipped, budget)
            rows.append(row)
            bad.extend(b)
            meshed.update((i, j))
    for i, g in enumerate(gears):
        b, n, engaged = _neighbours(parts, g, clipped, paired.get(i, ()))
        bad.extend(b)
        notes.extend(n)
        if engaged:
            meshed.add(i)
        near = _near_others(parts, g)
        if i not in meshed and not b:
            if near:
                bad.append("gear: %s (%d teeth) meshes with nothing - no gear, rack or toothed "
                           "belt reaches into its teeth, so it drives nothing; %s next to it"
                           % (g["label"], g["z"], ", ".join(near)))
            else:
                notes.append("gear: %s (%d teeth, module %.2f) stands alone" % (
                    g["label"], g["z"], g["module"]))
        if g["bore"] and (near or i in meshed or b):
            if not _bore_filled(parts, g):
                bad.append("gear: nothing goes through the %.2f mm bore of %s - no shaft, axle or "
                           "pin carries it, so it spins free or falls off" % (2 * g["bore"], g["label"]))
    notes.append("gears: %d found, %.1f s" % (len(gears), time.time() - t0))
    return rows, bad, notes


def _neighbours(parts, g, clipped, skip=()):
    """A gear against every part that is not a gear: (problems, notes,
    engaged). Teeth into a part = a rack/belt (pitch checked); a smooth
    surface just past the tips = drives nothing."""
    bad, notes, engaged = [], [], False
    zone = _disc(g, g["tip"], g["root"] + 0.25 * (g["tip"] - g["root"]),
                 g["lo"] + 0.1, g["hi"] - 0.1)
    ring = _disc(g, g["tip"] + SMOOTH_REACH_MM, g["tip"], g["lo"] + 0.1, g["hi"] - 0.1)
    gb = zone.BoundBox
    gb.enlarge(SMOOTH_REACH_MM + 0.1)
    for k, p in enumerate(parts):
        if k == g["part"] or k in skip or p.get("shape") is None:
            continue
        sh = p["shape"]
        if not sh.BoundBox.intersect(gb):
            continue
        inside = sh.common(zone)
        if inside.Volume > BIND_MM3:
            if p.get("atech"):
                continue
            if _vol(sh, clipped(g)) > BIND_MM3:
                bad.append("gear: %s cuts into the teeth of %s - its teeth must sit in the gear's "
                           "tooth spaces with clearance" % (p["label"], g["label"]))
                engaged = True
                continue
            engaged = True
            pb = _pitch_of(inside, g)
            if pb:
                bad.append("gear: the teeth of %s sit %.1f deg apart round %s, whose teeth are "
                           "%.1f deg apart (module %.2f, pitch %.2f mm) - space them at the "
                           "gear's pitch" % (p["label"], pb, g["label"], 360.0 / g["z"],
                                              g["module"], math.pi * g["module"]))
            else:
                notes.append("gear: %s engages the teeth of %s" % (p["label"], g["label"]))
            continue
        if p.get("atech"):
            continue
        facing = _vol(sh, ring)
        if facing > 0.05:
            gap = _radial_gap(sh, g)
            bad.append("gear: the teeth of %s face a smooth surface of %s%s - nothing reaches "
                       "into the tooth spaces, so the gear cannot drive it. Give %s teeth at "
                       "the gear's pitch (%.2f mm, module %.2f, %d teeth) or drive it another way"
                       % (g["label"], p["label"], (" %.2f mm past the tips" % gap) if gap else "",
                          p["label"], math.pi * g["module"], g["module"], g["z"]))
    return bad, notes, engaged


def _radial_gap(sh, g):
    try:
        return sh.distToShape(_disc(g, g["tip"], 0, g["lo"] + 0.1, g["hi"] - 0.1))[0]
    except Exception:                                   # noqa: BLE001
        return None


def _pitch_of(inside, g):
    """The spacing (deg) of another part's teeth round g when it is not a
    whole number of g's tooth pitches, else None."""
    u, w = _frame(g["axis"])
    angs = []
    solids = [s for s in inside.Solids if s.Volume > BIND_MM3]
    big = max([s.Volume for s in solids] or [0.0])
    for s in solids:
        if s.Volume < 0.9 * big:
            continue                                    # a part-tooth where the belt leaves the gear
        q = s.CenterOfMass - g["centre"]
        angs.append(math.degrees(math.atan2(q.dot(w), q.dot(u))) % 360.0)
    if len(angs) < 2:
        return None
    angs.sort()
    pitch = 360.0 / g["z"]
    diffs = [b - a for a, b in zip(angs, angs[1:])]
    for dd in diffs:
        n = dd / pitch
        if round(n) < 1 or abs(n - round(n)) > 0.15:
            return sum(diffs) / len(diffs)
    return None


def _near_others(parts, g):
    out = []
    big = _disc(g, g["tip"] + SMOOTH_REACH_MM, g["root"], g["lo"] - 0.5, g["hi"] + 0.5)
    bb = big.BoundBox
    for k, p in enumerate(parts):
        if k == g["part"] or p.get("shape") is None or p.get("atech"):
            continue
        if p["shape"].BoundBox.intersect(bb) and _vol(p["shape"], big) > 0.01:
            out.append(p["label"])
    return out[:3]


def _mesh_in_bore(mesh, g):
    """Does a mesh (an Atech module: a motor's shaft) stand in g's bore?
    Rays out from the axis at three heights hit it inside the bore."""
    u, w = _frame(g["axis"])
    for f in (0.2, 0.5, 0.8):
        o = g["centre"] + g["axis"] * (g["lo"] + (g["hi"] - g["lo"]) * f)
        for d in (u, w, u.negative(), w.negative()):
            try:
                hits = mesh.foraminate(o, d)
            except Exception:                           # noqa: BLE001
                return False
            for pt in (hits or {}).values():
                q = _vec(tuple(pt)) - o
                if q.dot(d) > -1e-6 and q.Length < g["bore"] * 1.02:
                    return True
    return False


def _bore_filled(parts, g):
    core = _disc(g, max(0.2, g["bore"] * 0.6), 0, g["lo"], g["hi"])
    bb = core.BoundBox
    for k, p in enumerate(parts):
        if p.get("mesh") is not None and _mesh_in_bore(p["mesh"], g):
            return True
        sh = p.get("shape")
        if sh is None:
            continue
        if not sh.BoundBox.intersect(bb):
            continue
        if _vol(sh, core) > 0.01:
            return True
    return False


def probe_text(row):
    """The GEAR line for ./check."""
    if "gears" in row:
        a, b = row["gears"]
        return "%s x %s: %d:%d teeth, centre %.2f mm (needs %.2f), %s" % (
            a, b, row["teeth"][0], row["teeth"][1], row.get("centre_mm", 0),
            row.get("centre_needed_mm", 0),
            {True: "turns clear", False: "binds", None: "not turned"}[row.get("turns")])
    return "%s: %d teeth, module %.2f%s%s" % (
        row["gear"], row["teeth"], row["module"],
        (", shift %.2f" % row["shift"]) if row.get("shift") else "",
        (", bore %.2f mm" % row["bore_d_mm"]) if row.get("bore_d_mm") else "")
