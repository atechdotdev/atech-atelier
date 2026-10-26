"""Unit tests for agent_kit/atech_form.py (R230) - runs INSIDE freecadcmd.

    <freecadcmd> fc_atech_form.py          (tests/test_kit_form.py does this)

Every expected number is a CLOSED FORM worked out by hand here (box,
cylinder, sphere, frustum, rounded-box volumes; exact face areas), or a
MEASURED bound stated next to it - never a value read back from the helper
under test. Prints PASS/FAIL per check and TIME lines, and ends with
ATECH_FORM_TESTS=<failures>. ATECH_FORM_SABOTAGE=<gate> breaks one gate to
prove the suite can fail:
  1             extrude_profile builds 5 % short
  coremin       profile_body(inset=) fillets core radii under CORE_MIN_R
  corefallback  a core fillet that fails is no longer left sharp (R250)
  rimwall       hollow() takes the first opening cut that passes the volume
                test without measuring its wall (R250, the sloped hardtop)
  nudge         split() keeps a plane that lies on a wall's flat face (R250)
R270 gates (each switches one new fallback off; its case must then raise):
  fillet_all fillet_sharp fillet_split fillet_shrink fillet_soften
  fillet_unfilleted          profile_body's fillet ladder rungs
  hollow_profile hollow_fitted hollow_thick     hollow()'s new rungs
  split_lip0 split_nudge     split()'s lip=0 fallback / the 3 mm nudge
  offset_polygon             the cusp-safe offset's polygon fallback
  fair                       spline fairing (the faired outline wiggles)
  tangent                    the tangent-end plan stretch
  guard                      the forked makeFillet guard (a hang is waited out)
  g1                         a spline meeting a line at a soft angle stays kinked
  cut_optional               cad.cut ignores optional=True
ATECH_FORM_ONLY=r270 runs only the R270 cases (test_kit_form_r270.py).
"""
import math
import os
import sys
import time
import traceback

sys.dont_write_bytecode = True     # keep the shipped kit folder clean
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "acadagent", "agent_kit")))

import FreeCAD as App  # noqa: E402
import Part  # noqa: E402

import atech_cad as cad  # noqa: E402
import atech_form as form  # noqa: E402

FAIL = []
PI = math.pi
SLOW = 5.0          # every helper on a toy-sized body must beat this (s)

SAB = os.environ.get("ATECH_FORM_SABOTAGE", "")
if SAB == "1":
    _real_extrude = form.extrude_profile

    def _bad_extrude(wire_or_points, height, taper_deg=0, direction="+Z"):
        return _real_extrude(wire_or_points, height * 0.95, taper_deg, direction)
    form.extrude_profile = _bad_extrude
elif SAB == "coremin":          # R250: tiny inset-core fillets attempted
    form.CORE_MIN_R = 0.0
elif SAB == "corefallback":     # R250: a failed core fillet raises again
    form._FILLET_OFF.add("unfilleted")      # R270: the ladder's last rung
    _real_fb = form._fillet_body

    def _strict_fb(body, r_top, r_bot, z0, what, core=False):
        try:
            return _real_fb(body, r_top, r_bot, z0, what, core)
        except cad.CadError as exc:
            raise RuntimeError(str(exc))
    form._fillet_body = _strict_fb
elif SAB == "rimwall":          # R250: _void no longer measures each opening cut
    _real_void = form._void

    def _old_void(shape, c, t, v0, extra=(), open_floor=0.0, alt=(), faces=()):
        res = _real_void(shape, c, t, v0, extra, open_floor, alt, ())
        return res[0], None, None
    form._void = _old_void
elif SAB == "nudge":            # R250: split no longer moves off a flat face
    form._nudged = lambda body, n, at, reach=0.3: None
    form._SPLIT_OFF.add("lip0")             # R270: or the lip=0 fallback hides it
elif SAB.startswith("fillet_"):             # R270: one fillet-ladder rung off
    form._FILLET_OFF.add(SAB[len("fillet_"):])
elif SAB.startswith("hollow_"):             # R270: one new hollow rung off
    form._HOLLOW_OFF.update({"profile": ["profile core"], "fitted": ["fitted core"],
                             "thick": ["makeThickness join=2", "makeThickness join=0"]}
                            [SAB[len("hollow_"):]])
elif SAB.startswith("split_"):              # R270: a split fallback off
    form._SPLIT_OFF.add({"lip0": "lip0", "nudge": "nudge3"}[SAB[len("split_"):]])
elif SAB == "offset_polygon":
    form._OFFSET_OFF.add("polygon")
elif SAB == "fair":
    form._FAIR_ON[0] = False
elif SAB == "tangent":
    form._TANGENT_ON[0] = False
elif SAB == "guard":
    form._GUARD_ON[0] = False
elif SAB == "g1":
    form._G1_ON[0] = False
elif SAB == "cut_optional":                 # R270: optional= ignored (strict)
    _real_cut = cad.cut

    def _strict_cut(shape, *tools, **kw):
        return _real_cut(shape, *tools)
    cad.cut = _strict_cut
ONLY = os.environ.get("ATECH_FORM_ONLY", "")


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


def timed(name, fn, limit=SLOW):
    t0 = time.time()
    res = fn()
    dt = time.time() - t0
    print("TIME %-34s %.2f s" % (name, dt))
    check("%s runs under %g s" % (name, limit), dt < limit, "%.2f s" % dt)
    return res


def one(s, name):
    check("%s: one valid solid" % name, s is not None and s.isValid()
          and len(s.Solids) == 1, None if s is None else (s.isValid(), len(s.Solids)))


def case(fn):
    if ONLY == "r270" and not fn.__name__.startswith("test_r270"):
        return fn
    try:
        fn()
    except Exception:                                   # noqa: BLE001
        check(fn.__name__, False, traceback.format_exc())
    return fn


def rounded_box_volume(a, b, c, r):
    """Every edge of an a x b x c box rounded r (closed form)."""
    A, B, C = a - 2 * r, b - 2 * r, c - 2 * r
    return (A * B * C + 2 * r * (A * B + B * C + A * C)
            + PI * r * r * (A + B + C) + 4.0 / 3.0 * PI * r ** 3)


RECT_SIDE = [(0, 0), ("line", (100, 0)), ("line", (100, 30)), ("line", (0, 30))]
RECT_PLAN = [(0, -20), ("line", (100, -20)), ("line", (100, 20)), ("line", (0, 20))]
CAR_SIDE = [(0, 6), (4, 15), (30, 20), (52, 31), (92, 32), (118, 22), (140, 18),
            ("corner", (143, 8)), ("line", (140, 0)), ("line", (3, 0))]
CAR_PLAN = [(0, -23), (30, -30), (110, -30), (143, -24), (143, 24), (110, 30),
            (30, 30), (0, 23)]


