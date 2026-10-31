# Starter (R820): "Just the board" - the Atech board lying flat in a printed
# tray, nothing seated yet. The place to start your own design: seat modules
# (ap.seat), then grow the tray into a case round them.
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation

FLAT = Rotation(Vector(1, 0, 0), 90)   # the board lying flat, components up
WALL = 2.0                             # tray floor and rim
CLEAR = 0.3                            # rim clearance round the board's edge
RIM = 1.2                              # rim height up the board's 2.5 mm edge:
                                       # low, so modules still plug in from the side

board = ap.board_object(doc)
board.Placement = Placement(Vector(0, 0, 0), FLAT)
# measured, not guessed: the board's flat underside lands on the tray floor
board.Placement = Placement(Vector(0, 0, WALL - cad.bound_of(board).ZMin), FLAT)
bb = cad.bound_of(board)

tray = cad.rounded_box(bb.XLength + 2 * (CLEAR + WALL), bb.YLength + 2 * (CLEAR + WALL),
                       WALL + RIM, 3.0,
                       at=(bb.XMin - CLEAR - WALL, bb.YMin - CLEAR - WALL, 0))
# the pocket the board drops into, 0.3 mm clear all round
tray = cad.cut(tray, cad.rounded_box(bb.XLength + 2 * CLEAR, bb.YLength + 2 * CLEAR,
                                     RIM + 1, 1.0,
                                     at=(bb.XMin - CLEAR, bb.YMin - CLEAR, WALL)))
doc.addObject("Part::Feature", "Tray").Shape = tray

INTENT = {"board": "flat"}
