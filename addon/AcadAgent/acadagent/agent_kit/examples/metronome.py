"""Example: "a digital metronome" - the classic pyramid: a click, a tempo dial, a BPM screen, a tap key, a beat light.

fork this file for a metronome / pyramid product (a metronome, a tuner, a
pyramid clock, a tapering tower - anything that narrows from a wide foot
to a small flat top and leans back); change PARAMETERS and the outlines.
ARCHETYPE: metronome

How it is built (R620):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board UPSIDE-DOWN UPRIGHT (INVERTED: modules face the front -Y, port 7
    at the TOP centre) low in the pyramid. The click speaker (13, 14) hangs
    out to the right behind a round grille; the knob (4, 5) hangs out to
    the left inside a round DIAL POD that stands out of the face, its cap
    flush with the pod's rim and a frosted ring over its 12 LEDs in the
    well's floor; the screen (9, 10, portrait) and the beat light (2)
    behind ONE smoked lens whose outline follows the taper; USB-C (1) in a
    pocket in the left flank; the TAP button CABLED from port 7 straight
    up into the apex (a twist-free straight rise) under a big brass key,
    held by a cradle. The body is a front-view trapezoid meeting a
    side-view trapezoid (every face a plane), its four sloping corners
    rounded, cut by a leaning foot plane; everything is built in a LOCAL
    frame (front face vertical) and tilted back ALPHA (half the back's
    slope) as one Placement, so front and back lean in alike and the foot
    stands flat on a walnut plinth. Hollowed with its own core, split
    front / back behind the board with a lip; three M2.5 screws from
    behind into heat-set insert bosses on pads in the front half; the
    plinth pegged into the back half's floor.
  * STAGE B - details: the grille's brass trim, tempo ticks round the
    pod, legends, the parting-line reveal, back vents, lettering on the
    back and the plinth, rubber feet.
DETAILS (visible, 31): 1 pyramid body leaning back; 2 four rounded
sloping corners; 3 rolled top edge; 4 walnut plinth with a soft edge;
5 smoked lens following the taper; 6 recessed black bezel round it;
7 portrait BPM window in the mask; 8 beat-light window in the mask;
9 round dial pod standing out of the face, the cap flush in its well;
10 frosted ring over the knob's LED ring; 11 brass bezel in the pod's
rim; 12 eleven tempo ticks round the pod; 13 "TEMPO" under the dial;
14 round click grille; 15 brass trim round the grille; 16 big brass TAP
key with flange and plunger; 17 "TAP" on the key; 18 raised ring round
the tap key; 19 USB-C pocket with liner in the left flank; 20 parting-line
reveal; 21 slot vents high on the back; 22 "ATECH" on the back;
23 "ATECH" on the plinth; 24 three countersunk screws on the back;
25 four rubber feet. Inside: 26 speaker chamber ring; 27 rib from the
front onto the board's spine; 28 board ledges and standoffs; 29 tap
cradle (cheeks + back plate); 30 screw pads with heat-set insert sleeves;
31 lip and groove keying front to back.
Materials: wood body, walnut plinth, brass key, bezel and trim, smoked
lens, black bezel, frosted dial ring, chrome screws, rubber feet.
MEASURED (R620, 2026-10-26): ./check CHECK PASS - see test_kit_examples_r500
(R500_TIMINGS line).
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
    "Front", "Bezel", "Lens", "Dial_Ring", "Dial_Bezel", "Grille_Trim", "Tap_Key", "Plinth",
    "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4", "Screw_1", "Screw_2", "Screw_3"],
    # the brass key presses the cabled tap button through its opening
    "covers": {"Tap_Key": "button_7"}}
REVIEW_CLOSEUPS = ["Lens", "Dial_Ring", "Tap_Key"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them (the taper eases itself where
# the hardware needs room: see K below).
HEIGHT = 230.0     # RESTYLE 195..265 height: the body, foot to flat top (local z)
DEPTH = 96.0       # RESTYLE 81..111 length: the body's foot, front to back (y)
TOP_W = 40.0       # RESTYLE 34..46 width: the flat top, side to side (x)
CORNER = 8.0       # RESTYLE 6.8..9.2 radius: the four sloping corner edges
WALL = 2.0         # RESTYLE 1.7..2.3 wall
# end RESTYLE
# R620: the product is built in a LOCAL frame - front face vertical at
# y = YF, x across, z up from the front-bottom edge - and tilted back
# ALPHA as one piece at the end of each stage (the clock's recipe).
BASE_W = 154.0                   # the foot, side to side: the knob and the speaker hang out 20 mm
TOP_D = 38.0                     # the flat top, front to back
SPK_FACE = -20.2                 # the speaker's face in front of the PCB (catalogue: 20.2)
YF = SPK_FACE - 1.5 - WALL       # the front face: 1.5 mm of air in front of the speaker
Z0 = 14.0                        # the board's bottom edge over the foot
TAP_RISE = 36.0                  # the tap button's centre over the board's top edge
TOP_R, FOOT_R = 3.0, 1.2         # the rolled top edge, the softened foot edge
LENS_Z = (88.0, 140.0)           # the smoked lens, bottom and top (local z)
LENS_IN = CORNER + 6.0           # its edge, in from the flanks (follows the taper)
BEZEL, RECESS, LENS_R = 4.0, 1.2, 5.0
DISH_R = 19.0                    # the dial well round the knob (finger room round the 12 mm cap)
RING_R = (5.6, 15.5)             # the frosted ring over the knob's LED ring (LEDs at r 11..13)
GRILLE_D = 32.0
TAP_D = 22.0                     # the brass tap key
PLINTH_T, PLINTH_OUT, RUB = 12.0, 5.0, 1.5
SCREWS = [(-46.0, 80.0), (46.0, 80.0)]       # (x, z) on the back; a third over the tap key (stage A)
COLOURS = {"Front": "wood", "Back": "wood", "Plinth": "#3a2618", "Bezel": "matte_black",
           "Lens": "smoked", "Dial_Ring": "frosted", "Brass": "brass", "Rubber": "rubber",
           "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
# the tilt: half the back's slope, so front and back lean in alike
BETA = math.degrees(math.atan2(DEPTH - TOP_D, HEIGHT))
ALPHA = BETA / 2.0
TAN_A = math.tan(math.radians(ALPHA))
Z_LIFT = RUB + PLINTH_T                       # the body's foot on the plinth
TILT = Placement(V(0, 0, Z_LIFT), Rotation(V(1, 0, 0), -ALPHA), V(0, YF, 0))
TILT_M = TILT.toMatrix()
INVERTED = Rotation(Vector(1, 0, 0), 180)     # face -Y, port 7 at the top, 1-6 on the left
board = ap.board_object(doc)
board.Placement = Placement(V(), INVERTED)
_b = ap.bbox(board)
board.Placement = TILT.multiply(Placement(V(-(_b.XMin + _b.XMax) / 2, 0, Z0 - _b.ZMin), INVERTED))
spk = ap.seat(doc, "speaker", (13, 14))       # the click: hangs out to the right, low
knob = ap.seat(doc, "knob", (4, 5))           # the tempo dial: hangs out to the left
scr = ap.seat(doc, "screen", (9, 10))         # portrait BPM, behind the lens
led = ap.seat(doc, "light", 2)                # the beat light, behind the lens
usb = ap.seat(doc, "usbc", 1)                 # left flank, mouth -X
# the tap button: port 7 sits on the board's TOP edge here, so its ribbon
# rises straight up into the apex (face -Y, pins down: no twist)
tap, tap_rib = ap.cable(doc, "button", 7, TILT.multiply(ap.module_placement(
    "button", (0, -4.8, Z0 + 120 + TAP_RISE), face="-Y", cable="-Z")))
tick("hardware")


def lbox(obj):
    """An Atech object's box in the LOCAL (untilted) frame."""
    g = (obj.Mesh if hasattr(obj, "Mesh") else obj.Shape).copy()
    g.Placement = TILT.inverse().multiply(g.Placement)
    return g.BoundBox


