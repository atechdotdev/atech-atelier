"""Unit tests for agent_kit/atech_cad.py - runs INSIDE freecadcmd.

    <freecadcmd> fc_atech_cad.py          (tests/test_agent_kit.py does this)

Every expected number is a CLOSED FORM worked out by hand here, never a value
read back from the helper under test. Prints PASS/FAIL per check and ends with
ATECH_CAD_TESTS=<failures>. ATECH_CAD_SABOTAGE=1 breaks one helper (hole()
drills a smaller diameter) to prove the suite can fail.
"""
import math
import os
import sys
import traceback

sys.dont_write_bytecode = True     # keep the shipped kit folder clean
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "acadagent", "agent_kit")))

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

import atech_cad as cad  # noqa: E402

FAIL = []
PI = math.pi

if os.environ.get("ATECH_CAD_SABOTAGE") == "1":
    _real_hole = cad.hole

    def _bad_hole(shape, at, axis, d, depth=None, through=False):
        return _real_hole(shape, at, axis, d * 0.9, depth, through)
    cad.hole = _bad_hole


def check(name, cond, detail=""):
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        FAIL.append(name)


def near(a, b, tol=1e-3):
    return abs(a - b) <= tol * max(1.0, abs(b))


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except cad.CadError as exc:
        return str(exc)
    return None


def case(fn):
    try:
        fn()
    except Exception:                                   # noqa: BLE001
        check(fn.__name__, False, traceback.format_exc())
    return fn


@case
def t_fuse_one():
    a = Part.makeBox(10, 10, 10)
    b = Part.makeBox(10, 10, 10, cad.V((5, 0, 0)))
    s = cad.fuse_one(a, b)
    check("fuse_one overlapping -> 1 solid, V=1500", len(s.Solids) == 1
          and near(s.Volume, 1500), s.Volume)
    far = Part.makeBox(10, 10, 10, cad.V((30, 0, 0)))
    msg = raises(cad.fuse_one, a, far)
    check("fuse_one apart -> raises naming 2 solids", msg and "2 separate" in msg, msg)
    touch = Part.makeBox(10, 10, 10, cad.V((10, 0, 0)))
    r = None
    try:
        r = cad.fuse_one(a, touch)
    except cad.CadError:
        r = "raised"
    # touching faces may legitimately merge or not; the helper must never
    # return a 2-solid shape
    check("fuse_one touching never returns 2 solids",
          r == "raised" or len(r.Solids) == 1, r)
    s2 = cad.fuse_one([a, b])
    check("fuse_one accepts a list", near(s2.Volume, 1500))


@case
def t_cut():
    a = Part.makeBox(10, 10, 10)
    s = cad.cut(a, Part.makeBox(2, 2, 20, cad.V((4, 4, -5))))
    check("cut V = 1000 - 40", near(s.Volume, 960), s.Volume)
    check("cut that misses raises",
          raises(cad.cut, a, Part.makeBox(1, 1, 1, cad.V((50, 0, 0)))) is not None)


@case
def t_rounded_box():
    x, y, z, r = 40.0, 30.0, 20.0, 5.0
    s = cad.rounded_box(x, y, z, r)
    check("rounded_box vertical V = xyz - (4-pi) r^2 z",
          near(s.Volume, x * y * z - (4 - PI) * r * r * z), s.Volume)
    m = cad.measure(s)
    check("rounded_box corner at origin, size exact",
          m["bbox_min"] == [0.0, 0.0, 0.0] and m["size"] == [x, y, z], m)
    s = cad.rounded_box(x, y, z, 3, edges="all")
    a, b, c, rr = x - 6, y - 6, z - 6, 3.0
    want = a * b * c + 2 * rr * (a * b + b * c + c * a) + PI * rr * rr * (a + b + c) \
        + 4.0 / 3.0 * PI * rr ** 3                       # Minkowski box + sphere
    check("rounded_box all V (Minkowski closed form)", near(s.Volume, want),
          (s.Volume, want))
    check("rounded_box r too big raises", raises(cad.rounded_box, 10, 10, 10, 5.5) is not None)
    # S48: the message names the limiting side and never clamps r
    msg = raises(cad.rounded_box, 30, 8, 50, 4.5) or ""
    check("rounded_box r over half a side names that side (y = 8 mm), r=3.9",
          "y = 8 mm" in msg and "use r=3.9 or less" in msg and "never clamped" in msg, msg)
    # S56: r = exactly half the short side is full round ends (the
    # self-watering planter's slot cutter SLOT_W / 2), built, not refused:
    # V = (L - 2r) * 2r * h + pi r^2 h
    s = cad.rounded_box(24, 5, 12, 2.5, at=(14, -2.5, 20))
    m = cad.measure(s)
    check("rounded_box r = half: obround V = (24-5)*5*12 + pi*2.5^2*12",
          near(s.Volume, 19 * 5 * 12 + PI * 6.25 * 12) and len(s.Solids) == 1,
          s.Volume)
    check("rounded_box obround keeps corner at `at` and the size",
          m["bbox_min"] == [14.0, -2.5, 20.0] and m["size"] == [24.0, 5.0, 12.0], m)
    s = cad.rounded_box(10, 10, 4, 5)
    check("rounded_box r = half of a square: a cylinder V = pi 25 * 4",
          near(s.Volume, PI * 25 * 4), s.Volume)
    # S56: the hex planter's back plate 100 x 4 x 150 with r=6: the message
    # offers edges='y' (its big face), and edges='y' builds it
    msg = raises(cad.rounded_box, 100, 4, 150, 6.0) or ""
    check("rounded_box limit message offers edges='y' for a plate on its edge",
          "y = 4 mm" in msg and "edges='y'" in msg and "x = 100 and z = 150" in msg, msg)
    s = cad.rounded_box(100, 4, 150, 6.0, edges="y")
    check("rounded_box edges='y' V = 100*4*150 - (4-pi) 36 * 4",
          near(s.Volume, 100 * 4 * 150 - (4 - PI) * 36 * 4), s.Volume)
    s = cad.rounded_box(20, 30, 40, 3, edges="x")
    check("rounded_box edges='x' V = xyz - (4-pi) r^2 x",
          near(s.Volume, 20 * 30 * 40 - (4 - PI) * 9 * 20), s.Volume)
    check("rounded_box unknown edges raises",
          "edges must be" in (raises(cad.rounded_box, 10, 10, 10, 1, edges="top") or ""))
    msg = raises(cad.rounded_box, 40, 40, 5, 3, edges="all") or ""
    check("rounded_box edges='all' limited by z offers edges='vertical'",
          "z = 5 mm" in msg and "edges='vertical'" in msg, msg)
    check("rounded_box negative r raises", raises(cad.rounded_box, 10, 10, 10, -1) is not None)
    at = cad.rounded_box(10, 10, 10, 0, at=(5, 6, 7))
    check("rounded_box at=", cad.measure(at)["bbox_min"] == [5.0, 6.0, 7.0])


