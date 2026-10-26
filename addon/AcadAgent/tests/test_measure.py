"""W3 measurement and inspection (R300-R316): acadagent/measure.py and
acadagent/inspect_tools.py.

    cd addon/AcadAgent/tests && python3 -m unittest test_measure
    QT_QPA_PLATFORM=offscreen "<app>/Contents/Resources/bin/python" -m unittest test_measure

The geometry core runs inside the bundled freecadcmd (PROBE below, written
to a temp file): every expected number is a CLOSED FORM worked out here
(box, cylinder, tube and sphere distances, angles, radii, volumes, wall
thicknesses, overlap volumes, margins, cap areas), checked to 0.01 mm.
Each CHECK line is PASS or FAIL; the run ends with W3_FAILS=<n>.

Sabotage (MeasureSabotage): a copy of the package with ONE line broken
(the dX component, a density, the thin-wall limit, a link to the measured
part, the element re-match after a rebuild, Show all's consumed-input rule)
must turn the matching check to FAIL - proof each check can fail. The real
files are never edited. The Qt card and button run in plain offscreen Qt
(no FreeCAD GUI: an offscreen GUI has no OpenGL) with a stub session.
Skips without freecadcmd (set ATECH_FREECADCMD) or without PySide6.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
PKG = os.path.join(ADDON, "acadagent")
KIT = os.path.join(PKG, "agent_kit")
REPO = os.path.normpath(os.path.join(ADDON, "..", ".."))
sys.path.insert(0, ADDON)


def _find_fc():
    cands = [os.environ.get("ATECH_FREECADCMD"),
             os.path.join(REPO, "dist", "build-macos-arm64", "Atech Atelier.app",
                          "Contents", "Resources", "bin", "freecadcmd"),
             os.path.join(REPO, "dist", "build", "squashfs-root", "usr", "bin", "freecadcmd"),
             shutil.which("freecadcmd")]
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


FC = _find_fc()

PROBE = r'''
import json, math, os, sys, time, traceback
sys.dont_write_bytecode = True
sys.path.insert(0, os.environ["W3_ADDON"])
import FreeCAD as App, Part, Mesh
from acadagent import measure as m
from acadagent import inspect_tools as it
m.KIT_DIR = os.environ["W3_KIT"]
FAILS = [0]
TOL = 0.01

def check(name, ok, detail=""):
    if not ok:
        FAILS[0] += 1
    print("CHECK %s %s %s" % (name, "PASS" if ok else "FAIL", detail))

def near(a, b, tol=TOL):
    return a is not None and abs(float(a) - float(b)) <= tol

def run(name, fn):
    try:
        fn()
    except Exception:
        check(name, False, traceback.format_exc().replace("\n", " | "))

V = App.Vector
doc = App.newDocument("w3")

def part(label, shape):
    o = doc.addObject("Part::Feature", label)
    o.Label = label
    o.Shape = shape
    return o

def face_at(obj, pt):
    vx = Part.Vertex(V(*pt))
    i = min(range(len(obj.Shape.Faces)), key=lambda k: obj.Shape.Faces[k].distToShape(vx)[0])
    return "Face%d" % (i + 1)

def edge_where(shape, pred):
    for i, e in enumerate(shape.Edges):
        if pred(e):
            return "Edge%d" % (i + 1)
    raise AssertionError("no such edge")

# ---------------------------------------------------------------- distance
def t_distance():
    a = Part.makeBox(10, 10, 10)
    b = Part.makeBox(10, 10, 10, V(15, 3, 4))
    r = m.distance(a, b)
    check("distance_faces", near(r["mm"], 5) and near(r["dx"], 5) and near(r["dy"], 0)
          and near(r["dz"], 0), r)
    r = m.distance(Part.Vertex(V(0, 0, 0)), Part.Vertex(V(3, 4, 12)))
    check("distance_points", near(r["mm"], 13) and near(r["dx"], 3) and near(r["dy"], 4)
          and near(r["dz"], 12), r)
    c = Part.makeBox(10, 10, 10, V(15, 20, 0))
    r = m.distance(a, c)
    check("distance_edges", near(r["mm"], math.hypot(5, 10)) and near(r["dx"], 5)
          and near(r["dy"], 10) and near(r["dz"], 0), r)
    cyl = Part.makeCylinder(5, 10, V(30, 0, 0))
    r = m.distance(a, cyl)
    check("distance_box_cylinder", near(r["mm"], 15), r)
    # through picks on document objects
    A = part("BlockA", a); B = part("BlockB", b); doc.recompute()
    r = m.measure("distance", [m.Pick(A, face_at(A, (10, 5, 5)), (10, 5, 5)),
                               m.Pick(B, face_at(B, (15, 8, 9)), (15, 8, 9))], doc)
    check("distance_picks", near(r["mm"], 5) and near(r["dx"], 5), r)
    t0 = time.time()
    for _ in range(20):
        m.measure("distance", [m.Pick(A, "Face2", None), m.Pick(B, "Face1", None)], doc)
    ms = (time.time() - t0) / 20 * 1000
    check("distance_under_200ms", ms < 200, "%.1f ms" % ms)

# ---------------------------------------------------------------- angle
def t_angle():
    l1 = Part.LineSegment(V(0, 0, 0), V(10, 0, 0)).toShape()
    l2 = Part.LineSegment(V(0, 0, 0), V(10 * math.cos(math.radians(30)),
                                           10 * math.sin(math.radians(30)), 0)).toShape()
    r = m.angle(l1, l2)
    check("angle_lines_30", near(r["deg"], 30) and near(r["between"], 30), r)
    l3 = Part.LineSegment(V(10, 0, 0), V(0, 0, 0)).toShape()
    r = m.angle(l2, l3)
    check("angle_lines_150_is_30", near(r["deg"], 30) and near(r["between"], 150), r)
    box = Part.makeBox(10, 10, 10)
    r = m.angle(box.Faces[0], box.Faces[4])
    check("angle_faces_90", near(r["deg"], 90), r)
    # a 20 deg wedge: the sloped face against the base
    w = Part.makePolygon([V(0, 0, 0), V(10, 0, 0), V(10, 0, 10 * math.tan(math.radians(20))),
                          V(0, 0, 0)])
    wedge = Part.Face(w).extrude(V(0, 5, 0))
    base = [f for f in wedge.Faces if abs(f.CenterOfMass.z) < 1e-6 and abs(f.Area - 50) < 1e-6][0]
    slope = max(wedge.Faces, key=lambda f: f.Area)
    r = m.angle(base, slope)
    check("angle_wedge_20", near(r["deg"], 20), r)
    try:
        m.angle(Part.makeSphere(3).Faces[0], box.Faces[0])
        check("angle_bad_pick_says_so", False)
    except m.MeasureError as e:
        check("angle_bad_pick_says_so", "flat" in str(e), str(e))

# ---------------------------------------------------------------- radius
def t_radius():
    cyl = Part.makeCylinder(5, 10)
    circ = [e for e in cyl.Edges if e.Curve.__class__.__name__ == "Circle"][0]
    r = m.radius(circ)
    check("radius_circle_edge", near(r["radius"], 5) and near(r["diameter"], 10), r)
    side = [f for f in cyl.Faces if f.Surface.__class__.__name__ == "Cylinder"][0]
    r = m.radius(side)
    check("radius_cylinder_face", near(r["radius"], 5), r)
    r = m.radius(Part.makeSphere(7).Faces[0])
    check("radius_sphere", near(r["radius"], 7) and near(r["diameter"], 14), r)
    arc = Part.ArcOfCircle(Part.Circle(V(1, 2, 0), V(0, 0, 1), 12.5), 0, 1.0).toShape()
    r = m.radius(arc)
    check("radius_arc", near(r["radius"], 12.5) and r["center"] == [1.0, 2.0, 0.0], r)

# ---------------------------------------------------------------- size
def t_size():
    r = m.size([Part.makeBox(10, 20, 30)])
    check("size_box", near(r["x"], 10) and near(r["y"], 20) and near(r["z"], 30), r)
    r = m.size([Part.makeCylinder(5, 10)])
    check("size_cylinder_tight", near(r["x"], 10) and near(r["y"], 10) and near(r["z"], 10), r)
    r = m.size([Part.makeBox(10, 10, 10), Part.makeBox(5, 5, 5, V(20, -5, 2))])
    check("size_union", near(r["x"], 25) and near(r["y"], 15) and near(r["z"], 10), r)
    s = Part.makeSphere(4)
    s.rotate(V(0, 0, 0), V(1, 1, 0), 33)
    r = m.size([s])
    check("size_sphere_rotated", near(r["x"], 8) and near(r["y"], 8) and near(r["z"], 8), r)

# ---------------------------------------------------------------- mass
def t_mass():
    b = Part.makeBox(10, 20, 30)          # 6000 mm3 = 6 cm3
    for mat, rho in (("PLA", 1.24), ("PETG", 1.27), ("ABS", 1.04), ("TPU", 1.21)):
        r = m.mass([b], mat)
        check("mass_box_%s" % mat, near(r["volume_mm3"], 6000) and near(r["grams"], 6 * rho, 1e-6),
              r)
    r = m.mass([Part.makeCylinder(5, 10)], "PLA")
    check("mass_cylinder", near(r["volume_mm3"], 250 * math.pi) and
          near(r["grams"], 0.25 * math.pi * 1.24, 1e-3), r)
    try:
        m.mass([b], "Wood")
        check("mass_unknown_material", False)
    except m.MeasureError:
        check("mass_unknown_material", True)

# ---------------------------------------------------------------- wall
def t_wall():
    shell = Part.makeBox(20, 20, 20).cut(Part.makeBox(16, 16, 16, V(2, 2, 2)))
    r = m.wall_at(shell, (0, 10, 10))
    check("wall_box_2mm", near(r["mm"], 2) and r["thin"] is False, r)
    r = m.wall_at(shell, (2, 10, 10))           # from the inside face
    check("wall_box_inner_face", near(r["mm"], 2), r)
    thin = Part.makeBox(20, 20, 20).cut(Part.makeBox(18.8, 18.8, 18.8, V(0.6, 0.6, 0.6)))
    r = m.wall_at(thin, (10, 0, 10))
    check("wall_thin_red", near(r["mm"], 0.6) and r["thin"] is True, r)
    tube = Part.makeCylinder(10, 10).cut(Part.makeCylinder(8.5, 10))
    r = m.wall_at(tube, (10, 0, 5))
    check("wall_tube_outer", near(r["mm"], 1.5), r)
    p = (8.5 * math.cos(1), 8.5 * math.sin(1), 5)
    r = m.wall_at(tube, p)
    check("wall_tube_inner", near(r["mm"], 1.5), r)
    plate = Part.makeBox(30, 30, 3)
    r = m.wall_at(plate, (15, 15, 3))
    check("wall_plate_top", near(r["mm"], 3) and r["dir"] == [0.0, 0.0, -1.0], r)
    T = part("Tube", tube); doc.recompute()
    r = m.measure("wall", [m.Pick(T, face_at(T, (10, 0, 5)), (10, 0, 5))], doc)
    check("wall_pick", near(r["mm"], 1.5), r)

# ---------------------------------------------------------------- interference
def t_interference():
    items = [{"label": "A", "shape": Part.makeBox(10, 10, 10)},
             {"label": "B", "shape": Part.makeBox(10, 10, 10, V(5, 0, 0))},
             {"label": "C", "shape": Part.makeBox(4, 4, 4, V(30, 0, 0))}]
    r = m.interference(items)
    p = r["pairs"]
    check("interference_one_pair", len(p) == 1 and {p[0]["a"], p[0]["b"]} == {"A", "B"}
          and near(p[0]["volume_mm3"], 500), r)
    items[1]["shape"] = Part.makeBox(10, 10, 10, V(10, 0, 0))     # touching only
    r = m.interference(items)
    check("interference_touching_is_none", r["pairs"] == [], r)
    s1 = Part.makeSphere(5)
    s2 = Part.makeSphere(5, V(6, 0, 0))
    # lens volume of two r=5 spheres 6 apart: pi*(4r+d)(2r-d)^2/12
    lens = math.pi * (4 * 5 + 6) * (2 * 5 - 6) ** 2 / 12
    r = m.interference([{"label": "S1", "shape": s1}, {"label": "S2", "shape": s2}])
    check("interference_sphere_lens", len(r["pairs"]) == 1 and
          near(r["pairs"][0]["volume_mm3"], lens), r)

# ---------------------------------------------------------------- fit
def t_fit():
    d2 = App.newDocument("w3fit")
    case = d2.addObject("Part::Feature", "Case")
    case.Shape = Part.makeBox(50, 40, 20, V(-25, -20, 0)).cut(
        Part.makeBox(46, 36, 18, V(-23, -18, 2)))
    board = d2.addObject("Mesh::Feature", "Board")
    board.Mesh = Mesh.createBox(40, 30, 2)
    board.Placement.Base = V(0, 0, 5)
    board.addProperty("App::PropertyString", "AtechRole", "Atech", "")
    board.AtechRole = "board"
    d2.recompute()
    r = m.measure("fit", [], d2)
    mm = r["margins"][0]["mm"]
    want = {"-x": 5, "+x": 5, "-y": 5, "+y": 5, "-z": 4, "+z": 14}
    check("fit_margins", r["margins"][0]["part"] == "Case" and
          all(near(mm[k], v) for k, v in want.items()), mm)
    head, _d = m.describe(r)
    check("fit_headline", head == "Fits, 4.0 mm to spare", head)
    board.Placement.Base = V(10, 0, 5)
    d2.recompute()
    r = m.measure("fit", [], d2)
    head, _d = m.describe(r)
    check("fit_sticks_out", near(r["margins"][0]["mm"]["+x"], -5) and head.startswith("Sticks out by 5.0"),
          head)
    App.closeDocument("w3fit")

# ---------------------------------------------------------------- section
def t_section():
    caps = m.section_caps([("B", Part.makeBox(10, 20, 30))], "Z", 5)
    check("section_box_cap", len(caps) == 1 and near(caps[0][1].Area, 200), caps and caps[0][1].Area)
    shell = Part.makeBox(20, 20, 20).cut(Part.makeBox(16, 16, 16, V(2, 2, 2)))
    caps = m.section_caps([("S", shell)], "X", 10)
    check("section_shell_ring", len(caps) == 1 and near(caps[0][1].Area, 400 - 256),
          caps and caps[0][1].Area)
    caps = m.section_caps([("S", shell)], "Z", 50)
    check("section_outside_empty", caps == [], caps)
    cut = m.cut_solid(Part.makeBox(10, 20, 30), "Z", 5)
    check("section_cut_below", near(cut.Volume, 1000) and near(cut.BoundBox.ZMax, 5), cut.Volume)
    cut = m.cut_solid(Part.makeBox(10, 20, 30), "Y", 5, flip=True)
    check("section_cut_flip", near(cut.Volume, 4500) and near(cut.BoundBox.YMin, 5), cut.Volume)
    n, d = m.clip_plane("Z", 5)
    keeps = lambda p: sum(n[i] * p[i] for i in range(3)) >= d
    check("section_clip_keeps_below", keeps((0, 0, 4)) and not keeps((0, 0, 6)), (n, d))
    n, d = m.clip_plane("Z", 5, flip=True)
    check("section_clip_flip", keeps((0, 0, 6)) and not keeps((0, 0, 4)), (n, d))
    check("section_range", m.section_range([shell], "Z") == (0.0, 20.0))
    from pivy import coin
    class FakeView(object):
        def __init__(self):
            self.root = coin.SoSeparator()
            self.root.addChild(coin.SoCube())
        def getSceneGraph(self):
            return self.root
    fv = FakeView()
    sv = m._SectionView()
    ok = sv.apply("Z", 10, False, m.section_caps([("S", shell)], "Z", 10), {}, view=fv)
    r = fv.root
    check("section_coin_graph", ok and r.getNumChildren() == 3 and r.findChild(sv.caps) == 0
          and r.findChild(sv.clip) == 1 and sv.caps.getNumChildren() == 1,
          r.getNumChildren())
    pl = sv.clip.plane.getValue()
    nn = pl.getNormal()
    check("section_coin_plane", near(nn[2], -1) and near(pl.getDistanceFromOrigin(), -10),
          (list(nn), pl.getDistanceFromOrigin()))
    sv.apply("Z", 4, True, m.section_caps([("S", shell)], "Z", 4), {}, view=fv)
    check("section_coin_moves", r.getNumChildren() == 3 and
          near(sv.clip.plane.getValue().getDistanceFromOrigin(), 4))
    sv.remove()
    check("section_coin_removed", r.getNumChildren() == 1)
    mk = m._Marks()
    mk.show([((0, 0, 0), (5, 0, 0))], view=fv)
    n_with = r.getNumChildren()
    mk.clear()
    check("section_marks_display_only", n_with == 2 and r.getNumChildren() == 1)

# ---------------------------------------------------------------- persistence
def t_persist():
    from acadagent import build
    d3 = App.newDocument("w3keep")
    script = "# model.py\n"
    def built(label, shape, bid):
        o = d3.addObject("Part::Feature", label)
        o.Label = label
        o.Shape = shape
        build._ensure_props(o)
        o.AtechAgentBuilt = True
        o.AtechAgentScript = script
        o.AtechAgentBuildId = bid
        o.AtechAgentBuild = 1
        return o
    store = {build._doc_key(d3): {"builds": {"b1": {"sha": build._sha(script)},
                                             "b2": {"sha": build._sha(script)}}}}
    base = built("Base", Part.makeBox(40, 40, 5), "b1")
    lid = built("Lid", Part.makeBox(40, 40, 3, V(0, 0, 10)), "b1")
    d3.recompute()
    picks = [m.Pick(lid, face_at(lid, (20, 20, 10)), (20, 20, 10)),
             m.Pick(base, face_at(base, (20, 20, 5)), (20, 20, 5))]
    res = m.measure("distance", picks, d3)
    check("keep_value", near(res["mm"], 5), res)
    o = m.record(d3, res, picks)
    mats = m.measurements(d3)
    check("keep_is_feature_python", len(mats) == 1 and o.TypeId == "App::FeaturePython"
          and "5.00 mm" in o.AtechMeasureText, o.AtechMeasureText)
    links = [p for p in o.PropertiesList if "Link" in o.getTypeIdOfProperty(p)
             and p not in ("ExpressionEngine",)]
    check("keep_has_no_links", not links, links)
    owned = build.owned(d3, store)
    check("keep_not_owned", o.Name not in {x.Name for x in owned} and
          {x.Name for x in owned} == {base.Name, lid.Name}, [x.Label for x in owned])
    # build.in_process: a previous-build object is KEPT (as "[previous
    # build]") only when something outside the build links to it
    prev_names = {x.Name for x in owned}
    kept = [x for x in owned if any(u.Name not in prev_names for u in x.InList)]
    check("keep_does_not_pin_previous_build", kept == [], [x.Label for x in kept])
    # the rebuild: old bodies removed, new ones with the same labels; the
    # new Lid is built upside down so its face numbers differ
    old_sub = picks[0].sub
    for x in owned:
        d3.removeObject(x.Name)
    base2 = built("Base", Part.makeBox(40, 40, 5), "b2")
    lidshape = Part.makeBox(40, 40, 3, V(0, 0, 13))
    lidshape.rotate(V(20, 20, 14.5), V(1, 0, 0), 180)
    lid2 = built("Lid", lidshape, "b2")
    d3.recompute()
    check("rebuild_face_numbers_moved", face_at(lid2, (20, 20, 13)) != old_sub,
          (face_at(lid2, (20, 20, 13)), old_sub))
    changed = m.refresh(d3)
    o = m.measurements(d3)[0]
    check("rebuild_remeasured", changed == 1 and near(o.AtechMeasureValue, 8)
          and not o.AtechMeasureStale and "8.00 mm" in o.AtechMeasureText, o.AtechMeasureText)
    lines = m.measurements_for_brief(d3)
    check("brief_lines", len(lines) == 2 and "Distance" in lines[1] and "Lid" in lines[1]
          and "8.00 mm" in lines[1], lines)
    # survives save and reopen
    path = os.path.join(os.environ["W3_TMP"], "keep.FCStd")
    d3.saveAs(path)
    App.closeDocument(d3.Name)
    d3 = App.openDocument(path)
    ms = m.measurements(d3)
    check("keep_survives_reopen", len(ms) == 1 and "8.00 mm" in ms[0].AtechMeasureText,
          [x.Label for x in ms])
    d3.removeObject(d3.getObjectsByLabel("Lid")[0].Name)
    m.refresh(d3)
    lines = m.measurements_for_brief(d3)
    check("brief_stale", m.measurements(d3)[0].AtechMeasureStale and "no longer" in lines[1], lines)
    m.remove(d3, m.measurements(d3)[0])
    check("remove_cleans_group", m.measurements(d3) == [] and m.measurements_for_brief(d3) == []
          and not any(getattr(x, "AtechMeasureGroup", False) for x in d3.Objects))
    # a kept mass (whole model) re-weighs after the model changes
    o = m.record(d3, m.measure("mass", [], d3, "PETG"), [], "PETG")
    check("keep_mass", near(o.AtechMeasureValue, 8 * 1.27, 1e-3), o.AtechMeasureText)
    App.closeDocument(d3.Name)

# ---------------------------------------------------------------- inspect
def t_inspect():
    d4 = App.newDocument("w3insp")
    a = d4.addObject("Part::Feature", "Base"); a.Shape = Part.makeBox(10, 10, 10)
    t = d4.addObject("Part::Feature", "Tool"); t.Shape = Part.makeCylinder(2, 20, V(5, 5, -5))
    c = d4.addObject("Part::Cut", "Cut"); c.Base = a; c.Tool = t
    other = d4.addObject("Part::Feature", "Other"); other.Shape = Part.makeBox(3, 3, 3, V(20, 0, 0))
    d4.recompute()
    a.Visibility = False
    t.Visibility = False
    check("inspect_end_parts", sorted(x.Label for x in it.end_parts(d4)) == ["Cut", "Other"],
          [x.Label for x in it.end_parts(d4)])
    hidden = it.isolate(d4, [c])
    check("inspect_isolate", hidden == ["Other"] and c.Visibility and not other.Visibility
          and it.is_isolated(d4))
    check("inspect_hidden_parts", it.hidden_parts(d4) == ["Other"], it.hidden_parts(d4))
    it.show_all(d4)
    check("inspect_show_all_keeps_inputs_hidden", other.Visibility and c.Visibility
          and not a.Visibility and not t.Visibility and not it.is_isolated(d4),
          (a.Visibility, t.Visibility))
    n = it.hide([other])
    check("inspect_hide", n == 1 and not other.Visibility)
    check("inspect_enabled", it.enabled("Atech_ShowAll", d4, []) and
          not it.enabled("Atech_Hide", d4, []) and it.enabled("Atech_Isolate", d4, [c]))
    it.show_all(d4)
    check("inspect_show_all_again", other.Visibility)
    check("inspect_transparency_headless_noop", it.set_transparency([c], 50) == 0)
    App.closeDocument("w3insp")

for name, fn in (("distance", t_distance), ("angle", t_angle), ("radius", t_radius),
                 ("size", t_size), ("mass", t_mass), ("wall", t_wall),
                 ("interference", t_interference), ("fit", t_fit),
                 ("section", t_section), ("persist", t_persist), ("inspect", t_inspect)):
    run(name, fn)
print("W3_FAILS=%d" % FAILS[0])
'''


def run_probe(addon=ADDON, timeout=600):
    tmp = tempfile.mkdtemp(prefix="w3probe-")
    try:
        path = os.path.join(tmp, "probe_w3.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(PROBE)
        env = dict(os.environ, W3_ADDON=addon, W3_KIT=KIT, W3_TMP=tmp,
                   ATECH_ARTIFACTS=os.path.join(REPO, "models"))
        p = subprocess.run([FC, path], env=env, capture_output=True, text=True,
                           timeout=timeout, cwd=tmp)
        out = p.stdout + p.stderr
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    checks = dict(re.findall(r"^CHECK (\S+) (PASS|FAIL)", out, re.M))
    m = re.search(r"W3_FAILS=(\d+)", out)
    return checks, (int(m.group(1)) if m else None), out


@unittest.skipIf(FC is None, "no freecadcmd (set ATECH_FREECADCMD)")
class MeasureCore(unittest.TestCase):
    """The core against closed forms, persistence, inspect (one run)."""

    @classmethod
    def setUpClass(cls):
        cls.checks, cls.fails, cls.out = run_probe()

    def _group(self, prefix, at_least):
        names = [n for n in self.checks if n.startswith(prefix)]
        self.assertGreaterEqual(len(names), at_least, (prefix, self.out[-3000:]))
        for n in names:
            with self.subTest(check=n):
                self.assertEqual(self.checks[n], "PASS", self._line(n))

    def _line(self, name):
        for ln in self.out.splitlines():
            if ln.startswith("CHECK %s " % name):
                return ln
        return self.out[-2000:]

    def test_r300_distance(self):
        self._group("distance_", 6)

    def test_r301_angle(self):
        self._group("angle_", 5)

    def test_r302_radius(self):
        self._group("radius_", 4)

    def test_r303_size(self):
        self._group("size_", 4)

    def test_r304_mass(self):
        self._group("mass_", 6)

    def test_r305_wall(self):
        self._group("wall_", 7)

    def test_r306_interference(self):
        self._group("interference_", 3)

    def test_r307_fit(self):
        self._group("fit_", 3)

    def test_r311_section(self):
        self._group("section_", 13)

    def test_r308_r309_keep_and_rebuild(self):
        self._group("keep_", 6)
        self._group("rebuild_", 2)
        self._group("remove_", 1)

    def test_r310_brief(self):
        self._group("brief_", 2)

    def test_r313_r315_inspect(self):
        self._group("inspect_", 8)

    def test_no_failures_at_all(self):
        self.assertEqual(self.fails, 0, self.out[-4000:])


PROBE_QT = r"""
import os, sys
sys.dont_write_bytecode = True
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.environ["W3_ADDON"])
import FreeCAD as App, Part
from PySide6 import QtWidgets
app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from acadagent import measure as m
m.KIT_DIR = os.environ["W3_KIT"]
doc = App.newDocument("w3qt")
a = doc.addObject("Part::Feature", "Base"); a.Shape = Part.makeBox(40, 40, 5)
b = doc.addObject("Part::Feature", "Lid"); b.Shape = Part.makeBox(40, 40, 3, App.Vector(0, 0, 12))
doc.recompute()
def face(o, pt):
    vx = Part.Vertex(App.Vector(*pt))
    return "Face%d" % (1 + min(range(len(o.Shape.Faces)), key=lambda i: o.Shape.Faces[i].distToShape(vx)[0]))
