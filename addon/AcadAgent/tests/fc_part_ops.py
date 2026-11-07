"""design_import + part_ops under freecadcmd (R880, R885): real geometry.

    ATECH_FREECADCMD=<freecadcmd> python3 -m unittest -v test_part_ops
    (or directly: <freecadcmd> fc_part_ops.py; the last line is
    PART_OPS_RESULT=<json>)

Covers: adding a STEP (one body; several bodies = one part each), an STL in
inches, set down beside what is there; source and licence recorded; each
op (push/pull out and in, holes, fillet, chamfer, hollow, mirror, split,
add / cut box and cylinder) with the volume it should have; steps in the
document frame on a moved and turned part; undo step / remove step / back
to original; steps and the original surviving save and reopen; mesh to
solid (a box mesh gives 6 faces); the agent's part_edits.json on a part
it may edit and one it may not; licence checks and credits.
"""
import json
import math
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import FreeCAD                                          # noqa: E402
import Mesh                                             # noqa: E402
import Part                                             # noqa: E402
from acadagent import design_import as di               # noqa: E402
from acadagent import part_ops as po                    # noqa: E402
from acadagent import shape_edit as se                  # noqa: E402

R = {"checks": {}, "errors": []}


def check(name, ok, detail=None):
    R["checks"][name] = bool(ok)
    if not ok:
        R["errors"].append("%s: %r" % (name, detail))


def near(a, b, tol=0.05):
    return abs(a - b) <= tol * max(1.0, abs(b))


def refused(fn):
    try:
        fn()
    except se.EditRefused as exc:
        return str(exc) or True
    return False


