"""Example: "the Sesame walking robot refitted for the Atech board and screen, same servos"

A remix of an open design. Sesame (Dorian Todd's quadruped, Apache-2.0)
keeps everything below its top cover exactly as upstream prints it: the
internal frame, the bottom cover, the 14500 battery, the eight MG90S servos
and the eight leg parts (agent_kit/third_party/sesame, see its NOTICE.md; its
STEP made into BREPs by projects/import_sesame.py). Only the top cover is new:

  Deck  screws onto the frame with the original four M2 screws. A spine the
        width of the original cover rises between the hips to a tray just
        over the femurs, which holds the Atech 14-port board flat on four
        posts with a 5 mm gap under it for the cables, and a head in front
        that holds the screen behind a 36 x 17 mm window.
  Lid   closes the tray and the head (fitted after the modules), three M2
        screws down into bosses in the deck's side bays, and holds the
        screen's back with a rib.

Hardware: the board lies flat, the USB-C module on port 8 at the back, the
IMU ("orientation", the SDK's icm40608: the walk steers by its heading) on
port 13, the screen cabled from ports 10+11, upright in the head with its
connector edge down. Its two ribbons loop down into the right bay, run flat
under the board and come up into the screen from below. The servo leads plug
into ports 2-5 (one leg each: hip on line A, knee on line B) and drop through
the spine to the servos.

The outline is MEASURED, not guessed: every pose of the firmware's
movement-sequences.h replayed on these legs. Above the femur tops the legs
reach the front and rear corners beyond |x| 37 and x 12..26 behind y 56 (the
dance pose lifts the rear feet there). So the tray is |x| <= 32.3 at both
ends, the side bays reach |x| 38 only between y -49.5 and 40 (a 36.8 step in
front of that), the back wall stops at y 54.9, and the head (|x| <= 23, down
to z 64) sits where no leg rises above z 57.

Numbered features: 1 spine with the four frame screw bosses; 2 tray floor and
lead slot; 3 board posts; 4 tray walls up to the board's top face; 5 side bays;
6 head with the screen window and its side ribs; 7 lid with the USB-C opening
and the screen's back rib; 8 lid screws into bay bosses.
"""
import gzip
import os

import Part
from FreeCAD import Vector, Placement, Rotation

import atech_geom
import atech_ports as ap
import atech_cad as cad

V = Vector
PARTS_DIR = os.path.join(os.path.dirname(atech_geom.__file__), "third_party", "sesame")


def sesame(name):
    """One upstream Sesame part, already in this frame (z up, front -Y)."""
    s = Part.Shape()
    with gzip.open(os.path.join(PARTS_DIR, name + ".brep.gz"), "rt", encoding="utf-8") as fh:
        s.importBrepFromString(fh.read())
    return s.Solids[0]


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def plan(pieces, z0, z1, grow=0.0):
    """Fuse rounded plan pieces (x0, x1, y0, y1, r) into one prism z0..z1,
    each grown by `grow` (negative shrinks: a wall's inside)."""
    return cad.fuse_one(*[cad.rounded_box(x1 - x0 + 2 * grow, y1 - y0 + 2 * grow, z1 - z0,
                                          max(0.5, r + grow), at=(x0 - grow, y0 - grow, z0))
                          for x0, x1, y0, y1, r in pieces])


UPSTREAM = ["frame", "bottom_cover", "battery"] + \
    ["femur_" + k for k in ("L1", "L2", "R1", "R2")] + ["foot_" + k for k in ("L3", "L4", "R3", "R4")] + \
    ["servo_%s_%s" % (j, s) for j in ("hip", "knee") for s in ("FL", "FR", "RL", "RR")]
SHAPES = {n: sesame(n) for n in UPSTREAM}

