# Starter (R820): "Board in a case" - the Atech board lying flat in a simple
# two-part case: a base that holds the board and a rounded cover that goes on
# after the modules, held by four screws up through the base. A button and a
# light sit under openings in the top. Adapt it: change the modules and
# ports, the case's size and corners, then add your own details.
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation

FLAT = Rotation(Vector(1, 0, 0), 90)   # the board lying flat, components up
WALL = 2.0                             # case walls, floor and top
CLEAR = 0.3                            # clearance round the board's edge
MARGIN = 6.0                           # room beside the board for the screws
TOP_AIR = 1.0                          # air over the tallest module
R = 6.0                                # the case's corner radius
RIM = 1.2                              # base rim up the board's edge (low, so
                                       # modules still slide in from the side)
COLOURS = {"Base": "graphite", "Cover": "matte_white", "Screw": "chrome"}

board = ap.board_object(doc)
board.Placement = Placement(Vector(0, 0, 0), FLAT)
# measured, not guessed: the board's flat underside lands on the base floor
board.Placement = Placement(Vector(0, 0, WALL - cad.bound_of(board).ZMin), FLAT)
pcb = cad.bound_of(board)
mods = [ap.seat(doc, "button", 3), ap.seat(doc, "light", 11)]
bb = cad.bound_of(board, *mods)

X0, X1 = bb.XMin - CLEAR - MARGIN, bb.XMax + CLEAR + MARGIN
Y0, Y1 = bb.YMin - CLEAR - MARGIN, bb.YMax + CLEAR + MARGIN
TOP = bb.ZMax + TOP_AIR + WALL                     # outside top of the cover
BASE_T = WALL + RIM                                # base: floor + rim

# Base: a plate with a pocket the board drops into, 0.3 mm clear all round.
base = cad.rounded_box(X1 - X0, Y1 - Y0, BASE_T, R, at=(X0, Y0, 0))
base = cad.cut(base, cad.rounded_box(pcb.XLength + 2 * CLEAR, pcb.YLength + 2 * CLEAR,
                                     RIM + 1, 1.0,
                                     at=(pcb.XMin - CLEAR, pcb.YMin - CLEAR, WALL)))

# Cover: a rounded shell standing on the base, open at the bottom.
cover = cad.rounded_box(X1 - X0, Y1 - Y0, TOP - BASE_T, R, at=(X0, Y0, BASE_T))
cover = cad.shell(cover, WALL, cad.faces_at(cover, "-Z"))
# A button must be pressed and a light seen: open the top over each
# module's working face (its "up" face), sized from its measured box.
cover = cad.cut(cover, [cad.rounded_box(ap.bbox(m).XLength - 4, ap.bbox(m).YLength - 4,
                                        WALL + 2, 1.5,
                                        at=(ap.bbox(m).XMin + 2, ap.bbox(m).YMin + 2,
                                            TOP - WALL - 1))
                        for m in mods])

# Four M2 screws up through the base into bosses in the cover's corners.
screws = []
for x in (X0 + MARGIN / 2 + 0.5, X1 - MARGIN / 2 - 0.5):
    for y in (Y0 + MARGIN / 2 + 0.5, Y1 - MARGIN / 2 - 0.5):
        base, cover = cad.screw_through(base, cover, (x, y, 0), size="M2", ribs=0)
        screws.append(cad.screw("csk_phillips", "M2", 6, at=(x, y, 0), axis="+Z"))

for name, shape in (("Base", base), ("Cover", cover)):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[name])
for i, s in enumerate(screws):
    o = doc.addObject("Part::Feature", "Screw_%d" % (i + 1))
    o.Shape = s
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])

# intent.json for this example (write it before model.py): the cover and
# its screws go on after the modules, so ./check tests the modules' slide
# paths without them.
INTENT = {"board": "flat", "fitted_after": ["Cover", "Screw_1", "Screw_2",
                                            "Screw_3", "Screw_4"]}
