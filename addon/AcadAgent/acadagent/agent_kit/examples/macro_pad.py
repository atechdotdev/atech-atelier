"""Example: "a macro pad" - a stream-deck style keypad: a low wedge, two big keys, a label screen, a dial.

fork this file for a macro pad / desk control surface (a stream deck, a
macro keypad, a media controller, a mini mixer - a low wedge deck with
keys, a dial and a display); change PARAMETERS and the outlines.
ARCHETYPE: macro pad

How it is built (R620):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT and turned ACROSS (long side left to right, modules face up)
    under a low deck. The label screen (9, 10) sits at the back-left with
    the two big keys (1, 2) right in front of it - each key under its own
    half of the screen; the status light (5) under a long frosted strip in
    front of the dial; the knob (13, 14) at the back-right inside a round
    DIAL CROWN that rises out of the deck, its cap flush with the crown's
    rim (only a module's working face may look out) and a frosted ring
    over its 12 LEDs in the well's floor; USB-C (7) in a pocket in the left
    end. Everything is built in a LOCAL frame (the deck flat, z up from
    the front-bottom edge) and tilted back ALPHA as one Placement - the
    deck leans toward the hand like a keyboard and the foot stands flat.
    The body is a rounded plan extruded and cut by the leaning foot plane
    (every face a plane or a cylinder), hollowed with its own core, split
    into the fixed Base (it carries the board on pads between fences) and
    the Top with a lip; five M2 screws from below into heat-set insert
    bosses; ribs from the deck onto the board's spine.
  * STAGE B - details: key legends, a brushed bezel in the crown's rim,
    the parting-line reveal, a grip groove along the front, vents and a
    model mark under the base, lettering, rubber feet.
DETAILS (visible, 28): 1 low wedge deck leaning toward the hand; 2 rolled
wrist edge along the front; 3 soft plan corners; 4 two big keys with
flanges and plungers; 5 "1" / "2" legends; 6 smoked label window in a
recessed black bezel; 7 frosted status strip; 8 round dial crown rising
out of the deck; 9 the dial's cap flush in its well; 10 frosted ring over
the knob's LED ring; 11 brushed bezel in the crown's rim; 12 rolled crown
foot; 13 USB-C pocket with liner in the left end; 14 parting-line reveal;
15 grip groove along the front; 16 "ATECH" on the deck; 17 slot vents
under the base; 18 "ATECH MP-2" under the base; 19 five countersunk
screws from below; 20 four rubber feet. Inside: 21 board pads; 22 end
fences; 23 ribs onto the board's spine; 24 screw bosses with heat-set
insert sleeves; 25 base / top lip; 26 the deck as the dial well's floor;
27 a light pipe under the strip; 28 key plungers.
Materials: graphite top, black base, ivory keys, smoked label window,
black bezel, frosted strip and dial ring, brushed dial bezel, chrome
screws, rubber feet.
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

INTENT = {"board": "flat", "fitted_after": [
    "Top", "Bezel", "Label_Window", "Status_Strip", "Dial_Ring", "Dial_Bezel", "Key_1", "Key_2",
    "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4", "Screw_5"],
    # each big key presses its button through its opening (a declared cover)
    "covers": {"Key_1": "button_p1", "Key_2": "button_p2"}}
REVIEW_CLOSEUPS = ["Key_1", "Dial_Bezel", "Label_Window"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them and the measured hardware.
WRIST = 20.0       # RESTYLE 17..23 length: the deck in front of the keys (y)
SIDE = 10.0        # RESTYLE 8.5..11.5 width: the deck past the board's ends (x)
RISE = 13.0        # RESTYLE 11..15 height: how much higher the back stands than the front
CORNER = 12.0      # RESTYLE 10.2..13.8 radius: the plan's corners
WALL = 2.0         # RESTYLE 1.7..2.3 wall
# end RESTYLE
# R620: the product is built in a LOCAL frame - the deck flat, x across,
# y away from the user, z up from the front-bottom edge - and tilted back
# ALPHA as one piece (the foot plane leans the other way, so it lands flat).
Z_PCB = WALL + 4.0               # the PCB top over the front edge's foot
AIR = 1.2                        # the deck's inner face over the tallest module (usbc 10.21):
                                 # the keys' flanges clear their buttons
EDGE_R, FOOT_R = 3.5, 1.2        # the rolled top edge (the wrist edge with it), the foot
CROWN = (27.0, 22.5)             # the dial crown's foot / rim radius (a cone: it grows out of the deck)
DISH_R = 19.0                    # the well round the knob (finger room round the 12 mm cap)
RING_R = (5.6, 15.5)             # the frosted ring over the knob's LED ring (LEDs at r 11..13)
KEY = (17.5, 26.0)               # the big keys, x by y (19.5 mm pitch: a 1.5 mm web between)
KEY_FWD = 5.0                    # each key's centre this far in front of its button (the USB-C sits behind key 1)
LABEL = (34.0, 18.0)             # the smoked label window (the active area 25.6 x 13.5)
STRIP = (44.0, 12.0)             # the frosted status strip over the light
BEZEL, RECESS = 2.5, 1.0
RUB = 1.5                        # the rubber feet's height
COLOURS = {"Top": "graphite", "Base": "matte_black", "Key": "#ece6da", "Label_Window": "smoked",
           "Bezel": "matte_black", "Status_Strip": "frosted", "Dial_Ring": "frosted",
           "Dial_Bezel": "brushed_alu", "Rubber": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
FLAT = Rotation(Vector(1, 0, 0), 90)
ACROSS = Rotation(Vector(0, 0, 1), 90).multiply(FLAT)      # long side along X, modules face +Z
# the plan: the board centred, the keys' front edge WRIST in from the front
# edge, the back behind the dial crown (the knob hangs 20 mm behind the board)
Y0 = -30.4 - WRIST                            # the front edge (the key row starts at y -30.4)
Y1 = 30.75 + CROWN[0] + 3.0                   # the back edge: the crown 3 mm inside it
X1 = max(60.4 + SIDE, 40.0 + CROWN[0] + 3.0)  # the ends
ALPHA = math.degrees(math.atan2(RISE, Y1 - Y0))
TAN_A = math.tan(math.radians(ALPHA))
TILT = Placement(V(0, 0, RUB), Rotation(V(1, 0, 0), ALPHA), V(0, Y0, 0))
TILT_M = TILT.toMatrix()
board = ap.board_object(doc)
board.Placement = Placement(V(), ACROSS)
_b = ap.bbox(board)
board.Placement = TILT.multiply(Placement(V(-(_b.XMin + _b.XMax) / 2, -(_b.YMin + _b.YMax) / 2,
                                            Z_PCB - 2.5 - _b.ZMin), ACROSS))
knob = ap.seat(doc, "knob", (13, 14))         # the volume dial: back-right, hangs 20 mm behind
scr = ap.seat(doc, "screen", (9, 10))         # the label screen: back-left
key1 = ap.seat(doc, "button", 1)              # the big keys, in front of the screen
key2 = ap.seat(doc, "button", 2)
led = ap.seat(doc, "light", 5)                # the status light, in front of the dial
usb = ap.seat(doc, "usbc", 7)                 # left end, mouth -X
tick("hardware")


def lbox(obj):
    """An Atech object's box in the LOCAL (untilted) frame."""
    g = (obj.Mesh if hasattr(obj, "Mesh") else obj.Shape).copy()
    g.Placement = TILT.inverse().multiply(g.Placement)
    return g.BoundBox


