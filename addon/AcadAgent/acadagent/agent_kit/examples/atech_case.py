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
# R270: something must HOLD the board (./check: "nothing holds the board"):
# a card-guide slot on the case floor - two rails 0.1 mm clear of the
# board's faces, rising 2 mm up its bottom edge.
pb = cad.bound_of(board)
floor = bb.ZMin - C                   # inner face of the floor
rails = [Part.makeBox(pb.XLength - 4, 1.2, pb.ZMin + 2 - floor + 0.5,
                      Vector(pb.XMin + 2, y, floor - 0.5))
         for y in (pb.YMin - 0.1 - 1.2, pb.YMax + 0.1)]
for m in mods:                        # the module side's rail stops 0.5 mm
    mb = ap.bbox(m)                   # short of each module
    keep_out = Part.makeBox(mb.XLength + 1, mb.YLength + 1, mb.ZLength + 1,
                            Vector(mb.XMin - 0.5, mb.YMin - 0.5, mb.ZMin - 0.5))
    if keep_out.common(rails[1]).Volume > 0:
        rails[1] = cad.cut(rails[1], keep_out)
case = cad.fuse_one(case, *rails)
doc.addObject("Part::Feature", "Case").Shape = case
# The ends are CLOSED by end caps in their closed position: every module
# must be enclosed on every side but its working face. A cap is a plate
# touching the case end (not overlapping it) with a lip L deep in the
# opening, G clear of the walls - a flat plate alone only touches and falls
# off (./check's joint line). They are listed in intent.json
#   "fitted_after": ["End_Cap_L", "End_Cap_R"]
# so ./check tests the slide paths without the caps (they go on after the
# modules) and still tests every overlap with them in place.
cb = case.BoundBox
L, G, T = 2.0, 0.15, 0.8       # lip depth, clearance to the walls, lip wall
for name, x, d in (("End_Cap_L", cb.XMin - W, 1), ("End_Cap_R", cb.XMax, -1)):
    plate = cad.rounded_box(W, cb.YLength, cb.ZLength, 0, at=(x, cb.YMin, cb.ZMin))
    x0 = cb.XMin - 0.5 if d > 0 else cb.XMax - L     # 0.5 mm into the plate
    iy, iz = cb.YLength - 2 * (W + G), cb.ZLength - 2 * (W + G)
    lip = cad.cut(Part.makeBox(L + 0.5, iy, iz, Vector(x0, cb.YMin + W + G, cb.ZMin + W + G)),
                  Part.makeBox(L + 2, iy - 2 * T, iz - 2 * T,
                               Vector(x0 - 0.75, cb.YMin + W + G + T, cb.ZMin + W + G + T)))
    doc.addObject("Part::Feature", name).Shape = cad.fuse_one(plate, lip)

# intent.json for this example (write it before model.py)
INTENT = {"board": "upright", "fitted_after": ["End_Cap_L", "End_Cap_R"]}