@case
def test_all_and_card():
    for name in form.__all__:
        fn = getattr(form, name, None)
        check("%s is public and documented" % name, callable(fn) and fn.__doc__)
        first = " ".join(fn.__doc__.split("\n\n")[0].split())
        # build.helper_card() cuts at the first ". " and at 170 chars
        cut = first.split(". ")[0]
        check("%s: first docstring sentence <= 170 chars" % name,
              len(cut) <= 170, len(cut))


@case
def test_spline_wire():
    pts = [(10 * math.cos(2 * PI * i / 12), 10 * math.sin(2 * PI * i / 12))
           for i in range(12)]
    w = form.spline_wire(pts, plane="XY")
    f = Part.Face(w)
    check("spline_wire: 12 points on r=10 close as ONE periodic edge",
          w.isClosed() and len(w.Edges) == 1, len(w.Edges))
    check("spline_wire: that loop's area is pi r^2 within 0.1 %",
          near(f.Area, PI * 100, 1e-3), f.Area)
    check("spline_wire: plane XY puts it at z = 0",
          abs(w.BoundBox.ZMin) < 1e-9 and abs(w.BoundBox.ZMax) < 1e-9)
    w = form.spline_wire(RECT_SIDE, plane="XZ")
    check("spline_wire: ('line', p) items give a 100 x 30 rectangle in XZ",
          len(w.Edges) == 4 and near(Part.Face(w).Area, 3000.0)
          and abs(w.BoundBox.YMax) < 1e-9, (len(w.Edges), Part.Face(w).Area))
    w = form.spline_wire([(0, 0), ("line", (10, 0)), ("arc", (15, 5), (10, 10)),
                          ("line", (0, 10))], plane="XY")
    check("spline_wire: ('arc', mid, end) adds a half disc: 100 + pi 25 / 2",
          near(Part.Face(w).Area, 100 + PI * 12.5), Part.Face(w).Area)
    w = form.spline_wire([(0, 0, 0), (10, 5, 3), (20, 0, 6)], closed=False)
    check("spline_wire: open 3D path keeps its end points",
          not w.isClosed() and (w.OrderedVertexes[-1].Point - App.Vector(20, 0, 6)).Length < 1e-9)
    msg = raises(form.profile_body, [(0, 0), (10, 10), (10, 0), (0, 10)], RECT_PLAN, spline=False)
    check("spline_wire/profile_body: a self-crossing outline raises", msg is not None
          and "crosses itself" in msg, msg)
    check("spline_wire: a bad plane raises", raises(form.spline_wire, pts, plane="QQ"))


@case
def test_rounded_rect_wire():
    w = form.rounded_rect_wire(20, 10, 3)
    check("rounded_rect_wire: 8 edges", len(w.Edges) == 8, len(w.Edges))
    check("rounded_rect_wire: area 200 - (4 - pi) 9",
          near(Part.Face(w).Area, 200 - (4 - PI) * 9), Part.Face(w).Area)
    w0 = form.rounded_rect_wire(20, 10, 0)
    check("rounded_rect_wire: r=0 is a 4-edge 200 mm2 rectangle",
          len(w0.Edges) == 4 and near(Part.Face(w0).Area, 200.0))
    wx = form.rounded_rect_wire(20, 10, 2, center=(5, 0, 7), normal="X")
    bb = wx.BoundBox
    check("rounded_rect_wire: normal X -> w along Y, h along Z, at x=5",
          near(bb.YLength, 20) and near(bb.ZLength, 10) and bb.XLength < 1e-9
          and near(bb.XMin, 5) and near(bb.Center.z, 7), (bb.YLength, bb.ZLength))
    wf = form.rounded_rect_wire(20, 10, 5)
    check("rounded_rect_wire: r = h/2 keeps 8 edges (stadium)", len(wf.Edges) == 8)
    check("rounded_rect_wire: r > h/2 raises", raises(form.rounded_rect_wire, 20, 10, 6))


@case
def test_profile_body_box():
    b = form.profile_body(RECT_SIDE, RECT_PLAN, spline=False)
    one(b, "profile_body box")
    check("profile_body: rectangle side x rectangle plan = 100 x 40 x 30 box",
          near(b.Volume, 120000.0), b.Volume)
    m = cad.measure(b)
    check("profile_body: box bbox", m["bbox_min"] == [0, -20, 0] and m["size"] == [100, 40, 30], m)
    f = form.profile_body(RECT_SIDE, RECT_PLAN, spline=False, fillet=3)
    check("profile_body: fillet=3 on every edge = the rounded-box closed form",
          near(f.Volume, rounded_box_volume(100, 40, 30, 3)), (f.Volume, rounded_box_volume(100, 40, 30, 3)))
    c = form.profile_body(RECT_SIDE, RECT_PLAN, spline=False, fillet=3, inset=2)
    check("profile_body: inset=2 is the 96 x 36 x 26 box rounded r=1",
          near(c.Volume, rounded_box_volume(96, 36, 26, 1)), c.Volume)
    s = form.profile_body(RECT_SIDE, RECT_PLAN, spline=False, fillet=(3, 0))
    bot = cad.faces_at(s, "-Z")
    top = cad.faces_at(s, "+Z")
    # the 4 upright edges are rounded too, so the bottom face loses 4 corners
    check("profile_body: fillet=(3, 0) keeps the bottom sharp (4000 - (4 - pi) 9)",
          len(bot) == 1 and near(bot[0].Area, 4000.0 - (4 - PI) * 9), [x.Area for x in bot])
    check("profile_body: ... and rounds the top (94 x 34 flat face)",
          len(top) == 1 and near(top[0].Area, 94 * 34.0), [x.Area for x in top])
    a = form.profile_body(RECT_SIDE, RECT_PLAN, spline=False, at=(10, 0, 5))
    check("profile_body: at moves the body", near(cad.measure(a)["bbox_min"][0], 10)
          and near(cad.measure(a)["bbox_min"][2], 5))
    check("profile_body: outlines that miss along X raise",
          raises(form.profile_body, RECT_SIDE, [(200, -5), ("line", (300, -5)),
                                                ("line", (300, 5)), ("line", (200, 5))],
                 spline=False))
    # R270: never raises while a valid body exists - softened or unfilleted
    big = form.profile_body(RECT_SIDE, RECT_PLAN, spline=False, fillet=60)
    one(big, "profile_body fillet=60")
    check("profile_body: a fillet bigger than the body returns a valid body inside "
          "the box, not a raise (R270)", big.Volume <= 120000.0 + 1e-6, big.Volume)