def W_(s):
    """Local frame -> world (tilted back, standing on its feet)."""
    s = s.copy()
    s.transformShape(TILT_M)
    return s


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(b):
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


BB = lbox(board)
KB, SB, K1, K2, LB, UB = [lbox(m) for m in (knob, scr, key1, key2, led, usb)]
Z_TOP = max(b.ZMax for b in (SB, K1, K2, LB, UB)) + AIR + WALL     # the deck's top face
print("DECK %.0f x %.0f, front %.1f / back %.1f mm thick, leaning %.1f deg" % (
    2 * X1, Y1 - Y0, Z_TOP, Z_TOP + RISE, ALPHA))

# ------------------------------------------------------------ the body
def foot_cut(t):
    """Everything above the leaning foot plane, raised t along its normal."""
    k = box(-400, 400, -400, 400, 0, 400)
    k.rotate(V(0, Y0, 0), V(1, 0, 0), -ALPHA)
    k.translate(V(0, t * math.sin(math.radians(ALPHA)), t * math.cos(math.radians(ALPHA))))
    return k


def slab(t):
    """The body inset t: the rounded plan extruded, cut by the foot plane
    (planes and cylinders only - robust booleans)."""
    w = cad.rounded_rect_wire(2 * (X1 - t), (Y1 - Y0) - 2 * t, max(CORNER - t, 0.6), (0, (Y0 + Y1) / 2, -80), "Z")
    s = Part.Face(w).extrude(V(0, 0, 80 + Z_TOP - t))
    return s.common(foot_cut(t))


