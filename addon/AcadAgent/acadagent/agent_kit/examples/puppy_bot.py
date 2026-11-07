"""Example: "a little puppy robot" - a rolling robot puppy with screen eyes, a ToF nose, a bark and a wagging tail.

fork this file for a robot pet / companion bot (a puppy, a kitten, a
rolling critter that follows you, wags and barks); change PARAMETERS and
the outlines.
ARCHETYPE: robot or character

How it is built:
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT in the torso, nose at the port-8 end (-Y; 8 and 12 empty),
    its height set by the tyre (shaft centre = PCB top + 10.14). Two
    dc_motor SEATED on 1 + 9 drive the hind wheels (the rover's N20 hub in
    each rim's hex socket); a third dc_motor SEATED on 7 points its shaft
    straight back out of the rump: the TAIL sits on it (an N20 hub in a hex
    socket) and the firmware wags it by reversing the motor - the tail is
    shorter than the shaft is high, so it clears the floor at any angle.
    The speaker SEATED on (4, 5) under a grille in the back; the button on
    10 under a key on the back; the IMU on 11 (picked up / patted); USB-C on
    3 in a pocket + liner in the left flank between the wheel and the
    speaker. The screen (13, 14) is CABLED into the head behind a smoked
    visor (the eyes) and the ToF (6) CABLED to the muzzle behind a black
    nose with an open slot; each is held by two ribs back from the face.
    Torso and head are rounded boxes fused, hollowed by their fused cores,
    split low (lip) into the fixed Chassis (a cradle holds the board, the
    front legs and paws stand under it) and the Body; four M2 screws from
    below into insert sleeves; a rib onto the spine.
  * STAGE B - details: floppy ears pinned to the head, a collar with a
    tag, hind haunches over the wheels, brows, paw pads, lettering.
Front paws are flat skids (PLA slides on a hard floor; a felt pad under
each helps on wood, carpet needs a 3/8" ball caster instead).
"""
import math
import time
import Part
import atech_ports as ap
import atech_cad as cad
import atech_modules as am
from FreeCAD import Vector, Placement, Rotation
V = Vector
T0 = time.time()

INTENT = {"board": "flat", "fitted_after": [
    "Body", "Visor", "Nose", "Key", "Tail", "Collar", "Tag", "Muzzle", "Spot", "Ear_L", "Ear_R",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4", "Screw_5",
    "Tyre_L", "Tyre_R", "Rim_L", "Rim_R", "Cap_L", "Cap_R"],
    "covers": {"Key": "button_p10"}}