try:
    tmp = tempfile.mkdtemp(prefix="atech-po-")
    step = os.path.join(tmp, "bracket_v2.step")
    Part.makeBox(40, 20, 10).exportStep(step)
    two = os.path.join(tmp, "two_bodies.step")
    Part.makeCompound([Part.makeBox(10, 10, 10),
                       Part.makeBox(10, 10, 10, FreeCAD.Vector(30, 0, 0))]).exportStep(two)
    stl = os.path.join(tmp, "knob.stl")
    Mesh.createBox(1, 2, 3).write(stl)          # inches

    doc = FreeCAD.newDocument("PartOps")
    doc.UndoMode = 1
    first = se.add_shape(doc, "box")             # something already there

    # ---- R880 add_file
    made = di.add_file(doc, step, source={"url": "https://makerworld.com/en/models/123-bracket",
                                          "author": "Ana", "licence": "cc-by-sa"},
                       agent_editable=True)
    check("one body, one part", len(made) == 1, len(made))
    b = made[0]
    check("label from file", b.Label == "bracket v2", b.Label)
    check("tagged import", di.is_import(b) and b.AtechImportFile == "bracket_v2.step")
    check("sha recorded", len(b.AtechImportSha256) == 64)
    src = di.source(b)
    check("source kept", src["author"] == "Ana" and src["licence"] == "cc-by-sa"
          and "makerworld" in src["url"], src)
    check("on the floor", near(se.position(b)[2], 0.0, 0.001), se.position(b))
    check("beside the box", se._world_bbox(b).XMin > se._world_bbox(first).XMax,
          (se._world_bbox(b).XMin, se._world_bbox(first).XMax))
    check("solid editable", po.can_edit(b) and po.has_base(b) and po.steps(b) == [])
    check("agent editable flag", po.agent_editable(b))

    parts = di.add_file(doc, two)
    check("two bodies, two parts", len(parts) == 2 and parts[1].Label == "two bodies 2",
          [p.Label for p in parts])
    check("not agent editable by default", not po.agent_editable(parts[0]))

    knob = di.add_file(doc, stl, units=25.4)[0]
    check("stl is a mesh", se.kind(knob) == "mesh")
    sz = se.size(knob)
    check("inches scaled", near(sz[0], 25.4) and near(sz[2], 76.2), sz)
    check("bad ext refused", refused(lambda: di.add_file(doc, os.path.join(tmp, "x.dwg"))))

    # ---- R885 ops on the bracket (40 x 20 x 10 = 8000)
    V0 = b.Shape.Volume
    check("volume 8000", near(V0, 8000), V0)
    po.apply(b, {"op": "push_pull", "face": "top", "distance": 5})
    check("pull top +5", near(b.Shape.Volume, 12000), b.Shape.Volume)
    check("taller", near(se.size(b)[2], 15), se.size(b))
    po.apply(b, {"op": "push_pull", "face": "+x", "distance": -10})
    check("push +x in 10", near(b.Shape.Volume, 9000), b.Shape.Volume)
    po.apply(b, {"op": "hole", "face": "top", "diameter": 6, "depth": None})
    check("through hole", near(b.Shape.Volume, 9000 - math.pi * 9 * 15, 0.01),
          b.Shape.Volume)
    v = b.Shape.Volume
    po.apply(b, {"op": "hole", "face": "top", "diameter": 4, "depth": 5,
                 "at": [se._world_bbox(b).XMin + 5, se._world_bbox(b).YMin + 5, 0]},
             frame="world")
    check("blind hole", near(b.Shape.Volume, v - math.pi * 4 * 5, 0.01), b.Shape.Volume)
    v = b.Shape.Volume
    po.apply(b, {"op": "fillet", "edges": "vertical", "radius": 2})
    check("fillet less volume", b.Shape.Volume < v and b.Shape.isValid())
    v = b.Shape.Volume
    po.apply(b, {"op": "chamfer", "edges": "face:bottom", "size": 0.5})
    check("chamfer", b.Shape.Volume < v and b.Shape.isValid())
    check("six steps", len(po.steps(b)) == 6, po.steps(b))
    check("too big fillet refused",
          refused(lambda: po.apply(b, {"op": "fillet", "edges": "all", "radius": 50})))
    check("refusal leaves steps", len(po.steps(b)) == 6)
    check("bad face refused", refused(lambda: po.apply(b, {"op": "push_pull",
                                                           "face": 999, "distance": 1})))
    check("unknown op refused", refused(lambda: po.apply(b, {"op": "explode"})))

    # undo / remove / reset
    po.undo_step(b)
    check("undo step", len(po.steps(b)) == 5 and near(b.Shape.Volume, v), b.Shape.Volume)
    po.remove_step(b, 0)                         # drop the +5 pull: replays the rest
    check("remove first step", len(po.steps(b)) == 4 and near(se.size(b)[2], 10),
          (po.steps(b), se.size(b)))
    doc.undo()
    check("doc undo restores step", len(po.steps(b)) == 5, po.steps(b))
    doc.redo()
    po.reset(b)
    check("back to original", po.steps(b) == [] and near(b.Shape.Volume, 8000))

    # hollow, mirror, split, add / cut
    po.apply(b, {"op": "hollow", "thickness": 2, "open": ["top"]})
    check("hollow open top", near(b.Shape.Volume, 8000 - 36 * 16 * 8, 0.02), b.Shape.Volume)
    po.reset(b)
    po.apply(b, {"op": "split", "plane": "x", "keep": "below"})
    check("split half", near(b.Shape.Volume, 4000), b.Shape.Volume)
    po.reset(b)
    po.apply(b, {"op": "add", "shape": "cylinder", "center": [20, 10, 10],
                 "axis": "z", "radius": 5, "height": 10})
    check("add cylinder", near(b.Shape.Volume, 8000 + math.pi * 250, 0.01), b.Shape.Volume)
    po.apply(b, {"op": "cut", "shape": "box", "min": [0, 0, 0], "max": [10, 20, 10]})
    check("cut box", near(b.Shape.Volume, 6000 + math.pi * 250, 0.01), b.Shape.Volume)
    check("missing cut refused", refused(lambda: po.apply(
        b, {"op": "cut", "shape": "box", "min": [500, 500, 500], "max": [510, 510, 510]})))
    po.reset(b)
    po.apply(b, {"op": "push_pull", "face": "+x", "distance": 10})
    po.apply(b, {"op": "mirror", "plane": "x"})
    check("mirror keeps volume", near(b.Shape.Volume, 10000), b.Shape.Volume)
    po.reset(b)

    # steps in the document frame on a moved, turned part: a world box cut
    se.move_to(b, 100, 100, 0)
    se.turn(b, "z", 90)
    bb = se._world_bbox(b)                      # now 20 (x) x 40 (y)
    check("turned", near(bb.XLength, 20) and near(bb.YLength, 40), (bb.XLength, bb.YLength))
    po.apply(b, {"op": "cut", "shape": "box",
                 "min": [bb.XMin - 1, bb.YMin - 1, bb.ZMin - 1],
                 "max": [bb.XMax + 1, bb.YMin + 10, bb.ZMax + 1]}, frame="world")
    check("world cut on turned part", near(b.Shape.Volume, 6000), b.Shape.Volume)
    bb2 = se._world_bbox(b)
    check("cut the right end", near(bb2.YMin, bb.YMin + 10) and near(bb2.YMax, bb.YMax),
          (bb.YMin, bb.YMax, bb2.YMin, bb2.YMax))
    se.move_to(b, 0, 200, 0)
    check("steps follow a move", near(b.Shape.Volume, 6000) and len(po.steps(b)) == 1)

    # ---- mesh to solid
    k2 = po.mesh_to_solid(knob)
    check("mesh became solid", se.kind(k2) == "solid" and len(k2.Shape.Faces) == 6,
          (se.kind(k2), len(k2.Shape.Faces)))
    check("solid kept import props", di.is_import(k2) and k2.AtechImportFile == "knob.stl")
    check("solid volume", near(k2.Shape.Volume, 25.4 * 50.8 * 76.2, 0.01), k2.Shape.Volume)
    check("label kept", k2.Label == "knob", k2.Label)
    po.apply(k2, {"op": "fillet", "edges": "face:top", "radius": 3})
    check("converted part edits", len(po.steps(k2)) == 1)

    # make_editable on a primitive
    s2 = po.make_editable(first)
    check("box made editable", se.kind(s2) == "solid" and po.has_base(s2))

    # ---- save / reopen keeps the original and steps
    path = os.path.join(tmp, "ops.FCStd")
    doc.saveAs(path)
    label = b.Label
    FreeCAD.closeDocument(doc.Name)
    doc = FreeCAD.openDocument(path)
    b = [o for o in doc.Objects if o.Label == label][0]
    check("reopen keeps base", po.has_base(b) and near(b.AtechBase.Volume, 8000),
          b.AtechBase.Volume if po.has_base(b) else None)
    check("reopen keeps steps", len(po.steps(b)) == 1)
    po.undo_step(b)
    check("reopen undo", near(b.Shape.Volume, 8000), b.Shape.Volume)

    # ---- the agent's part_edits.json
    bb = se._world_bbox(b)
    text = json.dumps({"edits": [{"part": label, "steps": [
        {"op": "push_pull", "face": "top", "distance": 2},
        {"op": "fillet", "edges": "vertical", "radius": 1, "m": [1] * 16}]}]})
    done, errs = po.apply_agent_edits(doc, text)
    check("agent edit applied", len(done) == 1 and not errs, (done, errs))
    check("agent frame stripped", all(s.get("m") is None or len(s["m"]) == 16
                                      for s in po.steps(b)))
    check("agent taller", near(se.size(b)[2], 12), se.size(b))
    other = [o for o in doc.Objects if o.Label == "two bodies 1"][0]
    done, errs = po.apply_agent_edits(doc, json.dumps(
        {"edits": [{"part": "two bodies 1", "steps": [{"op": "mirror", "plane": "x"}]}]}))
    check("agent refused when not allowed", not done and errs and "not let" in errs[0], errs)
    check("not allowed part untouched", po.steps(other) == [])
    done, errs = po.apply_agent_edits(doc, "{nope")
    check("bad json said", errs and "JSON" in errs[0], errs)
    done, errs = po.apply_agent_edits(doc, json.dumps(
        {"edits": [{"part": label, "steps": [{"op": "push_pull", "face": "top",
                                              "distance": 1},
                                             {"op": "fillet", "edges": "all",
                                              "radius": 90}]}]}))
    check("failed agent steps all-or-nothing", errs and len(po.steps(b)) == 2,
          (errs, po.steps(b)))
    lines = po.brief_lines(doc)
    check("brief lists editable part", lines and lines[0].startswith(label)
          and any("flat top" in ln for ln in lines), lines[:4])
    check("brief skips others", not any(ln.startswith("two bodies") for ln in lines))
    il = di.brief_lines(doc)
    check("import brief", any("by Ana" in ln and "you may edit" in ln for ln in il)
          and any("never change" in ln for ln in il), il)

    # ---- licences
    check("cc-by-sa publishable", di.licence_problem(b) == "")
    di.set_source(other, licence="sdfl", author="Bo")
    check("sdfl not publishable", "does not allow sharing" in di.licence_problem(other))
    di.set_source(other, licence="cc-by-nd")
    po.apply(other, {"op": "mirror", "plane": "x"})
    check("nd edited refused", "does not allow changes" in di.licence_problem(other))
    di.set_source(other, licence="unknown")
    check("unknown asks", "not stated" in di.licence_problem(other))
    di.set_source(other, licence="cc-by-nc")
    check("strictest nc-sa", di.strictest_licence(doc.Objects) == "cc-by-nc-sa",
          di.strictest_licence(doc.Objects))
    cr = di.credits(doc)
    check("credit line", any(c.startswith("bracket v2 by Ana (CC BY-SA), https://makerworld")
                             for c in cr), cr)
except Exception:                                       # noqa: BLE001
    R["errors"].append(traceback.format_exc())

R["ok"] = not R["errors"] and all(R["checks"].values())
print("PART_OPS_RESULT=" + json.dumps(R))