def on_foot(e):
    return all(abs(v.Point.z + (v.Point.y - Y0) * TAN_A) < 1e-3 for v in e.Vertexes)


outer = slab(0.0)
# (the top's outline is one tangent chain: rounding it rolls the whole rim)
outer = cad.soften(outer, EDGE_R, [e for e in outer.Edges if e.BoundBox.ZMin > Z_TOP - 1e-3])
outer = cad.soften(outer, FOOT_R, [e for e in outer.Edges if on_foot(e)])
# the core keeps SHARP inner edges (a filleted core leaves concave rounds
# ./check reads as clip channels - the handheld's lesson)
body = cad.hollow(outer, WALL, core=lambda t: slab(t))
skin = slab(0.5)                              # clips ribs 0.5 mm under the outer skin
tick("body")
SPLIT = Z_PCB - 2.0                           # in the cavity: the lip's top stays under the PCB top
base, top = cad.split(body, "Z", at=SPLIT, lip=1.2)
tick("split")


def floor_z(x, y):
    """The base's inner floor height at (x, y) (the foot plane leans)."""
    return -(y - Y0) * TAN_A + WALL / math.cos(math.radians(ALPHA))


# the fixed base holds the board: pads 0.1 mm under it (0.5 mm into the
# floor), fences off its ends - the left one split round the USB-C module
UNDER = BB.ZMin - 0.1
pads = [box(x - 4, x + 4, y - 4, y + 4, floor_z(x, y + 4) - 0.5, UNDER)
        for x in (BB.XMin + 10, 0.0, BB.XMax - 10) for y in (-22.0, 22.0)]
fences = [box(BB.XMin - 1.8, BB.XMin - 0.3, y0, y0 + 6, floor_z(BB.XMin, y0 + 6) - 0.5, Z_PCB - 0.8)
          for y0 in (-17.0, 11.0)]
fences += [box(BB.XMax + 0.3, BB.XMax + 1.8, y0, y0 + 6, floor_z(BB.XMax, y0 + 6) - 0.5, Z_PCB - 0.8)
           for y0 in (-17.0, 11.0)]
base = cad.fuse_one(base, *[p.common(skin) for p in pads + fences])
# board retention: two ribs from the deck down onto the spine (0.2 mm off
# it), between the key row and the back row
SPINE_Z = BB.ZMax                              # the spine's top (PCB top + 4.5)
top = cad.fuse_one(top, *[box(x - 2, x + 2, -6, 6, SPINE_Z + 0.2, Z_TOP - WALL + 0.5) for x in (-30.0, 10.0)])
# five M2 screws from below into insert bosses in the top: off the board's
# ends and behind the screen (no screw through the board, a module or a
# slide corridor)
SX = BB.XMax + 0.6 + 2.8                      # off the board's ends: the insert sleeve 0.6 mm clear of the keys
SCREWS = [(-SX, -24.0), (-SX, 24.0), (SX, -24.0), (SX, 4.0), (-40.0, (SB.YMax + Y1) / 2)]
screws = []
for x, y in SCREWS:
    zb = -(y - Y0) * TAN_A                     # the foot's outer face under the screw
    base, top = cad.screw_through(base, top, (x, y, zb), size="M2", ribs=0)
    ring = [(0.0, 0.0)] + [(rr * math.cos(math.radians(a_)), rr * math.sin(math.radians(a_)))
                           for rr in (1.5, 3.0) for a_ in range(0, 360, 45)]
    z0 = max(floor_z(x + ex, y + ey) for ex, ey in ring) + 0.1
    top = cad.fuse_one(top, cyl(2.8, (x, y, z0), Z_TOP - WALL + 0.5 - z0))
    top = cad.cut(top, cyl(1.6, (x, y, z0 - 0.1), 6.5))
    screws.append(cad.screw("csk_phillips", "M2", 8, at=(x, y, zb), axis="+Z"))
