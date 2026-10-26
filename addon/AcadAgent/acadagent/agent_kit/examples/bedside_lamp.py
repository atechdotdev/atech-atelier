"""Example: "a bedside lamp" - a turned column lamp with a frosted globe.

fork this file for a bedside lamp / tall product (a table lamp, a night
light, a candle, a vase, a bottle, a trophy - anything revolved and taller
than wide); change PARAMETERS and the outlines.
ARCHETYPE: lamp

How it is built (R270):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board UPRIGHT in the column (portrait, modules facing the front -Y);
    the top light CABLED from port 8 straight up the neck into the globe
    (a straight rise: the cleanest ribbon); the touch button CABLED from
    port 7 down into the foot, facing up under a key cap in the foot's top
    (a seated module would face the front wall, 45 mm away); two lights
    seated behind a frosted window in the column; USB-C seated on port 2
    behind a pocket in the right side. The body is ONE closed (radius,
    height) section of lines and tangent arcs (foot, cove, column,
    shoulder, neck) revolved - hollow, fair, no boolean - split low in the
    foot into the fixed Base (it carries a plate behind the board, posts
    under it) and the Shell; three M2.5 screws from below into bosses with
    heat-set insert pockets.
  * STAGE B - details: the parting-line reveal and column bands (in the
    section), a brass gallery ring, vents, lettering, a rubber ring foot.
DETAILS (visible, 27): 1 flared foot; 2 rolled foot edges; 3 cove into the
column; 4 column; 5 rolled shoulder; 6 neck cove; 7 frosted globe; 8 globe
collar; 9 brass gallery ring; 10 frosted light window; 11 parting-line
reveal on the foot; 12-13 two bands round the column; 14 touch key cap in
the foot; 15 raised ring round it; 16 plunger to the button; 17 USB-C
pocket with liner; 18 back vent slots; 19 "ATECH" on the foot; 20 rib onto
the board's spine; 21 a plate with standoffs behind the board; 22 posts
under the board; 23 three countersunk screws from below; 24 heat-set
insert bosses; 25 lip keying shell to base; 26 rubber ring foot in a
recess; 27 the light ribbon hidden inside the neck.
Materials: cream shell, frosted globe and window, brass gallery and key,
graphite base, rubber ring foot, chrome screws.
MEASURED (R270, 2026-10-20): see test_kit_examples_r270 (TIMINGS line).
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
    "Shell", "Globe", "Light_Window", "Gallery", "Badge", "Finial", "Button_Cap", "Ring_Foot",
    "Screw_1", "Screw_2", "Screw_3"],
    "covers": {"Button_Cap": "button_7"}}
REVIEW_CLOSEUPS = ["Globe", "Button_Cap", "Light_Window"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# R270: the silhouette is these numbers - foot, cove, column, shoulder,
# neck, globe. Heights in mm from the desk; radii from the lamp's axis.
WALL = 2.0
FOOT = 1.5                     # the rubber ring foot under the base
Z0 = 20.0                      # board bottom (the button and its ribbon fit under it)
R_FOOT, H_FOOT = 60.0, 19.0    # foot radius and top
RF_BOT, RF_EDGE = 2.5, 4.0     # foot bottom / top edge rolls
COVE = 8.0                     # concave cove from the foot into the column
R_COL = 35.0                   # column radius (board corners need >= 33 inside)
Z_SH, R_SH = 150.0, 10.0       # shoulder height, shoulder roll
R_NECK, Z_NECK = 13.0, 172.0   # neck radius and its top (the ribbon rises inside)
GAL = (160.0, 162.0, 17.5)     # brass gallery ring: z0, z1, outer radius
ZG, RG, WG = 215.0, 52.0, 1.8  # globe centre, radius, wall
SPLIT = 8.0                    # base / shell seam in the foot's side
REVEAL_Z = SPLIT + 2.0         # parting-line reveal groove just above it
BANDS = (40.0, 136.0)          # decorative grooves round the column
WINDOW = (92.0, 128.0)         # frosted light window, z range (lights at 100..120)
TOP_LIGHT_Z = 185.0            # the cabled light's centre (inside the globe)
BUTTON_R = 46.0                # touch key distance from the axis, at the front
SCREW = "M2.5"
COLOURS = {"Base": "graphite", "Shell": "cream", "Globe": "frosted", "Light_Window": "frosted",
           "Gallery": "brass", "Button_Cap": "brass", "Ring_Foot": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
UPRIGHT_FRONT = Rotation(Vector(0, 0, 1), 180)
board = ap.board_object(doc)


def place_board(rot, x0=0.0, y0=None, z0=0.0):
    board.Placement = Placement(Vector(), rot)
    bb = ap.bbox(board)
    board.Placement = Placement(Vector(x0 - bb.XMin, 0 if y0 is None else y0 - bb.YMin,
                                       z0 - bb.ZMin), rot)


place_board(UPRIGHT_FRONT, 0, None, Z0)          # x 0..60, z 20..140, modules face -Y
BB = ap.bbox(board)
AX, AY = 30.0, -4.0                             # the lamp's axis: the stack's middle
usb = ap.seat(doc, "usbc", 2)                    # right side, mouth +X
glow_r = ap.seat(doc, "light", 5)                # behind the window
glow_l = ap.seat(doc, "light", 13)
top_light, top_rib = ap.cable(doc, "light", 8, ap.module_placement(
    "light", (AX, -4.8, TOP_LIGHT_Z), face="-Y", cable="-Z"))      # straight up the neck
btn, btn_rib = ap.cable(doc, "button", 7, ap.module_placement(
    "button", (AX, AY - BUTTON_R, 9.5), face="+Z", cable="+Y"))    # in the foot, facing up
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def annulus(r0, r1, z0, z1, c=(AX, AY)):
    return cad.cut(cyl(r1, (c[0], c[1], z0), z1 - z0), cyl(r0, (c[0], c[1], z0 - 1), z1 - z0 + 2))


def arc(c, r, a0, a1):
    """('arc', mid, end) of the circle (c, r) from angle a0 to a1 (deg)."""
    am, a1 = math.radians((a0 + a1) / 2), math.radians(a1)
    return ("arc", (c[0] + r * math.cos(am), c[1] + r * math.sin(am)),
            (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1)))


def notch(r, z, w=0.8, d=0.6):
    """A groove notched into a vertical outer wall at radius r (the section
    goes down the wall: top edge first)."""
    return [(r, z + w / 2), (r - d, z + w / 2), (r - d, z - w / 2), (r, z - w / 2)]


# the body section: outer skin up from the bottom centre, then back down
# the inside WALL in (concentric arcs) - lines and arcs only, so fair
cf = (R_FOOT - RF_BOT, FOOT + RF_BOT)                 # foot bottom roll centre
ce = (R_FOOT - RF_EDGE, H_FOOT - RF_EDGE)             # foot top roll centre
cc = (R_COL + COVE, H_FOOT + COVE)                    # cove centre
cs = (R_COL - R_SH, Z_SH - R_SH)                      # shoulder centre
cn = (R_NECK + 4.0, Z_SH + 4.0)                       # neck cove centre
section = [
    (0, FOOT), (cf[0], FOOT), arc(cf, RF_BOT, -90, 0),
    *reversed(notch(R_FOOT, REVEAL_Z, 1.0, 0.7)),
    (R_FOOT, ce[1]), arc(ce, RF_EDGE, 0, 90),
    (cc[0], H_FOOT), arc(cc, COVE, -90, -180),
    *reversed(notch(R_COL, BANDS[0])), *reversed(notch(R_COL, BANDS[1])),
    (R_COL, cs[1]), arc(cs, R_SH, 0, 90),
    (cn[0], Z_SH), arc(cn, 4.0, -90, -180),
    (R_NECK, Z_NECK), (R_NECK - WALL, Z_NECK),                       # the open neck rim
    (R_NECK - WALL, cn[1]), arc(cn, 4.0 + WALL, -180, -90),
    (cs[0], Z_SH - WALL), arc(cs, R_SH - WALL, 90, 0),
    (R_COL - WALL, cc[1]), arc(cc, COVE + WALL, -180, -90),
    (ce[0], H_FOOT - WALL), arc(ce, RF_EDGE - WALL, 90, 0),
    (R_FOOT - WALL, cf[1]), arc(cf, RF_BOT - WALL, 0, -90),
    (0, FOOT + WALL),
]
body = cad.revolve_profile(section, at=(AX, AY, 0))
tick("body")
base, shell = cad.split(body, "Z", at=SPLIT, lip=1.2)
tick("split")

# the fixed base holds the board: a plate behind it (standoffs 0.1 mm off
# its back) and two posts under its bottom edge, clear of port 7's ribbon
PLATE_Y = BB.YMax + 0.1
plate = box(8, 52, PLATE_Y + 1.0, PLATE_Y + 6.0, FOOT + 1.5, BB.ZMax - 4)
pads = [box(x, x + 6, PLATE_Y, PLATE_Y + 1.5, z, z + 8) for x in (9, 45) for z in (40, 80, 120)]
posts = [box(x, x + 6, 0.3, PLATE_Y + 1.5, FOOT + 1.5, Z0 - 0.1) for x in (3, 51)]
base = cad.fuse_one(base, plate, *pads, *posts)
# R500: the cabled modules are HELD, not hung on their ribbons - two pads
# on the base floor 0.2 mm under the touch button (the key cap's plunger
# is its other side), and two ribs rising out of the neck rim 0.2 mm off
# either side of the globe light (its face, -Y, and its ribbon, -Z, clear)
bk = ap.bbox(btn)
base = cad.fuse_one(base, *[box(x, x + 4, bk.YMin + 4, bk.YMax - 4, FOOT + WALL - 0.5, bk.ZMin - 0.2)
                            for x in (bk.XMin + 3, bk.XMax - 7)])
tl = ap.bbox(top_light)
light_ribs = [box(x0, x1, tl.YMin + 2, tl.YMax - 2, Z_NECK - 3.0, tl.ZMax - 4)
              for x0, x1 in ((tl.XMin - 1.7, tl.XMin - 0.2), (tl.XMax + 0.2, tl.XMax + 1.7))]
# board retention rib from the front wall onto the spine (0.2 mm off it)
SPINE_Y = BB.YMin                                 # the spine's face (-4.5)
shell = cad.fuse_one(shell, box(AX - 1, AX + 1, AY - R_COL + 1.0, SPINE_Y - 0.2, 44, 66))   # under the badge
shell = cad.fuse_one(shell, *light_ribs)
# three M2.5 screws up through the floor into bosses hanging from the foot
# top, each with a heat-set insert pocket (1.4 d + 0.1) in a sleeve
INSERT_D = {"M2": 3.2, "M2.5": 3.6, "M3": 4.3}[SCREW]
screws = []
for ang in (90, 210, 330):
    x, y = AX + 47 * math.cos(math.radians(ang)), AY + 47 * math.sin(math.radians(ang))
    shell = cad.screw_boss(shell, (x, y, FOOT + 2.1), axis="+Z", size=SCREW, ribs=0)
    shell = cad.fuse_one(shell, cyl(INSERT_D / 2 + 1.2, (x, y, FOOT + 2.1), 10.0))
    shell = cad.cut(shell, cyl(INSERT_D / 2, (x, y, FOOT + 2.0), 9.0))
    base = cad.countersink(base, (x, y, FOOT), "+Z", 2.9, 5.6, 90.0)
    screws.append(cad.screw("csk_phillips", SCREW, 10, at=(x, y, FOOT), axis="+Z"))
tick("base + screws")

# the frosted window over the two seated lights: an insert cut out of the
# column's front wall (it fills its opening exactly)
# R270: a SECTOR cutter (radial sides: no knife-edge sliver where a box
# side crosses the curved wall obliquely), 70 deg either side of the front
# so every ray from both lights gets out; the bar is filled to a FLAT back
# 3 mm in front of the lights - a solid frosted light bar (a curved panel
# alone reads to ./check as a 66 mm open clip channel)
WIN_DEG = 70.0
q = math.radians(WIN_DEG)
fan = Part.Face(Part.makePolygon([V(AX, AY, 0), V(AX - 60 * math.sin(q), AY - 60 * math.cos(q), 0),
                                  V(AX, AY - 70, 0), V(AX + 60 * math.sin(q), AY - 60 * math.cos(q), 0),
                                  V(AX, AY, 0)]))
fan.translate(V(0, 0, WINDOW[0]))
win_cut = fan.extrude(V(0, 0, WINDOW[1] - WINDOW[0]))
window = shell.common(win_cut)
shell = cad.cut(shell, win_cut)
LIGHT_FACE_Y = min(ap.bbox(glow_r).YMin, ap.bbox(glow_l).YMin)
fill = win_cut.common(cyl(R_COL - WALL, (AX, AY, WINDOW[0] - 1), WINDOW[1] - WINDOW[0] + 2)) \
    .common(box(-50, 110, AY - 60, LIGHT_FACE_Y - 3.0, WINDOW[0] - 1, WINDOW[1] + 1))
window = cad.fuse_one(window, fill)
# the touch key in the foot top: cap, flange 0.1 mm under the wall, a
# plunger to 0.16 mm over the button module's cap
bb_ = ap.bbox(btn)
bx, by = (bb_.XMin + bb_.XMax) / 2, (bb_.YMin + bb_.YMax) / 2
base_z = H_FOOT - WALL - 0.9
cap = cad.button_cap(14, (H_FOOT + 1.6) - base_z, dome=0.8, flange=1.5, at=(bx, by, base_z), axis="+Z")
shell = cad.opening_for(shell, cap, clearance=0.25, chamfer=0.4, axis="+Z")
cap = cad.fuse_one(cap, cyl(3.0, (bx, by, bb_.ZMax + 0.16), base_z - (bb_.ZMax + 0.16) + 0.5))
# USB-C on the right: a pocket brings the wall to 0.25 mm off the mouth
ub = ap.bbox(usb)
uy, uz = -5.9, (ub.ZMin + ub.ZMax) / 2


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


pocket = xprism(uy - 6.0, uy + 6.0, uz - 5.0, uz + 5.0, ub.XMax + 1.3, AX + R_COL + 5, 3)
liner = cad.cut(xprism(uy - 8.0, uy + 8.0, uz - 7.0, uz + 7.0, ub.XMax + 0.25, AX + R_COL - 1.0, 4), pocket)
shell = cad.fuse_one(cad.cut(shell, pocket), liner)
shell = cad.socket_opening(shell, usb, margin=1.5)
# the globe: one revolved section (collar + sphere), resting on the gallery
RC_I, RC_O = R_NECK + 0.3, R_NECK + 3.0
z_o = ZG - math.sqrt(RG ** 2 - RC_O ** 2)
z_i = ZG - math.sqrt((RG - WG) ** 2 - RC_I ** 2)
a_o = math.degrees(math.atan2(z_o - ZG, RC_O))
a_i = math.degrees(math.atan2(z_i - ZG, RC_I))
globe = cad.revolve_profile([
    (RC_I, GAL[1]), (RC_O, GAL[1]), (RC_O, z_o), arc((0, ZG), RG, a_o, 90),
    (0, ZG + RG - WG), arc((0, ZG), RG - WG, 90, a_i)], at=(AX, AY, 0))
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one;
# the reveal and the column bands are already in the section)
# brass gallery ring: an insert in a 1 mm groove round the neck
gallery = annulus(R_NECK - 1.0, GAL[2], GAL[0], GAL[1])
shell = cad.cut(shell, gallery)
# a raised ring round the touch key, vents on the back, lettering
shell = cad.fuse_one(shell, annulus(8.6, 10.2, H_FOOT - 0.5, H_FOOT + 0.6, (bx, by)))
shell = cad.grille(shell, (AX, AY + R_COL, 70), (0, 1, 0), (30, 40), kind="slot", hole=2.4, pitch=5.0)
shell = cad.text(shell, "ATECH", (AX, AY + R_COL + 13, H_FOOT), (0, 0, 1), 6, depth=0.5, mode="deboss",
                 up=(0, -1, 0))
# a brass badge inset in the column front, lettered
badge_cut = cad.rounded_box(34, 15, 11, 3, at=(AX - 17, AY - R_COL - 4, 70), edges="y")   # through the wall: no thin skin
badge = shell.common(badge_cut)
shell = cad.cut(shell, badge_cut)
badge = cad.text(badge, "ATECH", (AX, AY - R_COL, 75.5), (0, -1, 0), 6, depth=0.4, mode="deboss")   # thin raised strokes read as a 0.6 mm wall
# a brass finial on the globe's pole, its peg through a hole in the glass
globe = cad.cut(globe, [cyl(2.2, (AX, AY, ZG + RG - WG - 1), WG + 2),
                        cyl(4.0, (AX, AY, ZG + RG - 0.6), 3.0)])         # hole + spot face
finial = cad.fuse_one(Part.makeSphere(5.0, V(AX, AY, ZG + RG + 4.5)),
                      cyl(4.0, (AX, AY, ZG + RG - 0.6), 2.5),
                      cyl(2.05, (AX, AY, ZG + RG - WG - 1.5), WG + 2.0))
# a rubber ring foot in a 1 mm recess under the base
base = cad.cut(base, annulus(51.0, 55.5, FOOT - 1, FOOT + 1.0))
ring_foot = annulus(51.15, 55.35, 0.0, FOOT + 1.0)
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o


o = part("Base", base)
o.ViewObject.ShapeColor = cad.color(COLOURS["Base"])
o = part("Shell", shell)
o.ViewObject.ShapeColor = cad.color(COLOURS["Shell"])
o = part("Globe", globe)
o.ViewObject.ShapeColor = cad.color(COLOURS["Globe"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Globe"])
o = part("Light_Window", window)
o.ViewObject.ShapeColor = cad.color(COLOURS["Light_Window"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Light_Window"])
o = part("Gallery", gallery)
o.ViewObject.ShapeColor = cad.color(COLOURS["Gallery"])
o = part("Button_Cap", cap)
o.ViewObject.ShapeColor = cad.color(COLOURS["Button_Cap"])
o = part("Badge", badge)
o.ViewObject.ShapeColor = cad.color(COLOURS["Gallery"])
o = part("Finial", finial)
o.ViewObject.ShapeColor = cad.color(COLOURS["Gallery"])
o = part("Ring_Foot", ring_foot)
o.ViewObject.ShapeColor = cad.color(COLOURS["Ring_Foot"])
for i, sh in enumerate(screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
print("TOTAL %.1f s" % (time.time() - T0))