@case
def test_profile_body_car():
    b = timed("profile_body car fillet=4", lambda: form.profile_body(
        CAR_SIDE, CAR_PLAN, fillet=4))
    one(b, "profile_body car")
    m = cad.measure(b)
    # MEASURED bound: the centripetal splines swing <= 7.5 mm past the knots
    check("profile_body car: size within the knots' box + the measured swing",
          135 < m["size"][0] < 152 and 55 < m["size"][1] < 70 and 30 < m["size"][2] < 37, m["size"])
    # MEASURED: without the trim the fillet bulged to z = -0.63 (4.4 mm3)
    check("profile_body car: nothing below the flat bottom z = 0 (fillet bulge trimmed)",
          m["bbox_min"][2] > -1e-3, m["bbox_min"])
    s = timed("profile_body car fillet=(4, 0)", lambda: form.profile_body(
        CAR_SIDE, CAR_PLAN, fillet=(4, 0)))
    one(s, "profile_body car sharp bottom")


@case
def test_loft():
    sq = [form.rounded_rect_wire(10, 10, 0, (0, 0, 0)),
          form.rounded_rect_wire(10, 10, 0, (0, 0, 10))]
    b = form.loft(sq, ruled=True)
    check("loft: two 10 x 10 squares 10 apart = 1000 mm3", near(b.Volume, 1000.0), b.Volume)
    fr = form.loft([form.rounded_rect_wire(10, 10, 0, (0, 0, 0)),
                    form.rounded_rect_wire(20, 20, 0, (0, 0, 10))], ruled=True)
    check("loft: ruled square 10 -> 20 = frustum h/3 (A1 + A2 + sqrt A1 A2)",
          near(fr.Volume, 10 / 3.0 * (100 + 400 + 200)), fr.Volume)
    py = form.loft([form.rounded_rect_wire(10, 10, 0, (0, 0, 0)), (0, 0, 9)], ruled=True)
    check("loft: square to an apex = pyramid A h / 3", near(py.Volume, 300.0), py.Volume)
    secs = [form.rounded_rect_wire(w, h, r, (x, 0, z), "X")
            for x, w, h, r, z in [(0, 50, 18, 6, 14), (15, 60, 26, 8, 16),
                                  (60, 64, 30, 9, 17), (110, 62, 28, 9, 16),
                                  (140, 52, 20, 7, 14)]]
    car = timed("loft 5 rounded sections", lambda: form.loft(secs))
    one(car, "loft car")
    msg = raises(form.loft, [form.rounded_rect_wire(10, 10, 0),
                             form.rounded_rect_wire(10, 10, 2, (0, 0, 5))])
    check("loft: sections with 4 and 8 edges raise", msg is not None and "edges" in msg, msg)
    w2 = form.rounded_rect_wire(10, 10, 2, (0, 0, 8))
    flip = Part.Wire(list(reversed([e.reversed() for e in w2.OrderedEdges])))
    msg = raises(form.loft, [form.rounded_rect_wire(10, 10, 2), flip])
    check("loft: a section running the other way round raises", msg is not None, msg)


@case
def test_extrude_profile():
    sq = [(0, 0), (10, 0), (10, 10), (0, 10)]
    b = form.extrude_profile(sq, 5)
    check("extrude_profile: 10 x 10 by 5 = 500 mm3", near(b.Volume, 500.0), b.Volume)
    t = form.extrude_profile(sq, 5, taper_deg=10)
    s2 = 10 - 2 * 5 * math.tan(math.radians(10))
    check("extrude_profile: 10 deg taper = frustum to a %.3f square" % s2,
          near(t.Volume, 5 / 3.0 * (100 + s2 * s2 + 10 * s2)), t.Volume)
    g = form.extrude_profile(sq, 5, taper_deg=-10)
    s3 = 10 + 2 * 5 * math.tan(math.radians(10))
    check("extrude_profile: -10 deg flares out", near(g.Volume, 5 / 3.0 * (100 + s3 * s3 + 10 * s3)), g.Volume)
    x = form.extrude_profile(sq, 7, direction="+X")
    m = cad.measure(x)
    check("extrude_profile: +X takes points as (y, z) and grows 7 along X",
          m["size"] == [7, 10, 10] and m["bbox_min"] == [0, 0, 0], m)
    c = form.extrude_profile(Part.Wire([Part.makeCircle(5)]), 4, taper_deg=5)
    r2 = 5 - 4 * math.tan(math.radians(5))
    check("extrude_profile: tapered circle = cone frustum",
          near(c.Volume, PI * 4 / 3.0 * (25 + r2 * r2 + 5 * r2)), c.Volume)
    check("extrude_profile: a taper closing the outline raises",
          raises(form.extrude_profile, sq, 40, taper_deg=20))
    check("extrude_profile: height <= 0 raises", raises(form.extrude_profile, sq, 0))


@case
def test_hollow_box():
    box = Part.makeBox(40, 30, 20)
    o = form.hollow(box, 2, open_faces=["+Z"])
    one(o, "hollow open box")
    check("hollow: open-top box = 40*30*20 - 36*26*18",
          near(o.Volume, 24000 - 36 * 26 * 18), o.Volume)
    c = form.hollow(box, 2)
    check("hollow: closed box = 40*30*20 - 36*26*16",
          near(c.Volume, 24000 - 36 * 26 * 16), c.Volume)
    check("hollow: t too big raises", raises(form.hollow, box, 12))
    check("hollow: no flat face that way raises",
          raises(form.hollow, Part.makeSphere(10), 1, open_faces=["+Z"]))


@case
def test_hollow_car():
    b = form.profile_body(CAR_SIDE, CAR_PLAN, fillet=4)
    v0 = b.Volume
    core = lambda t: form.profile_body(CAR_SIDE, CAR_PLAN, fillet=4, inset=t)  # noqa: E731
    h = timed("hollow car closed (core)", lambda: form.hollow(b, 2, core=core))
    one(h, "hollow car")
    mw = h.Shells and len(h.Shells) == 2 and h.Shells[1].distToShape(h.Shells[0])[0]
    # MEASURED: 1.45-1.5 mm where three fillets meet at the nose; 2.0 elsewhere
    check("hollow car: two shells, measured wall 1.4..2.05 mm", mw and 1.4 < mw < 2.05, mw)
    check("hollow car: removed the core volume", v0 - h.Volume > 0.6 * v0, (v0, h.Volume))
    s = form.profile_body(CAR_SIDE, CAR_PLAN, fillet=(4, 0))
    core0 = lambda t: form.profile_body(CAR_SIDE, CAR_PLAN, fillet=(4, 0), inset=t)  # noqa: E731
    # KNOWN LIMIT, MEASURED (R230): 3-5 s, up to 8 s when OCCT's inset core
    # needs the fallback cut
    o = timed("hollow car open bottom (core)",
              lambda: form.hollow(s, 2, open_faces=["-Z"], core=core0), limit=10.0)
    one(o, "hollow car open")
    bot = cad.faces_at(o, "-Z")
    check("hollow car open: the bottom is an open rim, not a floor",
          bot and sum(f.Area for f in bot) < 0.25 * cad.faces_at(s, "-Z")[0].Area,
          [f.Area for f in bot])
    msg = raises(form.hollow, b, 2, open_faces=["-Z"])
    check("hollow: opening a face with rounded rims raises with the knife-edge fix",
          msg is not None and "knife" in msg, msg)


