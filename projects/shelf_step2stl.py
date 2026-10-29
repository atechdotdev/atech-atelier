"""shelf_step2stl - one STEP file -> one binary STL, run in a child freecadcmd.

    SHELF_IN=<part.step> SHELF_OUT=<part.stl> freecadcmd shelf_step2stl.py

Run by shelf.tessellate(), so OpenCASCADE meshes the (sometimes 50 MB) STEP
in its own process, not on a worker thread of the app. The mesh is
user_parts.read_mesh's: the chord error every imported STEP gets. Prints
one line SHELF_STL={json}: triangles and size_mm, or {"error": ...}.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    import user_parts
    mesh = user_parts.read_mesh(os.environ["SHELF_IN"])
    mesh.write(os.environ["SHELF_OUT"])
    bb = mesh.BoundBox
    return {"triangles": int(mesh.CountFacets),
            "size_mm": [round(bb.XLength, 3), round(bb.YLength, 3),
                        round(bb.ZLength, 3)]}


try:
    rep = main()
except Exception as exc:                               # noqa: BLE001
    rep = {"error": "%s: %s" % (type(exc).__name__, exc)}
print("SHELF_STL=" + json.dumps(rep))
sys.stdout.flush()