@case
def t_fillet_safe():
    # S28: the helpers return a SHAPE; the reason is in cad.last_reason()
    # and in an optional why=[] list.
    b = Part.makeBox(20, 20, 10)
    s = cad.fillet_safe(b, 2, cad.edges_parallel(b, "Z"))
    check("fillet_safe returns a shape, vertical edges ok",
          isinstance(s, Part.Shape) and cad.last_reason() is None
          and near(s.Volume, 4000 - 4 * (1 - PI / 4) * 4 * 10), s.Volume)
    why = []
    s = cad.fillet_safe(b, 6, None, why=why)             # 6 > half of 10 mm
    check("fillet_safe impossible -> original shape + reason",
          s.isSame(b) and why and why[0] and cad.last_reason() == why[0], why)
    s = cad.fillet_safe(b, 1, lambda e: e.BoundBox.ZMin > 9.99)
    check("fillet_safe predicate (top 4 edges)", cad.last_reason() is None
          and near(s.Volume, 4000 - (1 - PI / 4) * 1 * 80), s.Volume)
    s = cad.chamfer_safe(b, 1, cad.edges_parallel(b, "Z"))
    check("chamfer_safe 4 edges V = 4000 - 4*0.5*1*1*10", cad.last_reason() is None
          and near(s.Volume, 3980), s.Volume)
    s = cad.fillet_safe(b, cad.edges_parallel(b, "Z"), 2)   # swapped order
    check("fillet_safe accepts (edges, r) too",
          near(s.Volume, 4000 - 4 * (1 - PI / 4) * 4 * 10), s.Volume)
    check("fillet_safe r of the wrong type names the signature",
          "r must be a number" in (raises(cad.fillet_safe, b, "2") or ""))
    msg = raises(cad.fuse_one, Part.makeBox(1, 1, 1),
                 Part.makeBox(1, 1, 1, cad.V((5, 0, 0))))
    check("S29: fuse_one on disjoint pieces points cutters at cut(list)",
          msg and "cad.cut(body, tools)" in msg, msg)
    two = [Part.makeCylinder(1, 20, cad.V((5, 5, -5))),
           Part.makeCylinder(1, 20, cad.V((15, 15, -5)))]
    s = cad.cut(b, two)
    check("S29: cut(list of disjoint tools) = one boolean",
          near(s.Volume, 4000 - 2 * PI * 10), s.Volume)


@case
def t_spur_gear():
    # S31. Closed forms: tip d = m(z+2), root d = m(z-2.5) (fcgear's
    # dedendum 1.25 m); a bore removes pi d^2/4 * t.
    m, z, t = 1.5, 24, 8.0
    g = cad.spur_gear(m, z, t)
    r = [math.hypot(v.X, v.Y) for v in g.Vertexes]
    check("spur_gear one valid solid", g.isValid() and len(g.Solids) == 1)
    check("spur_gear tip d = m(z+2) = 39", abs(2 * max(r) - m * (z + 2)) < 0.02,
          2 * max(r))
    check("spur_gear root d = m(z-2.5) = 32.25", abs(2 * min(r) - m * (z - 2.5)) < 0.02,
          2 * min(r))
    check("spur_gear thickness", near(cad.measure(g)["size"][2], t))
    gb = cad.spur_gear(m, z, t, bore=8)
    check("spur_gear bore removes pi*16*8", near(g.Volume - gb.Volume, PI * 16 * t),
          g.Volume - gb.Volume)
    gj = cad.spur_gear(m, z, t, backlash=0.2)
    rj = [math.hypot(v.X, v.Y) for v in gj.Vertexes]
    check("spur_gear backlash keeps tip and root", abs(max(rj) - max(r)) < 0.01
          and abs(min(rj) - min(r)) < 0.01, (max(rj), min(rj)))
    check("spur_gear backlash thins the teeth", gj.Volume < g.Volume,
          (gj.Volume, g.Volume))
    check("spur_gear too few teeth raises", raises(cad.spur_gear, 1, 4, 5) is not None)
    check("gear_shift_for(17) = 0.0057", abs(cad.gear_shift_for(17) - 0.0057) < 1e-4,
          cad.gear_shift_for(17))


