"""Example: "a music box" - a walnut-look box with a lid line, a brass speaker grille, a glowing knob and a lit window.

fork this file for a music box / jukebox / record player (a keepsake or
jewellery box that plays, a sound box with a dial and a lid line); change PARAMETERS and the outlines.
ARCHETYPE: music box

How it is built (R425):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT in the box, turned so its long side runs across (ROT) and
    its front column (9-14) faces the front: the speaker SEATS on the pair
    (13, 14) and the knob on (9, 10) - both overhang the board edge 20 mm
    toward the front, under the lid's front half; the light on 11 between
    them under a frosted lit window; the button on 4 in the back row under
    a brass key cap; USB-C on 7 at the right end, in a pocket in the right
    side. Ports 8 and 12 stay empty (reserved: the firmware cannot drive
    them). The board rides at HEIGHT - its stack: the lid's inner face sits
    0.8 mm over the speaker whatever the height, so the knob always stands
    the same 14 mm proud of the lid. The box: a body block and a lid block
    1 mm proud all round (the lid line is a real step), rounded corners,
    the lid's top edge rolled, hollowed with a sharp core, split LOW into
    the fixed Base (a dark plinth: it carries the board on pads, end and
    side fences, under every module's slide path) and the Body (fitted
    after); four M2.5 screws from below into insert bosses.
  * STAGE B - details: the lid-line reveal, brass hinges on the back
    across the lid line, a brass keyhole escutcheon on the front, a groove
    frame round the lid top, the LED pixel grid on the lit window, the
    back vents, lettering, brass feet.
RESTYLE (R425): WIDTH, DEPTH, HEIGHT, CORNER and WALL drive every outline
and every cutter below. The board's height follows HEIGHT (BZ), the screws
and fences follow the walls; the hardware frame in x / y (the board centred,
the front column toward the front) is the board's own: never move it with
a knob.
DETAILS (visible, 28): 1 body block; 2 lid block 1 mm proud (the lid
line); 3 rolled lid edge; 4 lid-line reveal groove; 5 groove frame round
the lid top; 6 domed brass speaker grille; 7 its ring of holes; 8 frosted
lit window; 9 LED pixel grid on it; 10 frosted light ring round the knob;
11 the knob standing 14 mm proud; 12 brass key cap; 13 raised ring round
the key; 14 USB-C pocket with liner; 15-16 two brass hinges with barrels
across the lid line; 17 brass keyhole escutcheon; 18 its keyhole; 19 back
vent slots; 20 "ATECH" on the lid; 21 "ATECH" on the plinth; 22 dark
plinth; 23-26 four brass feet in recesses; 27 four screws from below;
28 the plinth's parting line.
Inside: board pads, end and side fences, a rib from the lid onto the
board's spine, the light pipe and the ring's pipe down to 0.5 mm off the
LEDs, insert bosses, the lip keying body to plinth, a plunger on the key.
Materials: walnut body and lid, dark plinth, brass grille, key, hinges,
escutcheon and feet, frosted window and ring, chrome screws.
MEASURED (R425, 2026-10-26): ./check CHECK PASS, see test_kit_examples_r500
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
    "Body", "Grille", "Light_Window", "Knob_Ring", "Knob_Cap", "Button_Cap", "Hinge_L", "Hinge_R",
    "Escutcheon", "Foot_1", "Foot_2", "Foot_3", "Foot_4", "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    "covers": {"Button_Cap": "button_p4"}}
REVIEW_CLOSEUPS = ["Grille", "Knob_Cap", "Light_Window", "Hinge_L"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them; test_kit_examples_r280 builds
# this file with each knob at its min and at its max, one at a time.
WIDTH = 170.0      # RESTYLE 144..196 width: the body across (x); 144: the speaker and the screws
DEPTH = 108.0      # RESTYLE 91.5..124.5 length: front to back (y); 91.5: the knob and the back row
HEIGHT = 40.0      # RESTYLE 34..46 height: the lid top over the desk (z)
CORNER = 10.0      # RESTYLE 8.5..11.5 radius: the plan corners (the lid's are 1 mm more)
WALL = 2.5         # RESTYLE 2.1..2.9 wall
# end RESTYLE
# Box frame: x across, y front (-) to back (+), z up; the desk at z = 0.
Z_BOT = 1.5                       # the plinth's underside (the brass feet stand 1.5 proud)
CY = -10.0                        # the box's centre in y: the hardware's (front -50.5, back 30.5)
X1 = WIDTH / 2
Y0, Y1 = CY - DEPTH / 2, CY + DEPTH / 2
LIP_OUT = 1.0                     # the lid stands this proud of the body all round
EDGE = 3.0                        # the lid's rolled top edge
STACK = 2.5 + 20.2                # board underside -> speaker top
BZ = HEIGHT - WALL - 0.8 - STACK  # the board's underside: the lid 0.8 mm over the speaker
SPLIT = BZ - 2.0                  # plinth / body seam, under every module's slide path
LID_Z = SPLIT + 0.55 * (HEIGHT - SPLIT)  # the lid line
GRILLE_D = 40.0                   # the brass grille over the speaker
WIN = (26.0, 26.0, 3.0)           # the lit window w, d, corner r
RING_R = (8.05, 17.0)             # the frosted ring round the knob shaft (inner, outer)
CAP_R = 11.0                      # the brass knob cap on the shaft
KEY_D = 12.0
SCREW = "M2.5"
COLOURS = {"Base": "#3b2618", "Body": "wood", "Grille": "brass", "Light_Window": "frosted",
           "Knob_Ring": "frosted", "Knob_Cap": "brass", "Button_Cap": "brass", "Hinge": "brass", "Escutcheon": "brass",
           "Foot": "brass", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
FLAT = Rotation(Vector(1, 0, 0), 90)
ROT = Rotation(Vector(0, 0, 1), -90).multiply(FLAT)    # long side across, ports 9-14 at the front
board = ap.board_object(doc)
board.Placement = Placement(Vector(), ROT)
_b = ap.bbox(board)
board.Placement = Placement(Vector(-60.0 - _b.XMin, 30.0 - _b.YMax, BZ - _b.ZMin), ROT)  # x -60..60, y -30..30
BB = ap.bbox(board)
PT = BB.ZMin + 2.5                                     # the PCB top: every module's seat
spk = ap.seat(doc, "speaker", (13, 14))                # front left, overhangs to y -50.4
knob = ap.seat(doc, "knob", (9, 10))                   # front right, overhangs to y -50.5
glow = ap.seat(doc, "light", 11)                       # front middle, under the lit window
btn = ap.seat(doc, "button", 4)                        # back row
usb = ap.seat(doc, "usbc", 7)                          # right end, mouth +X
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def annulus(r0, r1, c, z0, z1):
    return cad.cut(cyl(r1, (c[0], c[1], z0), z1 - z0), cyl(r0, (c[0], c[1], z0 - 1), z1 - z0 + 2))


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
    return rest, piece


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


# ------------------------------------------------------------ the box
# a body block and a lid block LIP_OUT proud all round: the lid line is a
# real step; the lid's top edge rolled, the plinth's bottom edge eased
lower = cad.rounded_box(WIDTH, DEPTH, LID_Z - Z_BOT, CORNER, at=(-X1, Y0, Z_BOT))
upper = cad.rounded_box(WIDTH + 2 * LIP_OUT, DEPTH + 2 * LIP_OUT, HEIGHT - LID_Z, CORNER + LIP_OUT,
                        at=(-X1 - LIP_OUT, Y0 - LIP_OUT, LID_Z))
outer = cad.fuse_one(lower, upper)
outer = cad.fillet_safe(outer, EDGE, edges=[e for e in outer.Edges if e.BoundBox.ZMin > HEIGHT - 0.01])
outer = cad.fillet_safe(outer, 1.2, edges=[e for e in outer.Edges if e.BoundBox.ZMax < Z_BOT + 0.01])
# the core keeps SHARP inner edges (a filleted core reads as clip channels)
core = cad.rounded_box(WIDTH - 2 * WALL, DEPTH - 2 * WALL, HEIGHT - 2 * WALL - Z_BOT, CORNER - WALL,
                       at=(-X1 + WALL, Y0 + WALL, Z_BOT + WALL))
shell = cad.cut(outer, core)
tick("box")
base, body = cad.split(shell, "Z", at=SPLIT, lip=1.2)
tick("split")

# ------------------------------------------------------------ the plinth holds the board
# pads 0.1 mm under the board, fences off its ends and long sides - all
# under the modules' seat plane (PT), so every slide path stays clear
FLOOR = Z_BOT + WALL
pads = [box(x - 4, x + 4, y - 4, y + 4, FLOOR - 0.5, BB.ZMin - 0.1) for x in (-48, 48) for y in (-20, 20)]
fences = [box(sx * 60.3, sx * 61.8, -8, 8, FLOOR - 0.5, PT - 1.5) for sx in (-1, 1)]
fences += [box(x - 6, x + 6, sy * 30.3, sy * 31.8, FLOOR - 0.5, PT - 1.5) for x in (-30, 30) for sy in (-1, 1)]
base = cad.fuse_one(base, *pads, *fences)
# four M2.5 screws up through the plinth into insert bosses in the body;
# each insert sleeve 3 mm off the inner wall (clear of the plinth's lip,
# MEASURED: 1.5 mm off it overlapped the lip), clear of the speaker and the
# knob (x beyond +-61.5)
SX = max(64.5, X1 - WALL - 6.0)
SCREWS = [(sx * SX, y) for sx in (-1, 1) for y in (Y0 + WALL + 6.0, Y1 - WALL - 6.0)]
INSERT_D = {"M2": 3.2, "M2.5": 3.6, "M3": 4.3}[SCREW]
screws = []
for x, y in SCREWS:
    base, body = cad.screw_through(base, body, (x, y, Z_BOT), size=SCREW, ribs=0)
    zf = FLOOR + 0.1
    body = cad.fuse_one(body, cyl(INSERT_D / 2 + 1.2, (x, y, zf), 10.0))
    body = cad.cut(body, cyl(INSERT_D / 2, (x, y, zf - 0.5), 9.5))
    screws.append(cad.screw("csk_phillips", SCREW, 8, at=(x, y, Z_BOT), axis="+Z"))
# board retention: a rib down from the lid onto the spine (0.2 mm off it)
body = cad.fuse_one(body, box(-12, -10, -3, 3, BB.ZMax + 0.2, HEIGHT - WALL + 0.5))
tick("plinth + screws")

# ------------------------------------------------------------ the lid's openings
TOP_IN = HEIGHT - WALL                       # the lid's inner face
# the speaker: a brass grille disc that fills its own opening (an insert),
# its top domed 1.2 mm, a ring of holes through it
scx, scy, _ = centre(spk)
body, grille = insert(body, cyl(GRILLE_D / 2, (scx, scy, TOP_IN - 1), WALL + 2))
dome = Part.makeSphere(GRILLE_D * 1.4, V(scx, scy, HEIGHT + 1.2 - GRILLE_D * 1.4))
grille = cad.fuse_one(grille, dome.common(cyl(GRILLE_D / 2, (scx, scy, HEIGHT - 0.5), 3.0)))
grille = cad.speaker_grille(grille, (scx, scy, HEIGHT + 1.2), (0, 0, 1), GRILLE_D - 6, ring_pitch=2.6, hole=1.5)
# the lit window: a frosted plate in the lid over the light, its light
# pipe down to 0.5 mm off the LEDs (narrower than the module: clear of the
# knob beside it)
lx, ly, _ = centre(glow)
lb = ap.bbox(glow)
body, window = insert(body, cad.rounded_box(WIN[0], WIN[1], WALL + 2, WIN[2],
                                            at=(lx - WIN[0] / 2, ly - WIN[1] / 2, TOP_IN - 1)))
window = cad.fuse_one(window, box(lb.XMin + 0.2, lb.XMax - 0.2, lb.YMin + 0.4, lb.YMax - 0.4, lb.ZMax + 0.5,
                                  TOP_IN + 0.3))
# the knob: its shaft up through a frosted ring over its LED ring, the
# ring's pipe down to 0.5 mm off the knob's plate
kx, ky, _ = centre(knob)
kb = ap.bbox(knob)
body = cad.cut(body, cyl(RING_R[0], (kx, ky, TOP_IN - 1), WALL + 2))     # the shaft's hole
body, ring = insert(body, annulus(RING_R[0] - 0.5, RING_R[1], (kx, ky), TOP_IN - 1, HEIGHT + 1))
ring = cad.fuse_one(ring, annulus(RING_R[0], RING_R[1] - 1.0, (kx, ky), PT + 10.6, TOP_IN + 0.3))
# a brass knob cap pushed on the shaft (bore 0.35 mm round its 12.2 mm
# cap), its plug 2 mm down the ring's bore (0.2 mm clear): the shaft
# turns it, the plug keeps it on its axis
KT = kb.ZMax + 2.0
knob_cap = cad.fuse_one(cyl(CAP_R, (kx, ky, HEIGHT + 0.6), KT - HEIGHT - 0.6),
                        annulus(6.45, RING_R[0] - 0.2, (kx, ky), HEIGHT - 2.0, HEIGHT + 1.0))
knob_cap = cad.fillet_safe(knob_cap, 1.5, edges=[e for e in knob_cap.Edges if e.BoundBox.ZMin > KT - 0.01])
knob_cap = cad.cut(knob_cap, cyl(6.45, (kx, ky, HEIGHT - 3.0), kb.ZMax + 0.4 - (HEIGHT - 3.0)))
print("KNOB %.1f mm proud of the lid, its cap %.1f" % (kb.ZMax - HEIGHT, KT - HEIGHT))
# the key: a brass cap through the lid, flange 0.1 mm under it, a plunger
# to 0.16 mm over the button's own cap
bx, by, _ = centre(btn)
bb_ = ap.bbox(btn)
base_z = TOP_IN - 0.9
cap = cad.button_cap(KEY_D, (HEIGHT + 1.6) - base_z, dome=0.8, flange=1.5, at=(bx, by, base_z), axis="+Z")
body = cad.opening_for(body, cap, clearance=0.25, chamfer=0.4, axis="+Z")
cap = cad.fuse_one(cap, cyl(3.0, (bx, by, bb_.ZMax + 0.16), base_z - (bb_.ZMax + 0.16) + 0.5))
# USB-C on the right: a pocket brings the wall to 0.25 mm off the mouth
ub = ap.bbox(usb)
uy, uz = (ub.YMin + ub.YMax) / 2, PT + 5.9
pocket = xprism(uy - 6.0, uy + 6.0, uz - 5.0, uz + 5.0, ub.XMax + 1.3, X1 + 5, 3)
liner = cad.cut(xprism(uy - 8.0, uy + 8.0, uz - 7.0, uz + 7.0, ub.XMax + 0.25, X1 - 1.0, 4), pocket)
body = cad.fuse_one(cad.cut(body, pocket), liner)
body = cad.socket_opening(body, usb, margin=1.5)
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# brass hinges on the back across the lid line: each fills a 1.2 mm
# recess in the back (an insert, cut before the reveal so no groove thins
# it), its barrel standing out at the line
hinges = []
for hx in (-0.3 * WIDTH, 0.3 * WIDTH):
    body, leaf = insert(body, box(hx - 13, hx + 13, Y1 - 1.2, Y1 + LIP_OUT + 2, LID_Z - 9, LID_Z + 6))
    leaf = cad.fuse_one(leaf, cyl(1.9, (hx - 13, Y1 + LIP_OUT + 1.0, LID_Z), 26, (1, 0, 0)))
    hinges.append(leaf)
# the brass keyhole escutcheon on the front, under the lid line: 1.4 mm
# deep (an insert), the keyhole 0.6 mm into it
body, esc = insert(body, cad.rounded_box(14, 3.0, 12, 3.0, at=(-7, Y0 - 1.6, LID_Z - 14), edges="y"))
esc = cad.cut(esc, [cyl(1.6, (0, Y0 - 1, LID_Z - 6), 1.6, (0, 1, 0)),
                    box(-0.8, 0.8, Y0 - 1, Y0 + 0.6, LID_Z - 11, LID_Z - 6)])
# the lid-line reveal just under the step, a groove frame round the lid top
body = cad.groove_ring(body, "Z", LID_Z - 1.0, w=0.8, depth=0.6)
FI = EDGE + 1.5
body = cad.groove_outline(body, [(-X1 - LIP_OUT + FI, Y0 - LIP_OUT + FI), (X1 + LIP_OUT - FI, Y0 - LIP_OUT + FI),
                                 (X1 + LIP_OUT - FI, Y1 + LIP_OUT - FI), (-X1 - LIP_OUT + FI, Y1 + LIP_OUT - FI)],
                          view="+Z", w=0.8, depth=0.5, both_sides=False)
# a raised ring round the key
body = cad.fuse_one(body, annulus(KEY_D / 2 + 1.6, KEY_D / 2 + 3.0, (bx, by), HEIGHT - 0.5, HEIGHT + 0.6))
# the LED pixel grid: shallow grooves across the lit window (4 x 4 cells)
cells = []
for i in (-1, 0, 1):
    cells.append(box(lx + i * WIN[0] / 4 - 0.3, lx + i * WIN[0] / 4 + 0.3, ly - WIN[1] / 2, ly + WIN[1] / 2,
                     HEIGHT - 0.4, HEIGHT + 1))
    cells.append(box(lx - WIN[0] / 2, lx + WIN[0] / 2, ly + i * WIN[1] / 4 - 0.3, ly + i * WIN[1] / 4 + 0.3,
                     HEIGHT - 0.4, HEIGHT + 1))
window = cad.cut(window, cells)
# the knob cap: a straight knurl round its side, a pointer groove on top
knob_cap = cad.knurl(knob_cap, "+Z", (kx, ky, HEIGHT + 0.6), CAP_R, 1.0, KT - HEIGHT - 2.4, n=40, depth=0.35)
knob_cap = cad.cut(knob_cap, box(kx - 0.5, kx + 0.5, ky - CAP_R + 1.5, ky - 7.0, KT - 0.6, KT + 1))
# back vents between the hinges, lettering on the lid and the plinth
body = cad.grille(body, (0, Y1, (SPLIT + LID_Z) / 2 + 1.0), (0, 1, 0), (0.3 * WIDTH, 8), kind="slot", hole=2.0,
                  pitch=5.0)
body = cad.text(body, "ATECH", (-0.24 * WIDTH, Y1 - 14, HEIGHT), (0, 0, 1), 6, depth=0.5, mode="deboss",
                up=(0, 1, 0))
# brass feet in recesses under the plinth, inboard of the screw heads
feet = []
for x in (-SX + 12, SX - 12):
    for y in (SCREWS[0][1], SCREWS[1][1]):
        base = cad.cut(base, cyl(4.6, (x, y, Z_BOT - 1), 2.0))
        feet.append(cad.foot(9, Z_BOT + 1.0, style="dome", at=(x, y, Z_BOT + 1.0)))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour])
    return o


part("Base", base, "Base")
part("Body", body, "Body")
part("Grille", grille, "Grille")
o = part("Light_Window", window, "Light_Window")
o.ViewObject.Transparency = cad.transparency("frosted")
o = part("Knob_Ring", ring, "Knob_Ring")
o.ViewObject.Transparency = cad.transparency("frosted")
part("Knob_Cap", knob_cap, "Knob_Cap")
part("Button_Cap", cap, "Button_Cap")
part("Hinge_L", hinges[0], "Hinge")
part("Hinge_R", hinges[1], "Hinge")
part("Escutcheon", esc, "Escutcheon")
for i, sh in enumerate(feet):
    part("Foot_%d" % (i + 1), sh, "Foot")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
