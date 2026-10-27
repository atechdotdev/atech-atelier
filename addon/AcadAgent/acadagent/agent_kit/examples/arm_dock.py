"""Example: "a robot arm dock" - a heavy low dock for an SO-101 arm: a sloped control deck and a podium with the arm's plate.

fork this file for a robot arm base / dock / controller (an SO-101
dock, a teach pendant base, a camera-slider controller: a machine on a
plate, the controls on a deck); change PARAMETERS and the outlines.
ARCHETYPE: robot arm dock

How it is built (R803):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT and turned ACROSS the other way round from the macro pad
    (ports 1-6 along the BACK, 9-14 along the front, 7 at the right end)
    under a sloped control deck. The robot_arm integrator sits on port 3
    (UART; ports 3 / 4 only) at the back, its servo-bus connector facing
    up: a rubber grommet in the deck over it gives the arm's cable a
    12 x 22 mm way out, straight into a cable gate in the podium's front
    edge that leads it onto the arm plate. In front: the screen (10, 11)
    behind a smoked window in a recessed black bezel (joint angles,
    recording status), the REC key (9) at the front right with the PLAY
    key (1) behind it, the jog dial (knob 13, 14) at the front left inside
    a round DIAL CROWN (its cap flush with the rim, a frosted ring over its
    LED ring), the status light (5) under a frosted lens, USB-C (7) in a
    pocket in the right end. Ports 8 and 12 stay empty (reserved). The
    deck is built in a LOCAL frame (flat, z up from its front-bottom edge)
    and tilted back ALPHA as one Placement; the PODIUM behind it is built
    upright in the world (its top level for the arm) and joined to the
    deck; the union is hollowed with its own core, split into the fixed
    Base (it carries the board on pads between fences) and the Top with a
    lip; six M2.5 screws from below into heat-set insert bosses.
  * STAGE B - details: the brushed arm plate in a recess on the podium
    (four M3 screws into inserts), its bolt pattern for the arm (four
    holes over M4 heat-set insert pockets), corner locating lugs, an
    embossed "SO-101" and an arrow to the arm's front; key and deck
    legends, the parting-line reveal, a grip groove, the 12 V jack opening
    in the back, vents and a model mark under the base, rubber feet.
    THE ARM'S BOLT PATTERN IS A PLACEHOLDER (BOLT, a square): measure the
    real SO-101 base before printing. The arm needs its own 12 V servo
    supply (the USB-C module does not feed the servo rail): the "12V"
    opening in the back takes a panel DC jack (no library module for it).
RESTYLE (R803): REACH, SIDE, PODIUM, CORNER and WALL drive every outline
and every cutter below; the plate, its bolt pattern and the podium screws
follow REACH and CORNER, the deck follows the board (never move the
hardware frame with a knob).
DETAILS (visible, 28): 1 low sloped control deck; 2 the podium rising
behind it, level for the arm; 3 rolled top edges; 4 soft plan corners;
5 brushed arm plate in a recess; 6 four arm bolt holes; 7 four corner
locating lugs; 8 embossed "SO-101"; 9 arrow to the arm's front; 10 four
countersunk plate screws; 11 rubber cable grommet with its 12 x 22 slot
over the arm connector; 12 cable gate in the podium's front edge; 13 smoked
screen window; 14 recessed black bezel; 15 red REC key; 16 PLAY key;
17 "REC" / "PLAY" legends; 18 round dial crown; 19 the jog dial's cap
flush in its well; 20 frosted ring over the dial's LEDs; 21 brushed crown
bezel; 22 frosted status lens; 23 USB-C pocket with liner in the right end;
24 "12V" jack opening with its legend in the back; 25 parting-line reveal;
26 grip groove along the front; 27 slot vents and "ATECH AD-1" under the
base; 28 six countersunk screws and six rubber feet.
Inside: board pads and end fences, ribs onto the board's spine, screw
bosses with heat-set insert sleeves, M4 insert pockets under the arm's
bolt holes, M3 insert sleeves under the plate screws, a block behind the
cable gate, base / top lip, key plungers, a light pipe under the lens.
Materials: graphite top, black base, brushed aluminium plate and crown
bezel, red REC key, ivory PLAY key, smoked window, black bezel, frosted
lens and dial ring, rubber grommet and feet, chrome screws.
MEASURED (R803, 2026-10-27): ./check CHECK PASS, see test_kit_examples_r500
(TIMINGS line).
"""
import math
import time
import Part
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation
V = Vector
T0 = time.time()