def W_(s):
    """Local frame -> world (tilted back, standing on the plinth)."""
    s = s.copy()
    s.transformShape(TILT_M)
    return s


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, d, h):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(b):
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


BB = lbox(board)
SB, KB, SC, LB, UB, TB = [lbox(m) for m in (spk, knob, scr, led, usb, tap)]
RB = lbox(tap_rib[0])

# ------------------------------------------------------------ the silhouette
# half-width hw(z) = HW0 - K z (front view) and the back's y yb(z) (side
# view); the taper K eases where a hardware corner or the lens's windows
# need the room (a short or narrow-topped restyle widens the top instead
# of cutting the flank into the knob)
HW0 = BASE_W / 2.0
SCREEN_WIN = (13.5 + 2.0, 25.6 + 2.0)          # mask window over the portrait active area (+1 each side)
LED_WIN = 19.0                                  # mask window over the 17 x 17 LEDs
sx, _sy, sz = centre(SC)
lx, _ly, lz = centre(LB)
need = [(max(abs(b.XMin), abs(b.XMax)) + WALL + 2.0, b.ZMax) for b in (SB, KB, SC, LB, UB, TB, BB)]
need += [(abs(sx) + SCREEN_WIN[0] / 2 + 2.0 + LENS_IN, sz + SCREEN_WIN[1] / 2),
         (abs(lx) + LED_WIN / 2 + 2.0 + LENS_IN, lz + LED_WIN / 2),
         (abs(sx) + SCREEN_WIN[0] / 2 + 2.0 + LENS_IN, LENS_Z[1])]