p = m.MeasurePanel(None, session=m.MeasureSession(lambda: doc), gui=False)
p.on_pick(m.Pick(b, face(b, (20, 20, 12)), (20, 20, 12)))
p.on_pick(m.Pick(a, face(a, (20, 20, 5)), (20, 20, 5)))
print("QT_VALUE", p.value.text())
p.keep()
print("QT_KEPT", p.kept.count(), p.kept.item(0).text())
p.chips["mass"].click()
p.material.setCurrentIndex(1)
p.run()
print("QT_MASS", p.value.text())
p.chips["wall"].click()
p.on_pick(m.Pick(a, face(a, (20, 20, 5)), (20, 20, 5)))
print("QT_WALL", p.value.text())
s = m.SectionPanel(None, doc_fn=lambda: doc, gui=False)
s.open_card()
s.set_axis("Z")
s.slider.setValue(int(round((2.5 - s.lo) / s.STEP)))
s.update_cut()
print("QT_SECTION", "%.2f" % s.offset(), len(s.caps), "%.1f" % sum(f.Area for _l, f in s.caps))
print("QT_BRIEF", m.measurements_for_brief(doc)[1])
"""


@unittest.skipIf(FC is None, "no freecadcmd (set ATECH_FREECADCMD)")
class MeasureCardOnFreeCAD(unittest.TestCase):
    """The real MeasureSession behind the card, in freecadcmd + offscreen
    Qt (no 3D view: gui=False)."""

    def test_card_end_to_end(self):
        tmp = tempfile.mkdtemp(prefix="w3qt-")
        try:
            path = os.path.join(tmp, "probe_qt.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(PROBE_QT)
            env = dict(os.environ, W3_ADDON=ADDON, W3_KIT=KIT, QT_QPA_PLATFORM="offscreen")
            out = subprocess.run([FC, path], env=env, capture_output=True, text=True,
                                 timeout=300, cwd=tmp)
            out = out.stdout + out.stderr
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if "No module named 'PySide6'" in out:
            self.skipTest("no PySide6 in freecadcmd")
        self.assertIn("QT_VALUE 7.00 mm", out, out[-3000:])
        self.assertIn("QT_KEPT 1 Distance Lid to Base: 7.00 mm", out, out[-3000:])
        # 40*40*5 + 40*40*3 = 12800 mm3 of PETG (1.27) = 16.256 g
        self.assertIn("QT_MASS 16.3 g", out, out[-3000:])
        self.assertIn("QT_WALL 5.00 mm", out, out[-3000:])
        self.assertIn("QT_SECTION 2.50 1 1600.0", out, out[-3000:])
        self.assertRegex(out, r"QT_BRIEF - Distance of Lid Face\d+, Base Face\d+: 7\.00 mm")


# one broken line per feature -> the named check must FAIL
SABOTAGE = (
    ("measure.py", 'dx": _r(abs(p2.x - p1.x))', 'dx": _r(abs(p2.y - p1.y))',
     "distance_faces"),
    ("measure.py", '("PETG", 1.27)', '("PETG", 1.17)', "mass_box_PETG"),
    ("measure.py", "THIN_WALL_MM = 0.8", "THIN_WALL_MM = 0.5", "wall_thin_red"),
    ("measure.py", "        g.addObject(o)\n",
     "        g.addObject(o)\n        o.addProperty('App::PropertyLinkList', 'Parts')\n"
     "        o.Parts = [p.obj for p in picks]\n", "keep_does_not_pin_previous_build"),
    ("measure.py", 'return "%s%s%d" % (path, prefix, best[1] + 1), tuple(best[2])',
     "return sub, point", "rebuild_remeasured"),
    ("measure.py", "    n = [-c for c in AXES[axis]]\n", "    n = list(AXES[axis])\n",
     "section_clip_keeps_below"),
    ("inspect_tools.py", "if _is_part(o) and not _consumed(o)", "if _is_part(o)",
     "inspect_show_all_keeps_inputs_hidden"),
)


@unittest.skipIf(FC is None, "no freecadcmd (set ATECH_FREECADCMD)")
class MeasureSabotage(unittest.TestCase):
    """Each break makes its check FAIL; the untouched files pass
    (MeasureCore) - the restore half of the sabotage."""

    def test_each_break_is_caught(self):
        for fname, old, new, check in SABOTAGE:
            with self.subTest(check=check):
                tmp = tempfile.mkdtemp(prefix="w3sab-")
                try:
                    dst = os.path.join(tmp, "acadagent")
                    shutil.copytree(PKG, dst, ignore=shutil.ignore_patterns(
                        "__pycache__", "agent_kit"))
                    p = os.path.join(dst, fname)
                    with open(p, encoding="utf-8") as fh:
                        src = fh.read()
                    self.assertEqual(src.count(old), 1, "sabotage anchor moved: %r" % old)
                    with open(p, "w", encoding="utf-8") as fh:
                        fh.write(src.replace(old, new))
                    checks, fails, out = run_probe(addon=tmp)
                    self.assertEqual(checks.get(check), "FAIL", out[-3000:])
                    self.assertGreater(fails or 0, 0)
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------- Qt (plain)
try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtWidgets  # noqa: F401
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    HAVE_QT = True
except Exception:                                       # noqa: BLE001
    HAVE_QT = False


class _StubSession(object):
    """MeasureSession's surface with canned results (no FreeCAD)."""

    def __init__(self, results):
        from acadagent import measure
        self.m = measure
        self.results = results
        self.mode = "distance"
        self.material = "PLA"
        self.picks = []
        self.result = None
        self.error = None
        self.doc_fn = lambda: None

    def set_mode(self, kind):
        self.mode, self.picks, self.result, self.error = kind, [], None, None

    def needs(self):
        return self.m.KIND_PICKS[self.mode]

    def add_pick(self, pick):
        self.picks.append(pick)
        if self.needs() and len(self.picks) >= self.needs():
            return self.run()
        return None

    def run(self):
        self.result = self.results.get(self.mode)
        self.error = None if self.result else "Pick something."
        return self.result

    def clear(self):
        self.picks, self.result, self.error = [], None, None


