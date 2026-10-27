"""Example: "a 4WD explorer rover" - a stepped-deck explorer on four motor-driven wheels, mast, beacon and solar panel.

fork this file for a 4WD rover / RC crawler / explorer (a Mars rover, a
four-wheel robot car, an off-road crawler, a patrol bot - four driven
wheels); change PARAMETERS and the outlines.
ARCHETYPE: vehicle

How it is built (R803):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT under the decks, nose at the port-8 end (-Y; port 8 and 12
    stay empty), its height set by the tyre (shaft centre = PCB top +
    10.14 = the measured tyre radius). FOUR dc_motor SEATED: 1 + 9 the rear
    axle, 5 + 13 the front (80 mm wheelbase); each shaft carries the
    library's N20 hub (am.load_module "n20_wheel", its D-bore flat on the
    shaft's flat) and the printed wheel fits over the hub with a hex socket
    0.15 mm clear - the coupler drives it. ONE wheel build (cad.wheel,
    block tread), copied and mirrored. The ToF (from 14) and the headlight
    (from 6) are CABLED to the nose (rc_tank's proven routes), each held by
    two ribs down from the deck: the ToF behind an OPEN slot in a black
    eye, the headlight behind a clear light pipe in a chrome bezel (both
    inserts). The orientation sensor SEATED flat and level on 3; a light
    SEATED on 4 under a light pipe up to an amber beacon dome; a button on
    10 under the GO key in the rear deck; USB-C on 7 in a pocket + liner in
    the rear plate. The hull is three STRAIGHT outlines intersected (side:
    chamfered rear plate, low rear deck over the motors, a step up to the
    instrument deck, a sloped nose over the lamp face, a raked chin; plan:
    cut nose corners; section: the deck's sides leaning in), hollowed by
    the same outlines inset WALL, split low (lip) into the fixed Hull_Lower
    (a cradle holds the board) and the Hull_Upper; four M2 screws from
    below into insert sleeves; a rib onto the spine.
  * STAGE B - details: flared fenders, the headlight guard, the beacon's
    cage, the key ring and legend, the camera mast (pinned in a collar)
    with a smoked visor, the roll bar with an antenna (pinned feet), vents,
    rivets, lettering, reflectors, the solar panel (an insert, cells
    scored), the skid plate with the bull bar, the split rear bar and the
    tow hitch on the chassis.
RESTYLE (R803): WHEEL_R, TYRE_W, HEIGHT, BUMPER and WALL drive every
outline and cutter below: the board height follows the measured tyre (L),
every hull height is taken over L, the fenders follow the tyre, the
bars follow BUMPER. The hardware's x / y frame (the board at x 0..60,
y -120..0) is the board's own: never move it with a knob.
DETAILS (visible, 30): 1 angular hull of straight outlines; 2 sloped nose
over a vertical lamp face; 3 raked chin; 4 instrument deck with leaning
sides; 5 rear deck stepped 20 mm down; 6 chamfered rear plate; 7-10 four
flared fenders; 11 headlight light pipe with a domed lens; 12 its chrome
bezel with a proud ring; 13 a guard hoop over it; 14 black ToF eye with
an open slot; 15 its hood ring; 16 amber beacon dome; 17 a three-hoop
cage over it; 18 yellow GO key; 19 its raised ring; 20 "GO" legend;
21 solar panel with 32 scored cells; 22 camera mast in a collar; 23 its
head with a smoked visor; 24 roll bar on flanged feet; 25 antenna with a
ball; 26 motor-bay vent slots; 27 rivets along the rear deck; 28
"EXPLORER" on the step; 29 "ATECH" and two red reflectors on the rear
plate; 30 USB-C pocket with liner; plus the bull bar on a skid plate,
the split rear bar with a tow hitch, block-tread tyres, five-window rims
with chrome caps.
Inside: board cradle; rib onto the spine; two ribs holding each cabled
module; light pipes; key plunger; insert sleeves; the hull lip; hex
sockets on the N20 hubs.
Materials: orange hull, graphite chassis and bars, navy solar panel,
satin grey mast, black eye and roll bar, chrome bezel, caps and screws,
clear and amber lenses, smoked visor, red reflectors, rubber tyres,
aluminium rims.
MEASURED (R803, 2026-10-27): ./check CHECK PASS, see test_kit_examples_r500
(TIMINGS line).
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
    "Hull_Upper", "Headlight_Bezel", "Headlight", "Sensor_Eye", "Beacon", "Key", "Solar_Panel",
    "Mast", "Mast_Visor", "Roll_Bar", "Reflector_L", "Reflector_R",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4",
    "Tyre_RL", "Tyre_FL", "Tyre_RR", "Tyre_FR", "Rim_RL", "Rim_FL", "Rim_RR", "Rim_FR",
    "Cap_RL", "Cap_FL", "Cap_RR", "Cap_FR"],
    "covers": {"Key": "button_p10"}}
REVIEW_CLOSEUPS = ["Rim_FL", "Beacon", "Mast"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them; test_kit_examples_r280 builds
# this file with each knob at its min and at its max, one at a time.
WHEEL_R = 30.0     # RESTYLE 25.5..34.5 radius: the tyres (the board rides on it: shaft = PCB top + 10.14)
TYRE_W = 20.0      # RESTYLE 17..23 width: each tyre across (x)
HEIGHT = 44.0      # RESTYLE 37.4..50.6 height: the instrument deck over the PCB top
BUMPER = 14.0      # RESTYLE 11.9..16.1 length: how far the bull bar and the rear bar stand out
WALL = 2.0         # RESTYLE 1.7..2.3 wall
# end RESTYLE
# World frame: the board FLAT at x 0..60, y -120..0 (nose at -Y, the
# port-8 end, port 8 left empty); z up, the tyres on z = 0. Heights are
# taken over the PCB top L (it follows the tyre radius).
HW = 52.9                        # hull half width round x = 30 (motor body 20.4 + 0.2 + wall)
YN, YR = -140.0, 12.0            # the nose face, the rear plate (y)
NOSE_UP = min(38.0, HEIGHT - 0.5)  # the vertical lamp face's top (the lamps sit at +24)
SHOULDER = 28.0                  # the side wall's knuckle; the instrument deck's sides lean in 9 mm
REAR_UP = 24.0                   # the rear deck (over the motors' tops, +19.14)
STEP_Y = -44.0                   # the instrument deck's back edge: a 4 mm step falls to the rear deck
HL = 34.0                        # headlight / ToF eye at x = 30 -+ HL (the cabled routes)
LENS_R, BEZEL_R, EYE_R = 9.6, 12.0, 12.0
BEACON_R, KEY_D = 8.0, 12.0
SCREWS = [(-15.0, -60.0), (75.0, -60.0), (-15.0, 4.0), (75.0, 4.0)]
MAST_AT = (-4.0, -108.0)         # the camera mast, front left of the instrument deck
PANEL = (34.0, 70.0, -118.0, -50.0)   # the solar panel x0, x1, y0, y1 on the instrument deck
ROLL_Y, ROLL_X = -36.0, (-12.0, 72.0)  # the roll bar over the rear deck
COLOURS = {"Hull_Lower": "graphite", "Hull_Upper": "orange", "Headlight_Bezel": "chrome",
           "Headlight": "glass", "Sensor_Eye": "matte_black", "Beacon": "#ffb020", "Key": "toy_yellow",
           "Solar_Panel": "#1d2f63", "Mast": "satin_grey", "Mast_Visor": "smoked", "Roll_Bar": "matte_black",
           "Reflector": "led_red", "Screw": "chrome", "Tyre": "rubber", "Rim": "brushed_alu", "Cap": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
# one wheel build, measured: its tread sets the axle height
WHEEL = cad.wheel(2 * WHEEL_R - 2.4, TYRE_W, hub_d=12.0, tread="block", tread_n=30, axis="-X", at=(0, 0, 0))
RT = cad.measure(WHEEL["tyre"])["size"][2] / 2.0
L = RT - 10.14                    # PCB top: the shaft centre 10.14 above it = the tyre radius
FZ = L - 2.7 - WALL               # the floor's underside (its top 0.2 under the board)
DZ = L + HEIGHT                   # the instrument deck
RZ = L + REAR_UP                  # the rear deck
SPLIT_Z = L - 2.2                 # lower / upper hull seam (lip top L - 1.0, under every slide path)
FLAT = Rotation(Vector(1, 0, 0), 90)
board = ap.board_object(doc)
board.Placement = Placement(Vector(0, 0, L), FLAT)     # nose -Y (port 8 end)
motors = {"RL": ap.seat(doc, "dc_motor", 1), "RR": ap.seat(doc, "dc_motor", 9),
          "FL": ap.seat(doc, "dc_motor", 5), "FR": ap.seat(doc, "dc_motor", 13)}
usb = ap.seat(doc, "usbc", 7)                          # rear plate, mouth +Y
imu = ap.seat(doc, "orientation", 3)                   # flat and level, mid-chassis
beacon_led = ap.seat(doc, "light", 4)                  # up, under the beacon
key = ap.seat(doc, "button", 10)                       # up, under the GO key
eye, eye_rib = ap.cable(doc, "distance_sensor", 14, ap.module_placement(
    "distance_sensor", (30 + HL, -132, L + 24), face="-Y", cable="-Z"), via=[(63, -118, L + 10.14)])
head, head_rib = ap.cable(doc, "light", 6, ap.module_placement(
    "light", (30 - HL, -132, L + 24), face="-Y", cable="-Z"), via=[(-3, -118, L + 10.14)])
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


def inset_poly(pts, d):
    """A polygon outline moved d inward (sharp corners kept)."""
    if d <= 0:
        return pts
    w = Part.makePolygon([V(x, 0, y) for x, y in pts + [pts[0]]])
    o = w.makeOffset2D(-d, join=2)
    if o.Length > w.Length:
        o = w.makeOffset2D(d, join=2)
    return [(v.X, v.Z) for v in o.OrderedVertexes]


def prism(pts, axis, a0, a1):
    """A polygon extruded along a world axis: axis 'x' takes (y, z) points,
    'y' (x, z), 'z' (x, y); from a0 to a1."""
    mk = {"x": lambda p, q: V(a0, p, q), "y": lambda p, q: V(p, a0, q), "z": lambda p, q: V(p, q, a0)}[axis]
    d = {"x": V(a1 - a0, 0, 0), "y": V(0, a1 - a0, 0), "z": V(0, 0, a1 - a0)}[axis]
    s = Part.Face(Part.makePolygon([mk(*p) for p in pts + [pts[0]]])).extrude(d)
    if s.Volume < 0:
        s.reverse()
    return s


def insert(shell, cutter):
    """(shell with the opening, the piece that fills it exactly)."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1:
        piece, rest = shell.common(cutter, 0.01), shell.cut(cutter, 0.01)
    if piece.Volume < 1 or not rest.isValid() or len(rest.Solids) != len(shell.Solids):
        raise cad.CadError("insert: the cutter does not cleanly cross the wall")
    return rest, cad.fuse_one(piece)


