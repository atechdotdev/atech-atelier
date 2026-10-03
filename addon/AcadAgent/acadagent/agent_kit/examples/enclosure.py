# Example: a hollow enclosure (open top, 2 mm walls) and a matching lid with
# a locating lip. Two separate parts -> two objects.
import atech_cad as cad

X, Y, Z = 80.0, 50.0, 30.0     # outside size of the box
WALL, R = 2.0, 4.0             # wall thickness, vertical corner radius
CLEAR = 0.2                    # lip-to-wall clearance per side (FDM)

box = cad.rounded_box(X, Y, Z, R)                         # solid block first
box = cad.shell(box, WALL, cad.faces_at(box, "+Z"))       # remove the top face
# Four M3 screw holes through the floor, drilled up from the bottom (z=0).
# through="wall" stops at the first wall: a hole in one wall of a hollow part
# never runs on into the wall behind it (through=True drills everything on
# the axis).
for x in (10.0, X - 10.0):
    for y in (10.0, Y - 10.0):
        box = cad.hole(box, at=(x, y, 0), axis="+Z", d=3.2, through="wall")

# Lid: a plate plus a lip that drops inside the walls.
lid = cad.rounded_box(X, Y, WALL, R, at=(0, 0, Z + 5))
lip = cad.rounded_box(X - 2 * (WALL + CLEAR), Y - 2 * (WALL + CLEAR), 3.0,
                      max(R - WALL - CLEAR, 0.5),
                      at=(WALL + CLEAR, WALL + CLEAR, Z + 5 - 3.0 + 0.5))
lid = cad.fuse_one(lid, lip)                              # 0.5 mm overlap joins them

doc.addObject("Part::Feature", "Enclosure").Shape = box
doc.addObject("Part::Feature", "Lid").Shape = lid
