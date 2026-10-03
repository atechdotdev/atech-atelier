# Example: an L-bracket with four M4 through holes and filleted outer edges.
# A complete model.py - `doc` and `App` are given; everything else is imported.
import atech_cad as cad

W, L, H, T = 40.0, 60.0, 35.0, 5.0      # width, base length, upright height, plate
HOLE_D = 4.5                            # M4 clearance

base = cad.rounded_box(L, W, T, 0)                       # corner at origin, z 0..T
upright = cad.rounded_box(T, W, H, 0, at=(0, 0, 0))      # x 0..T, rises to z=H
body = cad.fuse_one(base, upright)                       # raises unless ONE solid

# Base holes: drilled DOWN from the top face (z = T) -> axis '-Z'.
for x in (25.0, 48.0):
    for y in (10.0, W - 10.0):
        body = cad.hole(body, at=(x, y, T), axis="-Z", d=HOLE_D, through=True)
# Upright holes: drilled from the outer face (x = 0) INTO the part -> '+X'.
for y in (10.0, W - 10.0):
    body = cad.hole(body, at=(0, y, 25.0), axis="+X", d=HOLE_D, through=True)

# Round the two far corners of the base only. fillet_safe returns a shape:
# on failure the sharp part, unchanged (the reason is printed).
body = cad.fillet_safe(
    body, 4.0, [e for e in cad.edges_parallel(body, "Z")
                if e.Vertexes[0].Point.x > L - 0.01])

obj = doc.addObject("Part::Feature", "Bracket")
obj.Shape = body
