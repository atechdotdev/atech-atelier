"""Example: "a smart photo frame" - a 5 x 7 wood picture frame round a small screen, leaning back on a fold-out stand.

fork this file for a photo frame / framed display (a picture frame, a
digital frame, a desk sign, a name plate, a framed message board - a flat
panel that leans back on a kickstand); change PARAMETERS and the outlines.
ARCHETYPE: frame

How it is built (R720):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board UPRIGHT_FRONT behind the picture (portrait, modules facing the
    front, -Y): the screen (10, 11) on the frame's centre line behind a
    bevelled mat window (the picture, portrait), the orientation sensor
    (5) beside it inside (it turns the picture portrait / landscape),
    USB-C (2) in a pocket with a liner in the right side; the button
    CABLED from port 7 straight down into the bottom rail, facing the
    front under a brass key; the light (the LED grid) CABLED from port 14
    straight out to the left, facing the BACK behind a frosted strip in
    the back - an ambient backlight on the wall. Each cabled module is
    held by ribs (and a pad) off the back. The frame is a solid moulding
    (Frame: a flat face, a bead groove, a chamfered sight edge) and a back
    box (Back: a front wall with the mat pocket, the cavity, the board's
    ledges and standoffs) screwed together from behind by four M2.5
    screws through columns into pilots in the moulding; the mat sits in
    the pocket, pegged into the moulding, a rib from it onto the board.
    Everything is built UPRIGHT and then TILTED back TILT degrees about
    the moulding's front-bottom edge (one Placement for the board, the
    cabled modules and every part); the moulding's bottom is cut to the
    desk and a fold-out kickstand, on a pin through a lug and its own
    knuckle, props it from behind.
  * STAGE B - details: the bead groove on the moulding, hex vents and a
    lettered brass badge on the back.
NOTE: no 2-port pair centres the screen on the board (3 + 4 fails its
seat check, MEASURED; 8 and 12 are reserved), so the board sits off the
frame's centre line and the frame is centred on the SCREEN.
DETAILS (visible, 20 of 28): 1 a flat wood moulding, soft outer edge;
2 its bead groove; 3 the chamfered sight edge; 4 a warm-white mat;
5 its 45 deg bevelled window round the screen; 6 brass key in the bottom
rail; 7 graphite back box, set in 3 mm from the moulding; 8 soft back
edges; 9 frosted backlight strip; 10 the hinge lug; 11 the stand's
knuckle; 12 chrome hinge pin; 13 the kickstand, tapered, its foot cut
flat on the desk; 14 USB-C pocket with liner in the right side; 15 hex
vents on the back; 16 a brass badge, lettered; 17-20 four countersunk
screws on the back. Inside: 21 board ledges and standoffs; 22 screw
columns back wall -> front wall; 23 pilots in the moulding; 24 ribs
above and below the light; 25 ribs and a pad round the button; 26 the
mat's four pegs in the moulding; 27 rib from the mat onto the board's
spine; 28 the liner round the USB-C socket.
Materials: wood moulding, warm-white mat, graphite back and stand,
frosted backlight strip, brass key and badge, chrome pin and screws.
MEASURED (R720, 2026-10-26): see test_kit_examples_r270 (TIMINGS line).
"""
import math
import time
import Part
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation
V = Vector
T0 = time.time()

