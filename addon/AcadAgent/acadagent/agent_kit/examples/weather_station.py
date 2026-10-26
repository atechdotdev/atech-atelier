"""Example: "a weather station" - a leaning, wedged display body on a sculpted foot, a louvred hut on top.

fork this file for a weather station / desk instrument (a thermometer, a
barometer, a hygrometer, an air-quality monitor, a plant or room sensor
with a display); change PARAMETERS and the outlines.
ARCHETYPE: weather station

How it is built (R412, resculpted R610):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board LANDSCAPE_UP in the body (modules facing the front, -Y): the
    screen (11, 12) behind a smoked lens in a recessed black bezel tray
    (its back is the mask with the screen window), MODE / NEXT keys (3, 4)
    under it, an alert LED (9) behind a clear lens, USB-C (7) in a pocket
    in the left side; temp_humidity CABLED from port 13 straight up out of
    the body, through a hollow post (the mast) into a louvred hut (stacked
    slats on three sides, a pitched roof with an overhang and drip edges)
    - away from the board's heat, a wall (the body's top) between them.
    R610: the body is built UPRIGHT in its own frame and the whole
    instrument - board, modules and every part - LEANS BACK TILT degrees
    (TP: the board is placed through it, the cabled sensor too, ibox()
    measures a module back in the upright frame). The body is three views:
    a soft front silhouette (cad.profile_body side), a plan with a curved
    back (spline), and a WEDGE (deep at the foot, thin at the top) cut
    along its length; hollowed with its own core and split front / back
    with a lip; four M2.5 screws from behind into insert bosses; it stands
    in a sculpted graphite foot (a spline cross-section: a lip in front, a
    backrest behind), pinned into its back half.
  * STAGE B - details: a sun shade over the display, key legends, gauge
    words, lettering, vents and a wall-hang keyhole on the back, rubber
    feet.
DETAILS (visible, 26 of 32): 1 leaning display body, soft 14 mm corners
and 3 mm edges; 2 wedge side profile, curved back; 3 sculpted graphite foot
with a front lip and a backrest; 4 the body seated in its pocket;
5 smoked display lens; 6 recessed black bezel round it; 7 black mask with
the screen window; 8 sun shade over the display; 9 MODE key cap; 10 NEXT
key cap; 11 "MODE" / "NEXT" over the keys; 12 "TEMP" / "RH" gauge words by
the screen; 13 clear alert-LED lens with a flange; 14 USB-C pocket with
liner in the left side; 15 "ATECH" on the foot; 16 louvred hut, stacked
slats on the front; 17-18 slats on both sides; 19 pitched hut roof with
an overhang; 20-21 drip edges under the eaves; 22 hollow post (the mast)
carrying the sensor's ribbon; 23 hex vents on the back; 24 wall-hang
keyhole; 25 four countersunk screws on the back; 26 four rubber feet.
Inside: 27 the sensor's holder (hut floor, back and side ribs); 28 rib
onto the board's spine; 29 board ledges and standoffs; 30 heat-set
insert bosses; 31 front / back lip; 32 two pins from the foot into the
back half.
Materials: matte white body, cream hut, graphite foot and roof, smoked
lens, black bezel, blue LED lens, coral keys, rubber feet, chrome screws.
MEASURED (R610, 2026-10-26): see test_kit_examples_r270 (TIMINGS line).
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
    "Front", "Bezel", "Lens", "Alert_Lens", "Key_Mode", "Key_Next", "Hut", "Hut_Roof", "Foot",
    "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4", "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    "covers": {"Key_Mode": "button_p3", "Key_Next": "button_p4"}}
REVIEW_CLOSEUPS = ["Hut", "Lens", "Key_Mode"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# R412: front = -Y, x across, z up (the desk at z = 0). R610: every number
# below is in the UPRIGHT body frame; TP leans the finished instrument
# back TILT degrees about the body's back-bottom edge.
WALL = 2.0
TILT = 12.0                      # R610: the face leans back (read from a desk, standing or seated)
SX0, SX1 = -12.0, 132.0          # body across (board x 0..120)
ZS, ZT = 12.0, 98.0              # body bottom (in the foot's pocket), body top
YF = -15.0                       # the flat front face (room for lens + mask before the screen)
SLAB_R, FILLET = 14.0, 3.0       # front silhouette's bottom corner radius, every outer edge
# R610: the plan's back is a spline (deepest mid-width); the WEDGE takes
# the back from WEDGE[0] at the foot to WEDGE[1] at the top
PLAN = [("line", (SX0, YF)), ("line", (SX1, YF)), ("line", (SX1, 8.0)), (126.0, 10.6), (110.0, 13.2),
        (85.0, 15.0), (60.0, 15.5), (35.0, 15.0), (10.0, 13.2), (-6.0, 10.6), ("line", (SX0, 8.0))]
WEDGE = (16.5, 6.8)
TOP_FALL, BULLNOSE = 3.5, 4.0    # R610: the top falls toward the front; its front edge rolls over
BOARD_Z0 = 22.0                  # board box min z (the keys' row above the foot)
LENS = (24.0, 100.0, 57.6, 87.6)  # smoked lens x0, x1, z0, z1 (the screen at z 63..82)
LENS_R, BEZEL, RECESS = 4.0, 4.0, 1.0
SCREEN_WIN = (36.0, 18.0)        # mask window over the screen (active area 25.6 x 13.5)
TH_Z = 116.0                     # the sensor's centre, in the hut
HUT = (76.0, 104.0, -15.0, 5.0, 104.0, 134.0)    # hut x0, x1, y0, y1, z0, z1
ROOF_OVER, RIDGE = 4.0, 8.0      # roof overhang, ridge height over the eaves
SLAT_PITCH, SLAT_TILT = 5.0, 20.0
# R610: the foot, in the WORLD (it stands on the desk): its cross-section
# (y, z) - a front lip, a hollow under the body, a backrest - and plan
FOOT_SIDE = [("line", (-28.0, 1.5)), ("line", (44.0, 1.5)), (46.5, 3.6), (45.0, 7.2), (38.5, 12.0),
             (31.0, 18.0), (25.5, 24.0), (21.5, 28.0), (15.0, 28.6), (6.0, 26.0), (-6.0, 23.8),
             (-16.0, 23.2), (-22.0, 22.2), (-26.5, 19.0), (-29.5, 13.0), ("corner", (-30.0, 6.5))]
# its plan (world x, y): the front bowed out mid-width, the ends rounded
FOOT_PLAN = [("line", (138.0, 58.0)), ("line", (-18.0, 58.0)), ("line", (-18.0, -8.0)), (-15.0, -18.0),
             (-4.0, -25.5), (60.0, -32.0), (124.0, -25.5), (135.0, -18.0), ("line", (138.0, -8.0))]
fx0, fx1 = -18.0, 138.0
# R610: and its front view (x, z): high in the middle, its ends rolling down
FOOT_FRONT = [("line", (-30.0, -1.0)), ("line", (150.0, -1.0)), ("line", (150.0, 6.0)), (144.0, 12.0),
              (134.0, 21.0), (118.0, 29.0), (60.0, 31.5), (2.0, 29.0), (-14.0, 21.0), (-24.0, 12.0),
              ("line", (-30.0, 6.0))]
SCREWS = [(-5.0, 36.0), (-5.0, 80.0), (125.0, 36.0), (125.0, 80.0)]          # (x, z) on the back, over the backrest
COLOURS = {"Front": "matte_white", "Back": "matte_white", "Bezel": "matte_black", "Lens": "smoked",
           "Alert_Lens": "led_blue", "Key": "coral", "Hut": "cream", "Hut_Roof": "graphite",
           "Foot": "graphite", "Rubber": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
LANDSCAPE_UP = Rotation(Vector(0, 0, 1), 180).multiply(Rotation(Vector(0, 1, 0), -90))
PIVOT = V(0, 10.0, ZS)
TP = Placement(V(), Rotation(V(1, 0, 0), -TILT), PIVOT)     # upright body frame -> world
board = ap.board_object(doc)
board.Placement = Placement(V(), LANDSCAPE_UP)
_b = ap.bbox(board)
upright = Placement(V(-_b.XMin, 0, BOARD_Z0 - _b.ZMin), LANDSCAPE_UP)   # x 0..120, z 22..82
board.Placement = upright
BB = ap.bbox(board)                             # in the body frame
board.Placement = TP.multiply(upright)          # R610: the board leans; the modules seat on it
scr = ap.seat(doc, "screen", (11, 12))          # top row centre
alert = ap.seat(doc, "light", 9)                # top row, left
key_m = ap.seat(doc, "button", 3)               # bottom row, under the screen
key_n = ap.seat(doc, "button", 4)
usb = ap.seat(doc, "usbc", 7)                   # left end, mouth -X
# the sensor: CABLED from port 13 straight up (a straight rise: the
# cleanest ribbon) into the hut, facing the front louvres
th, th_rib = ap.cable(doc, "temp_humidity", 13, TP.multiply(ap.module_placement(
    "temp_humidity", (90, -4.84, TH_Z), face="-Y", cable="-Z")))


def ibox(m):
    """R610: a module's (or a cable's) box in the UPRIGHT body frame."""
    g = (m.Mesh if hasattr(m, "Mesh") else m.Shape).copy()
    g.Placement = TP.inverse().multiply(g.Placement)
    return g.BoundBox


def T(s):
    """Body frame -> world (the lean)."""
    s = s.copy()
    s.rotate(PIVOT, V(1, 0, 0), -TILT)
    return s


TB, RB = ibox(th), ibox(th_rib[0])
tick("hardware")


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


def centre(m):
    b = ibox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


def section_x(pts, x0, x1):
    """A (y, z) polygon extruded along X from x0 to x1 (lines only)."""
    f = Part.Face(Part.makePolygon([V(x0, y, z) for y, z in pts + pts[:1]]))
    s = f.extrude(V(x1 - x0, 0, 0))
    if s.Volume < 0:
        s.reverse()
    return s


def ray(shape, p0, p1):
    """Where the segment p0 -> p1 crosses the shape's surface (R610: the
    curved back has no number to read off)."""
    return [v.Point for v in shape.section(Part.makeLine(V(*p0), V(*p1))).Vertexes]


def back_y(shape, x, z):
    """The rearmost surface point of `shape` along +Y at (x, z)."""
    return max(p.y for p in ray(shape, (x, -40, z), (x, 60, z)))


# ------------------------------------------------------------ the body
# R610: front silhouette x plan (profile_body), x the wedge (a (y, z)
# section along X) - its new edges softened like the rest


def top_z(y):
    """The top's height at depth y (body frame): it falls TOP_FALL toward
    the front, so leaning back it stands near level under the hut."""
    return ZT - 0.2 - TOP_FALL * (WEDGE[1] - y) / (WEDGE[1] - YF)


def wedge(t):
    """The (y, z) section along X: the sloped back, the falling top, a
    BULLNOSE radius round the front-top edge - every edge moved t in."""
    import math
    lo = ZS - 10.0
    f = lambda z: WEDGE[0] + (WEDGE[1] - WEDGE[0]) * (z - ZS) / (ZT - ZS)     # noqa: E731
    zb, zf = top_z(f(ZT)), top_z(YF + BULLNOSE)
    a0, a1 = V(0, YF + BULLNOSE, zf), V(0, YF, zf - BULLNOSE)
    c = V(0, YF + BULLNOSE, zf - BULLNOSE)
    mid = c + V(0, -math.sqrt(0.5), math.sqrt(0.5)) * BULLNOSE
    w_ = Part.Wire([Part.makeLine(V(0, YF - 10, lo), V(0, f(lo), lo)),
                    Part.makeLine(V(0, f(lo), lo), V(0, f(ZT), zb)),
                    Part.makeLine(V(0, f(ZT), zb), a0),
                    Part.Arc(a0, mid, a1).toShape(),
                    Part.makeLine(a1, V(0, YF - 10, zf - BULLNOSE)),
                    Part.makeLine(V(0, YF - 10, zf - BULLNOSE), V(0, YF - 10, lo))])
    face = Part.Face(w_ if not t else w_.makeOffset2D(-t, join=0))
    face.translate(V(SX0 - 10, 0, 0))
    return face.extrude(V(SX1 - SX0 + 20, 0, 0))


# the front silhouette (x, z): soft bottom corners, top shoulders that roll
# down into the sides (the falling top section governs mid-width)
R_ = SLAB_R
side = cad.spline_wire([("line", (SX0 + R_, ZS)), ("line", (SX1 - R_, ZS)),
                        ("arc", (SX1 - R_ * (1 - 0.7071), ZS + R_ * (1 - 0.7071)), (SX1, ZS + R_)),
                        ("line", (SX1, ZT - 16.0)), (SX1 - 2.0, ZT - 8.5), (SX1 - 12.0, ZT - 3.0),
                        (100.0, ZT), (60.0, ZT + 0.4), (20.0, ZT),
                        (SX0 + 12.0, ZT - 3.0), (SX0 + 2.0, ZT - 8.5), ("line", (SX0, ZT - 16.0)),
                        ("line", (SX0, ZS + R_)),
                        ("arc", (SX0 + R_ * (1 - 0.7071), ZS + R_ * (1 - 0.7071)), (SX0 + R_, ZS))],
                       plane="XZ")
outer = cad.profile_body(side, PLAN, fillet=FILLET).common(wedge(0))
crease = [e for e in outer.Edges if e.BoundBox.YMin > 4.0 and e.BoundBox.ZLength > 1.0
          and abs(e.BoundBox.YMax - e.BoundBox.YMin) < 12.0]
outer = cad.fillet_safe(outer, FILLET, edges=crease)
# R610 (MEASURED, as on the toy car): a filleted spline body fails OCCT's
# BOP check (InvalidCurveOnSurface) and later booleans on it misfire (a
# screw boss "removed nothing"); a 0.01 mm edge tolerance passes it
outer.fixTolerance(0.01)
# the core keeps SHARP inner edges (a filleted core's concave rounds read
# to ./check as open clip channels - the handheld's lesson)
core = cad.profile_body(side, PLAN, fillet=None, inset=WALL).common(wedge(WALL))
skin = cad.profile_body(side, PLAN, fillet=FILLET, inset=0.5).common(wedge(0.5))   # 0.5 mm under the skin
slab = cad.cut(outer, core)
SPLIT_Y = BB.YMax + 0.3
front, back = cad.split(slab, "Y", at=SPLIT_Y, lip=1.2)
tick("body")

# ------------------------------------------------------------ back: holds the board
# R610: the ledges and standoffs reach back to the curved wall, clipped
# 0.5 mm under its skin
ledges = [box(BB.XMin + 4, BB.XMax - 4, 0.6, 30, BB.ZMin - 2.3, BB.ZMin - 0.3),
          box(BB.XMin + 4, BB.XMax - 4, 0.6, 30, BB.ZMax + 0.3, BB.ZMax + 2.3)]
ledges += [box(BB.XMin + x, BB.XMin + x + 6, BB.YMax + 0.1, 30, BB.ZMin + z, BB.ZMin + z + 6)
           for x in (8, 57, 106) for z in (7, 47)]
back = cad.fuse_one(back, *[lg.common(skin) for lg in ledges])
# four M2.5 screws from behind into bosses on the front's inside, each
# with a heat-set insert pocket (1.4 d + 0.1) in a sleeve
# R610: screw_through runs on the halves' pieces round each screw (a
# local box): on the whole spline shell its pilot "removed nothing" - a
# 28 mm3 hole is inside the Shape.Volume noise of a big spline body
# (MEASURED); what it adds and removes is then applied in one fuse / cut
screws, sleeves, pockets, bosses, csks = [], [], [], [], []
for x, z in SCREWS:
    yo = back_y(outer, x, z)
    lb = box(x - 7.5, x + 7.5, -20, 30, z - 7.5, z + 7.5)
    b0, f0 = back.common(lb), front.common(lb)
    b1, f1 = cad.screw_through(b0, f0, (x, yo, z), size="M2.5", ribs=0)
    csks.append(b0.cut(b1))
    bosses.append(f1.cut(f0))
    # its length as screw_through prints it: the tip 4.5 mm in front of
    # the board plane, however deep the curved back is there
    screws.append(cad.screw("csk_phillips", "M2.5", round(yo + 4.5), at=(x, yo, z), axis="-Y"))
    # the sleeve's top 0.1 mm under the back's inner face all round it
    # (that face slopes and curves: its lowest point over the sleeve)
    yb = min(back_y(core, x + dx, z + dz) for dx in (-3, 0, 3) for dz in (-3, 0, 3)) - 0.1
    sleeves.append(cyl(3.0, (x, yb, z), (0, -1, 0), 10.0))
    pockets.append(cyl(1.8, (x, yb + 0.5, z), (0, -1, 0), 9.5))
back = cad.cut(back, csks)
front = cad.fuse_one(front, *(bosses + sleeves))
front = cad.cut(front, pockets)
# board retention: a rib from the front wall onto the spine (0.2 mm off)
front = cad.fuse_one(front, box(58, 62, YF + WALL - 0.5, BB.YMin - 0.2, 44, 52))
tick("back + screws")

# ------------------------------------------------------------ the face
# the display: a black bezel tray set RECESS back in its opening, holding
# the smoked lens, its back the mask with the screen window
lx0, lx1, lz0, lz1 = LENS
front = cad.cut(front, yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, YF - 6,
                              YF + WALL + 1))
yt0, yt1 = YF + RECESS, YF + WALL + 3.0         # tray front, mask back (0.36 mm off the screen)
tray = cad.fuse_one(yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, yt0, YF + WALL + 1),
                    yprism(lx0 - 2, lx1 + 2, lz0 - 2, lz1 + 2, LENS_R + 2, YF + WALL + 0.5, yt1))
y_lens1 = YF + WALL + 1.7
tray = cad.cut(tray, yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 - 1, y_lens1))
lens = yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 + 0.6, y_lens1 - 0.3)   # 0.3 mm air before the mask
sx, _sy, sz = centre(scr)
tray = cad.cut(tray, cad.rounded_box(SCREEN_WIN[0], 10, SCREEN_WIN[1], 1.5,
                                     at=(sx - SCREEN_WIN[0] / 2, yt1 - 5, sz - SCREEN_WIN[1] / 2), edges="y"))
# MODE / NEXT keys: caps through the face, flange 0.1 mm behind the wall,
# a plunger to 0.16 mm off each module's own cap
keys = {}
y_base = YF + WALL + 0.9
for nm, m in (("Key_Mode", key_m), ("Key_Next", key_n)):
    kx, _ky, kz = centre(m)
    kb = ibox(m)
    cap = cad.button_cap(12, y_base - (YF - 1.6), dome=0.8, flange=1.5, at=(kx, y_base, kz), axis="-Y")
    front = cad.opening_for(front, cap, clearance=0.25, chamfer=0.4, axis="-Y")
    keys[nm] = cad.fuse_one(cap, cyl(3.0, (kx, kb.YMin - 0.16, kz), (0, -1, 0), (kb.YMin - 0.16) - y_base + 0.5))
# the alert LED: a clear light pipe from 0.4 mm off the LEDs to 0.8 mm
# proud, a flange behind the wall
ax_, _ay, az_ = centre(alert)
ab = ibox(alert)
pipe = cad.lens(17.0, (ab.YMin - 0.4) - (YF - 0.8), dome=0.8, at=(ax_, ab.YMin - 0.4, az_), axis="-Y")
front = cad.opening_for(front, pipe, clearance=0.2, chamfer=0.0, axis="-Y")
pipe = cad.fuse_one(pipe, cyl(10.0, (ax_, YF + WALL + 0.9, az_), (0, -1, 0), 0.8))
# USB-C on the left side: a pocket brings the wall to 0.25 mm off the
# socket mouth, then the measured opening
ub = ibox(usb)
uy, uz = -5.9, (ub.ZMin + ub.ZMax) / 2
pocket = xprism(uy - 5.5, uy + 5.5, uz - 6.5, uz + 6.5, SX0 - 5, ub.XMin - 1.3, 3)
liner = cad.cut(xprism(YF + 1.0, min(uy + 7.0, SPLIT_Y - 0.6), uz - 8.0, uz + 8.0, ub.XMin - 0.25, SX0 + 1.0, 3.5),
                pocket)
front = cad.fuse_one(cad.cut(front, pocket), liner)
# the plug opening through that wall: the mouth (10 x 3.5 mm, its long
# side along Z) plus 1.5 mm a side, as cad.socket_opening measures it on
# the upright build. R610: cut by hand in the body frame - socket_opening
# on the leaning shell turned the pocket inside out (the socket sealed,
# MEASURED), and on the body frame it measures the leaning module
front = cad.cut(front, xprism(uy - 3.25, uy + 3.25, uz - 6.5, uz + 6.5, ub.XMin - 2.0, ub.XMin - 0.1, 1.5))
tick("face")

# ------------------------------------------------------------ the hut
# a hollow post from inside the slab's top up to the hut floor carries the
# ribbon (>= 0.75 mm round it); the hut holds the sensor on its floor
# (0.25 mm under it), a rib behind it and ribs at its sides (0.3 mm off)
hx0, hx1, hy0, hy1, hz0, hz1 = HUT
pin_ = (RB.XMin - 1.1, RB.XMax + 1.1, -3.3, 0.3)          # post bore x0, x1, y0, y1
# R610: the post's foot follows the falling top, 1 mm down into it
PY1 = SPLIT_Y + 0.5                              # R610: the post spans the seam (a 0.5 mm sliver of
                                                 # the front's top wall was left behind it)
post = cad.cut(box(pin_[0] - 2, pin_[1] + 2, pin_[2] - 2, PY1, ZT - 6, hz0 + 0.5),
               [box(pin_[0], pin_[1], pin_[2], pin_[3], ZT - 10, hz0 + 10),
                section_x([(-20, ZT - 20), (20, ZT - 20), (20, top_z(20) - 1.0), (-20, top_z(-20) - 1.0)],
                          pin_[0] - 5, pin_[1] + 5)])
front = cad.cut(front, box(pin_[0] - 2, pin_[1] + 2, pin_[2] - 2, PY1, ZT - 5, ZT + 1))
_bk = back.cut(box(pin_[0] - 2, pin_[1] + 2, pin_[2] - 2, PY1, ZT - 5, ZT + 1))   # 20 mm3: under
assert _bk.isValid() and len(_bk.Solids) == 1, "the back's post notch"           # cad.cut's volume noise
back = _bk
hut = cad.cut(box(hx0, hx1, hy0, hy1, hz0, hz1), box(hx0 + WALL, hx1 - WALL, hy0 + WALL, hy1 - WALL, hz0 + WALL,
                                                       hz1 + 1))
hut = cad.cut(hut, box(pin_[0], pin_[1], pin_[2], pin_[3], hz0 - 1, hz0 + WALL + 1))
assert TB.ZMin - (hz0 + WALL) <= 0.5, "the sensor must sit on the hut's floor"
hut = cad.fuse_one(hut, post)
holder = [box(TB.XMin + 2, TB.XMax - 2, TB.YMax + 0.25, hy1 - WALL + 0.5, TB.ZMax - 7, TB.ZMax),
          box(hx0 + WALL - 0.5, TB.XMin - 0.3, -6, -2, TB.ZMin + 2, TB.ZMax - 2),
          box(TB.XMax + 0.3, hx1 - WALL + 0.5, -6, -2, TB.ZMin + 2, TB.ZMax - 2)]
# louvres: the front and both sides opened, stacked slats across each
# (tilted SLAT_TILT down-and-out; the straight gap between them lets the
# air - and the check's rays - through)
WZ0, WZ1 = hz0 + WALL + 2.0, hz1 - 3.0
hut = cad.cut(hut, [box(hx0 + WALL + 0.5, hx1 - WALL - 0.5, hy0 - 1, hy0 + WALL + 1, WZ0, WZ1),
                    box(hx0 - 1, hx0 + WALL + 1, hy0 + WALL + 0.5, hy1 - WALL - 0.5, WZ0, WZ1),
                    box(hx1 - WALL - 1, hx1 + 1, hy0 + WALL + 0.5, hy1 - WALL - 0.5, WZ0, WZ1)])
slats = []
n = int((WZ1 - WZ0) / SLAT_PITCH)
for i in range(n):
    zc = WZ0 + SLAT_PITCH * (i + 0.5)
    s = box(hx0 + 0.5, hx1 - 0.5, hy0 - 1.5, hy0 + 3.5, zc - 0.8, zc + 0.8)
    s.rotate(V(0, hy0 + 1.0, zc), V(1, 0, 0), SLAT_TILT)
    slats.append(s)
    for x_, sg in ((hx0 + 1.0, -1), (hx1 - 1.0, 1)):
        t = box(x_ - 2.5, x_ + 2.5, hy0 + 0.5, hy1 - 0.5, zc - 0.8, zc + 0.8)
        t.rotate(V(x_, 0, zc), V(0, 1, 0), -sg * SLAT_TILT)
        slats.append(t)
hut = cad.fuse_one(hut, *slats, *holder)      # the side ribs hang on the side slats
# the roof: a pitched plate with an overhang, drip edges under its eaves,
# a spigot down into the hut's open top
ry0, ry1, ymid = hy0 - ROOF_OVER, hy1 + ROOF_OVER, (hy0 + hy1) / 2
roof = section_x([(ry0, hz1), (ry0, hz1 + 2.0), (ymid, hz1 + 2.0 + RIDGE), (ry1, hz1 + 2.0), (ry1, hz1)],
                 hx0 - ROOF_OVER, hx1 + ROOF_OVER)
roof = cad.fuse_one(roof,
                    box(hx0 + WALL + 0.2, hx1 - WALL - 0.2, hy0 + WALL + 0.2, hy1 - WALL - 0.2, hz1 - 2.0, hz1 + 0.5),
                    box(hx0 - ROOF_OVER, hx1 + ROOF_OVER, ry0, ry0 + 1.2, hz1 - 2.0, hz1 + 0.5),
                    box(hx0 - ROOF_OVER, hx1 + ROOF_OVER, ry1 - 1.2, ry1, hz1 - 2.0, hz1 + 0.5))
tick("hut")

# ------------------------------------------------------------ the lean
# R610: every body-frame part leans back into the world now
front, back, tray, lens, pipe, hut, roof = [T(s_) for s_ in (front, back, tray, lens, pipe, hut, roof)]
keys = {k: T(v) for k, v in keys.items()}
screws = [T(s_) for s_ in screws]

# ------------------------------------------------------------ the foot
# R610: a sculpted graphite foot in the WORLD: its cross-section (y, z) as
# profile_body's side, its rounded plan, turned so its length runs along
# X; the leaning body stands in a pocket of its own bottom, two pins
# up into the back half's floor
foot = cad.profile_body(FOOT_SIDE, [(it[0], (it[1][1], -it[1][0])) if isinstance(it[0], str) else (it[1], -it[0])
                                     for it in FOOT_PLAN], fillet=4.0)
foot.rotate(V(0, 0, 0), V(0, 0, 1), 90)          # body x -> world y, body -y -> world x
ff = Part.Face(cad.spline_wire(FOOT_FRONT, plane="XZ"))
ff.translate(V(0, -60, 0))
foot = foot.common(ff.extrude(V(0, 140, 0)))
foot.fixTolerance(0.01)                          # (the spline body's BOP check, as the body's)
low = T(outer.common(box(SX0 - 5, SX1 + 5, YF - 5, 30, ZS - 1, ZS + 25)))
foot = cad.cut(foot, low)        # R610: the body's own bottom: it rests on the pocket's floor
                                 # (moved copies of the spline body as a 0.2 mm clearance cut
                                 # nothing or everything, MEASURED)
pins_xy = [(20.0, SPLIT_Y + 3.5), (100.0, SPLIT_Y + 3.5)]       # clear of the lip and the back wall
foot = cad.fuse_one(foot, *[T(cyl(1.2, (x, y, ZS - 0.5), (0, 0, 1), WALL + 1.5)) for x, y in pins_xy])
back = cad.cut(back, [T(cyl(1.35, (x, y, ZS - 1), (0, 0, 1), WALL + 3)) for x, y in pins_xy])
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one;
# the face and the back are detailed in the WORLD - the leaning parts)


def W_(p):
    """A body-frame point in the world."""
    return TP.multVec(V(*p))


def Wn(n):
    return TP.Rotation.multVec(V(*n))


def on_piece(shape, at, fn, h=22.0):
    """R610: apply a cutting detail fn (lettering, a grille) to the piece of
    `shape` round world point `at` and cut what it removed from the whole:
    on the big spline shell a letter's 5 mm3 is inside the Shape.Volume
    noise and cad.cut called it "removed nothing" (MEASURED)."""
    lb = Part.makeBox(2 * h, 2 * h, 2 * h, V(at) - V(h, h, h))
    loc = shape.common(lb)
    res = shape.cut(loc.cut(fn(loc)))
    if not res.isValid() or len(res.Solids) != len(shape.Solids):
        raise cad.CadError("on_piece: the detail at %s broke the part" % (V(at),))
    return res


# a sun shade over the display
front = cad.fuse_one(front, T(cad.soften(box(lx0 - BEZEL, lx1 + BEZEL, YF - 2.2, YF + 1.2, lz1 + BEZEL + 0.4,
                                             lz1 + BEZEL + 1.8), 0.5)))
# legends and gauge words
UP = Wn((0, 0, 1))
for m, t in ((key_m, "MODE"), (key_n, "NEXT")):
    kx, _ky, kz = centre(m)
    at = W_((kx, YF, kz + 10.5))
    front = on_piece(front, at, lambda s_: cad.text(s_, t, at, Wn((0, -1, 0)), 3.2, depth=0.4, mode="deboss", up=UP))
for t, at, sz in (("TEMP", W_((ax_, YF, lz0 - 2.0)), 4), ("RH", W_((114.0, YF, 72.0)), 5)):
    front = on_piece(front, at, lambda s_: cad.text(s_, t, at, Wn((0, -1, 0)), sz, depth=0.4, mode="deboss", up=UP))
yf_foot = min(p.y for p in ray(foot, (60, -60, 9.0), (60, 0, 9.0)))
foot = on_piece(foot, (60.0, yf_foot, 9.0),
                lambda s_: cad.text(s_, "ATECH", (60.0, yf_foot, 9.0), (0, -1, 0), 6, depth=0.5, mode="deboss"))
# the back: hex vents low, a wall-hang keyhole high, lettering (on the
# curved, sloped back: each spot measured)
outer_w = T(outer)


def on_back(x, z):
    """The back's surface point at body-frame (x, z), in the world, and its normal."""
    p = W_((x, 40, z))
    d = Wn((0, -1, 0))
    hit = [q for q in ray(outer_w, p, p + d * 80)]
    q = max(hit, key=lambda q_: (q_ - p).dot(d) * -1)
    return q, Wn((0, 1, 0))