class _Obj(object):
    Label = "Lid"


def button_closes_cleanly(measure):
    """The Measure button opens its card over the bar's parent and is
    unchecked again when the card closes (X / Escape)."""
    host = QtWidgets.QWidget()
    host.resize(900, 600)
    bar = QtWidgets.QFrame(host)
    bar._icons = []
    b = measure.make_measure_button(bar, gui=False, session=_StubSession({}))
    ok = bar._icons and bar._icons[-1][0] is b and b.isCheckable()
    b.setChecked(True)
    ok = ok and b.panel is not None and b.panel.parentWidget() is host
    host.show()
    _APP.processEvents()
    ok = ok and b.panel.isVisible() and b.panel.x() == 16
    b.panel.close_card()
    ok = ok and not b.isChecked() and not b.panel.isVisible()
    b.setChecked(True)
    ok = ok and b.panel.isVisible()
    b.setChecked(False)
    ok = ok and not b.panel.isVisible()
    host.close()
    return bool(ok)


@unittest.skipUnless(HAVE_QT, "PySide6 not available")
class MeasureQt(unittest.TestCase):
    def setUp(self):
        from acadagent import measure
        self.m = measure

    def test_r312_button_and_card(self):
        self.assertTrue(button_closes_cleanly(self.m))

    def test_r312_sabotage_button_never_unchecks(self):
        real = self.m._attach

        def broken(button, make_panel):
            def toggled(on):
                if on:
                    if button.panel is None:
                        button.panel = make_panel()
                    button.panel.open_card()
            button.panel = None
            button.toggled.connect(toggled)
            return button
        self.m._attach = broken
        try:
            self.assertFalse(button_closes_cleanly(self.m))
        finally:
            self.m._attach = real
        self.assertTrue(button_closes_cleanly(self.m))       # restored

    def test_r305_thin_wall_shows_red(self):
        from acadagent import style
        res = {"kind": "wall", "mm": 0.6, "thin": True, "at": [0, 0, 0], "dir": [0, 0, 1]}
        p = self.m.MeasurePanel(None, session=_StubSession({"wall": res}), gui=False)
        p.set_mode("wall")
        p.on_pick(self.m.Pick(_Obj(), "Face1", (0, 0, 0)))
        self.assertEqual(p.value.text(), "0.60 mm")
        self.assertIn(style.tokens()["fail"], p.value.styleSheet())
        self.assertIn("too thin", p.detail.text())
        self.assertTrue(p.btn_keep.isEnabled())
        ok = dict(res, mm=1.6, thin=False)
        p.session.results["wall"] = ok
        p.on_pick(self.m.Pick(_Obj(), "Face2", (0, 0, 0)))
        self.assertEqual(p.value.text(), "1.60 mm")
        self.assertEqual(p.value.styleSheet(), "")

    def test_r300_distance_two_picks(self):
        res = {"kind": "distance", "mm": 12.0, "dx": 0.0, "dy": 5.0, "dz": 10.9,
               "p1": [0, 0, 0], "p2": [0, 5, 10.9]}
        p = self.m.MeasurePanel(None, session=_StubSession({"distance": res}), gui=False)
        p.on_pick(self.m.Pick(_Obj(), "Face1", None))
        self.assertIn("1 of 2 picked", p.detail.text())
        self.assertFalse(p.btn_keep.isEnabled())
        p.on_pick(self.m.Pick(_Obj(), "Face2", None))
        self.assertEqual(p.value.text(), "12.00 mm")
        self.assertEqual(p.detail.text(), "dX 0.00  dY 5.00  dZ 10.90 mm")

    def test_modes_material_and_names(self):
        p = self.m.MeasurePanel(None, session=_StubSession({}), gui=False)
        self.assertEqual([b.text() for b in (p.chips[k] for k, *_r in self.m.KINDS)],
                         ["Distance", "Angle", "Radius", "Size", "Wall", "Overlaps",
                          "Mass", "Fit"])
        p.show()
        p.chips["mass"].click()
        self.assertEqual(p.session.mode, "mass")
        self.assertTrue(p.mat_row.isVisible())
        self.assertTrue(p.btn_run.isVisible())
        self.assertEqual([p.material.itemData(i) for i in range(p.material.count())],
                         ["PLA", "PETG", "ABS", "TPU"])
        p.material.setCurrentIndex(2)
        self.assertEqual(p.session.material, "ABS")
        p.chips["distance"].click()
        self.assertFalse(p.mat_row.isVisible())
        self.assertFalse(p.btn_run.isVisible())
        for w in p.findChildren(QtWidgets.QAbstractButton):
            if w.isVisible():
                self.assertTrue(w.accessibleName() or w.text(), w.objectName())
        p.close()

    def test_r311_section_card(self):
        p = self.m.SectionPanel(None, doc_fn=lambda: None, gui=False)
        p.set_axis("Y")
        self.assertEqual(p.tabs.index(), 1)
        self.assertEqual(p.slider.accessibleName(), "Cut position")
        self.assertTrue(p.pos.text().startswith("Y "))

    def test_section_button(self):
        host = QtWidgets.QWidget()
        bar = QtWidgets.QFrame(host)
        bar._icons = []
        b = self.m.make_section_button(bar, gui=False, doc_fn=lambda: None)
        self.assertEqual(b.accessibleName(), "Section view")
        b.setChecked(True)
        self.assertIsNotNone(b.panel)
        b.panel.close_card()
        self.assertFalse(b.isChecked())

    def test_inspect_menu_actions(self):
        from acadagent import inspect_tools as it
        menu = QtWidgets.QMenu()
        acts = it.add_actions(menu, doc_fn=lambda: None, selection_fn=lambda: [])
        self.assertEqual([a.text() for a in acts.values()],
                         ["Hide", "Isolate", "Show all", "See-through"])
        self.assertFalse(any(a.isEnabled() for a in acts.values()))


