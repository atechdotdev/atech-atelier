"""Example: "an RC tank" - a tracked toy tank around real Atech hardware.

fork this file for an RC tank / tracked vehicle (a tank, a bulldozer, a
snow cat, a tracked rover - two tracks); change PARAMETERS and the outlines.
ARCHETYPE: vehicle

How it is built (R413):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT under the deck, nose at the port-8 end (-Y), its height set
    by the sprocket (shaft centre = PCB top + 10.14); dc_motor on ports 1
    and 9 drive the REAR sprockets directly through soft-square holes in
    the hull sides; the ToF and both headlights CABLED to the glacis (the
    toy car's proven routes), each held by ribs; USB-C on port 7 in a
    pocket in the rear plate. The hull is two STRAIGHT outlines
    (cad.profile_body, spline=False, fillet) hollowed with its own core and
    split low (lip) into the fixed Hull_Lower (a cradle holds the board)
    and the Hull_Upper; four M2 screws from below into insert bosses. Each
    side runs a track: a TPU belt loop round the sprocket and a front
    idler, its inside toothed at the sprocket's pitch so the sprocket
    really drives it (R740: ./check fails a gear against a smooth belt;
    the loop holds a whole number of teeth, the idler grooved for them),
    the tread pads (a rubber skin with lugs) as their own part, four road
    wheels on a bogie pinned to the hull. A turret on a pinned ring, a
    barrel with a muzzle brake.
  * STAGE B - details: the hatch, antenna, vision block, engine-deck
    louvres, exhaust, tow hooks, headlight guards, rivets, lettering.
DETAILS (visible, 28 of 33): 1 hull of straight outlines, 3 mm edges;
2 sloped glacis; 3 chamfered rear deck; 4 turret with a sloped front and
cheeks; 5 brushed turret ring (pinned to hull and turret); 6 barrel;
7 muzzle brake with two slots; 8 mantlet block; 9 commander's hatch;
10 its hinge; 11 antenna with a ball; 12 ToF aperture in the glacis;
13-14 headlight lenses; 15-16 headlight guards; 17 engine-deck louvres;
18 exhaust pipe; 19-20 tow hooks; 21 USB-C pocket in the rear plate;
22-23 geared drive sprockets; 24-25 front idlers; 26 road wheels on
bogies; 27 toothed track belts; 28 tread pads with lugs (their own parts);
29 driver's vision block; 30 rivets along the deck edges; "ATECH" on the
turret. Inside: 31 board cradle; 32 rib from the deck onto the spine;
33 ribs holding the ToF and the headlights; four screws from below into
insert bosses; a lip keying the hull halves.
Materials: green hull and turret, graphite lower hull, sprockets and
belts, rubber treads, satin grey road wheels, brushed ring, clear lenses,
chrome screws and guards.
MEASURED (R413, 2026-10-20): see test_kit_examples_r270 (TIMINGS line).
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
    "Hull_Upper", "Turret_Ring", "Turret", "Headlight_L", "Headlight_R", "Sprocket_L", "Sprocket_R",
    "Idler_L", "Idler_R", "Road_Wheels_L", "Road_Wheels_R", "Track_L", "Track_R", "Treads_L", "Treads_R",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4"]}
REVIEW_CLOSEUPS = ["Turret", "Treads_L", "Sprocket_L"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# R413: the hull's body frame has x = length (nose at +x), z = height;
# W() turns it into the world (nose at -Y, centred on the board's x = 30).
SHAFT_Z = 19.3                    # sprocket axis height (sets the board height)
WALL, R_OUT = 2.0, 3.0
DECK = 52.0                       # deck height (the cabled ToF stands under it)
SIDE = [(-12, 4.5), (144, 4.5), (150, 16), (139, DECK), (-6, DECK), (-12, DECK - 6)]   # hull side (x, z)
HALF_W = 52.7                     # hull half width (motor body + 0.3 + wall)
SPLIT_Z = 7.0                     # lower / upper hull seam (lip top 8.2, under the slide paths)
TRACK_X = (-23.2, -39.2)          # left track's inner, outer x (the right mirrors at x = 30)
IDLER_Y = -140.0                  # front idler axis (y), trimmed below to a whole number of teeth
R_IN, BELT, SKIN, LUG = 15.3, 2.0, 1.0, 1.0   # belt inner radius, belt, tread skin, lug heights
GEAR_M, GEAR_Z = 1.5, 18          # sprocket: module, teeth (tips at r 15.0, 0.3 under the belt)
TEETH_W = 6.0                     # belt teeth across the track, over the 5.6 mm sprocket
WHEELS_Y = (-32.0, -60.0, -88.0, -116.0)      # road wheels
WHEEL_R = 7.0
TURRET_C = (30.0, -59.0)          # turret ring centre
BARREL_TIP = -206.0
HL = 34.0                         # headlights at x = 30 -+ HL
SCREWS = [(-14.0, -60.0), (74.0, -60.0), (-14.0, 5.0), (74.0, 5.0)]
COLOURS = {"Hull_Lower": "graphite", "Hull_Upper": "toy_green", "Turret": "toy_green",
           "Turret_Ring": "brushed_alu", "Lens": "glass", "Sprocket": "graphite", "Idler": "graphite",
           "Road_Wheels": "satin_grey", "Track": "graphite", "Treads": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
FLAT = Rotation(Vector(1, 0, 0), 90)
board = ap.board_object(doc)
L = SHAFT_Z - 10.14               # PCB top: the shaft 10.14 above it
board.Placement = Placement(Vector(0, 0, L), FLAT)     # nose -Y (port 8 end)
mot_l = ap.seat(doc, "dc_motor", 1)
mot_r = ap.seat(doc, "dc_motor", 9)
usb = ap.seat(doc, "usbc", 7)                          # rear, mouth +Y
eye, eye_rib = ap.cable(doc, "distance_sensor", 8, ap.module_placement(
    "distance_sensor", (30, -131.4, L + 30), face="-Y", cable="-Z"))
head_l, hl_rib = ap.cable(doc, "light", 6, ap.module_placement(
    "light", (30 - HL, -132, L + 24), face="-Y", cable="-Z"), via=[(-3, -118, L + 10.14)])
head_r, hr_rib = ap.cable(doc, "light", 14, ap.module_placement(
    "light", (30 + HL, -132, L + 24), face="-Y", cable="-Z"), via=[(63, -118, L + 10.14)])
mb = ap.bbox(mot_l)
SHAFT_Y = (mb.YMin + mb.YMax) / 2                      # rear axle, measured
# R740: the belt's teeth go round the loop at the sprocket's pitch; the
# loop at the pitch line (2 runs + one turn of the pitch circle) must hold
# a whole number of them, so the idler moves to the nearest such spot
PITCH = math.pi * GEAR_M
R_P = GEAR_M * GEAR_Z / 2.0
IDLER_Y = SHAFT_Y - round(2 * (SHAFT_Y - IDLER_Y) / PITCH) * PITCH / 2.0
LZ = ap.bbox(head_l).ZMin + ap.bbox(head_l).ZLength / 2
tick("hardware")


def W(s):
    """Body frame (x = length, nose at +x) -> world (nose at -Y, centred on x = 30)."""
    s = s.copy()
    s.rotate(V(0, 0, 0), V(0, 0, 1), -90)
    s.translate(V(30, 0, 0))
    return s


def inset_poly(pts, d):
    """A polygon outline moved d inward (sharp corners kept)."""
    w = Part.makePolygon([V(x, 0, y) for x, y in pts + [pts[0]]])
    o = w.makeOffset2D(-d, join=2)
    if o.Length > w.Length:
        o = w.makeOffset2D(d, join=2)
    return [(v.X, v.Z) for v in o.OrderedVertexes]


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, d, h):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def xcyl(r, x0, x1, y, z):
    return Part.makeCylinder(r, abs(x1 - x0), V(min(x0, x1), y, z), V(1, 0, 0))


def stadium(r, x0, x1):
    """The track loop's solid outline at radius r round both axles, x0..x1."""
    return cad.fuse_one(xcyl(r, x0, x1, SHAFT_Y, SHAFT_Z), xcyl(r, x0, x1, IDLER_Y, SHAFT_Z),
                        box(min(x0, x1), max(x0, x1), IDLER_Y, SHAFT_Y, SHAFT_Z - r, SHAFT_Z + r))