@case
def t_bound_of():
    import Mesh
    a = Part.makeBox(10, 10, 10)
    b = Part.makeBox(5, 5, 5, cad.V((20, 0, -3)))
    mesh = Mesh.Mesh(Part.makeBox(2, 2, 2, cad.V((0, -7, 0))).tessellate(0.1))

    class _Feat(object):                # a Mesh::Feature stand-in: .Mesh only
        Mesh = mesh
    bb = cad.bound_of(a, [b, _Feat()])
    check("bound_of spans shapes and meshes",
          [round(v, 6) for v in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)]
          == [0, -7, -3, 25, 10, 10],
          (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax))
    check("bound_of nothing raises", raises(cad.bound_of) is not None)


@case
def t_faces_edges():
    b = Part.makeBox(10, 20, 30)
    check("faces_at +Z = one face at z=30", len(cad.faces_at(b, "+Z")) == 1
          and near(cad.faces_at(b, "+Z")[0].CenterOfMass.z, 30))
    check("faces_at -X at x=0", near(cad.faces_at(b, "-x")[0].CenterOfMass.x, 0))
    check("edges_parallel Z = 4", len(cad.edges_parallel(b, "Z")) == 4)


@case
def t_shell():
    b = Part.makeBox(40, 30, 20)
    s = cad.shell(b, 2, cad.faces_at(b, "+Z"))
    check("shell open top V = 40*30*20 - 36*26*18", near(s.Volume, 24000 - 36 * 26 * 18),
          s.Volume)
    check("shell keeps outside size", cad.measure(s)["size"] == [40.0, 30.0, 20.0])
    s = cad.shell(b, 2)
    check("shell closed V = 24000 - 36*26*16", near(s.Volume, 24000 - 36 * 26 * 16),
          s.Volume)
    check("shell t=0 raises", raises(cad.shell, b, 0) is not None)
    # S56: the limit is named up front, never met by a reduced t
    thin = Part.makeBox(40, 30, 6)
    msg = raises(cad.shell, thin, 3) or ""
    check("shell t = half the smallest size raises naming Z (z = 6 mm)",
          "t must be < 3" in msg and "z = 6 mm" in msg and "use t=2.9" in msg, msg)
    s = cad.shell(thin, 3, cad.faces_at(thin, "+Z"))
    check("shell open on Z: t may reach the whole Z size less (floor 3 of 6)",
          near(s.Volume, 40 * 30 * 6 - 34 * 24 * 3), s.Volume)
    msg = raises(cad.shell, thin, 6, cad.faces_at(thin, "+Z")) or ""
    check("shell open on Z: t = the Z size raises", "t must be < 6" in msg, msg)


