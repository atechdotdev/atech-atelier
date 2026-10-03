"""Seed for stand_for_existing_part: the user's existing clock enclosure.

The clock body of the logged desk-stand session (fixtures/desk_stand_overlap.py,
first half, verbatim geometry): 107.4 x 26.0 x 147.9 mm, rounded vertical
edges, a front window recess, centred on X/Y with its base at z = 0.
Run by fc_build.py into the fresh document BEFORE the agent's model.py; gets
`doc`. The object is the user's, not the agent's (no AtechAgentBuilt).
"""
import Part
from FreeCAD import Vector

CW, CT, CH = 107.4, 26.0, 147.9
CR = 6.0


def rounded_slab(w, d, h, r):
    box = Part.makeBox(w, d, h)
    verticals = [e for e in box.Edges
                 if abs(e.Vertexes[0].Point.z - e.Vertexes[-1].Point.z) > h * 0.5]
    return box.makeFillet(r, verticals)


clock = rounded_slab(CW, CT, CH, CR)
clock = clock.cut(Part.makeBox(CW - 20.0, 2.5, CH - 36.0, Vector(10.0, -0.01, 24.0)))
clock.translate(Vector(-CW / 2.0, -CT / 2.0, 0))

obj = doc.addObject("Part::Feature", "Clock_Enclosure")
obj.Shape = clock
