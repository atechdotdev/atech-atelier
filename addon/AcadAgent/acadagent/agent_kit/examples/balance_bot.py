"""Example: "a self-balancing robot" - a two-wheeled inverted pendulum with a screen face.

fork this file for a balancing robot (a two-wheeled self-balancing bot, a
segway-style toy, an inverted-pendulum robot, a wheeled character that
stands on two wheels); change PARAMETERS and the outlines.
ARCHETYPE: balancing robot

How it is built (R803):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board UPRIGHT_FRONT (portrait, modules face -Y), its height set by the
    wheels (shaft centre = WHEEL_R). dc_motor SEATED on 1 and 9: the
    shafts point out sideways at the bottom, an n20 hub (the library's
    n20_wheel coupler, its D-flat on the shaft's flat) on each, and each
    road wheel's rim drives through a HEX SOCKET round that hub. The
    orientation module on 7: on the centre line, level with the axle,
    square to the body, sealed behind the front (2.6 mm air). The face:
    the screen on (13, 14) behind a smoked window with a light tunnel and
    the light on 6 behind a domed status eye, both in a black face plate;
    the START key on 3 (a cap through the front, a plunger); USB-C on 4 in
    a pocket in the right flank. Ports 8 and 12 stay empty (reserved). The
    body is ONE front silhouette (hips between the wheels, a waist, a
    wider head with big round corners) x one plan (cad.profile_body,
    lines + exact arcs, filleted), hollowed with its own core and split
    FRONT / BACK behind the board (the back is fixed: ledges and standoffs
    hold the board; a rib from the front sits on its spine). Four M2.5
    screws from the back into insert bosses in the front. Fenders over the
    tyres, fused to the front's waist.
  * STAGE B - details: the key ring and legends, a brow over the face
    plate, two ears, the carry handle, the parking foot with a rubber pad,
    a vent, the battery hatch line.
RESTYLE (R803): HEAD_W, HEIGHT, DEPTH, WHEEL_R and WALL drive every outline
and cutter below. WHEEL_R moves the whole hardware frame up or down (the
board rides on the shaft height), so everything is placed from BZ and the
measured module boxes; the hips' side walls stay 0.3 mm off the gearboxes
and the tyres 0.3 mm off the hips whatever the wall.
DETAILS (visible, 30): 1 hips between the wheels, a waist, a wider head
with big round top corners; 2 rolled 3 mm edges; 3 front / back seam;
4 black face plate; 5 smoked screen window; 6 domed blue status eye;
7 brow over the face plate; 8-9 two ears with raised hubs; 10 START key
cap; 11 raised ring round it; 12 "START" legend; 13 "ATECH" on the hips;
14 USB-C pocket with liner in the right flank; 15 "USB" legend; 16-17
fenders with wings into the waist; 18-19 block-tread tyres; 20-21 orange
five-spoke rims; 22-23 chrome centre caps; 24 carry handle; 25 parking
foot (two legs and a bar); 26 rubber pad in the bar's tread; 27 vent slots
in the head's back; 28 battery hatch line; 29 "BATTERY" and a thumb
dimple on the hatch; 30 four countersunk screws in the back.
Inside: the n20 hubs in the rims' hex sockets (hidden meshes: a mesh
cannot be named in fitted_after), soft-square shaft holes, the light
tunnel and light pipe, a rib onto the board's spine, ledges and
standoffs, insert bosses, the front / back lip, a plunger on the key.
Materials: white body, black face plate, smoked window, blue eye, orange
key and rims, rubber tyres and foot pad, chrome caps and screws.
MEASURED (R803, 2026-10-27): ./check CHECK PASS, see test_kit_examples_r500
(TIMINGS line).
"""
import math
import time
import Part
import atech_ports as ap
import atech_modules as am
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation
V = Vector
T0 = time.time()

