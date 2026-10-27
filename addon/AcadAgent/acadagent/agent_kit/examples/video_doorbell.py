"""Example: "a video doorbell" - a tall rounded slab on a wall plate, a big ring button.

fork this file for a doorbell / wall-mounted product (a video doorbell, an
intercom, a keypad, a wall sensor, a thermostat - anything screwed flat to a
wall with its face toward a visitor); change PARAMETERS and the outlines.
ARCHETYPE: doorbell

How it is built (R270):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board UPRIGHT behind the face (portrait, modules facing the visitor,
    -Y); the BUTTON seated on port 7 - the bottom middle of the board, so
    the big round press sits on the centre line with no ribbon; the glow
    LIGHT on port 9 right beside it, under a frosted ring round the button;
    the DISTANCE SENSOR (someone at the door) on port 6 and the MICROPHONE
    on the pair (13, 14) behind a smoked visor (the sensor gets an OPEN
    aperture through it, the mic a pin-hole cluster and a seal ring); USB-C
    on port 3 in a pocket in the right side. The SPEAKER is CABLED from the
    pair (1, 2) to the top of the slab, over the board: its ribbons fold
    back round the board's right edge, run flat BEHIND the board, rise
    behind the speaker and loop over its top into its sockets - every bend
    round the ribbon's width, no twist (no seated module stands in the way,
    and the slab stays thin). The slab is ONE front silhouette (a rounded
    rectangle) and ONE plan with a crowned face (lines and one arc,
    cad.profile_body), hollowed with its own core and split just behind the
    modules into the Front and the Back; the Back is fused to the wall
    plate, carries the board (pads, ledges) and the speaker (posts), and
    four M2.5 screws from the plate's back run into insert bosses in the
    Front.
  * STAGE B - details: the parting-line reveal, raised trims round the
    speaker grille and the sensor aperture, a ring groove on the button,
    lettering, the plate's two countersunk wall-screw holes with their
    screws.
RESTYLE (R425): WIDTH, HEIGHT, DEPTH, CORNER and WALL drive every outline
and cutter; the hardware (the board, the speaker over it, the ribbons'
U-turn) sets a floor the slab never shrinks below (printed as FLOOR).
DETAILS (visible, 28): 1 tall rounded slab; 2 crowned face; 3 rolled face
edge; 4 wall plate standing proud all round; 5-6 countersunk wall-screw
holes top and bottom with their screws; 7 smoked visor; 8 open sensor
aperture through it; 9 raised sensor trim; 10 mic pin holes; 11 mic seal
ring inside; 12 big round button cap; 13 ring groove on the cap; 14 frosted
glow ring round it; 15 plunger to the button; 16 round speaker grille;
17 raised trim round it; 18 speaker chamber to the driver; 19 USB-C pocket
with liner; 20 parting-line reveal; 21 "ATECH" on the face; 22 rolled edge
on the plate; 23 rib onto the board's spine; 24 board pads and ledges;
25 four screws from the back into insert bosses; 26 posts behind the
speaker; 27 the speaker ribbons flat behind the board; 28 lip keying the
Front into the Back.
Materials: warm-white front, graphite wall plate and trims, smoked visor,
frosted glow ring, brushed button cap, chrome screws.
MEASURED (R500, 2026-10-26): see test_kit_examples_r500 (TIMINGS line).
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
    "Front", "Visor", "Glow_Ring", "Button_Cap", "Sensor_Trim", "Grille_Trim",
    "speaker_2_1_cable_p1", "speaker_2_1_cable_p2",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    # the key cap presses the button through its opening (a declared cover)
    "covers": {"Button_Cap": "button_p7"}}
REVIEW_CLOSEUPS = ["Button_Cap", "Visor", "Grille_Trim"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them. The board and its modules set
# a floor under WIDTH, HEIGHT and DEPTH: below it the slab keeps the
# smallest size that still holds the hardware (printed as FLOOR).
WIDTH = 84.0       # RESTYLE 71..97 width: across the slab (x)
HEIGHT = 196.0     # RESTYLE 166..226 height: the slab, bottom to top (z)
DEPTH = 36.0       # RESTYLE 30..42 length: the plate's face to the crown of the face (y)
CORNER = 26.0      # RESTYLE 22..30 radius: the slab's corners in the front view
WALL = 2.4         # RESTYLE 2.0..2.8 wall
# end RESTYLE
# Device frame: x across, z up, the visitor in front (-Y), the wall behind
# (+Y). The board's frame (fixed: the hardware decides it):
AX = 30.0                      # the centre line: the board's middle, port 7's button
BACK_IN = 4.6                  # the back wall's inner face (the ribbons run behind the board)
PLATE_T = 4.0                  # the wall plate's thickness behind the slab
PLATE_SIDE, PLATE_END = 6.0, 15.0   # the plate stands out round the slab (sides, top / bottom)
EDGE = 2.0 * WALL              # the rolled edge round the face (R425: 2 x WALL keeps the sharp
                               # core's corner wall >= 0.58 WALL - at EDGE 5, WALL 2 left 0.76 mm)
CROWN = 3.0                    # the face's crown (its middle forward of its edges)
SPK_Y, SPK_Z = -11.1, 141.5    # the speaker's centre: over the board's top edge
BUTTON_D = 24.0                # the big round press
RING_R = 21.0                  # the frosted glow ring round it (its outer radius)
VISOR_Z = (77.0, 120.5)        # the smoked visor's band over the board (mic and sensor behind it)
GRILLE_D = 32.0                # the speaker grille
SCREW = "M2.5"
COLOURS = {"Front": "#ece9e2", "Back": "graphite", "Visor": "smoked", "Glow_Ring": "frosted",
           "Button_Cap": "brushed_alu", "Trim": "graphite", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
# the speaker over the board's top edge, its pins up (+Z). Its ribbons
# leave the right edge (+X), fold back round it to run flat BEHIND the
# board, left to the sockets' x, up behind the speaker and over its top
# into its sockets (port 2 lands at x 40, port 1 at x 20: the two never
# cross). R500, MEASURED: under the button the speaker sat in the
# button's slide path, and pins DOWN needs a half twist from these plugs.
YB = 3.5                                          # the ribbons' layer behind the board
PLUG = (63.22, -1.27)                             # each plug's lead end (x, y): MEASURED
SOCK = (SPK_Y + 8.83, SPK_Z + 22.64)              # each socket's lead end (y, z): MEASURED
SPK = (AX - 20.0, AX + 20.0, SPK_Y - 10.1, SPK_Y + 10.1, SPK_Z - 20.0, SPK_Z + 20.0)   # its box: MEASURED
BTN_Z = 9.37                                      # the button module's centre: MEASURED
RIB_X = PLUG[0] + (YB - PLUG[1]) / 2 + 0.6        # the U-turns' outside (+ half the ribbon, + its curve)
RIB_TOP = SOCK[1] + 0.1 + (YB - SOCK[0]) / 2 + 0.8   # the loops over the speaker

# ------------------------------------------------------------ the slab's size
# R425: the knobs, never below what the hardware needs; worked out in the
# board's frame (z from its bottom edge) BEFORE anything is placed. The
# ends are fitted round every hardware point near a corner (end_fit), so a
# tighter CORNER or a shorter slab steps the ends out instead of cutting a
# module. LIFT then stands the plate's foot on z = 0 (./check: the lowest
# point exactly on the desk - a wall product is checked standing up).
M = WALL + 1.0                                    # hardware kept this far inside the skin
W = max(WIDTH, 2 * (max(AX + 0.4, RIB_X - AX) + M))
X0, X1 = AX - W / 2, AX + W / 2
R = min(CORNER, W / 2 - 1.0)
LOW = [(-0.4, 0.2), (60.4, 0.2), (RIB_X, 3.0), (AX - RING_R, BTN_Z), (AX, BTN_Z - RING_R - EDGE)]
HIGH = [(-0.4, 119.8), (60.4, 119.8), (SPK[0], SPK[5]), (SPK[1], SPK[5]), (AX - 17, RIB_TOP),
        (AX + 17, RIB_TOP)]


def end_fit(px, pz, sign):
    """The end (z) a point (px, pz) needs: M inside the skin, round the
    corner of radius R when it lies in a corner's reach."""
    dx = max(X0 + R - px, px - (X1 - R), 0.0)
    if dx <= 0:
        return pz + sign * M
    k = (R - M) ** 2 - dx * dx
    if k < -1e-6:
        raise cad.CadError("the slab is too narrow for its corner radius at x %.1f" % px)
    return pz + sign * (R - math.sqrt(max(k, 0.0)))


