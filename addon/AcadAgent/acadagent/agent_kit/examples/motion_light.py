"""Example: "a motion-sensing night light" - an arched wall pebble with a frosted glowing moon and an open PIR eye.

fork this file for a motion night light / sensor light (a hallway or
stair night light, a bedside motion glow, a closet light, a porch
presence lamp); change PARAMETERS and the outlines.
ARCHETYPE: motion light

How it is built (R803):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board UPRIGHT_FRONT in the pebble (portrait, modules facing the room,
    -Y; the wall behind, +Y). Four lights SEATED on 5 / 6 (right) and 13 /
    14 (left) - the top two rows of both columns - glow behind ONE big
    round frosted diffuser (the "moon", an insert filling its opening in
    the front, domed 2 mm, a light pipe 0.4 mm off each LED grid). Low on
    the face the PIR motion sensor on 1 looks out through an OPEN round
    window in a black eye bezel (infrared does not pass plastic or glass:
    nothing covers the dome), a visor over the window's top half shades it
    toward the floor; the mode key on 9 is its mirror on the left (a key
    cap through the front, a plunger onto the button); USB-C on 7 in a
    pocket in the bottom (the cable drops behind the chin). Ports 8 and 12
    stay empty (reserved by the firmware). The pebble: one rounded slab
    (cad.rounded_box, big plan corners, the front edge rolled), hollowed
    with a sharp core, split FRONT / BACK just behind the board (the back
    is fixed: it carries the board on ledges and standoffs); four M2.5
    screws from the wall side, through the wall plate and the back, into
    insert bosses in the front. The wall plate follows the outline, proud
    all round, with two keyholes and four rubber bumpers on its back.
  * STAGE B - details: the front / back reveal, a raised rim round the
    moon, the visor, a raised ring round the key, legends, the plate's
    rolled edge, keyholes, bumpers.
RESTYLE (R803): WIDTH, HEIGHT, DEPTH, CORNER and WALL drive every outline
and every cutter below; the front's inner face stays 2.6 mm in front of
the lights whatever the wall (YF), the screws follow the sides and the top
corners (screw_at). The hardware frame (the board at x 0..60, BZ above the
pebble's floor) is the board's own: never move it with a knob.
DETAILS (visible, 30): 1 arched pebble slab with big corners; 2 rolled
front edge; 3 front / back reveal; 4 two-tone halves (warm white front,
stone back); 5 frosted moon diffuser; 6 its 2 mm dome; 7 raised rim round
it; 8 black eye bezel, proud of the face; 9 its OPEN PIR window; 10 the
window's flared mouth; 11 visor over the window; 12 mode key cap, domed;
13 raised ring round it; 14 "MODE" legend; 15 "AUTO" legend over the eye;
16 "ATECH" wordmark between them; 17 USB-C pocket with liner in the
bottom; 18 the wall plate, proud all round; 19 its rolled front edge;
20 the plate's chin; 21-22 two keyholes in the plate's back; 23-26 four
countersunk screws in the plate's back; 27-30 four rubber bumpers in
recesses on the plate's back.
Inside: four light pipes, a rib onto the board's spine, board ledges and
standoffs, insert bosses, the front / back lip, a plunger on the key.
Materials: warm white front, stone back, frosted moon, black eye bezel,
sand key, graphite wall plate, rubber bumpers, chrome screws.
MEASURED (R803, 2026-10-27): ./check CHECK PASS, see test_kit_examples_r500
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

INTENT = {"board": "upright", "fitted_after": [
    "Front", "Moon", "Eye_Bezel", "Mode_Key", "Wall_Plate",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    "covers": {"Mode_Key": "button_p9"}}
REVIEW_CLOSEUPS = ["Moon", "Eye_Bezel", "Mode_Key"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them; test_kit_examples_r280 builds
# this file with each knob at its min and at its max, one at a time.
WIDTH = 108.0      # RESTYLE 91.5..124.5 width: the pebble across (x); 91.5: the moon's rim on the face
HEIGHT = 190.0     # RESTYLE 161..219 height: the pebble (z); 161: the moon under the top edge
DEPTH = 30.0       # RESTYLE 25.5..34.5 length: the pebble front to the wall (y)
CORNER = 40.0      # RESTYLE 34..46 radius: the pebble's corners, seen from the front
WALL = 2.5         # RESTYLE 2.1..2.9 wall
# end RESTYLE
# Frame: x across (the viewer's right +), y from the room (-) to the wall
# (+), z up; the plate's chin on z = 0.
X0, X1 = 30.0 - WIDTH / 2, 30.0 + WIDTH / 2     # the board's centre line x = 30
PB = 10.0                        # the pebble's bottom (the plate's chin below it)
ZT = PB + HEIGHT                 # the pebble's top
YF = -12.1 - WALL                # the front: its inner face 2.6 mm in front of the lights
YB = YF + DEPTH                  # the back (on the wall plate)
EDGE = 5.0                       # the rolled front edge
BZ = PB + WALL + 12.0            # the board's bottom: room for the USB-C pocket below
PLATE_T, PLATE_OUT = 5.0, 5.0    # the wall plate's thickness, how far it stands out round the pebble
MOON_R, MOON_DOME = 38.0, 2.0    # the frosted moon over the four lights; its dome
RIM = (2.2, 1.0)                 # the raised rim round the moon: width, height
EYE_R, WINDOW_D = 12.0, 11.5     # the PIR eye bezel; its OPEN window (the dome is ~9.4 across)
VISOR = (1.2, 4.0)               # the visor over the window: wall, reach
KEY_D = 12.0
SCREW = "M2.5"
COLOURS = {"Front": "#f1ece2", "Back": "#cfc8bb", "Moon": "frosted", "Eye_Bezel": "matte_black",
           "Mode_Key": "#d9c7a7", "Wall_Plate": "graphite", "Bumper": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
UPRIGHT_FRONT = Rotation(Vector(0, 0, 1), 180)
board = ap.board_object(doc)


def place_board(rot, x0=0.0, y0=None, z0=0.0):
    board.Placement = Placement(Vector(), rot)
    bb = ap.bbox(board)
    board.Placement = Placement(Vector(x0 - bb.XMin, 0 if y0 is None else y0 - bb.YMin,
                                       z0 - bb.ZMin), rot)


place_board(UPRIGHT_FRONT, 0, None, BZ)          # x 0..60, z BZ..BZ + 120, modules face -Y
BB = ap.bbox(board)
lights = [ap.seat(doc, "light", p) for p in (5, 6, 13, 14)]   # the top two rows: one glow
pir = ap.seat(doc, "pir", 1)                      # bottom right: low, toward the floor
key = ap.seat(doc, "button", 9)                   # bottom left, the eye's mirror
usb = ap.seat(doc, "usbc", 7)                     # bottom centre, mouth -Z
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, -1, 0)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


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


def zprism(x0, x1, y0, y1, z0, z1, r):
    w = cad.rounded_rect_wire(x1 - x0, y1 - y0, r, ((x0 + x1) / 2, (y0 + y1) / 2, z0), "Z")
    return Part.Face(w).extrude(V(0, 0, z1 - z0))


# ------------------------------------------------------------ the pebble
peb = cad.rounded_box(WIDTH, DEPTH, HEIGHT, CORNER, at=(X0, YF, PB), edges="y")
peb = cad.fillet_safe(peb, EDGE, edges=[e for e in peb.Edges if e.BoundBox.YMax < YF + 0.01])
peb = cad.fillet_safe(peb, 1.0, edges=[e for e in peb.Edges if e.BoundBox.YMin > YB - 0.01])
# the core keeps SHARP inner edges (a filleted core reads as clip channels)
core = cad.rounded_box(WIDTH - 2 * WALL, DEPTH - 2 * WALL, HEIGHT - 2 * WALL, CORNER - WALL,
                       at=(X0 + WALL, YF + WALL, PB + WALL), edges="y")
shell = cad.cut(peb, core)
tick("pebble")
# the split stays just behind the board's back: the back is the fixed half
SPLIT_Y = BB.YMax - 0.3
front, back = cad.split(shell, "Y", at=SPLIT_Y, lip=1.2)
tick("split")

# ------------------------------------------------------------ the back holds the board
# ledges under and over the board's short edges (0.3 mm clear), standoffs
# 0.1 mm behind it - all behind the module layer
YI = YB - WALL + 0.5                       # into the back wall
ledges = [box(4, 56, 0.6, YI, BB.ZMin - 2.3, BB.ZMin - 0.3), box(4, 56, 0.6, YI, BB.ZMax + 0.3, BB.ZMax + 2.3)]
ledges += [box(x, x + 6, BB.YMax + 0.1, YI, BZ + z, BZ + z + 6) for x in (8, 46) for z in (10, 57, 104)]
back = cad.fuse_one(back, *ledges)
# the wall plate: the pebble's outline, proud all round, a chin below it
plate = cad.rounded_box(WIDTH + 2 * PLATE_OUT, PLATE_T, ZT + PLATE_OUT, CORNER + PLATE_OUT,
                        at=(X0 - PLATE_OUT, YB, 0.0), edges="y")
plate = cad.fillet_safe(plate, 1.8, edges=[e for e in plate.Edges if e.BoundBox.YMax < YB + 0.01])


def screw_at(sx, top):
    """A side screw low on the straight flank, or a top one on the corner's
    diagonal, its sleeve 1.5 mm inside the inner wall (it follows WIDTH,
    CORNER and WALL)."""
    if not top:
        return (X0 + WALL + 4.5) if sx < 0 else (X1 - WALL - 4.5), PB + CORNER + 6.0
    cx = (X0 + CORNER) if sx < 0 else (X1 - CORNER)
    d = (CORNER - WALL - 4.5) / math.sqrt(2.0)
    return cx + sx * d, ZT - CORNER + d


# four M2.5 screws from the wall side: through the plate and the back
# into insert bosses in the front, clear of every module
SCREWS = [screw_at(-1, False), screw_at(1, False), screw_at(-1, True), screw_at(1, True)]
INSERT_D = {"M2": 3.2, "M2.5": 3.6, "M3": 4.3}[SCREW]
screws = []
for x, z in SCREWS:
    back, front = cad.screw_through(back, front, (x, YB, z), size=SCREW, ribs=0)
    yb = YB - WALL - 0.1
    front = cad.fuse_one(front, cyl(INSERT_D / 2 + 1.2, (x, yb, z), 10.0))
    front = cad.cut(front, cyl(INSERT_D / 2, (x, yb + 0.5, z), 9.5))
    plate = cad.countersink(plate, (x, YB + PLATE_T, z), "-Y", 2.9, 5.6, 90.0)
    screws.append(cad.screw("csk_phillips", SCREW, round(PLATE_T + 10.0), at=(x, YB + PLATE_T, z), axis="-Y"))
# board retention: a rib from the front wall onto the spine (0.2 mm off)
front = cad.fuse_one(front, box(29, 31, YF + WALL - 0.5, BB.YMin - 0.2, BZ + 30, BZ + 42))
tick("back + screws")

# ------------------------------------------------------------ the face
# the moon: ONE frosted insert filling a round opening over the four
# lights, domed MOON_DOME at its centre, a light pipe from its back to
# 0.4 mm off each LED grid
MX, MZ = 30.0, (BB.ZMax - 40.0 + BB.ZMax) / 2         # between the two top rows
front, moon = insert(front, cyl(MOON_R, (MX, YF + WALL + 1, MZ), WALL + 2))
RS = (MOON_R ** 2 + MOON_DOME ** 2) / (2 * MOON_DOME)  # the dome's sphere
dome = Part.makeSphere(RS, V(MX, YF - MOON_DOME + RS, MZ))
moon = cad.fuse_one(moon, dome.common(cyl(MOON_R, (MX, YF + 0.5, MZ), MOON_DOME + 1.0)))
for m in lights:
    cx, _cy, cz = centre(m)
    mb = ap.bbox(m)
    y0 = mb.YMin - 0.4
    moon = cad.fuse_one(moon, box(cx - 9.0, cx + 9.0, y0, YF + WALL - 0.5, cz - 9.0, cz + 9.0))
# the PIR eye: a black bezel (an insert, proud of the face) with an OPEN
# round window over the dome - infrared does not pass plastic or glass
ex, _ey, ez = centre(pir)
front, eye = insert(front, cyl(EYE_R, (ex, YF + WALL + 1, ez), WALL + 2))
eye = cad.fuse_one(eye, cyl(EYE_R, (ex, YF + 0.5, ez), 1.7))
eye = cad.cut(eye, cyl(WINDOW_D / 2, (ex, YF + WALL + 1, ez), WALL + 4))
# the mode key: a cap through the front, flange 0.1 mm behind the wall, a
# plunger to 0.16 mm off the button's own cap
kx, _ky, kz = centre(key)
kb = ap.bbox(key)
y_base = YF + WALL + 0.9
cap = cad.button_cap(KEY_D, y_base - (YF - 1.6), dome=0.8, flange=1.5, at=(kx, y_base, kz), axis="-Y")
front = cad.opening_for(front, cap, clearance=0.25, chamfer=0.4, axis="-Y")
cap = cad.fuse_one(cap, cyl(3.0, (kx, kb.YMin - 0.16, kz), (kb.YMin - 0.16) - y_base + 0.5))
# USB-C in the bottom: a pocket brings the wall to 0.25 mm off the mouth
# (the liner stops 0.3 mm short of the back's board ledge, y 0.6)
ub = ap.bbox(usb)
ux, uy = (ub.XMin + ub.XMax) / 2, BB.YMin + 4.5 - 5.9          # the receptacle: 5.9 mm off the PCB top
pocket = zprism(ux - 6.5, ux + 6.5, uy - 3.25 - 1.5, uy + 3.25 + 1.5, PB - 5, ub.ZMin - 1.3, 3)
liner = cad.cut(zprism(ux - 8.5, ux + 8.5, YF + WALL - 0.5, min(uy + 7.0, 0.3), PB + 1.0,
                       ub.ZMin - 0.25, 3.5), pocket)
front = cad.fuse_one(cad.cut(front, pocket), liner)
front = cad.socket_opening(front, usb, margin=1.5)
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# the eye: the window's mouth flared (a wider field of view), a visor over
# its top half that shades it toward the floor
eye = cad.cut(eye, Part.makeCone(WINDOW_D / 2, WINDOW_D / 2 + 1.6, 1.2, V(ex, YF - 0.0, ez), V(0, -1, 0)))
tube = cad.cut(cyl(WINDOW_D / 2 + 1.0 + VISOR[0], (ex, YF - 1.0, ez), VISOR[1]),
               cyl(WINDOW_D / 2 + 1.0, (ex, YF, ez), VISOR[1] + 2))
eye = cad.fuse_one(eye, tube.common(box(ex - 20, ex + 20, YF - 20, YF, ez + 0.5, ez + 20)))
# the front / back reveal, a raised rim round the moon and round the key
front = cad.groove_ring(front, "Y", SPLIT_Y - 2.0, w=0.8, depth=0.6)
front = cad.fuse_one(front, cad.cut(cyl(MOON_R + RIM[0], (MX, YF + 0.5, MZ), RIM[1] + 0.5),
                                    cyl(MOON_R + 0.15, (MX, YF + 1.0, MZ), RIM[1] + 2.0)))
front = cad.fuse_one(front, cad.cut(cyl(KEY_D / 2 + 3.0, (kx, YF + 0.5, kz), 1.1),
                                    cyl(KEY_D / 2 + 1.6, (kx, YF + 1.0, kz), 2.0)))
# legends: MODE over the key, AUTO over the eye, the wordmark between
front = cad.text(front, "MODE", (kx, YF, kz + EYE_R + 4.5), (0, -1, 0), 3.5, depth=0.4, mode="deboss")
front = cad.text(front, "AUTO", (ex, YF, ez + EYE_R + 4.5), (0, -1, 0), 3.5, depth=0.4, mode="deboss")
front = cad.text(front, "ATECH", (30.0, YF, (ez + EYE_R + MZ - MOON_R) / 2 + 3.0), (0, -1, 0), 5.0,
                 depth=0.4, mode="deboss")
# two keyholes in the plate's back (blind: the wall screw's head goes in
# the round hole, the plate drops onto it; the head runs in a pocket)
KZ = ZT - CORNER
for kxh in (30 - 0.22 * WIDTH, 30 + 0.22 * WIDTH):
    plate = cad.cut(plate, [cyl(4.2, (kxh, YB + PLATE_T + 1, KZ), 4.5),
                            box(kxh - 2.2, kxh + 2.2, YB + PLATE_T + 1, YB + PLATE_T - 2.0, KZ, KZ + 9),
                            box(kxh - 4.2, kxh + 4.2, YB + PLATE_T - 2.0, YB + PLATE_T - 3.5, KZ, KZ + 9)])
# four rubber bumpers in 1.2 mm recesses in the plate's back
BUMPS = [(X0 + CORNER * 0.5, PB + CORNER * 0.35), (X1 - CORNER * 0.5, PB + CORNER * 0.35),
         (30 - 0.2 * WIDTH, ZT - 9.0), (30 + 0.2 * WIDTH, ZT - 9.0)]
bumpers = []
for bx, bz in BUMPS:
    plate = cad.cut(plate, cyl(4.1, (bx, YB + PLATE_T + 1, bz), 2.2))
    bumpers.append(cyl(4.0, (bx, YB + PLATE_T - 1.2, bz), 2.6, (0, 1, 0)))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour=None):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour or name])
    return o


for nm, sh in (("Back", back), ("Front", front), ("Eye_Bezel", eye), ("Wall_Plate", plate)):
    part(nm, sh)
part("Mode_Key", cap)
o = part("Moon", moon)
o.ViewObject.Transparency = cad.transparency("frosted")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
for i, sh in enumerate(bumpers):
    part("Bumper_%d" % (i + 1), sh, "Bumper")
print("TOTAL %.1f s" % (time.time() - T0))