@case
def t_hole():
    plate = Part.makeBox(30, 20, 5)
    s = cad.hole(plate, (10, 10, 5), "-Z", 4, through=True)
    check("hole through V = 3000 - pi*4*5", near(s.Volume, 3000 - PI * 4 * 5), s.Volume)
    s = cad.hole(plate, (10, 10, 5), "-Z", 4, depth=3)
    check("hole blind V = 3000 - pi*4*3", near(s.Volume, 3000 - PI * 4 * 3), s.Volume)
    s = cad.hole(plate, (0, 10, 2.5), "+X", 2, through=True)
    check("hole along +X through 30 mm", near(s.Volume, 3000 - PI * 30), s.Volume)
    msg = raises(cad.hole, plate, (10, 10, 5), "+Z", 4, through=True)
    check("hole WRONG axis (away from part) raises", msg and "INTO" in msg, msg)
    msg = raises(cad.hole, plate, (10, 10, 2.5), "-Z", 4, through=True)
    check("hole with `at` buried mid-plate raises", msg and "BEHIND" in msg, msg)
    # Drilling OUTWARD from inside a bore (concave entry face) is legitimate:
    # tube r 3..8, radial d=4 hole from the bore wall through the outer wall.
    tube = Part.makeCylinder(8, 20).cut(Part.makeCylinder(3, 20))
    s = cad.hole(tube, (3, 0, 10), "+X", 4, through=True)
    check("hole outward from a bore is accepted and removes material",
          s.Volume < tube.Volume - 1.0 and len(s.Solids) == 1, s.Volume)
    check("hole needs depth xor through",
          raises(cad.hole, plate, (10, 10, 5), "-Z", 4) is not None)
    # R181: through="wall" stops at the first wall of a hollow part. An
    # open-top 60 x 40 x 30 box, 2 mm walls: a d=3 hole from the +Y face
    # removes pi*1.5^2*2 (one wall); through=True removes both walls.
    case = cad.shell(Part.makeBox(60, 40, 30), 2, cad.faces_at(Part.makeBox(60, 40, 30), "+Z"))
    s = cad.hole(case, (10, 40, 15), "-Y", 3, through="wall")
    check("hole through='wall' on a hollow case: one wall, V = pi 2.25 * 2",
          near(case.Volume - s.Volume, PI * 2.25 * 2), case.Volume - s.Volume)
    s = cad.hole(case, (10, 40, 15), "-Y", 3, through=True)
    check("hole through=True on a hollow case drills both walls, V = pi 2.25 * 4",
          near(case.Volume - s.Volume, PI * 2.25 * 4), case.Volume - s.Volume)
    s = cad.hole(plate, (10, 10, 5), "-Z", 4, through="wall")
    check("hole through='wall' on a solid plate = through, V = pi*4*5",
          near(plate.Volume - s.Volume, PI * 4 * 5), plate.Volume - s.Volume)
    s = cad.counterbore(case, (10, 40, 15), "-Y", 3, 6, 1, through="wall")
    check("counterbore through='wall': V = pi/4 (36*1 + 9*1)",
          near(case.Volume - s.Volume, PI / 4 * (36 + 9)), case.Volume - s.Volume)
    s = cad.countersink(case, (10, 40, 15), "-Y", 3, 5, 90, through="wall")
    h = 1.0                                               # (5-3)/2 at 90 deg
    want = PI * h / 3 * (2.5 ** 2 + 2.5 * 1.5 + 1.5 ** 2) + PI * 2.25 * (2 - h)
    check("countersink through='wall': frustum + one wall", near(case.Volume - s.Volume, want),
          (case.Volume - s.Volume, want))
    # R181 review: a wall hole low enough to graze the floor (d=4 at z=3,
    # floor z 0..2) meets ONE solid under the whole tool (front wall + floor
    # + back wall) - it must still stop at the front wall: the back wall
    # (y 0..2) keeps all its volume, and only a floor groove up to BACK
    # past the wall is taken
    back = Part.makeBox(60, 2, 30)
    s = cad.hole(case, (30, 40, 3), "-Y", 4, through="wall")
    check("hole through='wall' grazing the floor leaves the back wall",
          near(s.common(back).Volume, case.common(back).Volume), s.common(back).Volume)
    check("hole through='wall' grazing the floor takes < 2 walls",
          case.Volume - s.Volume < PI * 4 * 2 * 2, case.Volume - s.Volume)
    # enlarging a wall hole: the axis is in air, the ring still finds the wall
    s1 = cad.hole(case, (10, 40, 15), "-Y", 3, through="wall")
    s2 = cad.hole(s1, (10, 40, 15), "-Y", 6, through="wall")
    check("hole through='wall' enlarging a hole: annulus of one wall, V = pi (9-2.25) 2",
          near(s1.Volume - s2.Volume, PI * (9 - 2.25) * 2), s1.Volume - s2.Volume)
    # a curved wall: the rim leaves a tube's inner face later than the axis
    tb = Part.makeCylinder(8, 30).cut(Part.makeCylinder(6, 30))
    s = cad.hole(tb, (8, 0, 15), "-X", 8, through="wall")
    plug = s.common(Part.makeCylinder(3.9, 4, App.Vector(8.5, 0, 15),
                                      App.Vector(-1, 0, 0))).Volume
    far = Part.makeBox(4, 20, 30, App.Vector(-8, -10, 0))
    check("hole through='wall' on a tube: no skin left, far wall intact",
          plug < 1e-3 and near(s.common(far).Volume, tb.common(far).Volume), plug)
    msg = raises(cad.hole, case, (10, 40, 15), "+Y", 3, through="wall")
    check("hole through='wall' pointing out of the part raises", msg and "INTO" in msg, msg)
    msg = raises(cad.hole, plate, (10, 10, 5), "-Z", 4, through="both")
    check("hole through='both' raises naming True / 'wall'", msg and "'wall'" in msg, msg)
    s = cad.counterbore(plate, (10, 10, 5), "-Z", 3.4, 6.5, 2)
    want = 3000 - PI / 4 * (6.5 ** 2 * 2 + 3.4 ** 2 * 3)
    check("counterbore V closed form", near(s.Volume, want), (s.Volume, want))
    s = cad.countersink(plate, (10, 10, 5), "-Z", 3.4, 6.4, 90)
    h = (6.4 - 3.4) / 2                                   # 90 deg: h = dr
    cone = PI * h / 3 * (3.2 ** 2 + 3.2 * 1.7 + 1.7 ** 2)
    want = 3000 - cone - PI * 1.7 ** 2 * (5 - h)
    check("countersink V closed form (frustum)", near(s.Volume, want), (s.Volume, want))


@case
def t_patterns():
    pin = Part.makeCylinder(1, 5)
    ps = cad.linear_pattern(pin, (10, 0, 0), 4)
    check("linear_pattern 4 copies, last at x=30", len(ps) == 4
          and near(ps[-1].BoundBox.Center.x, 30))
    g = cad.linear_pattern(pin, (10, 0, 0), 3, (0, 10, 0), 2)
    check("linear_pattern grid 3x2", len(g) == 6)
    p = Part.makeBox(1, 1, 1, cad.V((10, -0.5, 0)))
    ring = cad.polar_pattern(p, 6)
    c = ring[1].BoundBox.Center
    check("polar_pattern 6 -> 60 deg step",
          near(math.degrees(math.atan2(c.y, c.x)), 60, 1e-4), (c.x, c.y))
    arc = cad.polar_pattern(p, 3, angle=90)
    c = arc[2].BoundBox.Center
    check("polar_pattern 3 over 90 deg -> last at 90",
          near(math.degrees(math.atan2(c.y, c.x)), 90, 1e-4))
    plate = Part.makeBox(50, 10, 5)
    holes = cad.linear_pattern(Part.makeCylinder(1, 10, cad.V((5, 5, -2))), (10, 0, 0), 5)
    s = cad.cut(plate, holes)
    check("cut with pattern V = 2500 - 5*pi*5", near(s.Volume, 2500 - 5 * PI * 5), s.Volume)


@case
def t_revolve():
    s = cad.revolve([(5, 0), (10, 0), (10, 8), (5, 8)])
    check("revolve ring V = pi(10^2-5^2)*8", near(s.Volume, PI * 75 * 8), s.Volume)
    s = cad.revolve([(0, 0), (10, 0), (0, 12)])
    check("revolve cone V = pi r^2 h / 3", near(s.Volume, PI * 100 * 12 / 3), s.Volume)
    check("revolve negative radius raises",
          raises(cad.revolve, [(-1, 0), (5, 0), (5, 5)]) is not None)


