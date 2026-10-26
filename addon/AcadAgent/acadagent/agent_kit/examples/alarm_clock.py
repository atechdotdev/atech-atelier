"""Example: "an alarm clock" - a clock radio with a swelling back, leaning back on its foot.

fork this file for an alarm clock / clock radio (a bedside clock, a timer,
a desk radio, a wake-up light - any landscape box whose face is a big
display); change PARAMETERS and the outlines.
ARCHETYPE: clock

How it is built (R410, resculpted R610):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board LANDSCAPE_FRONT behind the face (modules facing the front, -Y);
    the speaker (13, 14) hangs below the board's left half behind a round
    grille, AL / SET keys (6, 5) above it, the screen (9, 10) and an alarm
    LED (3) behind ONE big smoked lens (>= half of the front) in a
    recessed black bezel tray whose back is the mask (a window over the
    screen's active area and one over the LED); the SNOOZE button CABLED
    from port 2 up behind the board to the top, facing up under a wide
    snooze bar, in a bracket on the back half. USB-C (8) in a pocket in
    the left side. The body is a soft front silhouette and a SPLINE plan
    whose back swells in one curve from side to side (cad.profile_body,
    fillet; R610 - the chamfered box read as a box), hollowed with its own
    inset core and split front / back with a lip; the back half's ledges
    and bracket are clipped to its curved wall, four M2.5 screws from
    behind into insert bosses on pads (screw_through on a local piece). EVERYTHING is
    built upright and then TILTED back TILT_DEG about the back-bottom edge
    (one Placement for the board, the cabled module and every part), so
    the face leans back on a graphite foot - the body's own plan, inset.
  * STAGE B - details: the chrome grille trim, the snooze bar's raised
    surround, key legends, lettering, vents, the parting-line reveal,
    rubber feet.
DETAILS (visible, 24 of 30): 1 body leaning back 12 deg, 18 mm corners;
2 graphite foot under it, the body's plan inset (pinned into the back
half); 3 soft 4 mm edges; 4 a back that swells in one curve; 5 big smoked lens (>= 50 % of the front);
6 recessed black bezel round it (1.2 mm step); 7 black mask behind the
lens; 8 screen window in the mask over the active area; 9 alarm-LED
window in the mask; 10 round speaker grille; 11 chrome trim ring round
the grille; 12 AL key cap with flange and plunger; 13 SET key cap;
14 "AL" / "SET" debossed on the keys; 15 wide snooze bar on the top;
16 raised surround round the snooze slot; 17 "SNOOZE" on the bar;
18 USB-C pocket with liner in the left side; 19 "ATECH" on the face;
20 hex vents on the back; 21 four countersunk screws on the back;
22 "ATECH" on the back; 23 parting-line reveal round the front half;
24 four rubber feet under the foot. Inside: 25 speaker chamber tube;
26 rib from the mask onto the board's spine; 27 board ledges and
standoffs; 28 snooze bracket with a shelf (the cabled module's holder);
29 screw pads with heat-set insert pockets; 30 front / back lip.
Materials: cream shell, graphite back and foot, smoked lens, black bezel,
chrome trim and screws, coral snooze bar, white keys, rubber feet.
MEASURED (R610, 2026-10-26): see test_kit_examples_r270 (TIMINGS line).
"""
import time
import Part
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation
V = Vector
T0 = time.time()

