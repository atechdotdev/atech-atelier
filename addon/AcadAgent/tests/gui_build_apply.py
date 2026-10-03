"""Regression checks for build.apply - the review findings of 2026-09-24.

Runs INSIDE a FreeCAD GUI session (transactions need the GUI's undo stack):
exec this file from the Python console or a driver. Prints one line per
check and a final BUILD_APPLY_RESULT=<n failures>. No Claude calls.
"""
import os
import tempfile

import FreeCAD
import Part

from acadagent import build

FAIL = []


def check(name, cond, detail=""):
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))
    if not cond:
        FAIL.append(name)


def write(ws, code):
    with open(os.path.join(ws, build.SCRIPT), "w", encoding="utf-8") as fh:
        fh.write(code)


def fresh(name):
    if name in FreeCAD.listDocuments():
        FreeCAD.closeDocument(name)
    return FreeCAD.newDocument(name)


ws = tempfile.mkdtemp(prefix="atech-build-test-")
BOX = ("import Part\no = doc.addObject('Part::Feature', '%s')\n"
       "o.Shape = Part.makeBox(%s, 10, 10)\n")

# 1. sys.exit in the script: Studio survives, nothing left behind
a = fresh("BA_A")
write(ws, "import sys, Part\ndoc.addObject('Part::Feature','Stray').Shape="
          "Part.makeBox(1,1,1)\nsys.exit(0)\n")
r = build.apply(ws, [build.SCRIPT], None)
check("sysexit_caught", r is not None and not r.ok and "SystemExit" in r.error,
      (r.error[-60:] if r else ""))
check("sysexit_rolled_back", a.getObject("Stray") is None)

# 2. builds stay in the chat's document; the user's same-named object in
#    another document is untouched
write(ws, BOX % ("Plate", 20))
r1 = build.apply(ws, [build.SCRIPT], None)
check("first_build_ok", r1.ok and r1.doc == "BA_A", r1.error)
b = fresh("BA_B")
user = b.addObject("Part::Feature", "Plate")
user.Shape = Part.makeBox(5, 5, 5)
FreeCAD.setActiveDocument("BA_B")
write(ws, BOX % ("Plate", 30))
r2 = build.apply(ws, [build.SCRIPT], r1.record())
check("second_build_in_chat_doc", r2.ok and r2.doc == "BA_A", r2.doc)
check("user_object_in_other_doc_untouched",
      b.getObject("Plate") is not None
      and abs(b.getObject("Plate").Shape.Volume - 125) < 1e-6)
check("previous_build_replaced",
      len([o for o in a.Objects if o.Label.startswith("Plate")]) == 1)

# 3. a user feature built on the agent's body keeps its input
FreeCAD.setActiveDocument("BA_A")
agent_obj = a.getObject(r2.created[0])
cut = a.addObject("Part::Cut", "UserCut")
cut.Base = agent_obj
tool = a.addObject("Part::Feature", "UserTool")
tool.Shape = Part.makeCylinder(2, 20)
cut.Tool = tool
a.recompute()
write(ws, BOX % ("Plate", 40))
r3 = build.apply(ws, [build.SCRIPT], r2.record())
check("dependency_kept", r3.ok and cut.Base is not None and cut.Base.Name == agent_obj.Name,
      "kept=%s" % (r3.kept,))

# 4. a sketch + extrusion design is not failed for its sketch
c = fresh("BA_C")
write(ws, """import Part, Sketcher
from FreeCAD import Vector
sk = doc.addObject('Sketcher::SketchObject', 'Sk')
pts = [Vector(0,0,0), Vector(20,0,0), Vector(20,10,0), Vector(0,10,0)]
for i in range(4):
    sk.addGeometry(Part.LineSegment(pts[i], pts[(i+1) % 4]))
doc.recompute()
ext = doc.addObject('Part::Extrusion', 'Ext')
ext.Base = sk
ext.Dir = Vector(0, 0, 5)
ext.Solid = True
""")
r4 = build.apply(ws, [build.SCRIPT], None)
check("sketch_design_ok", r4.ok, r4.error[-80:])
check("sketch_not_flagged", build.failures(r4) == "", build.failures(r4))
check("end_result_measured",
      [m["label"] for m in r4.measurements] == ["Ext"]
      and abs(r4.measurements[0]["volume_mm3"] - 1000) < 1e-3,
      str([(m["label"], m["volume_mm3"]) for m in r4.measurements]))

# 5. labels: exact restore of Name001, never strip a real number
d = fresh("BA_D")
write(ws, BOX % ("Gear1", 10))
r5 = build.apply(ws, [build.SCRIPT], None)
check("real_number_label_kept", d.getObject(r5.created[0]).Label == "Gear1",
      d.getObject(r5.created[0]).Label)
write(ws, BOX % ("Gear1", 12))
r6 = build.apply(ws, [build.SCRIPT], r5.record())
check("suffix_label_restored", d.getObject(r6.created[0]).Label == "Gear1",
      d.getObject(r6.created[0]).Label)

# 6. an .stl export imports through Mesh
e = fresh("BA_E")
import Mesh
stl = os.path.join(ws, "part.stl")
Mesh.Mesh(Part.makeBox(10, 10, 10).tessellate(0.1)).write(stl)
os.remove(os.path.join(ws, build.SCRIPT))
r7 = build.apply(ws, ["part.stl"], None)
check("stl_imports", r7 is not None and r7.ok, r7.error if r7 else "none")

# 8. a script that deletes an existing object and then raises is fully
#    rolled back
f = fresh("BA_F")
keep = f.addObject("Part::Feature", "Keep")
keep.Shape = Part.makeBox(3, 3, 3)
f.recompute()
write(ws, "doc.removeObject('Keep')\nraise RuntimeError('boom')\n")
r8 = build.apply(ws, [build.SCRIPT], None)
check("failed_script_rolled_back", not r8.ok and f.getObject("Keep") is not None,
      r8.error[-80:])

# 9. a new chat on a reopened document adopts the agent's build instead of
#    duplicating it (script persisted in the document)
g = fresh("BA_G")
os.makedirs(ws, exist_ok=True)
write(ws, BOX % ("Case", 10))
r9 = build.apply(ws, [build.SCRIPT], None)
ws2 = tempfile.mkdtemp(prefix="atech-build-test-")
prev = build.adopt(g, ws2)
check("script_persisted", prev is not None
      and os.path.exists(os.path.join(ws2, build.SCRIPT)))
r10 = build.apply(ws2, [build.SCRIPT], prev)
check("adopted_build_replaced_not_duplicated",
      r10.ok and [o.Label for o in g.Objects] == ["Case"],
      str([o.Label for o in g.Objects]))

for n in ("BA_A", "BA_B", "BA_C", "BA_D", "BA_E", "BA_F", "BA_G"):
    if n in FreeCAD.listDocuments():
        FreeCAD.closeDocument(n)
print("BUILD_APPLY_RESULT=%d" % len(FAIL))