@case
def t_snap_fit():
    L, t, w, h, ang = 12.0, 1.5, 6.0, 1.0, 30.0
    s = cad.snap_fit_cantilever(L, t, w, h, ang)
    ramp = h / math.tan(math.radians(ang))
    want = w * (t * (L + ramp) + h * ramp / 2)
    check("snap_fit V = w(t(L+ramp) + h*ramp/2)", near(s.Volume, want), (s.Volume, want))
    m = cad.measure(s)
    check("snap_fit hook sticks out h along +X", near(m["size"][0], t + h), m["size"])
    eps = cad.cantilever_strain(L, t, h)
    check("cantilever_strain = 1.5 t y / L^2", near(eps, 1.5 * t * h / L ** 2))
    check("snap_fit max_strain enforced",
          raises(cad.snap_fit_cantilever, L, t, w, h, max_strain=eps / 2) is not None)


@case
def t_measure():
    c = Part.makeCylinder(5, 10)
    c.rotate(cad.V((0, 0, 0)), cad.V((1, 1, 0)), 37)    # tilted: BoundBox is loose
    m = cad.measure(c)
    bound = c.BoundBox
    check("measure bbox tight <= BoundBox",
          m["size"][0] <= bound.XLength + 1e-6 and m["size"][2] <= bound.ZLength + 1e-6,
          (m["size"], [bound.XLength, bound.YLength, bound.ZLength]))
    check("measure volume = pi r^2 h", near(m["volume_mm3"], PI * 25 * 10))
    check("measure solids/valid", m["solids"] == 1 and m["valid"] is True)


def _rrect(x, y, r):
    """Area of an x*y rectangle with its 4 corners rounded to r."""
    return x * y - (4 - PI) * r * r


@case
def t_shell_rounded_side_open():
    # S44: makeThickness hands a rounded_box opened on +-X back UNCHANGED.
    # 80x60x40, vertical edges r, wall t, open at both X ends. Closed form:
    #   outer rounded box - core (76x56x36, corner r-t) - the two end slabs
    #   (the flat part of the core's end face, (56-2(r-t)) x 36, t thick)
    for r in (3.0, 5.0):
        t = 2.0
        b = cad.rounded_box(80, 60, 40, r)
        s = cad.shell(b, t, cad.faces_at(b, "+X") + cad.faces_at(b, "-X"))
        want = (_rrect(80, 60, r) * 40 - _rrect(76, 56, r - t) * 36
                - 2 * t * (56 - 2 * (r - t)) * 36)
        m = cad.measure(s)
        check("shell rounded_box r=%g open +-X: V closed form" % r,
              near(s.Volume, want) and len(s.Solids) == 1 and s.isValid(),
              (s.Volume, want))
        check("shell rounded_box r=%g keeps the outer size" % r,
              all(near(a, b_) for a, b_ in zip(m["size"], (80, 60, 40))), m["size"])
    # r == t: the inward offset degenerates at an exact zero radius
    b = cad.rounded_box(80, 60, 40, 2.0)
    s = cad.shell(b, 2.0, cad.faces_at(b, "+Z"))
    check("shell rounded_box r == t open +Z hollows", s.Volume < 0.5 * b.Volume
          and len(s.Solids) == 1, s.Volume)


@case
def t_stray_preexisting_solid():
    # R135: a shape already holding a small disjoint pin; the cut splits the
    # bar into two real halves - not a stray sliver
    bar = Part.makeBox(50, 10, 10)
    pin = Part.makeBox(2, 2, 2, cad.V((0, 20, 0)))
    both = Part.makeCompound([bar, pin])
    r = None
    try:
        r = cad.cut(both, Part.makeBox(1, 12, 12, cad.V((24.5, -1, -1))))
    except cad.CadError as exc:
        r = str(exc)
    check("cut keeps a pre-existing small solid (3 solids, no raise)",
          not isinstance(r, str) and len(r.Solids) == 3
          and near(r.Volume, 49 * 100 + 8), r if isinstance(r, str) else r.Volume)
    msg = raises(cad.cut, both, Part.makeBox(1, 12, 12, cad.V((47, -1, -1))))
    check("cut still raises on a real sliver beside a pre-existing solid",
          msg is not None and "stray" in msg, msg)


@case
def t_place_on():
    box = Part.makeBox(80, 60, 38)
    lid = Part.makeBox(80, 60, 2, cad.V((0, 0, 100)))
    check("place_on seats the lid on the box top",
          near(cad.measure(cad.place_on(lid, box))["bbox_min"][2], 38))
    check("place_on gap=-2 sinks a 2 mm lip",
          near(cad.measure(cad.place_on(lid, box, gap=-2))["bbox_min"][2], 36))
    check("place_on -Z puts it under the box",
          near(cad.measure(cad.place_on(lid, box, direction="-Z"))["bbox_max"][2], 0))