INTENT = {"board": "upright", "fitted_after": [
    "Front", "Bezel", "Screen_Lens", "Eye_Lens", "Start_Key",
    "Tyre_L", "Tyre_R", "Rim_L", "Rim_R", "Cap_L", "Cap_R",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    "covers": {"Start_Key": "button_p3"}}
REVIEW_CLOSEUPS = ["Bezel", "Rim_L", "Back"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them; test_kit_examples_r280 builds
# this file with each knob at its min and at its max, one at a time.
HEAD_W = 92.0      # RESTYLE 78..106 width: the head across (x)
HEIGHT = 195.0     # RESTYLE 165..225 height: the body's top (z, the handle stands above it)
DEPTH = 44.0       # RESTYLE 37..51 length: the body front to back (y)
WHEEL_R = 40.0     # RESTYLE 34..46 radius: the wheels (they set the board's height)
WALL = 2.0         # RESTYLE 1.7..2.3 wall
# end RESTYLE
# Frame: x across (the viewer's right +), y front (-) to back (+), z up;
# the tyres on z = 0. The board stands UPRIGHT_FRONT at x 0..60, its centre
# line x = 30; its height is set by the wheels (shaft centre = WHEEL_R).
SHAFT_UP = 9.987                 # MEASURED: a seated motor's shaft centre above the board's bottom edge
BZ = WHEEL_R - SHAFT_UP          # the board's bottom edge
TORSO_W = 76.0                   # the waist between the hips and the head
MOTOR_END = 20.38                # MEASURED: the gearbox end past the board edge (shaft tip 29.18)
FRONT_IN = -20.2                 # the front's inner face: 1 mm in front of the motors (y -19.14)
YF = FRONT_IN - WALL
YB = YF + DEPTH
FILLET = 3.0
WHEEL_W = 16.0                   # tyre width
WHEEL_IN = -23.3                 # the left tyre's inner face (the hub's inner end is -23.18)
FENDER = (3.0, 2.5)              # the fender's air over the tyre, its thickness
SCREEN_WIN = (16.0, 28.0)        # smoked window over the portrait screen (active 13.5 x 25.6)
EYE_R = 8.0                      # the status eye over the light
KEY_D = 12.0
SCREW = "M2.5"
COLOURS = {"Front": "matte_white", "Back": "matte_white", "Bezel": "matte_black",
           "Screen_Lens": "smoked", "Eye_Lens": "led_blue", "Start_Key": "orange",
           "Tyre": "rubber", "Rim": "orange", "Cap": "chrome", "Foot_Pad": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
UPRIGHT_FRONT = Rotation(Vector(0, 0, 1), 180)
board = ap.board_object(doc)


def place_board(rot, x0=0.0, y0=None, z0=0.0):
    board.Placement = Placement(Vector(), rot)
    bb = ap.bbox(board)
    board.Placement = Placement(Vector(x0 - bb.XMin, 0 if y0 is None else y0 - bb.YMin,
                                       z0 - bb.ZMin), rot)


place_board(UPRIGHT_FRONT, 0, None, BZ)          # x 0..60, z BZ..BZ + 120, modules face -Y
BB = ap.bbox(board)
mot_r = ap.seat(doc, "dc_motor", 1)              # shaft +X (right wheel)
mot_l = ap.seat(doc, "dc_motor", 9)              # shaft -X (left wheel)
imu = ap.seat(doc, "orientation", 7)             # on the centre line, level with the axle
key = ap.seat(doc, "button", 3)                  # START, on the right chest
usb = ap.seat(doc, "usbc", 4)                    # the right flank, mouth +X
light = ap.seat(doc, "light", 6)                 # the status eye
scr = ap.seat(doc, "screen", (13, 14))           # the face, portrait
ML, MR = ap.bbox(mot_l), ap.bbox(mot_r)
SY, SZ = -10.14, (ML.ZMin + ML.ZMax) / 2         # the shaft: 10.14 in front of the PCB, on the motor's centre line
XM = (ML.XMin + MR.XMax) / 2                     # the mirror plane between the shaft tips
# the n20 hubs (shaft couplers) on the D-shafts, each flat on the shaft's
# flat (MEASURED: the left shaft's flat faces -Z, the right one's +Z)
HUB_PL = {"L": Placement(V(ML.XMin + 6.0, SY - 2.70, SZ + 2.12),
                         Rotation(V(0, 1, 0), -90).multiply(Rotation(V(0, 0, 1), 90))),
          "R": Placement(V(MR.XMax - 6.0, SY - 2.70, SZ - 2.12),
                         Rotation(V(0, 1, 0), 90).multiply(Rotation(V(0, 0, 1), 90)))}

hubs = {}
for side_ in "LR":
    hubs[side_], _rep = am.load_module(doc, "n20_wheel", label="Hub_" + side_, placement=HUB_PL[side_])
    # R803: the hub sits inside its wheel's hex socket, pressed on after the
    # motor is seated; a Mesh::Feature cannot be named in fitted_after, so it
    # is hidden (an obstacle to nothing) - toggle it in the tree to see it
    hubs[side_].Visibility = False
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, -1, 0)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(m):
    b = ap.bbox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


def yslab(w, h, r, cx, cz, y0, y1):
    """A rounded rectangle w x h (x, z), corner r, from y0 to y1."""
    return cad.rounded_box(w, abs(y1 - y0), h, r, at=(cx - w / 2, min(y0, y1), cz - h / 2), edges="y")


def insert(shell, cutter):
    """(shell with the opening, the piece that fills it exactly)."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1:
        piece, rest = shell.common(cutter, 0.01), shell.cut(cutter, 0.01)
    if piece.Volume < 1 or not rest.isValid() or len(rest.Solids) != len(shell.Solids):
        raise cad.CadError("insert: the cutter does not cleanly cross the wall")
    return rest, piece


def arc_pts(cx, cz, r, a0, a1, n=4):
    """Corner facets (n segments) from angle a0 to a1 (deg) round (cx, cz)."""
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cz + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def mirror_x(s):
    return cad.mirror(s, "YZ", (XM, 0, 0))


# ------------------------------------------------------------ the body: hips, waist, head
# one front silhouette (x, z) x one plan (x, y): the hips hold the motors
# between the wheels, the waist narrows above the tyres, the head widens
# round the face; hollowed with its own inset core
HX0 = ML.XMin + (29.18 - MOTOR_END) - 0.3 - WALL     # the hip's outer face (0.3 off the gearbox)
HX1 = 2 * XM - HX0
Z0 = BZ - 10.0 - WALL                                # the bottom
HIP_Z = ML.ZMax + 0.3 + WALL + 3.0                   # the hips' top
TX0, TX1 = 30 - TORSO_W / 2, 30 + TORSO_W / 2
HEAD_Z0 = BZ + 88.0                                  # where the head is full width (over the USB-C)
AX0, AX1 = 30 - HEAD_W / 2, 30 + HEAD_W / 2
HR = 0.3 * HEAD_W                                    # the head's top corners


def corner(cx, cy, r, a):
    """An exact quarter arc round (cx, cy) from angle a to a + 90 deg."""
    p = lambda d: (cx + r * math.cos(math.radians(d)), cy + r * math.sin(math.radians(d)))
    return [p(a), ("arc", p(a + 45), p(a + 90))]


SIDE = (corner(HX1 - 6, Z0 + 6, 6, -90)
        + [(HX1, HIP_Z), (TX1, HIP_Z + 10), (TX1, HEAD_Z0 - 8), (AX1, HEAD_Z0)]
        + corner(AX1 - HR, HEIGHT - HR, HR, 0) + corner(AX0 + HR, HEIGHT - HR, HR, 90)
        + [(AX0, HEAD_Z0), (TX0, HEAD_Z0 - 8), (TX0, HIP_Z + 10), (HX0, HIP_Z)]
        + corner(HX0 + 6, Z0 + 6, 6, 180))
PX0, PX1 = min(HX0, AX0), max(HX1, AX1)
PLAN = [(PX0, YF), (PX1, YF), (PX1, YB), (PX0, YB)]
body = cad.profile_body(SIDE, PLAN, spline=False, fillet=FILLET)
shell = cad.hollow(body, WALL, core=lambda t: cad.profile_body(SIDE, PLAN, spline=False, fillet=FILLET, inset=t))
tick("body")
SPLIT_Y = BB.YMax - 0.3                          # behind the modules: the back is fixed, it holds the board
front, back = cad.split(shell, "Y", at=SPLIT_Y, lip=1.2)
tick("split")

# ------------------------------------------------------------ the back holds the board
YI = YB - WALL + 0.5
ledges = [box(4, 56, 0.6, YI, BB.ZMin - 2.3, BB.ZMin - 0.3), box(4, 56, 0.6, YI, BB.ZMax + 0.3, BB.ZMax + 2.3)]
ledges += [box(x, x + 6, BB.YMax + 0.1, YI, BZ + z, BZ + z + 6) for x in (8, 46) for z in (10, 57, 104)]
back = cad.fuse_one(back, *ledges)
# board retention: a rib from the front wall onto the spine (0.2 mm off)
front = cad.fuse_one(front, box(29, 31, FRONT_IN - 0.5, BB.YMin - 0.2, BZ + 52, BZ + 64))
# four M2.5 screws from the back into insert bosses in the front: two low
# in the hips, two in the head over the board
SCREWS = [(HX0 + WALL + 7.0, BZ - 5.0), (HX1 - WALL - 7.0, BZ - 5.0), (8.0, BB.ZMax + 6.0), (52.0, BB.ZMax + 6.0)]
INSERT_D = {"M2": 3.2, "M2.5": 3.6, "M3": 4.3}[SCREW]
screws = []
for x, z in SCREWS:
    back, front = cad.screw_through(back, front, (x, YB, z), size=SCREW, ribs=0)
    yb = YB - WALL - 0.1
    front = cad.fuse_one(front, cyl(INSERT_D / 2 + 1.2, (x, yb, z), 10.0))
    front = cad.cut(front, cyl(INSERT_D / 2, (x, yb + 0.5, z), 9.5))
    screws.append(cad.screw("csk_phillips", SCREW, round(WALL + 10.0), at=(x, YB, z), axis="-Y"))
tick("back + screws")

# ------------------------------------------------------------ the face
# a black face plate (an insert in the front) carries the smoked screen
# window (a light tunnel back to 1 mm off the screen) and the status eye
# (a clear lens with its light pipe to 0.4 mm off the LEDs)
sx, _sy, sz = centre(scr)
lx, _ly, lz = centre(light)
FZ0, FZ1 = sz - SCREEN_WIN[1] / 2 - 6.0, BB.ZMax + 1.5
front, bezel = insert(front, yslab(68.0, FZ1 - FZ0, 8.0, 30.0, (FZ0 + FZ1) / 2, YF - 1, FRONT_IN + 1))
bezel, screen_lens = insert(bezel, yslab(SCREEN_WIN[0], SCREEN_WIN[1], 2.0, sx, sz, YF - 1, FRONT_IN + 1))
sb = ap.bbox(scr)
tunnel = cad.cut(yslab(SCREEN_WIN[0] + 3.0, SCREEN_WIN[1] + 3.0, 3.0, sx, sz, FRONT_IN - 0.5, sb.YMin - 1.0),
                 yslab(SCREEN_WIN[0], SCREEN_WIN[1], 2.0, sx, sz, FRONT_IN - 1, sb.YMin))
bezel = cad.fuse_one(bezel, tunnel)
lb = ap.bbox(light)
bezel, eye = insert(bezel, cyl(EYE_R, (lx, FRONT_IN + 1, lz), WALL + 2))
dome = Part.makeSphere(EYE_R * 3, V(lx, YF - 0.8 + EYE_R * 3, lz))
eye = cad.fuse_one(eye, dome.common(cyl(EYE_R, (lx, YF + 0.5, lz), 2.0)),
                   cyl(EYE_R, (lx, lb.YMin - 0.4, lz), (lb.YMin - 0.4) - (FRONT_IN - 0.3)))
# the START key: a cap through the front, a plunger to 0.16 mm off the button
kx, _ky, kz = centre(key)
kb = ap.bbox(key)
y_base = FRONT_IN + 0.9
cap = cad.button_cap(KEY_D, y_base - (YF - 1.6), dome=0.8, flange=1.5, at=(kx, y_base, kz), axis="-Y")
front = cad.opening_for(front, cap, clearance=0.25, chamfer=0.4, axis="-Y")
cap = cad.fuse_one(cap, cyl(3.0, (kx, kb.YMin - 0.16, kz), (kb.YMin - 0.16) - y_base + 0.5))
# USB-C in the right flank: a pocket brings the wall to 0.25 mm off the mouth
ub = ap.bbox(usb)
uy, uz = -5.9, (ub.ZMin + ub.ZMax) / 2                # the receptacle: 5.9 mm off the PCB top


def xprism(x0, x1, y0, y1, z0, z1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


pocket = xprism(ub.XMax + 1.3, TX1 + 5, uy - 4.75, uy + 4.75, uz - 6.5, uz + 6.5, 3)
liner = cad.cut(xprism(ub.XMax + 0.25, TX1 - WALL + 0.5, uy - 7.0, min(uy + 7.0, 0.3), uz - 8.5, uz + 8.5, 3.5),
                pocket)
front = cad.fuse_one(cad.cut(front, pocket), liner)
front = cad.socket_opening(front, usb, margin=1.5)
# the shafts through the hips: soft-square holes (no coaxial round holes)


def shaft_hole(a, x0, x1):
    w = cad.rounded_rect_wire(2 * a, 2 * a, 0.9 * a, (x0, SY, SZ), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


front = cad.cut(front, [shaft_hole(2.7, HX0 - 1, HX0 + WALL + 1), shaft_hole(2.7, HX1 + 1, HX1 - WALL - 1)])
tick("face + usb")

# ------------------------------------------------------------ the wheels
# one wheel, mirrored: a block-tread tyre, an orange five-spoke rim with a
# boss whose HEX SOCKET takes the n20 hub (the coupler drives the wheel),
# a chrome cap over the shaft tip
WXC = WHEEL_IN - WHEEL_W / 2
w = cad.wheel(2 * WHEEL_R, WHEEL_W, hub_d=12.0, spokes=5, tread="block", axis="-X", at=(WXC, SY, SZ))
RW = 0.84 * WHEEL_W / 2                          # the rim's half width (cad.wheel)
rim = cad.fuse_one(w["rim"], Part.makeCylinder(6.0, WHEEL_IN - (WXC + RW) + 0.5, V(WXC + RW - 0.5, SY, SZ),
                                               V(1, 0, 0)))
HEX = [(0, 1.85), (0.73, 0), (4.67, 0), (5.4, 1.85), (4.67, 3.7), (0.73, 3.7)]   # MEASURED hub outline


def socket(side):
    """The hub's hex outline + 0.15 mm, along its axis, placed as the hub
    is, and a 3.4 mm clearance hole for the shaft tip past it."""
    w_ = Part.makePolygon([V(x, y, 0) for x, y in HEX + [HEX[0]]]).makeOffset2D(0.15, join=2)
    s_ = Part.Face(w_).extrude(V(0, 0, 7.15))
    s_.translate(V(0, 0, -1.0))
    s_.Placement = HUB_PL[side].multiply(s_.Placement)
    tip = Part.makeCylinder(1.7, 2.0, V(2.70, 2.12, 5.9))
    tip.Placement = HUB_PL[side].multiply(tip.Placement)
    return [s_, tip]


wheels = {"Tyre_L": w["tyre"], "Rim_L": cad.cut(rim, socket("L")), "Cap_L": w["cap"],
          "Tyre_R": mirror_x(w["tyre"]), "Rim_R": cad.cut(mirror_x(rim), socket("R")), "Cap_R": mirror_x(w["cap"])}
tick("wheels")
# the fenders: a band over each tyre, fused to the front's waist (its rear
# half stays clear of the back)
FR0 = WHEEL_R + FENDER[0]


def band(x0, x1):
    ring = cad.cut(Part.makeCylinder(FR0 + FENDER[1], x1 - x0, V(x0, SY, SZ), V(1, 0, 0)),
                   Part.makeCylinder(FR0, x1 - x0 + 2, V(x0 - 1, SY, SZ), V(1, 0, 0)))
    a0, a1 = math.radians(25), math.radians(155)
    r = FR0 + FENDER[1] + 5
    wedge = Part.Face(Part.makePolygon([V(x0 - 1, SY, SZ), V(x0 - 1, SY + r * math.cos(a0), SZ + r * math.sin(a0)),
                                        V(x0 - 1, SY, SZ + r * 1.5),
                                        V(x0 - 1, SY + r * math.cos(a1), SZ + r * math.sin(a1)),
                                        V(x0 - 1, SY, SZ)])).extrude(V(x1 - x0 + 2, 0, 0))
    return ring.common(wedge)


fender = cad.fuse_one(band(WHEEL_IN - WHEEL_W - 2.0, HX0 - 0.3).common(box(-200, 200, -200, 200, 0, 300)),
                      band(HX0 - 1.0, TX0 + WALL * 0.5).common(box(-200, 200, YF + 3.0, SPLIT_Y - 1.0, 0, 300)))
fender = cad.soften(fender, 0.8)
front = cad.fuse_one(front, fender, mirror_x(fender))
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# a raised ring round the START key, legends, a brow over the face plate
front = cad.fuse_one(front, cad.cut(cyl(KEY_D / 2 + 3.0, (kx, YF + 0.5, kz), 1.1),
                                    cyl(KEY_D / 2 + 1.6, (kx, YF + 1.0, kz), 2.0)))
front = cad.text(front, "START", (kx, YF, kz - KEY_D / 2 - 6.0), (0, -1, 0), 3.5, depth=0.4, mode="deboss")
front = cad.text(front, "ATECH", (30.0, YF, (Z0 + HIP_Z) / 2), (0, -1, 0), 6.0, depth=0.5, mode="deboss")
front = cad.text(front, "USB", (TX1, uy - 10.0, uz), (1, 0, 0), 3.5, depth=0.4, mode="deboss", up=(0, 1, 0))
brow = cad.soften(box(30 - 33.0, 30 + 33.0, YF - 1.6, YF + 0.6, FZ1 + 1.5, FZ1 + 4.0), 0.8)
# the ears: a disc on each side of the head with a raised hub
EY, EZ = (YF + SPLIT_Y) / 2 - 1.0, sz
ear = cad.fuse_one(Part.makeCylinder(9.0, 4.5, V(AX0 + 1.0, EY, EZ), V(-1, 0, 0)),
                   Part.makeCylinder(5.0, 5.5, V(AX0 - 2.0, EY, EZ), V(-1, 0, 0)))
ear = cad.soften(ear, 0.8)
front = cad.fuse_one(front, brow, ear, mirror_x(ear))
tick("front details")
# the back: a carry handle on top, a parking foot (two legs and a bar with
# a rubber pad inset in its tread) so it rests upright when switched off,
# a vent over the board, the battery hatch line
HY = YB - 7.0
HX = HEAD_W / 2 - HR - 1.0
handle = cad.pipe([(30 - HX, HY, HEIGHT - 0.6 * WALL), (30 - HX, HY, HEIGHT + 10.0), (30, HY, HEIGHT + 19.0),
                   (30 + HX, HY, HEIGHT + 10.0), (30 + HX, HY, HEIGHT - 0.6 * WALL)], r=3.5)
KX, FOOT_R, FY = 18.0, 3.5, YB + 22.0
legs = [cad.pipe([(30 + s_ * KX, YB - 5.0, Z0 + 0.6 * WALL), (30 + s_ * KX, YB + 8.0, Z0 - 2.0),
                  (30 + s_ * KX, FY, FOOT_R)], r=3.0) for s_ in (-1, 1)]
bar = Part.makeCylinder(FOOT_R, 2 * KX + 6.0, V(30 - KX - 3.0, FY, FOOT_R), V(1, 0, 0))
foot = cad.fuse_one(bar, *legs)
pad_cut = box(30 - KX + 3.0, 30 + KX - 3.0, FY - 0.5 * FOOT_R, FY + 0.5 * FOOT_R, -1.0, 2.2)
pad = foot.common(pad_cut)
foot = cad.cut(foot, pad_cut)
back = cad.fuse_one(back, handle, foot)
back = cad.grille(back, (30.0, YB, BB.ZMax + 6.0), (0, 1, 0), (32.0, 10.0), kind="slot", hole=2.4, pitch=4.5)
back = cad.groove_outline(back, [(30 - 22, BZ + 20), (30 + 22, BZ + 20), (30 + 22, BZ + 94), (30 - 22, BZ + 94)],
                          view="-Y", w=1.0, depth=0.8, both_sides=False)
back = cad.cut(back, Part.makeSphere(6.0, V(30.0, YB + 5.2, BZ + 88.0)))      # the hatch's thumb dimple
back = cad.text(back, "BATTERY", (30.0, YB, BZ + 57.0), (0, 1, 0), 5.0, depth=0.5, mode="deboss")
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour=None):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour or name])
    return o


for nm, sh in (("Back", back), ("Front", front), ("Bezel", bezel)):
    part(nm, sh)
part("Start_Key", cap)
o = part("Screen_Lens", screen_lens)
o.ViewObject.Transparency = cad.transparency("smoked")
o = part("Eye_Lens", eye)
o.ViewObject.Transparency = cad.transparency("glass")
o = part("Foot_Pad", pad)
for nm, sh in wheels.items():
    part(nm, sh, nm[:-2])
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
