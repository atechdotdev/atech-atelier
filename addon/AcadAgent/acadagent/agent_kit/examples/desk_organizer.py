"""Example: "a smart desk organizer" - a display block, three pen cups and a phone dock on one tray.

fork this file for a desk organizer / desk tidy (a pen holder, a desk caddy,
a tidy tray, a phone dock with storage, a stationery stand - a low footprint
with cups, slots and a small display); change PARAMETERS and the outlines.
ARCHETYPE: organizer

How it is built (R720):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board LANDSCAPE_UP in the front display block (modules facing the
    front, -Y): the screen (10, 11) behind a smoked lens in a recessed
    black bezel tray (its back is the mask with the screen window, for the
    time and the temperature), temp_humidity (14) in a sealed chamber
    behind a slot vent (away from the board's heat), the button (6) under
    a key cap below it, USB-C (7) in a pocket with a liner in the left
    side. The body is ONE tray: a footprint (a rounded rectangle) as the
    plinth, the display block on its front left, three pen cups of
    different heights behind the block and a phone dock on the right (a
    side section along X: a low front lip, a tilted phone slot, a tall
    back rest) - fused, hollowed as ONE core open below (the plinth, the
    block round the electronics, the dock with a wall kept round its slot
    and its cable tunnel) and split low into the fixed Base (it carries
    posts under the board and a plate behind it) and the Shell; five
    M2.5 screws from below into bosses hanging from the shell (the
    plinth's skin, the slot's and the tunnel's floors). The phone slot
    leans back SLOT_TILT degrees, its floor grooved for the cable, the
    groove a tunnel out of the back. The board stands 24 mm up: the
    bottom-row button slides 20 mm down out of its port, over the Base.
  * STAGE B - details: the parting-line reveal, the raised ring round the
    key, lettering, hex vents under the block, soft rims on the cups,
    rubber feet.
DETAILS (visible, 24 of 30): 1 a tray footprint with 16 mm corners; 2 the
display block, soft 4 mm top edges; 3 smoked lens; 4 recessed black bezel
round it; 5 black mask with the screen window; 6 slot vent over the
sensor; 7 key cap with flange and plunger; 8 raised ring round the key;
9 USB-C pocket with liner in the left side; 10 "ATECH" on the block;
11-13 three pen cups (0.72 / 1.0 / 0.86 of CUP_H) with soft rims; 14 the
phone dock's low front lip; 15 the phone slot, leaning back; 16 the tall
back rest; 17 the cable groove in the slot floor; 18 the cable tunnel's
exit in the back; 19 the parting-line reveal round the plinth; 20 the
graphite base under it; 21 hex vents under the block; 22 five countersunk
screws from below; 23-24 four rubber feet. Inside: 25 the sensor chamber
(a sleeve from the vent to 0.3 mm off the sensor); 26 rib onto the board's
spine; 27 posts under the board; 28 a plate with pads behind it; 29 screw
bosses under the plinth's skin; 30 the base / shell lip.
Materials: warm-white shell, graphite base, smoked lens, black bezel,
coral key, rubber feet, chrome screws.
MEASURED (R720, 2026-10-26): see test_kit_examples_r270 (TIMINGS line).
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
    "Shell", "Bezel", "Lens", "Key", "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4", "Screw_5"],
    # the key cap presses the button through its opening (a declared cover)
    "covers": {"Key": "button_p6"}}
REVIEW_CLOSEUPS = ["Lens", "Key", "Shell"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them; test_kit_examples_r280 builds
# this file with each knob at its min and at its max, one at a time.
LENGTH = 232.0     # RESTYLE 197..267 length: left end to right end (x); the dock takes what the block leaves
DEPTH = 90.0       # RESTYLE 76..104 width: front to back (y); the cups fill what the block leaves
CUP_H = 140.0      # RESTYLE 119..161 height: the tallest pen cup (the others 0.72 / 0.86 of it)
CORNER = 16.0      # RESTYLE 13..19 radius: the footprint's plan corners
WALL = 2.0         # RESTYLE 1.7..2.3 wall
# end RESTYLE
# Frame: front = -Y, x across, z up, the desk at z = 0. The hardware frame
# (the board, the block that wraps it) is the board's own: never move it
# with a knob.
YF = -18.0                       # the front face (room for lens + mask before the screen)
YB = YF + DEPTH                  # the back face
YBK = 12.0                       # the display block's back (the plate behind the board)
FOOT = 1.5                       # the rubber feet under the base: the tray stands on them
BX0, BZ0 = 12.0, 24.0            # board box min x, z (x 12..132, z 24..84): a bottom-row
                                 # module slides 20 mm down out of its port, over the base
W_BLOCK, H_BLOCK = 144.0, 96.0   # the display block: x 0..144, its top
BLOCK_R, TOP_R = 6.0, 4.0        # its back corners, its top edges
PZ = 12.0                        # the plinth (the tray) height
LENS = (26.0, 78.0, 59.0, 87.0)  # smoked lens x0, x1, z0, z1 (the screen at z 65..84)
LENS_R, BEZEL, RECESS = 4.0, 4.0, 1.0
SCREEN_WIN = (36.0, 18.0)        # mask window over the screen (active area 25.6 x 13.5)
VENT = (19.0, 19.0)              # slot vent over the sensor
KEY_D = 13.0
GAP = 6.0                        # block -> dock
DOCK_X0 = W_BLOCK + GAP
LIP_H = 34.0                     # the dock's front lip
BACK_H = 0.55 * CUP_H            # the dock's back rest at the slot
SLOT_W, SLOT_Z, SLOT_TILT = 14.0, 22.0, 14.0   # phone slot width, floor, lean back (deg)
SLOT_Y = YF + 0.4 * DEPTH        # the slot's centre at its floor
CABLE = (10.0, 9.0)              # the cable groove / tunnel: width, height
CUP_SHARE = (0.72, 1.0, 0.86)
R_CUP = min(23.0, (YB - YBK - 4.0) / 2)
CUP_Y = (YBK + YB) / 2
CUP_X = [W_BLOCK / 2 + k * (2 * R_CUP + 2.0) for k in (-1, 0, 1)]
SPLIT = FOOT + WALL + 0.6        # base / shell seam, in the cavity
SCREW = "M2.5"
COLOURS = {"Shell": "#ece6da", "Base": "graphite", "Bezel": "matte_black", "Lens": "smoked",
           "Key": "coral", "Rubber": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
LANDSCAPE_UP = Rotation(Vector(0, 0, 1), 180).multiply(Rotation(Vector(0, 1, 0), -90))
board = ap.board_object(doc)
board.Placement = Placement(Vector(), LANDSCAPE_UP)
_b = ap.bbox(board)
board.Placement = Placement(Vector(BX0 - _b.XMin, 0, BZ0 - _b.ZMin), LANDSCAPE_UP)
BB = ap.bbox(board)                             # x 12..132, z 16..76, modules face -Y
scr = ap.seat(doc, "screen", (10, 11))          # top row, left of centre: behind the lens
th = ap.seat(doc, "temp_humidity", 14)          # top row, right: behind the vent
key = ap.seat(doc, "button", 6)                 # bottom row, right: under the sensor
usb = ap.seat(doc, "usbc", 7)                   # left end, mouth -X
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


def section_x(pts, x0, x1):
    """A (y, z) polygon extruded along X from x0 to x1 (lines only)."""
    f = Part.Face(Part.makePolygon([V(x0, y, z) for y, z in pts + pts[:1]]))
    s = f.extrude(V(x1 - x0, 0, 0))
    if s.Volume < 0:
        s.reverse()
    return s


def footprint(inset, z0, z1):
    """The tray's plan (a rounded rectangle) moved `inset` in, z0..z1."""
    w = cad.rounded_rect_wire(LENGTH - 2 * inset, DEPTH - 2 * inset, CORNER - inset,
                              (LENGTH / 2, YF + DEPTH / 2, z0), "Z")
    return Part.Face(w).extrude(V(0, 0, z1 - z0))