@case
def t_wedge():
    # S60: every volume is the prismatoid closed form z/6 (A0 + 4 Am + A1)
    # worked out here by hand; every position is the corner `at` + sizes
    f = cad.wedge(30, 2, 40, top_x=0, top_at=(0, 0))
    check("wedge fin (triangle 30 x 40 x 2 thick) V = 30*40/2*2 = 1200",
          near(f.Volume, 1200) and len(f.Solids) == 1 and f.isValid(), f.Volume)
    m = cad.measure(f)
    check("wedge fin corner at origin, size 30 x 2 x 40",
          m["bbox_min"] == [0.0, 0.0, 0.0] and m["size"] == [30.0, 2.0, 40.0], m)
    top = max(f.Vertexes, key=lambda p: p.Point.z).Point
    check("wedge fin top_at=(0, 0): the ridge stands over x = 0 (a vertical back edge)",
          near(top.x, 0) and near(top.z, 40), top)
    p = cad.wedge(10, 10, 6, top_x=4, top_y=4)
    check("wedge frustum V = (a^2 + ab + b^2) h / 3 = (100 + 40 + 16) * 2 = 312",
          near(p.Volume, 312), p.Volume)
    tz = [v.Point for v in p.Vertexes if near(v.Point.z, 6)]
    check("wedge frustum centred: top face x, y in 3 .. 7",
          len(tz) == 4 and near(min(v.x for v in tz), 3) and near(max(v.x for v in tz), 7)
          and near(min(v.y for v in tz), 3) and near(max(v.y for v in tz), 7), tz)
    r = cad.wedge(20, 8, 5, top_x=0, top_at=(20, 0), at=(1, 2, 3))
    check("wedge ramp V = 20*8*5/2 = 400, at=(1, 2, 3), high end over x = 21",
          near(r.Volume, 400) and cad.measure(r)["bbox_min"] == [1.0, 2.0, 3.0]
          and near(max(r.Vertexes, key=lambda p: p.Point.z).Point.x, 21), r.Volume)
    a = cad.wedge(10, 8, 4, top_x=2, top_y=2, top_at=(1, 5))
    ta = [v.Point for v in a.Vertexes if near(v.Point.z, 4)]
    check("wedge top_at=(1, 5): top face x 1 .. 3, y 5 .. 7 (not mirrored in Y), "
          "V = 4/6 (80 + 4*6*5 + 4) = 136",
          near(min(v.x for v in ta), 1) and near(max(v.x for v in ta), 3)
          and near(min(v.y for v in ta), 5) and near(max(v.y for v in ta), 7)
          and near(a.Volume, 4 / 6.0 * (80 + 4 * 6 * 5 + 4)), (ta, a.Volume))
    t = cad.wedge(10, 6, 4, top_x=10, top_y=0)
    check("wedge ridge along X (top_y=0) V = 10*6*4/2 = 120", near(t.Volume, 120), t.Volume)
    check("wedge pyramid (top 0 x 0) V = 10*10*9/3 = 300",
          near(cad.wedge(10, 10, 9, top_x=0, top_y=0).Volume, 300))
    check("wedge zero height raises", raises(cad.wedge, 10, 10, 0) is not None)
    check("wedge negative top raises", raises(cad.wedge, 10, 10, 5, -1) is not None)
    check("wedge is in __all__ (the prompt's helper card)", "wedge" in cad.__all__)


@case
def t_snap_fit_pair():
    # S61: a 60 x 40 x 30 box, 2 mm walls and floor, a flat 3 mm lid on it.
    # Closed forms, worked by hand: wall 2 -> engage min(1, 0.8*2) = 1.0,
    # hook depth hd = 1.0 + 0.2 = 1.2, lead-in ramp = 1.2 / tan 30 =
    # 2.078461; beam length min(10, 30 - 2 - ramp - 0.4 - 1) = 10.
    # Window (through the 2 mm wall): 8.4 x 2 x (ramp + 0.4) each.
    # Hook below the plate: 8 x (1.2 (10 + ramp) + 1.2 ramp / 2) each.
    ramp = 1.2 / math.tan(math.radians(30))
    win = 8.4 * 2.0 * (ramp + 0.4)
    hook = 8.0 * (1.2 * (10.0 + ramp) + 0.5 * 1.2 * ramp)

    def pair(turn=None):
        case = Part.makeBox(60, 40, 30).cut(Part.makeBox(56, 36, 30, cad.V((2, 2, 2))))
        lid = Part.makeBox(60, 40, 3, cad.V((0, 0, 30)))
        if turn:
            for s in (case, lid):
                s.rotate(cad.V((0, 0, 0)), cad.V(turn[0]), turn[1])
        return case, lid
    case, lid = pair()
    c2, l2 = cad.snap_fit_pair(case, lid, count=4)
    check("snap_fit_pair: case loses 4 windows = 4 x 8.4 x 2 x (ramp + 0.4)",
          near(case.Volume - c2.Volume, 4 * win), (case.Volume - c2.Volume, 4 * win))
    check("snap_fit_pair: lid gains 4 hooks = 4 x 8 x (1.2 (10 + ramp) + 0.6 ramp)",
          near(l2.Volume - lid.Volume, 4 * hook), (l2.Volume - lid.Volume, 4 * hook))
    check("snap_fit_pair: one solid each, valid",
          len(c2.Solids) == 1 and len(l2.Solids) == 1 and c2.isValid() and l2.isValid())
    check("snap_fit_pair: closed, the pair shares no volume",
          c2.common(l2).Volume < 1e-6, c2.common(l2).Volume)
    up = l2.copy()
    up.translate(cad.V((0, 0, 0.3)))
    check("snap_fit_pair: lifted 0.3 (> the 0.2 clearance) the hooks hit the "
          "window tops - it holds", c2.common(up).Volume > 0.1, c2.common(up).Volume)
    up.translate(cad.V((0, 0, -0.2)))
    check("snap_fit_pair: lifted 0.1 (< clearance) it is still free",
          c2.common(up).Volume < 1e-6, c2.common(up).Volume)
    # the windows sit on the longer (+-Y) walls at x = 15 and 45, z from
    # 30 - 10 - ramp - 0.2 to 30 - 10 + 0.2
    zs = [30 - 10 - ramp - 0.2, 30 - 10 + 0.2]
    for x, y in ((15, 1), (45, 1), (15, 39), (45, 39)):
        p = cad.V((x, y, 0.5 * (zs[0] + zs[1])))
        check("snap_fit_pair: window through the wall at (%g, %g)" % (x, y),
              case.isInside(p, 1e-6, True) and not c2.isInside(p, 1e-6, True))
    # a lid on the +X side (the same pair turned): the same volumes
    case, lid = pair(((0, 1, 0), 90))           # +Z -> +X
    c3, l3 = cad.snap_fit_pair(case, lid, count=4, direction="+X")
    check("snap_fit_pair direction='+X': same windows and hooks",
          near(case.Volume - c3.Volume, 4 * win) and near(l3.Volume - lid.Volume, 4 * hook),
          (case.Volume - c3.Volume, l3.Volume - lid.Volume))
    check("snap_fit_pair direction='+X': closed pair shares nothing",
          c3.common(l3).Volume < 1e-6)
    case, lid = pair()
    check("snap_fit_pair: count must be even",
          raises(cad.snap_fit_pair, case, lid, count=3) is not None)
    far = lid.copy()
    far.translate(cad.V((0, 0, 5)))
    msg = raises(cad.snap_fit_pair, case, far)
    check("snap_fit_pair: a lid parked above the case raises (place_on)",
          msg is not None and "place_on" in msg, msg)
    shallow = Part.makeBox(60, 40, 6).cut(Part.makeBox(56, 36, 6, cad.V((2, 2, 2))))
    msg = raises(cad.snap_fit_pair, shallow, Part.makeBox(60, 40, 3, cad.V((0, 0, 6))))
    check("snap_fit_pair: a 6 mm deep case is too shallow",
          msg is not None and "too shallow" in msg, msg)
    msg = raises(cad.snap_fit_pair, case, lid, max_strain=0.01)
    check("snap_fit_pair: strain 1.5 x 1.2 x 1.0 / 100 = 1.8 % > max_strain 1 % raises",
          msg is not None and "1.80%" in msg, msg)
    # a lid with a lip inside the walls: the lip is cut back round each beam
    lip = Part.makeBox(55.6, 35.6, 5.5, cad.V((2.2, 2.2, 25))).cut(
        Part.makeBox(51.6, 31.6, 6, cad.V((4.2, 4.2, 24.9))))
    lid_lip = cad.fuse_one(Part.makeBox(60, 40, 3, cad.V((0, 0, 30))), lip)
    c4, l4 = cad.snap_fit_pair(case, lid_lip, count=2)
    check("snap_fit_pair with a lip: one solid, closed pair shares nothing",
          len(l4.Solids) == 1 and c4.common(l4).Volume < 1e-6, c4.common(l4).Volume)
    check("snap_fit_pair is in __all__ (the prompt's helper card)",
          "snap_fit_pair" in cad.__all__)


