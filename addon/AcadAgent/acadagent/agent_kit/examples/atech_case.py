# Example: the Atech board standing upright with a button and a speaker
# module, in a case that rests exactly on the desk (z = 0). Adapt it: change
# the modules and ports, then refine the case (lid, snaps, openings).
import Part
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation

W, C = 2.0, 1.0                # case wall, clearance around the electronics
board = ap.board_object(doc)


def seat_all(lift):
    # The board's Placement is set BEFORE seating: modules follow it.
    # Rotation() = upright; Rotation(Vector(1, 0, 0), 90) lays it flat.
    board.Placement = Placement(Vector(0, 0, lift), Rotation())
    return [ap.seat(doc, "button", 3), ap.seat(doc, "speaker", (9, 10))]


mods = seat_all(0)
low = cad.bound_of(board, *mods).ZMin
for m in mods:                 # measured, not guessed: seat again so the
    ap.remove(doc, m.AtechPorts[0])    # case bottom lands exactly on z = 0
mods = seat_all(W + C - low)
bb = cad.bound_of(board, *mods)

case = cad.rounded_box(bb.XLength + 2 * (W + C), bb.YLength + 2 * (W + C),
                       bb.ZLength + 2 * (W + C), 0,
                       at=(bb.XMin - W - C, bb.YMin - W - C, bb.ZMin - W - C))
# Open at both X ends: modules on ports 1-6 and 9-14 slide in along X, so a
# closed wall there blocks their slide path (./check fails slide_path).
case = cad.shell(case, W, cad.faces_at(case, "+X") + cad.faces_at(case, "-X"))
# A button must be pressed and a speaker heard: open the wall IN FRONT OF
# each module's working face (the +Y side, away from the board), sized from
# the module's measured box. ./check's OPEN lines say how much of each face
# can see out (a window cut elsewhere does not count).
y_wall = bb.YMax + C                  # inner face of the +Y wall
windows = []
for m in mods:
    mb = ap.bbox(m)
    windows.append(Part.makeBox(mb.XLength - 4, W + 1, mb.ZLength - 4,
                                Vector(mb.XMin + 2, y_wall - 0.5, mb.ZMin + 2)))
case = cad.cut(case, windows)
doc.addObject("Part::Feature", "Case").Shape = case
# To CLOSE the ends: add end caps in their closed position (flush with the
# case, touching - not overlapping it) and list them in intent.json:
#   "fitted_after": ["End_Cap_L", "End_Cap_R"]
# ./check then tests the slide paths without the caps (they go on after the
# modules) and still tests every overlap with them in place.
