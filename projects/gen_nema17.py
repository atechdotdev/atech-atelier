"""gen_nema17 — write models/stl/nema17_stepper.stl.

    freecadcmd projects/gen_nema17.py        # from the repository root

WHERE EVERY NUMBER COMES FROM
    The NEMA 17 face is a standard (NEMA ICS 16): a 42.3 mm square flange,
    four M3 holes on a 31.0 mm square, a 22.0 mm pilot boss 2.0 mm proud and
    a 5.0 mm shaft. Those are the dimensions a mount is designed against, and
    they hold for every NEMA 17 (studio's stepper_motor module drives one; the
    two studio's parts list stocks, Elextra H59658/H59659, are NEMA 17s).

    What the standard does NOT fix, and this mesh therefore states as a
    choice rather than a fact: the body length (34, 40 and 48 mm are all
    common; 40 is used), the shaft length (24 mm, the usual), the corner
    chamfer and the hole depth. A design that depends on any of them must
    measure the real motor. presets.yaml says the same in agent_notes.

FRAME
    The mounting face is the plane y = 0, the shaft points +Y along the
    vertical axis through x = z = 0, and the body hangs below to y = -40.
    So a motor placed at a plate's top face stands on its own flange.
"""
import os

import FreeCAD
import Mesh
import MeshPart
import Part

FLANGE = 42.3          # square, mm (standard)
HOLE_PITCH = 31.0      # M3 holes on this square (standard)
HOLE_D = 3.0           # M3 thread, drawn as its nominal diameter
HOLE_DEPTH = 4.5       # choice: typical tapped depth
PILOT_D = 22.0         # standard
PILOT_H = 2.0          # standard
SHAFT_D = 5.0          # standard
SHAFT_L = 24.0         # choice: the usual length past the flange face
FLAT_DEPTH = 0.5       # choice: D-flat 4.5 mm across, the common cut
FLAT_L = 15.0          # choice: length of the D-flat from the shaft tip
BODY_L = 40.0          # choice: one of the common body lengths
CHAMFER = 5.0          # choice: corner chamfer of the square body

V = FreeCAD.Vector


def build():
    body = Part.makeBox(FLANGE, BODY_L, FLANGE, V(-FLANGE / 2, -BODY_L, -FLANGE / 2))
    edges = [e for e in body.Edges
             if abs(e.Vertexes[0].Point.y - e.Vertexes[1].Point.y) > BODY_L - 1e-6]
    body = body.makeChamfer(CHAMFER, edges)
    h = HOLE_PITCH / 2
    for sx in (-1, 1):
        for sz in (-1, 1):
            hole = Part.makeCylinder(HOLE_D / 2, HOLE_DEPTH, V(sx * h, -HOLE_DEPTH, sz * h),
                                     V(0, 1, 0))
            body = body.cut(hole)
    pilot = Part.makeCylinder(PILOT_D / 2, PILOT_H, V(0, 0, 0), V(0, 1, 0))
    shaft = Part.makeCylinder(SHAFT_D / 2, SHAFT_L, V(0, 0, 0), V(0, 1, 0))
    flat = Part.makeBox(SHAFT_D, FLAT_L, SHAFT_D,
                        V(SHAFT_D / 2 - FLAT_DEPTH, SHAFT_L - FLAT_L, -SHAFT_D / 2))
    shaft = shaft.cut(flat)
    return body.fuse([pilot, shaft]).removeSplitter()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(os.path.dirname(here), "models", "stl", "nema17_stepper.stl")
    shape = build()
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.05,
                                  AngularDeflection=0.2, Relative=False)
    mesh.write(out)
    bb = Mesh.Mesh(out).BoundBox
    print("wrote %s: %d facets, %.2f x %.2f x %.2f mm"
          % (out, mesh.CountFacets, bb.XLength, bb.YLength, bb.ZLength))


main()
