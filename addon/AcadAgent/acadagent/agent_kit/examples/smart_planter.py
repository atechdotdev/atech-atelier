"""Example: "a smart desk planter" - a soft-backed pot with a flat instrument face, an inner pot over a drip tray.

fork this file for a planter / pot (a smart pot, a herb garden, a
self-watering planter, a cachepot or vase with a display - anything that
holds soil or water behind an instrument
face); change PARAMETERS and the outlines.
ARCHETYPE: planter

How it is built (R700):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board LANDSCAPE_UP in a shallow electronics bay behind the flat front
    face (modules facing the front, -Y): the screen (10, 11) behind a
    smoked lens in a recessed black bezel tray (moisture / temperature
    readout), the glow light (14) behind a frosted light pipe (the status
    glow), temp_humidity (6) behind a round-hole vent with a second slot
    vent under it (a chimney: cool air in low, out past the sensor), USB-C
    (7) in a pocket in the left side. The body is ONE plan outline (a
    crisp front, CORNER-rounded back corners) and one side outline
    (cad.profile_body, soft EDGE fillet) hollowed with its own sharp core,
    a partition wall closing the bay from the soil cavity behind it, the
    cavity opened at the top; split low into the fixed Base (it carries
    the board: posts under it, a plate behind it) and the Shell, four M2.5
    screws from below through Base pillars into insert bosses in the bay.
    Behind the partition: a Drip_Tray on the Base floor, the Pot_Liner
    standing on four feet in it (drainage holes in its floor), the Soil.
  * STAGE B - details: the parting-line reveal and a collar groove under
    the rim, the liner's rolled rim and the tray's finger notch, drainage
    holes, lettering, rubber feet.
DETAILS (visible, 24 of 30): 1 flat instrument face with crisp corners;
2 soft rounded back; 3 soft EDGE fillet round the top and the base;
4 smoked lens over the screen; 5 recessed black bezel tray; 6 the mask
window over the screen's active area; 7 frosted glow light pipe with a
flange; 8 round-hole sensor vent; 9 slot vent under it; 10 USB-C pocket
with liner in the left side; 11 parting-line reveal over the base;
12 collar groove under the rim; 13 graphite base; 14 open soil cavity;
15 terracotta inner pot; 16 its rolled rim; 17 the soil; 18 drip tray
under the pot; 19 the tray's finger notch; 20 "ATECH" under the screen;
21 "AIR" over the sensor vent; 22 four countersunk screws under the base;
23 four rubber feet; 24 drainage holes in the pot floor. Inside:
25 partition wall between bay and soil; 26 insert bosses with heat-set
pockets; 27 base pillars under them; 28 board posts and a plate with pads
behind it; 29 a rib onto the board's spine; 30 the pot's four feet.
Materials: warm ceramic-white shell, graphite base, terracotta pot, soil,
sage drip tray, smoked lens, black bezel, frosted glow, rubber feet,
chrome screws.
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
    "Shell", "Bezel", "Lens", "Glow_Lens", "Drip_Tray", "Pot_Liner", "Soil",
    "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4", "Screw_1", "Screw_2", "Screw_3", "Screw_4"]}
REVIEW_CLOSEUPS = ["Lens", "Pot_Liner", "Glow_Lens"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them (the hardware frame below is
# the board's own: never move it with a knob).
WIDTH = 160.0      # RESTYLE 136..184 width: across the face (x), centred on the board
DEPTH = 135.0      # RESTYLE 114..156 length: front face to back (y)
HEIGHT = 120.0     # RESTYLE 102..138 height: desk to rim (z)
CORNER = 24.0      # RESTYLE 20..28 radius: the back plan corners (the front stays crisp)
WALL = 2.4         # RESTYLE 2.0..2.8 wall
# end RESTYLE
# Frame: x across, y front (-) to back, z up; the desk at z = 0.
# The hardware frame (fixed: the board decides it):
ZB = 30.0                            # board bottom (the bay's floor and the sensor's corridor under it)
Y_IN = -13.0                         # the front wall's inner face (0.4 mm in front of the modules' faces)
FOOT = 1.5                           # rubber feet under the base
EDGE = 3.0                           # the soft fillet round the top and the base
R_FRONT = 4.0                        # the front's plan corners: crisp (the USB-C liner needs the side flat)
SPLIT = FOOT + WALL + 3.6            # base / shell seam (lip top < the sensor's corridor at z 10.5)
X0, X1 = 60.0 - WIDTH / 2, 60.0 + WIDTH / 2
YF = Y_IN - WALL                     # the front face
YB = YF + DEPTH                      # the back
ZT = HEIGHT                          # the rim
RECESS, BEZEL, LENS_R = 1.0, 4.0, 3.0
SCREEN_WIN = (28.0, 16.0)            # mask window over the screen (active area 25.6 x 13.5)
TRAY_H, TRAY_GAP, TRAY_T = 16.0, 2.0, 1.6    # drip tray height, gap to the walls, wall
POT_FEET, POT_WALL = 5.0, 1.8        # the pot stands 5 mm over the tray floor (a reservoir)
SOIL_DOWN = 16.0                     # soil level under the rim
SCREW = "M2.5"
COLOURS = {"Base": "graphite", "Shell": "#ece6da", "Bezel": "matte_black", "Lens": "smoked",
           "Glow_Lens": "frosted", "Drip_Tray": "#9fb59a", "Pot_Liner": "#c46a43", "Soil": "#4a3426",
           "Rubber": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
LANDSCAPE_UP = Rotation(Vector(0, 0, 1), 180).multiply(Rotation(Vector(0, 1, 0), -90))
board = ap.board_object(doc)
board.Placement = Placement(Vector(), LANDSCAPE_UP)
_b = ap.bbox(board)
board.Placement = Placement(Vector(-_b.XMin, 0, ZB - _b.ZMin), LANDSCAPE_UP)   # x 0..120, z 30..90
BB = ap.bbox(board)
scr = ap.seat(doc, "screen", (10, 11))         # top row, left of centre: the readout
glow = ap.seat(doc, "light", 14)               # top row, right: the status glow
th = ap.seat(doc, "temp_humidity", 6)          # bottom row, right: under the glow, away from USB-C
usb = ap.seat(doc, "usbc", 7)                  # left end, mouth -X
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
    return (corner((x0 + rf, y0 + rf), rf, 180, 270, 2) + corner((x1 - rf, y0 + rf), rf, 270, 360, 2)
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


def tub(pts, z0, z1, t, floor):
    """An open-top vessel: the plan prism hollowed to wall t, floor `floor`."""
    outer = zprism(pts, z0, z1)
    inner = Part.Face(Part.makePolygon([V(x, y, z0) for x, y in pts + pts[:1]])).makeOffset2D(-t, join=0)
    inner.translate(V(0, 0, floor))
    return cad.cut(outer, inner.extrude(V(0, 0, z1 - z0)))


# ------------------------------------------------------------ the body
PLAN = plan_pts(X0, X1, YF, YB, R_FRONT, CORNER)
SIDE = [(X0, FOOT), (X1, FOOT), (X1, ZT), (X0, ZT)]
body = cad.profile_body(SIDE, PLAN, spline=False, fillet=(EDGE, EDGE))
# the core keeps SHARP inner edges (a filleted core's concave rounds read
# to ./check as open clip channels - the handheld's lesson)
core = cad.profile_body(SIDE, PLAN, spline=False, fillet=None, inset=WALL)
hull = cad.cut(body, core)
# the parting-line reveal goes in BEFORE the split (it needs a closed ring)
hull = cad.groove_ring(hull, "Z", SPLIT + 2.5, w=0.8, depth=0.6)
tick("body")
base, shell = cad.split(hull, "Z", at=SPLIT, lip=1.2)
tick("split")
XI0, XI1 = X0 + WALL, X1 - WALL                 # the inner side walls
YI1 = YB - WALL                                 # the inner back wall
FLOOR = FOOT + WALL                             # the base floor's top

# the fixed base holds the board: posts under its bottom edge (under the
# free ports 1-5, clear of the sensor's corridor), a plate behind it with
# pads 0.1 mm off its back
PLATE_Y = BB.YMax + 0.1
posts = [box(x, x + 6, 0.3, PLATE_Y + 1.5, FLOOR - 0.5, BB.ZMin - 0.1) for x in (4.0, 62.0)]
plate = box(10, 110, PLATE_Y + 1.0, PLATE_Y + 5.0, FLOOR - 0.5, BB.ZMax - 4)
pads = [box(x, x + 6, PLATE_Y, PLATE_Y + 1.5, z, z + 8) for x in (14, 57, 100) for z in (40, 72)]
base = cad.fuse_one(base, plate, *pads, *posts)
# the partition: a wall across the cavity behind the plate, from above the
# lip to the top wall - the bay in front, the soil behind
PART_Y0 = PLATE_Y + 5.5
PART_Y1 = PART_Y0 + WALL
shell = cad.fuse_one(shell, box(XI0 - 0.5, XI1 + 0.5, PART_Y0, PART_Y1, SPLIT + 2.0, ZT - WALL + 0.5).common(
    zprism(PLAN, 0, ZT)))
# open the soil cavity: the core's own outline behind the partition, up
# through the top wall (straight inner walls to the rim)
lift = core.copy()
lift.translate(V(0, 0, WALL + 2.0))
shell = cad.cut(shell, lift.common(box(X0 - 5, X1 + 5, PART_Y1, YB + 5, ZT - WALL - 1.0, ZT + 5)))
# board retention: a rib from the front wall onto the spine (0.2 mm off)
shell = cad.fuse_one(shell, box(58, 62, Y_IN - 0.5, BB.YMin - 0.2, 52, 64))
tick("base + partition")

# four M2.5 screws from below, in the bay's two ends: a pillar on the base
# floor up to 0.1 mm under an insert boss hung on the shell's side wall
# (a heat-set insert pocket 3.6 in a sleeve, R270)
INSERT_D = {"M2": 3.2, "M2.5": 3.6, "M3": 4.3}[SCREW]
BOSS_Z0 = SPLIT + 2.0                           # over the lip's groove
SCREWS = [(XI0 + 3.2, -8.5), (XI0 + 3.2, 1.5), (XI1 - 3.2, -8.5), (XI1 - 3.2, 1.5)]
screws, sleeves, bridges, pockets, pillars = [], [], [], [], []
for x, y in SCREWS:
    wall_x = XI0 - 0.5 if x < 60 else XI1 + 0.5
    sleeves.append(cyl(INSERT_D / 2 + 1.2, (x, y, BOSS_Z0), 12.0))
    bridges.append(box(min(wall_x, x), max(wall_x, x), y - 3.0, y + 3.0, BOSS_Z0, BOSS_Z0 + 12.0))
    pockets.append(cyl(INSERT_D / 2, (x, y, BOSS_Z0 - 1.0), 10.5))
    pillars.append(cyl(INSERT_D / 2 + 1.2, (x, y, FLOOR - 0.5), BOSS_Z0 - 0.1 - (FLOOR - 0.5)))
    screws.append(cad.screw("csk_phillips", SCREW, int(BOSS_Z0 + 6.0 - FOOT), at=(x, y, FOOT), axis="+Z"))
shell = cad.cut(cad.fuse_one(shell, *sleeves, *bridges), pockets)
base = cad.fuse_one(base, *pillars)
for x, y in SCREWS:
    base = cad.countersink(base, (x, y, FOOT), "+Z", 2.9, 5.6, 90.0)
tick("screws")

# ------------------------------------------------------------ the face
# the readout: a black bezel tray set RECESS back in its opening, holding
# the smoked lens, its back the mask with the screen window (0.36 mm off
# the screen)
sx, _sy, sz = centre(scr)
LENS = (sx - 18.0, sx + 18.0, sz - 11.0, sz + 11.0)     # its back lip clears the USB-C module
lx0, lx1, lz0, lz1 = LENS
shell = cad.cut(shell, yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, YF - 6, Y_IN + 1))
yt0, yt1 = YF + RECESS, Y_IN + 3.0
tray = cad.fuse_one(yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, yt0, Y_IN + 1),
                    yprism(lx0 - 2, lx1 + 2, lz0 - 2, lz1 + 2, LENS_R + 2, Y_IN + 0.5, yt1))
y_lens1 = Y_IN + 1.7
tray = cad.cut(tray, yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 - 1, y_lens1))
lens = yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 + 0.6, y_lens1 - 0.3)          # 0.3 mm air before the mask
tray = cad.cut(tray, cad.rounded_box(SCREEN_WIN[0], 10, SCREEN_WIN[1], 1.5,
                                     at=(sx - SCREEN_WIN[0] / 2, yt1 - 5, sz - SCREEN_WIN[1] / 2), edges="y"))
# the glow: a frosted light pipe from 0.4 mm off the LEDs to 0.8 mm proud,
# a flange behind the wall
gx, _gy, gz = centre(glow)
gb = ap.bbox(glow)
pipe = cad.lens(17.0, (gb.YMin - 0.4) - (YF - 0.8), dome=0.8, at=(gx, gb.YMin - 0.4, gz), axis="-Y")
shell = cad.opening_for(shell, pipe, clearance=0.2, chamfer=0.0, axis="-Y")
pipe = cad.fuse_one(pipe, cyl(10.0, (gx, Y_IN + 0.9, gz), 0.8, (0, -1, 0)))
# the sensor: a round-hole vent over its 4.5 mm port, a slot vent under it
tx, _ty, tz = centre(th)
shell = cad.grille(shell, (tx, YF, tz), (0, -1, 0), (14, 14), kind="round", hole=1.8, pitch=3.0)
shell = cad.grille(shell, (tx, YF, SPLIT + 10.5), (0, -1, 0), (24, 9), kind="slot", hole=1.8, pitch=4.0)
# USB-C on the left side: a pocket brings the wall to 0.25 mm off the
# socket mouth, then the measured opening
ub = ap.bbox(usb)
uy, uz = -5.9, (ub.ZMin + ub.ZMax) / 2
pocket = xprism(uy - 4.5, uy + 4.5, uz - 6.5, uz + 6.5, X0 - 5, ub.XMin - 1.3, 3)
# (the liner runs down into the front wall: no thin skin under the pocket)
liner = cad.cut(xprism(Y_IN - 0.4, uy + 6.5, uz - 8.0, uz + 8.0, ub.XMin - 0.25, XI0 - 0.5, 3.0), pocket)
shell = cad.fuse_one(cad.cut(shell, pocket), liner)
shell = cad.socket_opening(shell, usb, margin=1.5)
tick("face")

# ------------------------------------------------------------ tray, pot, soil
# the soil cavity's plan, inset: the tray TRAY_GAP off every wall, the pot
# standing on four feet inside the tray, the soil in the pot
cav = (XI0, XI1, PART_Y1, YI1)
tp = plan_pts(cav[0] + TRAY_GAP, cav[1] - TRAY_GAP, cav[2] + TRAY_GAP, cav[3] - TRAY_GAP, 3.0,
              CORNER - WALL - TRAY_GAP)
drip = tub(tp, FLOOR, FLOOR + TRAY_H, TRAY_T, TRAY_T)
# two locating pegs under the tray drop into holes through the base floor
# (0.15 mm clear): it cannot slide or lift off sideways
tcx, tcy = (XI0 + XI1) / 2, (PART_Y1 + YI1) / 2
PEGS = [(tcx - 0.3 * (XI1 - XI0), tcy), (tcx + 0.3 * (XI1 - XI0), tcy)]
drip = cad.fuse_one(drip, *[cyl(2.5, (x, y, FLOOR - 1.5), 2.0) for x, y in PEGS])
base = cad.cut(base, [cyl(2.65, (x, y, FOOT - 1), WALL + 2) for x, y in PEGS])
g = TRAY_GAP + TRAY_T + 1.0
pp = plan_pts(cav[0] + g, cav[1] - g, cav[2] + g, cav[3] - g, 2.0, CORNER - WALL - g)
POT_Z0 = FLOOR + TRAY_T + POT_FEET
pot = tub(pp, POT_Z0, ZT - 4.0, POT_WALL, 2.0)
pcx, pcy = (cav[0] + cav[1]) / 2, (cav[2] + cav[3]) / 2
pw, pd = (cav[1] - cav[0]) - 2 * g, (cav[3] - cav[2]) - 2 * g
pot_feet = [cyl(4.0, (pcx + sx_ * (pw / 2 - 9), pcy + sy_ * (pd / 2 - 9), FLOOR + TRAY_T), POT_FEET + 1.0)
            for sx_ in (-1, 1) for sy_ in (-1, 1)]
pot = cad.fuse_one(pot, *pot_feet)
sp = Part.Face(Part.makePolygon([V(x, y, 0) for x, y in pp + pp[:1]])).makeOffset2D(-POT_WALL, join=0)
sp.translate(V(0, 0, POT_Z0 + 2.0))
soil = sp.extrude(V(0, 0, (ZT - SOIL_DOWN) - (POT_Z0 + 2.0)))
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# a collar groove under the rim, round the sides and back (clear of the
# readout's bezel at a low HEIGHT)
if ZT - 12.0 > lz1 + BEZEL + 4.0:
    shell = cad.groove_ring(shell, "Z", ZT - 12.0, w=0.8, depth=0.6)
# the pot: a rolled rim band round its top, drainage holes in its floor
rim = cad.cut(zprism(plan_pts(cav[0] + g - 1.5, cav[1] - g + 1.5, cav[2] + g - 1.5, cav[3] - g + 1.5, 3.5,
                              CORNER - WALL - g + 1.5), ZT - 10.0, ZT - 4.0),
              zprism(pp, ZT - 11.0, ZT - 3.0))
pot = cad.fuse_one(pot, cad.soften(rim, 0.6))
pot = cad.grille(pot, (pcx, pcy, POT_Z0), (0, 0, -1), (pw - 34, pd - 34), kind="round", hole=4.0, pitch=13.0)
# the tray: a finger notch in its back rim
drip = cad.cut(drip, cad.rounded_box(24, 8, 8, 3.5, at=(pcx - 12, cav[3] - TRAY_GAP - 5, FLOOR + TRAY_H - 6),
                                     edges="y"))
# lettering: ATECH under the readout, AIR over the sensor vent
shell = cad.text(shell, "ATECH", (sx, YF, lz0 - BEZEL - 8.0), (0, -1, 0), 6, depth=0.5, mode="deboss")
shell = cad.text(shell, "AIR", (tx, YF, tz + 12.0), (0, -1, 0), 4, depth=0.4, mode="deboss")
# rubber feet in recesses under the base
feet = []
for x in (X0 + 18, X1 - 18):
    for y in (YF + 32, YB - 20):
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


for nm, sh in (("Base", base), ("Shell", shell), ("Bezel", tray), ("Lens", lens), ("Glow_Lens", pipe),
               ("Drip_Tray", drip), ("Pot_Liner", pot), ("Soil", soil)):
    part(nm, sh)
for i, sh in enumerate(feet):
    part("Rubber_%d" % (i + 1), sh, "Rubber")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