def soft_y(x0, x1, z0, z1, r, y0, y1):
    w = cad.rounded_rect_wire(x1 - x0, z1 - z0, r, ((x0 + x1) / 2, y0, (z0 + z1) / 2), "Y")
    s = Part.Face(w).extrude(V(0, y1 - y0, 0))
    if s.Volume < 0:
        s.reverse()
    return s


def ring(r_out, r_in, p, d, h):
    return cad.cut(cyl(r_out, p, d, h), cyl(r_in, tuple(a - 0.5 * b for a, b in zip(p, d)), d, h + 1.0))


# ------------------------------------------------------------ the hull
# three straight outlines intersected: the SIDE (y, z: a chamfered rear
# plate, a low rear deck over the motors, a 4 mm step up to the
# instrument deck, a sloped nose over the vertical lamp face, a chin raked
# for the approach angle), the PLAN (x, y: the nose corners cut) and the
# SECTION (x, z: vertical sides to the shoulder, the deck's sides leaning in)
SIDE = [(YR - 3, FZ), (YN + 10, FZ), (YN, L + 10), (YN, L + NOSE_UP), (YN + 14, DZ), (STEP_Y, DZ),
        (STEP_Y + 4, RZ), (YR - 4, RZ), (YR, RZ - 4), (YR, FZ + 3)]