# === PARAMETERS (measured from the upstream parts where they matter) ===
FRAME_TOP = SHAPES["frame"].BoundBox.ZMax                      # 53.80
FEMUR_TOP = max(SHAPES["femur_" + k].BoundBox.ZMax for k in ("L1", "L2", "R1", "R2"))   # 71.75
FRAME_SCREW_Z = FRAME_TOP - 1.27     # the screws' heads sit under the frame's 1.27 mm top plate
FRAME_SCREWS = ((16.785, 36.04), (-16.785, 36.04), (15.93, -33.62), (-15.93, -33.62))
BOTTOM_SCREW_Z = SHAPES["bottom_cover"].BoundBox.ZMax - 1.27 - 0.2   # 0.2 mm under its seat
BOTTOM_SCREWS = ((0.0, -29.46), (0.0, 30.67))
SPINE = 18.5                 # half width: the original cover's (18.69); the femurs swing outside it
SPINE_Y = 39.61              # the frame's ends
WALL = 2.0
FLOOR_Z0 = FEMUR_TOP + 1.2   # tray underside, over the femur tops
LEAD_GAP = 5.0               # under the board: the ribbons and servo leads
BOARD_Y = -8.0               # board centre: 8 mm forward, clear of the rear feet (back wall < y 56)
CLEAR = 0.3                  # round the board
BAY_X, BAY_Y = 38.0, (-49.5, 40.0)  # MEASURED: above the floor the legs stay beyond |x| 39.7 there
HEAD_X, HEAD_Z0 = 23.0, 64.0
LID_SCREWS = ((33.3, 35.5), (-33.3, 35.5), (-33.3, -2.5))   # in the bays, clear of leads, ribbons, the IMU and the walls
COLOURS = {"frame": "graphite", "bottom": "graphite", "battery": "satin_grey",
           "femur": "matte_white", "foot": "matte_white", "servo": "toy_blue",
           "Deck": "matte_white", "Lid": "sky", "Screw": "chrome"}

# === HARDWARE ===
board = ap.board_object(doc)
FLAT_BACK = Rotation(V(0, 0, 1), 180).multiply(Rotation(V(1, 0, 0), 90))   # components up, port 8 at +Y
board.Placement = Placement(V(), FLAT_BACK)
b0 = ap.bbox(board)
BOARD_Z0 = FLOOR_Z0 + WALL + LEAD_GAP
board.Placement = Placement(V(-(b0.XMin + b0.XMax) / 2, BOARD_Y - (b0.YMin + b0.YMax) / 2,
                              BOARD_Z0 - b0.ZMin), FLAT_BACK)
BB = ap.bbox(board)
PCB_TOP = BB.ZMin + 2.5      # the face modules seat on (MEASURED: 2.5 above the underside)
usb = ap.seat(doc, "usbc", 8)
imu = ap.seat(doc, "orientation", 13)       # heading for the walk (the firmware steers by it)
UB = ap.bbox(usb)
X0, X1 = BB.XMin - CLEAR - WALL, BB.XMax + CLEAR + WALL
Y0 = BB.YMin - CLEAR - WALL                  # front of the tray
Y1 = UB.YMax + 0.25 + WALL                   # back wall just behind the USB-C mouth
HY0 = Y0 - 15.0                              # front of the head
FT, BU = FLOOR_Z0 + WALL, BB.ZMin            # floor top, board underside
# the screen: upright behind the head's front wall (0.2 mm off it), its
# connector edge down; the ribbons run flat under the board, one above the
# other, and come up into it from below
SCREEN_C = (0.0, HY0 + WALL + 0.2 + 9.64 / 2, BU - 8.6 + 19.5 / 2)
# the ribbons' waypoints: found by an offline search over this geometry
# (no ribbon within 0.3 mm of the board, the floor, the bay walls, the
# screen or the lid; 1.0 mm between them; no twist) - each leaves its plug
# outward, loops down into the bay, runs flat under the board (port 10's
# low, port 11's above it) and drops in front of the board into the screen
ROUTE = {
    10: [(-34.69, -38.52, 81.25), (-34.32, -38.9, 78.31), (-26.87, -41.63, 78.56),
         (-22.72, -46.71, 78.44), (-14.32, -61.97, 78.07), (-12.8, -69.35, 78.0),
         (-10.21, -72, 72.08), (-8.71, -73.86, 68.07)],
    11: [(-33.86, -18.94, 81.89), (-32.65, -18.38, 77.88), (-27.53, -21.92, 77.51),
         (-12.12, -39.25, 76.21), (-2.21, -53.92, 78.28), (9.34, -66.29, 77.49),
         (9.7, -70.03, 76.26), (9.89, -72.2, 74.18), (10.32, -72.07, 68.51)]}