def centre(b):
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


def top_edges(s, z):
    return [e for e in s.Edges if e.BoundBox.ZMin > z - 0.05]


# ------------------------------------------------------------ the body
# the plinth: the footprint, its top edge rolled
plinth = footprint(0, FOOT, PZ)
plinth = cad.soften(plinth, 2.0, top_edges(plinth, PZ))
# the display block: back corners BLOCK_R, its front-left corner the
# footprint's own (clipped to it), every top edge rolled TOP_R
block = cad.rounded_box(W_BLOCK, YBK - YF, H_BLOCK - FOOT, BLOCK_R, at=(0, YF, FOOT))
block = block.common(footprint(0, -1, H_BLOCK + 1))
block = cad.soften(block, TOP_R, top_edges(block, H_BLOCK))
# the phone dock: a side section along X (a low lip, a tall back rest
# falling to the back), clipped to the footprint's corners, edges rolled
# (the lip's top runs flat into the slot and the back rest's top starts
# behind it: the line between them lies inside the slot, so neither edge
# is a knife edge)
_t = math.tan(math.radians(SLOT_TILT))
y_sf = SLOT_Y - SLOT_W / 2 + (LIP_H - SLOT_Z) * _t           # the slot's front face at the lip's top
y_sb = SLOT_Y + SLOT_W / 2 + (BACK_H - SLOT_Z) * _t          # its back face at the back rest's top
DOCK_SEC = [(YF, FOOT), (YF, LIP_H), (y_sf + 1.0, LIP_H), (y_sb - 1.0, BACK_H), (y_sb + 6.0, BACK_H),
            (YB, BACK_H - 0.3 * DEPTH), (YB, FOOT)]