INTENT = {"board": "upright", "fitted_after": [
    "Front", "Bezel", "Lens", "Grille_Trim", "Key_AL", "Key_SET", "Snooze_Key", "Foot",
    "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4", "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    # each key cap presses its button through its opening (a declared cover)
    "covers": {"Key_AL": "button_p6", "Key_SET": "button_p5", "Snooze_Key": "button_2"}}
REVIEW_CLOSEUPS = ["Lens", "Snooze_Key", "Grille_Trim"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# R410: the body is built UPRIGHT in a local frame (front = -Y, x across,
# z up, the desk at z = 0) and then tilted back TILT_DEG as one piece.
WALL = 2.0
W, H = 180.0, 105.6              # front silhouette: width 1.6-2 x the height
FRONT_R = 18.0                   # silhouette corner radius (R610: 12 read as a box)
FILLET = 4.0                     # every outer edge
YF, YB = -24.0, 44.0             # front face, back face at its deepest (local y)
# R610: the plan (x, y) - a flat face, straight sides, and a BACK that
# swells in one spline from side to side (the old chamfered box read as a
# box); every back-half detail is measured on it
PLAN = [("line", (0, YF)), ("line", (W, YF)), ("line", (W, 6.0)), (W - 4.0, 22.0), (W - 22.0, 37.0),
        (W - 55.0, 42.8), (W / 2, YB), (55.0, 42.8), (22.0, 37.0), (4.0, 22.0), ("line", (0, 6.0))]
BOARD_X0, BOARD_Z0 = 10.0, 28.0  # board box min (the speaker hangs to z 7.4)
LENS = (53.0, 167.0, 10.0, 96.0)       # smoked lens x0, x1, z0, z1 (>= half the front)
LENS_R = 6.0
BEZEL = 4.0                      # black bezel ring round the lens
RECESS = 1.2                     # the bezel's step back from the face
SCREEN_WIN = (36.0, 18.0)        # mask window over the screen (active area 25.6 x 13.5)
LED_WIN = 21.0                   # mask window over the alarm LED (17 x 17 LEDs)
GRILLE_D = 32.0
SNOOZE = (80.0, 13.0, 4.0)       # snooze bar w, d, height above the top
SNOOZE_X = 90.0                  # bar centre (the button sits under it at x 96.6)
SNOOZE_Y, SNOOZE_Z = 30.0, 96.0  # the cabled snooze button's centre
TILT_DEG = 12.0                  # the face leans back this much
LIFT = 4.0                       # the back-bottom edge stands this high
SCREWS = [(40.0, 98.5), (140.0, 98.5), (65.0, 7.0), (150.0, 7.0)]   # (x, z) on the back
COLOURS = {"Front": "cream", "Back": "graphite", "Bezel": "matte_black", "Lens": "smoked",
           "Grille_Trim": "chrome", "Key": "matte_white", "Snooze_Key": "coral",
           "Foot": "graphite", "Rubber": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
LANDSCAPE_FRONT = Rotation(Vector(0, 0, 1), 180).multiply(Rotation(Vector(0, 1, 0), 90))
# the tilt: about the back-bottom edge (local y = YB, z = 0), then up LIFT
TILT = Placement(V(0, 0, LIFT), Rotation(V(1, 0, 0), -TILT_DEG), V(0, YB, 0))
TILT_M = TILT.toMatrix()
board = ap.board_object(doc)
board.Placement = Placement(V(), LANDSCAPE_FRONT)
_b = ap.bbox(board)
board.Placement = TILT.multiply(Placement(V(BOARD_X0 - _b.XMin, 0, BOARD_Z0 - _b.ZMin), LANDSCAPE_FRONT))
spk = ap.seat(doc, "speaker", (13, 14))        # hangs below the board's left half
key_al = ap.seat(doc, "button", 6)
key_set = ap.seat(doc, "button", 5)
scr = ap.seat(doc, "screen", (9, 10))          # behind the lens
led = ap.seat(doc, "light", 3)                 # the alarm LED, behind the lens
usb = ap.seat(doc, "usbc", 8)                  # left end, mouth -X
# the snooze button: CABLED from port 2 up over the board's top edge and
# back, facing up under the top wall (pins forward: one flat bend, no twist)
snz, snz_rib = ap.cable(doc, "button", 2, TILT.multiply(ap.module_placement(
    "button", (96.6, SNOOZE_Y, SNOOZE_Z), face="+Z", cable="-Y")))
tick("hardware")


def lbox(obj):
    """An Atech object's box in the LOCAL (untilted) frame."""
    g = (obj.Mesh if hasattr(obj, "Mesh") else obj.Shape).copy()
    g.Placement = TILT.inverse().multiply(g.Placement)     # (a Mesh keeps its own Placement)
    return g.BoundBox


def W_(s):
    """Local frame -> world (tilted back, standing on the foot)."""
    s = s.copy()
    s.transformShape(TILT_M)
    return s


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


def centre(b):
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


BB = lbox(board)
SB, KA, KS, SC, LB, UB, NB = [lbox(m) for m in (spk, key_al, key_set, scr, led, usb, snz)]
RB = lbox(snz_rib[0])
print("LOCAL board x %.1f..%.1f z %.1f..%.1f; snooze ribbon x %.1f..%.1f y %.1f..%.1f z %.1f..%.1f" % (
    BB.XMin, BB.XMax, BB.ZMin, BB.ZMax, RB.XMin, RB.XMax, RB.YMin, RB.YMax, RB.ZMin, RB.ZMax))

# ------------------------------------------------------------ body
side = cad.rounded_rect_wire(W, H, FRONT_R, (W / 2, 0, H / 2), "Y")
outer = cad.profile_body(side, PLAN, fillet=FILLET)
outer.fixTolerance(0.01)          # R610: a filleted spline body fails OCCT's BOP check without it
core = cad.profile_body(side, PLAN, fillet=FILLET, inset=WALL)
skin = cad.profile_body(side, PLAN, fillet=FILLET, inset=0.5)      # clips ribs 0.5 mm under the skin
body = cad.cut(outer, core)
tick("body")
# the split stays behind the modules' slide paths (y <= 0) and in front of
# the snooze bracket; the fixed Back carries the board
SPLIT_Y = BB.YMax + 0.3
front, back = cad.split(body, "Y", at=SPLIT_Y, lip=1.2)
tick("split")

# ------------------------------------------------------------ back: holds the board
# ledges under and over the board's long edges (0.3 mm clear, the top one
# notched for the snooze ribbon), standoffs 0.1 mm behind it. R610: each
# reaches back to the curved wall, clipped 0.5 mm under its skin
YIN = YB + 10.0                   # (past the back: clipped to the skin)
ledges = [box(BB.XMin + 4, BB.XMax - 4, 0.6, YIN, BB.ZMin - 2.3, BB.ZMin - 0.3),
          box(BB.XMin + 4, RB.XMin - 2, 0.6, YIN, BB.ZMax + 0.3, BB.ZMax + 2.3),
          box(RB.XMax + 2, BB.XMax - 4, 0.6, YIN, BB.ZMax + 0.3, BB.ZMax + 2.3)]
ledges += [box(BB.XMin + x, BB.XMin + x + 6, BB.YMax + 0.1, YIN, BB.ZMin + z, BB.ZMin + z + 6)
           for x in (8, 57, 106) for z in (7, 47)]
# the snooze button's bracket: two cheeks off the back wall either side of
# the module (0.3 mm clear) and a shelf 0.1 mm under it - behind the ribbon
yb0 = RB.YMax + 1.0
ledges += [box(NB.XMin - 1.8, NB.XMin - 0.3, yb0, YIN, NB.ZMin - 1.5, NB.ZMax + 0.4),
           box(NB.XMax + 0.3, NB.XMax + 1.8, yb0, YIN, NB.ZMin - 1.5, NB.ZMax + 0.4),
           box(NB.XMin - 1.8, NB.XMax + 1.8, yb0, YIN, NB.ZMin - 1.5, NB.ZMin - 0.1)]
back = cad.fuse_one(back, *[lg.common(skin) for lg in ledges])
# screw pads on the front half's top and floor (clear of the lens tray and
# the board), then four M2.5 screws from behind into insert bosses
pads = []
for x, z in SCREWS:
    if z > H / 2:
        pads.append(box(x - 4.5, x + 4.5, -12.0, SPLIT_Y - 2.5, z - 4.5, H - WALL + 0.5))
    else:
        pads.append(box(x - 4.5, x + 4.5, -12.0, SPLIT_Y - 2.5, WALL - 0.5, z + 4.5))
front = cad.fuse_one(front, *pads)


def ray(shape, p0, p1):
    """R610: where the segment p0 -> p1 crosses the shape's surface."""
    return [v.Point for v in shape.section(Part.makeLine(V(*p0), V(*p1))).Vertexes]


def back_y(shape, x, z):
    """The rearmost surface point of `shape` along +Y at (x, z)."""
    return max(p.y for p in ray(shape, (x, -60, z), (x, 80, z)))


# R610: screw_through on the halves' pieces round each screw (on the
# whole spline shell its pilot's 28 mm3 is inside Shape.Volume's noise,
# MEASURED on the weather station); its cuts and bosses applied in one go
screws, csks, bosses, sleeves, pockets = [], [], [], [], []
for x, z in SCREWS:
    yo = back_y(outer, x, z)
    lb = box(x - 7.5, x + 7.5, -30, 60, z - 7.5, z + 7.5)
    b0, f0 = back.common(lb), front.common(lb)
    b1, f1 = cad.screw_through(b0, f0, (x, yo, z), size="M2.5", ribs=0)
    csks.append(b0.cut(b1))
    bosses.append(f1.cut(f0))
    # a heat-set insert pocket (1.4 d + 0.1) in a sleeve at the boss end,
    # its top 0.1 mm under the curved back's inner face all round it
    yb = min(back_y(core, x + dx, z + dz) for dx in (-3, 0, 3) for dz in (-3, 0, 3)) - 0.1
    sleeves.append(cyl(3.0, (x, yb, z), (0, -1, 0), 10.0))
    pockets.append(cyl(1.8, (x, yb + 0.5, z), (0, -1, 0), 9.5))
    screws.append(cad.screw("csk_phillips", "M2.5", round(yo - yb + 7.9), at=(x, yo, z), axis="-Y"))
back = cad.cut(back, csks)
front = cad.cut(cad.fuse_one(front, *(bosses + sleeves)), pockets)
tick("back + screws")

def on_piece(shape, at, fn, h=24.0):
    """R610: apply a cutting detail fn (an opening, lettering, a grille) to the piece of
    `shape` round `at` and cut what it removed from the whole: on the
    spline back a letter's volume is inside Shape.Volume's noise and
    cad.cut called it "removed nothing" (MEASURED)."""
    lb = Part.makeBox(2 * h, 2 * h, 2 * h, V(at) - V(h, h, h))
    loc = shape.common(lb)
    res = shape.cut(loc.cut(fn(loc)))
    if not res.isValid() or len(res.Solids) != len(shape.Solids):
        raise cad.CadError("on_piece: the detail at %s broke the part" % (V(at),))
    return res


# ------------------------------------------------------------ the face
# the lens tray: a black bezel ring set RECESS back in its opening, a pocket
# holding the smoked lens and a mask back with the two windows
lx0, lx1, lz0, lz1 = LENS
front = cad.cut(front, yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, YF - 6, YF + WALL + 1))
yt0, yt1 = YF + RECESS, YF + WALL + 3.0          # tray front, mask back
tray = cad.fuse_one(yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, yt0, YF + WALL + 1),
                    yprism(lx0 - 2, lx1 + 2, lz0 - 2, lz1 + 2, LENS_R + 2, YF + WALL + 0.5, yt1))
y_lens1 = YF + WALL + 1.4                         # the lens back = the mask's face
tray = cad.cut(tray, yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 - 1, y_lens1))
lens = yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 + 0.6, y_lens1 - 0.3)   # 0.3 mm air before the mask
sx, _sy, sz = centre(SC)
lx, _ly, lz = centre(LB)
tray = cad.cut(tray, [cad.rounded_box(SCREEN_WIN[0], 10, SCREEN_WIN[1], 1.5,
                                      at=(sx - SCREEN_WIN[0] / 2, yt1 - 5, sz - SCREEN_WIN[1] / 2), edges="y"),
                      cad.rounded_box(LED_WIN, 10, LED_WIN, 3.0, at=(lx - LED_WIN / 2, yt1 - 5, lz - LED_WIN / 2),
                                      edges="y")])
