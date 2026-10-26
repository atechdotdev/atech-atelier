"""Example: "a handheld game console" - landscape, sculpted grips, one big black screen.

fork this file for a handheld game console / held product (a game pad, a
remote, a meter - anything gripped in two hands); change PARAMETERS and the outlines.
ARCHETYPE: handheld

How it is built (R270, R420):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT, turned so its long side runs across the device and moved
    40 mm to the left (SHIFT), so the screen SEATS on the pair (13, 14) right
    on the device's centre line and the four D-pad buttons SEAT on ports 1,
    2, 9, 10 under the left thumb - every D-pad module seated, no ribbon to
    route (R420: four modules, so the D-pad reads all four directions);
    A CABLED straight out of the end port 8 into the right grip, B cabled
    from port 12 round the top of the board; USB-C seated on port 5 in the
    bottom edge, a power LED on port 4 under the glass. The cover glass
    (>= 40 % of the face) is ONE gloss-black screen: a gloss-black mask
    under clear glass, the mask's window exactly over the screen's active
    area, a second small window over the LED. The body: ONE plan outline
    and ONE side outline of lines (grip bellies under the palms, the back
    crowned between them), cad.profile_body with a crisp face edge and a
    big rolled underside (the back tapers into the sides), hollowed with
    its own core, split into the fixed Back (it carries the board) and the
    Front; four M2 screws from the back into insert bosses.
  * STAGE B - details: the parting-line reveal, soft-touch grip pads in the
    bellies, a battery door with a finger notch, vents, rubber feet, a
    lanyard eyelet, lettering, the D-pad arrows.
D-PAD (R420): a cross cap that rocks on a hidden plate over FOUR button
modules seated on the 2 x 2 cells 1 / 2 / 9 / 10 (20 x 41 mm apart); each
direction closes the two switches on its side (up: 9 + 10, left: 1 + 9), a
diagonal closes one - the plate carries a plunger onto each module.
RESTYLE (R425): LENGTH, DEPTH, HEIGHT, CORNER, EDGE and WALL drive every
outline and every cutter below (test_kit_examples_r280 builds each at its
documented min and max). The hardware frame (SHIFT, the D-pad cells, the
screen) is the board's own: never move it with a knob.
DETAILS (visible, 30): 1 grip bellies; 2 crowned back; 3 crisp face edge;
4 rolled tapering underside; 5 gloss-black cover glass; 6 mask window
over the active area; 7 LED window in the mask; 8 raised rim round the
glass; 9 cross D-pad; 10 four D-pad arrows; 11-12 round A / B caps with
letters; 13 USB-C pocket in the bottom edge; 14 parting-line reveal;
15-16 soft-touch grip pads in recesses; 17 battery door seam; 18 door
finger notch; 19 vent slots on the back; 20 top-edge vent; 21 four
rubber feet on the bellies; 22 lanyard eyelet; 23 "ATECH" under the
screen; 24 model mark on the back; 25 four screws from the back;
26 insert bosses; 27 rib under the mask onto the board; 28 board pads and
end fences; 29 lip keying front to back; 30 plungers under every key.
Materials: warm-white front, graphite back, gloss-black glass and mask,
graphite D-pad, signal-red A / B, soft-touch grips, rubber feet, chrome
screws, green LED.
MEASURED (R420, 2026-10-20): see test_kit_examples_r270 (TIMINGS line).
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
    "Front", "Bezel", "Cover_Glass", "DPad_Cap", "A_Cap", "B_Cap", "LED_Pipe", "Grip_L", "Grip_R",
    "button_12_cable_p12",       # B's ribbon goes in after the screen is seated (it crosses its slide path)
    "Foot_1", "Foot_2", "Foot_3", "Foot_4", "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    "covers": {"DPad_Cap": ["button_p1", "button_p2", "button_p9", "button_p10"],
               "A_Cap": "button_8", "B_Cap": "button_12"}}
REVIEW_CLOSEUPS = ["DPad_Cap", "Bezel", "A_Cap"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them; test_kit_examples_r280 builds
# this file with each knob at its min and at its max, one at a time.
LENGTH = 252.0     # RESTYLE 214..290 length: across the grips (x)
DEPTH = 98.0       # RESTYLE 83.3..112.7 width: bottom edge to top edge (y) - 83.3: B's ribbon lane
HEIGHT = 27.7      # RESTYLE 23.5..31.9 height: the face over the desk (thickness where held)
CORNER = 28.0      # RESTYLE 23.5..32.5 radius: the grips' plan corners (the top corners 0.55 x)
EDGE = 3.4         # RESTYLE 2.85..3.95 radius: the face edge (the underside rolls 2.5 x)
WALL = 2.0         # RESTYLE 1.7..2.3 wall
# end RESTYLE
# Device frame: x across, y up the face, z out of the face (the bellies on
# the desk at Z_BOT). The board's frame (fixed: the hardware decides it):
SHIFT = -40.0                        # board centre x: the screen on (13, 14) lands on x = 0
PT = 9.5                             # PCB top (underside 7.0): room for deep bellies
DPAD = (SHIFT - 40.0, 0.0)           # the D-pad: the middle of the cells 1 / 2 / 9 / 10
X1 = LENGTH / 2
Y0 = -31.2 - WALL                    # bottom edge (inner wall 0.8 off the board)
Y1 = Y0 + DEPTH                      # top edge
Z_BOT = 0.5                          # the bellies (the feet stand 0.5 proud: the desk at 0)
Z_FACE = Z_BOT + HEIGHT              # the face
Z_C = 6.4 - WALL                     # the crowned back between the grips (floor 0.6 under the board)
SPLIT = Z_C + WALL + 0.8             # back / front seam: in the cavity, lip top < the PCB top (R2)
R_TOP = 0.55 * CORNER


def corner_fit(a, b, m):
    """R425: the largest plan-corner radius that keeps a point a mm in from
    the end and b mm in from the edge (the board's corner) m mm inside the
    outer skin - a short restyle tightens the corner instead of cutting
    the wall into the board (the sweep's LENGTH-min failure, MEASURED)."""
    k = a + b - m
    return k + math.sqrt(max(0.0, k * k - (a * a + b * b - m * m)))


GLASS_W = min(126.0, 2 * (X1 - 52.0))                # cover glass: clear of the D-pad and B
THUMB_A = (X1 - 21.0, -3.0)                          # A: straight out of the end port 8
THUMB_B = (max(X1 - 42.0, GLASS_W / 2 + 11.0), 17.0)  # B: up and left of A, clear of the glass
COLOURS = {"Back": "graphite", "Front": "#ebe8e1", "Bezel": "#0b0c0e", "Cover_Glass": "smoked",
           "DPad": "graphite", "AB": "signal_red", "LED_Pipe": "led_green", "Grip": "soft_touch",
           "Foot": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
FLAT = Rotation(Vector(1, 0, 0), 90)
ACROSS = Rotation(Vector(0, 0, 1), 90).multiply(FLAT)     # long side along X
board = ap.board_object(doc)
board.Placement = Placement(Vector(), ACROSS)
_b = ap.bbox(board)
board.Placement = Placement(Vector(SHIFT - (_b.XMin + _b.XMax) / 2, -(_b.YMin + _b.YMax) / 2,
                                   PT + 4.5 - _b.ZMax), ACROSS)  # x -100..20, y -30..30
BB = ap.bbox(board)
screen = ap.seat(doc, "screen", (13, 14))          # x -20..20, y 11..30: the centre line
pads = [ap.seat(doc, "button", n) for n in (1, 2, 9, 10)]   # the D-pad's four switches
usb = ap.seat(doc, "usbc", 5)                       # bottom edge, mouth -Y
led = ap.seat(doc, "light", 4)                      # power LED, under the glass
ZM = Z_FACE - WALL - 0.9 - 0.5 - 5.02               # cabled keys' centre: 0.5 under their cap base
btn_a, a_rib = ap.cable(doc, "button", 8, ap.module_placement(
    "button", (THUMB_A[0], THUMB_A[1], ZM), face="+Z", cable="-X"))
# B from port 12: out of the top edge, a flat lane north of the board, an
# S-bend down into B's socket on its west side - every bend IN the
# ribbon's plane, so it needs no twist (R425, MEASURED: a fold up and back
# leaves the ribbon a half twist, spread over its length, and it tore at
# every restyle; a lane over the screen blinds it). The lane is what sets
# DEPTH's minimum: the ribbon (14 wide) turns at 7.5 mm.
_sy, _sz = BB.YMax + 2.83, PT + 1.27                # port 12's plug lead end (measured)
_bx, _bz = THUMB_B[0] - 12.9, ZM - 3.75             # B's socket lead end (west of the module)
RB = 7.5                                            # the ribbon's bend radius in its plane


def arc_pts(c, r, a0, a1, z0, z1, n=6):
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)),
             z0 + (z1 - z0) * i / n) for i in range(1, n + 1)]


