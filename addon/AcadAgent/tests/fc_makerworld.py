"""makerworld under freecadcmd (R900): a Bambu Studio style 3MF read and
added; the publish bundle made, and refused for a forbidden licence.

    ATECH_FREECADCMD=<freecadcmd> python3 -m unittest -v test_makerworld
    (or directly: <freecadcmd> fc_makerworld.py; the last line is
    MAKERWORLD_RESULT=<json>)
"""
import json
import os
import sys
import tempfile
import traceback
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import FreeCAD                                          # noqa: E402
import Part                                             # noqa: E402
from acadagent import design_import as di               # noqa: E402
from acadagent import makerworld as mw                  # noqa: E402
from acadagent import shape_edit as se                  # noqa: E402

R = {"checks": {}, "errors": []}


def check(name, ok, detail=None):
    R["checks"][name] = bool(ok)
    if not ok:
        R["errors"].append("%s: %r" % (name, detail))


CUBE_V = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0),
          (0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10)]
CUBE_T = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
          (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def bambu_3mf(path):
    """The layout Bambu Studio writes: the mesh in 3D/Objects/object_1.model,
    the main model a component of it (moved 100 mm in x), a build item
    placing it again (+0, +50, 0)."""
    ns = 'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
    pns = 'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
    verts = "".join('<vertex x="%g" y="%g" z="%g"/>' % v for v in CUBE_V)
    tris = "".join('<triangle v1="%d" v2="%d" v3="%d"/>' % t for t in CUBE_T)
    obj = ('<?xml version="1.0"?><model unit="millimeter" %s><resources>'
           '<object id="1" type="model"><mesh><vertices>%s</vertices><triangles>%s'
           '</triangles></mesh></object></resources><build/></model>' % (ns, verts, tris))
    main = ('<?xml version="1.0"?><model unit="millimeter" %s %s><resources>'
            '<object id="2" name="Cable clip" type="model"><components>'
            '<component p:path="/3D/Objects/object_1.model" objectid="1" '
            'transform="1 0 0 0 1 0 0 0 1 100 0 0"/></components></object>'
            '</resources><build><item objectid="2" transform="1 0 0 0 1 0 0 0 1 0 50 0"/>'
            '</build></model>' % (ns, pns))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("3D/3dmodel.model", main)
        z.writestr("3D/Objects/object_1.model", obj)


try:
    tmp = tempfile.mkdtemp(prefix="atech-mw-")
    p = os.path.join(tmp, "cable_clip.3mf")
    bambu_3mf(p)
    items = mw.read_3mf(p)
    check("one build item", len(items) == 1 and items[0][0] == "Cable clip", items[:1])
    xs = [v[0] for t in items[0][1] for v in t]
    ys = [v[1] for t in items[0][1] for v in t]
    check("transforms applied", min(xs) == 100 and max(xs) == 110 and min(ys) == 50,
          (min(xs), max(xs), min(ys)))
    check("12 triangles", len(items[0][1]) == 12)

    doc = FreeCAD.newDocument("MW")
    doc.UndoMode = 1
    made = di.add_file(doc, p, source={"url": "https://makerworld.com/en/models/42-cable-clip",
                                        "author": "Ana", "licence": "cc-by-sa"},
                       label="Cable clip")
    m = made[0]
    check("added as mesh", se.kind(m) == "mesh" and m.Mesh.CountFacets == 12,
          (se.kind(m), m.Mesh.CountFacets))
    check("size 10 mm", all(abs(a - 10) < 1e-6 for a in se.size(m)), se.size(m))
    check("label from link", m.Label == "Cable clip", m.Label)

    from acadagent import part_ops as po
    s = po.mesh_to_solid(m)
    check("bambu mesh to solid", len(s.Shape.Faces) == 6 and abs(s.Shape.Volume - 1000) < 1e-3)

    own = doc.addObject("Part::Feature", "Base")
    own.Shape = Part.makeBox(30, 30, 3)
    plan = mw.publish_plan(doc)
    check("plan ok", not plan["problems"], plan["problems"])
    check("plan licence sa", plan["licence"] == "cc-by-sa", plan["licence"])
    check("plan remix credit", plan["remix"] and "Ana" in plan["remix"][0], plan["remix"])
    bad = mw.publish_plan(doc, "cc-by")
    check("dropping SA refused", bad["problems"] and "CC BY-SA" in bad["problems"][0],
          bad["problems"])

    out = os.path.join(tmp, "bundle")
    b = mw.write_bundle(doc, out, "Clip holder", "Holds a cable.", "cc-by-sa",
                        picture=False)
    names = sorted(os.path.basename(f) for f in b["files"])
    check("bundle files", "Clip_holder.3mf" in names and "Clip_holder.step" in names
          and "description.txt" in names, names)
    check("3mf not empty", os.path.getsize(os.path.join(out, "Clip_holder.3mf")) > 200)
    text = open(os.path.join(out, "description.txt"), encoding="utf-8").read()
    check("description credits", "Remix of:" in text and "Ana" in text
          and "CC BY-SA" in text and "atech.dev/atelier" in text, text)

    di.set_source(s, licence="sdfl")
    try:
        mw.write_bundle(doc, os.path.join(tmp, "b2"), "x", "", "cc-by", picture=False)
        check("sdfl blocks bundle", False)
    except ValueError as exc:
        check("sdfl blocks bundle", "does not allow sharing" in str(exc), str(exc))
    check("nothing written when blocked", not os.path.exists(os.path.join(tmp, "b2")))
except Exception:                                       # noqa: BLE001
    R["errors"].append(traceback.format_exc())

R["ok"] = not R["errors"] and all(R["checks"].values())
print("MAKERWORLD_RESULT=" + json.dumps(R))