# board retention: a rib from the mask onto the board's spine (0.2 mm off)
tray = cad.fuse_one(tray, box(58, 62, yt1 - 0.5, BB.YMin - 0.2, 50, 66))
share = (lx1 - lx0) * (lz1 - lz0) / (W * H)
print("DISPLAY lens %.0f x %.0f = %.0f %% of the %.0f x %.0f front" % (lx1 - lx0, lz1 - lz0, 100 * share, W, H))
# speaker: a round grille over the surround, a chamber tube to 0.5 mm off
# the driver (the sound goes out, not into the case)
gx, _gy, gz = centre(SB)
front = cad.speaker_grille(front, (gx, YF, gz), (0, -1, 0), GRILLE_D, ring_pitch=2.6, hole=1.5)
front = cad.fuse_one(front, cad.cut(cyl(18.5, (gx, SB.YMin - 0.5, gz), (0, -1, 0), (SB.YMin - 0.5) - (YF + 1.0)),
                                    cyl(17.2, (gx, SB.YMin, gz), (0, -1, 0), 40)))
# AL / SET keys: caps through the face, flange 0.1 mm behind the wall, a
# plunger to 0.16 mm off each module's own cap
keys = {}
y_base = YF + WALL + 0.9
for nm, kb in (("Key_AL", KA), ("Key_SET", KS)):
    kx, _ky, kz = centre(kb)
    cap = cad.button_cap(12, y_base - (YF - 1.6), dome=0.8, flange=1.5, at=(kx, y_base, kz), axis="-Y")
    front = cad.opening_for(front, cap, clearance=0.25, chamfer=0.4, axis="-Y")
    keys[nm] = cad.fuse_one(cap, cyl(3.0, (kx, kb.YMin - 0.16, kz), (0, -1, 0), (kb.YMin - 0.16) - y_base + 0.5))