dock = section_x(DOCK_SEC, DOCK_X0, LENGTH + 1.0).common(footprint(0, -1, BACK_H + 1))
dock = cad.soften(dock, 3.0, [e for e in dock.Edges if e.BoundBox.ZMax > PZ + 1.0])
# the pen cups: solid posts with a rolled rim (bored below)
cups = []
for x, s in zip(CUP_X, CUP_SHARE):
    c = cyl(R_CUP, (x, CUP_Y, FOOT), (0, 0, 1), s * CUP_H - FOOT)
    cups.append(cad.soften(c, 2.0, top_edges(c, s * CUP_H)))
outer = cad.fuse_one(plinth, block, dock, *cups)
tick("body")
# the phone slot: a box leaning back SLOT_TILT about its floor's centre
# line, through the dock's whole length (a wide phone overhangs it)
slot = box(DOCK_X0 - 5, LENGTH + 5, SLOT_Y - SLOT_W / 2, SLOT_Y + SLOT_W / 2, SLOT_Z, SLOT_Z + 200)
slot.rotate(V(0, SLOT_Y, SLOT_Z), V(1, 0, 0), -SLOT_TILT)
# the cable groove in the slot floor, run on as a tunnel out of the back
# (an octagon section: flat facets, no round channel)
DOCK_XC = (DOCK_X0 + LENGTH) / 2
cw, ch = CABLE
cz0 = SLOT_Z - 4.0
oct_ = [(-cw / 2 + 2, cz0), (cw / 2 - 2, cz0), (cw / 2, cz0 + 2), (cw / 2, cz0 + ch - 2), (cw / 2 - 2, cz0 + ch),
        (-cw / 2 + 2, cz0 + ch), (-cw / 2, cz0 + ch - 2), (-cw / 2, cz0 + 2)]
f = Part.Face(Part.makePolygon([V(DOCK_XC + u, SLOT_Y, z) for u, z in oct_ + oct_[:1]]))
tunnel = f.extrude(V(0, YB - SLOT_Y + 5.0, 0))
# hollow: the plinth and the block (the electronics) and the dock, one
# core open below; the dock's core keeps a WALL round the slot and the
# tunnel (their keep-outs), so both have floors and walls
core_block = cad.rounded_box(W_BLOCK - 2 * WALL, YBK - YF - 2 * WALL, H_BLOCK - FOOT - 2 * WALL, BLOCK_R - WALL,
                             at=(WALL, YF + WALL, FOOT + WALL)).common(footprint(WALL, 0, H_BLOCK))
sec = Part.Face(Part.makePolygon([V(DOCK_X0 + WALL, y, z) for y, z in DOCK_SEC + DOCK_SEC[:1]])).makeOffset2D(-WALL)
slot_keep = box(DOCK_X0 - 5, LENGTH + 5, SLOT_Y - SLOT_W / 2 - WALL, SLOT_Y + SLOT_W / 2 + WALL, SLOT_Z - WALL,
                SLOT_Z + 200)
slot_keep.rotate(V(0, SLOT_Y, SLOT_Z), V(1, 0, 0), -SLOT_TILT)
tunnel_keep = box(DOCK_XC - cw / 2 - WALL, DOCK_XC + cw / 2 + WALL, SLOT_Y - 1.0, YB + 5.0, cz0 - WALL, cz0 + ch + WALL)
core_dock = sec.extrude(V(LENGTH - DOCK_X0 - 2 * WALL, 0, 0)).common(footprint(WALL, 0, BACK_H + 1)).cut(
    Part.makeCompound([slot_keep, tunnel_keep]))
core = cad.fuse_one(footprint(WALL, FOOT + WALL, PZ - WALL), core_block, *core_dock.Solids)
body = cad.cut(outer, core)
base, shell = cad.split(body, "Z", at=SPLIT, lip=1.2)
tick("hollow + split")