@case
def test_pipe():
    p = form.pipe([(0, 0, 0), (50, 0, 0)], r=2, caps="flat")
    check("pipe: straight 50 mm tube r=2 = pi r^2 L", near(p.Volume, PI * 4 * 50), p.Volume)
    q = form.pipe([(0, 0, 0), (50, 0, 0)], r=2)
    check("pipe: round caps add one ball", near(q.Volume, PI * 4 * 50 + 4 / 3.0 * PI * 8), q.Volume)
    path = [(0, 0, 0), (10, 0, 15), (30, 0, 20), (50, 0, 15), (60, 0, 0)]
    h = timed("pipe spline handle", lambda: form.pipe(path, r=2.5, caps="flat"))
    w = form.spline_wire(path, closed=False)
    check("pipe: spline tube = pi r^2 L within 1 %", near(h.Volume, PI * 6.25 * w.Length, 1e-2),
          (h.Volume, PI * 6.25 * w.Length))
    msg = raises(form.pipe, [(0, 0, 0), (5, 0, 5), (10, 0, 0)], r=6)
    check("pipe: r over the tightest bend raises", msg is not None and "bend" in msg, msg)
    sq = form.pipe([(0, 0, 0), (0, 0, 30)], profile=[(-2, -2), (2, -2), (2, 2), (-2, 2)])
    check("pipe: a square profile from 2D points = 16 x 30", near(sq.Volume, 480.0), sq.Volume)
    hx = form.pipe(Part.Wire(Part.makeHelix(4, 20, 10)), r=0.8, frenet=True, caps="flat")
    one(hx, "pipe helix")


@case
def test_revolve_profile():
    c = form.revolve_profile([(0, 0), (5, 0), (5, 10), (0, 10)])
    check("revolve_profile: rectangle -> cylinder pi 25 10", near(c.Volume, PI * 250), c.Volume)
    s = form.revolve_profile([(0, -5), ("arc", (5, 0), (0, 5))])
    check("revolve_profile: half disc -> sphere 4/3 pi 125", near(s.Volume, 4 / 3.0 * PI * 125), s.Volume)
    x = form.revolve_profile([(0, 0), (5, 0), (5, 10), (0, 10)], axis="X", at=(1, 2, 3))
    m = cad.measure(x)
    check("revolve_profile: axis X through (1,2,3): 10 long on X, d 10",
          near(m["size"][0], 10) and near(m["size"][1], 10) and near(m["bbox_min"][0], 1)
          and near(m["center_of_mass"][1], 2) and near(m["center_of_mass"][2], 3), m)
    h = form.revolve_profile([(0, 0), (5, 0), (5, 10), (0, 10)], angle=90)
    check("revolve_profile: 90 deg = a quarter", near(h.Volume, PI * 250 / 4), h.Volume)
    sp = form.revolve_profile([(0, 0), ("line", (8, 0)), (9, 4), (6, 9), ("corner", (0, 10)),
                               ("line", (0, 0))], spline=True)
    one(sp, "revolve_profile spline")
    msg = raises(form.revolve_profile, [(0, 0), (8, 0), (9, 4), (6, 9), ("corner", (0, 10))],
                 spline=True)
    check("revolve_profile: a spline that swings across the axis raises",
          msg is not None and "crosses the axis" in msg, msg)
    check("revolve_profile: a negative radius raises",
          raises(form.revolve_profile, [(-1, 0), (5, 0), (5, 10)]))


@case
def test_mirror():
    b = Part.makeBox(2, 3, 4, App.Vector(5, 1, 0))
    m = form.mirror(b, "YZ")
    check("mirror: YZ flips X", near(cad.measure(m)["bbox_min"][0], -7) and near(m.Volume, 24))
    m = form.mirror(b, "XZ", through=(0, 10, 0))
    check("mirror: XZ through y=10 maps y 1..4 to 16..19", near(cad.measure(m)["bbox_min"][1], 16))
    half = Part.makeBox(10.5, 4, 3, App.Vector(-0.5, 0, 0))
    s = form.symmetric(half, "YZ")
    check("symmetric: half x -0.5..10 + its mirror -> one 20 x 4 x 3 solid",
          len(s.Solids) == 1 and near(s.Volume, 20 * 12), s.Volume)
    msg = raises(form.symmetric, Part.makeBox(5, 4, 3, App.Vector(1, 0, 0)), "YZ")
    check("symmetric: a half that misses the plane raises", msg is not None and "CROSS" in msg, msg)
    a, c = form.mirror_pair(Part.makeBox(5, 4, 3, App.Vector(1, 0, 0)), "YZ")
    check("mirror_pair: two separate bodies", a.Volume == c.Volume and
          a.common(c).Volume < 1e-9)
    check("mirror_pair: overlapping raises", raises(form.mirror_pair, half, "YZ"))


@case
def test_split_box():
    box = form.hollow(Part.makeBox(40, 30, 20), 2)
    lo, up = form.split(box, "Z", at=10)
    check("split: the two halves add up to the body", near(lo.Volume + up.Volume, box.Volume),
          (lo.Volume, up.Volume, box.Volume))
    check("split: halves meet at z=10", near(lo.BoundBox.ZMax, 10) and near(up.BoundBox.ZMin, 10))
    lo0, up0 = lo.Volume, up.Volume
    lo, up = form.split(box, "Z", at=10, lip=1.5, clearance=0.2)
    one(lo, "split lower")
    one(up, "split upper")
    # ring: the outer section 40 x 30 shrunk by 1.1 (half the 2 mm wall, but
    # >= 0.9 + 0.2 clearance so the upper keeps 0.9 mm of skin; sharp
    # corners stay sharp inward) = 37.8 x 27.8, minus the 36 x 26 cavity shrunk
    # 1 mm (the lip stands 1 mm into it) = 34 x 24; it rises 1.5 and sinks
    # 0.3 into lower - which only adds volume over the cavity (36x26-34x24)
    ring = 37.8 * 27.8 - 34 * 24
    gain = ring * 1.5 + (36 * 26 - 34 * 24) * 0.3
    check("split: lower gains exactly the lip ring x 1.5 (+ its 0.3 mm root)",
          near(lo.Volume, lo0 + gain), (lo.Volume - lo0, gain))
    groove = (38.2 * 28.2 - 36 * 26) * 1.7
    check("split: upper loses exactly the groove (38.2 x 28.2 - 36 x 26) x 1.7",
          near(up.Volume, up0 - groove), (up0 - up.Volume, groove))
    # R270: a solid section splits WITHOUT a lip (WARNING), never raises
    lo, up = form.split(Part.makeBox(10, 10, 10), "Z", at=5, lip=1)
    check("split: a lip on a solid body falls back to lip=0 (R270): 500 + 500",
          near(lo.Volume, 500.0) and near(up.Volume, 500.0), (lo.Volume, up.Volume))
    check("split: at outside the body raises", raises(form.split, box, "Z", at=30))