INTENT = {"board": "flat", "fitted_after": [
    "Top", "Bezel", "Screen_Window", "Status_Lens", "Dial_Ring", "Dial_Bezel", "Cable_Grommet",
    "Key_Rec", "Key_Play", "Arm_Plate",
    "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4", "Rubber_5", "Rubber_6",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4", "Screw_5", "Screw_6",
    "Plate_Screw_1", "Plate_Screw_2", "Plate_Screw_3", "Plate_Screw_4"],
    # each key presses its button through its opening (a declared cover)
    "covers": {"Key_Rec": "button_p9", "Key_Play": "button_p1"}}
REVIEW_CLOSEUPS = ["Arm_Plate", "Dial_Bezel", "Cable_Grommet"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them and the measured hardware.
REACH = 120.0      # RESTYLE 100..140 length: the arm podium behind the deck (y)
SIDE = 12.0        # RESTYLE 10..14 width: the dock past the board's ends (x)
PODIUM = 47.0      # RESTYLE 39.5..54.5 height: the podium's top (the arm's seat) over the desk
CORNER = 16.0      # RESTYLE 13.5..18.5 radius: the plan's corners
WALL = 2.5         # RESTYLE 2.1..2.9 wall
# end RESTYLE
# The deck is built in a LOCAL frame - flat, x across, y away from the
# user, z up from the front-bottom edge - and tilted back ALPHA as one
# piece; the podium is built in the world (its top level for the arm).
ALPHA = 6.0                      # the deck's lean toward the hand
RUB = 1.5                        # the rubber feet's height (the body's bottom over the desk)
Z_PCB = WALL + 4.0               # the PCB top over the deck's front foot
AIR = 1.2                        # the deck's inner face over the tallest module (usbc 10.21)
EDGE_R, FOOT_R = 3.5, 1.2        # the rolled top edges, the foot
KNOB_C = (-40.0, -30.72)         # MEASURED: the knob (13, 14)'s axis, turned as below
CROWN = (27.0, 22.5)             # the dial crown's foot / rim radius
DISH_R = 19.0                    # the well round the knob's 12 mm cap
RING_R = (5.6, 15.5)             # the frosted ring over the knob's LED ring
KEY = 17.0                       # the REC / PLAY key caps (square)
LABEL = (32.0, 17.0)             # the smoked screen window (active area 25.6 x 13.5)
BEZEL, RECESS = 2.5, 1.0
LENS_R = 6.5                     # the status lens
GROMMET = (24.0, 32.0)           # the rubber grommet round the arm cable's exit (x, y)
SLOT = (12.0, 22.0)              # its slot: the plug and cable's way out (>= 8 mm)
GATE = (14.0, 9.0)               # the cable gate in the podium's front edge: width, depth
PLATE_T, PLATE_SINK = 4.0, 1.0   # the arm plate: thickness, how deep it sits in its recess
SCREW = "M2.5"
COLOURS = {"Top": "graphite", "Base": "matte_black", "Arm_Plate": "brushed_alu",
           "Key_Rec": "signal_red", "Key_Play": "cream", "Screen_Window": "smoked",
           "Bezel": "matte_black", "Status_Lens": "frosted", "Dial_Ring": "frosted",
           "Dial_Bezel": "brushed_alu", "Cable_Grommet": "rubber", "Rubber": "rubber",
           "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
FLAT = Rotation(Vector(1, 0, 0), 90)
TURN = Rotation(Vector(0, 0, 1), -90).multiply(FLAT)      # ports 1-6 at the back, 9-14 front, 7 right
# the plan: the board centred, the dial crown 3 mm inside the front and
# the left end, the podium from YP (behind the back row) for REACH
Y0 = KNOB_C[1] - CROWN[0] - 3.0               # the front edge
X1 = max(60.62 + SIDE, -KNOB_C[0] + CROWN[0] + 3.0)  # the ends (the USB-C module's mouth at 60.62)
YP = 44.0                                     # the podium's front, over the deck (the back row ends at 30.5)
TAN_A = math.tan(math.radians(ALPHA))
COS_A, SIN_A = math.cos(math.radians(ALPHA)), math.sin(math.radians(ALPHA))
TILT = Placement(V(0, 0, RUB), Rotation(V(1, 0, 0), ALPHA), V(0, Y0, 0))
TILT_M, LOCAL_M = TILT.toMatrix(), TILT.inverse().toMatrix()
board = ap.board_object(doc)
board.Placement = Placement(V(), TURN)
_b = ap.bbox(board)
board.Placement = TILT.multiply(Placement(V(-(_b.XMin + _b.XMax) / 2, -(_b.YMin + _b.YMax) / 2,
                                            Z_PCB - 2.5 - _b.ZMin), TURN))
knob = ap.seat(doc, "knob", (13, 14))         # the jog dial: front left, hangs 20 mm forward
scr = ap.seat(doc, "screen", (10, 11))        # joint angles / recording status: front centre
rec = ap.seat(doc, "button", 9)               # REC: front right
play = ap.seat(doc, "button", 1)              # PLAY: behind REC
led = ap.seat(doc, "light", 5)                # status: back left
arm = ap.seat(doc, "robot_arm", 3)            # the SO-101's servo bus (UART: port 3 or 4)
usb = ap.seat(doc, "usbc", 7)                 # right end, mouth +X
tick("hardware")


def lbox(obj):
    """An Atech object's box in the LOCAL (untilted) frame."""
    g = (obj.Mesh if hasattr(obj, "Mesh") else obj.Shape).copy()
    g.Placement = TILT.inverse().multiply(g.Placement)
    return g.BoundBox


def W_(s):
    """Local frame -> world (tilted back, standing on its feet)."""
    s = s.copy()
    s.transformShape(TILT_M)
    return s


def L_(s):
    """World -> local frame."""
    s = s.copy()
    s.transformShape(LOCAL_M)
    return s


def to_local(x, y, z):
    return TILT.inverse().multVec(V(x, y, z))


def box(x0, x1, y0, y1, z0, z1):
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(b):
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


BB = lbox(board)
KB, SB, RB, PB, LB, AB, UB = [lbox(m) for m in (knob, scr, rec, play, led, arm, usb)]
Z_TOP = max(b.ZMax for b in (SB, RB, PB, LB, AB, UB)) + AIR + WALL     # the deck's top face
# the podium in the world: its front where the deck's top meets YP, its
# top PODIUM over the desk
YPW = TILT.multVec(V(0, YP, Z_TOP)).y
Y1W = YPW + REACH
HP = PODIUM
YD = to_local(0, YPW + 2 * CORNER + 8.0, Z_TOP).y      # the deck's plan runs on into the podium
print("DOCK %.0f x %.0f, deck %.1f thick at the front, podium %.0f high, leaning %.1f deg" % (
    2 * X1, Y1W - Y0, Z_TOP, HP, ALPHA))


# ------------------------------------------------------------ the body
def above_desk(z):
    """Everything over the world plane z, in the local frame."""
    return L_(box(-400, 400, -400, 800, z, 600))


def deck(t):
    """The deck inset t: the rounded plan extruded to its top, cut by the
    foot plane (planes and cylinders only - robust booleans)."""
    w = cad.rounded_rect_wire(2 * (X1 - t), (YD - Y0) - 2 * t, max(CORNER - t, 0.6), (0, (Y0 + YD) / 2, -80), "Z")
    s = Part.Face(w).extrude(V(0, 0, 80 + Z_TOP - t))
    return s.common(above_desk(RUB + t))


def podium_w(t):
    """The podium inset t, in the world (upright, its top level)."""
    return cad.rounded_box(2 * (X1 - t), REACH - 2 * t, HP - RUB - 2 * t, max(CORNER - t, 0.6),
                           at=(-X1 + t, YPW + t, RUB + t))


def core(t):
    return cad.fuse_one(deck(t), L_(podium_w(t)))


def wz(p):
    """A local point's height over the desk."""
    return RUB + (p.y - Y0) * SIN_A + p.z * COS_A


d0 = deck(0.0)
d0 = cad.soften(d0, EDGE_R, [e for e in d0.Edges if e.BoundBox.ZMin > Z_TOP - 1e-3])
d0 = cad.soften(d0, FOOT_R, [e for e in d0.Edges if all(abs(wz(v.Point) - RUB) < 1e-3 for v in e.Vertexes)])
p0 = podium_w(0.0)
p0 = cad.soften(p0, EDGE_R, [e for e in p0.Edges if e.BoundBox.ZMin > HP - 1e-3])
p0 = cad.soften(p0, FOOT_R, [e for e in p0.Edges if e.BoundBox.ZMax < RUB + 1e-3])
outer = cad.fuse_one(d0, L_(p0))
# the core keeps SHARP inner edges (a filleted core reads as clip channels)
body = cad.hollow(outer, WALL, core=core)
skin = core(0.5)                              # clips ribs 0.5 mm under the outer skin
inner = core(WALL - 0.5)                      # clips bosses 0.5 mm into the wall
tick("body")
SPLIT = Z_PCB - 2.0                           # in the cavity: the lip's top stays under the PCB top
base, top = cad.split(body, "Z", at=SPLIT, lip=1.2)
tick("split")


def floor_z(x, y):
    """The base's inner floor height at local (x, y) (the foot plane leans)."""
    return -(y - Y0) * TAN_A + WALL / COS_A


def foot_z(y):
    """The foot's outer face at local y."""
    return -(y - Y0) * TAN_A


# the fixed base holds the board: pads 0.1 mm under it (0.5 mm into the
# floor), fences off its ends
UNDER = BB.ZMin - 0.1
pads = [box(x - 4, x + 4, y - 4, y + 4, floor_z(x, y + 4) - 0.5, UNDER)
        for x in (BB.XMin + 10, 0.0, BB.XMax - 10) for y in (-22.0, 22.0)]
fences = [box(BB.XMin - 1.8, BB.XMin - 0.3, y0, y0 + 6, floor_z(BB.XMin, y0 + 6) - 0.5, Z_PCB - 0.8)
          for y0 in (-17.0, 11.0)]
fences += [box(BB.XMax + 0.3, BB.XMax + 1.8, y0, y0 + 6, floor_z(BB.XMax, y0 + 6) - 0.5, Z_PCB - 0.8)
           for y0 in (-17.0, 11.0)]
base = cad.fuse_one(base, *[p.common(skin) for p in pads + fences])
# board retention: two ribs from the deck down onto the spine (0.2 mm off
# it), between the rows
SPINE_Z = BB.ZMax
top = cad.fuse_one(top, *[box(x - 2, x + 2, -6, 6, SPINE_Z + 0.2, Z_TOP - WALL + 0.5) for x in (-30.0, 10.0)])
# six M2.5 screws from below into insert bosses in the top: off the
# board's ends, and in the podium's back corners (on the corner's
# diagonal, 5.5 mm inside the wall)
SX = BB.XMax + 0.6 + 3.0
DG = max(CORNER - WALL - 5.5, 0.0) / math.sqrt(2.0)
POD = [(sx * (X1 - CORNER + DG), Y1W - CORNER + DG) for sx in (-1, 1)]
SCREWS = [(-SX, -22.0), (-SX, 22.0), (SX, -22.0), (SX, 22.0)]
SCREWS += [(to_local(x, y, RUB).x, to_local(x, y, RUB).y) for x, y in POD]
INSERT_D = {"M2": 3.2, "M2.5": 3.6, "M3": 4.3}[SCREW]
screws = []
for x, y in SCREWS:
    zb = foot_z(y)
    base, top = cad.screw_through(base, top, (x, y, zb), size=SCREW, ribs=0)
    ring = [(0.0, 0.0)] + [(rr * math.cos(math.radians(a_)), rr * math.sin(math.radians(a_)))
                           for rr in (1.5, 3.2) for a_ in range(0, 360, 45)]
    z0 = max(floor_z(x + ex, y + ey) for ex, ey in ring) + 0.1
    top = cad.fuse_one(top, cyl(INSERT_D / 2 + 1.2, (x, y, z0), 120).common(inner))
    top = cad.cut(top, cyl(INSERT_D / 2, (x, y, z0 - 0.1), 7.0))
    screws.append(cad.screw("csk_phillips", SCREW, 8, at=(x, y, zb), axis="+Z"))
tick("base + screws")


def insert(shell, cutter):
    """(shell with the opening, the piece that fills it exactly)."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1 or not rest.isValid() or len(rest.Solids) != len(shell.Solids):
        raise cad.CadError("insert: the cutter does not cleanly cross the wall")
    return rest, piece


def zbox(w, d, r, cx, cy, z0, z1):
    return cad.rounded_box(w, d, z1 - z0, r, at=(cx - w / 2, cy - d / 2, z0))


# ------------------------------------------------------------ the deck
# REC and PLAY: caps through the deck (flange 0.1 mm under it), a plunger
# to 0.16 mm over each module's own cap
base_z = Z_TOP - WALL - 0.9
keys = {}
for nm, kb in (("Key_Rec", RB), ("Key_Play", PB)):
    kx, ky, _kz = centre(kb)
    cap = cad.button_cap((KEY, KEY), (Z_TOP + 1.8) - base_z, dome=0.6, flange=0.8, at=(kx, ky, base_z), axis="+Z")
    top = cad.opening_for(top, cap, clearance=0.25, chamfer=0.4, axis="+Z")
    keys[nm] = cad.fuse_one(cap, cyl(3.0, (kx, ky, kb.ZMax + 0.16), base_z - (kb.ZMax + 0.16) + 0.5))
# the screen: a black bezel frame set RECESS down in its opening, a smoked
# window inside it over the active area
sx, sy, _sz = centre(SB)
top, bezel = insert(top, zbox(LABEL[0] + 2 * BEZEL, LABEL[1] + 2 * BEZEL, 3.0 + BEZEL, sx, sy, Z_TOP - WALL - 1,
                              Z_TOP + 1))
bezel = bezel.cut(box(-300, 300, -300, 300, Z_TOP - RECESS, Z_TOP + 2))
bezel, window = insert(bezel, zbox(LABEL[0], LABEL[1], 3.0, sx, sy, Z_TOP - WALL - 2, Z_TOP + 2))
# the status light: a frosted lens through the deck, a pipe under it to
# 0.5 mm over the LEDs
lx, ly, _lz = centre(LB)
top, lens = insert(top, cyl(LENS_R, (lx, ly, Z_TOP - WALL - 1), WALL + 2))
lens = cad.fuse_one(lens, cyl(LENS_R - 1.0, (lx, ly, LB.ZMax + 0.5), Z_TOP - WALL + 0.5 - (LB.ZMax + 0.5)))
# the arm's cable: a rubber grommet through the deck over the integrator,
# its slot the servo-bus plug's and cable's way out (up, then back into
# the podium's cable gate)
ax, ay, _az = centre(AB)
gy = ay + 3.5
top, grommet = insert(top, zbox(GROMMET[0], GROMMET[1], 6.0, ax, gy, Z_TOP - WALL - 1, Z_TOP + 1))
grommet = cad.cut(grommet, zbox(SLOT[0], SLOT[1], SLOT[0] / 2 - 0.01, ax, gy, Z_TOP - WALL - 2, Z_TOP + 2))
# the dial crown: a cone rising out of the deck round the knob, its rim
# 0.4 mm over the cap's top (only a module's working face may look out,
# so the cap sits FLUSH in a well); a frosted ring in the well's floor
# over the 12 LEDs, a brushed bezel in a rebate round the rim
kx, ky, _kz = centre(KB)
z_rim = KB.ZMax + 0.4
crown = Part.makeCone(CROWN[0], CROWN[1], z_rim - (Z_TOP - 1.0), V(kx, ky, Z_TOP - 1.0))
top = cad.cut(cad.fuse_one(top, crown), cyl(DISH_R, (kx, ky, Z_TOP - 0.01), 80))
ring_cut = cad.cut(cyl(RING_R[1], (kx, ky, Z_TOP - WALL - 1), WALL + 2),
                   cyl(RING_R[0], (kx, ky, Z_TOP - WALL - 2), WALL + 4))
dial_ring = top.common(ring_cut)
top = cad.cut(top, cyl(RING_R[1], (kx, ky, Z_TOP - WALL - 1), WALL + 2))
reb = cad.cut(cyl(CROWN[1] + 1.0, (kx, ky, z_rim - 2.5), 3.5), cyl(CROWN[1] - 1.4, (kx, ky, z_rim - 3.0), 6.0))
dial_bezel = top.common(reb)
top = cad.cut(top, reb)
dial_bezel = cad.soften(dial_bezel, 0.5, [e for e in dial_bezel.Edges if e.BoundBox.ZMin > z_rim - 1e-3
                                          and e.BoundBox.XLength > 2 * CROWN[1] - 0.5])
# USB-C in the right end: a pocket brings the wall to 0.25 mm off the mouth
uy, uz = (UB.YMin + UB.YMax) / 2, Z_PCB + 5.9


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


pocket = xprism(uy - 6.5, uy + 6.5, uz - 5.0, uz + 5.0, UB.XMax + 1.3, X1 + 5, 3)
liner = cad.cut(xprism(uy - 8.5, uy + 8.5, max(uz - 7.5, SPLIT + 1.6), uz + 7.5, UB.XMax + 0.25, X1 + 2, 4), pocket)
top = cad.fuse_one(cad.cut(top, pocket), liner.common(skin))
tick("deck")

# ------------------------------------------------------------ into the world
parts = {"Top": top, "Base": base, "Bezel": bezel, "Screen_Window": window, "Status_Lens": lens,
         "Dial_Ring": dial_ring, "Dial_Bezel": dial_bezel, "Cable_Grommet": grommet}
parts.update(keys)
parts = {k: W_(v) for k, v in parts.items()}
screws = [W_(s) for s in screws]
# the USB-C opening is MEASURED from the module, so it is cut after the tilt
parts["Top"] = cad.socket_opening(parts["Top"], usb, margin=1.5)
T = parts["Top"]
# the cable gate: a block behind the podium's front edge, a notch through
# it - the cable rises out of the grommet and lies in the notch onto the plate
gx = W_(Part.Vertex(V(ax, gy, Z_TOP))).Point.x
T = cad.fuse_one(T, box(gx - GATE[0] / 2 - 3, gx + GATE[0] / 2 + 3, YPW, YPW + GATE[1] + 6.0,
                        HP - GATE[1] - 4.0, HP + 1).common(W_(skin)))
T = cad.cut(T, box(gx - GATE[0] / 2, gx + GATE[0] / 2, YPW - 4.0, YPW + GATE[1], HP - GATE[1], HP + 5))
# the arm plate: a brushed plate in a PLATE_SINK recess in the podium's
# top, four M3 screws into heat-set insert sleeves; the arm's bolt
# pattern (four holes over M4 insert pockets) - BOLT IS A PLACEHOLDER
PL = min(REACH - GATE[1] - 15.0, 2 * X1 - 24.0)
BOLT = PL - 30.0
PCX, PCY = 0.0, YPW + GATE[1] + 7.0 + PL / 2
PZ0, PZ1 = HP - PLATE_SINK, HP - PLATE_SINK + PLATE_T
T, plate = T.cut(zbox(PL, PL, 8.0, PCX, PCY, PZ0, HP + 5)), zbox(PL, PL, 8.0, PCX, PCY, PZ0, PZ1)
plate_screws = []
for dx, dy in ((-(PL / 2 - 6), 0), (PL / 2 - 6, 0), (0, -(PL / 2 - 6)), (0, PL / 2 - 6)):
    x, y = PCX + dx, PCY + dy
    T = cad.fuse_one(T, cyl(4.3 / 2 + 1.4, (x, y, HP - WALL - 9.5), 10.0))
    T = cad.cut(T, cyl(4.3 / 2, (x, y, PZ0 - 8.0), 8.0 + 0.01))
    plate = cad.countersink(plate, (x, y, PZ1), "-Z", 3.4, 6.6, 90.0)
    plate_screws.append(cad.screw("csk_phillips", "M3", 10, at=(x, y, PZ1), axis="-Z"))
for sx_ in (-1, 1):
    for sy_ in (-1, 1):
        x, y = PCX + sx_ * BOLT / 2, PCY + sy_ * BOLT / 2
        T = cad.fuse_one(T, cyl(5.7 / 2 + 1.6, (x, y, HP - WALL - 9.5), 10.0))
        T = cad.cut(T, cyl(5.7 / 2, (x, y, PZ0 - 9.0), 9.0 + 0.01))
        plate = cad.cut(plate, cyl(2.25, (x, y, PZ0 - 1), PLATE_T + 2))
parts["Top"] = T
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
UP_W, N_W = TILT.Rotation.multVec(V(0, 1, 0)), TILT.Rotation.multVec(V(0, 0, 1))   # the deck's axes


def on_deck(x, y, z=None):
    """A local point on the deck's top, in the world."""
    return TILT.multVec(V(x, y, Z_TOP if z is None else z))


# the deck (its parts are back in the LOCAL frame for the ring groove):
# the parting-line reveal, a grip groove along the front, lettering
T = L_(parts["Top"])
T = cad.groove_ring(T, "Z", SPLIT + 2.2, w=0.8, depth=0.6)
Y_GRIP = Y0 + EDGE_R + 0.8
T = cad.cut(T, box(KNOB_C[0] + CROWN[0] + 4.0, X1 - CORNER - 4.0, Y_GRIP - 0.6, Y_GRIP + 0.6, Z_TOP - 0.6, Z_TOP + 1))
T = cad.text(T, "ATECH", (sx, (Y_GRIP + SB.YMin) / 2 - 1.0, Z_TOP), (0, 0, 1), 4.5, depth=0.4, mode="deboss",
             up=(0, 1, 0))
parts["Top"] = W_(T)
# key legends, debossed in the caps
for nm, kb, t in (("Key_Rec", RB, "REC"), ("Key_Play", PB, "PLAY")):
    kx_, ky_, _ = centre(kb)
    parts[nm] = cad.text(parts[nm], t, on_deck(kx_, ky_, Z_TOP + 1.8), N_W, 3.5, depth=0.4, mode="deboss", up=UP_W)
# the grommet stands 1 mm proud, its rim rolled
G = L_(parts["Cable_Grommet"])
rim = cad.cut(zbox(GROMMET[0], GROMMET[1], 6.0, ax, gy, Z_TOP - 0.3, Z_TOP + 1.0),
              zbox(SLOT[0], SLOT[1], SLOT[0] / 2 - 0.01, ax, gy, Z_TOP - 1, Z_TOP + 2))
rim = cad.soften(rim, 0.6, [e for e in rim.Edges if e.BoundBox.ZMin > Z_TOP + 1.0 - 1e-3])
parts["Cable_Grommet"] = W_(cad.fuse_one(G, rim))
# the arm plate: rolled top edge, four corner locating lugs round the
# arm's base, an embossed "SO-101" and an arrow to the arm's front (+Y,
# away from the controls)
P = plate
P = cad.soften(P, 0.8, [e for e in P.Edges if e.BoundBox.ZMin > PZ1 - 1e-3 and e.BoundBox.ZMax < PZ1 + 1e-3
                        and (e.BoundBox.XLength > PL - 20 or e.BoundBox.YLength > PL - 20)])
LUG = BOLT / 2 + 6.0                          # the lugs' inner faces: 6 mm outside the bolt pattern
lugs = []
for sx_ in (-1, 1):
    for sy_ in (-1, 1):
        lugs += [box(PCX + sx_ * (LUG - 12.0), PCX + sx_ * (LUG + 3.0), PCY + sy_ * LUG, PCY + sy_ * (LUG + 3.0),
                     PZ1 - 0.5, PZ1 + 3.0),
                 box(PCX + sx_ * LUG, PCX + sx_ * (LUG + 3.0), PCY + sy_ * (LUG - 12.0), PCY + sy_ * (LUG + 3.0),
                     PZ1 - 0.5, PZ1 + 3.0)]
P = cad.fuse_one(P, *lugs)
P = cad.text(P, "SO-101", (PCX, PCY - BOLT / 2 + 9.0, PZ1), (0, 0, 1), 9.0, depth=0.6, mode="emboss", up=(0, 1, 0))
arrow = Part.Face(Part.makePolygon([V(PCX + a_, PCY + b_, PZ1 - 0.2) for a_, b_ in (
    (-3.0, -10.0), (3.0, -10.0), (3.0, 4.0), (9.0, 4.0), (0.0, 16.0), (-9.0, 4.0), (-3.0, 4.0), (-3.0, -10.0))]))
P = cad.fuse_one(P, arrow.extrude(V(0, 0, 0.8)))
plate = P
# the back: the 12 V jack's opening (a panel DC jack: the arm's servo
# supply - the USB-C module does not feed the servo rail) and its legend
B = parts["Base"]
JX, JZ = -(X1 - CORNER - 14.0), RUB + WALL + 8.0
B = cad.cut(B, cyl(4.0, (JX, Y1W + 1.0, JZ), WALL + 2.0, (0, -1, 0)))
B = cad.text(B, "12V", (JX, Y1W, JZ + 8.5), (0, 1, 0), 4.0, depth=0.4, mode="deboss")
# under the base: slot vents and a model mark
MID = (YPW + Y1W) / 2
B = cad.grille(B, (0.0, MID + 8.0, RUB), (0, 0, -1), (48, 26), kind="slot", hole=2.0, pitch=4.5)
B = cad.text(B, "ATECH AD-1", (0.0, MID - 16.0, RUB), (0, 0, -1), 4.5, depth=0.4, mode="deboss", up=(0, -1, 0))
parts["Base"] = B
tick("stage B")


# ------------------------------------------------------------ feet
B = parts["Base"]
# six feet: the deck's front corners, mid-podium, and inside the back
# corners' screws
FEET = [(sx * (X1 - 14.0), y) for sx in (-1, 1) for y in (TILT.multVec(V(0, Y0, 0)).y + 14.0,
                                                          (YPW + Y1W) / 2 - 10.0)]
FEET += [(sx * (X1 - CORNER - 12.0), Y1W - 13.0) for sx in (-1, 1)]
B = cad.fuse_one(B, *[cyl(6.0, (x, y, RUB + WALL - 0.5), 1.5) for x, y in FEET])
rubbers = []
for x, y in FEET:
    B = cad.cut(B, cyl(4.6, (x, y, RUB - 1), 2.2))
    rubbers.append(cad.foot(9, RUB + 1.2, style="dome", at=(x, y, RUB + 1.2)))
parts["Base"] = B
parts["Arm_Plate"] = plate
tick("feet")


# ------------------------------------------------------------ parts
def part(name, shape, colour=None):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour or name])
    return o


for nm, sh in parts.items():
    o = part(nm, sh)
    if nm in ("Screen_Window", "Status_Lens", "Dial_Ring"):
        o.ViewObject.Transparency = cad.transparency(COLOURS[nm])
for i, sh in enumerate(rubbers):
    part("Rubber_%d" % (i + 1), sh, "Rubber")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
for i, sh in enumerate(plate_screws):
    part("Plate_Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