def _hinge_pair():
    """The S65 box: 60 x 40 x 25 outside, 2 mm walls, open on top, a 2 mm
    lid plate seated on it."""
    body = Part.makeBox(60, 40, 25)
    box = cad.shell(body, 2.0, cad.faces_at(body, "+Z"))
    return box, cad.place_on(Part.makeBox(60, 40, 2), box)


@case
def t_pin_hinge():
    import atech_geom
    box, lid = _hinge_pair()
    b, l, m = cad.pin_hinge(box, lid)
    # closed forms: bore = 1.75 + 2 x 0.2 = 2.15; knuckle radius = 2.15/2 +
    # the 2 mm wall = 3.075; 3 knuckles on 60 mm with 2 gaps of 0.2:
    # s = (60 - 0.4) / 3 = 19.8667; the axis ON the back face (y = 40) at the
    # wall top (z = 25), opening by the right-hand rule about -X
    s, R, rb = (60 - 0.4) / 3.0, 1.075 + 2.0, 1.075
    check("pin_hinge: motion entry = Lid about (30, 40, 25) along -X, 0 .. 90",
          m == {"part": "Lid", "axis": [[30.0, 40.0, 25.0], [-1.0, 0.0, 0.0]],
                "range_deg": [0.0, 90.0]}, m)
    check("pin_hinge: one valid solid each", len(b.Solids) == 1 and len(l.Solids) == 1
          and b.isValid() and l.isValid())

    def at(x, r, deg):          # a point r from the axis, deg up from +Y
        return cad.V((x, 40 + r * math.cos(math.radians(deg)),
                      25 + r * math.sin(math.radians(deg))))
    mids = (s / 2, s + 0.2 + s / 2, 2 * (s + 0.2) + s / 2)
    owners = ((b, l), (l, b), (b, l))
    for k, (x, (own, other)) in enumerate(zip(mids, owners)):
        check("pin_hinge: knuckle %d (x = %.2f) belongs to the %s only" % (
            k, x, "box" if own is b else "lid"),
            own.isInside(at(x, R - 0.1, 90), 1e-6, True)
            and not other.isInside(at(x, R - 0.1, 90), 1e-6, True)
            and not own.isInside(at(x, R + 0.1, 90), 1e-6, True))
        check("pin_hinge: knuckle %d bore is %.3f across (1.75 pin + 2 x 0.2)" % (k, 2 * rb),
              not own.isInside(at(x, rb - 0.02, 45), 1e-6, True)
              and own.isInside(at(x, rb + 0.02, 45), 1e-6, True))
    gap = s + 0.1                    # between knuckle 0 and 1: 0.2 mm axial gap
    check("pin_hinge: 0.2 mm axial gap between knuckles is air",
          not b.isInside(at(gap, 2.5, 90), 1e-6, True)
          and not l.isInside(at(gap, 2.5, 90), 1e-6, True))
    check("pin_hinge: closed, the pair shares no volume", b.common(l).Volume < 1e-6)
    parts = [{"label": "Box", "shape": b}, {"label": "Lid", "shape": l}]
    row, bad, _w, _n = atech_geom.motion_probe(parts, {"motion": [m]})
    check("pin_hinge: ./check's sweep (motion_probe) passes 0 .. 90 in 5 deg steps",
          not bad and row["parts"][0]["verdict"] == "PASS"
          and row["parts"][0]["positions"] == 19, (bad, row))
    # sabotage: the same parts, the declared axis 3 mm inside the back face
    bad_m = {"part": "Lid", "axis": [[30.0, 37.0, 25.0], [-1.0, 0.0, 0.0]],
             "range_deg": [0, 90]}
    row, bad, _w, _n = atech_geom.motion_probe(parts, {"motion": [bad_m]})
    check("pin_hinge sabotage: axis 3 mm inside the back face is BLOCKED at 5 deg",
          bad and row["parts"][0]["verdict"] == "BLOCKED"
          and row["parts"][0]["blocked_at"] == 5.0, (bad, row))
    msg = raises(cad.pin_hinge, box, lid, axis=[[0, 37, 25], [1, 0, 0]])
    check("pin_hinge: an explicit axis 3 mm inside the back face raises",
          msg is not None and "3.00 mm INSIDE" in msg, msg)
    b2, l2, m2 = cad.pin_hinge(box, lid, axis=[[0, 41, 25], [1, 0, 0]])
    check("pin_hinge: an explicit axis 1 mm outside the face is kept (y = 41)",
          m2["axis"][0][1:] == [41.0, 25.0] and m2["axis"][1] == [-1.0, 0.0, 0.0], m2)
    b3, l3, m3 = cad.pin_hinge(box, lid, axis="-X", knuckles=2)
    check("pin_hinge axis='-X': on x = 0 at the wall top, opening about -Y",
          m3["axis"] == [[0.0, 20.0, 25.0], [0.0, -1.0, 0.0]], m3)
    far = lid.copy()
    far.translate(cad.V((0, 0, 5)))
    msg = raises(cad.pin_hinge, box, far)
    check("pin_hinge: a lid parked above the box raises (place_on)",
          msg is not None and "place_on" in msg, msg)
    check("pin_hinge: knuckles must be >= 2",
          raises(cad.pin_hinge, box, lid, knuckles=1) is not None)
    check("pin_hinge: a tangent clearance raises",
          raises(cad.pin_hinge, box, lid, clearance=0.0) is not None)
    check("pin_hinge is in __all__", "pin_hinge" in cad.__all__)