@case
def test_split_car():
    b = form.profile_body(CAR_SIDE, CAR_PLAN, fillet=4)
    h = form.hollow(b, 2, core=lambda t: form.profile_body(CAR_SIDE, CAR_PLAN, fillet=4, inset=t))
    lo, up = timed("split car no lip", lambda: form.split(h, "Z", at=12))
    one(lo, "split car lower")
    one(up, "split car upper")
    # KNOWN LIMIT, MEASURED (R230): 4.9-5.3 s on the 143 mm car shell with
    # other agents loading the machine - the lip fuse (1.2 s) and groove
    # cut (1.4 s) on two spline shells; without a lip 0.6 s
    lo, up = timed("split car lip=2", lambda: form.split(h, "Z", at=12, lip=2), limit=7.0)
    one(lo, "split car lip lower")
    one(up, "split car lip upper")
    check("split car: chassis + shell stay apart (the clearance)",
          lo.common(up).Volume < 1e-6)



# ------------------------------------------------------------------ R250
SOAP_SIDE = [(0, 0), ("line", (60, 0)), (64, 6), (58, 16), (30, 20), (2, 16), (-4, 6)]
SOAP_PLAN = [(-6, 0), (5, -18), (30, -22), (55, -18), (66, 0), (55, 18), (30, 22), (5, 18)]


@case
def test_r250_inset_core_small_fillet():
    # fillet 2.3 - inset 2 = 0.3 < CORE_MIN_R: the core is the SHARP
    # 96 x 36 x 26 box (closed form), not a 0.3 mm fillet of offset curves
    c = form.profile_body(RECT_SIDE, RECT_PLAN, spline=False, fillet=2.3, inset=2)
    check("R250 profile_body: an inset core radius under 0.5 stays sharp = 96*36*26",
          near(c.Volume, 96 * 36 * 26.0, 1e-7), c.Volume)   # r=0.3 would take 12 mm3
    # MEASURED: the soap bar's core fillet r=1 fails at every rung (0.3 up)
    b = form.profile_body(SOAP_SIDE, SOAP_PLAN, fillet=3)
    core = timed("R250 profile_body soap inset=2", lambda: form.profile_body(
        SOAP_SIDE, SOAP_PLAN, fillet=3, inset=2))
    one(core, "R250 soap core")
    check("R250 profile_body: the unfilleted soap core lies inside the body",
          core is not None and core.cut(b).Volume < 1e-3 and core.Volume < b.Volume)
    h = timed("R250 hollow soap (sharp core)", lambda: form.hollow(
        b, 2, core=lambda t: form.profile_body(SOAP_SIDE, SOAP_PLAN, fillet=3, inset=t)))
    one(h, "R250 hollow soap")
    mw = form._gap(h.Shells[1], h.Shells[0]) if len(h.Shells) == 2 else 0
    # a sharp core in an r=3 body: the wall at its edges >= 3 - sqrt(2) (3 - 2)
    check("R250 hollow soap: two shells, wall >= 3 - sqrt(2) = 1.59 mm",
          1.5 < mw < 2.05, mw)


@case
def test_r250_hollow_sloped_open_bottom():
    # the toy car's hardtop: a windscreen sloping in over an open bottom.
    # MEASURED: the open-face cutters ran 0.22 mm from its outer skin and
    # the whole core rung failed; the core's own end faces leave 1.77 mm
    side = [(-17, 57), ("line", (86, 57)), ("line", (69, 76.5)), ("line", (-17, 76.5))]
    plan = form.rounded_rect_wire(110, 92, 7, (40, 0, 0), "Z")
    b = form.profile_body(side, plan, spline=False, fillet=(4, 0))
    h = timed("R250 hollow sloped hardtop open -Z", lambda: form.hollow(
        b, 2, open_faces=["-Z"], core=lambda t: form.profile_body(
            side, plan, spline=False, fillet=(4, 0), inset=t)))
    one(h, "R250 hardtop")
    # the windscreen's outer skin at z = 58.5 is at x = 86 - 1.5 * 17 / 19.5
    xo = 86 - 1.5 * 17 / 19.5
    check("R250 hollow: material 1 mm inside the sloped windscreen at z=58.5",
          h.isInside(App.Vector(xo - 1.0, 0, 58.5), 1e-6, True))
    check("R250 hollow: the bottom is open (no floor at z=57.5 mid-cabin)",
          not h.isInside(App.Vector(30, 0, 57.5), 1e-6, True))


@case
def test_r250_split_on_inner_face():
    box = form.hollow(Part.makeBox(40, 30, 20), 2)      # floor 0..2, roof 18..20
    for at in (2.0, 1.95):
        lo, up = timed("R250 split at z=%g lip=1.5" % at, lambda: form.split(
            box, "Z", at=at, lip=1.5))
        one(lo, "R250 split lower at %g" % at)
        one(up, "R250 split upper at %g" % at)
        check("R250 split at z=%g (the floor's inner face): moved to 2.01, lip to 3.51"
              % at, near(up.BoundBox.ZMin, 2.01, 1e-4) and near(lo.BoundBox.ZMax, 3.51, 1e-4),
              (lo.BoundBox.ZMax, up.BoundBox.ZMin))
        check("R250 split at z=%g: halves apart" % at, lo.common(up).Volume < 1e-6)
    lo, up = form.split(box, "Z", at=2.0)
    check("R250 split lip=0 on the face stays where asked",
          near(lo.BoundBox.ZMax, 2.0, 1e-6), lo.BoundBox.ZMax)
    lo, up = form.split(Part.makeBox(10, 10, 10), "Z", at=5, lip=1)
    check("R250 split: a lip on a solid body splits plain (R270 lip=0 fallback)",
          near(lo.BoundBox.ZMax, 5.0) and near(up.BoundBox.ZMin, 5.0))



# ------------------------------------------------------------------ R270
# The round-1 outlines, numbers as the agents' model.py computed them
# (toy car w03: SIDE/PLAN from its hardware; desk robot w06: torso_body).
R1_CAR_SIDE = [(-16.0, 8.0), (-20.0, 10.0), (-22.0, 18.0), (-22.5, 34.0), (-22.3, 50.0),
               (-21.2, 58.6), (-19.6, 63.1), (-15.0, 63.0), (-4.5, 62.5), (20.0, 62.3),
               (58.0, 62.0), (80.0, 61.2), (100.0, 60.3), (130.0, 58.9), (150.0, 57.9),
               (161.97, 56.6), (168.47, 54.0), (171.77, 49.0), (172.97, 40.2), (172.57, 28.0),
               (170.97, 18.0), ("corner", (166.47, 10.0)), ("line", (151.97, 7.0)),
               ("line", (-10.5, 7.0))]