# a 1 mm boss inside the floor over each rubber foot (its 1.2 mm recess
# leaves the floor whole at any WALL)
FEET = [(x, y) for x in (-(X1 - 16.0), X1 - 16.0) for y in (Y0 + 16.0, Y1 - 16.0)]
base = cad.fuse_one(base, *[cyl(6.0, (x, y, floor_z(x, y + 6) - 0.5),
                                (floor_z(x, y - 6) + 1.0) - (floor_z(x, y + 6) - 0.5))
                            for x, y in FEET])
tick("base + screws")


def insert(shell, cutter):
    """(shell with the opening, the piece that fills it exactly)."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1 or not rest.isValid() or len(rest.Solids) != len(shell.Solids):
        raise cad.CadError("insert: the cutter does not cleanly cross the wall")
    return rest, piece


def zbox(w, d, r, cx, cy, z0, z1):
    return cad.rounded_box(w, d, z1 - z0, r, at=(cx - w / 2, cy - d / 2, z0))


# ------------------------------------------------------------ the deck
# the big keys: caps through the deck (flange 0.1 mm under it), a plunger
# to 0.16 mm over each module's own cap
base_z = Z_TOP - WALL - 0.9
keys = {}
for nm, kb in (("Key_1", K1), ("Key_2", K2)):
    kx, ky, _kz = centre(kb)
    cap = cad.button_cap(KEY, (Z_TOP + 1.8) - base_z, dome=0.6, flange=0.8, at=(kx, ky - KEY_FWD, base_z), axis="+Z")
    top = cad.opening_for(top, cap, clearance=0.25, chamfer=0.4, axis="+Z")
    keys[nm] = cad.fuse_one(cap, cyl(3.0, (kx, ky, kb.ZMax + 0.16), base_z - (kb.ZMax + 0.16) + 0.5))
# the label window: a black bezel frame set RECESS down in its opening, a
# smoked window inside it over the active area
sx, sy, _sz = centre(SB)
top, bezel = insert(top, zbox(LABEL[0] + 2 * BEZEL, LABEL[1] + 2 * BEZEL, 3.0 + BEZEL, sx, sy, Z_TOP - WALL - 1,
                              Z_TOP + 1))
bezel = bezel.cut(box(-300, 300, -300, 300, Z_TOP - RECESS, Z_TOP + 2))
bezel, label = insert(bezel, zbox(LABEL[0], LABEL[1], 3.0, sx, sy, Z_TOP - WALL - 2, Z_TOP + 2))
# the status strip: a frosted bar through the deck over the light, a pipe
# under its middle to 0.5 mm over the LEDs
lx, ly, _lz = centre(LB)
top, strip = insert(top, zbox(STRIP[0], STRIP[1], STRIP[1] / 2 - 0.01, lx, ly, Z_TOP - WALL - 1, Z_TOP + 1))
strip = cad.fuse_one(strip, zbox(17.0, STRIP[1] - 1.0, 2.0, lx, ly, LB.ZMax + 0.5, Z_TOP - WALL + 0.5))
# the dial crown: a cone rising out of the deck round the knob, its rim
# 0.4 mm over the cap's top (R620, MEASURED: a cap standing proud is "a
# module sticking out of the body" - only its working face may look out,
# so the cap sits FLUSH in a well and the fingers reach in round it); the
# deck is the well's floor (its inner face 0.6 mm over the knob's base), a
# frosted ring in it over the 12 LEDs round the shaft (an insert)
kx, ky, _kz = centre(KB)
z_rim = KB.ZMax + 0.4
crown = Part.makeCone(CROWN[0], CROWN[1], z_rim - (Z_TOP - 1.0), V(kx, ky, Z_TOP - 1.0))
top = cad.cut(cad.fuse_one(top, crown), cyl(DISH_R, (kx, ky, Z_TOP - 0.01), 80))
ring_cut = cad.cut(cyl(RING_R[1], (kx, ky, Z_TOP - WALL - 1), WALL + 2),
                   cyl(RING_R[0], (kx, ky, Z_TOP - WALL - 2), WALL + 4))
dial_ring = top.common(ring_cut)
top = cad.cut(top, cyl(RING_R[1], (kx, ky, Z_TOP - WALL - 1), WALL + 2))     # the ring's seat + the shaft's way out
# the brushed bezel: a ring in a rebate round the crown's rim (it fills it)
reb = cad.cut(cyl(CROWN[1] + 1.0, (kx, ky, z_rim - 2.5), 3.5), cyl(CROWN[1] - 1.4, (kx, ky, z_rim - 3.0), 6.0))
dial_bezel = top.common(reb)
top = cad.cut(top, reb)
dial_bezel = cad.soften(dial_bezel, 0.5, [e for e in dial_bezel.Edges if e.BoundBox.ZMin > z_rim - 1e-3
                                          and e.BoundBox.XLength > 2 * CROWN[1] - 0.5])
# USB-C in the left end: a pocket brings the wall to 0.25 mm off the mouth
uy, uz = (UB.YMin + UB.YMax) / 2, Z_PCB + 5.9


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


pocket = xprism(uy - 6.5, uy + 6.5, uz - 5.0, uz + 5.0, -X1 - 5, UB.XMin - 1.3, 3)
liner = cad.cut(xprism(uy - 8.5, uy + 8.5, max(uz - 7.5, SPLIT + 1.6), uz + 7.5, UB.XMin - 0.25, -X1 - 2, 4), pocket)
top = cad.fuse_one(cad.cut(top, pocket), liner.common(skin))
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# key legends, the parting-line reveal, a grip groove along the front
for nm, kb, t in (("Key_1", K1, "1"), ("Key_2", K2, "2")):
    kx_, ky_, _ = centre(kb)
    keys[nm] = cad.text(keys[nm], t, (kx_, ky_ - KEY_FWD + 6.0, Z_TOP + 1.8), (0, 0, 1), 6, depth=0.4, mode="deboss",
                        up=(0, 1, 0))
top = cad.groove_ring(top, "Z", SPLIT + 2.2, w=0.8, depth=0.6)
Y_GRIP = Y0 + EDGE_R + 0.8
top = cad.cut(top, box(-(X1 - 2 * CORNER), X1 - 2 * CORNER, Y_GRIP - 0.6, Y_GRIP + 0.6, Z_TOP - 0.6, Z_TOP + 1))
top = cad.text(top, "ATECH", (lx, (Y_GRIP + K1.YMin) / 2 + 1.0, Z_TOP), (0, 0, 1), 4.5, depth=0.4,
               mode="deboss", up=(0, 1, 0))
tick("stage B")


# ------------------------------------------------------------ tilt + feet
parts = {"Top": top, "Base": base, "Bezel": bezel, "Label_Window": label, "Status_Strip": strip,
         "Dial_Ring": dial_ring, "Dial_Bezel": dial_bezel}
parts.update(keys)
parts = {k: W_(v) for k, v in parts.items()}
# the USB-C opening is MEASURED from the module, so it is cut after the tilt
parts["Top"] = cad.socket_opening(parts["Top"], usb, margin=1.5)
screws = [W_(s) for s in screws]
# under the base (flat on the desk now): vents, a model mark, rubber feet
B = parts["Base"]
foot_pts = [TILT.multVec(V(x, y, -(y - Y0) * TAN_A)) for x, y in FEET]
mid = TILT.multVec(V(0, (Y0 + Y1) / 2 + 6.0, -((Y0 + Y1) / 2 + 6.0 - Y0) * TAN_A))
B = cad.grille(B, (mid.x - 22.0, mid.y, RUB), (0, 0, -1), (34, 22), kind="slot", hole=2.0, pitch=4.5)
B = cad.text(B, "ATECH MP-2", (mid.x + 28.0, mid.y, RUB), (0, 0, -1), 4.5, depth=0.4, mode="deboss",
             up=(0, -1, 0))
rubbers = []
for p in foot_pts:
    B = cad.cut(B, cyl(4.6, (p.x, p.y, RUB - 1), 2.2))
    rubbers.append(cad.foot(9, RUB + 1.2, style="dome", at=(p.x, p.y, RUB + 1.2)))
parts["Base"] = B
tick("tilt + feet")


# ------------------------------------------------------------ parts
def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o


for nm, sh in parts.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Key" if nm.startswith("Key") else nm])
    if nm in ("Label_Window", "Status_Strip", "Dial_Ring"):
        o.ViewObject.Transparency = cad.transparency(COLOURS[nm])
for i, sh in enumerate(rubbers):
    o = part("Rubber_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Rubber"])
for i, sh in enumerate(screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
print("TOTAL %.1f s" % (time.time() - T0))