K = min([(HW0 - TOP_W / 2.0) / HEIGHT] + [(HW0 - x) / z for x, z in need])
YB0, YB1 = YF + DEPTH, YF + TOP_D
print("TAPER K %.3f (top %.1f wide), lean %.1f deg (back slope %.1f)" % (K, 2 * (HW0 - K * HEIGHT), ALPHA, BETA))


def hw(z):
    return HW0 - K * z


def yb(z):
    return YB0 - (YB0 - YB1) * z / HEIGHT


def foot_cut(t):
    """Everything above the leaning foot plane, raised t along its normal."""
    k = box(-400, 400, -400, 400, 0, 800)
    k.rotate(V(0, YF, 0), V(1, 0, 0), ALPHA)
    k.translate(V(0, -t * math.sin(math.radians(ALPHA)), t * math.cos(math.radians(ALPHA))))
    return k


def frustum(t, z1=None):
    """The body inset t: the front view's trapezoid (extruded along Y)
    meets the side view's (extruded along X) - every face a PLANE (R620,
    MEASURED: a ruled loft gave B-spline faces and the click grille's cut
    came out INVALID) - cut by the foot, its four sloping corners rounded."""
    z1 = HEIGHT - t if z1 is None else z1
    zb = -30.0
    fv = [V(-(hw(zb) - t), YF + t, zb), V(hw(zb) - t, YF + t, zb), V(hw(z1) - t, YF + t, z1),
          V(-(hw(z1) - t), YF + t, z1)]
    sv = [V(-300, YF + t, zb), V(-300, yb(zb) - t, zb), V(-300, yb(z1) - t, z1), V(-300, YF + t, z1)]
    a = Part.Face(Part.makePolygon(fv + [fv[0]])).extrude(V(0, YB0 + 60 - YF, 0))
    b = Part.Face(Part.makePolygon(sv + [sv[0]])).extrude(V(600, 0, 0))
    s = a.common(b).common(foot_cut(t))
    edges = [e for e in s.Edges if e.BoundBox.ZLength > 0.5 * HEIGHT]
    r = max(CORNER - t, 0.8)
    out = s.makeFillet(r, edges)
    if not out.isValid() or len(out.Solids) != 1:
        raise cad.CadError("frustum: the corner fillet (r %g) failed" % r)
    return out


def on_foot(e):
    return all(abs(v.Point.z - (v.Point.y - YF) * TAN_A) < 1e-3 for v in e.Vertexes)