_R1_HALF = [(-22.5, 0.0), (-22.2, 24.0), (-20.9, 40.0), (-17.9, 52.0), (-12.0, 60.497),
            (-2.0, 63.897), (10.0, 64.497), (22.0, 63.997), (33.0, 61.497), (42.0, 57.019),
            (52.0, 55.219), (78.0, 55.019), (98.0, 55.619), (108.0, 58.997), (118.0, 63.197),
            (130.0, 64.497), (142.0, 63.797), (152.0, 60.497), (160.0, 54.997),
            (166.47, 45.997), (170.47, 34.0), (172.57, 18.0), (173.17, 0.0)]
R1_CAR_PLAN = _R1_HALF + [(x, -y) for x, y in reversed(_R1_HALF[1:-1])]
# a hand-typed 15-knot slab plan (uneven spacing): interpolated it swings
# through 2 inflections its knots do not make (MEASURED)
SLAB15_PLAN = [(0, 0), (2, 18), (4, 40), (12, 52), (30, 58), (60, 59), (90, 58), (108, 52),
               (116, 40), (118, 18), (116, -2), (108, -12), (60, -16), (12, -12), (3, -6)]
SLAB15_SIDE = [(-2, 0), ("line", (122, 0)), (124, 8), (121, 26), (110, 36), (80, 40),
               (40, 40), (10, 36), (-1, 26), (-4, 10)]
# a heart lens with a cusp at its notch: makeOffset2D join=2 returns NULL
HEART = [("corner", (0, -10)), (5, -5), (9, 0), (10, 4), (8.5, 8), (5, 9.5), (1.8, 8.4),
         (0.4, 6.4), ("corner", (0, 5)), (-0.4, 6.4), (-1.8, 8.4), (-5, 9.5), (-8.5, 8),
         (-10, 4), (-9, 0), (-5, -5)]


def extra_flips(points, plane):
    """Curvature sign flips of spline_wire(points) beyond the knots' own."""
    w = form.spline_wire(points, plane=plane)
    n = App.Vector(*form._PLANE_NORMAL[plane])
    flips = 0
    for e in w.Edges:
        if isinstance(e.Curve, Part.BSplineCurve):
            flips += form._curve_flips(e.Curve, e.FirstParameter, e.LastParameter, n,
                                       len(w.Edges) == 1, 400)[0]
    pts = [form._to3(p, plane) for p in points if not isinstance(p[0], str)]
    return flips - form._poly_flips(pts, True, n)


def mesh_vol(s):
    """Volume of a fine tessellation: OCCT's Shape.Volume of lofted and
    offset spline solids is up to 13 % off (MEASURED R270: a hollow car
    301 612 mm3 where its halves' meshes add up to 342 005)."""
    import Mesh
    return Mesh.Mesh(s.tessellate(0.05)).Volume


def wall_of(h):
    return form._gap(h.Shells[1], h.Shells[0]) if len(h.Shells) == 2 else None


def r270(*gates):
    """An R270 case: a sabotage run of any other gate skips it (the R250
    gates' runs stay fast); the plain run does them all."""
    def deco(fn):
        if SAB and SAB not in gates:
            print("SKIP %s (sabotage %s)" % (fn.__name__, SAB))
            return fn
        return case(fn)
    return deco


def isolated(knob, names, fn):
    """fn() with only the named rungs on (the rest of the ladder off)."""
    knob[0] = tuple(names)
    try:
        return fn()
    finally:
        knob[0] = None


@r270("fair")
def test_r270_fair_15_knots():
    form._FAIR_ON[0], keep = False, form._FAIR_ON[0]
    raw = extra_flips(SLAB15_PLAN, "XY")
    form._FAIR_ON[0] = keep
    got = extra_flips(SLAB15_PLAN, "XY")
    check("R270 fair: the interpolated 15-knot plan wiggles (2 extra inflections, "
          "MEASURED)", raw >= 2, raw)
    check("R270 fair: faired, it makes no inflection its knots do not", got == 0, got)
    w = form.spline_wire(SLAB15_PLAN, plane="XY")
    dev = max(w.distToShape(Part.Vertex(form._to3(p, "XY")))[0] for p in SLAB15_PLAN)
    check("R270 fair: every knot within FAIR_TOL_MAX of the faired curve",
          dev <= form.FAIR_TOL_MAX + 1e-6, dev)
    check("R270 fair: still ONE periodic edge", len(w.Edges) == 1 and w.isClosed())
    b = timed("R270 profile_body slab15 fillet=6", lambda: form.profile_body(
        SLAB15_SIDE, SLAB15_PLAN, fillet=6), limit=15.0)
    one(b, "R270 slab15 body")
    h = timed("R270 hollow slab15 (no core=: the profile core)",
              lambda: form.hollow(b, 2.0), limit=15.0)
    one(h, "R270 slab15 shell")
    mw = wall_of(h)
    check("R270 hollow slab15: two shells, min wall >= 0.8 mm", mw is not None and mw >= 0.8, mw)


@r270("g1")
def test_r270_g1_join():
    # a floor line meeting the tail spline at ~10 deg joins TANGENT
    w = form.spline_wire(R1_CAR_SIDE, plane="XZ")
    ends = []
    for e in w.Edges:
        if isinstance(e.Curve, Part.BSplineCurve):
            for u, p in ((e.FirstParameter, e.Vertexes[0].Point),
                         (e.LastParameter, e.Vertexes[-1].Point)):
                if (p - App.Vector(-10.5, 0, 7.0)).Length < 1e-6:
                    ends.append(e.tangentAt(u))
    ok = ends and abs(abs(ends[0].x) - 1.0) < 1e-6 and abs(ends[0].z) < 1e-6
    check("R270 G1: the spline leaves the floor line's end (-10.5, 7) along X",
          ok, ends)


@r270("tangent")
def test_r270_tangent_ends():
    b = form.profile_body(R1_CAR_SIDE, R1_CAR_PLAN)
    one(b, "R270 round-1 car body")
    seam = [e for e in b.Edges if isinstance(e.Curve, Part.Line) and e.BoundBox.XLength < 1e-6
            and e.BoundBox.YLength < 1e-6 and abs(e.BoundBox.XMin + 22.5) < 0.2]
    # MEASURED: without the stretch the common carries a 12.5 mm line edge
    # at the tail (x = -22.5, y = 0) and every fillet r=7..2.1 failed
    check("R270 tangent ends: no degenerate seam edge at the tail", not seam,
          [e.Length for e in seam])


@r270("fillet_unfilleted")
def test_r270_car_fillet_never_fails():
    for fil in ((7.0, 2.0), 7.0):
        b = timed("R270 round-1 car fillet=%s" % (fil,), lambda: form.profile_body(
            R1_CAR_SIDE, R1_CAR_PLAN, fillet=fil), limit=60.0)
        one(b, "R270 round-1 car fillet=%s" % (fil,))
        m = cad.measure(b)
        check("R270 car fillet=%s: inside the unfilleted body's box" % (fil,),
              m["bbox_min"][2] > 7.0 - 0.05 and m["bbox_max"][2] < 63.5, m)