Z0 = min(end_fit(px, pz, -1) for px, pz in LOW)
Z1 = max(end_fit(px, pz, 1) for px, pz in HIGH)
grow = max(0.0, HEIGHT - (Z1 - Z0))
LIFT = PLATE_END - (Z0 - grow / 2)                # the board's bottom edge over the desk
Z0, Z1 = Z0 - grow / 2 + LIFT, Z1 + grow / 2 + LIFT
Y_BACK = BACK_IN + WALL                           # the slab's back face = the plate's front
SAG = CROWN * (1 - ((SPK[1] - AX) / (W / 2 + 3)) ** 2)   # the crown left at the speaker's edge
D = max(DEPTH, Y_BACK - (SPK[2] - 0.8 - WALL - (CROWN - SAG)))
Y_MID = Y_BACK - D                                # the crown of the face
Y_EDGE = Y_MID + CROWN
print("FLOOR slab %.1f x %.1f x %.1f (knobs %.1f x %.1f x %.1f)" % (W, Z1 - Z0, D, WIDTH, HEIGHT, DEPTH))

# ------------------------------------------------------------ hardware
UPRIGHT_FRONT = Rotation(Vector(0, 0, 1), 180)
board = ap.board_object(doc)


def place_board(rot, x0=0.0, y0=None, z0=0.0):
    board.Placement = Placement(Vector(), rot)
    bb = ap.bbox(board)
    board.Placement = Placement(Vector(x0 - bb.XMin, 0 if y0 is None else y0 - bb.YMin,
                                       z0 - bb.ZMin), rot)