# ------------------------------------------------------------ base: holds the board
# posts under the board's bottom edge and a plate behind it (pads 0.1 mm
# off its back), all behind the modules' layer (y > 0.6)
PLATE_Y = BB.YMax + 0.1
plate = box(BX0 + 10, BB.XMax - 10, PLATE_Y + 1.0, PLATE_Y + 6.0, FOOT + WALL - 0.5, BB.ZMax - 6)
pads = [box(x, x + 6, PLATE_Y, PLATE_Y + 1.5, z, z + 8)
        for x in (BX0 + 12, BX0 + 57, BX0 + 102) for z in (BZ0 + 8, BZ0 + 44)]
# (clear of the button's column: it slides down out of port 6)
posts = [box(x, x + 8, 0.6, PLATE_Y + 6.0, FOOT + WALL - 0.5, BZ0 - 0.1) for x in (BX0 + 14, BX0 + 70)]
base = cad.fuse_one(base, plate, *pads, *posts)
# five M2.5 screws from below into bosses hanging from the shell (the
# plinth's top skin between the block and the cups and under a cup; the
# slot's floor and the tunnel's floor in the dock); each screw's length
# as cad.screw_through works it out, from the measured reach


def first_above(shape, x, y, z0):
    """The first surface of `shape` straight above (x, y, z0)."""
    s = shape.section(Part.makeLine(V(x, y, z0), V(x, y, z0 + 300)))
    return min(v.Point.z for v in s.Vertexes)


SCREWS = [((CUP_X[0] + CUP_X[1]) / 2, YBK + 3.5), ((CUP_X[1] + CUP_X[2]) / 2, YBK + 3.5),
          (CUP_X[0], CUP_Y), (DOCK_X0 + 14.0, SLOT_Y), (DOCK_XC, (SLOT_Y + YB) / 2 + 4.0)]
screws = []
for x, y in SCREWS:
    reach = first_above(shell, x, y, FOOT + WALL + 0.1) - (FOOT + WALL + 0.1)
    base, shell = cad.screw_through(base, shell, (x, y, FOOT), size=SCREW, ribs=0)
    L = int(min(WALL + 0.85 * reach, WALL + 0.1 + min(reach, 4 * 2.5 + 1.0) - 0.3))
    screws.append(cad.screw("csk_phillips", SCREW, L, at=(x, y, FOOT), axis="+Z"))
tick("base + screws")

# ------------------------------------------------------------ the face
# board retention: a rib from the front wall onto the spine (0.2 mm off),
# in the band between the module rows
shell = cad.fuse_one(shell, box(BX0 + 48, BX0 + 52, YF + WALL - 0.5, BB.YMin - 0.2, BZ0 + 22, BZ0 + 30))
# the display: a black bezel tray set RECESS back in its opening, holding
# the smoked lens, its back the mask with the screen window
lx0, lx1, lz0, lz1 = LENS
shell = cad.cut(shell, yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, YF - 6,
                              YF + WALL + 1))
yt0, yt1 = YF + RECESS, YF + WALL + 3.0
tray = cad.fuse_one(yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, yt0, YF + WALL + 1),
                    yprism(lx0 - 2, lx1 + 2, lz0 - 2, lz1 + 2, LENS_R + 2, YF + WALL + 0.5, yt1))
y_lens1 = YF + WALL + 1.7
tray = cad.cut(tray, yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 - 1, y_lens1))
lens = yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 + 0.6, y_lens1 - 0.3)   # 0.3 mm air before the mask
sx, _sy, sz = centre(ap.bbox(scr))
tray = cad.cut(tray, cad.rounded_box(SCREEN_WIN[0], 10, SCREEN_WIN[1], 1.5,
                                     at=(sx - SCREEN_WIN[0] / 2, yt1 - 5, sz - SCREEN_WIN[1] / 2), edges="y"))
# the sensor: a slot vent in the face, a sealed chamber (a sleeve) from the
# wall to 0.3 mm off the sensor - it breathes the room, not the board
tb = ap.bbox(th)
tx, _ty, tz = centre(tb)
shell = cad.fuse_one(shell, cad.cut(box(tb.XMin - 1.6, tb.XMax + 1.6, YF + WALL - 0.5, tb.YMin - 0.3,
                                        tb.ZMin - 1.6, tb.ZMax + 1.6),
                                    box(tb.XMin - 0.4, tb.XMax + 0.4, YF, tb.YMin + 1, tb.ZMin - 0.4, tb.ZMax + 0.4)))