class MeasurePure(unittest.TestCase):
    """No FreeCAD, no Qt."""

    def test_describe_and_tables(self):
        from acadagent import measure as m
        self.assertEqual(dict(m.MATERIALS), {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04,
                                             "TPU": 1.21})
        self.assertEqual(m.THIN_WALL_MM, 0.8)
        self.assertEqual(m.describe({"kind": "mass", "grams": 7.44, "volume_cm3": 6.0,
                                     "material": "PLA", "density": 1.24})[0], "7.4 g")
        self.assertEqual(m.describe({"kind": "interference", "pairs": []})[0], "No overlaps")
        self.assertEqual(m.describe({"kind": "angle", "deg": 30, "between": 150})[0],
                         "30.00°")
        n, d = m.clip_plane("X", 3)
        self.assertEqual((n, d), ([-1.0, -0.0, -0.0], -3.0))

    def test_session_pick_cycle(self):
        from acadagent import measure as m
        s = m.MeasureSession(doc_fn=lambda: None)
        calls = []
        s.run = lambda: calls.append(list(s.picks)) or None
        s.add_pick("a")
        s.add_pick("b")
        s.add_pick("c")          # a third pick starts over
        self.assertEqual(calls, [["a", "b"]])
        self.assertEqual(s.picks, ["c"])
        s.set_mode("radius")
        s.add_pick("r")
        self.assertEqual(calls[-1], ["r"])

    def test_no_link_properties_in_source(self):
        with open(os.path.join(PKG, "measure.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("PropertyLink", src)
        self.assertNotIn("AtechAgentBuilt\"", src.replace("AtechAgentBuilt flag", ""))


if __name__ == "__main__":
    unittest.main()