def mirror_x(s):
    return cad.mirror(s, "YZ", (30, 0, 0))


# ------------------------------------------------------------ hull
PLAN = [(-12, -HALF_W), (150, -HALF_W), (150, HALF_W), (-12, HALF_W)]
hull = cad.profile_body(SIDE, PLAN, spline=False, fillet=R_OUT)
core = cad.profile_body(inset_poly(SIDE, WALL), [(-10, -HALF_W + WALL), (148, -HALF_W + WALL),
                                                 (148, HALF_W - WALL), (-10, HALF_W - WALL)],
                        spline=False, fillet=None)
hull = W(cad.cut(hull, core))
lower, upper = cad.split(hull, "Z", at=SPLIT_Z, lip=1.2)
tick("hull + split")
# board cradle in the fixed lower hull: a ledge under the board's edge and
# a rim 0.3 mm round it, notched where the nose ribbons pass
bb = ap.bbox(board)
PCB0 = L - 2.5
cradle = cad.cut(box(bb.XMin - 2.3, bb.XMax + 2.3, bb.YMin - 2.3, bb.YMax + 2.3, 6.0, PCB0 + 1.4),
                 [box(bb.XMin - 0.3, bb.XMax + 0.3, bb.YMin - 0.3, bb.YMax + 0.3, PCB0 - 0.1, 20),
                  box(bb.XMin + 6, bb.XMax - 6, bb.YMin + 6, bb.YMax - 6, 5, 20),
                  box(-8, 68, bb.YMin - 5, bb.YMin + 2, PCB0 - 0.1, 20)])