PLAN = [(30 - HW, YR), (30 + HW, YR), (30 + HW, YN + 3), (30 + HW - 3, YN), (30 - HW + 3, YN), (30 - HW, YN + 3)]
SEC = [(30 - HW + 3, FZ), (30 + HW - 3, FZ), (30 + HW, FZ + 3), (30 + HW, L + SHOULDER), (30 + HW - 9, DZ),
       (30 - HW + 9, DZ), (30 - HW, L + SHOULDER), (30 - HW, FZ + 3)]


def hull_solid(t=0.0):
    return prism(inset_poly(SIDE, t), "x", -60, 120).common(prism(inset_poly(PLAN, t), "z", -10, 150)).common(
        prism(inset_poly(SEC, t), "y", -200, 60))


outer = hull_solid()
core = hull_solid(WALL)
skin = hull_solid(0.6)            # ribs and holders are clipped to it: they stop inside the outer skin
hull = cad.cut(outer, core)
lower, upper = cad.split(hull, "Z", at=SPLIT_Z, lip=1.2)
tick("hull + split")

# board cradle in the fixed lower hull: a ledge under the board's edge and
# a rim 0.3 mm round it
PCB0 = L - 2.5
cradle = cad.cut(box(BB.XMin - 2.3, BB.XMax + 2.3, BB.YMin - 2.3, BB.YMax + 2.3, FZ + WALL - 0.5, PCB0 + 1.4),
                 [box(BB.XMin - 0.3, BB.XMax + 0.3, BB.YMin - 0.3, BB.YMax + 0.3, PCB0 - 0.1, DZ),
                  box(BB.XMin + 6, BB.XMax - 6, BB.YMin + 6, BB.YMax - 6, FZ, DZ)])