@r270("fillet_all", "fillet_sharp", "fillet_split", "fillet_shrink", "fillet_soften", "fillet_unfilleted")
def test_r270_fillet_rungs_isolated():
    ka = form._FILLET_ONLY
    box = (RECT_SIDE, RECT_PLAN)
    for rung, fil in (("all", 3), ("sharp", 3), ("split", 3), ("shrink", 19), ("soften", 19)):
        msg = None
        try:
            b = isolated(ka, [rung], lambda: form.profile_body(*box, spline=False, fillet=fil))
            ok = b.isValid() and len(b.Solids) == 1 and b.Volume < 120000.0 - 1.0
        except cad.CadError as exc:
            ok, msg = False, str(exc)[:160]
        check("R270 fillet rung '%s' alone rounds the 100x40x30 box (fillet=%g)"
              % (rung, fil), ok, msg)
    # 'sharp' leaves a soft crease alone: a 10 deg chin line
    side = [(0, 0), ("line", (100, 0)), ("line", (120, 3.5)), ("line", (120, 30)),
            ("line", (0, 30))]
    b = isolated(ka, ["sharp"], lambda: form.profile_body(side, RECT_PLAN, spline=False,
                                                          fillet=3))
    one(b, "R270 sharp rung with a soft crease")
    u = isolated(ka, ["unfilleted"], lambda: form.profile_body(RECT_SIDE, RECT_PLAN,
                                                               spline=False, fillet=60))
    check("R270 fillet rung 'unfilleted' alone returns the plain 120000 mm3 box",
          near(u.Volume, 120000.0), u.Volume)


@r270("hollow_profile", "hollow_fitted", "hollow_thick")
def test_r270_hollow_rungs_isolated():
    kh = form._HOLLOW_ONLY
    b = form.profile_body(CAR_SIDE, CAR_PLAN, fillet=4)
    soap = form.profile_body(SOAP_SIDE, SOAP_PLAN, fillet=3)
    # the profile core on the car; the fitted (scaled) core on the round soap
    # bar - on the car scaling never keeps half the wall (0.74 mm, MEASURED)
    for rung, body in (("profile core", b), ("fitted core", soap)):
        try:
            h = isolated(kh, [rung], lambda: form.hollow(body, 2.0))
            mw = wall_of(h)
            ok = h.isValid() and len(h.Solids) == 1 and mw is not None and mw >= 0.8
        except cad.CadError as exc:
            ok, mw = False, str(exc)[:200]
        check("R270 hollow rung '%s' alone hollows it, wall >= 0.8 mm" % rung, ok, mw)
    box = Part.makeBox(40, 30, 20)
    try:
        h = isolated(kh, ["makeThickness join=2", "makeThickness join=0"],
                     lambda: form.hollow(box, 2))
        ok = near(h.Volume, 24000 - 36 * 26 * 16) or h.Volume
    except cad.CadError as exc:
        ok = str(exc)[:200]
    check("R270 hollow rung makeThickness alone: closed box 24000 - 36*26*16", ok is True, ok)
    try:
        h = isolated(kh, ["fitted core"], lambda: form.hollow(box, 2, open_faces=["+Z"]))
        ok = h.isValid() and not h.isInside(App.Vector(20, 15, 19.5), 1e-6, True) and \
            h.isInside(App.Vector(20, 15, 1.0), 1e-6, True)
    except cad.CadError as exc:
        ok = str(exc)[:200]
    check("R270 hollow 'fitted core' alone opens the box top and keeps its floor", ok is True, ok)


@r270("split_lip0")
def test_r270_split_solid_section():
    # round 1, toy car: "split: the section at Z=11.5 is solid" - the floor
    # reached past the split plane. Here: a 5 mm skin, floor z 7..12.
    b = form.profile_body(R1_CAR_SIDE, R1_CAR_PLAN)
    h = timed("R270 hollow round-1 car t=5", lambda: form.hollow(b, 5.0), limit=30.0)
    lo, up = timed("R270 split car Z=11.5 lip=1.5 (solid section)",
                   lambda: form.split(h, "Z", at=11.5, lip=1.5), limit=30.0)
    one(lo, "R270 car split lower")
    one(up, "R270 car split upper")
    a, b = mesh_vol(lo) + mesh_vol(up), mesh_vol(h)
    check("R270 split car (lip=0 fallback): the halves' meshes add up to the shell's",
          near(a, b, 5e-3), (a, b))


ROBOT_T_A = [(10, 68.6), (40, 71.0), (70, 70.4), (97, 68.2), (112, 66.8)]
ROBOT_T_YF = [(10, -26.5), (30, -28.6), (50, -29.0), (75, -28.0), (112, -25.0)]


def _lerp(knots, z):
    if z <= knots[0][0]:
        return knots[0][1]
    for (z0, v0), (z1, v1) in zip(knots, knots[1:]):
        if z <= z1:
            return v0 + (v1 - v0) * (z - z0) / (z1 - z0)
    return knots[-1][1]


def _roll(dz, R, t):
    r = R - t
    if dz <= 0:
        return t
    dz = min(dz, r)
    return t + r - math.sqrt(max(r * r - dz * dz, 0.0))


def _bowed_rect(a, yf, yb, Rf, rf, rb, z, cx=60.0):
    V = App.Vector
    cf = V(cx, yf + Rf, z)
    ycf = yf + Rf - math.sqrt((Rf - rf) ** 2 - (a - rf) ** 2)

    def P(x, y):
        return V(x, y, z)

    def arc(c, r, a0, a1):
        am, a0, a1 = math.radians((a0 + a1) / 2), math.radians(a0), math.radians(a1)
        return Part.Arc(P(c.x + r * math.cos(a0), c.y + r * math.sin(a0)),
                        P(c.x + r * math.cos(am), c.y + r * math.sin(am)),
                        P(c.x + r * math.cos(a1), c.y + r * math.sin(a1))).toShape()
    cl, cr = V(cx - (a - rf), ycf, z), V(cx + (a - rf), ycf, z)
    bl, br = V(cx - (a - rb), yb - rb, z), V(cx + (a - rb), yb - rb, z)
    phl = math.degrees(math.atan2(cl.y - cf.y, cl.x - cf.x)) % 360
    phr = math.degrees(math.atan2(cr.y - cf.y, cr.x - cf.x)) % 360
    return Part.Wire([
        Part.makeLine(P(br.x, yb), P(bl.x, yb)), arc(bl, rb, 90, 180),
        Part.makeLine(P(cx - a, bl.y), P(cx - a, ycf)), arc(cl, rf, 180, phl),
        arc(cf, Rf, phl, phr), arc(cr, rf, phr, 360),
        Part.makeLine(P(cx + a, ycf), P(cx + a, br.y)), arc(br, rb, 0, 90)])