outer = frustum(0.0, HEIGHT)
outer = cad.soften(outer, TOP_R, [e for e in outer.Edges if e.BoundBox.ZMin > HEIGHT - 1e-3])
outer = cad.soften(outer, FOOT_R, [e for e in outer.Edges if on_foot(e)])
# the core keeps SHARP inner edges (a filleted core leaves concave rounds
# ./check reads as clip channels - the handheld's lesson)
body = cad.hollow(outer, WALL, core=lambda t: frustum(t))
skin = frustum(0.5)                           # clips ribs 0.5 mm under the outer skin
tick("body")
SPLIT_Y = BB.YMax + 0.3                       # behind the board: the front carries every opening
# (R620, MEASURED: cad.split's own lip found "almost no room" on this
# planar trapezoid section at every y tried - the lip is built here: a
# ring from half the wall to 1 mm into the cavity, 1.2 mm behind the split,
# notched round the ledges below; the back gets the matching groove)
front, back = cad.split(body, "Y", at=SPLIT_Y, lip=0)
LIP, LIP_C = 1.2, 0.2


def ring_of(t0, t1, y0, y1):
    """The body's wall band from inset t0 to inset t1, between y0 and y1."""
    return cad.cut(frustum(t0), frustum(t1)).common(box(-300, 300, y0, y1, -100, 400))


T_LIP = max(WALL / 2, 1.2)                    # the back keeps >= 1 mm of skin beside the groove
lip = ring_of(T_LIP, WALL + 1.0, SPLIT_Y - 0.3, SPLIT_Y + LIP)
groove = ring_of(T_LIP - LIP_C, WALL + 0.5, SPLIT_Y - 1.0, SPLIT_Y + LIP + LIP_C)
tick("split")

# ------------------------------------------------------------ back: holds the board
# a ledge under the board's bottom edge, two over its top edge (either
# side of the tap ribbon), standoffs 0.1 mm behind it - each reaching back
# to the sloping wall, clipped 0.5 mm under its skin
YIN = YB0 + 10.0
ledges = [box(BB.XMin + 4, BB.XMax - 4, 0.6, YIN, -5, BB.ZMin - 0.3),
          box(BB.XMin + 4, RB.XMin - 2.5, 0.6, YIN, BB.ZMax + 0.3, BB.ZMax + 2.3),
          box(RB.XMax + 2.5, BB.XMax - 4, 0.6, YIN, BB.ZMax + 0.3, BB.ZMax + 2.3)]
ledges += [box(x, x + 6, BB.YMax + 0.1, YIN, BB.ZMin + z, BB.ZMin + z + 6)
           for x in (BB.XMin + 8, BB.XMax - 14) for z in (20, 60, 100)]
# the tap button's cradle: cheeks 0.3 mm off its sides and a plate 0.1 mm
# behind it (the key presses it backward), clear of its ribbon below
ledges += [box(TB.XMin - 1.8, TB.XMin - 0.3, TB.YMin + 1.0, YIN, TB.ZMin + 1.0, TB.ZMax + 1.0),
           box(TB.XMax + 0.3, TB.XMax + 1.8, TB.YMin + 1.0, YIN, TB.ZMin + 1.0, TB.ZMax + 1.0),
           box(TB.XMin - 1.8, TB.XMax + 1.8, TB.YMax + 0.1, YIN, TB.ZMin + 1.0, TB.ZMax + 1.0)]
# (a ledge that reaches forward of the split keeps out of the front half's walls)
back = cad.fuse_one(back, *[lg.common(skin).cut(front) if lg.BoundBox.YMin < SPLIT_Y else lg.common(skin)
                            for lg in ledges])
# the lip on the front, notched 0.3 mm round the ledges it crosses; its groove in the back
front = cad.fuse_one(front, cad.cut(lip, [cad.rounded_box(lg.BoundBox.XLength + 0.6, lg.BoundBox.YLength + 0.6,
                                                          lg.BoundBox.ZLength + 0.6, 0.0,
                                                          at=(lg.BoundBox.XMin - 0.3, lg.BoundBox.YMin - 0.3,
                                                              lg.BoundBox.ZMin - 0.3))
                                          for lg in ledges[:3]], optional=True))