@case
def t_socket_opening():
    """S66: needs the Atech module library (projects/); SKIP without it."""
    import atech_geom
    projects = os.path.normpath(os.path.join(HERE, "..", "..", "..", "projects"))
    if projects not in sys.path:
        sys.path.append(projects)
    try:
        import atech_ports as ap
        doc = App.newDocument("socket_opening_test")
        ap.board_object(doc)
        usb = ap.seat(doc, "usbc", 5)
    except Exception as exc:                            # noqa: BLE001
        print("SKIP socket_opening: no Atech library here (%s)" % exc)
        return
    board = [o for o in doc.Objects if getattr(o, "AtechRole", None) == "board"][0]
    ub = ap.bbox(usb)
    # a 2 mm plate 4.5 mm off the module's -X end (port 5: a left-edge port,
    # its mouth faces -X - R164), 40 x 40 round the module's centre
    plate = Part.makeBox(2.0, 40.0, 40.0, cad.V((ub.XMin - 6.5, ub.Center.y - 20,
                                                   ub.Center.z - 20)))

    def open_rays(shape):
        rows = atech_geom.face_open([{"label": "Wall", "shape": shape}],
                                    {"label": "board", "mesh": board.Mesh},
                                    [{"label": usb.Label, "module": "usbc",
                                      "mesh": usb.Mesh, "axes": [
                                          list(usb.Placement.Rotation.multVec(cad.V(e)))
                                          for e in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]}])
        return rows[0]
    before = open_rays(plate)
    cut_plate = cad.socket_opening(plate, usb)
    after = open_rays(cut_plate)
    check("socket_opening: the plate seals the socket before (0 rays open, mouth -X)",
          before["open"] == 0 and atech_geom.normal_text(before["normal"]) == "-X", before)
    check("socket_opening: after the call every ray from the mouth gets out",
          after["open"] == after["rays"], after)
    # the shell measured R164: a 10 x 3.5 mouth; + 1.5 a side = 13 x 6.5,
    # through the 2 mm plate
    removed = plate.Volume - cut_plate.Volume
    check("socket_opening: removes (10 + 3) x (3.5 + 3) x 2 = 169 mm3",
          abs(removed - 169.0) < 0.5, removed)
    check("socket_opening: one valid solid", len(cut_plate.Solids) == 1
          and cut_plate.isValid())
    behind = plate.copy()
    behind.translate(cad.V((ub.XLength + 20.0, 0, 0)))    # behind the module, +X
    msg = raises(cad.socket_opening, behind, usb)
    check("socket_opening: a wall not in front of the mouth raises",
          msg is not None and "in front of" in msg, msg)
    light = ap.seat(doc, "light", 2)
    msg = raises(cad.socket_opening, plate, light)
    check("socket_opening: a module with no socket mouth raises",
          msg is not None and "no socket mouth" in msg, msg)
    check("socket_opening is in __all__", "socket_opening" in cad.__all__)
    App.closeDocument(doc.Name)


print("ATECH_CAD_TESTS=%d" % len(FAIL))
sys.stdout.flush()
os._exit(0)