lower = cad.fuse_one(lower, cradle)
# board retention: a rib from the deck onto the spine (0.2 mm above it)
upper = cad.fuse_one(upper, box(29, 31, -76, -62, L + 4.5 + 0.2, DZ).common(skin))
# four M2 screws up through the floor into bosses in the upper hull, each
# with a heat-set insert pocket in a sleeve
screws = []
for x, y in SCREWS:
    lower, upper = cad.screw_through(lower, upper, (x, y, FZ), size="M2", ribs=0)
    screws.append(cad.screw("csk_phillips", "M2", 10, at=(x, y, FZ), axis="+Z"))
z_boss = FZ + WALL + 0.7
upper = cad.fuse_one(upper, *[cyl(2.8, (x, y, FZ + WALL + 0.1), (0, 0, 1), 10.0) for x, y in SCREWS])
upper = cad.cut(upper, [cyl(1.6, (x, y, FZ + WALL - 0.5), (0, 0, 1), 10.5) for x, y in SCREWS])
tick("cradle + screws")

# ------------------------------------------------------------ motors, hubs, wheels
AX = {}
for k, m in motors.items():
    b = ap.bbox(m)
    left = k[1] == "L"
    AX[k] = (b.XMin if left else b.XMax, (b.YMin + b.YMax) / 2, L + 10.14, left)   # shaft tip x, y, z