scr, ribbons = ap.cable(doc, "screen", (10, 11), ap.module_placement(
    "screen", SCREEN_C, face="-Y", cable="-Z"), via=ROUTE, smooth=True)
SB = ap.bbox(scr)

# === DECK ===
TRAY = [(X0, X1, Y0, Y1, 4.0), (-BAY_X, BAY_X, BAY_Y[0], BAY_Y[1], 4.0),
        # a narrower step at the bays' front: port 10's ribbon loops 1 mm
        # past y -48; the feet come to |x| 37.95 between y -52 and -50
        (-BAY_X + 1.2, BAY_X - 1.2, BAY_Y[0] - 1.5, BAY_Y[0] + 8.0, 2.5)]
HEADP = [(-HEAD_X, HEAD_X, HY0, Y0 + WALL, 4.0)]
TOP = PCB_TOP - 0.3          # the deck stops under the modules' slide paths
# 1 spine: a tube the original cover's size, open into the frame below
spine = cad.cut(box(-SPINE, SPINE, -SPINE_Y, SPINE_Y, FRAME_TOP, FLOOR_Z0 + 0.5),
                box(-SPINE + WALL, SPINE - WALL, -SPINE_Y + WALL, SPINE_Y - WALL, FRAME_TOP - 1, FLOOR_Z0 + 1))
bosses = [Part.makeCylinder(2.4, 9.0, V(x, y, FRAME_TOP)) for x, y in FRAME_SCREWS]
# 2-5 tray: floor, walls, bays, four posts under the board's corners
tray = cad.cut(plan(TRAY, FLOOR_Z0, TOP), plan(TRAY, FT, TOP + 1, grow=-WALL))
posts = [box(x - 2, x + 2, y - 2, y + 2, FT - 0.5, BU - 0.1)
         for x in (BB.XMin + 3, BB.XMax - 3) for y in (BB.YMin + 3, BB.YMax - 3)]
# 6 head: in front of the tray and lower, open at the top into the lid
head = cad.cut(plan(HEADP, HEAD_Z0, TOP), plan(HEADP, HEAD_Z0 + WALL, TOP + 1, grow=-WALL))
deck = cad.fuse_one(spine, tray, head, *(bosses + posts))
deck = cad.cut(deck, [
    # the tray's front wall gives way to the head above the floor (the
    # screen's back rib fences the board); below it, it is the head's back
    box(-HEAD_X + WALL, HEAD_X - WALL, Y0 - 1, Y0 + WALL + 0.5, FT, TOP + 1),
    # the lead slot: the spine's inside, up through the floor
    box(-SPINE + WALL, SPINE - WALL, -SPINE_Y + WALL, SPINE_Y - WALL, FLOOR_Z0 - 1, FT + 1)] +
    # the frame screws' thread-forming pilots (M2: 1.7 mm), from below
    [Part.makeCylinder(0.85, 7.0, V(x, y, FRAME_TOP - 0.5)) for x, y in FRAME_SCREWS])