shell = cad.grille(shell, (tx, YF, tz), (0, -1, 0), VENT, kind="slot", hole=2.2, pitch=3.6)
# the key: a cap through the face, flange 0.1 mm behind the wall, a
# plunger to 0.16 mm off the module's own cap
kb = ap.bbox(key)
kx, _ky, kz = centre(kb)
y_base = YF + WALL + 0.9
cap = cad.button_cap(KEY_D, y_base - (YF - 1.6), dome=0.8, flange=1.5, at=(kx, y_base, kz), axis="-Y")
shell = cad.opening_for(shell, cap, clearance=0.25, chamfer=0.4, axis="-Y")
cap = cad.fuse_one(cap, cyl(3.0, (kx, kb.YMin - 0.16, kz), (0, -1, 0), (kb.YMin - 0.16) - y_base + 0.5))
# USB-C on the left side: a pocket brings the wall to 0.25 mm off the
# socket mouth (a real plug reaches it), a liner round it, then the
# measured opening
ub = ap.bbox(usb)
uy, uz = -5.9, (ub.ZMin + ub.ZMax) / 2         # the receptacle: 5.9 mm above the PCB top
pocket = xprism(uy - 5.5, uy + 5.5, uz - 6.5, uz + 6.5, -5, ub.XMin - 1.3, 3)
liner = cad.cut(xprism(YF + 1.0, uy + 7.0, uz - 8.0, uz + 8.0, ub.XMin - 0.25, WALL - 1.0, 3.5), pocket)
shell = cad.fuse_one(cad.cut(shell, pocket), liner)
shell = cad.socket_opening(shell, usb, margin=1.5)
tick("face")

# ------------------------------------------------------------ cups and the dock
# the cups bored down to the plinth's skin (it is their floor)
shell = cad.cut(shell, [cyl(R_CUP - WALL, (x, CUP_Y, PZ), (0, 0, 1), s * CUP_H) for x, s in zip(CUP_X, CUP_SHARE)])
# the phone slot and the cable tunnel (built with the body: their
# keep-outs shaped the dock's core)
shell = cad.cut(shell, [slot, tunnel])
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# the parting-line reveal round the plinth, just over the seam
shell = cad.groove_ring(shell, "Z", SPLIT + 2.5, w=0.8, depth=0.6)
# a raised ring round the key (0.6 mm proud), lettering on the block
shell = cad.fuse_one(shell, cad.soften(cad.cut(cyl(KEY_D / 2 + 2.6, (kx, YF + 0.8, kz), (0, -1, 0), 1.4),
                                               cyl(KEY_D / 2 + 1.5, (kx, YF + 1.0, kz), (0, -1, 0), 2)), 0.3))
shell = cad.text(shell, "ATECH", ((BX0 + 10 + kx - 14) / 2, YF, BZ0 + 10), (0, -1, 0), 7, depth=0.5,
                 mode="deboss")
# the cups' inner rims rolled
before = shell
shell = cad.soften(shell, 0.8, [e for e in shell.Edges
                                if any(abs(e.BoundBox.ZMax - s * CUP_H) < 0.05 and
                                       abs(e.BoundBox.XMax - (x + R_CUP - WALL)) < 0.05
                                       for x, s in zip(CUP_X, CUP_SHARE))])
# hex vents under the block, in front of the posts
base = cad.grille(base, ((BX0 + BB.XMax) / 2, YF + 8.0, FOOT), (0, 0, -1), (90.0, 10.0), kind="hex", hole=3.0,
                  pitch=4.5)
# rubber feet in recesses under the base
feet = []
FEET = [(x, y) for x in (CORNER, LENGTH - CORNER) for y in (YF + CORNER * 0.75, YB - CORNER * 0.75)]
# (a 1 mm recess - the foot's plug - under a pad on the floor's top that
# keeps 1.5 mm of floor over it at any WALL)
base = cad.fuse_one(base, *[cyl(5.5, (x, y, FOOT + WALL - 0.3), (0, 0, 1), 2.8 - WALL) for x, y in FEET])
base = cad.cut(base, [cyl(4.6, (x, y, FOOT - 1.0), (0, 0, 1), 2.0) for x, y in FEET])
for x, y in FEET:
    feet.append(cad.foot(9, FOOT + 1.0, style="dome", at=(x, y, FOOT + 1.0)))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour])
    return o


part("Shell", shell, "Shell")
part("Base", base, "Base")
part("Bezel", tray, "Bezel")
o = part("Lens", lens, "Lens")
o.ViewObject.Transparency = cad.transparency(COLOURS["Lens"])
part("Key", cap, "Key")
for i, sh in enumerate(feet):
    part("Rubber_%d" % (i + 1), sh, "Rubber")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
