"""Example: "a countertop pet feeder" - a base unit with a rotary dispenser, a hopper bin with a window, a bowl.

fork this file for a pet feeder / dispenser (an automatic feeder, a
treat or cereal dispenser, a fish feeder, a pill dispenser - a motor-driven
rotor under a hopper that drops portions down a
spout); change PARAMETERS and the outlines.
ARCHETYPE: feeder

How it is built (R700):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board LANDSCAPE_UP high in the base unit's face (modules facing the
    front, -Y): the screen (10, 11) behind a smoked lens in a recessed
    black bezel tray (the feeding schedule), the FEED key (13) beside it
    under a key cap, a status light (3) under the screen behind a frosted
    pipe, USB-C (7) in a pocket in the left side; the dc_motor CABLED from
    port 4 straight down (pins up, shaft down: twist-free) into a cradle on
    the dispenser, its shaft in the hub of a six-pocket rotor turning in a
    closed drum - food falls from the hopper down a duct into the drum's
    rear pocket, rides round and drops out of the front one into a curved
    spout over the bowl. The base unit is ONE plan outline (a crisp front,
    CORNER-rounded back) and one side outline (cad.profile_body) hollowed
    with its own sharp core and split front / back with a lip (the fixed
    Back carries the board, the duct and the dispenser on two pinned
    posts); it stands on a graphite Base plate whose tongue carries the
    bowl, four M2.5 screws from below into insert sleeves in both halves.
    The hopper Bin is the same plan, pinned onto the base unit; its top is
    split off as the Lid on a pin hinge (the pin modelled).
  * STAGE B - details: the hopper window, a funnel in the bin, the
    parting-line reveal, key / light legends, lettering, a lid finger
    notch, rubber feet.
DETAILS (visible, 26 of 34): 1 flat face with crisp corners; 2 soft
rounded back; 3 soft EDGE fillets; 4 smoked lens over the screen;
5 recessed black bezel tray; 6 mask window over the active area; 7 FEED
key cap with flange and plunger; 8 raised ring round it; 9 "FEED" under
the key; 10 frosted status-light pipe; 11 USB-C pocket with liner in the
left side; 12 curved spout over the bowl; 13 brushed steel bowl with a
rolled rim; 14 its foot ring in a recess in the base tongue;
15 graphite base plate with a rounded tongue; 16 hopper bin; 17 its
clear window; 18 "MAX" over the window; 19 lid split off the bin's top;
20 full-length pin hinge; 21 lid finger notch; 22 "ATECH" on the lid;
23 parting-line reveal round the base unit; 24 "ATECH" on the face;
25 four countersunk screws under the base; 26 four rubber feet. Inside:
27 six-pocket rotor on the motor shaft; 28 the closed drum with inlet
and outlet; 29 motor cradle cheeks; 30 food duct from the bin; 31 funnel
into the bin's outlet; 32 two posts pinned into the drum; 33 board
carrier wall, ledges and pads, a rib onto the spine; 34 locating pegs
under the bin.
Materials: warm-white base unit, graphite base, plinth and lid,
smoked window and lens, black bezel, coral FEED key, brushed bowl and
spout, frosted status light, rubber feet, chrome screws and pin.
MEASURED (R700, 2026-10-26): see test_kit_examples_r500 (TIMINGS line).
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
    "Front", "Bezel", "Lens", "Status_Lens", "Feed_Key", "Bin", "Window", "Lid", "Hinge_Pin",
    "Bowl", "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4", "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    # the key cap presses the FEED button through its opening (a declared cover)
    "covers": {"Feed_Key": "button_p13"}}
REVIEW_CLOSEUPS = ["Front", "Bin", "Rotor"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them (the hardware frame below is
# the board's and the dispenser's own: never move it with a knob).
WIDTH = 160.0      # RESTYLE 136..184 width: across the face (x), centred on the board
DEPTH = 150.0      # RESTYLE 127..173 length: front face to back (y)
HEIGHT = 110.0     # RESTYLE 93..127 height: the hopper bin (its capacity)
CORNER = 24.0      # RESTYLE 20..28 radius: the back plan corners (the front stays crisp)
WALL = 2.4         # RESTYLE 2.0..2.8 wall
# end RESTYLE
# Frame: x across, y front (-) to back, z up; the desk at z = 0.
# The hardware frame (fixed: the board and the dispenser decide it):
ZB = 180.0                           # board bottom (the motor hangs under it on its ribbon)
Y_IN = -13.0                         # the front wall's inner face (0.4 mm in front of the modules)
FOOT = 1.5                           # rubber feet under the base plate
PL = 12.0                            # the base plate's top: the base unit stands on it
ZU = ZB + 70.0                       # the base unit's top (the bin stands on it)
EDGE = 3.0                           # soft fillet round every outer edge
R_FRONT = 4.0                        # the front's plan corners: crisp (the USB-C liner needs the side flat)
AX, AY = 70.0, 17.57                 # the dispenser's axis: the motor shaft (measured, cable port 4)
RR = 26.0                            # rotor radius (the drum 1 mm round it, 2 mm walls)
CH0 = 78.0                           # the drum's bottom (the spout drops 20 mm to the face)
CH1 = CH0 + 22.0                     # the drum's top
OUTLET = (60.0, AY - math.sqrt(16.0 ** 2 - 10.0 ** 2))   # front pocket, on the face's centre line
INLET = (AX, AY + 20.0)              # rear pocket, under the duct
TONGUE = 110.0                       # the base plate reaches this far in front of the face
BOWL_R, BOWL_H = 42.0, 28.0          # the bowl: rim radius, height (the spout clears its rim)
LID_T = 12.0                         # the lid: split off the bin's top
X0, X1 = 60.0 - WIDTH / 2, 60.0 + WIDTH / 2
YF = Y_IN - WALL                     # the front face
YB = YF + DEPTH                      # the back
RECESS, BEZEL, LENS_R = 1.0, 4.0, 3.0
SCREEN_WIN = (28.0, 16.0)            # mask window over the screen (active area 25.6 x 13.5)
SCREW = "M2.5"
COLOURS = {"Base": "graphite", "Back": "#efeae2", "Front": "#efeae2", "Bezel": "matte_black",
           "Lens": "smoked", "Status_Lens": "frosted", "Feed_Key": "coral", "Dispenser": "satin_grey",
           "Rotor": "orange", "Bin": "#efeae2", "Window": "smoked", "Lid": "graphite",
           "Hinge_Pin": "chrome", "Bowl": "brushed_alu", "Rubber": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
LANDSCAPE_UP = Rotation(Vector(0, 0, 1), 180).multiply(Rotation(Vector(0, 1, 0), -90))
board = ap.board_object(doc)
board.Placement = Placement(Vector(), LANDSCAPE_UP)
_b = ap.bbox(board)
board.Placement = Placement(Vector(-_b.XMin, 0, ZB - _b.ZMin), LANDSCAPE_UP)   # x 0..120, z 180..240
BB = ap.bbox(board)
scr = ap.seat(doc, "screen", (10, 11))         # top row, left of centre: the schedule
key = ap.seat(doc, "button", 13)               # top row, right of the screen: FEED now
led = ap.seat(doc, "light", 3)                 # bottom row, under the screen: the status glow
usb = ap.seat(doc, "usbc", 7)                  # left end, mouth -X
# the motor: CABLED from port 4 (bottom row) straight down - pins up, the
# PCB facing back (face x cable along X: no twist), the shaft down on the
# dispenser's axis; its tip 0.3 mm over the drum's top minus the shaft
motor, motor_rib = ap.cable(doc, "dc_motor", 4, ap.module_placement(
    "dc_motor", (AX, AY - 0.57, CH1 + 0.3 - 8.8 + 24.15), face="+Y", cable="+Z"))
MB = ap.bbox(motor)
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(m):
    b = ap.bbox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


def corner(c, r, a0, a1, n=6):
    """A plan corner as n straight facets (the profile fillet rounds them)."""
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def plan_pts(x0, x1, y0, y1, rf, rb):
    """A plan outline: front corners rf, back corners rb (facets)."""
    return (corner((x0 + rf, y0 + rf), rf, 180, 270, 2 if rf < 8 else 6)
            + corner((x1 - rf, y0 + rf), rf, 270, 360, 2 if rf < 8 else 6)
            + corner((x1 - rb, y1 - rb), rb, 0, 90) + corner((x0 + rb, y1 - rb), rb, 90, 180))


def zprism(pts, z0, z1):
    f = Part.Face(Part.makePolygon([V(x, y, z0) for x, y in pts + pts[:1]]))
    return f.extrude(V(0, 0, z1 - z0))


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


def ring(r0, r1, c, z0, z1):
    return cad.cut(cyl(r1, (c[0], c[1], z0), z1 - z0), cyl(r0, (c[0], c[1], z0 - 1), z1 - z0 + 2))


# ------------------------------------------------------------ the base unit
PLAN = plan_pts(X0, X1, YF, YB, R_FRONT, CORNER)
SIDE = [(X0, PL), (X1, PL), (X1, ZU), (X0, ZU)]
body = cad.profile_body(SIDE, PLAN, spline=False, fillet=(EDGE, EDGE))
# the core keeps SHARP inner edges (a filleted core's concave rounds read
# to ./check as open clip channels)
core = cad.profile_body(SIDE, PLAN, spline=False, fillet=None, inset=WALL)
unit = cad.cut(body, core)
unit = cad.groove_ring(unit, "Z", PL + 8.0, w=0.8, depth=0.6)       # the parting-line reveal
tick("body")
# split front / back just behind the board: the fixed Back carries it, the
# Front (and everything in the modules' slide paths) is fitted after
SPLIT_Y = BB.YMax - 0.3
front, back = cad.split(unit, "Y", at=SPLIT_Y, lip=1.2)
tick("split")
XI0, XI1, YI1 = X0 + WALL, X1 - WALL, YB - WALL
FLOOR = PL + WALL                               # the base unit's floor top

# the board: a carrier wall behind it (from the board's bottom edge to the
# top wall), pads 0.1 mm off its back, ledges 0.3 mm under / over its long
# edges - clear of the motor's plug and ribbon (x 62..78)
CY0 = BB.YMax + 3.5
carrier = box(XI0 - 0.5, XI1 + 0.5, CY0, CY0 + WALL, ZB - 3.0, ZU - WALL + 0.5).common(zprism(PLAN, 0, ZU))
pads = [box(x, x + 6, BB.YMax + 0.1, CY0 + 0.5, z, z + 6) for x in (8, 57, 106) for z in (ZB + 7, ZB + 47)]
ledges = [box(x0, x1, 0.6, CY0 + 0.5, BB.ZMin - 2.3, BB.ZMin - 0.3) for x0, x1 in ((4, 58), (82, 116))]
ledges.append(box(4, 116, 0.6, CY0 + 0.5, BB.ZMax + 0.3, BB.ZMax + 2.3))
# the food duct from the bin down to the drum's inlet (0.3 mm over it)
duct = cad.cut(cyl(8.5, (INLET[0], INLET[1], CH1 + 0.3), ZU - WALL + 0.5 - (CH1 + 0.3)),
               cyl(6.5, (INLET[0], INLET[1], CH1 - 1), ZU - CH1 + 5))
# two posts from the floor to the drum's bottom, a pin on each into it
POSTS = [(AX - 20.0, AY + 10.0), (AX + 20.0, AY + 10.0)]
posts = [cyl(4.0, (x, y, FLOOR - 0.5), CH0 - (FLOOR - 0.5)) for x, y in POSTS]
pins = [cyl(1.5, (x, y, CH0 - 0.5), 2.0) for x, y in POSTS]
back = cad.fuse_one(back, carrier, *pads, *ledges, duct, *posts, *pins)
back = cad.cut(back, cyl(6.5, (INLET[0], INLET[1], ZU - WALL - 1), WALL + 2))     # the duct through the top
# board retention: a rib from the front wall onto the spine (0.2 mm off)
front = cad.fuse_one(front, box(66, 70, Y_IN - 0.5, BB.YMin - 0.2, ZB + 24, ZB + 36))
tick("back")

# ------------------------------------------------------------ the dispenser
# a closed drum (floor, wall, top) round the rotor: the inlet over the rear
# pocket, the outlet under the front one, the shaft through the top; two
# cradle cheeks 0.3 mm off the motor's sides
drum = cad.cut(cyl(RR + 3.0, (AX, AY, CH0), CH1 - CH0), cyl(RR + 1.0, (AX, AY, CH0 + 2.0), CH1 - CH0 - 4.0))
drum = cad.fuse_one(drum, box(MB.XMin - 2.3, MB.XMin - 0.3, MB.YMin + 2, MB.YMax - 2, CH1 - 0.5, CH1 + 28),
                    box(MB.XMax + 0.3, MB.XMax + 2.3, MB.YMin + 2, MB.YMax - 2, CH1 - 0.5, CH1 + 28))
drum = cad.cut(drum, [cyl(6.0, (INLET[0], INLET[1], CH1 - 3), 4), cyl(7.2, (OUTLET[0], OUTLET[1], CH0 - 1), 4),
                      cyl(2.6, (AX, AY, CH1 - 3), 4)]
               + [cyl(1.65, (x, y, CH0 - 1), 4) for x, y in POSTS])
# the rotor: a hub on the shaft (bore 3.3, blind, 0.3 mm past the tip) and
# six vanes - six pockets that carry a portion from the inlet to the outlet
TIP = MB.ZMin
hub = cad.cut(cyl(7.0, (AX, AY, CH0 + 2.5), CH1 - CH0 - 5.0), cyl(1.65, (AX, AY, TIP - 0.3), 20))
vanes = []
for k in range(6):
    v = box(6.0, RR - 0.5, -1.0, 1.0, CH0 + 2.5, CH1 - 2.5)
    v.rotate(V(0, 0, 0), V(0, 0, 1), 60.0 * k + 30.0)
    v.translate(V(AX, AY, 0))
    vanes.append(v)
rotor = cad.fuse_one(hub, *vanes)
tick("dispenser")

# ------------------------------------------------------------ the spout
# a curved tube fused into the face: from 0.5 mm under the outlet straight
# down, round a 22 mm bend to 30 deg and out over the bowl's rim; its bore
# (12 mm: kibble) opened at both ends. Dense points on the arc and the
# line: a sparse spline bulges
RS, SLOPE, RUN = 22.0, 60.0, 22.0
SP = [(OUTLET[0], OUTLET[1] - RS + RS * math.cos(math.radians(a)), CH0 - 0.5 - RS * math.sin(math.radians(a)))
      for a in range(0, int(SLOPE) + 1, 10)]
d1 = V(0, -math.sin(math.radians(SLOPE)), -math.cos(math.radians(SLOPE)))
SP += [tuple(V(*SP[-1]) + d1 * (RUN * k / 3.0)) for k in (1, 2, 3)]
front = cad.fuse_one(front, cad.pipe(SP, r=7.5, caps="flat"))
# (the bore's path runs 2 mm past both ends: coincident end faces made the
# cut INVALID, MEASURED)
SPB = [(SP[0][0], SP[0][1], SP[0][2] + 2.0)] + SP + [tuple(V(*SP[-1]) + d1 * 2.0)]
front = cad.cut(front, cad.pipe(SPB, r=6.0, caps="flat"))
tick("spout")

# ------------------------------------------------------------ the base plate + bowl
BOWL_C = (60.0, YF - BOWL_R - 4.0)               # its rim 4 mm off the face
bplan = plan_pts(X0, X1, YF - TONGUE, YB, 40.0, CORNER)
base = cad.profile_body([(X0, FOOT), (X1, FOOT), (X1, PL), (X0, PL)], bplan, spline=False, fillet=(EDGE, 1.5))
base = cad.cut(base, cyl(32.3, (BOWL_C[0], BOWL_C[1], PL - 2.0), 3.0))       # the bowl's recess
B0 = PL + 1.0                                   # the bowl's bottom (its foot ring 3 mm under it)
bowl = cad.revolve_profile([(0, B0), (30.0, B0), (BOWL_R - 2.0, B0 + BOWL_H - 2.5), (BOWL_R, B0 + BOWL_H - 1.0),
                            (BOWL_R - 0.8, B0 + BOWL_H), (BOWL_R - 2.6, B0 + BOWL_H),
                            (BOWL_R - 4.4, B0 + BOWL_H - 2.5), (28.4, B0 + 2.2), (0, B0 + 2.2)],
                           at=(BOWL_C[0], BOWL_C[1], 0))
bowl = cad.fuse_one(bowl, ring(28.0, 32.0, BOWL_C, PL - 2.0, B0 + 0.5))
# four M2.5 screws up through the plate into insert sleeves on both
# halves' floors (a heat-set pocket 3.6, open through the floor)
INSERT_D = {"M2": 3.2, "M2.5": 3.6, "M3": 4.3}[SCREW]
SCREWS_B = [(XI0 + 30.0, YI1 - 12.0), (XI1 - 30.0, YI1 - 12.0)]       # clear of the feet
SCREWS_F = [(XI0 + 4.0, -6.5), (XI1 - 4.0, -6.5)]
screws = []
for half, pts_ in (("back", SCREWS_B), ("front", SCREWS_F)):
    sl = [cyl(INSERT_D / 2 + 1.2, (x, y, FLOOR - 0.5), 10.5) for x, y in pts_]
    pk = [cyl(INSERT_D / 2, (x, y, PL - 1.0), WALL + 9.0) for x, y in pts_]
    if half == "back":
        back = cad.cut(cad.fuse_one(back, *sl), pk)
    else:
        front = cad.cut(cad.fuse_one(front, *sl), pk)
for x, y in SCREWS_B + SCREWS_F:
    base = cad.countersink(base, (x, y, FOOT), "+Z", 2.9, 5.6, 90.0)
    screws.append(cad.screw("csk_phillips", SCREW, int(PL - FOOT + 6.0), at=(x, y, FOOT), axis="+Z"))
tick("base + bowl")

# ------------------------------------------------------------ the face
# the schedule: a black bezel tray set RECESS back in its opening, holding
# the smoked lens, its back the mask with the screen window
sx, _sy, sz = centre(scr)
LENS = (sx - 18.0, sx + 18.0, sz - 11.0, sz + 11.0)
lx0, lx1, lz0, lz1 = LENS
front = cad.cut(front, yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, YF - 6, Y_IN + 1))
yt0, yt1 = YF + RECESS, Y_IN + 3.0
tray = cad.fuse_one(yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, yt0, Y_IN + 1),
                    yprism(lx0 - 2, lx1 + 2, lz0 - 2, lz1 + 2, LENS_R + 2, Y_IN + 0.5, yt1))
y_lens1 = Y_IN + 1.7
tray = cad.cut(tray, yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 - 1, y_lens1))
lens = yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 + 0.6, y_lens1 - 0.3)
tray = cad.cut(tray, cad.rounded_box(SCREEN_WIN[0], 10, SCREEN_WIN[1], 1.5,
                                     at=(sx - SCREEN_WIN[0] / 2, yt1 - 5, sz - SCREEN_WIN[1] / 2), edges="y"))
# FEED: a key cap through the face, flange 0.1 mm behind the wall, a
# plunger to 0.16 mm off the module's own cap
kx, _ky, kz = centre(key)
kb = ap.bbox(key)
y_base = Y_IN + 0.9
cap = cad.button_cap(14, y_base - (YF - 1.6), dome=0.8, flange=1.5, at=(kx, y_base, kz), axis="-Y")
front = cad.opening_for(front, cap, clearance=0.25, chamfer=0.4, axis="-Y")
cap = cad.fuse_one(cap, cyl(3.0, (kx, kb.YMin - 0.16, kz), (kb.YMin - 0.16) - y_base + 0.5, (0, -1, 0)))
# the status light: a frosted pipe from 0.4 mm off the LEDs to 0.8 mm proud
gx, _gy, gz = centre(led)
gb = ap.bbox(led)
pipe = cad.lens(14.0, (gb.YMin - 0.4) - (YF - 0.8), dome=0.8, at=(gx, gb.YMin - 0.4, gz), axis="-Y")
front = cad.opening_for(front, pipe, clearance=0.2, chamfer=0.0, axis="-Y")
pipe = cad.fuse_one(pipe, cyl(8.6, (gx, Y_IN + 0.9, gz), 0.8, (0, -1, 0)))
# USB-C on the left side: a pocket brings the wall to 0.25 mm off the
# socket mouth, a liner down into the front wall, the measured opening
ub = ap.bbox(usb)
uy, uz = -5.9, (ub.ZMin + ub.ZMax) / 2
pocket = xprism(uy - 4.5, uy + 4.5, uz - 6.5, uz + 6.5, X0 - 5, ub.XMin - 1.3, 3)
liner = cad.cut(xprism(Y_IN - 0.4, min(uy + 6.5, SPLIT_Y - 0.6), uz - 8.0, uz + 8.0, ub.XMin - 0.25, XI0 - 0.5, 3.0),
                pocket)
front = cad.fuse_one(cad.cut(front, pocket), liner)
front = cad.socket_opening(front, usb, margin=1.5)
tick("face")

# ------------------------------------------------------------ the hopper bin + lid
# the same plan as the base unit, hollowed closed with its own core, its
# top split off as the lid (no lip: it swings on a pin hinge at the back)
ZH = ZU + HEIGHT
BSIDE = [(X0, ZU), (X1, ZU), (X1, ZH), (X0, ZH)]
hb = cad.profile_body(BSIDE, PLAN, spline=False, fillet=(EDGE, EDGE))
hopper = cad.cut(hb, cad.profile_body(BSIDE, PLAN, spline=False, fillet=None, inset=WALL))
bin_, lid = cad.split(hopper, "Z", at=ZH - LID_T)
# the bin's outlet over the duct; two pegs under its floor into holes in
# the base unit's top (0.15 mm clear)
PEGS = [(60.0 - 0.3 * WIDTH, YI1 - 22.0), (60.0 + 0.3 * WIDTH, YI1 - 22.0)]
bin_ = cad.cut(bin_, cyl(6.5, (INLET[0], INLET[1], ZU - 1), WALL + 2))
bin_ = cad.fuse_one(bin_, *[cyl(2.5, (x, y, ZU - 1.8), 2.3) for x, y in PEGS])
back = cad.cut(back, [cyl(2.65, (x, y, ZU - WALL - 1), WALL + 2) for x, y in PEGS])
# the clear window: an insert cut out of the bin's front wall
WZ0, WZ1 = ZU + 14.0, ZH - LID_T - 12.0
bin_, window = bin_.cut(yprism(X0 + 22, X1 - 22, WZ0, WZ1, 8.0, YF - 2, Y_IN + 1)), \
    bin_.common(yprism(X0 + 22, X1 - 22, WZ0, WZ1, 8.0, YF - 2, Y_IN + 1))
# the hinge: knuckles along the back top edge, the pin modelled - then the
# knuckle ends that would hang past the rounded back corners trimmed off
bin0, lid0 = bin_, lid
bin_, lid, motion = cad.pin_hinge(bin_, lid, knuckles=2, pin_d=3.0, clearance=0.2, axis="+Y", part="Lid")
(px, py, pz), _d = motion["axis"]
HX0, HX1 = X0 + CORNER, X1 - CORNER            # the straight back wall
ends = [box(X0 - 10, HX0, YI1 - 10, YB + 15, pz - 10, pz + 10), box(HX1, X1 + 10, YI1 - 10, YB + 15, pz - 10, pz + 10)]
bin_ = cad.fuse_one(cad.cut(bin_, ends), *[e.common(bin0) for e in ends])
lid = cad.fuse_one(cad.cut(lid, ends), *[e.common(lid0) for e in ends])
hinge_pin = cyl(1.5, (HX0 + 0.5, py, pz), HX1 - HX0 - 1.0, (1, 0, 0))
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# a funnel in the bin: a cone from its floor up round the outlet
fz = ZU + WALL - 0.5
# (a 2 mm skin normal to its slope, its top end square to it: an acute
# horizontal top edge read as a 0.15 mm wall, MEASURED)
fn = V(-18.0, 26.5, 0)
fn.normalize()
fn = fn * 2.0
funnel = cad.revolve_profile([(6.5, fz), (9.5, fz), (36.0, fz + 18.0), (36.0 + fn.x, fz + 18.0 + fn.y),
                              (9.5 + fn.x, fz + fn.y), (6.5, fz + fn.y)], at=(INLET[0], INLET[1], 0))
bin_ = cad.fuse_one(bin_, funnel.common(zprism(PLAN, 0, ZH)))
# raised ring round the key; legends and lettering
front = cad.fuse_one(front, cad.soften(cad.cut(cyl(10.8, (kx, YF + 0.8, kz), 1.4, (0, -1, 0)),
                                               cyl(9.3, (kx, YF + 1.0, kz), 2.0, (0, -1, 0))), 0.3))
front = cad.text(front, "FEED", (kx, YF, kz - 15.0), (0, -1, 0), 4.5, depth=0.4, mode="deboss")
front = cad.text(front, "ATECH", (60.0, YF, 130.0), (0, -1, 0), 9, depth=0.6, mode="deboss")
bin_ = cad.text(bin_, "MAX", (60.0, YF, WZ1 + 5.0), (0, -1, 0), 4.5, depth=0.4, mode="deboss")
lid = cad.text(lid, "ATECH", (60.0, (YF + YB) / 2, ZH), (0, 0, 1), 8, depth=0.5, mode="deboss", up=(0, 1, 0))
# a finger notch under the lid's front edge
# (the cutter starts 3 mm under the lid: its rounded bottom corners left a
# 0.5 mm sliver on the lid's edge when they sat on it, MEASURED)
lid = cad.cut(lid, cad.rounded_box(40, 6, 8, 2.0, at=(40.0, YF - 1, ZH - LID_T - 3.0), edges="y"))
# rubber feet in recesses under the base plate
feet = []
for x in (X0 + 16, X1 - 16):
    for y in (YF - TONGUE + 30, YB - 18):
        base = cad.cut(base, cyl(4.6, (x, y, FOOT - 1), 2.2))
        feet.append(cad.foot(9, FOOT + 1.2, style="dome", at=(x, y, FOOT + 1.2)))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour=None):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    c = COLOURS[colour or name]
    o.ViewObject.ShapeColor = cad.color(c)
    if c in ("smoked", "frosted", "glass"):
        o.ViewObject.Transparency = cad.transparency(c)
    return o


for nm, sh in (("Back", back), ("Front", front), ("Dispenser", drum), ("Rotor", rotor), ("Base", base),
               ("Bowl", bowl), ("Bezel", tray), ("Lens", lens), ("Feed_Key", cap), ("Status_Lens", pipe),
               ("Bin", bin_), ("Window", window), ("Lid", lid), ("Hinge_Pin", hinge_pin)):
    part(nm, sh)
for i, sh in enumerate(feet):
    part("Rubber_%d" % (i + 1), sh, "Rubber")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