back = cad.cut(back, groove)
# the third screw: midway between the tap key's flange (and its cradle)
# and the top (R620: a fixed height ran into the key at HEIGHT 195)
SCREWS.append((0.0, (max(TB.ZMax + 1.0, (TB.ZMin + TB.ZMax) / 2 + TAP_D / 2 + 3.0) + HEIGHT - WALL) / 2))
# screw pads in the front half (from the front wall back to 2.5 mm short of
# the split), clear of the knob, the speaker and the tap key
pads = [box(x - 4.5, x + 4.5, YF + WALL - 0.5, SPLIT_Y - 2.5, z - 4.5, z + 4.5).common(skin) for x, z in SCREWS]
# board retention: a rib from the front wall onto the spine (0.2 mm off it)
pads.append(box(-2, 2, YF + WALL - 0.5, BB.YMin - 0.2, BB.ZMin + 48, BB.ZMin + 64))
front = cad.fuse_one(front, *pads)


def ray(shape, p0, p1):
    return [v.Point for v in shape.section(Part.makeLine(V(*p0), V(*p1))).Vertexes]


def back_y(shape, x, z):
    """The rearmost surface point of `shape` along +Y at (x, z)."""
    return max(p.y for p in ray(shape, (x, -80, z), (x, 200, z)))


# screw_through on the halves' pieces round each screw (the clock's
# recipe: on the whole shell a pilot's volume is inside the noise), the
# cuts and bosses applied in one go; a heat-set insert pocket (1.4 d + 0.1)
# in a sleeve at the boss's end
core = frustum(WALL)
screws, csks, bosses, sleeves, pockets = [], [], [], [], []
for x, z in SCREWS:
    yo = back_y(outer, x, z)
    lb = box(x - 7.5, x + 7.5, -40, YIN + 20, z - 7.5, z + 7.5)
    b0, f0 = back.common(lb), front.common(lb.common(box(-300, 300, -100, SPLIT_Y - 1.0, -100, 400)))
    b1, f1 = cad.screw_through(b0, f0, (x, yo, z), size="M2.5", ribs=0)
    csks.append(b0.cut(b1))
    bosses.append(f1.cut(f0))
    ys = min(back_y(core, x + dx, z + dz) for dx in (-3, 0, 3) for dz in (-3, 0, 3)) - 0.1
    sleeves.append(cyl(3.0, (x, ys, z), (0, -1, 0), 10.0))
    pockets.append(cyl(1.8, (x, ys + 0.5, z), (0, -1, 0), 9.5))
    screws.append(cad.screw("csk_phillips", "M2.5", round(yo - ys + 7.9), at=(x, yo, z), axis="-Y"))
back = cad.cut(back, csks)
front = cad.cut(cad.fuse_one(front, *(bosses + sleeves)), pockets)
tick("back + screws")


def on_piece(shape, at, fn, h=24.0):
    """Apply a cutting detail fn to the piece of `shape` round `at` and cut
    what it removed from the whole (the clock's recipe for big shells)."""
    lb = Part.makeBox(2 * h, 2 * h, 2 * h, V(at) - V(h, h, h))
    loc = shape.common(lb)
    res = shape.cut(loc.cut(fn(loc)))
    if not res.isValid() or len(res.Solids) != len(shape.Solids):
        raise cad.CadError("on_piece: the detail at %s broke the part" % (V(at),))
    return res


def tprism(inset, r, z0, z1, y0, y1):
    """A trapezoid that follows the flanks (inset from them) between z0 and
    z1, its corners rounded r, extruded along Y from y0 to y1."""
    pts = [V(-(hw(z0) - inset), y0, z0), V(hw(z0) - inset, y0, z0), V(hw(z1) - inset, y0, z1),
           V(-(hw(z1) - inset), y0, z1)]
    s = Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(0, y1 - y0, 0))
    return cad.fillet_safe(s, r, cad.edges_parallel(s, "Y"))