def robot_torso(t=0.0):
    """The round-1 desk robot's torso (its model.py, verbatim numbers): a
    loft of bowed-rect sections with rolled bottom/top edges."""
    z0, z1, r_bot, r_top = 10.0, 112.0, 5.0, 14.0
    rb_, rt_ = r_bot - t, r_top - t
    side = (z1 - r_top) - (z0 + r_bot)
    total = math.pi / 2 * rb_ + side + math.pi / 2 * rt_
    count = max(12, int(round(total / 4.0)))
    zs = []
    for k in range(count + 1):
        s_ = total * k / count
        if s_ <= math.pi / 2 * rb_:
            zs.append(z0 + r_bot - rb_ * math.cos(s_ / rb_))
        elif s_ <= math.pi / 2 * rb_ + side:
            zs.append(z0 + r_bot + (s_ - math.pi / 2 * rb_))
        else:
            zs.append(z1 - r_top + rt_ * math.sin((s_ - math.pi / 2 * rb_ - side) / rt_))
    secs = []
    for z in zs:
        e = max(_roll(z0 + r_bot - z, r_bot, t), _roll(z - (z1 - r_top), r_top, t))
        secs.append(_bowed_rect(_lerp(ROBOT_T_A, z) - e, _lerp(ROBOT_T_YF, z) + e, 9.0 - e,
                                600.0 - e, 16.0 - e, 15.0 - e, z))
    return Part.makeLoft(secs, True, False, False, 3).Solids[0]


@r270("split_lip0", "split_nudge")
def test_r270_robot_lip_split():
    # round 1, desk robot: split(torso, "Y", at=2.2, lip=1.2) raised "the
    # wall at the split is 0.96 mm - too thin for a lip", then "the lower
    # part is invalid at Y=2.2" / "0 separate solids" at every plane tried
    torso = cad.cut(robot_torso(), robot_torso(2.0))
    mw = wall_of(torso)
    check("R270 robot torso shell: min wall >= 0.8 mm", mw is not None and mw >= 0.8, mw)
    lo, up = timed("R270 split robot torso Y=2.2 lip=1.2",
                   lambda: form.split(torso, "Y", at=2.2, lip=1.2), limit=40.0)
    one(lo, "R270 robot split front")
    one(up, "R270 robot split back")
    a, b = mesh_vol(lo) + mesh_vol(up), mesh_vol(torso)
    check("R270 robot split (lip=0 fallback): the halves' meshes add up to the torso's",
          near(a, b, 5e-3), (a, b))
    check("R270 robot split: the halves stay apart", lo.common(up).Volume < 1e-3)
    h = timed("R270 hollow robot torso (core 0.87 mm: the next rungs)", lambda: form.hollow(
        robot_torso(), 2.0, core=robot_torso), limit=30.0)
    mw = wall_of(h)
    check("R270 hollow robot torso: one solid, min wall >= 0.8 mm",
          h.isValid() and len(h.Solids) == 1 and mw is not None and mw >= 0.8, mw)


@r270("offset_polygon")
def test_r270_heart_offset():
    f = Part.Face(form.spline_wire(HEART, plane="XZ"))
    check("R270 heart: makeOffset2D join=2 fails on the cusp (MEASURED)",
          raises(lambda: form._offset_face(f, -0.1, "heart", join=2)) is not None)
    for d in (-0.1, 0.8, 1.5):
        try:
            g = form._offset2d(f, d, "heart")
            ok = g.isValid() and ((d < 0 and g.Area < f.Area) or (d > 0 and g.Area > f.Area))
        except cad.CadError as exc:
            ok = str(exc)[:160]
        check("R270 heart: the cusp-safe offset by %g is one valid face" % d, ok is True, ok)
    # the polygon fallback on its own (joins switched off)
    form._OFFSET_OFF.update(("join2", "join0"))
    try:
        g = form._offset2d(f, 0.8, "heart")
        ok = g.isValid() and abs(g.Area - (f.Area + 0.8 * f.OuterWire.Length)) < \
            0.1 * f.Area
    except cad.CadError as exc:
        ok = str(exc)[:160]
    finally:
        form._OFFSET_OFF.discard("join2")
        form._OFFSET_OFF.discard("join0")
    check("R270 heart: the polygon fallback alone grows it by ~0.8 x perimeter", ok is True, ok)


@r270()
def test_r270_shell_body():
    lo, up = timed("R270 shell_body car (classic) wall 2 split 12 lip 1.2",
                   lambda: form.shell_body(CAR_SIDE, CAR_PLAN, 2.0, split_z=12, fillet=4),
                   limit=40.0)
    one(lo, "R270 shell_body lower")
    one(up, "R270 shell_body upper")
    check("R270 shell_body: lower and upper apart", lo.common(up).Volume < 1e-6)
    lo, up = timed("R270 shell_body slab15 wall 2 (fillet=(6, 0))",
                   lambda: form.shell_body(SLAB15_SIDE, SLAB15_PLAN, 2.0, split_z=14,
                                           fillet=(6, 0)), limit=40.0)
    one(lo, "R270 shell_body slab lower")
    one(up, "R270 shell_body slab upper")
    msg = raises(form.shell_body, CAR_SIDE, CAR_PLAN, 40.0)
    check("R270 shell_body: an impossible wall raises ONE CadError naming the step",
          msg is not None and msg.startswith("shell_body: the hollow step failed"), msg)


@r270("cut_optional")
def test_r270_cut_optional():
    box = Part.makeBox(10, 10, 10)
    far = Part.makeBox(1, 1, 1, App.Vector(50, 0, 0))
    check("R270 cad.cut: a miss still raises by default", raises(cad.cut, box, far))
    r = cad.cut(box, far, optional=True)
    check("R270 cad.cut(optional=True): a miss returns the shape unchanged",
          near(r.Volume, 1000.0), r.Volume)


@r270("guard")
def test_r270_guard():
    box = Part.makeBox(10, 10, 10)
    t0 = time.time()
    res, why = form._guarded(lambda: (time.sleep(3), box)[1], 0.5)
    dt = time.time() - t0
    check("R270 guard: a hung OCCT call is killed after its limit",
          res is None and "killed" in str(why) and dt < 2.0, (why, dt))
    res, why = form._guarded(lambda: box.makeFillet(1, box.Edges), 10)
    check("R270 guard: a real fillet comes back intact (BREP round trip)",
          res is not None and near(res.Volume, rounded_box_volume(10, 10, 10, 1)),
          None if res is None else res.Volume)
    if form._guard_ok():
        import ctypes
        res, why = form._guarded(lambda: ctypes.string_at(0), 5)
        check("R270 guard: a segfault in the call is reported, not fatal",
              res is None and "crash" in str(why), why)


print("ATECH_FORM_TESTS=%d" % len(FAIL))
sys.stdout.flush()
os._exit(0)