# the window shows the 25.6 x 13.5 active area with room to spare; the frame
# round it is the lip the screen's face rests 0.2 mm behind
FACE_C = ((SB.XMin + SB.XMax) / 2, SB.ZMin + 19.5 / 2)
WIN = Part.Face(cad.rounded_rect_wire(36.0, 17.0, 2.0, (FACE_C[0], HY0 - 1.0, FACE_C[1]), "Y")).extrude(V(0, WALL + 2.0, 0))
deck = cad.cut(deck, WIN)
# side ribs 0.2 mm off the screen's ends (the lid's rib holds its back)
deck = cad.fuse_one(deck, *[box(x0, x1, SB.YMin + 1.0, SB.YMax + 2.0, HEAD_Z0 + WALL - 0.5, TOP)
                            for x0, x1 in ((SB.XMin - 1.8, SB.XMin - 0.2), (SB.XMax + 0.2, SB.XMax + 1.8))])

# === LID ===
LID_TOP = UB.ZMax + 0.6 + WALL
lid = cad.cut(cad.fuse_one(plan(TRAY, TOP, LID_TOP), plan(HEADP, TOP, LID_TOP)),
              [plan(TRAY, TOP - 1, LID_TOP - WALL, grow=-WALL),
               plan(HEADP, TOP - 1, LID_TOP - WALL, grow=-WALL),
               # one space: the head's inside joins the tray's
               box(-HEAD_X + WALL, HEAD_X - WALL, Y0 - 1, Y0 + WALL + 1, TOP - 1, LID_TOP - WALL), WIN])
lid = cad.socket_opening(lid, usb, margin=1.5)
# a rib down from the lid 0.2 mm behind the screen's top half
lid = cad.fuse_one(lid, box(SB.XMin + 2.0, SB.XMax - 2.0, SB.YMax + 0.2, SB.YMax + 1.8, TOP + 0.3, LID_TOP - WALL + 0.5))
lid_screws = []
for x, y in LID_SCREWS:
    lid, deck = cad.screw_through(lid, deck, (x, y, LID_TOP), size="M2", ribs=0)
    lid_screws.append(cad.screw("csk_phillips", "M2", 10, at=(x, y, LID_TOP), axis="-Z"))

# === SCREWS (upstream's, where upstream puts them) ===
screws = [cad.screw("pan_phillips", "M2", 8, at=(x, y, FRAME_SCREW_Z), axis="+Z") for x, y in FRAME_SCREWS]
screws += [cad.screw("pan_phillips", "M2", 8, at=(x, y, BOTTOM_SCREW_Z), axis="+Z") for x, y in BOTTOM_SCREWS]

# === OBJECTS ===
for n in UPSTREAM:
    o = doc.addObject("Part::Feature", n)
    o.Shape = SHAPES[n]
    o.ViewObject.ShapeColor = cad.color(COLOURS[n.split("_")[0]])
for name, shape in (("Deck", deck), ("Lid", lid)):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[name])
for i, s in enumerate(screws + lid_screws):
    o = doc.addObject("Part::Feature", "Screw_%d" % (i + 1))
    o.Shape = s
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])

# upstream fits: each servo horn is pressed into its femur, and each knee
# servo sits in its femur's pocket (the leg shell slides over the motor)
INTENDED_OVERLAPS = [("femur_" + f, "servo_%s_%s" % (j, s)) for j in ("hip", "knee")
                     for f, s in (("L1", "FL"), ("L2", "RL"), ("R1", "FR"), ("R2", "RR"))]

# "imported": Sesame's own parts, printed as upstream made them - ./check
# judges their fit, not their walls
INTENT = {"board": "flat", "fitted_after": ["Lid"],
          "imported": ["frame", "bottom_cover", "battery", "femur_L1", "femur_L2", "femur_R1", "femur_R2",
                       "foot_L3", "foot_L4", "foot_R3", "foot_R4", "servo_hip_FL", "servo_hip_FR",
                       "servo_hip_RL", "servo_hip_RR", "servo_knee_FL", "servo_knee_FR",
                       "servo_knee_RL", "servo_knee_RR"]}