c_, n_ = on_back(60, 36)
back = on_piece(back, c_, lambda s_: cad.grille(s_, c_, n_, (50, 10), kind="hex", hole=3.0, pitch=4.5), h=30.0)
kh = W_((60, 0, 84))
key_hole = T(cad.fuse_one(cyl(3.5, (60, back_y(outer, 60, 84) - 3.0, 84), (0, 1, 0), 10),
                          box(58.4, 61.6, back_y(outer, 60, 84) - 3.0, back_y(outer, 60, 84) + 5, 84, 90)))
back = cad.cut(back, key_hole)
c_, n_ = on_back(60, 56)
back = on_piece(back, c_, lambda s_: cad.text(s_, "ATECH", c_, n_, 7, depth=0.5, mode="deboss", up=UP), h=26.0)
# rubber feet in recesses under the foot
feet = []
for x in (fx0 + 13, fx1 - 13):
    for y in (-20.0, 36.0):
        foot = cad.cut(foot, cyl(4.6, (x, y, 0.5), (0, 0, 1), 2.2))
        feet.append(cad.foot(9, 2.7, style="dome", at=(x, y, 2.7)))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour])
    return o


for nm, sh in (("Front", front), ("Back", back), ("Bezel", tray), ("Hut", hut), ("Hut_Roof", roof),
               ("Foot", foot)):
    part(nm, sh, nm)
for nm, sh in (("Lens", lens), ("Alert_Lens", pipe)):
    o = part(nm, sh, nm)
    o.ViewObject.Transparency = cad.transparency("smoked" if nm == "Lens" else "glass")
for nm, sh in keys.items():
    part(nm, sh, "Key")
for i, sh in enumerate(feet):
    part("Rubber_%d" % (i + 1), sh, "Rubber")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