place_board(UPRIGHT_FRONT, 0, None, LIFT)        # x 0..60, y -4.5..2.5, z LIFT..LIFT + 120
BB = ap.bbox(board)
btn = ap.seat(doc, "button", 7)                  # bottom middle: the big press
glow = ap.seat(doc, "light", 9)                  # beside it, under the glow ring
tof = ap.seat(doc, "distance_sensor", 6)         # top right: someone at the door
mic = ap.seat(doc, "microphone", (13, 14))       # top left
usb = ap.seat(doc, "usbc", 3)                    # right side, mouth +X


def arc3(c, r, a0, a1, plane, fixed, n=6):
    """n points on an arc (no start point): c, r in `plane` ('XY' / 'XZ' /
    'YZ'), the third coordinate = fixed."""
    out = []
    for i in range(1, n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        u, v = c[0] + r * math.cos(a), c[1] + r * math.sin(a)
        out.append({"XY": (u, v, fixed), "XZ": (u, fixed, v), "YZ": (fixed, u, v)}[plane])
    return out


def line3(p0, p1, step=8.0):
    """Points every `step` mm from p0 (excluded) to p1 (included)."""
    n = max(1, int(math.dist(p0, p1) / step))
    return [tuple(p0[k] + (p1[k] - p0[k]) * i / n for k in range(3)) for i in range(1, n + 1)]


def ribbon_route(z, xd, rd=6.0):
    """From a right-edge plug at height z to the speaker socket at x = xd: a
    U-turn back round the board edge into the layer YB, a run left, a
    quarter turn up at xd, a rise behind the speaker, a loop over it."""
    r = (YB - PLUG[1]) / 2
    pts = arc3((PLUG[0], PLUG[1] + r), r, -90, 90, "XY", z, 6)
    pts += line3(pts[-1], (xd + rd, YB, z))
    pts += arc3((xd + rd, z + rd), rd, -90, -180, "XZ", YB, 5)
    # the loop ends 0.1 mm over the socket's lead end (R500, MEASURED: the
    # API's spline takes its end tangent at the whole cable's scale, so a
    # 2 mm last span looped 42 mm up out of the slab)
    ru = (YB - SOCK[0]) / 2
    zu = SOCK[1] + LIFT + 0.1
    pts += line3(pts[-1], (xd, YB, zu), 12.0)
    pts += arc3(((YB + SOCK[0]) / 2, zu), ru, 0, 180, "YZ", xd, 12)
    return pts


spk, spk_ribs = ap.cable(doc, "speaker", (1, 2), ap.module_placement(
    "speaker", (AX, SPK_Y, SPK_Z + LIFT), face="-Y", cable="+Z"),
    via={2: ribbon_route(LIFT + 29.99, AX + 10), 1: ribbon_route(LIFT + 9.99, AX - 10)})
SB = ap.bbox(spk)
print("RIBBONS top %.2f (allowed %.2f), right %.2f (allowed %.2f)" % (
    max(r_.Shape.BoundBox.ZMax for r_ in spk_ribs), RIB_TOP + LIFT, max(r_.Shape.BoundBox.XMax for r_ in spk_ribs),
    RIB_X))
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, d, h):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(m):
    b = ap.bbox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