# the snooze bar: a wide cap through the top wall (the back half), its
# flange 0.1 mm under the wall, a plunger down onto the cabled button
z_base = H - WALL - 0.9
bar = cad.button_cap((SNOOZE[0], SNOOZE[1]), (H + SNOOZE[2]) - z_base, dome=0.3, flange=1.5,
                     at=(SNOOZE_X, SNOOZE_Y, z_base), axis="+Z")
back = on_piece(back, (SNOOZE_X, SNOOZE_Y, H), lambda s_: cad.opening_for(s_, bar, clearance=0.3, chamfer=0.4,
                                                                         axis="+Z"), h=48.0)   # 55 s on the whole
nx, ny, _nz = centre(NB)
bar = cad.fuse_one(bar, cyl(3.0, (nx, ny, NB.ZMax + 0.16), (0, 0, 1), z_base - (NB.ZMax + 0.16) + 0.5))
# USB-C on the left side: a pocket brings the wall to 0.25 mm off the
# socket mouth (a real plug reaches it), then the measured opening
uy, uz = -5.9, (UB.ZMin + UB.ZMax) / 2         # the receptacle: 5.9 mm above the PCB top
pocket = xprism(uy - 6.5, uy + 6.0, uz - 5.5, uz + 5.5, -5, UB.XMin - 1.3, 3)
liner = cad.cut(xprism(uy - 8.5, min(uy + 8.0, SPLIT_Y - 0.6), uz - 7.5, uz + 7.5, UB.XMin - 0.25, 1.0, 4), pocket)
front = cad.fuse_one(cad.cut(front, pocket), liner)
tick("face")
# the foot: under the body's flat bottom (local z <= 0), pinned into the
# back half's floor; clipped to the desk after the tilt
# R610: the foot is the body's own plan inset FOOT_IN (a box under the
# swelling back read as a crate)
FOOT_IN = 12.0
pegs = [(40.0, 24.0), (140.0, 24.0)]
ff = Part.Face(cad.spline_wire(PLAN, plane="XY")).makeOffset2D(-FOOT_IN)
ff.translate(V(0, 0, -40))
foot_l = cad.fuse_one(ff.extrude(V(0, 0, 40)),
                      *[box(x - 2.85, x + 2.85, y - 2.85, y + 2.85, -1, WALL + 1.0) for x, y in pegs])
