"""Unit tests for agent_kit/atech_detail.py - runs INSIDE freecadcmd (R230+).

    <freecadcmd> fc_atech_detail.py        (tests/test_kit_detail.py does this)

Every expected number is a CLOSED FORM worked out by hand here (or built
here from Part primitives), never a value read back from the helper under
test. Prints PASS/FAIL per check and ends with ATECH_DETAIL_TESTS=<failures>.

ATECH_DETAIL_SABOTAGE=<gate> breaks one gate to prove the suite can fail:
  fillet   soften()'s result gate accepts anything (an INVALID fillet slips out)
  hex      grille() drills hexes 0.9x their size
  wall     grille()/speaker_grille() drill through EVERY wall, not the first
  breach   groove_outline()'s wall-thickness gate is off
  overlap  wheel() builds the rim 0.3 mm INTO the tyre bead (its gate must raise)
  surface  grille()/text() accept a `center`/`at` any distance off the surface
  meets    opening_for()'s "the part still meets the wall" gate is off
  rim      screw_boss() measures the floor at the column's axis only
  offset   groove_ring()/groove_outline() offset a slice wire the old way
           (Part.Face(wire.makeOffset2D): INVALID on spline sections, R250)
  probe    a groove cut is no longer proven by probe points (R250)
  onewall  opening_for() may cut a channel along a wall or a second wall
  workface opening_for() ignores a module's measured working face (R250)
  madeaxis opening_for() forgets the axis a cap / lens was built along
  riblen   screw_boss() gussets reach 0.8 x their height (12 mm on M3)
R270 gates:
  cusp     inlay()'s offsets go back to makeOffset2D join=2 (NULL on a cusp)
  local    opening_for() casts its rays on the whole wall, not its local region
  guard    soften()'s makeFillet runs in-process again (a hang is waited out)
ATECH_DETAIL_ONLY=r270 runs only the R270 cases (test_kit_form_r270.py).
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
import atech_detail as det  # noqa: E402
import atech_form as form  # noqa: E402

V = App.Vector
FAIL = []
PI = math.pi
TIMES = {}
SAB = os.environ.get("ATECH_DETAIL_SABOTAGE", "")

if SAB == "fillet":
    det._fillet_ok = lambda before, res, what: None
elif SAB == "hex":
    _real_hex = det._hex_face
    det._hex_face = lambda af: _real_hex(af * 0.9)
elif SAB == "wall":
    _real_drill = det._drill_pattern
    det._drill_pattern = lambda shape, c, n, holes, through, what: _real_drill(
        shape, c, n, holes, True, what)
elif SAB == "breach":
    det._wall_check = lambda *a, **k: []
elif SAB == "overlap":
    det.RIM_GAP = -0.3                          # the rim pushed into the bead
elif SAB == "surface":
    det.ON_SURFACE = 1e9
elif SAB == "meets":
    det._still_meets = lambda part, wall: 0.0
elif SAB == "rim":
    det._floor_under_rim = lambda case, p, a, od, t_in, sink, u, v: (t_in, sink)
elif SAB == "offset":           # R250: the old wire offset (invalid on splines)
    def _old_offset(w, d):
        try:
            f = Part.Face(w.makeOffset2D(d, 0, False, False, False))
        except Exception:                               # noqa: BLE001
            return None
        a0 = Part.Face(w).Area
        return f if (d < 0 and f.Area < a0) or (d > 0 and f.Area > a0) else None
    det._offset_loop = _old_offset
elif SAB == "probe":            # R250: grooves no longer proven by probe points
    det._cut_probed = lambda shape, tools, probes, what, region=None: shape.cut(
        tools if len(tools) > 1 else tools[0])
elif SAB == "onewall":          # R250: opening_for may cut along / into 2 walls
    det._one_wall = lambda *a, **k: None
elif SAB == "workface":         # R250: a module's working face is ignored
    det._module_axis = lambda obj: (None, None)
elif SAB == "madeaxis":         # R250: a cap / lens forgets its build axis
    det._shape_key = lambda shape: None
elif SAB == "riblen":           # R250: gussets reach 0.8 x their height again
    det.RIB_LEN_D = 100.0
elif SAB == "cusp":             # R270: the old join=2-only offset in inlay()
    form._offset2d = lambda face, d, what: form._offset_face(face, d, what, join=2)
elif SAB == "local":            # R270: opening_for's rays on the whole wall
    det._LOCAL_ON[0] = False
elif SAB == "guard":            # R270: soften's fillets unguarded
    form._GUARD_ON[0] = False
ONLY = os.environ.get("ATECH_DETAIL_ONLY", "")

def check(name, cond, detail=""):
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        FAIL.append(name)


def near(a, b, rel=1e-3, abs_=1e-6):
    return abs(a - b) <= max(abs_, rel * max(1.0, abs(b)))


def raises(fn, *a, **k):
    try:
        fn(*a, **k)
    except cad.CadError as exc:
        return str(exc)
    return None


def ok_solid(s, n=1):
    return s is not None and s.isValid() and len(s.Solids) == n


def timed(name, fn):
    t = time.time()
    out = fn()
    TIMES[name] = round(time.time() - t, 3)
    return out


def case(fn):
    if ONLY == "r270" and not fn.__name__.startswith("t_r270"):
        return fn
    try:
        fn()
    except Exception:                                   # noqa: BLE001
        check(fn.__name__, False, traceback.format_exc())
    return fn


def open_box(x, y, z, t):
    """A box open at +Z with walls and floor t thick, built from primitives."""
    return Part.makeBox(x, y, z).cut(Part.makeBox(x - 2 * t, y - 2 * t, z, V(t, t, t)))


def rounded_volume(a, b, c, r):
    """A box a x b x c with EVERY edge and corner rounded r (closed form)."""
    return ((a - 2 * r) * (b - 2 * r) * (c - 2 * r)
            + 2 * r * ((a - 2 * r) * (b - 2 * r) + (b - 2 * r) * (c - 2 * r)
                       + (a - 2 * r) * (c - 2 * r))
            + PI * r * r * ((a - 2 * r) + (b - 2 * r) + (c - 2 * r))
            + 4.0 / 3.0 * PI * r ** 3)


# ------------------------------------------------------------------ soften
@case
def t_soften():
    box = Part.makeBox(30, 20, 10)
    s = timed("soften box r=2", lambda: det.soften(box, 2))
    check("soften: a 30x20x10 box at r=2 has the closed-form rounded volume",
          ok_solid(s) and near(s.Volume, rounded_volume(30, 20, 10, 2)), s.Volume)
    check("soften: success leaves last_reason() None", cad.last_reason() is None,
          cad.last_reason())
    # r=6 cannot fit a 10 mm side: the ladder's 0.6 step (3.6) can
    s = det.soften(box, 6)
    check("soften: r=6 on a 10 mm side falls back to the ladder's r=3.6",
          ok_solid(s) and near(s.Volume, rounded_volume(30, 20, 10, 3.6)), s.Volume)
    # every rung invalid -> the input back, unchanged, with a reason
    s = det.soften(box, 20, min_r=19)
    check("soften: nothing roundable -> the input unchanged", s.isSame(box) or
          near(s.Volume, 6000.0), s.Volume)
    check("soften: ... and last_reason() says why", bool(cad.last_reason())
          and "no edge" in cad.last_reason(), cad.last_reason())
    # seam / tangent edges are skipped, not failures: a fillet's own edges
    rounded = det.soften(box, 2)
    s = det.soften(rounded, 0.5)
    check("soften: an all-rounded box has no sharp edge left (tangent edges skipped)",
          s.isSame(rounded) and "no sharp" in (cad.last_reason() or ""), cad.last_reason())
    msg = raises(det.soften, Part.makeBox(1, 1, 1).Faces[0], 0.2)
    check("soften: a face (no solid) raises", msg is not None and "no solid" in msg, msg)


@case
def t_soften_gate():
    # MEASURED (R232): window edges at r=1.5 on a 2 mm wall give an INVALID
    # makeFillet result WITHOUT an exception. soften must never return it.
    sh = open_box(80, 60, 30, 2)
    cutw = cad.cut(sh, [Part.makeBox(20, 6, 10, V(10 + 30 * i, -1, 8)) for i in range(2)])
    raw = cutw.makeFillet(1.5, det.new_edges(cutw, sh))
    check("soften gate: the raw makeFillet(1.5) really is invalid here", not raw.isValid())
    s = timed("soften window edges r=1.5 (ladder)",
              lambda: det.soften(cutw, 1.5, det.new_edges(cutw, sh)))
    check("soften gate: soften(1.5) returns a VALID single solid", ok_solid(s),
          (s.isValid(), len(s.Solids)))
    check("soften gate: ... with the windows' edges rounded (volume dropped)",
          s.Volume < cutw.Volume - 1.0, (cutw.Volume, s.Volume))


@case
def t_soften_partial():
    # A spline car body cut by two arches: fillet-all fails at every radius
    # (r2 gap 1); soften rounds most edges and leaves the rest sharp.
    pts = [V(0, 0, 5), V(5, 0, 16), V(35, 0, 20), V(55, 0, 32), V(95, 0, 33), V(120, 0, 22),
           V(140, 0, 18), V(142, 0, 6), V(140, 0, 0)]
    sp = Part.BSplineCurve()
    sp.interpolate(pts)
    side = Part.Face(Part.Wire([sp.toShape(), Part.makeLine(pts[-1], V(2, 0, 0)),
                                Part.makeLine(V(2, 0, 0), pts[0])])).extrude(V(0, 60, 0))
    side.translate(V(0, -30, 0))
    pp = [V(0, -24, 0), V(30, -30, 0), V(110, -30, 0), V(142, -25, 0), V(142, 25, 0),
          V(110, 30, 0), V(30, 30, 0), V(0, 24, 0)]
    plan = Part.Face(Part.makePolygon(pp + [pp[0]])).extrude(V(0, 0, 40))
    car = cad.cut(side.common(plan), [Part.makeCylinder(13, 80, V(x, -40, 3), V(0, 1, 0))
                                      for x in (28, 112)])
    whole = None
    try:
        whole = car.makeFillet(2.5, car.Edges)
    except Exception:                                   # noqa: BLE001
        pass
    check("soften partial: fillet-all r=2.5 fails on the cut car body",
          whole is None or not whole.isValid())
    t0 = time.time()
    s = det.soften(car, 2.5, budget_s=8)
    TIMES["soften car body partial"] = round(time.time() - t0, 3)
    check("soften partial: valid single solid", ok_solid(s))
    check("soften partial: some edges rounded (volume changed)", abs(s.Volume - car.Volume) > 1.0)
    check("soften partial: last_reason() names the edges left sharp",
          "stayed sharp" in (cad.last_reason() or ""), cad.last_reason())
    check("soften partial: within budget_s + one attempt (< 12 s)", time.time() - t0 < 12.0)


@case
def t_new_edges():
    box = Part.makeBox(30, 20, 10)
    c = cad.cut(box, Part.makeCylinder(2, 20, V(10, 10, -5)))
    ne = det.new_edges(c, box)
    kinds = sorted(type(e.Curve).__name__ for e in ne)
    check("new_edges: a through hole adds 2 circles + 1 seam line",
          kinds == ["Circle", "Circle", "Line"], kinds)
    # an old edge only shortened by the cut is NOT new
    c2 = cad.cut(box, Part.makeBox(4, 30, 4, V(13, -5, 8)))     # notch across the top
    ne2 = det.new_edges(c2, box)
    old_tops = [e for e in ne2 if abs(e.BoundBox.ZMin - 10) < 1e-6 and abs(e.BoundBox.ZMax - 10) < 1e-6
                and abs(e.BoundBox.YMin - e.BoundBox.YMax) < 1e-6]
    check("new_edges: the box's top edges the notch split stay old", not old_tops,
          [e.BoundBox for e in old_tops])
    # 3 lines on each end face, 2 along the notch floor, 2 where its walls
    # meet the top face
    check("new_edges: the notch made 10 new edges (3 + 3 + 2 + 2)",
          len(ne2) == 10, len(ne2))


# ------------------------------------------------------------- panel lines
@case
def t_groove_ring():
    box = Part.makeBox(40, 30, 20)
    s = timed("groove_ring box", lambda: det.groove_ring(box, "Z", 10, w=0.6, depth=0.5))
    # outer 40 x 30 minus the inward offset 39 x 29 (sharp corners), 0.6 tall
    check("groove_ring: removes (40*30 - 39*29) * 0.6 = 41.4 mm3",
          ok_solid(s) and near(box.Volume - s.Volume, 41.4, 1e-3), box.Volume - s.Volume)
    sh = open_box(40, 30, 20, 2)
    s2 = det.groove_ring(sh, "+Z", (0, 0, 12), w=0.6, depth=0.5)
    check("groove_ring: on a 2 mm walled box, the same 41.4 mm3, one solid",
          ok_solid(s2) and near(sh.Volume - s2.Volume, 41.4, 1e-3), sh.Volume - s2.Volume)
    msg = raises(det.groove_ring, sh, "Z", 12, 0.6, 2.5)
    check("groove_ring: depth 2.5 through a 2 mm wall raises naming the wall",
          msg is not None and "wall" in msg, msg)
    msg = raises(det.groove_ring, box, "Z", 50)
    check("groove_ring: a plane that misses the body raises", msg is not None, msg)


@case
def t_groove_outline():
    box = Part.makeBox(60, 40, 20)
    s = timed("groove_outline box both sides",
              lambda: det.groove_outline(box, [(10, 4), (50, 4), (50, 16), (10, 16)], "+Y"))
    # the band 0.6 wide round a 40 x 12 rectangle (outer offset has round
    # corners): (40*12 + 0.6*52 + pi*0.09) - 39.4*11.4, 0.5 deep, 2 sides
    band = (480 + 0.6 * 52 + PI * 0.09) - 39.4 * 11.4
    check("groove_outline: removes band(62.32 mm2) x 0.5 x 2 sides",
          ok_solid(s) and near(box.Volume - s.Volume, band * 0.5 * 2, 2e-3),
          (box.Volume - s.Volume, band))
    s1 = det.groove_outline(box, [(10, 4), (50, 4), (50, 16), (10, 16)], "+Y", both_sides=False)
    check("groove_outline: both_sides=False cuts the +Y side only",
          near(box.Volume - s1.Volume, band * 0.5, 2e-3)
          and near(box.common(Part.makeBox(60, 20, 20)).Volume,
                   s1.common(Part.makeBox(60, 20, 20)).Volume), box.Volume - s1.Volume)
    sh = open_box(60, 40, 20, 2)
    s2 = det.groove_outline(sh, [(10, 4), (50, 4), (50, 16), (10, 16)], "+Y")
    check("groove_outline: on a 2 mm shell it stays in the skin (same volume, 1 solid)",
          ok_solid(s2) and near(sh.Volume - s2.Volume, band * 0.5 * 2, 2e-3),
          sh.Volume - s2.Volume)
    msg = raises(det.groove_outline, sh, [(10, 4), (50, 4), (50, 16), (10, 16)], "+Y", 0.6, 1.8)
    check("groove_outline: depth 1.8 in a 2 mm wall raises naming the wall",
          msg is not None and "wall" in msg, msg)
    # curved: a cylinder seen from +X, the band follows the surface
    cyl = Part.makeCylinder(20, 40)
    s3 = det.groove_outline(cyl, [(-8, 10), (8, 10), (8, 30), (-8, 30)], "+X", both_sides=False)
    check("groove_outline: on a curved cylinder it removes ~band x depth (within 15%)",
          ok_solid(s3) and abs((cyl.Volume - s3.Volume) - ((16 * 20 + 0.3 * 72 + PI * 0.09)
                                                           - 15.4 * 19.4) * 0.5) < 0.15 *
          ((16 * 20 + 0.3 * 72 + PI * 0.09) - 15.4 * 19.4) * 0.5, cyl.Volume - s3.Volume)


# ---------------------------------------------------------------- grilles
HEX_A = math.sqrt(3) / 2 * 9.0          # a 3 mm across-flats hexagon


@case
def t_grille_flat():
    plate = Part.makeBox(60, 40, 2)
    s = timed("grille 37 hex on plate", lambda: det.grille(plate, (30, 20, 2), "+Z", (40, 30)))
    # lattice by hand (R236): rows dy = 4.5*sqrt(3)/2 = 3.897, |b| <= 13 - 1.732
    # -> 5 rows; even rows |a| <= 16.5 -> 7 holes, odd (offset 2.25) -> 8
    check("grille: 37 hexes through the 2 mm plate = 37 * 7.794 * 2 mm3",
          ok_solid(s) and near(plate.Volume - s.Volume, 37 * HEX_A * 2, 1e-4),
          plate.Volume - s.Volume)
    s = det.grille(plate, (30, 20, 2), "+Z", (40, 14), kind="slot", hole=1.5, pitch=3)
    obround = 1.5 * (10 - 1.5) + PI * 0.75 ** 2
    check("grille slot: 11 obround 1.5 x 10 slots through 2 mm",
          ok_solid(s) and near(plate.Volume - s.Volume, 11 * obround * 2, 1e-4),
          plate.Volume - s.Volume)
    s = det.grille(plate, (30, 20, 2), "+Z", 30, kind="round")
    # round area R = 13: rows j=0 (|a|<=11.5: 5... ) counted by hand below
    n = 0
    dy = 4.5 * math.sqrt(3) / 2
    for j in range(-4, 5):
        for i in range(-4, 5):
            a, b = i * 4.5 + (2.25 if j % 2 else 0), j * dy
            if math.hypot(a, b) + 1.5 <= 13 + 1e-9:
                n += 1
    check("grille round in a circle: %d holes of d3 through 2 mm" % n,
          ok_solid(s) and near(plate.Volume - s.Volume, n * PI * 2.25 * 2, 1e-4),
          (plate.Volume - s.Volume, n))
    s = timed("speaker_grille 95 holes", lambda: det.speaker_grille(plate, (30, 20, 2), "+Z", 30))
    # 1 + rings k=1..5 of round(2*pi*k) = 6, 13, 19, 25, 31 holes
    check("speaker_grille: 95 holes of d1.4 through 2 mm",
          ok_solid(s) and near(plate.Volume - s.Volume, 95 * PI * 0.49 * 2, 1e-4),
          plate.Volume - s.Volume)
    msg = raises(det.grille, plate, (30, 20, 2), "-Z", (40, 30))
    check("grille: `normal` pointing INTO the part (it would drill the far face) raises",
          msg is not None and "OUT" in msg, msg)
    s = det.grille(plate, (30, 20, 0), "-Z", (40, 30))
    check("grille: from the bottom face with normal -Z is fine (same 37 holes)",
          near(plate.Volume - s.Volume, 37 * HEX_A * 2, 1e-4))
    msg = raises(det.grille, plate, (30, 20, 2), "+Z", (40, 30), "hex", 3, 3.2)
    check("grille: a web under 0.6 mm raises", msg is not None and "web" in msg, msg)
    msg = raises(det.grille, plate, (130, 20, 2), "+Z", (40, 30))
    check("grille: an area off the part raises", msg is not None, msg)


@case
def t_grille_shell():
    sh = open_box(60, 40, 20, 2)
    s = timed("grille hex on shell wall",
              lambda: det.grille(sh, (30, 0, 10), "-Y", (40, 14), hole=3, pitch=4.5, margin=1))
    far = Part.makeBox(60, 20, 20, V(0, 20, 0))
    check("grille through='wall': the FAR wall is untouched",
          near(sh.common(far).Volume, s.common(far).Volume), s.common(far).Volume)
    removed = sh.Volume - s.Volume
    check("grille through='wall': removes whole hexes x 2 mm only",
          ok_solid(s) and abs(removed / (HEX_A * 2) - round(removed / (HEX_A * 2))) < 1e-3,
          removed / (HEX_A * 2))
    # curved: a tube r=20, wall 2; grille facing +X
    tube = Part.makeCylinder(20, 40).cut(Part.makeCylinder(18, 40))
    s = timed("grille hex on curved tube",
              lambda: det.grille(tube, (20, 0, 20), "+X", (24, 24), margin=1))
    farc = Part.makeBox(40, 40, 40, V(-40, -20, 0))
    check("grille on a curved tube: one valid solid, far side untouched",
          ok_solid(s) and near(tube.common(farc).Volume, s.common(farc).Volume))
    # 24 x 24 area, margin 1: |a| <= 9.5, |b| <= 9.27 -> rows of 5, 4, 5, 4, 5
    # = 23 holes; the curved wall is >= 2 mm thick along X, up to 12% more
    cnt = (tube.Volume - s.Volume) / (HEX_A * 2)
    check("grille on a curved tube: 23 holes through the wall (2 - 2.24 mm along X)",
          23 <= cnt <= 23 * 1.12, cnt)
    check("grille on a curved tube: the centre hole is open through the near wall",
          not s.isInside(V(19, 0, 20), 1e-6, True))


# ------------------------------------------------------------------ wheel
@case
def t_wheel():
    w = timed("wheel d40 block", lambda: det.wheel(40, 16, tread="block", bore=3, axis="+Y",
                                                   at=(10, 0, 20)))
    check("wheel: tyre, rim, cap", sorted(w) == ["cap", "rim", "tyre"], sorted(w))
    check("wheel: each one valid solid", all(ok_solid(w[k]) for k in w))
    bb = cad.measure(w["tyre"])
    check("wheel: tyre is d 40 (X, Z) x width 16 (Y), centred at `at`",
          near(bb["size"][0], 40, 2e-3) and near(bb["size"][2], 40, 2e-3)
          and near(bb["size"][1], 16, 2e-3) and near(bb["center_of_mass"][0], 10, 1e-3)
          and near(bb["center_of_mass"][2], 20, 1e-3), bb)
    for a, b in (("tyre", "rim"), ("rim", "cap"), ("tyre", "cap")):
        v = w[a].common(w[b]).Volume
        check("wheel: %s and %s do not overlap" % (a, b), v < 1e-3, v)
    check("wheel: the rim stays 0.1 mm inside the tyre bead (distance > 0.05)",
          w["tyre"].distToShape(w["rim"])[0] > 0.05, w["tyre"].distToShape(w["rim"])[0])
    check("wheel: the cap faces +Y (in front of the rim's centre)",
          w["cap"].BoundBox.Center.y > w["rim"].BoundBox.Center.y)
    bare = det.wheel(40, 16, tread=None, axis="+Y", at=(10, 0, 20))
    check("wheel: the block tread removes rubber", bare["tyre"].Volume - w["tyre"].Volume > 50,
          bare["tyre"].Volume - w["tyre"].Volume)
    check("wheel: the bore goes through (a point on the axis inside the hub is air)",
          not w["rim"].isInside(V(10, -3, 20), 1e-6, True))
    for tread, style in (("chevron", "bar"), ("rib", "window")):
        x = timed("wheel d40 %s %s" % (tread, style),
                  lambda: det.wheel(40, 16, tread=tread, spoke_style=style, spokes=6))
        check("wheel %s/%s: valid, no overlaps" % (tread, style),
              all(ok_solid(x[k]) for k in x) and x["tyre"].common(x["rim"]).Volume < 1e-3)
    msg = raises(det.wheel, 20, 8, rim_d=19.5)
    check("wheel: rim_d too close to d raises", msg is not None and "rim_d" in msg, msg)
    check("wheel: a block-tread wheel builds in < 6 s", TIMES["wheel d40 block"] < 6.0,
          TIMES["wheel d40 block"])


# ------------------------------------------------------------------- text
def _letters_area(text, size):
    font = os.path.join(App.getHomePath(), "fonts", "DejaVuSans.ttf")
    f = Part.makeFace([w for ch in Part.makeWireString(text, font, size) for w in ch],
                      "Part::FaceMakerBullseye")
    return f.Area


@case
def t_text():
    box = Part.makeBox(60, 40, 20)
    A = _letters_area("ATECH", 8)
    s = timed("text emboss flat", lambda: det.text(box, "ATECH", (30, 20, 20), "+Z", 8, depth=0.6))
    check("text emboss: adds letters' area x 0.6 mm, one solid",
          ok_solid(s) and near(s.Volume - box.Volume, A * 0.6, 1e-3), (s.Volume - box.Volume, A))
    check("text emboss: the letters stand 0.6 mm proud", near(s.BoundBox.ZMax, 20.6, 1e-4))
    s = det.text(box, "ATECH", (30, 0, 10), "-Y", 8, depth=0.5, mode="deboss")
    check("text deboss: removes letters' area x 0.5 mm",
          ok_solid(s) and near(box.Volume - s.Volume, A * 0.5, 1e-3), box.Volume - s.Volume)
    cyl = Part.makeCylinder(20, 40)
    s = timed("text emboss curved", lambda: det.text(cyl, "AI", (20, 0, 20), "+X", 8, depth=0.6))
    a2 = _letters_area("AI", 8)
    check("text emboss on a cylinder: ~area x 0.6 (within 10%), one solid",
          ok_solid(s) and abs((s.Volume - cyl.Volume) - a2 * 0.6) < 0.1 * a2 * 0.6,
          (s.Volume - cyl.Volume, a2 * 0.6))
    msg = raises(det.text, box, "ATECH", (30, 20, 20), "-Z", 8)
    check("text: a normal pointing into the part raises", msg is not None, msg)
    sh = open_box(60, 40, 20, 2)
    msg = raises(det.text, sh, "AB", (30, 0, 10), "-Y", 6, depth=1.8, mode="deboss")
    check("text deboss: 1.8 mm into a 2 mm wall raises", msg is not None and "wall" in msg, msg)


# ----------------------------------------------------------------- colour
@case
def t_color():
    check("color('rubber') is MATERIALS' ShapeColor",
          det.color("rubber") == tuple(det.MATERIALS["rubber"]["ShapeColor"]))
    check("color('#ff8000') -> (1, 0.502, 0)", det.color("#ff8000") == (1.0, 0.502, 0.0),
          det.color("#ff8000"))
    check("color((255, 0, 0)) -> (1, 0, 0)", det.color((255, 0, 0)) == (1.0, 0.0, 0.0))
    check("color('Toy Yellow') is case/space tolerant",
          det.color("Toy Yellow") == det.color("toy_yellow"))
    msg = raises(det.color, "plaid")
    check("color: an unknown name raises listing the names", msg is not None and "rubber" in msg,
          msg)
    check("transparency('glass') = 60, ('rubber') = 0",
          det.transparency("glass") == 60 and det.transparency("rubber") == 0)
    names = ("rubber", "glass", "chrome", "matte_white", "matte_black", "satin_grey",
             "signal_red", "toy_yellow", "led_white", "smoked", "wood", "brushed_alu",
             "soft_touch")
    check("MATERIALS has every agreed name", all(n in det.MATERIALS for n in names))
    check("every material colour is 3 floats in 0..1",
          all(len(m["ShapeColor"]) == 3 and all(0 <= c <= 1 for c in m["ShapeColor"])
              for m in det.MATERIALS.values()))


# ----------------------------------------------------------------- screws
@case
def t_screws():
    for kind in ("socket", "button", "csk_phillips", "pan_phillips"):
        s = det.screw(kind, "M3", 8)
        check("screw %s M3x8: one valid solid" % kind, ok_solid(s))
        bb = cad.measure(s)
        check("screw %s: the tip is 8 mm below `at`" % kind, near(bb["bbox_min"][2], -8, 1e-3),
              bb["bbox_min"])
        # shank diameter = 2.9 (0.1 undersize): section at z=-4
        sec = s.slice(V(0, 0, 1), -4.0)
        rad = max(e.Curve.Radius for w in sec for e in w.Edges if isinstance(e.Curve, Part.Circle))
        check("screw %s: shank is d - 0.1 = 2.9" % kind, near(rad, 1.45, 1e-6), rad)
    check("screw csk_phillips: the head top is flush at `at` (z max 0)",
          near(cad.measure(det.screw("csk_phillips"))["bbox_max"][2], 0.0, 1e-3))
    check("screw socket: head height k = 3 above `at`",
          near(cad.measure(det.screw("socket"))["bbox_max"][2], 3.0, 1e-3))
    s = det.screw("socket", "M4", 10, at=(5, 0, 0), axis="+X")
    bb = cad.measure(s)
    check("screw axis +X: runs from x=5-4 (head) to x=15 (tip)",
          near(bb["bbox_min"][0], 1.0, 1e-3) and near(bb["bbox_max"][0], 15.0, 1e-3), bb)
    msg = raises(det.screw, "socket", "M7")
    check("screw: unknown size raises", msg is not None and "M3" in msg, msg)


@case
def t_boss():
    sh = open_box(60, 40, 20, 2)
    s = timed("screw_boss", lambda: det.screw_boss(sh, (10, 10, 15), "-Z", "M3", ribs=4))
    check("screw_boss: one valid solid", ok_solid(s))
    added = s.Volume - sh.Volume
    col = PI * 3.3 ** 2 * 13 - PI * 1.5 ** 2 * 13
    check("screw_boss: adds at least the 6.6 x 13 column less its 3 mm pilot",
          added > col * 0.95, (added, col))
    check("screw_boss: the pilot is open down to the floor",
          not s.isInside(V(10, 10, 3), 1e-6, True) and not s.isInside(V(10, 10, 14), 1e-6, True))
    check("screw_boss: the floor under the pilot is intact", s.isInside(V(10, 10, 1), 1e-6, True))
    check("screw_boss: the column wall is material", s.isInside(V(12.6, 10, 8), 1e-6, True))
    check("screw_boss: the gusset reaches the -X wall 8 mm away",
          s.isInside(V(3.5, 10, 2.6), 1e-6, True))
    # a sloped roof: a half tube r 20 / 18 along Y, the boss hanging from
    # it at x = 10 (30 deg slope): the column's rim must stay inside the skin
    outer = Part.makeCylinder(20, 30, V(0, 0, 0), V(0, 1, 0)).common(
        Part.makeBox(50, 30, 25, V(-25, 0, 0)))
    tunnel = outer.cut(Part.makeCylinder(18, 30, V(0, 0, 0), V(0, 1, 0)))
    b = timed("screw_boss under a sloped roof", lambda: det.screw_boss(
        tunnel, (10, 15, 1), "+Z", "M3", ribs=0))
    check("screw_boss on a 30 deg roof: one valid solid", ok_solid(b))
    out = b.cut(outer).Volume
    check("screw_boss on a 30 deg roof: nothing pokes out of the roof", out < 1e-6, out)
    check("screw_boss on a 30 deg roof: the column (>= 10 mm, less its pilot) is added",
          b.Volume > tunnel.Volume + PI * (3.3 ** 2 - 1.5 ** 2) * 10, b.Volume - tunnel.Volume)
    check("screw_boss: the input case is untouched", near(tunnel.Volume, outer.Volume -
          PI * 18 ** 2 / 2 * 30, 1e-4) and not tunnel.isInside(V(500, 500, 500), 1e-6, True))
    msg = raises(det.screw_boss, sh, (10, 10, 1), "-Z")
    check("screw_boss: `at` inside material raises", msg is not None and "inside" in msg, msg)
    msg = raises(det.screw_boss, sh, (10, 10, 15), "+Z")
    check("screw_boss: an axis pointing away from the floor raises", msg is not None, msg)
    msg = raises(det.screw_boss, sh, (10, 10, 15), "-Z", "M3", 5)
    check("screw_boss: h too short for the floor raises", msg is not None and "reach" in msg, msg)


@case
def t_screw_through():
    sh = open_box(60, 40, 20, 2)
    lid = Part.makeBox(60, 40, 2, V(0, 0, 20))
    lid2, case2 = timed("screw_through", lambda: det.screw_through(lid, sh, (8, 8, 22), "M3"))
    check("screw_through: lid and case one valid solid each", ok_solid(lid2) and ok_solid(case2))
    check("screw_through: the lid is drilled at `at`", not lid2.isInside(V(8, 8, 21), 1e-6, True))
    check("screw_through: the countersink is 6.2 at the top (3.0 mm off axis is air)",
          not lid2.isInside(V(11.0, 8, 21.95), 1e-6, True)
          and lid2.isInside(V(11.3, 8, 21.95), 1e-6, True))
    check("screw_through: a boss stands under it", case2.isInside(V(10.6, 8, 12), 1e-6, True))
    check("screw_through: the boss top is 0.1 mm under the lid",
          near(case2.common(Part.makeBox(10, 10, 10, V(3, 3, 10))).BoundBox.ZMax, 19.9, 1e-3))
    scr = det.screw("csk_phillips", "M3", 10, at=(8, 8, 22), axis="-Z")
    # R444 / R500: the screw clears the lid's countersunk hole; in the case
    # it shares only the thread's annulus with the 0.85 d pilot it bites in
    # (shank d - 0.1 = 2.9 against the M3 pilot 2.5, over <= 10 mm, x 1.2
    # slack as atech_geom.THREAD_SLACK) - more would be the head or the
    # shank in solid material
    thread = PI * ((2.9 / 2) ** 2 - (det.pilot_d(3.0) / 2) ** 2) * 10 * 1.2
    v_lid, v_case = scr.common(lid2).Volume, scr.common(case2).Volume
    check("screw_through: the matching csk screw clears the lid and only bites its pilot",
          v_lid < 1e-3 and 1e-3 < v_case <= thread, (v_lid, v_case, thread))
    thin = Part.makeBox(60, 40, 1.2, V(0, 0, 20))
    msg = raises(det.screw_through, thin, sh, (8, 8, 21.2))
    check("screw_through: a 1.2 mm lid is too thin for an M3 csk head", msg is not None
          and "thin" in msg, msg)


# ---------------------------------------------------- caps, lenses, feet
@case
def t_caps():
    c = det.button_cap(8, 6, dome=0.5, flange=1.0, stem_d=2)
    bb = cad.measure(c)
    check("button_cap round: one valid solid", ok_solid(c))
    check("button_cap round: 10 wide at the flange, top at 6, stem to -2",
          near(bb["size"][0], 10, 1e-3) and near(bb["bbox_max"][2], 6, 1e-3)
          and near(bb["bbox_min"][2], -2, 1e-3), bb)
    c = det.button_cap((10, 6), 5, dome=0.4, flange=0.8, at=(0, 0, 3), axis="+Y")
    bb = cad.measure(c)
    check("button_cap rect: along +Y, 5 tall from y=0", ok_solid(c)
          and near(bb["bbox_max"][1], 5, 1e-3) and near(bb["bbox_min"][1], 0, 1e-3), bb)
    L = det.lens(5, 3, dome=0.8)
    Rs = (2.5 ** 2 + 0.8 ** 2) / (2 * 0.8)
    want = PI * 2.5 ** 2 * (3 - 0.8) + PI * 0.8 ** 2 * (3 * Rs - 0.8) / 3
    check("lens: cylinder + spherical cap, closed form", ok_solid(L) and near(L.Volume, want, 1e-4),
          (L.Volume, want))
    f = det.foot(10, 3, "cylinder")
    c_ = min(0.9, 0.75, 0.6)
    want = PI * 25 * 3 - c_ * c_ / 2 * 2 * PI * (5 - c_ / 3)
    check("foot cylinder: chamfered closed form", ok_solid(f) and near(f.Volume, want, 1e-4),
          (f.Volume, want))
    f = det.foot(10, 3, "dome", at=(1, 2, 3))
    rr = min(1.8, 2.25)
    want = PI * 25 * 3 - (1 - PI / 4) * rr * rr * 2 * PI * (5 - rr * (10 - 3 * PI) / (12 - 3 * PI))
    check("foot dome: filleted closed form (Pappus)", ok_solid(f) and near(f.Volume, want, 1e-3),
          (f.Volume, want))
    check("foot: its flat top is at `at`", near(cad.measure(f)["bbox_max"][2], 3, 1e-4))


@case
def t_opening():
    lid = Part.makeBox(60, 40, 2, V(0, 0, 20))
    cap = det.button_cap(8, 6, dome=0.5, flange=1.0, at=(30, 20, 16))
    s = timed("opening_for cap", lambda: det.opening_for(lid, cap, clearance=0.2, chamfer=0.3))
    hole = PI * 4.2 ** 2 * 2
    removed = lid.Volume - s.Volume
    check("opening_for: a d 8.4 opening (cap 8 + 2 x 0.2), plus the 0.3 chamfer",
          ok_solid(s) and hole < removed < hole + 2.0, (removed, hole))
    check("opening_for: the cap passes the lid without touching", cap.common(s).Volume < 1e-6)
    check("opening_for: the 10 mm flange did not set the size", removed < PI * 5.2 ** 2 * 2)
    bb = App.BoundBox(27, 18, 10, 33, 22, 15)
    s = det.opening_for(lid, bb, clearance=0.2, chamfer=0)
    # the 6 x 4 outline offset 0.2 (round corners): 24 + 0.2 * 20 + pi * 0.04
    check("opening_for a BoundBox: the 6 x 4 outline + 0.2 through 2 mm",
          near(lid.Volume - s.Volume, (24 + 0.2 * 20 + PI * 0.04) * 2, 1e-4),
          lid.Volume - s.Volume)
    # a rib under the lid that the cap's 10 mm flange runs into: the opening
    # cannot fix that, the gate must say so
    # beside the opening (x >= 34.5: clear of the 4.2 outline, inside the
    # 5 mm flange)
    ribbed = cad.fuse_one(lid, Part.makeBox(6.5, 40, 6.5, V(34.5, 0, 14)))
    msg = raises(det.opening_for, ribbed, cap, axis="+Z")
    check("opening_for: a cap whose flange runs into a rib raises", msg is not None
          and "still overlaps" in msg, msg)
    # R250: a rib INSIDE the outline would be cut 8 mm deep along the axis
    ribbed = cad.fuse_one(lid, Part.makeBox(7, 40, 6.5, V(33, 0, 14)))
    msg = raises(det.opening_for, ribbed, cap, axis="+Z")
    check("opening_for: a rib inside the outline raises (one wall only, R250)",
          msg is not None and "inside material" in msg, msg)
    msg = raises(det.opening_for, lid, Part.makeBox(2, 2, 2, V(100, 100, 100)), axis="+Z")
    check("opening_for: no wall in front raises", msg is not None, msg)


@case
def t_knurl():
    cyl = Part.makeCylinder(12, 15)
    s = timed("knurl straight 60", lambda: det.knurl(cyl, "Z", (0, 0, 0), 12, 1, 14, n=60,
                                                    depth=0.4))
    # 60 V grooves 90 deg, 0.4 deep: depth^2 each in section (flat approx), 13 long
    check("knurl straight: removes ~60 x 0.16 x 13 = 124.8 mm3 (within 3%)",
          ok_solid(s) and abs((cyl.Volume - s.Volume) - 124.8) < 0.03 * 124.8,
          cyl.Volume - s.Volume)
    s = timed("knurl diamond 40", lambda: det.knurl(cyl, "+Z", (0, 0, 0), 12, 1, 14, n=40,
                                                   kind="diamond"))
    check("knurl diamond: one valid solid", ok_solid(s))
    s = det.knurl(cyl, "Z", (0, 0, 0), 12, 1, 14, n=40, kind="rings")
    check("knurl rings: one valid solid, material removed", ok_solid(s) and s.Volume < cyl.Volume)
    msg = raises(det.knurl, cyl, "Z", (0, 0, 0), 10, 1, 14)
    check("knurl: a wrong r raises with the measured radius", msg is not None and "12" in msg, msg)
    msg = raises(det.knurl, cyl, "Z", (0, 0, 0), 12, 1, 14, n=200, depth=0.4)
    check("knurl: depth over half the pitch raises", msg is not None and "pitch" in msg, msg)


@case
def t_api():
    import ast
    with open(det.__file__.replace(".pyc", ".py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in det.__all__:
        if name == "MATERIALS":
            continue
        doc = " ".join((ast.get_docstring(fns[name]) or "").split("\n\n")[0].split())
        import re
        m = re.match(r"(.+?\.)(\s|$)", doc)
        first = m.group(1) if m else doc
        check("api: %s's first docstring sentence is <= 170 chars and whole" % name,
              0 < len(first) <= 170 and not first.endswith("..."), len(first))
    check("api: every __all__ name exists", all(hasattr(det, n) for n in det.__all__))


# ------------------------------------------------------------------ R250
CAR_SIDE = [(0, 6), (4, 15), (30, 20), (52, 31), (92, 32), (118, 22), (140, 18),
            ("corner", (143, 8)), ("line", (140, 0)), ("line", (3, 0))]
CAR_PLAN = [(0, -23), (30, -30), (110, -30), (143, -24), (143, 24), (110, 30),
            (30, 30), (0, 23)]
_CAR = []


def heavy(*gates):
    """A slow case (the hollow spline car, ~5 s to build): a sabotage run of
    an unrelated gate skips it, every other run does it."""
    def deco(fn):
        if SAB and SAB not in gates:
            print("SKIP %s (sabotage %s)" % (fn.__name__, SAB))
            return fn
        return case(fn)
    return deco


def car_shell():
    """The 143 mm spline car body hollowed t=2 with its exact core (built once)."""
    if not _CAR:
        b = form.profile_body(CAR_SIDE, CAR_PLAN, fillet=4)
        _CAR.append(form.hollow(b, 2, core=lambda t: form.profile_body(
            CAR_SIDE, CAR_PLAN, fillet=4, inset=t)))
    return _CAR[0]


def surface_y(shape, x, z, side):
    """y of the outer skin at (x, z), seen from side -1 (-Y) or +1 (+Y)."""
    o = V(x, 100 * side, z)
    t_in = [r for r in det._rays(shape, [o], V(0, -side, 0), 300)[0] if r[1] > 0][0][0]
    return 100 * side - side * t_in


def air(s, p):
    return not s.isInside(V(*p), 1e-6, True)


def solid_at(s, p):
    return s.isInside(V(*p), 1e-6, True)


@case
def t_r250_section_offsets():
    # MEASURED (R250): Part.Face(wire.makeOffset2D(..)) of EVERY car slice
    # tried was INVALID, and at x = 71.64 the inward one did not shrink at
    # all (groove_ring: "section too small"). The section is convex, so the
    # inner parallel face has the Steiner area A - L d + pi d^2.
    b = form.profile_body(CAR_SIDE, CAR_PLAN, fillet=4)
    for ax, d0 in (("X", 71.64), ("Z", 10.32), ("Y", 0.13)):
        a = {"X": V(1, 0, 0), "Y": V(0, 1, 0), "Z": V(0, 0, 1)}[ax]
        w = b.slice(a, d0)[0]
        A, L = Part.Face(w).Area, w.Length
        f = det._inset(w, 0.5)
        want = A - L * 0.5 + PI * 0.25
        check("R250 _inset: car slice %s=%g gives a VALID face of area A - L d + pi d^2"
              % (ax, d0), f is not None and f.isValid() and near(f.Area, want, 2e-3),
              None if f is None else (f.isValid(), f.Area, want))
        g = det._outset(w, 2.0)
        want = A + L * 2.0 + PI * 4.0
        check("R250 _outset: car slice %s=%g gives a VALID face of area A + L d + pi d^2"
              % (ax, d0), g is not None and g.isValid() and near(g.Area, want, 2e-3),
              None if g is None else (g.isValid(), g.Area, want))
    y = surface_y(b, 71.64, 12, -1)
    gr = timed("R250 groove_ring car x=71.64", lambda: det.groove_ring(b, "X", 71.64))
    check("R250 groove_ring car x=71.64: cut, one valid solid",
          ok_solid(gr) and air(gr, (71.64, y + 0.25, 12)))


@heavy("offset", "probe")
def t_r250_groove_ring_spline():
    # MEASURED (R250): the slice's makeOffset2D face was INVALID (29
    # OffsetCurve edges) and cad.cut's volume test said "removed nothing"
    # on the hollow car, the solid car and its split halves
    h = car_shell()
    y = surface_y(h, 70, 12, -1)
    g = timed("R250 groove_ring hollow spline car", lambda: det.groove_ring(h, "Z", 12))
    check("R250 groove_ring car: one valid solid", ok_solid(g))
    check("R250 groove_ring car: air 0.25 mm under the skin in the groove (z=12)",
          air(g, (70, y + 0.25, 12)))
    check("R250 groove_ring car: still material 0.8 mm under the skin (depth 0.5)",
          solid_at(g, (70, y + 0.8, 12)))
    check("R250 groove_ring car: still material beside the 0.6 band (z=12.5)",
          solid_at(g, (70, y + 0.25, 12.5)))
    lo, up = form.split(h, "Z", at=12)
    y2 = surface_y(up, 70, 20, -1)
    g2 = timed("R250 groove_ring split upper", lambda: det.groove_ring(up, "Z", 20))
    check("R250 groove_ring on a split (open) half: cut there, one valid solid",
          ok_solid(g2) and air(g2, (70, y2 + 0.25, 20)) and solid_at(g2, (70, y2 + 0.8, 20)))


@heavy("offset", "probe", "breach")
def t_r250_groove_outline_minus_y():
    h = car_shell()
    pts = [(40, 8), (90, 8), (90, 22), (40, 22)]
    ym, yp = surface_y(h, 65, 8, -1), surface_y(h, 65, 8, 1)
    g = timed("R250 groove_outline -Y on the car", lambda: det.groove_outline(
        h, pts, view="-Y", both_sides=False))
    check("R250 groove_outline -Y: one valid solid", ok_solid(g))
    check("R250 groove_outline -Y: the -Y skin is grooved 0.5 deep at the outline",
          air(g, (65, ym + 0.25, 8)) and solid_at(g, (65, ym + 0.8, 8)))
    check("R250 groove_outline -Y: both_sides=False leaves the +Y skin whole",
          solid_at(g, (65, yp - 0.25, 8)))
    g2 = det.groove_outline(h, pts, view="+Y", both_sides=True)
    check("R250 groove_outline +Y both sides: both skins grooved",
          ok_solid(g2) and air(g2, (65, ym + 0.25, 8)) and air(g2, (65, yp - 0.25, 8)))


@case
def t_r250_cut_probed_gate():
    box = Part.makeBox(20, 20, 20)
    far = Part.makeBox(2, 2, 2, V(18.5, 18.5, 18.5))       # clips a far corner only
    msg = raises(det._cut_probed, box, [far], [V(10, 0.25, 10)], "probe test")
    check("R250 _cut_probed: a cut that misses every probe point raises",
          msg is not None and "probe" in msg, msg)
    near_ = Part.makeBox(4, 1, 4, V(8, -0.5, 8))
    s = det._cut_probed(box, [near_], [V(10, 0.25, 10)], "probe test")
    check("R250 _cut_probed: a cut through the probe passes",
          ok_solid(s) and air(s, (10, 0.25, 10)))


def closed_box(x, y, z, t):
    return Part.makeBox(x, y, z).cut(Part.makeBox(x - 2 * t, y - 2 * t, z - 2 * t, V(t, t, t)))


@case
def t_r250_opening_default_axis():
    bx = closed_box(100, 60, 40, 2)                         # front wall y 0..2
    lens = det.lens(10, 6, at=(50, 4, 20), axis="-Y")       # y 4 -> -2: through it
    hole = PI * 5.2 ** 2 * 2
    s = timed("R250 opening_for lens, no axis", lambda: det.opening_for(bx, lens))
    rem = bx.Volume - s.Volume
    check("R250 opening_for: no axis -> the lens's own -Y: one d 10.4 hole in ONE wall",
          ok_solid(s) and hole < rem < hole + 3.0, (rem, hole))
    moved = lens.copy()
    moved.translate(V(0, 0, 1))                             # forgets its axis
    s = det.opening_for(bx, moved)
    rem = bx.Volume - s.Volume
    check("R250 opening_for: a moved lens -> the nearest whole wall, still -Y",
          ok_solid(s) and hole < rem < hole + 3.0, (rem, hole))
    msg = raises(det.opening_for, bx, lens, axis="+X")
    check("R250 opening_for: an axis ALONG the wall the lens sits in raises",
          msg is not None and "inside material" in msg, msg)
    # a cap low in a tall box, 6 mm from a side wall: the nearest wall is the
    # side one; the cap was built to look up (+Z) through the lid
    tall = closed_box(60, 30, 40, 2)
    cap = det.button_cap(6, 6, dome=0.5, flange=1.0, at=(8, 15, 10))
    s = det.opening_for(tall, cap)
    check("R250 opening_for: a cap opens the lid it was built to look through",
          ok_solid(s) and air(s, (8, 15, 39)) and solid_at(s, (1, 15, 13)))


@case
def t_r250_opening_module_working_face():
    projects = os.path.normpath(os.path.join(HERE, "..", "..", "..", "projects"))
    if projects not in sys.path:
        sys.path.append(projects)
    try:
        import atech_ports as ap
        doc = App.newDocument("r250_opening_module")
        ap.board_object(doc)
        btn = ap.seat(doc, "button", 3)
    except Exception as exc:                            # noqa: BLE001
        print("SKIP R250 opening_for module: no Atech library here (%s)" % exc)
        return
    b = ap.bbox(btn)
    a, how = det._module_axis(btn)
    check("R250 _module_axis: a seated button works through +Y here (its 'up')",
          a is not None and (a - V(0, 1, 0)).Length < 1e-6, (a, how))
    # an L of two plates: the top plate 20 mm in front of the working face,
    # a side plate only 1 mm off its -X side (the NEAREST wall)
    top = Part.makeBox(b.XLength + 20, 2, b.ZLength + 20, V(b.XMin - 10, b.YMax + 20, b.ZMin - 10))
    side = Part.makeBox(2, b.YLength + 30, b.ZLength + 20, V(b.XMin - 3, b.YMin - 5, b.ZMin - 10))
    wall = cad.fuse_one(top, side)
    s = det.opening_for(wall, btn, clearance=0.2, chamfer=0)
    cx, cz = (b.XMin + b.XMax) / 2, (b.ZMin + b.ZMax) / 2
    check("R250 opening_for(module): the opening is in front of its working face",
          ok_solid(s) and air(s, (cx, b.YMax + 21, cz)), how)
    check("R250 opening_for(module): the nearer side plate is untouched",
          solid_at(s, (b.XMin - 2, (b.YMin + b.YMax) / 2, cz)))


@case
def t_r250_screw_through_long_column():
    case_ = open_box(60, 40, 40, 2)
    lid = Part.makeBox(60, 40, 2, V(0, 0, 40))
    lid2, c2 = timed("R250 screw_through 37 mm column", lambda: det.screw_through(
        lid, case_, (30, 20, 42), "M3"))
    add = c2.cut(case_)
    ext = max(abs(add.BoundBox.XMin - 30), abs(add.BoundBox.XMax - 30),
              abs(add.BoundBox.YMin - 20), abs(add.BoundBox.YMax - 20))
    # od/2 + max(2, 2 d) = 3.3 + 6; the old reach was 3.3 + 0.8 x 13 = 13.7
    check("R250 screw_through: gussets on a 37 mm column reach <= 3.3 + 6 mm",
          ok_solid(c2) and ext <= 9.3 + 1e-3, ext)
    lid3, c3 = det.screw_through(lid, case_, (30, 20, 42), "M3", ribs=0)
    add = c3.cut(case_)
    ext = max(abs(add.BoundBox.XMin - 30), abs(add.BoundBox.XMax - 30))
    check("R250 screw_through ribs=0: a plain 6.6 mm column", ok_solid(c3) and ext <= 3.3 + 1e-3,
          ext)
    lid4, c4 = det.screw_through(lid, case_, (30, 20, 42), "M3", rib_len=3)
    add = c4.cut(case_)
    ext = max(abs(add.BoundBox.XMin - 30), abs(add.BoundBox.XMax - 30))
    check("R250 screw_through rib_len=3: gussets 3 mm out", ok_solid(c4) and ext <= 6.3 + 1e-3,
          ext)
    check("R250 screw_through: ribs=-1 raises",
          raises(det.screw_through, lid, case_, (30, 20, 42), "M3", ribs=-1))


print("TIMES " + " ".join("%s=%.2fs" % (k.replace(" ", "_"), v) for k, v in TIMES.items()))
# ------------------------------------------------------------------ R270
HEART = [("corner", (0, -10)), (5, -5), (9, 0), (10, 4), (8.5, 8), (5, 9.5), (1.8, 8.4),
         (0.4, 6.4), ("corner", (0, 5)), (-0.4, 6.4), (-1.8, 8.4), (-5, 9.5), (-8.5, 8),
         (-10, 4), (-9, 0), (-5, -5)]
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


def r270(*gates):
    def deco(fn):
        if SAB and SAB not in gates:
            print("SKIP %s (sabotage %s)" % (fn.__name__, SAB))
            return fn
        return case(fn)
    return deco


@r270("cusp")
def t_r270_inlay_heart():
    box = open_box(60, 40, 30, 2)                  # front wall y = 0..2
    w = form.spline_wire(HEART, plane="XZ")
    w.translate(V(30, 0, 15))
    f = Part.Face(w)
    res, ins = timed("R270 inlay heart", lambda: det.inlay(box, w, flange=1.0))
    check("R270 inlay: the box stays one valid solid", ok_solid(res))
    check("R270 inlay: the pocket goes through the 2 mm wall: heart area x 2 removed",
          near(box.Volume - res.Volume, 2.0 * f.Area, 2e-2), (box.Volume - res.Volume,
                                                             2.0 * f.Area))
    check("R270 inlay: the insert is one valid solid", ok_solid(ins))
    check("R270 inlay: the insert does not overlap the box", ins.common(res).Volume < 1e-3)
    check("R270 inlay: the insert is flush with the outer face (y = 0)",
          abs(ins.BoundBox.YMin) < 1e-6, ins.BoundBox.YMin)
    check("R270 inlay: a flange sits behind the wall (y > 2)",
          ins.BoundBox.YMax > 2.0 + 0.5 and solid_at(ins, (30, 2.4, 15 - 9.9)),
          ins.BoundBox.YMax)
    check("R270 inlay: the flange is 1 mm wider than the heart all round",
          ins.BoundBox.XLength > f.BoundBox.XLength + 1.9, (ins.BoundBox.XLength,
                                                            f.BoundBox.XLength))
    check("R270 inlay: air through the wall at the heart's centre",
          air(res, (30, 1.0, 15)))


_R1_SHELL = []


def r1_shell():
    if not _R1_SHELL:
        b = form.profile_body(R1_CAR_SIDE, R1_CAR_PLAN, fillet=(5, 0))
        _R1_SHELL.append(form.hollow(b, 2.0))
    return _R1_SHELL[0]


@r270("local")
def t_r270_opening_local():
    h = r1_shell()
    lens = det.lens(12, 6, 1.0, at=(160.0, 20.0, 35.0), axis="+X")
    seen = []
    real_rays = det._rays

    def spy(shape, origins, d, length):
        seen.append(shape.BoundBox.DiagonalLength)
        return real_rays(shape, origins, d, length)
    det._rays = spy
    t0 = time.time()
    try:
        res = det.opening_for(h, lens)
    finally:
        det._rays = real_rays
    dt = time.time() - t0
    TIMES["R270 opening_for on the round-1 car shell"] = round(dt, 3)
    # MEASURED (an earlier build of this shell): 23.4 s on the whole shell,
    # 22.0 s of it the rays; 1.3 s on the local region
    check("R270 opening_for: every ray batch runs on the LOCAL region (its box under "
          "half the shell's)", seen and max(seen) < 0.5 * h.BoundBox.DiagonalLength,
          (seen, h.BoundBox.DiagonalLength))
    check("R270 opening_for on a spline shell: under 6 s", dt < 6.0, dt)
    check("R270 opening_for: one valid shell, the lens clear of it",
          ok_solid(res) and lens.common(res).Volume < 1e-3)
    check("R270 opening_for: air in the wall in front of the lens",
          air(res, (det._c()._tight_bbox(h).XMax - 1.0, 20.0, 35.0)) or air(
              res, (170.0, 20.0, 35.0)))


class _Hang(object):
    """A shape stand-in whose makeFillet hangs (OCCT did, 126 s, MEASURED)."""

    def __init__(self, s):
        self.s = s

    def makeFillet(self, r, es):
        time.sleep(form.GUARD_S + 6.0)
        return self.s.makeFillet(r, es)


@r270("guard")
def t_r270_soften_guard():
    box = Part.makeBox(10, 10, 10)
    t0 = time.time()
    res, why = det._try_fillet_timed(_Hang(box), box.Edges, 1.0, "hang")
    dt = time.time() - t0
    check("R270 soften: a hung makeFillet is killed at atech_form.GUARD_S, not waited out",
          res is None and dt < form.GUARD_S + 3.0 and "killed" in str(why), (why, dt))


print("ATECH_DETAIL_TESTS=%d" % len(FAIL))
sys.stdout.flush()
os._exit(0)