lower = cad.fuse_one(lower, cradle)
# board retention: a rib from the deck onto the spine (0.2 mm above it)
upper = cad.fuse_one(upper, box(29, 31, -58, -44, L + 4.5 + 0.2, DECK - 1.0))
# four M2 screws up through the floor into bosses in the upper hull, each
# with a heat-set insert pocket in a sleeve (all sleeves in ONE fuse)
screws = []
for x, y in SCREWS:
    lower, upper = cad.screw_through(lower, upper, (x, y, 4.5), size="M2")
    screws.append(cad.screw("csk_phillips", "M2", 10, at=(x, y, 4.5), axis="+Z"))
z_boss = 4.5 + WALL + 0.1 + 0.6
upper = cad.fuse_one(upper, *[cyl(2.8, (x, y, z_boss), (0, 0, 1), 9.4) for x, y in SCREWS])
upper = cad.cut(upper, [cyl(1.6, (x, y, z_boss), (0, 0, 1), 9.5) for x, y in SCREWS])
tick("hull fasteners")

# ------------------------------------------------------------ motors, sprockets, idlers


def shaft_hole(a, x0, x1, y, z):
    """A soft-square hole for a round shaft (no coaxial round holes)."""
    w = cad.rounded_rect_wire(2 * a, 2 * a, 0.9 * a, (x0, y, z), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


upper = cad.cut(upper, [shaft_hole(2.7, -19.0, -25.0, SHAFT_Y, SHAFT_Z),
                        shaft_hole(2.7, 79.0, 85.0, SHAFT_Y, SHAFT_Z)])
# idler stub axles and road-wheel bogie pin holes in the hull sides
ti, to = TRACK_X
upper = cad.fuse_one(upper, xcyl(2.0, -21.0, to + 1.0, IDLER_Y, SHAFT_Z),
                     mirror_x(xcyl(2.0, -21.0, to + 1.0, IDLER_Y, SHAFT_Z)))
PIN_Y = (WHEELS_Y[0] + WHEELS_Y[1]) / 2, (WHEELS_Y[2] + WHEELS_Y[3]) / 2
WZ = SHAFT_Z - R_IN + WHEEL_R + 0.3                  # road wheels 0.3 mm over the belt
PIN_YR = tuple(y + 5.0 for y in PIN_Y)              # the right side's pins: not coaxial with the left
upper = cad.cut(upper, [xcyl(1.65, -19.0, -25.0, y, WZ) for y in PIN_Y]
                + [mirror_x(xcyl(1.65, -19.0, -25.0, y, WZ)) for y in PIN_YR])
# a geared sprocket on each shaft (bore 3.3), a tooth SPACE straight down
# where the belt's first tooth sits; an idler on each stub, grooved where
# the belt's teeth pass, its rim riding 0.3 mm under the belt
gear = cad.spur_gear(GEAR_M, GEAR_Z, 5.6, bore=3.3)
gear.rotate(V(0, 0, 0), V(0, 1, 0), -90)             # axis -X
gear.translate(V(-23.2, SHAFT_Y, SHAFT_Z))           # x -23.2 .. -28.8
gear = cad.mesh_phase(gear, (-23.2, SHAFT_Y, SHAFT_Z), "-X", (0, 0, -1))
T_IN = R_P - GEAR_M                                  # belt tooth tips (sprocket root + 0.375)
idler = cad.cut(cad.fuse_one(xcyl(T_IN - 0.4, ti - 0.3, ti - TEETH_W - 0.4, IDLER_Y, SHAFT_Z),
                             xcyl(R_IN - 0.3, ti - TEETH_W - 0.4, to + 1.2, IDLER_Y, SHAFT_Z)),
                xcyl(2.15, ti + 1, to, IDLER_Y, SHAFT_Z))
# road wheels on a bogie beam, its two arms pinned into the hull side
def bogie_for(pin_ys):
    rw = [xcyl(WHEEL_R, ti - TEETH_W - 0.6, to + 0.6, y, WZ) for y in WHEELS_Y]   # beside the teeth
    beam = box(to + 3.0, ti - 3.0, WHEELS_Y[-1], WHEELS_Y[0], WZ - 1.6, WZ + 1.6)
    arms = [box(-30.0, -22.9, y - 3, y + 3, WZ - 2.5, WZ + 2.5) for y in pin_ys]
    pins = [xcyl(1.5, -23.2, -20.6, y, WZ) for y in pin_ys]
    b = cad.fuse_one(*rw, beam, *arms, *pins)
    return cad.cut(b, [xcyl(4.2, to - 1.0, to + 1.6, y, WZ) for y in WHEELS_Y])   # 1 mm hub recesses


bogie = bogie_for(PIN_Y)
# the track: a TPU belt loop round sprocket and idler with teeth on its
# inside that sit in the sprocket's tooth spaces (rack teeth: 20 deg
# flanks, 0.15 mm backlash a flank), the tread pads (a rubber skin with
# lugs) as their own part


def belt_teeth():
    """One tooth a pitch round the loop's pitch line, the first under the
    sprocket: a trapezoid from inside the belt (h -2.1) to its tip (h = m)."""
    run = SHAFT_Y - IDLER_Y
    loop = 2 * run + 2 * math.pi * R_P
    n = int(round(loop / PITCH))
    tan_a, bl = math.tan(math.radians(20)), 0.15
    teeth = []
    for k in range(n):
        s = k * loop / n
        if s < run:                                  # bottom run, toward the idler
            p, t, nn = (SHAFT_Y - s, SHAFT_Z - R_P), (-1, 0), (0, 1)
        elif s < run + math.pi * R_P:                # round the idler
            a = -math.pi / 2 - (s - run) / R_P
            p, t, nn = (IDLER_Y + R_P * math.cos(a), SHAFT_Z + R_P * math.sin(a)), \
                (math.sin(a), -math.cos(a)), (-math.cos(a), -math.sin(a))
        elif s < 2 * run + math.pi * R_P:            # top run, back
            p, t, nn = (IDLER_Y + s - run - math.pi * R_P, SHAFT_Z + R_P), (1, 0), (0, -1)
        else:                                        # round the sprocket
            a = math.pi / 2 - (s - 2 * run - math.pi * R_P) / R_P
            p, t, nn = (SHAFT_Y + R_P * math.cos(a), SHAFT_Z + R_P * math.sin(a)), \
                (math.sin(a), -math.cos(a)), (-math.cos(a), -math.sin(a))
        pts = []
        for h, sg in ((-2.1, 1), (GEAR_M, 1), (GEAR_M, -1), (-2.1, -1)):
            hw = sg * (PITCH / 4 - h * tan_a - bl)
            pts.append(V(ti, p[0] + t[0] * hw + nn[0] * h, p[1] + t[1] * hw + nn[1] * h))
        f = Part.Face(Part.makePolygon(pts + [pts[0]]))
        teeth.append(f.extrude(V(-TEETH_W, 0, 0)))
    return teeth


belt = cad.fuse_one(cad.cut(stadium(R_IN + BELT, ti, to), stadium(R_IN, ti + 1, to - 1)), *belt_teeth())
r_s = R_IN + BELT
treads = [cad.cut(stadium(r_s + SKIN, ti, to), stadium(r_s, ti + 1, to - 1))]
n = int((SHAFT_Y - IDLER_Y) / 9.0)
for i in range(n + 1):
    y = IDLER_Y + i * (SHAFT_Y - IDLER_Y) / n
    treads.append(box(to, ti, y - 2.0, y + 2.0, SHAFT_Z - r_s - SKIN - LUG, SHAFT_Z - r_s - SKIN + 0.3))
    treads.append(box(to, ti, y - 2.0, y + 2.0, SHAFT_Z + r_s + SKIN - 0.3, SHAFT_Z + r_s + SKIN + LUG))
tread = cad.fuse_one(*treads)
running = {"Sprocket_L": gear, "Idler_L": idler, "Road_Wheels_L": bogie, "Track_L": belt, "Treads_L": tread}
for k in list(running):
    running[k[:-1] + "R"] = mirror_x(bogie_for(PIN_YR) if k == "Road_Wheels_L" else running[k])
tick("running gear")

# ------------------------------------------------------------ the glacis: ToF, headlights, USB-C
# the ToF looks out through an OPEN aperture (no glass) in the glacis
eb = ap.bbox(eye)
ec = ((eb.XMin + eb.XMax) / 2, (eb.ZMin + eb.ZMax) / 2)
upper = cad.cut(upper, cad.rounded_box(13.0, 30, 9.0, 2.0, at=(ec[0] - 6.5, eb.YMin - 28, ec[1] - 4.5), edges="y"))
# headlights: clear light pipes from 0.4 mm off the LEDs out through the
# sloped glacis (their tops stand proud: lamp housings), a flange inside
lenses = []
for m in (head_l, head_r):
    b = ap.bbox(m)
    cx = (b.XMin + b.XMax) / 2
    y0 = b.YMin - 0.4
    pipe_ = cad.lens(17.6, 16.0, dome=1.2, at=(cx, y0, LZ), axis="-Y")
    upper = cad.opening_for(upper, pipe_, clearance=0.2, chamfer=0.0, axis="-Y")
    lenses.append(pipe_)
# the cabled modules' holders: ribs either side of each, down from the
# deck, 0.3 mm off
holders = []
for m in (eye, head_l, head_r):
    b = ap.bbox(m)
    for x0, x1 in ((b.XMin - 1.6, b.XMin - 0.3), (b.XMax + 0.3, b.XMax + 1.6)):
        holders.append(box(x0, x1, b.YMin + 1.0, b.YMax - 1.0, b.ZMin + 3.0, DECK - 1.0))
upper = cad.fuse_one(upper, *holders)
# USB-C in the rear plate: a pocket brings the wall to 0.25 mm off the mouth


def soft_y(x0, x1, z0, z1, r, y0, y1):
    w = cad.rounded_rect_wire(x1 - x0, z1 - z0, r, ((x0 + x1) / 2, y0, (z0 + z1) / 2), "Y")
    s = Part.Face(w).extrude(V(0, y1 - y0, 0))
    if s.Volume < 0:
        s.reverse()
    return s


ub = ap.bbox(usb)
ux, uz = (ub.XMin + ub.XMax) / 2, L + 5.9
pocket = soft_y(ux - 9, ux + 9, uz - 5, uz + 5, 2.5, ub.YMax + 1.3, 20)
liner = cad.cut(soft_y(ux - 11, ux + 11, max(uz - 7, SPLIT_Z + 1.5), uz + 7, 3.5, ub.YMax + 0.25, 11.0), pocket)
upper = cad.fuse_one(cad.cut(upper, pocket), liner)
upper = cad.socket_opening(upper, usb, margin=1.5)
tick("glacis + usb")

# ------------------------------------------------------------ turret
tx, ty = TURRET_C
ring = cad.cut(cyl(31.0, (tx, ty, DECK), (0, 0, 1), 3.0), cyl(25.0, (tx, ty, DECK - 1), (0, 0, 1), 5))
T_PLAN = [(tx - 34, ty + 28), (tx + 34, ty + 28), (tx + 38, ty - 4), (tx + 26, ty - 32), (tx - 26, ty - 32),
          (tx - 38, ty - 4)]
T_SIDE = [(tx - 38, DECK + 3), (tx + 38, DECK + 3), (tx + 32, DECK + 23), (tx - 32, DECK + 23)]
turret = cad.profile_body(T_SIDE, T_PLAN, spline=False, fillet=2.0)
TZ = DECK + 13.0                                     # barrel axis height
mantlet = cad.soften(box(tx - 9, tx + 9, ty - 39, ty - 28, TZ - 7, TZ + 7), 1.5)
barrel = cyl(3.5, (tx, ty - 36, TZ), (0, -1, 0), (ty - 36) - (BARREL_TIP + 10))
brake = cad.cut(cyl(5.5, (tx, BARREL_TIP + 11, TZ), (0, -1, 0), 11.0),
                [box(tx - 7, tx + 7, BARREL_TIP + y0, BARREL_TIP + y0 + 2.2, TZ - 2.2, TZ + 2.2) for y0 in (3, 7)])
turret = cad.fuse_one(turret, mantlet, barrel, brake)
# pins: the ring pinned down into the deck and up into the turret
for a in (0, 120, 240):
    px, py = tx + 28 * math.cos(math.radians(a)), ty + 28 * math.sin(math.radians(a))
    ring = cad.fuse_one(ring, cyl(1.2, (px, py, DECK - 1.8), (0, 0, 1), 6.6))
    upper = cad.cut(upper, cyl(1.35, (px, py, DECK - 3), (0, 0, 1), 4))
    turret = cad.cut(turret, cyl(1.35, (px, py, DECK + 2), (0, 0, 1), 4))
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# the commander's hatch with its hinge, an antenna, lettering
TT = DECK + 23
turret = cad.fuse_one(turret, cad.soften(cyl(9.0, (tx + 10, ty + 8, TT - 0.5), (0, 0, 1), 2.3), 0.6),
                      xcyl(1.6, tx + 3, tx + 17, ty + 17.5, TT + 0.8),
                      cad.pipe([(tx - 22, ty + 18, TT - 0.5), (tx - 22.5, ty + 19, TT + 20),
                                (tx - 23.5, ty + 21, TT + 40)], r=0.9),
                      Part.makeSphere(2.0, V(tx - 23.5, ty + 21, TT + 41)))
turret = cad.text(turret, "ATECH", (tx - 12, ty - 14, TT), (0, 0, 1), 6, depth=0.5, mode="deboss", up=(0, 1, 0))
# the driver's vision block on the glacis' top edge, engine-deck louvres,
# an exhaust and two tow hooks on the rear plate
upper = cad.fuse_one(upper, cad.soften(box(-6, 8, -142, -134, DECK - 1, DECK + 3.5), 0.8))
upper = cad.grille(upper, (30, -6, DECK), (0, 0, 1), (44, 12), kind="slot", hole=2.4, pitch=5.0)
upper = cad.fuse_one(upper,
                     cad.pipe([(66, 11.5, 40), (68, 16, 41), (70, 19, 46)], r=2.6),
                     *[cad.pipe([(x - 5, 11.0, 22), (x - 3, 16, 22), (x + 3, 16, 22), (x + 5, 11.0, 22)], r=1.3)
                       for x in (2, 58)])
# rivets along both deck edges
upper = cad.fuse_one(upper, *[Part.makeSphere(1.0, V(x, y, DECK - 0.4))
                              for x in (-17.5, 77.5) for y in range(-120, 0, 15)])
# guards over the headlights: a hoop on each lamp housing
guards = []
for m in (head_l, head_r):
    b = ap.bbox(m)
    cx = (b.XMin + b.XMax) / 2
    guards.append(cad.pipe([(cx - 11, -141.0, LZ - 4), (cx - 10, -151.5, LZ + 6), (cx, -152.5, LZ + 12),
                            (cx + 10, -151.5, LZ + 6), (cx + 11, -141.0, LZ - 4)], r=1.0))
upper = cad.fuse_one(upper, *guards)
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour])
    return o


for nm, sh in (("Hull_Lower", lower), ("Hull_Upper", upper), ("Turret_Ring", ring), ("Turret", turret)):
    part(nm, sh, nm)
for i, sd in enumerate("LR"):
    o = part("Headlight_" + sd, lenses[i], "Lens")
    o.ViewObject.Transparency = cad.transparency("glass")
for nm, sh in running.items():
    part(nm, sh, nm[:-2])
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