_bk = back.cut(Part.makeCompound([box(x - 3.0, x + 3.0, y - 3.0, y + 3.0, -1, WALL + 2) for x, y in pegs]))
assert _bk.isValid() and len(_bk.Solids) == 1      # (a 70 mm3 bore is under cad.cut's volume noise here)
back = _bk
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)



# a chrome trim ring round the grille, in a 1 mm groove
front = cad.cut(front, cad.cut(cyl(GRILLE_D / 2 + 3.4, (gx, YF - 1, gz), (0, 1, 0), 2.0),
                               cyl(GRILLE_D / 2 + 1.0, (gx, YF - 2, gz), (0, 1, 0), 4.0)))
trim = cad.soften(cad.cut(cyl(GRILLE_D / 2 + 3.4, (gx, YF - 0.6, gz), (0, 1, 0), 1.6),
                          cyl(GRILLE_D / 2 + 1.0, (gx, YF - 1, gz), (0, 1, 0), 3.0)), 0.3)
# a raised surround round the snooze slot (0.8 mm proud of the top)
o_w, o_d = SNOOZE[0] + 6.6, SNOOZE[1] + 6.6
surround = cad.cut(cad.rounded_box(o_w, o_d, 1.6, 3.0, at=(SNOOZE_X - o_w / 2, SNOOZE_Y - o_d / 2, H - 0.8)),
                   cad.rounded_box(SNOOZE[0] + 1.2, SNOOZE[1] + 1.2, 4, 1.0,
                                   at=(SNOOZE_X - SNOOZE[0] / 2 - 0.6, SNOOZE_Y - SNOOZE[1] / 2 - 0.6, H - 2)))