def line_pts(p0, p1, step=12.0):
    n = max(1, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / step))
    return [tuple(p0[k] + (p1[k] - p0[k]) * i / n for k in range(3)) for i in range(1, n)]


_px = SHIFT + 10.0                                  # port 12's x
_xs = _bx - 2 * RB - 1.0                            # where the S-bend starts
_vy = THUMB_B[1] + RB                               # the S-bend's lower centre
# dense points on arcs and lines: a sparse spline bulged 3.4 mm into the
# top wall at DEPTH min (MEASURED)
_arc1 = arc_pts((_px + RB, _sy), RB, 180, 90, _sz, _sz)
_arc2 = arc_pts((_xs, _sy), RB, 90, 0, _sz, _sz + 0.5)
B_VIA = (_arc1 + line_pts(_arc1[-1], (_xs, _sy + RB, _sz)) + [(_xs, _sy + RB, _sz)] + _arc2
         + line_pts(_arc2[-1], (_xs + RB, _vy, (_sz + _bz) / 2)) + [(_xs + RB, _vy, (_sz + _bz) / 2)]
         + arc_pts((_xs + 2 * RB, _vy), RB, 180, 270, (_sz + _bz) / 2, _bz)[:-1])
btn_b, b_rib = ap.cable(doc, "button", 12, ap.module_placement(
    "button", (THUMB_B[0], THUMB_B[1], ZM), face="+Z", cable="-X"), via=B_VIA)
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(m):
    b = ap.bbox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


