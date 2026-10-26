"""Example: "a small desk fan" - a guarded fan head on a stem and a long foot.

fork this file for a desk fan / blower (a table fan, a clip fan, a
turbine - a rotor behind a guard); change PARAMETERS and the outlines.
ARCHETYPE: fan

How it is built (R411):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT in the foot (port 8 at the front); the dc_motor CABLED from
    port 7 straight back, up the hollow stem, through the tilt collar and
    the neck into the motor pod, its shaft forward (-Y) on the fan axis;
    the power key (6) and a glow light (14) seated at the foot's front,
    facing up under a key cap and a frosted lens; USB-C (1) behind a
    pocket in the left side. The foot is two straight outlines
    (cad.profile_body, fillet) hollowed with its own core and split low
    into the fixed Base (standoffs, fences) and the Foot_Shell; three M2.5
    screws from below. The motor pod is ONE revolved (radius, y) section
    with its walls in it (no core, no boolean), bulkheads hold the motor,
    a rear cap is keyed in and screwed. The rotor (hub + five pitched
    blades) sits on the shaft between the rear guard (pegged to the pod)
    and the front guard (a ring, radial bars and two rings, clipped over
    the rear guard's rim) - the guard is >= 60 % of the front.
  * STAGE B - details: the guard badge, raised rings round the key and
    lens, lettering, vents, a groove on the collar, rubber feet.
DETAILS (visible, 25 of 31): 1 front guard ring; 2 twelve radial bars;
3 two concentric rings; 4 rim band hooked behind the rear guard, pinned;
5 rear guard with twelve radial bars; 6 coral domed centre badge; 7 six
wide pitched blades on a domed hub (a separate rotor); 8 revolved motor pod
with a rolled nose; 9 domed rear cap; 10 its screw; 11 tilt collar
(brushed barrel across the stem); 12 tilt knobs on both ends; 13 grooves
round the collar; 14 hollow stem; 15 raised socket ring where the stem
meets the foot; 16 long foot with chamfered top edges, soft fillets;
17 power key cap with flange and plunger; 18 raised ring round it;
19 frosted glow lens (a light pipe with a flange); 20 raised ring round
it; 21 "ATECH" on the foot's nose; 22 USB-C pocket with liner in the left
side; 23 slot vents on the foot's back; 24 four rubber feet; 25 three
countersunk screws under the foot. Inside: 26 the motor ribbon run up the
stem, collar and neck (a 17.2 mm bore); 27 two bulkheads round the motor
(its holder, 0.3 mm clear); 28 the pad the cap screw bites; 29 rib onto
the board's spine; 30 standoffs and fences under the board; 31 lip
keying the shell to the base.
Materials: mint foot shell and pod, graphite base and cap, chrome guards
and key, sky blades, coral badge, brushed collar, frosted lens, rubber
feet, chrome screws.
MEASURED (R411, 2026-10-20): see test_kit_examples_r270 (TIMINGS line).
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
    "Foot_Shell", "Stem", "Collar", "Pod", "Pod_Cap", "Guard_Rear", "Guard_Front", "Badge",
    "Rotor", "Key_Power", "Glow_Lens", "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    "covers": {"Key_Power": "button_p6"}}
REVIEW_CLOSEUPS = ["Guard_Front", "Rotor", "Collar"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# R411: the fan axis runs along -Y (front), centred over the board's x = 30.
WALL = 2.0
FOOT = 1.5                         # rubber feet under the base
L = 8.5                            # PCB top (board z 6..13)
SPLIT = 4.5                        # base / foot-shell seam (lip top 5.7, under the slide paths)
FOOT_TOP = 25.0
FOOT_SIDE = [(-10, FOOT), (70, FOOT), (70, 19), (66, FOOT_TOP), (-6, FOOT_TOP), (-10, 19)]   # (x, z)
FOOT_PLAN_W = (-10.0, 70.0, -130.0, 30.0)     # x0, x1, y0, y1 of the foot's plan
FOOT_R = 18.0                      # its plan corner radius (board corners >= 4.7 inside)
STEM = (30.0, 9.0)                 # the stem's axis (x, y): behind the board's back edge
STEM_R, BORE_R = 11.0, 8.6         # stem outside, the ribbon bore (ribbon 14 wide, twisted)
Z_COLLAR = 88.0                    # the tilt collar's axis height
MOTOR_Y = -37.85                   # the motor's centre (its shaft tip at y -62)
MOTOR_Z = 125.0                    # ... and height (the shaft is 0.57 above it)
RP = 19.5                          # pod radius
POD_Y0, POD_Y1 = -55.5, 22.0       # pod nose face, rear rim
GUARD_R = 80.0                     # the guard's radius (>= 60 % of the front)
GUARD_Y = (-55.5, -56.7, -68.4, -70.8)   # rear guard face / back, front bars back / face
BLADES, PITCH, BLADE_Y = 6, 12.0, -62.5   # wide blades: the rotor fills the guard
SCREWS = [(-3.4, -60.0), (63.4, -60.0), (-3.4, 8.0), (63.4, 8.0)]   # sleeves clear of walls and lip
COLOURS = {"Base": "graphite", "Foot_Shell": "mint", "Stem": "chrome", "Collar": "brushed_alu",
           "Pod": "mint", "Pod_Cap": "graphite", "Guard_Rear": "chrome", "Guard_Front": "chrome",
           "Badge": "coral", "Rotor": "sky", "Key_Power": "chrome", "Glow_Lens": "frosted",
           "Rubber": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
FLAT = Rotation(Vector(1, 0, 0), 90)
board = ap.board_object(doc)
board.Placement = Placement(Vector(0, 0, L), FLAT)     # x 0..60, y -120..0
key = ap.seat(doc, "button", 6)                        # front left, facing up
glow = ap.seat(doc, "light", 14)                       # front right, facing up
usb = ap.seat(doc, "usbc", 1)                          # back left, mouth -X
# the motor: CABLED from port 7 (back centre) straight back, up the stem
# and into the pod; pins back (+Y), so the shaft points forward (-Y)
motor, motor_rib = ap.cable(doc, "dc_motor", 7, ap.module_placement(
    "dc_motor", (STEM[0], MOTOR_Y, MOTOR_Z), face="+Z", cable="+Y"),
    via=[(STEM[0], 8, 20), (STEM[0], STEM[1], 60), (STEM[0], STEM[1], 104)])
BB = ap.bbox(board)
MB = ap.bbox(motor)
AX, AZ = STEM[0], MB.ZMin + 10.14                      # the fan axis: the shaft, measured
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def ycyl(r, y0, y1, x=None, z=None):
    """A cylinder on the fan axis (or parallel to it) from y0 to y1."""
    x, z = AX if x is None else x, AZ if z is None else z
    return Part.makeCylinder(r, abs(y1 - y0), V(x, min(y0, y1), z), V(0, 1, 0))


def yring(r0, r1, y0, y1):
    return cad.cut(ycyl(r1, y0, y1), ycyl(r0, y0 - 1 if y0 < y1 else y0 + 1, y1 + 1 if y0 < y1 else y1 - 1))


def annulus(r0, r1, z0, z1, c):
    return cad.cut(cyl(r1, (c[0], c[1], z0), z1 - z0), cyl(r0, (c[0], c[1], z0 - 1), z1 - z0 + 2))


def arc(c, r, a0, a1):
    """('arc', mid, end) of the circle (c, r) from angle a0 to a1 (deg)."""
    am, a1 = math.radians((a0 + a1) / 2), math.radians(a1)
    return ("arc", (c[0] + r * math.cos(am), c[1] + r * math.sin(am)),
            (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1)))


def centre(m):
    b = ap.bbox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2


def bar_y(r0, r1, ang, w, y0, y1):
    """A straight radial bar across the fan axis at angle ang (deg)."""
    b = box(AX + r0, AX + r1, min(y0, y1), max(y0, y1), AZ - w / 2, AZ + w / 2)
    b.rotate(V(AX, 0, AZ), V(0, 1, 0), ang)
    return b


# ------------------------------------------------------------ the foot
fx0, fx1, fy0, fy1 = FOOT_PLAN_W
plan = cad.rounded_rect_wire(fx1 - fx0, fy1 - fy0, FOOT_R, ((fx0 + fx1) / 2, (fy0 + fy1) / 2, 0), "Z")
foot = cad.profile_body(FOOT_SIDE, plan, spline=False, fillet=3.0)
foot = cad.hollow(foot, WALL, core=lambda t: cad.profile_body(FOOT_SIDE, plan, spline=False, fillet=None,
                                                              inset=t))
base, shell = cad.split(foot, "Z", at=SPLIT, lip=1.2)
tick("foot")
# the fixed base holds the board: standoffs 0.1 mm under it, fences 0.3 mm
# off its long edges - all under the modules' slide paths
PCB0 = L - 2.5
holders = [box(x - 3, x + 3, y - 3, y + 3, FOOT + 1.5, PCB0 - 0.1)
           for x in (BB.XMin + 12, BB.XMax - 12) for y in (BB.YMax - 30, BB.YMin + 30)]
holders += [box(x0, x1, y - 4, y + 4, FOOT + 1.5, L - 1.0)
            for x0, x1 in ((BB.XMin - 1.8, BB.XMin - 0.3), (BB.XMax + 0.3, BB.XMax + 1.8))
            for y in (-40, -80)]
base = cad.fuse_one(base, *holders)
# board retention: a rib from the shell's top onto the spine (0.2 mm off)
shell = cad.fuse_one(shell, box(29, 31, -80, -40, L + 4.5 + 0.2, FOOT_TOP - 1.5))
# three M2.5 up through the floor into bosses hanging from the top, each
# with a heat-set insert pocket (1.4 d + 0.1) in a sleeve
screws = []
for x, y in SCREWS:
    shell = cad.screw_boss(shell, (x, y, FOOT + 2.1), axis="+Z", size="M2.5", ribs=0)
    base = cad.countersink(base, (x, y, FOOT), "+Z", 2.9, 5.6, 90.0)
    screws.append(cad.screw("csk_phillips", "M2.5", 10, at=(x, y, FOOT), axis="+Z"))
# all sleeves in ONE fuse, all pockets in ONE cut (TRAPS 12: one at a time,
# the second sleeve's fuse came back as 2 solids, MEASURED)
shell = cad.fuse_one(shell, *[cyl(3.0, (x, y, FOOT + 2.1), 10.0) for x, y in SCREWS])
shell = cad.cut(shell, [cyl(1.8, (x, y, FOOT + 2.0), 9.0) for x, y in SCREWS])
# the stem's socket: a raised ring on the top, the stem pressed through it
# into the foot (line to line: it is held, and the ribbon rises inside it)
shell = cad.fuse_one(shell, cyl(STEM_R + 4.0, (STEM[0], STEM[1], FOOT_TOP - 1.0), 5.0))
shell = cad.cut(shell, cyl(STEM_R, (STEM[0], STEM[1], FOOT_TOP - 8.0), 20.0))
stem = cad.cut(cyl(STEM_R, (STEM[0], STEM[1], FOOT_TOP - 4.0), Z_COLLAR - (FOOT_TOP - 4.0)),
               cyl(BORE_R, (STEM[0], STEM[1], FOOT_TOP - 5.0), 200))
tick("base + screws + stem")

# ------------------------------------------------------------ foot openings
# the power key: a cap through the top, flange 0.1 mm under it, a plunger
# to 0.16 mm over the module's own cap
kx, ky = centre(key)
k_top = ap.bbox(key).ZMax
base_z = FOOT_TOP - WALL - 0.9
cap = cad.button_cap(13, (FOOT_TOP + 1.6) - base_z, dome=0.8, flange=1.5, at=(kx, ky, base_z), axis="+Z")
shell = cad.opening_for(shell, cap, clearance=0.25, chamfer=0.4, axis="+Z")
cap = cad.fuse_one(cap, cyl(3.0, (kx, ky, k_top + 0.16), base_z - (k_top + 0.16) + 0.5))
# the glow light: a frosted light pipe from 0.4 mm over the LEDs to 1.2 mm
# proud, a flange under the top wall
gx, gy = centre(glow)
g_top = ap.bbox(glow).ZMax
lens = cad.lens(17.6, (FOOT_TOP + 1.2) - (g_top + 0.4), dome=1.0, at=(gx, gy, g_top + 0.4), axis="+Z")
shell = cad.opening_for(shell, lens, clearance=0.2, chamfer=0.0, axis="+Z")
lens = cad.fuse_one(lens, cyl(10.4, (gx, gy, FOOT_TOP - WALL - 0.9), 0.8))
# USB-C on the left: a pocket brings the wall to 0.25 mm off the mouth
ub = ap.bbox(usb)
uy, uz = (ub.YMin + ub.YMax) / 2, L + 5.9


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


pocket = xprism(uy - 6.5, uy + 6.5, uz - 5.0, uz + 5.0, fx0 - 5, ub.XMin - 1.3, 3)
liner = cad.cut(xprism(uy - 8.5, uy + 8.5, max(uz - 7.0, SPLIT + 1.6), uz + 7.0, ub.XMin - 0.25, fx0 + 1.0, 3.5),
                pocket)
shell = cad.fuse_one(cad.cut(shell, pocket), liner)
shell = cad.socket_opening(shell, usb, margin=1.5)
tick("foot openings")

# ------------------------------------------------------------ the motor pod
# ONE revolved (radius, y) section with both skins in it: a rolled nose,
# the barrel, an open rear rim (the cap closes it); the shaft passes a
# 2.6 mm hole on the axis
RN = 5.0                           # nose roll
pod = cad.revolve_profile([
    (2.6, POD_Y0), (RP - RN, POD_Y0), arc((RP - RN, POD_Y0 + RN), RN, -90, 0),
    (RP, POD_Y1), (RP - WALL, POD_Y1),
    (RP - WALL, POD_Y0 + RN), arc((RP - RN, POD_Y0 + RN), RN - WALL, 0, -90),
    (2.6, POD_Y0 + WALL)], axis="Y", at=(AX, 0, AZ))
# the neck down into the collar, its bore up into the pod
# (the neck runs up past the pod's curved underside, then the pod's inside
# is cut clear again, so the junction is one clean intersection)
pod = cad.fuse_one(pod, cyl(STEM_R, (STEM[0], STEM[1], Z_COLLAR), AZ - RP + 6.0 - Z_COLLAR))
pod = cad.cut(pod, [ycyl(RP - WALL - 0.1, POD_Y0 + RN, POD_Y1 + 1),
                    cyl(BORE_R, (STEM[0], STEM[1], Z_COLLAR - 1), AZ - RP + 8.0 - Z_COLLAR)])
# the motor's holder: two stations of four ribs from the wall to 0.3 mm
# off its body (ribs, not discs: a disc across the bore reads as a 35 mm
# hole through three walls)
mcx, mcz = (MB.XMin + MB.XMax) / 2, (MB.ZMin + MB.ZMax) / 2
inner = ycyl(RP - WALL + 0.3, -60, 0)
ribs = []
for y in (-50.0, -32.0):
    ribs += [box(mcx - 2, mcx + 2, y, y + 2.0, MB.ZMax + 0.3, AZ + RP),
             box(mcx - 2, mcx + 2, y, y + 2.0, AZ - RP, MB.ZMin - 0.3),
             box(AX - RP, MB.XMin - 0.3, y, y + 2.0, mcz - 2, mcz + 2),
             box(MB.XMax + 0.3, AX + RP, y, y + 2.0, mcz - 2, mcz + 2)]
ribs = [r.common(inner) for r in ribs]
# the pad the cap screw bites: a web from the pod's crown down to the
# axis, behind the motor and above its ribbon
pad = box(AX - 4, AX + 4, -11.0, -7.0, AZ - 4.0, AZ + RP - 1.0).common(ycyl(RP - 0.5, -20, 0))
pod = cad.fuse_one(pod, *ribs, pad)
# the rear cap: a dome with a spigot ring 3 mm into the pod's bore
YC, RC_O = 5.375, 25.625           # the dome's centre (on the axis) and outer radius
RC_I = RC_O - WALL
Y_PAD = YC + RC_I - 1.4           # a flat pad inside the apex for the screw's boss
a6 = math.degrees(math.acos(6.0 / RC_I))
cap_rear = cad.revolve_profile([
    (0, Y_PAD), (6.0, Y_PAD), (6.0, YC + RC_I * math.sin(math.radians(a6))),
    arc((0, YC), RC_I, a6, math.degrees(math.asin((POD_Y1 + 1.2 - YC) / RC_I))),
    (15.5, POD_Y1 + 1.2), (15.5, POD_Y1 - 3.0), (RP - WALL - 0.2, POD_Y1 - 3.0), (RP - WALL - 0.2, POD_Y1),
    (RP, POD_Y1), arc((0, YC), RC_O, math.degrees(math.atan2(POD_Y1 - YC, RP)), 90)],
    axis="Y", at=(AX, 0, AZ))
yc_out = YC + RC_O                 # the dome's apex, on the fan axis
cap_rear, pod = cad.screw_through(cap_rear, pod, (AX, yc_out, AZ), size="M2", ribs=0)
y_top = Y_PAD - 0.1
pod = cad.fuse_one(pod, ycyl(2.8, y_top, y_top - 9.0))
pod = cad.cut(pod, ycyl(1.6, y_top + 0.5, y_top - 9.0))
screws.append(cad.screw("csk_phillips", "M2", 8, at=(AX, yc_out, AZ), axis="-Y"))
# the tilt collar: a brushed barrel across the stem, the stem's top and
# the neck's foot pressed into its bore, tilt knobs on both ends
collar = cad.fuse_one(cyl(14.0, (AX - 17, STEM[1], Z_COLLAR), 34.0, (1, 0, 0)),
                      cyl(14.0, (STEM[0], STEM[1], Z_COLLAR - 14.0), 28.0),        # walls >= 3 round the bore
                      cad.soften(cyl(9.0, (AX - 21, STEM[1], Z_COLLAR), 4.5, (1, 0, 0)), 1.0),
                      cad.soften(cyl(9.0, (AX + 16.5, STEM[1], Z_COLLAR), 4.5, (1, 0, 0)), 1.0))
collar = cad.cut(collar, cyl(STEM_R, (STEM[0], STEM[1], Z_COLLAR - 20), 40))
tick("pod + collar")

# ------------------------------------------------------------ guards + rotor
gr_face, gr_back, gf_back, gf_face = GUARD_Y
# rear guard: a centre disc against the pod's nose (three pegs into it),
# twelve radial bars, a rim ring
rear = cad.fuse_one(ycyl(RP + 2.5, gr_face, gr_back), yring(GUARD_R - 6.0, GUARD_R - 2.2, gr_face, gr_back),
                    *[bar_y(RP, GUARD_R - 5.0, a, 2.4, gr_face, gr_back) for a in range(0, 360, 30)])
rear = cad.cut(rear, ycyl(2.6, gr_face + 1, gr_back - 1))
pegs = []
for a in (90, 210, 330):
    px, pz = AX + 12.0 * math.cos(math.radians(a)), AZ + 12.0 * math.sin(math.radians(a))
    pegs.append(ycyl(1.35, gr_face - 0.3, gr_face + 1.8, px, pz))          # a pin, 0.15 mm clear
    pod = cad.cut(pod, ycyl(1.5, POD_Y0 - 1, POD_Y0 + WALL + 1, px, pz))
rear = cad.fuse_one(rear, *pegs)
# front guard: a ring, twelve radial bars, two rings, a centre disc; its
# rim band runs back over the rear guard's ring and hooks behind it
front = cad.fuse_one(
    yring(GUARD_R - 4.0, GUARD_R, gf_back, gf_face),
    yring(GUARD_R - 2.0, GUARD_R, gr_face + 1.5, gf_back),
    yring(GUARD_R - 5.0, GUARD_R - 2.0, gr_face + 1.5, gr_face),
    yring(29.3, 30.7, gf_back, gf_face), yring(51.3, 52.7, gf_back, gf_face),
    ycyl(15.0, gf_back, gf_face - 1.2),
    *[bar_y(14.0, GUARD_R - 2.5, a, 1.8, gf_back, gf_face) for a in range(0, 360, 30)])
# three pins from the hook into the rear guard's ring (a pinned joint)
for a in (30, 150, 270):
    px, pz = AX + 76.0 * math.cos(math.radians(a)), AZ + 76.0 * math.sin(math.radians(a))
    front = cad.fuse_one(front, ycyl(0.9, gr_face + 0.5, gr_back + 0.1, px, pz))
    rear = cad.cut(rear, ycyl(1.05, gr_face + 1, gr_back - 1, px, pz))
GUARD_SHARE = math.pi * GUARD_R ** 2 / ((2 * GUARD_R) * (AZ + GUARD_R))
print("GUARD d %.0f = %.0f %% of the %.0f x %.0f front" % (2 * GUARD_R, 100 * GUARD_SHARE, 2 * GUARD_R,
                                                            AZ + GUARD_R))
# the rotor: a domed hub on the shaft (bore 3.3, blind) and five pitched
# blades - lines only, each a flat plate turned PITCH about its radius
my0 = MB.YMin                                       # the shaft tip
hub = cad.revolve_profile([(1.65, gr_back - 0.5), (10.0, gr_back - 0.5), (10.0, -63.0),
                           arc((6.0, -63.0), 4.0, 0, -90), (0, -67.0), (0, my0 - 0.3), (1.65, my0 - 0.3)],
                          axis="Y", at=(AX, 0, AZ))
OUTLINE = [(8, -7), (22, -12), (38, -17), (54, -20), (62, -18.5), (66.5, -10), (67, 0), (65, 9),
           (58, 15.5), (42, 15), (24, 11), (8, 7)]   # (radius, along the turn): wide blades
blades = []
for k in range(BLADES):
    f = Part.Face(Part.makePolygon([V(AX + u, 0, AZ + v) for u, v in OUTLINE + OUTLINE[:1]]))
    b = f.extrude(V(0, 1.6, 0))
    b.translate(V(0, BLADE_Y - 0.8, 0))
    b.rotate(V(AX, BLADE_Y, AZ), V(1, 0, 0), PITCH)
    b.rotate(V(AX, BLADE_Y, AZ), V(0, 1, 0), 360.0 * k / BLADES)
    blades.append(b)
rotor = cad.fuse_one(hub, *blades)
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# the badge: a coral domed disc in a pocket of the guard's centre
front = cad.cut(front, ycyl(10.0, gf_face - 2.2, gf_face + 0.4))
badge = cad.soften(ycyl(9.85, gf_face - 1.6, gf_face + 0.4), 0.6)    # a domed button 0.4 proud
# raised rings round the key and the lens, a groove round the collar
shell = cad.fuse_one(shell, annulus(8.3, 9.8, FOOT_TOP - 0.5, FOOT_TOP + 0.6, (kx, ky)),
                     annulus(9.6, 11.1, FOOT_TOP - 0.5, FOOT_TOP + 0.6, (gx, gy)))
for gxx in (AX - 14.5, AX + 14.5):
    collar = cad.groove_ring(collar, "X", gxx, w=0.8, depth=0.6)
# lettering on the foot's nose, slot vents on its back
shell = cad.text(shell, "ATECH", (30, fy0, 14.0), (0, -1, 0), 6, depth=0.5, mode="deboss")
shell = cad.grille(shell, (30, fy1, 14.0), (0, 1, 0), (36, 8), kind="slot", hole=2.0, pitch=4.5)
# rubber feet in recesses under the base
feet = []
for x in (fx0 + 10, fx1 - 10):
    for y in (fy0 + 14, fy1 - 14):
        base = cad.cut(base, cyl(4.6, (x, y, FOOT - 1), 2.2))
        feet.append(cad.foot(9, FOOT + 1.2, style="dome", at=(x, y, FOOT + 1.2)))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[name.split("_")[0] if name.startswith(("Rubber", "Screw"))
                                              else name])
    return o


for nm, sh in (("Base", base), ("Foot_Shell", shell), ("Stem", stem), ("Collar", collar), ("Pod", pod),
               ("Pod_Cap", cap_rear), ("Guard_Rear", rear), ("Guard_Front", front), ("Badge", badge),
               ("Rotor", rotor), ("Key_Power", cap)):
    part(nm, sh)
o = part("Glow_Lens", lens)
o.ViewObject.Transparency = cad.transparency(COLOURS["Glow_Lens"])
for i, sh in enumerate(feet):
    part("Rubber_%d" % (i + 1), sh)
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh)
print("TOTAL %.1f s" % (time.time() - T0))