INTENT = {"board": "upright", "fitted_after": [
    "Frame", "Back", "Mat", "Key", "Halo_Lens", "Badge", "Kickstand", "Hinge_Pin",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    # the key cap presses the cabled button through its opening
    "covers": {"Key": "button_7"}}
REVIEW_CLOSEUPS = ["Mat", "Kickstand", "Key"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them; test_kit_examples_r280 builds
# this file with each knob at its min and at its max, one at a time.
WIDTH = 136.0      # RESTYLE 115..157 width: the frame across (x); the sight takes the change
RELIEF = 6.0       # RESTYLE 5.0..7.0 height: the moulding's relief, its face to the mat (y)
CORNER = 8.0       # RESTYLE 6.5..9.5 radius: the frame's corners (the back box's 3 mm less)
WALL = 2.0         # RESTYLE 1.7..2.3 wall
# end RESTYLE
# R720: built UPRIGHT in a local frame (front = -Y, x across, z up, the
# desk at z = 0), then tilted back TILT degrees as one piece about the
# moulding's front-bottom edge. The picture (the screen) and the board
# are fixed by the hardware: never move them with a knob.
TILT = 12.0                      # the frame leans back this much
FH = 190.0                       # the frame's height (a 5 x 7 portrait; the board + the key set it)
SCREEN_C = (9.37, 39.99)         # MEASURED: the screen (10, 11) centre over the board's corner
CX, CZ = SCREEN_C[0], FH / 2     # the picture's centre = the screen's centre
MW = 30.0                        # the moulding's width (top and bottom; the sides follow WIDTH)
CHAMFER = 3.0                    # the sight edge's 45 deg chamfer
SIGHT_R = 2.0
REB = 4.0                        # the mat pocket round the sight
MAT_WIN = (18.0, 38.0)           # the mat's window at its back: the screen's face (19.5 x 39.5)
MAT_BACK = -10.4                 # 0.2 mm in front of the USB-C module (its face at -10.21)
MAT_T = 3.6
INSET = 3.0                      # the back box, set in from the moulding
KEY_D, KEY_Z = 9.0, 19.5         # the key in the bottom rail (the cabled button's centre)
HALO = (24.0, 14.0)              # the frosted backlight strip
KR, KW, KW_TIP = 4.0, 44.0, 34.0  # hinge knuckle r, stand width (hinge, foot)
T_K = 4.0                        # stand thickness
STAND_DEG = 28.0                 # the stand's angle from vertical (on the desk)
PIN_D = 2.0
COLOURS = {"Frame": "wood", "Back": "graphite", "Mat": "#f4f0e6", "Key": "brass",
           "Halo_Lens": "frosted", "Kickstand": "graphite", "Hinge_Pin": "chrome", "Badge": "brass", "Screw": "chrome"}

# the stack, front to back (derived): the moulding, the mat in the back
# box's front wall (its back flush with the wall's), the cavity
YR = MAT_BACK - MAT_T - 0.1                  # the moulding's back = the back box's front
YM = YR - RELIEF                             # the moulding's face
FX0 = CX - WIDTH / 2
SW, SH = WIDTH - 2 * MW, FH - 2 * MW         # the sight (the picture)
SX0, SX1, SZ0, SZ1 = CX - SW / 2, CX + SW / 2, CZ - SH / 2, CZ + SH / 2
ZH = 0.58 * FH                               # the hinge


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
UPRIGHT_FRONT = Rotation(Vector(0, 0, 1), 180)
TILT_PL = Placement(V(0, 0, 0), Rotation(V(1, 0, 0), -TILT), V(0, YM, 0))
TILT_M = TILT_PL.toMatrix()
Z0 = CZ - SCREEN_C[1]                           # the board's bottom edge
board = ap.board_object(doc)
board.Placement = Placement(V(), UPRIGHT_FRONT)
_b = ap.bbox(board)
board.Placement = TILT_PL.multiply(Placement(V(-_b.XMin, 0, Z0 - _b.ZMin), UPRIGHT_FRONT))
scr = ap.seat(doc, "screen", (10, 11))         # left column: the picture, portrait
imu = ap.seat(doc, "orientation", 5)            # right column: turns the picture portrait / landscape
usb = ap.seat(doc, "usbc", 2)                   # right column, mouth +X
# the key: CABLED from port 7 straight down (a straight drop: the
# cleanest ribbon), facing the front behind the bottom rail
btn, btn_rib = ap.cable(doc, "button", 7, TILT_PL.multiply(ap.module_placement(
    "button", (30.0, -3.48, KEY_Z), face="-Y", cable="+Z")))
# the backlight: CABLED from port 14 straight out to the left, facing the
# BACK (an ambient glow on the wall behind)
glow, glow_rib = ap.cable(doc, "light", 14, TILT_PL.multiply(ap.module_placement(
    "light", (-30.0, 2.3, Z0 + 110.0), face="+Y", cable="+X")))
tick("hardware")


def lbox(obj):
    """An Atech object's box in the LOCAL (untilted) frame."""
    g = (obj.Mesh if hasattr(obj, "Mesh") else obj.Shape).copy()
    g.Placement = TILT_PL.inverse().multiply(g.Placement)
    return g.BoundBox


def W_(s):
    """Local frame -> world (tilted back, standing on the moulding)."""
    s = s.copy()
    s.transformShape(TILT_M)
    return s


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, d, h):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def yprism(x0, x1, z0, z1, r, y0, y1):
    """A rounded rectangle in (x, z) extruded along Y from y0 to y1."""
    w = cad.rounded_rect_wire(x1 - x0, z1 - z0, r, ((x0 + x1) / 2, y0, (z0 + z1) / 2), "Y")
    s = Part.Face(w).extrude(V(0, y1 - y0, 0))
    if s.Volume < 0:
        s.reverse()
    return s


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


def frustum(w0, h0, w1, h1, r0, r1, y0, y1, cx, cz):
    """A rounded-rectangle frustum along Y: w0 x h0 at y0 to w1 x h1 at y1
    (a 45 deg chamfer or bevel cutter)."""
    a = cad.rounded_rect_wire(w0, h0, r0, (cx, y0, cz), "Y")
    b = cad.rounded_rect_wire(w1, h1, r1, (cx, y1, cz), "Y")
    return cad.loft([a, b], ruled=True)


def centre(b):
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


BB = lbox(board)
SB, IB, UB = lbox(scr), lbox(imu), lbox(usb)
KB, LB = lbox(btn), lbox(glow)
KRB, LRB = lbox(btn_rib[0]), lbox(glow_rib[0])
print("LOCAL board x %.1f..%.1f z %.1f..%.1f; key x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f; "
      "light x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f" % (
          BB.XMin, BB.XMax, BB.ZMin, BB.ZMax, KB.XMin, KB.XMax, KB.YMin, KB.YMax, KB.ZMin, KB.ZMax,
          LB.XMin, LB.XMax, LB.YMin, LB.YMax, LB.ZMin, LB.ZMax))
YB = LB.YMax + 0.4 + WALL                       # the back: its inner face 0.4 mm behind the light
YBI = YB - WALL
# the back box: set in INSET, its bottom lifted clear of the desk after the
# tilt (the desk is the plane z = (y - YM) tan TILT in the local frame)
TAN = math.tan(math.radians(TILT))
CB = (YB - YM) * TAN + 0.8
BX0, BX1, BZ1 = FX0 + INSET, FX0 + WIDTH - INSET, FH - INSET
IX0, IX1, IZ0, IZ1 = BX0 + WALL, BX1 - WALL, CB + WALL, BZ1 - WALL   # its cavity

# ------------------------------------------------------------ the moulding
frame = cad.rounded_box(WIDTH, RELIEF, FH, CORNER, at=(FX0, YM, 0), edges="y")
frame = cad.soften(frame, 2.0, [e for e in frame.Edges if e.BoundBox.YMax < YM + 0.05])
# the sight: a 45 deg chamfer at the face, then straight through
frame = cad.cut(frame, [frustum(SW + 2 * (CHAMFER + 0.5), SH + 2 * (CHAMFER + 0.5), SW, SH,
                                SIGHT_R + CHAMFER + 0.5, SIGHT_R, YM - 0.5, YM + CHAMFER, CX, CZ),
                        yprism(SX0, SX1, SZ0, SZ1, SIGHT_R, YM + CHAMFER - 0.2, YR + 1.0)])
tick("moulding")

# ------------------------------------------------------------ the back box
back = cad.rounded_box(BX1 - BX0, YB - YR, BZ1 - CB, CORNER - INSET, at=(BX0, YR, CB), edges="y")
back = cad.soften(back, 3.0, [e for e in back.Edges if e.BoundBox.YMin > YB - 0.05])
PX0, PX1, PZ0, PZ1 = SX0 - REB, SX1 + REB, SZ0 - REB, SZ1 + REB    # the mat pocket
back = cad.cut(back, [cad.rounded_box(IX1 - IX0, YBI - MAT_BACK, IZ1 - IZ0, max(1.0, CORNER - INSET - WALL),
                                      at=(IX0, MAT_BACK, IZ0), edges="y"),
                      yprism(PX0, PX1, PZ0, PZ1, SIGHT_R + REB, YR - 1.0, MAT_BACK + 1.0)])
tick("back box")
# the board: a ledge under its bottom edge (notched for the key's ribbon)
# and one over its top, standoffs 0.1 mm behind it
add = [box(BB.XMin + 3, KRB.XMin - 2, 0.6, YBI + 0.5, BB.ZMin - 2.3, BB.ZMin - 0.3),
       box(KRB.XMax + 2, BB.XMax - 3, 0.6, YBI + 0.5, BB.ZMin - 2.3, BB.ZMin - 0.3),
       box(BB.XMin + 3, BB.XMax - 3, 0.6, YBI + 0.5, BB.ZMax + 0.3, BB.ZMax + 2.3)]
add += [box(BB.XMin + x, BB.XMin + x + 6, BB.YMax + 0.1, YBI + 0.5, BB.ZMin + z, BB.ZMin + z + 6)
        for x in (6, 48) for z in (10, 55, 90)]
# the backlight's holder: ribs above and below (0.3 mm off), the back
# wall 0.4 mm behind its face; the key's: ribs either side, a pad behind
# (the light's cable leaves its +X side: its ribs are above and below it)
add += [box(LB.XMin + 2.0, LB.XMax - 2.0, LB.YMin + 1.0, YBI + 0.5, LB.ZMin - 1.6, LB.ZMin - 0.3),
        box(LB.XMin + 2.0, LB.XMax - 2.0, LB.YMin + 1.0, YBI + 0.5, LB.ZMax + 0.3, LB.ZMax + 1.6),
        box(KB.XMin - 1.6, KB.XMin - 0.3, KB.YMin + 1.0, YBI + 0.5, KB.ZMin + 2.0, KB.ZMax - 2.0),
        box(KB.XMax + 0.3, KB.XMax + 1.6, KB.YMin + 1.0, YBI + 0.5, KB.ZMin + 2.0, KB.ZMax - 2.0),
        box(KB.XMin + 3, KB.XMax - 3, KB.YMax + 0.2, YBI + 0.5, KB.ZMin + 4, KB.ZMax - 3)]
# four M2.5 screws from the back, through columns (back wall -> front
# wall) into pilots in the moulding: in the corners, under and over the board
SCREWS = [(x, z) for x in (IX0 + 6.0, IX1 - 6.0) for z in ((IZ0 + PZ0) / 2, IZ1 - 4.0)]
add += [cyl(3.0, (x, YBI + 0.5, z), (0, -1, 0), YBI - MAT_BACK + 1.0) for x, z in SCREWS]
back = cad.fuse_one(back, *add)
PILOT = min(5.0, RELIEF - 1.2)
SCREW_L = int(YB - YR + PILOT - 0.3)
screws = []
for x, z in SCREWS:
    back = cad.countersink(back, (x, YB, z), "-Y", 2.9, 4.9, 90.0)
    frame = cad.hole(frame, (x, YR, z), "-Y", 2.1, depth=PILOT)
    screws.append(cad.screw("csk_phillips", "M2.5", SCREW_L, at=(x, YB, z), axis="-Y"))
tick("board + screws")

# ------------------------------------------------------------ the mat, openings
mat = yprism(PX0 + 0.2, PX1 - 0.2, PZ0 + 0.2, PZ1 - 0.2, SIGHT_R + REB - 0.2, YR + 0.1, MAT_BACK)
sx, _sy, sz = centre(SB)
mw, mh = MAT_WIN
# the mat's window, bevelled 45 deg (wider at the front), on the screen
mat = cad.cut(mat, frustum(mw + 2 * MAT_T + 1.0, mh + 2 * MAT_T + 1.0, mw - 1.0, mh - 1.0, 2.5, 1.0,
                           YR - 0.4, MAT_BACK + 0.5, sx, sz))
# board retention: a rib from the mat's back onto the spine (0.2 mm off),
# in the board's middle column
mat = cad.fuse_one(mat, box(BB.XMin + 28, BB.XMin + 32, MAT_BACK - 0.5, BB.YMin - 0.2, BB.ZMin + 60, BB.ZMin + 70))
# four locating pegs on the mat's face, in the band the moulding's lip
# covers, into blind bores in the moulding (0.2 mm clear)
PEGS = [(x, z) for x in (SX0 - REB / 2, SX1 + REB / 2) for z in (CZ - SH / 4, CZ + SH / 4)]
mat = cad.fuse_one(mat, *[cyl(0.9, (x, YR + 0.6, z), (0, -1, 0), 2.2) for x, z in PEGS])
frame = cad.cut(frame, [cyl(1.1, (x, YR + 0.5, z), (0, -1, 0), 2.6) for x, z in PEGS])
# the key: a cap through the back box's front wall and the moulding,
# flange 0.1 mm behind the wall, a plunger to 0.16 mm off the button
kx, _ky, kz = centre(KB)
y_base = MAT_BACK + 0.9
cap = cad.button_cap(KEY_D, y_base - (YM - 1.2), dome=0.6, flange=1.5, at=(kx, y_base, kz), axis="-Y")
back = cad.opening_for(back, cap, clearance=0.25, chamfer=0.0, axis="-Y")
frame = cad.opening_for(frame, cap, clearance=0.25, chamfer=0.4, axis="-Y")
cap = cad.fuse_one(cap, cyl(2.5, (kx, KB.YMin - 0.16, kz), (0, -1, 0), (KB.YMin - 0.16) - y_base + 0.5))
# the backlight strip: a frosted insert that fills its window in the back
lx, _ly, lz = centre(LB)
halo_cut = yprism(lx - HALO[0] / 2, lx + HALO[0] / 2, lz - HALO[1] / 2, lz + HALO[1] / 2, 4.0, YBI - 1.0, YB + 1.0)
halo = back.common(halo_cut)
back = cad.cut(back, halo_cut)
# USB-C on the right side: a pocket through the wall, a liner from the
# wall to 0.25 mm off the socket mouth (its skin 0.3 mm behind the mat),
# and the plug opening through the liner's end (the mouth + 1.5 mm a side)
uy, uz = -5.9, (UB.ZMin + UB.ZMax) / 2
pocket = xprism(uy - 3.2, uy + 5.5, uz - 6.5, uz + 6.5, UB.XMax + 1.3, BX1 + 5, 3)
liner = cad.cut(xprism(MAT_BACK + 0.3, uy + 7.0, uz - 8.0, uz + 8.0, UB.XMax + 0.25, IX1 + 1.0, 3.5), pocket)
back = cad.fuse_one(cad.cut(back, pocket), liner)
back = cad.cut(back, xprism(uy - 3.25, uy + 3.25, uz - 6.5, uz + 6.5, UB.XMax - 0.1, UB.XMax + 2.0, 1.5))
tick("openings")
# the hinge: ONE lug off the back (the stand's knuckle beside it - each
# bore crosses one knuckle), a pin through both
YH = YB + KR + 0.4                              # the axis: the knuckle 0.4 mm off the back
LUG = (CX - KW / 2, CX - 0.15)
back = cad.fuse_one(back, cad.fuse_one(box(LUG[0], LUG[1], YB - 0.5, YH, ZH - KR, ZH + KR),
                                       cyl(KR, (LUG[0], YH, ZH), (1, 0, 0), LUG[1] - LUG[0])))
back = cad.cut(back, cyl(PIN_D / 2 + 0.2, (LUG[0] - 1, YH, ZH), (1, 0, 0), LUG[1] - LUG[0] + 2))
pin = cyl(PIN_D / 2, (LUG[0] + 0.3, YH, ZH), (1, 0, 0), KW - 0.6)
# the moulding's bottom cut to the desk: the plane the tilt lays flat
keep = box(-300, 400, -400, 400, 0, 600)
keep.rotate(V(0, YM, 0), V(1, 0, 0), TILT)
frame = frame.common(keep)
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# a bead groove round the moulding's face, BEAD in from its edge
BEAD = 6.0
groove = cad.cut(yprism(FX0 + BEAD, FX0 + WIDTH - BEAD, BEAD, FH - BEAD, CORNER - BEAD + 1.0, YM - 1.0, YM + 0.6),
                 yprism(FX0 + BEAD + 0.9, FX0 + WIDTH - BEAD - 0.9, BEAD + 0.9, FH - BEAD - 0.9,
                        max(0.5, CORNER - BEAD + 0.1), YM - 2.0, YM + 1.0))
frame = cad.cut(frame, groove)
# the back: hex vents low (under the board), lettering
back = cad.grille(back, (CX, YB, (IZ0 + BB.ZMin) / 2 + 4.0), (0, 1, 0), (50.0, 12.0), kind="hex", hole=3.0,
                  pitch=4.5)
# a brass badge inset in the back (an insert that fills its window in
# the wall), lettered
BADGE = (34.0, 11.0, ZH - 24.0)
badge_cut = yprism(CX - BADGE[0] / 2, CX + BADGE[0] / 2, BADGE[2] - BADGE[1] / 2, BADGE[2] + BADGE[1] / 2, 2.0,
                   YBI - 1.0, YB + 1.0)
badge = back.common(badge_cut)
back = cad.cut(back, badge_cut)
badge = cad.text(badge, "ATECH", (CX, YB, BADGE[2]), (0, 1, 0), 7, depth=0.3, mode="deboss")
tick("stage B")


# ------------------------------------------------------------ tilt + stand
parts = {k: W_(v) for k, v in (("Frame", frame), ("Back", back), ("Mat", mat), ("Key", cap),
                               ("Halo_Lens", halo), ("Badge", badge), ("Hinge_Pin", pin))}
screws = [W_(s) for s in screws]
# the kickstand in the WORLD: a tapered plate on a knuckle beside the lug,
# swung STAND_DEG back from vertical; long enough to reach the desk, its
# foot cut flat on it. In its own frame: the hinge axis along X through
# the origin, the plate hanging along -Z from 0.5 mm under the knuckles
H = TILT_PL.multVec(V(CX, YH, ZH))
phi = math.radians(STAND_DEG)
L = (H.z - T_K / 2 * math.sin(phi)) / math.cos(phi) + 3.0
z_top = -(KR + 0.5)
leg = Part.Face(Part.makePolygon([V(-KW / 2, 0, z_top), V(KW / 2, 0, z_top), V(KW_TIP / 2, 0, -L),
                                  V(-KW_TIP / 2, 0, -L), V(-KW / 2, 0, z_top)])).extrude(V(0, T_K, 0))
leg.translate(V(0, -T_K / 2, 0))
leg = cad.soften(leg, 1.2, [e for e in leg.Edges if e.BoundBox.ZMax < z_top - 0.05 or e.BoundBox.ZMin > z_top - 0.05])
stand = cad.fuse_one(leg, cyl(KR, (0.15, 0, 0), (1, 0, 0), KW / 2 - 0.15),
                     box(0.15, KW / 2, -T_K / 2, T_K / 2, z_top - 0.5, 0))
stand = cad.cut(stand, cyl(PIN_D / 2 + 0.2, (-1, 0, 0), (1, 0, 0), KW / 2 + 2))
stand.rotate(V(0, 0, 0), V(1, 0, 0), STAND_DEG)
stand.translate(V(CX, H.y, H.z))
parts["Kickstand"] = stand.common(box(-300, 400, -400, 400, 0, 600))
tick("tilt + stand")


# ------------------------------------------------------------ parts
def part(name, shape, colour):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour])
    return o


for nm, sh in parts.items():
    o = part(nm, sh, nm)
    if nm == "Halo_Lens":
        o.ViewObject.Transparency = cad.transparency(COLOURS[nm])
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