# ------------------------------------------------------------ the face
# the lens tray: a black bezel set RECESS back in its opening, a pocket for
# the smoked lens, a mask back with the two windows (the clock's tray, its
# outline following the pyramid's flanks)
lz0, lz1 = LENS_Z
front = cad.cut(front, tprism(LENS_IN - BEZEL, LENS_R + BEZEL, lz0 - BEZEL, lz1 + BEZEL, YF - 6, YF + WALL + 1))
yt0, yt1 = YF + RECESS, YF + WALL + 3.0
tray = cad.fuse_one(tprism(LENS_IN - BEZEL, LENS_R + BEZEL, lz0 - BEZEL, lz1 + BEZEL, yt0, YF + WALL + 1),
                    tprism(LENS_IN - 2, LENS_R + 2, lz0 - 2, lz1 + 2, YF + WALL + 0.5, yt1))
y_lens1 = YF + WALL + 1.4
tray = cad.cut(tray, tprism(LENS_IN, LENS_R, lz0, lz1, yt0 - 1, y_lens1))
lens = tprism(LENS_IN, LENS_R, lz0, lz1, yt0 + 0.6, y_lens1 - 0.3)       # 0.3 mm air before the mask
tray = cad.cut(tray, [cad.rounded_box(SCREEN_WIN[0], 10, SCREEN_WIN[1], 1.5,
                                      at=(sx - SCREEN_WIN[0] / 2, yt1 - 5, sz - SCREEN_WIN[1] / 2), edges="y"),
                      cad.rounded_box(LED_WIN, 10, LED_WIN, 3.0, at=(lx - LED_WIN / 2, yt1 - 5, lz - LED_WIN / 2),
                                      edges="y")])
print("DISPLAY lens %.0f wide at its foot, %.0f..%.0f high" % (2 * (hw(lz0) - LENS_IN), lz0, lz1))
# the click: a round grille over the speaker's surround, a chamber ring to
# 0.5 mm off the driver (the sound goes out, not into the case)
gx, _gy, gz = centre(SB)
front = on_piece(front, (gx, YF, gz), lambda s_: cad.speaker_grille(s_, (gx, YF, gz), (0, -1, 0), GRILLE_D,
                                                                     ring_pitch=2.6, hole=1.5), h=22.0)
front = cad.fuse_one(front, cad.cut(cyl(18.5, (gx, SB.YMin - 0.5, gz), (0, -1, 0), (SB.YMin - 0.5) - (YF + 1.0)),
                                    cyl(17.2, (gx, SB.YMin, gz), (0, -1, 0), 40)))
# the dial pod: a round tube standing out of the face round the knob, its
# rim 0.4 mm past the cap's top (R620, MEASURED: a cap standing proud of
# the face is "a module sticking out of the body" - ./check lets only its
# working face look out, so the cap sits FLUSH in a well and the fingers
# reach in round it); the shaft comes through the well's floor 0.5 mm in
# front of the knob's base (MEASURED 10.0 off the PCB), a frosted ring in
# the floor over the 12 LEDs round the shaft (an insert: it fills its opening)
kx, _ky, kz = centre(KB)
k_base = KB.YMax - 10.0                        # the knob's base face (PCB top at KB.YMax)
yf0 = k_base - 0.5                             # the well floor's inner face
y_rim = KB.YMin - 0.4                          # the pod's rim
R_POD = DISH_R + WALL + 1.0
front = cad.cut(cad.fuse_one(front, cyl(R_POD, (kx, yf0, kz), (0, -1, 0), yf0 - y_rim)),
                cyl(DISH_R, (kx, yf0 - WALL, kz), (0, -1, 0), 80))
# the brass bezel: a ring in a rebate round the rim (it fills it exactly)
reb = cad.cut(cyl(R_POD + 1.0, (kx, y_rim - 1.0, kz), (0, 1, 0), 3.5),
              cyl(R_POD - 1.4, (kx, y_rim - 2.0, kz), (0, 1, 0), 6.0))
dial_bezel = front.common(reb)
front = cad.cut(front, reb)
dial_bezel = cad.soften(dial_bezel, 0.5, [e for e in dial_bezel.Edges if e.BoundBox.YMax < y_rim + 1e-3
                                          and e.BoundBox.XLength > 2 * R_POD - 0.5])