back = cad.fuse_one(back, surround)
# legends and lettering
for nm, kb, t in (("Key_AL", KA, "AL"), ("Key_SET", KS, "SET")):
    kx, _ky, kz = centre(kb)
    keys[nm] = cad.text(keys[nm], t, (kx, YF - 1.6, kz), (0, -1, 0), 3.6, depth=0.4, mode="deboss")
bar = cad.text(bar, "SNOOZE", (SNOOZE_X, SNOOZE_Y, H + SNOOZE[2]), (0, 0, 1), 5, depth=0.4, mode="deboss",
               up=(0, 1, 0))
front = cad.text(front, "ATECH", (gx, YF, 58), (0, -1, 0), 6, depth=0.5, mode="deboss")
back = on_piece(back, (W / 2, back_y(outer, W / 2, 80), 80),
                lambda s_: cad.text(s_, "ATECH", (W / 2, back_y(outer, W / 2, 80), 80), (0, 1, 0), 7, depth=0.5,
                                    mode="deboss", up=(0, 0, 1)))
# hex vents on the back, clear of the screws and the bracket
back = on_piece(back, (W / 2, back_y(outer, W / 2, 50), 50),
                lambda s_: cad.grille(s_, (W / 2, back_y(outer, W / 2, 50), 50), (0, 1, 0), (70, 16), kind="hex",
                                      hole=3.0, pitch=4.5), h=42.0)
# the parting-line reveal round the front half
front = cad.groove_ring(front, "Y", SPLIT_Y - 3.0, w=0.8, depth=0.6)
tick("stage B")


# ------------------------------------------------------------ tilt + foot
parts = {"Front": front, "Back": back, "Bezel": tray, "Lens": lens, "Grille_Trim": trim,
         "Snooze_Key": bar}
parts.update(keys)
parts = {k: W_(v) for k, v in parts.items()}
# the USB-C opening is MEASURED from the module, so it is cut after the tilt
parts["Front"] = cad.socket_opening(parts["Front"], usb, margin=1.5)
screws = [W_(s) for s in screws]
RUB = 1.5                                          # the rubber feet's height
foot = W_(foot_l).common(box(-50, W + 50, -150, 150, RUB, 200))
rubbers = []
for x in (30.0, W - 30.0):
    for y in (YF + 18.0, 20.0):
        p = TILT.multVec(V(x, y, 0))
        foot = cad.cut(foot, cyl(4.6, (p.x, p.y, RUB - 1), (0, 0, 1), 2.2))
        rubbers.append(cad.foot(9, RUB + 1.2, style="dome", at=(p.x, p.y, RUB + 1.2)))
parts["Foot"] = foot
tick("tilt + foot")


# ------------------------------------------------------------ parts
def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o


for nm, sh in parts.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Key" if nm.startswith("Key") else nm])
    if nm == "Lens":
        o.ViewObject.Transparency = cad.transparency(COLOURS["Lens"])
for i, sh in enumerate(rubbers):
    o = part("Rubber_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Rubber"])
for i, sh in enumerate(screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
print("TOTAL %.1f s" % (time.time() - T0))