def bottom_z(shape, x, y):
    """The back's outer surface height at (x, y) (a ray up from below)."""
    s = shape.section(Part.makeLine(V(x, y, -50), V(x, y, 80)))
    return min(v.Point.z for v in s.Vertexes)


def top_z(shape, x, y):
    """The face's height at (x, y) (a ray down from above)."""
    s = shape.section(Part.makeLine(V(x, y, 80), V(x, y, -50)))
    return max(v.Point.z for v in s.Vertexes)


def insert(shell, cutter):
    """(shell with the opening, the piece that fills it exactly)."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1:
        piece, rest = shell.common(cutter, 0.01), shell.cut(cutter, 0.01)
    if piece.Volume < 1 or not rest.isValid() or len(rest.Solids) != len(shell.Solids):
        raise cad.CadError("insert: the cutter does not cleanly cross the wall")
    return rest, piece


def corner(c, r, a0, a1, n=6):
    """A plan corner as n straight facets (R270: an exact-arc plan made the
    shell's booleans unreliable - MEASURED, a 3.2 mm3 cut removed 0.36)."""
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


# lines only (R270 robust body recipe): no spline to wiggle; the profile
# fillet rounds every facet edge into one soft corner
R_BL = min(CORNER, corner_fit(X1 + BB.XMin, BB.YMin - Y0, WALL + 1.5))
R_TL = min(R_TOP, corner_fit(X1 + BB.XMin, Y1 - BB.YMax, WALL + 1.5))
PLAN = (corner((-X1 + R_BL, Y0 + R_BL), R_BL, 180, 270) + corner((X1 - CORNER, Y0 + CORNER), CORNER, 270, 360)
        + corner((X1 - R_TOP, Y1 - R_TOP), R_TOP, 0, 90) + corner((-X1 + R_TL, Y1 - R_TL), R_TL, 90, 180))
# the side (x, z): a belly under each palm down to the desk, the back
# crowned up between them (under the board), the face flat - all from the
# knobs (R425)
BX0, BX1 = X1 - 12.0, X1 - 0.25 * LENGTH            # the belly's flat, from the end
CX = X1 - 0.36 * LENGTH                             # where the crown begins
SIDE = [(-X1, Z_BOT + 8.0), (-X1 + 4, Z_BOT + 1.5), (-BX0, Z_BOT), (-BX1, Z_BOT), (-CX, Z_C), (CX, Z_C),
        (BX1, Z_BOT), (BX0, Z_BOT), (X1 - 4, Z_BOT + 1.5), (X1, Z_BOT + 8.0), (X1, Z_FACE), (-X1, Z_FACE)]

body = cad.profile_body(SIDE, PLAN, spline=False, fillet=(EDGE, 2.5 * EDGE))
# the core keeps SHARP inner edges: a filleted core leaves 4 mm concave
# rounds that ./check reads as open clip channels (R270, MEASURED)
shell = cad.hollow(body, WALL, core=lambda t: cad.profile_body(SIDE, PLAN, spline=False, fillet=None,
                                                               inset=t))
tick("body + hollow")
back, front = cad.split(shell, "Z", at=SPLIT, lip=1.2)
tick("split")


# the fixed back holds the board: pads 0.1 mm under it, fences off its
# ends (the east fence split round A's ribbon)
def floor_top(x, y):
    return bottom_z(back, x, y) + WALL - 0.5          # 0.5 mm into the floor


pads_ = [box(x - 4, x + 4, y - 4, y + 4, floor_top(x, y), BB.ZMin - 0.1)
         for x in (BB.XMin + 12, BB.XMax - 12) for y in (-24, 24)]
fences = [box(BB.XMin - 1.8, BB.XMin - 0.3, -8, 8, floor_top(BB.XMin - 1, 0), PT - 1.0)]
fences += [box(BB.XMax + 0.3, BB.XMax + 1.8, y0, y0 + 5, floor_top(BB.XMax + 1, y0 + 2.5), PT - 1.0)
           for y0 in (-14.5, 9.5)]
back = cad.fuse_one(back, *pads_, *fences)
# screws from the back into insert bosses (1.4 d + 0.1 pockets, R270): two
# in the right belly, two over the board's top-left (clear of the D-pad)
SY_TOP = (33.6 + Y1 - WALL) / 2               # between the plugs' leads and the top wall
SCREWS = [(X1 - 28.0, Y0 + 11.0), (X1 - 28.0, Y1 - 11.0), (DPAD[0] - 12.0, SY_TOP), (DPAD[0] + 14.0, SY_TOP)]
screws = []
for x, y in SCREWS:
    at = (x, y, bottom_z(back, x, y))
    # the boss foot 0.1 over the back's floor, measured round the boss
    # before the hole (R425: at LENGTH 290 a screw on the belly's ramp put
    # the foot into the floor)
    # (R500: sampled on two rings under the 2.8 mm sleeve - at LENGTH 290
    # the crowned floor rose 0.2 mm between the old 5 points, MEASURED)
    ring = [(0.0, 0.0)] + [(rr * math.cos(math.radians(a_)), rr * math.sin(math.radians(a_)))
                           for rr in (1.5, 3.0) for a_ in range(0, 360, 30)]
    z0 = max(bottom_z(back, x + ex, y + ey) for ex, ey in ring) + WALL + 0.1
    back, front = cad.screw_through(back, front, at, size="M2", ribs=0)
    top = Z_FACE - WALL
    front = cad.fuse_one(front, cyl(2.8, (x, y, z0), top - z0 + 0.5))
    front = cad.cut(front, cyl(1.6, (x, y, z0 - 0.1), 6.5))
    screws.append(cad.screw("csk_phillips", "M2", 6, at=at, axis="+Z"))
tick("back + screws")

# the cover glass over a gloss-black mask: two layers that fill ONE
# opening in the face exactly (R270), the mask's window exactly over the
# screen's 25.6 x 13.5 active area (+0.4 each side) - R420: the whole
# glass reads as one black screen, no lighter module frame shows
sx_, sy_, sz_ = centre(screen)
lx, ly, _ = centre(led)
gy0, gy1 = ly - 4.2, Y1 - 4.0                      # the LED's window 2 mm inside the glass
# R425: >= 1 mm of glass into the opening (held) and >= 1 mm of mask
# under it (printable): a thin wall gets a mask that hangs below it
GLASS_T = max(1.0, WALL - 1.0)
MASK_Z0 = Z_FACE - GLASS_T - 1.0
front, glass = insert(front, cad.rounded_box(GLASS_W, gy1 - gy0, 6, 6.0,
                                             at=(-GLASS_W / 2, gy0, Z_FACE - WALL)))
glass, bezel = insert(glass, box(-300, 300, -200, 200, Z_FACE - 10, Z_FACE - GLASS_T))
if MASK_Z0 < Z_FACE - WALL - 0.01:
    bezel = cad.fuse_one(bezel, cad.rounded_box(GLASS_W, gy1 - gy0, (Z_FACE - WALL) - MASK_Z0 + 0.3, 6.0,
                                                at=(-GLASS_W / 2, gy0, MASK_Z0)))
ACTIVE = (25.6 + 0.8, 13.5 + 0.8)
bezel = cad.cut(bezel, cad.rounded_box(ACTIVE[0], ACTIVE[1], 6, 0.8,
                                       at=(sx_ - ACTIVE[0] / 2, sy_ - ACTIVE[1] / 2, Z_FACE - 4)))
bezel = cad.cut(bezel, cyl(2.2, (lx, ly, Z_FACE - 4), 6))         # the LED's window in the mask
# board retention: a rib under the mask down onto the board's spine (0.2
# mm off it), clear of the screen and the USB-C module
bezel = cad.fuse_one(bezel, box(SHIFT + 28, SHIFT + 30, -8, 8, BB.ZMax + 0.2, MASK_Z0 + 0.5))
# the LED: a light pipe up to 0.3 mm under the glass, seen through the mask
pipe = cad.lens(3.6, (Z_FACE - GLASS_T - 0.3) - (ap.bbox(led).ZMax + 0.4), dome=0.4,
                at=(lx, ly, ap.bbox(led).ZMax + 0.4), axis="+Z")
FACE_FRACTION = GLASS_W * (gy1 - gy0) / (2 * X1 * (Y1 - Y0))
print("WINDOW %.0f x %.0f = %.0f %% of the face" % (GLASS_W, gy1 - gy0, 100 * FACE_FRACTION))
# the cabled keys' holders: two posts from the back's floor to 0.1 mm
# under each module (the cap holds it from above) - away from its pins
for m in (btn_a, btn_b):
    mb_ = ap.bbox(m)
    for yy in (mb_.YMin + 3.0, mb_.YMax - 5.0):
        xx = mb_.XMax - 6.0
        back = cad.fuse_one(back, box(xx, xx + 3.0, yy, yy + 2.0, floor_top(xx + 1.5, yy + 1.0), mb_.ZMin - 0.1))
# keys: caps through the face (flange / plate 0.1 mm behind it), plungers
# to 0.16 mm over each module's own cap
base_z = Z_FACE - WALL - 0.9
caps = {}
dx, dy = DPAD
cross = cad.fuse_one(cad.rounded_box(26, 8.5, Z_FACE + 1.4 - base_z, 1.6, at=(dx - 13, dy - 4.25, base_z)),
                     cad.rounded_box(8.5, 26, Z_FACE + 1.4 - base_z, 1.6, at=(dx - 4.25, dy - 13, base_z)))
front = cad.opening_for(front, cross, clearance=0.25, chamfer=0.4, axis="+Z")
# the hidden rocker plate: one plunger onto each of the four switches
pxs = [centre(m) for m in pads]
plate = cad.rounded_box(34, 52, 0.8, 5, at=(dx - 17, dy - 26, base_z))
plungers = [cyl(2.2, (x, y, ap.bbox(m).ZMax + 0.16), base_z - ap.bbox(m).ZMax + 0.34)
            for (x, y, _), m in zip(pxs, pads)]
caps["DPad_Cap"] = cad.fuse_one(cross, plate, *plungers)
for nm, m in (("A_Cap", btn_a), ("B_Cap", btn_b)):
    x, y, _ = centre(m)
    cap = cad.button_cap(12, (Z_FACE + 1.6) - base_z, dome=0.8, flange=1.5, at=(x, y, base_z), axis="+Z")
    front = cad.opening_for(front, cap, clearance=0.25, chamfer=0.4, axis="+Z")
    caps[nm] = cad.fuse_one(cap, cyl(3.0, (x, y, ap.bbox(m).ZMax + 0.16), base_z - ap.bbox(m).ZMax + 0.34))
# USB-C in the bottom edge: a pocket brings the wall to 0.25 mm off the mouth
ub = ap.bbox(usb)
ux, uz = (ub.XMin + ub.XMax) / 2, PT + 5.9
pocket = cad.rounded_box(13, 6, 9, 3, at=(ux - 6.5, Y0 - 1, uz - 4.5), edges="y")
pocket = pocket.common(box(-300, 300, -200, ub.YMin - 1.3, -50, 50))
# (R425: the liner starts 0.5 mm inside the pocket whatever the wall - at
# WALL 1.7 a liner from the wall's own inner face missed the pocket)
liner = cad.cut(cad.rounded_box(17, 1.55, 13, 4, at=(ux - 8.5, ub.YMin - 1.8, uz - 6.5), edges="y"), pocket)
front = cad.fuse_one(cad.cut(front, pocket), liner.common(box(-300, 300, -200, 200, SPLIT + 1.3, 50)))
front = cad.socket_opening(front, usb, margin=1.5)
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# parting-line reveal just above the seam, round the whole device
front = cad.groove_ring(front, "Z", SPLIT + 2.2, w=0.8, depth=0.6)
# soft-touch grip pads: inserts that fill a recess in each belly, under
# the palms (an insert: no overlap, no gap)
grips = []
GRIP_X = (X1 - 0.25 * LENGTH + 4.0, X1 - 26.0)     # under the palm, inboard of the feet
GRIP_Y = (Y0 + 0.18 * DEPTH, Y0 + 0.6 * DEPTH)
GRIP_SINK = 1.05                                   # recess depth: the pad sits 1 mm inside the back
for sgn in (-1, 1):
    x0, x1 = sorted((sgn * GRIP_X[0], sgn * GRIP_X[1]))
    pad_cut = cad.rounded_box(x1 - x0, GRIP_Y[1] - GRIP_Y[0], 4.0, 6.0, at=(x0, GRIP_Y[0], Z_BOT - 2.0))
    back, g_ = insert(back, pad_cut.common(box(-300, 300, -200, 200, Z_BOT - 2.0, Z_BOT + GRIP_SINK)))
    # the pad stands 0.3 mm proud of the belly (soft under the palm)
    grips.append(g_.cut(box(-300, 300, -200, 200, Z_BOT - 3.0, Z_BOT - 0.3)))
# a battery door seam and finger notch on the back, vents, a model mark
door_x = 0.0
back = cad.groove_outline(back, [(door_x - 30, -24), (door_x + 30, -24), (door_x + 30, 0), (door_x - 30, 0)],
                          view="-Z", w=0.6, depth=0.5, both_sides=False)
# (R425: the notch is measured beside the seam, half the wall deep - one
# measured IN the seam's groove left a 0.3 mm skin at WALL 2.3)
back = cad.cut(back, cad.rounded_box(10, 3, 1.5 + 0.5 * WALL, 1.4,
                                     at=(door_x - 5, -25.5, bottom_z(back, door_x, -27.5) - 1.5)))
back = cad.grille(back, (door_x, 14, bottom_z(back, door_x, 14)), (0, 0, -1), (50, 12), kind="slot", hole=2.0,
                  pitch=4.5)
back = cad.text(back, "ATECH AX-1", (door_x, -12, bottom_z(back, door_x, -12)), (0, 0, -1), 4.5, depth=0.4,
                mode="deboss", up=(0, 1, 0))
# rubber feet in the bellies, outboard of the grip pads
feet = []
FOOT_IN = max(18.0, 2.5 * EDGE + 9.0)                # clear of the rolled underside
for x, y in ((-(X1 - FOOT_IN), Y0 + FOOT_IN), (-(X1 - FOOT_IN), Y1 - FOOT_IN), (X1 - FOOT_IN, Y0 + FOOT_IN),
             (X1 - FOOT_IN, Y1 - FOOT_IN)):
    # R500: a short restyle brings a foot under a screw head (LENGTH 214:
    # Foot_2 on Screw_3, MEASURED) - step it toward the middle till clear
    yc = (Y0 + Y1) / 2
    for _ in range(20):
        if min(math.hypot(x - sx, y - sy) for sx, sy in SCREWS) >= 8.0:
            break
        y += 1.0 if y < yc else -1.0
    zb = bottom_z(back, x, y)
    back = cad.cut(back, cyl(3.1, (x, y, zb - 1), 2.0))
    feet.append(cad.foot(6, 1.4, style="dome", at=(x, y, zb + 0.9)))      # 0.5 proud: z = 0
# a vent slot row in the top edge, over the board
front = cad.grille(front, (SHIFT, Y1, (Z_FACE + SPLIT) / 2 + 1.5), (0, 1, 0), (40, 9), kind="slot", hole=1.6,
                   pitch=4.0)
# lettering: A / B on the caps, arrows on the D-pad, ATECH under the glass
for nm, t in (("A_Cap", "A"), ("B_Cap", "B")):
    x, y, _ = centre(btn_a if nm == "A_Cap" else btn_b)
    caps[nm] = cad.text(caps[nm], t, (x, y, Z_FACE + 1.6), (0, 0, 1), 5.5, depth=0.4, mode="deboss", up=(0, 1, 0))
arrows = []
for ang in (0, 90, 180, 270):
    a = math.radians(ang)
    cx, cy = dx + 9.0 * math.cos(a), dy + 9.0 * math.sin(a)
    tri = Part.makePolygon([V(cx + 2.0 * math.cos(a), cy + 2.0 * math.sin(a), Z_FACE + 1.1),
                            V(cx + 1.6 * math.cos(a + 2.1), cy + 1.6 * math.sin(a + 2.1), Z_FACE + 1.1),
                            V(cx + 1.6 * math.cos(a - 2.1), cy + 1.6 * math.sin(a - 2.1), Z_FACE + 1.1),
                            V(cx + 2.0 * math.cos(a), cy + 2.0 * math.sin(a), Z_FACE + 1.1)])
    arrows.append(Part.Face(tri).extrude(V(0, 0, 1)))
caps["DPad_Cap"] = cad.cut(caps["DPad_Cap"], arrows)
front = cad.text(front, "ATECH", (0, (Y0 + gy0) / 2, top_z(front, 0, (Y0 + gy0) / 2)), (0, 0, 1), 5, depth=0.4,
                 mode="deboss", up=(0, 1, 0))
# a raised rim round the cover glass (0.6 mm proud, 2 mm wide)
rim = cad.cut(cad.rounded_box(GLASS_W + 4, gy1 - gy0 + 4, 1.2, 8.0, at=(-GLASS_W / 2 - 2, gy0 - 2, Z_FACE - 0.6)),
              cad.rounded_box(GLASS_W, gy1 - gy0, 3, 6.0, at=(-GLASS_W / 2, gy0, Z_FACE - 1)))
front = cad.fuse_one(front, rim)
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o


o = part("Back", back)
o.ViewObject.ShapeColor = cad.color(COLOURS["Back"])
o = part("Front", front)
o.ViewObject.ShapeColor = cad.color(COLOURS["Front"])
o = part("Bezel", bezel)
o.ViewObject.ShapeColor = cad.color(COLOURS["Bezel"])
o = part("Cover_Glass", glass)
o.ViewObject.ShapeColor = cad.color(COLOURS["Cover_Glass"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Cover_Glass"])
for nm, sh in caps.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["AB"] if nm in ("A_Cap", "B_Cap") else COLOURS["DPad"])
o = part("LED_Pipe", pipe)
o.ViewObject.ShapeColor = cad.color(COLOURS["LED_Pipe"])
o.ViewObject.Transparency = cad.transparency("glass")
for i, sh in enumerate(grips):
    o = part("Grip_" + "LR"[i], sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Grip"])
for i, sh in enumerate(feet):
    o = part("Foot_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Foot"])
for i, sh in enumerate(screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
print("TOTAL %.1f s" % (time.time() - T0))