def front_y(shape, x, z, nth=0):
    """The front surface's y at (x, z), measured with a ray; nth=1 gives the
    next face in (the front wall's inner face)."""
    s = shape.section(Part.makeLine(V(x, -200, z), V(x, 200, z)))
    ys = sorted(v.Point.y for v in s.Vertexes)
    return ys[nth]


def insert(shell, cutter):
    """(shell with the opening, the piece it removed): a part that fills its
    opening exactly. Exact booleans first, fuzzy (0.01 mm) after."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1:
        piece, rest = shell.common(cutter, 0.01), shell.cut(cutter, 0.01)
    if piece.Volume < 1 or not rest.isValid() or len(rest.Solids) != len(shell.Solids):
        raise cad.CadError("insert: the cutter does not cleanly cross the wall")
    return rest, piece


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


bx_, _by, bz_ = centre(btn)

# ------------------------------------------------------------ the slab
SIDE = cad.rounded_rect_wire(W, Z1 - Z0, R, (AX, 0, (Z0 + Z1) / 2), "Y")
PLAN = [(X0 - 3, Y_EDGE), ("arc", (AX, Y_MID), (X1 + 3, Y_EDGE)), (X1 + 3, Y_BACK), (X0 - 3, Y_BACK)]
body = cad.profile_body(SIDE, PLAN, spline=False, fillet=EDGE)
# the core keeps SHARP inner edges (a filleted core reads as open clip
# channels to ./check - handheld_console.py, R270)
slab = cad.hollow(body, WALL, core=lambda t: cad.profile_body(SIDE, PLAN, spline=False, fillet=None,
                                                              inset=t))
tick("slab")
# the split just behind the modules (their slide paths stay in the Front,
# fitted after them) and in front of the ribbons behind the board
SPLIT_Y = 0.6
front, back = cad.split(slab, "Y", at=SPLIT_Y, lip=1.2)
tick("split")

# ------------------------------------------------------------ the Back: plate, board, speaker
PX0, PX1, PZ0, PZ1 = X0 - PLATE_SIDE, X1 + PLATE_SIDE, Z0 - PLATE_END, Z1 + PLATE_END
plate = cad.rounded_box(PX1 - PX0, PLATE_T + 0.5, PZ1 - PZ0, R + PLATE_SIDE, at=(PX0, Y_BACK - 0.5, PZ0),
                        edges="y")
# pads 0.1 mm behind the board, clear of the ribbons' lanes (x 13..27 and
# 33..47 rising, the plugs' U-turns past x 60); ledges 0.3 mm under and
# over its ends; two posts 0.2 mm behind the speaker, outside its sockets
PAD_Y = BB.YMax + 0.1
pads = [box(x, x + 8, PAD_Y, BACK_IN + 0.5, BB.ZMin + z, BB.ZMin + z + 8) for x, z in
        ((2, 4), (2, 100), (50, 46), (50, 100))]
ledges = [box(x, x + 8, -3.0, BACK_IN + 0.5, z0, z1) for x in (2, 50)
          for z0, z1 in ((BB.ZMin - 2.3, BB.ZMin - 0.3), (BB.ZMax + 0.3, min(BB.ZMax + 2.3, SB.ZMin - 0.1)))]
posts = [box(x, x + 2, SB.YMax + 0.2, BACK_IN + 0.5, SB.ZMin + 2, SB.ZMin + 22) for x in
         (SB.XMin + 0.5, SB.XMax - 2.5)]
back = cad.fuse_one(back, plate, *pads, *ledges, *posts)
tick("back")

# four M2.5 screws from the plate's back into insert bosses in the Front,
# beside the board (clear of the ribbons' U-turns low on the right, the
# USB-C pocket and the visor); heat-set insert pockets (1.4 d + 0.1) in sleeves
SX = (X0 + WALL + 3.05, X1 - WALL - 3.05)
SCREWS = [(SX[0], BB.ZMin + 40.0), (SX[0], BB.ZMin + 126.0), (SX[1], BB.ZMin + 66.0), (SX[1], BB.ZMin + 126.0)]
Y_PB = Y_BACK + PLATE_T                           # the plate's back face (on the wall)
screws = []
for x, z in SCREWS:
    back, front = cad.screw_through(back, front, (x, Y_PB, z), size=SCREW, ribs=0)
    yb = BACK_IN - 0.1
    front = cad.fuse_one(front, cyl(3.0, (x, yb, z), (0, -1, 0), 10.0))
    front = cad.cut(front, cyl(1.8, (x, yb + 0.5, z), (0, -1, 0), 9.5))
    # the length screw_through prints: through the plate into the pilot,
    # its tip 0.3 mm short of the pilot's bottom
    reach = (BACK_IN - 0.1) - front_y(front, x, z, nth=1)
    lid_t = Y_PB - BACK_IN
    length = int(min(lid_t + 0.85 * reach, lid_t + 0.1 + min(reach, 4.0 * 2.5 + 1.0) - 0.3))
    screws.append(cad.screw("csk_phillips", SCREW, length, at=(x, Y_PB, z), axis="-Y"))
tick("screws")

# ------------------------------------------------------------ the Front: openings
# board retention: a rib from the face onto the board's spine (0.2 mm off)
y_in = front_y(front, AX, BB.ZMin + 50, nth=1)
front = cad.fuse_one(front, box(AX - 1, AX + 1, y_in - 0.5, BB.YMin - 0.2, BB.ZMin + 40, BB.ZMin + 60))
# the speaker: a round grille, a chamber tube from the wall to 0.5 mm off
# the driver, ribs either side of it 0.2 mm off (with the posts behind it,
# it is held - R442)
sx_, sz_ = AX, SPK_Z + LIFT
y_spk = front_y(front, sx_, sz_)
front = cad.speaker_grille(front, (sx_, y_spk, sz_), (0, -1, 0), GRILLE_D, ring_pitch=2.6, hole=1.5)
y_spk_in = front_y(front, sx_ + GRILLE_D / 2 + 2, sz_, nth=1)
front = cad.fuse_one(front, cad.cut(cyl(19.0, (sx_, SB.YMin - 0.5, sz_), (0, -1, 0),
                                        (SB.YMin - 0.5) - y_spk_in + 1.0),
                                    cyl(17.4, (sx_, SB.YMin, sz_), (0, -1, 0), 40)),
                     *[box(x0, x1, y_spk_in - 0.5, SB.YMin + 8, SB.ZMin + 4, SB.ZMin + 30)
                       for x0, x1 in ((SB.XMin - 2.0, SB.XMin - 0.2), (SB.XMax + 0.2, SB.XMax + 2.0))])
# the button: a big round cap through the face, its flange 0.1 mm behind
# the wall, a plunger to 0.16 mm off the module's own cap
bb_ = ap.bbox(btn)
y_btn = front_y(front, bx_, bz_)
y_base = max(front_y(front, bx_ + dx, bz_, nth=1) for dx in (-BUTTON_D / 2 - 1.5, 0, BUTTON_D / 2 + 1.5)) + 0.9
cap = cad.button_cap(BUTTON_D, y_base - (y_btn - 1.8), dome=1.0, flange=1.5, at=(bx_, y_base, bz_), axis="-Y")
front = cad.opening_for(front, cap, clearance=0.25, chamfer=0.5, axis="-Y")
cap = cad.fuse_one(cap, cyl(3.0, (bx_, bb_.YMin - 0.16, bz_), (0, -1, 0), (bb_.YMin - 0.16) - y_base + 0.5))
# the glow ring: a frosted bezel round the cap's opening that fills its
# ring in the face (an insert - its hole IS the cap's opening, so no island
# of wall is left between them), the light on port 9 behind its left side
ring_cut = cad.cut(cyl(RING_R, (bx_, y_btn + 6, bz_), (0, -1, 0), 14),
                   cyl(BUTTON_D / 2 + 0.25, (bx_, y_btn + 8, bz_), (0, -1, 0), 18))
front, ring = insert(front, ring_cut)
# the smoked visor over the mic and the sensor: an insert that fills its
# window in the face
VX0, VX1 = X0 + WALL + 4.0, X1 - WALL - 4.0
visor_cut = cad.rounded_box(VX1 - VX0, 30, VISOR_Z[1] - VISOR_Z[0], 5.0, at=(VX0, Y_MID - 10, BB.ZMin + VISOR_Z[0]),
                            edges="y")
front, visor = insert(front, visor_cut)
# the sensor sees through an OPEN aperture in the visor (a ToF needs no
# glass in front of it); the mic hears through a pin-hole cluster and a
# seal ring from the visor back to 0.3 mm off its face
tx_, _ty, tz_ = centre(tof)
mx_, _my, mz_ = centre(mic)
TOF_AP = (14.0, 8.0)                             # >= the ToF's 10 x 6 open aperture
visor = cad.cut(visor, cad.rounded_box(TOF_AP[0], 30, TOF_AP[1], 3.0,
                                       at=(tx_ - TOF_AP[0] / 2, Y_MID - 10, tz_ - TOF_AP[1] / 2), edges="y"))
y_mic = front_y(visor, mx_, mz_)
visor = cad.speaker_grille(visor, (mx_, y_mic, mz_), (0, -1, 0), 7.0, ring_pitch=2.2, hole=1.2)
y_mic_in = front_y(visor, mx_ + 6, mz_, nth=1)
mb_ = ap.bbox(mic)
visor = cad.fuse_one(visor, cad.cut(cyl(6.5, (mx_, mb_.YMin - 0.3, mz_), (0, -1, 0),
                                        (mb_.YMin - 0.3) - y_mic_in + 0.5),
                                    cyl(5.3, (mx_, mb_.YMin + 1, mz_), (0, -1, 0), 40)))
# USB-C on the right: a pocket brings the wall to 0.25 mm off the mouth
# (a real plug reaches it), a liner round the pocket, then the opening
ub = ap.bbox(usb)
uy, uz = -5.9, (ub.ZMin + ub.ZMax) / 2            # the receptacle: 5.9 mm in front of the PCB
# (the plug's overmould: 15 along the socket's 10 mm side (z), 7.5 across
# it - its edge kept 0.9 mm clear of the parting-line reveal)
pocket = xprism(uy - 3.75, uy + 3.75, uz - 7.5, uz + 7.5, ub.XMax + 1.3, X1 + 5, 3)
liner = cad.cut(xprism(uy - 5.75, min(uy + 5.75, SPLIT_Y - 0.4), uz - 9.5, uz + 9.5, ub.XMax + 0.25, X1 - 1.0, 3.5),
                pocket)
front = cad.fuse_one(cad.cut(front, pocket), liner)
front = cad.socket_opening(front, usb, margin=1.5)
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# parting-line reveal round the slab, just in front of the seam
front = cad.groove_ring(front, "Y", SPLIT_Y - 1.4, w=0.8, depth=0.6)
# a raised graphite trim round the speaker grille and round the sensor
# aperture: each fills a recess in the face and stands 0.8 mm proud
# (blind recesses, half the wall deep: a ring cut through the wall would
# leave the grille's disc an island)
TRIM_SINK = 0.5 * WALL
grille_trim = cad.cut(cyl(GRILLE_D / 2 + 3.5, (sx_, y_spk + TRIM_SINK, sz_), (0, -1, 0), TRIM_SINK + 0.8),
                      cyl(GRILLE_D / 2 + 1.0, (sx_, y_spk + 6, sz_), (0, -1, 0), 10))
front = cad.cut(front, grille_trim)
sensor_trim = cad.cut(cad.rounded_box(TOF_AP[0] + 5, 30, TOF_AP[1] + 5, 4.0,
                                      at=(tx_ - TOF_AP[0] / 2 - 2.5, Y_MID - 10, tz_ - TOF_AP[1] / 2 - 2.5),
                                      edges="y"),
                      cad.rounded_box(TOF_AP[0], 40, TOF_AP[1], 3.0,
                                      at=(tx_ - TOF_AP[0] / 2, Y_MID - 15, tz_ - TOF_AP[1] / 2), edges="y"))
y_tof = front_y(visor, tx_ - TOF_AP[0] / 2 - 1.5, tz_)
sensor_trim = sensor_trim.common(box(-500, 500, y_tof - 0.8, y_tof + TRIM_SINK, -500, 500))
visor = cad.cut(visor, sensor_trim)
# a ring groove on the button's face, lettering on the slab
y_cg = front_y(cap, bx_ + BUTTON_D / 2 - 2.9, bz_)      # the dome's surface at the groove
cap = cad.cut(cap, cad.cut(cyl(BUTTON_D / 2 - 2.6, (bx_, y_cg - 0.5, bz_), (0, 1, 0), 0.9),
                           cyl(BUTTON_D / 2 - 3.2, (bx_, y_cg - 1.0, bz_), (0, 1, 0), 2.0)))
zt = BB.ZMin + 52
front = cad.text(front, "ATECH", (AX, front_y(front, AX, zt), zt), (0, -1, 0), 6.5, depth=0.5, mode="deboss")
# the plate: countersunk wall-screw holes top and bottom, their screws
wall_screws = []
for z in (PZ0 + PLATE_END / 2, PZ1 - PLATE_END / 2):
    plate_at = (AX, Y_BACK - 0.5, z)                 # the plate's exposed face
    back = cad.countersink(back, plate_at, "+Y", 4.2, 8.4, 90.0)
    wall_screws.append(cad.screw("csk_phillips", "M4", 25, at=plate_at, axis="+Y"))   # into wall plugs
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
o = part("Visor", visor)
o.ViewObject.ShapeColor = cad.color(COLOURS["Visor"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Visor"])
o = part("Glow_Ring", ring)
o.ViewObject.ShapeColor = cad.color(COLOURS["Glow_Ring"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Glow_Ring"])
o = part("Button_Cap", cap)
o.ViewObject.ShapeColor = cad.color(COLOURS["Button_Cap"])
o = part("Grille_Trim", grille_trim)
o.ViewObject.ShapeColor = cad.color(COLOURS["Trim"])
o = part("Sensor_Trim", sensor_trim)
o.ViewObject.ShapeColor = cad.color(COLOURS["Trim"])
for i, sh in enumerate(screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
for i, sh in enumerate(wall_screws):
    o = part("Wall_Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
print("TOTAL %.1f s" % (time.time() - T0))