REVIEW_CLOSEUPS = ["Muzzle", "Tail", "Ear_L"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
WHEEL_R = 30.0       # hind wheels (the board rides on them: shaft = PCB top + 10.14)
TYRE_W = 20.0
WALL = 2.0
# World frame: the board FLAT at x 0..60, y -120..0 (nose at -Y), z up,
# the wheels and paws on z = 0. Heights are taken over the PCB top L.
HW = 52.9                         # torso half width round x = 30 (motor body 20.4 + 0.2 + wall)
TY0, TY1 = -127.0, 23.0           # torso front (the board ends at y -120), rump (the tail motor's body ends at y 20.4)
TOP = 44.0                        # torso top over L
TORSO_R = 14.0
HX0, HX1, HY0, HY1 = -4.0, 64.0, -152.0, -100.0   # head box in plan
HZ0, HZ1 = -4.7, 120.0            # head bottom (= the torso floor) / top over L
HEAD_R = 12.0
SCREEN_Z, NOSE_Z = 94.0, 38.0     # screen and ToF centres over L (their ribbons run 14.5 straight down)
VISOR = (36.0, 20.0, 6.0)         # smoked visor w, h, corner r
SCREWS = [(-6.0, -30.0), (-6.0, 5.0), (66.0, 5.0), (66.0, -70.0), (-13.0, -106.0)]   # flat floor, off the board, speaker and plugs
LEGS = [(6.0, -114.0), (54.0, -114.0)]             # front legs (x, y)
COLOURS = {"Chassis": "graphite", "Body": "#e8b878", "Visor": "smoked", "Nose": "matte_black",
           "Key": "coral", "Tail": "#e8b878", "Muzzle": "#f6e7cf", "Spot": "#8a5a3c", "Ear": "#8a5a3c", "Collar": "led_red", "Tag": "chrome",
           "Screw": "chrome", "Tyre": "rubber", "Rim": "#8a5a3c", "Cap": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
WHEEL = cad.wheel(2 * WHEEL_R - 2.4, TYRE_W, hub_d=12.0, tread="block", tread_n=30, axis="-X", at=(0, 0, 0))
RT = cad.measure(WHEEL["tyre"])["size"][2] / 2.0
L = RT - 10.14                    # PCB top: the shaft centre 10.14 above it = the tyre radius
FZ = L - 2.7 - WALL               # the floor's underside (its top 0.2 under the board)
SPLIT_Z = L - 2.2
FLAT = Rotation(Vector(1, 0, 0), 90)
board = ap.board_object(doc)
board.Placement = Placement(Vector(0, 0, L), FLAT)
motors = {"L": ap.seat(doc, "dc_motor", 1), "R": ap.seat(doc, "dc_motor", 9)}
tail_m = ap.seat(doc, "dc_motor", 7)                    # shaft +Y out of the rump
spk = ap.seat(doc, "speaker", (4, 5))                   # face up, under the back
key = ap.seat(doc, "button", 10)
imu = ap.seat(doc, "orientation", 11)
usb = ap.seat(doc, "usbc", 3)                           # mouth -X, left flank
FACE_Y = HY0 + WALL + 0.6                               # module faces 0.6 behind the face wall
scr, scr_ribs = ap.cable(doc, "screen", (13, 14), ap.module_placement(
    "screen", (30, FACE_Y + 9.64 / 2, L + SCREEN_Z), face="-Y", cable="-Z"),
    # each ribbon its own route, plug -> module: out of the right edge, up
    # the flank, forward into the head and up into the screen from behind
    # the nose; 13's runs over 14's
    # (the last two points sit on the socket's line: the curve cannot sag
    # into the nose sensor under it)
    via={13: [(70, -88, L + 10), (70, -98, L + 26), (54, -110, L + 36), (40, -118, L + 56), (24, -128, L + 62),
              (20, -139, L + 62), (20, -141.2, L + 66)],
         14: [(70, -112, L + 8), (58, -118, L + 24), (48, -128, L + 44), (40, -134, L + 56),
              (40, -139, L + 62), (40, -141.2, L + 66)]})
tof, tof_rib = ap.cable(doc, "distance_sensor", 6, ap.module_placement(
    "distance_sensor", (30, FACE_Y + 9.54 / 2, L + NOSE_Z), face="-Y", cable="-Z"),
    via=[(-4, -114, L + 4), (6, -124, L + 3.5), (22, -132, L + 3.5), (30, -137, L + 5.5), (30, -141.1, L + 10)])     # out of the left edge, under the chin
BB = ap.bbox(board)
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, d, h):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(m):
    b = ap.bbox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


def insert(shell, cutter):
    """(shell with the opening, the piece that fills it exactly)."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1:
        piece, rest = shell.common(cutter, 0.01), shell.cut(cutter, 0.01)
    if piece.Volume < 1 or not rest.isValid() or len(rest.Solids) != len(shell.Solids):
        raise cad.CadError("insert: the cutter does not cleanly cross the wall")
    return rest, cad.fuse_one(piece)


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    s = Part.Face(w).extrude(V(x1 - x0, 0, 0))
    if s.Volume < 0:
        s.reverse()
    return s


def ring(r_out, r_in, p, d, h):
    return cad.cut(cyl(r_out, p, d, h), cyl(r_in, tuple(a - 0.5 * b for a, b in zip(p, d)), d, h + 1.0))


# ------------------------------------------------------------ torso + head
def hull_solid(t=0.0):
    # the top rounded all round, the lower half upright-sided: a rounded
    # bottom edge would curve into the motors and speaker on the floor
    torso = cad.fuse_one(
        cad.rounded_box(2 * HW - 2 * t, TY1 - TY0 - 2 * t, L + TOP - FZ - 2 * t, TORSO_R - t,
                        at=(30 - HW + t, TY0 + t, FZ + t), edges="all"),
        cad.rounded_box(2 * HW - 2 * t, TY1 - TY0 - 2 * t, L + 24 - FZ - t, TORSO_R - t,
                        at=(30 - HW + t, TY0 + t, FZ + t), edges="vertical"))
    head = cad.fuse_one(
        cad.rounded_box(HX1 - HX0 - 2 * t, HY1 - HY0 - 2 * t, HZ1 - HZ0 - 2 * t, HEAD_R - t,
                        at=(HX0 + t, HY0 + t, L + HZ0 + t), edges="all"),
        cad.rounded_box(HX1 - HX0 - 2 * t, HY1 - HY0 - 2 * t, 30 - HZ0 - t, HEAD_R - t,
                        at=(HX0 + t, HY0 + t, L + HZ0 + t), edges="vertical"))   # a flat chin floor
    return cad.fuse_one(torso, head)


outer = hull_solid()
core = hull_solid(WALL)
skin = hull_solid(0.6)            # ribs are clipped to it: they stop inside the outer skin
hull = cad.cut(outer, core)
lower, upper = cad.split(hull, "Z", at=SPLIT_Z, lip=1.2)
tick("hull + split")

# board cradle in the fixed chassis: a ledge under the board's edge, a rim 0.3 round it
PCB0 = L - 2.5
cradle = cad.cut(box(BB.XMin - 2.3, BB.XMax + 2.3, BB.YMin - 2.3, BB.YMax + 2.3, FZ + WALL - 0.5, PCB0 + 1.4),
                 [box(BB.XMin - 0.3, BB.XMax + 0.3, BB.YMin - 0.3, BB.YMax + 0.3, PCB0 - 0.1, L + TOP),
                  box(BB.XMin + 6, BB.XMax - 6, BB.YMin + 6, BB.YMax - 6, FZ, L + TOP)])
lower = cad.fuse_one(lower, cradle)
# board retention: a rib from the back onto the spine (0.2 mm above it)
upper = cad.fuse_one(upper, box(29, 31, -76, -62, L + 4.5 + 0.2, L + TOP).common(skin))
screws = []
for x, y in SCREWS:
    lower, upper = cad.screw_through(lower, upper, (x, y, FZ), size="M2", ribs=0)
    screws.append(cad.screw("csk_phillips", "M2", 10, at=(x, y, FZ), axis="+Z"))
upper = cad.fuse_one(upper, *[cyl(2.8, (x, y, FZ + WALL + 0.1), (0, 0, 1), 10.0) for x, y in SCREWS])
upper = cad.cut(upper, [cyl(1.6, (x, y, FZ + WALL - 0.5), (0, 0, 1), 10.5) for x, y in SCREWS])
tick("cradle + screws")


# ------------------------------------------------------------ hind wheels, tail
def shaft_hole_x(a, x0, x1, y, z):
    w = cad.rounded_rect_wire(2 * a, 2 * a, 0.9 * a, (x0, y, z), "X")
    s = Part.Face(w).extrude(V(x1 - x0, 0, 0))
    if s.Volume < 0:
        s.reverse()
    return s


AX = {}
for k, m in motors.items():
    b = ap.bbox(m)
    left = k == "L"
    AX[k] = (b.XMin if left else b.XMax, (b.YMin + b.YMax) / 2, L + 10.14, left)
upper = cad.cut(upper, [shaft_hole_x(2.7, 30 - HW + WALL + 1.5, 30 - HW - 2.0, y, z) if lf else
                        shaft_hole_x(2.7, 30 + HW - WALL - 1.5, 30 + HW + 2.0, y, z)
                        for _t, y, z, lf in AX.values()])
HUB = [(0, 1.85), (0.73, 0), (4.67, 0), (5.4, 1.85), (4.67, 3.7), (0.73, 3.7)]
hub_w = Part.makePolygon([V(x, y, 0) for x, y in HUB + [HUB[0]]]).makeOffset2D(0.15, join=2)
sock = Part.Face(hub_w).extrude(V(0, 0, 6.75))
sock.translate(V(0, 0, -0.6))
hex_sock = sock.copy()             # the tail's socket: the shaft ends inside the hub
sock = cad.fuse_one(sock, cyl(1.7, (2.70, 2.12, 5.9), (0, 0, 1), 3.0))
rim_in = cad.measure(WHEEL["rim"])["bbox_max"][0]
WHEEL["rim"] = cad.fuse_one(WHEEL["rim"], cyl(6.0, (rim_in - 0.5, 0, 0), (1, 0, 0), TYRE_W / 2 - rim_in + 0.5))
wheels = {}
for k, (tip, y, z, lf) in AX.items():
    if lf:
        pl = Placement(V(tip + 6.0, y + 2.12, z + 2.70), Rotation(V(1, 0, -1), 180))
    else:
        pl = Placement(V(tip - 6.0, y - 2.12, z + 2.70), Rotation(V(0, 1, 0), 90))
    hub, _ = am.load_module(doc, "n20_wheel", label="Hub_" + k, placement=pl)
    hub.Visibility = False
    inner = tip + 6.0 - 0.2 if lf else tip - 6.0 + 0.2
    cx = inner - TYRE_W / 2 if lf else inner + TYRE_W / 2
    s_cut = sock.copy()
    s_cut.transformShape(pl.toMatrix())
    for part_k, sh in WHEEL.items():
        s = sh.copy() if lf else cad.mirror(sh, "YZ", (0, 0, 0))
        s.translate(V(cx, y, z))
        if part_k == "rim":
            s = cad.cut(s, s_cut)
        wheels["%s_%s" % (part_k.capitalize(), k)] = s
# the tail motor: its shaft out through the rump (a soft-square hole), the
# n20 hub on it (the right motor's hub turned 90 deg about z), the tail's
# hex socket over the hub
tb = ap.bbox(tail_m)
TX, TZ, TTIP = (tb.XMin + tb.XMax) / 2, L + 10.14, tb.YMax
w = cad.rounded_rect_wire(5.4, 5.4, 2.4, (TX, TY1 - WALL - 1.5, TZ), "Y")
upper = cad.cut(upper, Part.Face(w).extrude(V(0, WALL + 4.0, 0)))
RZ90 = Rotation(V(0, 0, 1), 90)
tpl = Placement(V(TX + 2.12, TTIP - 6.0, TZ + 2.70), RZ90.multiply(Rotation(V(0, 1, 0), 90)))
thub, _ = am.load_module(doc, "n20_wheel", label="Hub_Tail", placement=tpl)
thub.Visibility = False
t_cut = hex_sock.copy()
t_cut.transformShape(tpl.toMatrix())
TAIL_Y0 = TY1 + 0.4
TAIL_LEN = TZ - 5.0               # tip ball to axis < axle height: it never reaches the floor
tail = cad.fuse_one(cad.soften(cyl(6.0, (TX, TAIL_Y0, TZ), (0, 1, 0), TTIP + 3.0 - TAIL_Y0), 1.0),
                    cad.pipe([(TX, TTIP - 1.0, TZ), (TX, TTIP + 3.0, TZ + 9.0), (TX, TTIP + 4.0, TZ + TAIL_LEN - 9.0),
                              (TX, TTIP + 1.0, TZ + TAIL_LEN - 4.0)], r=3.2),
                    Part.makeSphere(4.2, V(TX, TTIP + 1.0, TZ + TAIL_LEN - 4.0)))
tail = cad.cut(tail, t_cut)
tick("wheels + tail")

# ------------------------------------------------------------ the face: visor (eyes), nose (ToF)
sx, _sy, sz = centre(scr)
upper, visor = insert(upper, cad.rounded_box(VISOR[0], WALL + 4, VISOR[1], VISOR[2],
                                             at=(sx - VISOR[0] / 2, HY0 - 2.0, sz - VISOR[1] / 2), edges="y"))
visor.translate(V(0, 0.4, 0))
nx, _ny, nz = centre(tof)
nose_cut = cad.rounded_box(18.0, WALL + 4, 13.0, 5.0, at=(nx - 9.0, HY0 - 2.0, nz - 6.5), edges="y")
upper, nose = insert(upper, nose_cut)
nose = cad.cut(nose, cad.rounded_box(13.0, WALL + 4, 9.0, 3.0, at=(nx - 6.5, HY0 - 1.5, nz - 4.5), edges="y"))
# holders: ribs back from the face wall either side of each cabled module (0.3 mm off)
holders = []
for m in (scr, tof):
    b = ap.bbox(m)
    for x0, x1 in ((b.XMin - 1.6, b.XMin - 0.3), (b.XMax + 0.3, b.XMax + 1.6)):
        holders.append(box(x0, x1, HY0 + 1.0, b.YMax - 1.0, b.ZMin + 1.0, b.ZMax - 1.0).common(skin))
upper = cad.fuse_one(upper, *holders)
tick("face")

# ------------------------------------------------------------ the back: speaker grille, key
spb = ap.bbox(spk)
spx, spy = (spb.XMin + spb.XMax) / 2, (spb.YMin + spb.YMax) / 2
TOPZ = L + TOP
upper = cad.speaker_grille(upper, (spx, spy, TOPZ), (0, 0, 1), 24, ring_pitch=2.6, hole=1.5)
upper = cad.fuse_one(upper, cad.cut(cyl(15.0, (spx, spy, spb.ZMax + 0.5), (0, 0, 1), TOPZ - WALL + 0.5 - spb.ZMax - 0.5),
                                    cyl(13.4, (spx, spy, spb.ZMax), (0, 0, 1), TOP)))
kx, ky, _kz = centre(key)
kb = ap.bbox(key)
z_base = TOPZ - WALL - 0.9
cap = cad.button_cap(12.0, TOPZ + 1.6 - z_base, dome=0.8, flange=1.5, at=(kx, ky, z_base), axis="+Z")
upper = cad.opening_for(upper, cap, clearance=0.25, chamfer=0.4, axis="+Z")
cap = cad.fuse_one(cap, cyl(3.0, (kx, ky, kb.ZMax + 0.16), (0, 0, 1), z_base - kb.ZMax - 0.16 + 0.5))
tick("back")

# ------------------------------------------------------------ USB-C in the left flank
ub = ap.bbox(usb)
uy, uz = (ub.YMin + ub.YMax) / 2, L + 5.9
X0 = 30 - HW
pocket = xprism(uy - 6.5, uy + 6.5, uz - 5.0, uz + 5.0, X0 - 5, ub.XMin - 1.3, 2.5)
liner = cad.cut(xprism(uy - 8.5, uy + 8.5, max(uz - 7.0, SPLIT_Z + 1.5), uz + 7.0, ub.XMin - 0.25, X0 + 1.0, 3.5),
                pocket)
upper = cad.fuse_one(cad.cut(upper, pocket), liner)
upper = cad.socket_opening(upper, usb, margin=1.5)
tick("stage A")



# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# ------------------------------------------------------------ front legs and paws on the chassis
legs = []
for x, y in LEGS:
    paw = cad.soften(cad.rounded_box(20.0, 26.0, 6.0, 6.0, at=(x - 10.0, y - 16.0, 0.0)), 1.5)
    # two toe lines across the front of each paw
    paw = cad.cut(paw, [box(x + dx - 0.6, x + dx + 0.6, y - 16.5, y - 10.0, 4.6, 7.0) for dx in (-3.5, 3.5)])
    legs += [cyl(7.0, (x, y, 5.0), (0, 0, 1), FZ - 5.0 + 0.5), paw]
lower = cad.fuse_one(lower, *legs)
tick("legs")


def head_outline(d, z):
    """The head's plan outline (its upright sides) moved d outward, at height z."""
    return cad.rounded_rect_wire(HX1 - HX0 + 2 * d, HY1 - HY0 + 2 * d, HEAD_R + d,
                                 ((HX0 + HX1) / 2, (HY0 + HY1) / 2, z), "Z")


def zband(d_out, d_in, z0, z1):
    """A band round the head's front (y < the torso's front): outline d_out
    minus outline d_in, from z0 to z1."""
    outer = Part.Face(head_outline(d_out, z0)).extrude(V(0, 0, z1 - z0))
    inner = Part.Face(head_outline(d_in, z0 - 1)).extrude(V(0, 0, z1 - z0 + 2))
    return cad.cut(outer, inner).common(box(HX0 - 20, HX1 + 20, HY0 - 20, TY0 - 0.3, z0 - 5, z1 + 5))


# ------------------------------------------------------------ collar and tag
# a red U collar under the chin: it slides on from the front into a 0.8 mm
# groove round the head (0.1 mm clear, 0.2 above and below), two pegs on
# its front press into the face; its ends stop 0.3 short of the torso
CZ0, CZ1 = L + 12.0, L + 19.0
upper = cad.cut(upper, zband(6.0, -0.8, CZ0 - 0.2, CZ1 + 0.2))
collar = zband(2.5, -0.7, CZ0, CZ1)
COLLAR_PEGS = [(30 - 16.0, CZ0 + 3.5), (30 + 16.0, CZ0 + 3.5)]
collar = cad.fuse_one(collar, *[cyl(1.4, (x, HY0 + 0.7 - 0.5, z), (0, 1, 0), 3.0) for x, z in COLLAR_PEGS])
upper = cad.cut(upper, [cyl(1.6, (x, HY0 - 1.0, z), (0, 1, 0), WALL + 3.0) for x, z in COLLAR_PEGS])
# the chrome tag hangs at its front on a peg into the collar
TAG_Y = HY0 - 2.5 - 0.3
tag = cad.fuse_one(cad.soften(cyl(6.5, (30, TAG_Y, CZ0 - 3.0), (0, -1, 0), 2.0), 0.5),
                   cyl(1.2, (30, TAG_Y - 0.5, CZ0 + 2.0), (0, 1, 0), 2.5))
collar = cad.cut(collar, cyl(1.35, (30, TAG_Y - 0.5, CZ0 + 2.0), (0, 1, 0), 2.5))
tag = cad.text(tag, "PUP", (30, TAG_Y - 2.0, CZ0 - 3.0), (0, -1, 0), 4.0, depth=0.3, mode="deboss")
tick("collar")

# ------------------------------------------------------------ muzzle and nose
# a cream muzzle pad on two pegs over the lower face, a hole round the nose
# (the ToF looks out through it: 25 x 19 at 4 mm keeps its cone clear),
# a smile and a philtrum line
muzzle = cad.soften(cad.rounded_box(36.0, 4.0, 42.0, 10.0, at=(nx - 18.0, HY0 - 4.0, nz - 18.0), edges="y"), 1.5)
muzzle = cad.cut(muzzle, cad.rounded_box(25.0, 10.0, 19.0, 7.0, at=(nx - 12.5, HY0 - 6.0, nz - 9.5), edges="y"))
MUZZLE_PEGS = [(nx - 13.0, nz + 16.0), (nx + 13.0, nz + 16.0)]
muzzle = cad.fuse_one(muzzle, *[cyl(1.4, (x, HY0 - 0.5, z), (0, 1, 0), 3.0) for x, z in MUZZLE_PEGS])
upper = cad.cut(upper, [cyl(1.6, (x, HY0 - 1.0, z), (0, 1, 0), WALL + 3.0) for x, z in MUZZLE_PEGS])
yf = HY0 - 4.0
muzzle = cad.cut(muzzle, [cad.pipe([(nx - 8, yf, nz - 12.0), (nx - 4, yf, nz - 15.0), (nx, yf, nz - 13.5),
                                    (nx + 4, yf, nz - 15.0), (nx + 8, yf, nz - 12.0)], r=0.8),
                          box(nx - 0.6, nx + 0.6, yf - 1, yf + 0.8, nz - 13.5, nz - 9.5)])
# the black nose: a domed button in front of its insert (a neck through the
# insert joins them), the slot opening wider through the dome
dome = cad.soften(cad.rounded_box(22.0, 4.45, 16.0, 6.0, at=(nx - 11.0, HY0 - 4.5, nz - 8.0), edges="y"), 1.2)
dome = cad.cut(dome, cad.rounded_box(17.0, 6.0, 12.0, 4.0, at=(nx - 8.5, HY0 - 5.5, nz - 6.0), edges="y"))
neck = cad.cut(cad.rounded_box(18.0, 2.0, 13.0, 5.0, at=(nx - 9.0, HY0 - 1.0, nz - 6.5), edges="y"),
               cad.rounded_box(13.0, 4.0, 9.0, 3.0, at=(nx - 6.5, HY0 - 2.0, nz - 4.5), edges="y"))
nose = cad.fuse_one(nose, neck, dome)
tick("muzzle + nose")

# ------------------------------------------------------------ floppy ears
# each pinned into a soft-square hole high on the head's side, hanging
# down and 10 deg out
EAR_Y, EAR_Z = (HY0 + HY1) / 2, L + 100.0
ears = {}
for nm, x0, sd in (("Ear_L", HX0, -1), ("Ear_R", HX1, 1)):
    a = 2.65
    hole = xprism(EAR_Y - a, EAR_Y + a, EAR_Z - a, EAR_Z + a, x0 + sd * 1.0, x0 - sd * (WALL + 1.0), 0.8 * a)
    upper = cad.cut(upper, hole)
    disc = cad.soften(cyl(7.0, (x0, EAR_Y, EAR_Z), (sd, 0, 0), 3.0), 1.0)
    peg = cyl(2.5, (x0 - sd * 3.0, EAR_Y, EAR_Z), (sd, 0, 0), 4.0)
    xin = x0 + sd * 2.5
    plate = cad.soften(cad.rounded_box(4.0, 28.0, 54.0, 12.0, at=(min(xin, xin + sd * 4.0), EAR_Y - 14.0, EAR_Z - 46.0),
                                       edges="x"), 1.5)
    plate.rotate(V(x0, EAR_Y, EAR_Z), V(0, 1, 0), -sd * 10.0)
    ears[nm] = cad.fuse_one(plate, disc, peg)
tick("ears")

# ------------------------------------------------------------ a spot on the back
# a brown patch that fills its own opening in the back (an insert)
spot_w = Part.Face(Part.Wire(Part.Ellipse(V(54.0, -82.0, TOPZ - WALL - 2.0), 13.0, 10.0).toShape()))
upper, spot = insert(upper, spot_w.extrude(V(0, 0, WALL + 5.0)))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour=None):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour or name])
    return o


part("Chassis", lower)
part("Body", upper)
o = part("Visor", visor)
o.ViewObject.Transparency = cad.transparency("smoked")
part("Nose", nose)
part("Key", cap)
part("Tail", tail)
part("Collar", collar)
part("Tag", tag)
part("Muzzle", muzzle)
part("Spot", spot)
for nm, sh in ears.items():
    part(nm, sh, "Ear")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
for nm, sh in wheels.items():
    part(nm, sh, nm.split("_")[0])
print("TOTAL %.1f s" % (time.time() - T0))