def shaft_hole(a, x0, x1, y, z):
    """A soft-square hole for a round shaft (no coaxial round holes)."""
    w = cad.rounded_rect_wire(2 * a, 2 * a, 0.9 * a, (x0, y, z), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


upper = cad.cut(upper, [shaft_hole(2.7, 30 - HW + WALL + 1.5, 30 - HW - 2.0, y, z) if lf else
                        shaft_hole(2.7, 30 + HW - WALL - 1.5, 30 + HW + 2.0, y, z)
                        for _t, y, z, lf in AX.values()])
# the N20 hub (the library's coupler) on every shaft; the printed wheel
# fits over it with a hex socket 0.15 mm clear (the coupler drives it) and
# a 3.4 mm hole past it for the shaft
HUB = [(0, 1.85), (0.73, 0), (4.67, 0), (5.4, 1.85), (4.67, 3.7), (0.73, 3.7)]
hub_w = Part.makePolygon([V(x, y, 0) for x, y in HUB + [HUB[0]]]).makeOffset2D(0.15, join=2)
sock = Part.Face(hub_w).extrude(V(0, 0, 6.75))
sock.translate(V(0, 0, -0.6))
sock = cad.fuse_one(sock, cyl(1.7, (2.70, 2.12, 5.9), (0, 0, 1), 3.0))
rim_in = cad.measure(WHEEL["rim"])["bbox_max"][0]          # the rim's inner face (the tyre's: TYRE_W / 2)
WHEEL["rim"] = cad.fuse_one(WHEEL["rim"], cyl(6.0, (rim_in - 0.5, 0, 0), (1, 0, 0), TYRE_W / 2 - rim_in + 0.5))
hubs, wheels = {}, {}
for k, (tip, y, z, lf) in AX.items():
    if lf:
        # turned so its bore's flat meets the left shaft's flat (the right
        # motors are the left ones turned 180 deg about z)
        pl = Placement(V(tip + 6.0, y + 2.12, z + 2.70), Rotation(V(1, 0, -1), 180))
    else:
        pl = Placement(V(tip - 6.0, y - 2.12, z + 2.70), Rotation(V(0, 1, 0), 90))
    hubs[k], _ = am.load_module(doc, "n20_wheel", label="Hub_" + k, placement=pl)
    # R803: the hub sits inside its wheel's hex socket, pressed on after the
    # motor is seated; a Mesh::Feature cannot be named in fitted_after, so it
    # is hidden (an obstacle to nothing) - toggle it in the tree to see it
    hubs[k].Visibility = False
    inner = tip + 6.0 - 0.2 if lf else tip - 6.0 + 0.2          # the wheel's inner face, 0.2 off the hub's end
    cx = inner - TYRE_W / 2 if lf else inner + TYRE_W / 2
    s_cut = sock.copy()
    s_cut.transformShape(pl.toMatrix())
    for part_k, sh in WHEEL.items():
        s = sh.copy() if lf else cad.mirror(sh, "YZ", (0, 0, 0))
        s.translate(V(cx, y, z))
        if part_k == "rim":
            s = cad.cut(s, s_cut)
        wheels["%s_%s" % (part_k.capitalize(), k)] = s
tick("wheels + hubs")

# ------------------------------------------------------------ the nose: headlight, ToF eye
# the headlight: a chrome bezel that fills its opening in the nose (an
# insert), a clear lens in it carrying a light pipe to 0.4 mm off the LEDs
hx, _hy, hz = centre(head)
hb = ap.bbox(head)
upper, bezel = insert(upper, cyl(BEZEL_R, (hx, YN + WALL + 1.0, hz), (0, -1, 0), WALL + 2.0))
bezel, lens = insert(bezel, cyl(LENS_R, (hx, YN + WALL + 1.0, hz), (0, -1, 0), WALL + 2.0))
lens = cad.fuse_one(lens, cyl(LENS_R, (hx, hb.YMin - 0.4, hz), (0, -1, 0), (hb.YMin - 0.4) - (YN + WALL - 0.3)),
                    Part.makeSphere(LENS_R * 2.5, V(hx, YN - 1.5 + LENS_R * 2.5, hz)).common(
                        cyl(LENS_R, (hx, YN + 0.5, hz), (0, -1, 0), 2.0)))
# the ToF: a black eye (an insert) with an OPEN slot - no glass over it
ex, _ey, ez = centre(eye)
upper, eye_ins = insert(upper, cyl(EYE_R, (ex, YN + WALL + 1.0, ez), (0, -1, 0), WALL + 2.0))
eye_ins = cad.cut(eye_ins, cad.rounded_box(13.0, WALL + 4, 9.0, 3.0, at=(ex - 6.5, YN - 1.5, ez - 4.5), edges="y"))
# holders: ribs either side of each cabled module, down from the deck, 0.3 mm off
holders = []
for m in (eye, head):
    b = ap.bbox(m)
    for x0, x1 in ((b.XMin - 1.6, b.XMin - 0.3), (b.XMax + 0.3, b.XMax + 1.6)):
        holders.append(box(x0, x1, b.YMin + 1.0, b.YMax - 1.0, b.ZMin + 3.0, DZ + 5).common(skin))
upper = cad.fuse_one(upper, *holders)
tick("nose")

# ------------------------------------------------------------ the decks: beacon, GO key
# the beacon: a light pipe from 0.4 mm over the LEDs up through the
# instrument deck (an insert there) into an amber dome standing on it
bx, by, _bz = centre(beacon_led)
lb = ap.bbox(beacon_led)
upper, beacon = insert(upper, cyl(BEACON_R, (bx, by, DZ - WALL - 1.0), (0, 0, 1), WALL + 2.0))
beacon = cad.fuse_one(beacon, cyl(BEACON_R, (bx, by, lb.ZMax + 0.4), (0, 0, 1), DZ - WALL + 0.3 - lb.ZMax - 0.4),
                      Part.makeSphere(BEACON_R + 2.0, V(bx, by, DZ - 2.5)).common(
                          cyl(BEACON_R + 3, (bx, by, DZ), (0, 0, 1), BEACON_R + 2)))
# the GO key: a cap through the rear deck, flange 0.1 mm under it, a
# plunger to 0.16 mm off the button's own cap
kx, ky, _kz = centre(key)
kb = ap.bbox(key)
z_base = RZ - WALL - 0.9
cap = cad.button_cap(KEY_D, RZ + 1.6 - z_base, dome=0.8, flange=1.5, at=(kx, ky, z_base), axis="+Z")
upper = cad.opening_for(upper, cap, clearance=0.25, chamfer=0.4, axis="+Z")
cap = cad.fuse_one(cap, cyl(3.0, (kx, ky, kb.ZMax + 0.16), (0, 0, 1), z_base - kb.ZMax - 0.16 + 0.5))
tick("decks")

# ------------------------------------------------------------ USB-C in the rear plate
ub = ap.bbox(usb)
ux, uz = (ub.XMin + ub.XMax) / 2, L + 5.9
pocket = soft_y(ux - 9, ux + 9, uz - 5, uz + 5, 2.5, ub.YMax + 1.3, YR + 8)
liner = cad.cut(soft_y(ux - 11, ux + 11, max(uz - 7, SPLIT_Z + 1.5), uz + 7, 3.5, ub.YMax + 0.25, YR - 0.5), pocket)
upper = cad.fuse_one(cad.cut(upper, pocket), liner)
upper = cad.socket_opening(upper, usb, margin=1.5)
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# flared fenders: a 2.5 mm arch over the top of each tyre (3 mm clear),
# standing off the hull side, its ends 4 mm over the axle line
fenders = []
for k, (tip, y, z, lf) in AX.items():
    x0 = 30 - HW + 0.6 if lf else 30 + HW - 0.6
    w = TYRE_W + 3.0 + (abs(x0 - tip) - 6.0)
    f = ring(RT + 5.5, RT + 3.0, (x0, y, z), (-1 if lf else 1, 0, 0), w)
    fenders.append(f.common(box(x0 - 60, x0 + 60, y - 60, y + 60, z + 4.0, z + 60)))
upper = cad.fuse_one(upper, *[cad.soften(f, 1.0) for f in fenders])
# a guard hoop over the headlight, a chrome ring proud round its lens, a
# black hood round the ToF eye
upper = cad.fuse_one(upper, cad.pipe([(hx - 13.0, YN + 0.5, hz - 8.0), (hx - 13.0, YN - 8, hz + 1.0),
                                      (hx, YN - 9.5, hz + 12.0), (hx + 13.0, YN - 8, hz + 1.0),
                                      (hx + 13.0, YN + 0.5, hz - 8.0)], r=1.0))
bezel = cad.fuse_one(bezel, ring(BEZEL_R - 0.5, LENS_R + 0.4, (hx, YN + 0.5, hz), (0, -1, 0), 2.0))
eye_ins = cad.fuse_one(eye_ins, ring(EYE_R - 0.5, 9.0, (ex, YN + 0.5, ez), (0, -1, 0), 2.5))
# a cage over the beacon: six bent legs from the deck into a ball over its
# dome (each leg ends at its own point inside the ball)
cage = Part.makeSphere(2.2, V(bx, by, DZ + 12.0))
for a in range(0, 360, 60):
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    cage = cad.fuse_one(cage, cad.pipe([(bx + 12.5 * c, by + 12.5 * s, DZ - 0.5),
                                        (bx + 11 * c, by + 11 * s, DZ + 7.0),
                                        (bx + 1.0 * c, by + 1.0 * s, DZ + 11.6)], r=0.8))
upper = cad.fuse_one(upper, cage)
# the GO key: a raised ring round it and its legend
upper = cad.fuse_one(upper, ring(KEY_D / 2 + 3.0, KEY_D / 2 + 1.6, (kx, ky, RZ - 0.5), (0, 0, 1), 1.6))
upper = cad.text(upper, "GO", (kx, ky + KEY_D / 2 + 6.0, RZ), (0, 0, 1), 4.5, depth=0.4, mode="deboss",
                 up=(0, -1, 0))
# the camera mast's collar on the instrument deck (the mast pins into it)
mx, my = MAST_AT
upper = cad.fuse_one(upper, cad.soften(cyl(6.0, (mx, my, DZ - 0.5), (0, 0, 1), 4.5), 0.8))
upper = cad.cut(upper, cyl(3.15, (mx, my, DZ + 4.5), (0, 0, -1), 4.5 + WALL - 1.0))
# roll bar feet: a boss under the rear deck at each, a blind hole 3 mm into it
upper = cad.fuse_one(upper, *[cyl(3.5, (x, ROLL_Y, RZ - WALL - 3.0), (0, 0, 1), 3.5) for x in ROLL_X])
upper = cad.cut(upper, [cyl(1.65, (x, ROLL_Y, RZ + 1.0), (0, 0, -1), 4.0) for x in ROLL_X])
# motor-bay vents in the rear deck, rivets along its edges, lettering
upper = cad.grille(upper, (13.0, -12.0, RZ), (0, 0, 1), (34.0, 14.0), kind="slot", hole=2.4, pitch=5.0)
upper = cad.fuse_one(upper, *[Part.makeSphere(1.0, V(x, y, RZ - 0.4)) for x in (30 - HW + 3.4, 30 + HW - 3.4)
                              for y in (-30.0, -20.0, -10.0, 0.0)])
upper = cad.text(upper, "ATECH", (30, YR, L + 16.5), (0, 1, 0), 5, depth=0.5, mode="deboss")
sn = V(0, DZ - RZ, 4).normalize()
upper = cad.text(upper, "EXPLORER", (30, STEP_Y + 2, (DZ + RZ) / 2), (0, sn.y, sn.z), 6, depth=0.5,
                 mode="deboss", up=(0, -sn.z, sn.y))
# red reflectors: inserts in the rear plate
upper, refl_l = insert(upper, box(-17, -7, YR - WALL - 1, YR + 1, L + 12, L + 17))
upper, refl_r = insert(upper, box(67, 77, YR - WALL - 1, YR + 1, L + 12, L + 17))
# the solar panel: an insert in the instrument deck, its cells scored
px0, px1, py0, py1 = PANEL
upper, panel = insert(upper, box(px0, px1, py0, py1, DZ - WALL - 1, DZ + 1))
nx, ny = 4, 8
panel = cad.cut(panel, [box(px0 + (px1 - px0) * i / nx - 0.3, px0 + (px1 - px0) * i / nx + 0.3, py0 + 1.5, py1 - 1.5,
                            DZ - 0.5, DZ + 1) for i in range(1, nx)]
                + [box(px0 + 1.5, px1 - 1.5, py0 + (py1 - py0) * j / ny - 0.3, py0 + (py1 - py0) * j / ny + 0.3,
                       DZ - 0.5, DZ + 1) for j in range(1, ny)])
tick("upper details")
# the camera mast: a post pinned into the collar (0.15 mm clear), a head
# with a smoked visor (an insert) looking forward
post = cyl(3.0, (mx, my, DZ - WALL + 1.15), (0, 0, 1), WALL + 29.6)
mhead = cad.rounded_box(20.0, 12.0, 11.0, 2.5, at=(mx - 10, my - 6, DZ + 29.0), edges="vertical")
mast = cad.fuse_one(post, mhead)
mast, visor = insert(mast, box(mx - 7.5, mx + 7.5, my - 7, my - 4.5, DZ + 31.5, DZ + 37.5))
# the roll bar: a hoop over the rear deck on two flanged feet pinned into
# it, an antenna up its right side
roll = cad.pipe([(ROLL_X[0], ROLL_Y, RZ + 3.0), (ROLL_X[0], ROLL_Y, DZ + 4.0), (ROLL_X[0] + 3.0, ROLL_Y, DZ + 10.0),
                 (30, ROLL_Y, DZ + 13.0), (ROLL_X[1] - 3.0, ROLL_Y, DZ + 10.0), (ROLL_X[1], ROLL_Y, DZ + 4.0),
                 (ROLL_X[1], ROLL_Y, RZ + 3.0)], r=2.0)
feet = []
for x in ROLL_X:
    feet += [cyl(4.0, (x, ROLL_Y, RZ), (0, 0, 1), 1.2), cyl(1.5, (x, ROLL_Y, RZ - 2.85), (0, 0, 1), 3.35)]
ant_x = ROLL_X[1] - 1.0
roll = cad.fuse_one(roll, *feet, cyl(0.8, (ant_x, ROLL_Y, DZ + 4.0), (0, 0, 1), 36.0),
                    Part.makeSphere(1.8, V(ant_x, ROLL_Y, DZ + 40.5)))
tick("mast + roll bar")
# the chassis: a skid plate under the nose carrying the bull bar, a rear
# plate carrying a split rear bar (the USB-C plug passes between) and a
# tow hitch
BZ = L + 5.0
skid = box(-14, 74, -96, YN - BUMPER + 1, FZ - 1.6, FZ + 0.5)
bull = [cyl(3.5, (-16, YN - BUMPER + 3, BZ), (1, 0, 0), 92.0),
        Part.makeSphere(3.5, V(-16, YN - BUMPER + 3, BZ)), Part.makeSphere(3.5, V(76, YN - BUMPER + 3, BZ))]
bull += [box(x - 2, x + 2, YN - BUMPER + 1, YN - BUMPER + 5, FZ - 1.0, BZ) for x in (4.0, 56.0)]
rear = box(-10, 70, -6, YR + BUMPER - 1, FZ - 1.6, FZ + 0.5)
RBZ = FZ + 3.5
rbar = []
for xa, xb in ((-16.0, 14.0), (46.0, 76.0)):
    rbar += [cyl(3.0, (xa, YR + BUMPER - 3, RBZ), (1, 0, 0), xb - xa),
             Part.makeSphere(3.0, V(xa, YR + BUMPER - 3, RBZ)), Part.makeSphere(3.0, V(xb, YR + BUMPER - 3, RBZ)),
             box((xa + xb) / 2 - 2, (xa + xb) / 2 + 2, YR + BUMPER - 5, YR + BUMPER - 1, FZ - 1.0, RBZ)]
hitch = cad.cut(box(26, 34, YR + 1.0, YR + BUMPER + 4, FZ - 1.6, FZ + 1.0),
                cyl(1.6, (30, YR + BUMPER + 1.0, FZ - 3), (0, 0, 1), 6))
lower = cad.fuse_one(lower, cad.soften(skid, 1.0), *bull, cad.soften(rear, 1.0), *rbar, hitch)
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour=None):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour or name])
    return o


for nm, sh in (("Hull_Lower", lower), ("Hull_Upper", upper), ("Headlight_Bezel", bezel),
               ("Sensor_Eye", eye_ins), ("Key", cap), ("Solar_Panel", panel), ("Mast", mast),
               ("Roll_Bar", roll)):
    part(nm, sh)
o = part("Headlight", lens)
o.ViewObject.Transparency = cad.transparency("glass")
o = part("Beacon", beacon)
o.ViewObject.Transparency = cad.transparency("glass")
o = part("Mast_Visor", visor)
o.ViewObject.Transparency = cad.transparency("smoked")
part("Reflector_L", refl_l, "Reflector")
part("Reflector_R", refl_r, "Reflector")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
for nm, sh in wheels.items():
    part(nm, sh, nm.split("_")[0])
print("TOTAL %.1f s" % (time.time() - T0))