ring_cut = cad.cut(cyl(RING_R[1], (kx, yf0 + 1, kz), (0, -1, 0), WALL + 2),
                   cyl(RING_R[0], (kx, yf0 + 2, kz), (0, -1, 0), WALL + 4))
dial_ring = front.common(ring_cut)
# the ring's seat and the shaft's way out
front = cad.cut(front, cyl(RING_R[1], (kx, yf0 + 1, kz), (0, -1, 0), WALL + 2))
# the tap key: a big brass cap through the face (flange 0.1 mm behind the
# wall), a plunger to 0.16 mm off the cabled button's own cap
tx, _ty, tz = centre(TB)
y_base = YF + WALL + 0.9
key = cad.button_cap(TAP_D, y_base - (YF - 1.8), dome=1.0, flange=1.5, at=(tx, y_base, tz), axis="-Y")
front = cad.opening_for(front, key, clearance=0.3, chamfer=0.5, axis="-Y")
key = cad.fuse_one(key, cyl(3.0, (tx, TB.YMin - 0.16, tz), (0, -1, 0), (TB.YMin - 0.16) - y_base + 0.5))
# USB-C in the left flank: a pocket brings the wall to 0.25 mm off the mouth
uy, uz = -5.9, (UB.ZMin + UB.ZMax) / 2         # the receptacle: 5.9 mm in front of the PCB


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


pocket = xprism(uy - 6.5, uy + 6.0, uz - 5.5, uz + 5.5, -(hw(uz - 6) + 5), UB.XMin - 1.3, 3)
liner = cad.cut(xprism(uy - 8.5, min(uy + 8.0, SPLIT_Y - 0.6), uz - 7.5, uz + 7.5, UB.XMin - 0.25,
                       -(hw(uz - 8) + 2), 4), pocket)          # clipped to the skin below
front = cad.fuse_one(cad.cut(front, pocket), liner.common(skin))
tick("face")

# the plinth: a walnut slab under the foot (built in the world frame - the
# foot is flat there), pegged up into the back half's floor
D_W = DEPTH / math.cos(math.radians(ALPHA))    # the foot's depth on the desk
PX0, PX1 = -(HW0 + PLINTH_OUT), HW0 + PLINTH_OUT
PY0, PY1 = YF - PLINTH_OUT, YF + D_W + PLINTH_OUT
plinth = cad.rounded_box(PX1 - PX0, PY1 - PY0, PLINTH_T, CORNER + PLINTH_OUT, at=(PX0, PY0, RUB))
plinth = cad.soften(plinth, 2.5, [e for e in plinth.Edges if e.BoundBox.ZMin > RUB + PLINTH_T - 1e-3])
PEGS = [(-36.0, 0.62 * DEPTH + YF), (36.0, 0.62 * DEPTH + YF)]          # local (x, y): behind the board
peg_w = [TILT.multVec(V(x, y, (y - YF) * TAN_A)) for x, y in PEGS]
plinth = cad.fuse_one(plinth, *[cyl(2.85, (p.x, p.y, Z_LIFT - 1.0), (0, 0, 1), WALL + 2.0) for p in peg_w])
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# a brass trim round the grille, in a 1 mm groove
trim = cad.soften(cad.cut(cyl(GRILLE_D / 2 + 3.4, (gx, YF - 0.6, gz), (0, 1, 0), 1.6),
                          cyl(GRILLE_D / 2 + 1.0, (gx, YF - 1, gz), (0, 1, 0), 3.0)), 0.3)
front = cad.cut(front, cad.cut(cyl(GRILLE_D / 2 + 3.4, (gx, YF - 1, gz), (0, 1, 0), 2.0),
                               cyl(GRILLE_D / 2 + 1.0, (gx, YF - 2, gz), (0, 1, 0), 4.0)))
# eleven tempo ticks round the dial (every 27 deg over 270, the long ones
# at the ends and the top), only where the face is flat
ticks = []
r0 = R_POD + 2.5
for i in range(11):
    a = math.radians(-135.0 + 27.0 * i)
    L = 5.0 if i in (0, 5, 10) else 3.2
    c = V(kx + (r0 + L / 2) * math.sin(a), YF, kz + (r0 + L / 2) * math.cos(a))
    if abs(c.x) + L > hw(c.z) - CORNER - 1.5:
        continue
    t_ = box(-0.6, 0.6, -1.0, 0.5, -L / 2, L / 2)
    t_.rotate(V(0, 0, 0), V(0, 1, 0), math.degrees(a))
    t_.translate(c)
    ticks.append(t_)
front = cad.cut(front, ticks)
# a raised ring round the tap key (0.6 mm proud)
front = cad.fuse_one(front, cad.soften(cad.cut(cyl(TAP_D / 2 + 3.6, (tx, YF + 0.8, tz), (0, -1, 0), 1.4),
                                               cyl(TAP_D / 2 + 2.0, (tx, YF + 1.0, tz), (0, -1, 0), 2)), 0.3))
# legends and lettering
front = cad.text(front, "TEMPO", (kx, YF, kz - R_POD - 9.0), (0, -1, 0), 5, depth=0.4, mode="deboss")
key = cad.text(key, "TAP", (tx, YF - 1.8, tz), (0, -1, 0), 5, depth=0.4, mode="deboss")
# the parting-line reveal round the front half
front = cad.groove_ring(front, "Y", SPLIT_Y - 3.0, w=0.8, depth=0.6)
# slot vents high on the back and its lettering (on the sloping back: the
# normal leans up BETA)
nb = (0, math.cos(math.radians(BETA)), math.sin(math.radians(BETA)))
zv = BB.ZMax + 13.0                           # between the board's top ledges and the tap cradle
back = on_piece(back, (0, back_y(outer, 0, zv), zv),
                lambda s_: cad.grille(s_, (0, back_y(outer, 0, zv), zv), nb, (2 * hw(zv) - 30, 14), kind="slot",
                                      hole=2.0, pitch=4.5), h=40.0)
zt = 90.0
back = on_piece(back, (0, back_y(outer, 0, zt), zt),
                lambda s_: cad.text(s_, "ATECH", (0, back_y(outer, 0, zt), zt), nb, 8, depth=0.5, mode="deboss",
                                    up=(0, -nb[2], nb[1])), h=40.0)
tick("stage B")


# ------------------------------------------------------------ tilt + plinth
parts = {"Front": front, "Back": back, "Bezel": tray, "Lens": lens, "Dial_Ring": dial_ring,
         "Dial_Bezel": dial_bezel, "Grille_Trim": trim, "Tap_Key": key}
parts = {k: W_(v) for k, v in parts.items()}
# the USB-C opening is MEASURED from the module, so it is cut after the tilt
parts["Front"] = cad.socket_opening(parts["Front"], usb, margin=1.5)
screws = [W_(s) for s in screws]
# the pegs' bores through the back's floor (vertical in the world)
parts["Back"] = cad.cut(parts["Back"], [cyl(3.0, (p.x, p.y, Z_LIFT - 1.0), (0, 0, 1), WALL + 3.0) for p in peg_w])
plinth = cad.text(plinth, "ATECH", (0, PY0, RUB + PLINTH_T / 2), (0, -1, 0), 6, depth=0.5, mode="deboss")
rubbers = []
for x in (PX0 + 16.0, PX1 - 16.0):
    for y in (PY0 + 16.0, PY1 - 16.0):
        plinth = cad.cut(plinth, cyl(4.6, (x, y, RUB - 1), (0, 0, 1), 2.2))
        rubbers.append(cad.foot(9, RUB + 1.2, style="dome", at=(x, y, RUB + 1.2)))
parts["Plinth"] = plinth
tick("tilt + plinth")


# ------------------------------------------------------------ parts
def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o


for nm, sh in parts.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS.get(nm, COLOURS["Brass"]))
    if nm in ("Lens", "Dial_Ring"):
        o.ViewObject.Transparency = cad.transparency(COLOURS[nm])
for i, sh in enumerate(rubbers):
    o = part("Rubber_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Rubber"])
for i, sh in enumerate(screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
print("TOTAL %.1f s" % (time.time() - T0))
