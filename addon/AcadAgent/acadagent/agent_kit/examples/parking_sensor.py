"""Example: "a garage parking assistant" - a traffic-light pod on a wall sign plate, ranging the bumper.

fork this file for a parking sign / wall-mounted signal (a garage parking
assistant, a stop / go light, a queue or room-busy sign, a wall
rangefinder); change PARAMETERS and the outlines.
ARCHETYPE: parking sign

How it is built (R425):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board UPRIGHT_FRONT in the pod (portrait, modules facing the car, -Y;
    the wall behind, +Y). The right column is the traffic light: three
    lights SEATED on 2 / 4 / 6 (green, amber, red, 40 mm apart) behind
    round lenses in a black signal panel, each lens carrying a light pipe
    to 0.4 mm off its LED grid, each with a hood over it. The left column:
    the distance sensor on 9 (bottom) behind an OPEN slot in a black eye,
    the SET key on 10 (a key cap through the front), the screen on the
    pair (13, 14) behind a smoked lens in a black bezel; USB-C on 7 in a
    pocket in the bottom (the cable drops to the socket below). Ports 8
    and 12 stay empty (reserved: the firmware cannot drive them). The pod:
    one rounded slab (cad.rounded_box, big plan corners, the front edge
    rolled), hollowed with a sharp core, split FRONT / BACK behind the
    modules (the back is fixed: it carries the board on ledges and
    standoffs); three M2.5 screws from the wall side, through the wall
    plate and the back, into insert bosses in the front. The wall plate
    (the sign board) stands proud of the pod all round, a blue "P" sign on
    it above the pod and two keyholes in its back.
  * STAGE B - details: the front / back reveal, lens hoods, the raised
    ring round the key, legends, the plate's rolled edge, lettering.
RESTYLE (R425): WIDTH, HEIGHT, DEPTH, CORNER and WALL drive every outline
and every cutter below; the front's inner face stays 2.6 mm in front of
the modules whatever the wall (YF), the screws follow the corners
(screw_at). The hardware frame (the board at x 0..60, BZ above the pod's
floor) is the board's own: never move it with a knob.
DETAILS (visible, 28): 1 pod slab with big corners; 2 rolled front edge;
3 front / back reveal; 4 black signal panel; 5-7 red / amber / green
lenses, domed; 8-10 a hood over each lens; 11 smoked screen lens; 12 black
bezel round it; 13 black sensor eye; 14 its open ranging slot; 15 SET key
cap; 16 raised ring round it; 17 "SET" legend; 18 USB-C pocket with liner
in the bottom; 19 the wall plate, proud all round; 20 its rolled front
edge; 21 blue "P" sign; 22 the raised "P"; 23 "ATECH" on the plate's chin;
24-25 two keyholes in the plate's back; 26-28 three countersunk screws in
the plate's back.
Inside: light pipes, a rib onto the board's spine, board ledges and
standoffs, insert bosses, the front / back lip, a plunger on the key.
Materials: white pod, graphite wall plate, black signal panel, bezel and
eye, red / amber / green lenses, smoked screen lens, coral key, blue sign,
chrome screws.
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

INTENT = {"board": "upright", "fitted_after": [
    "Front", "Signal_Bezel", "Lens_Red", "Lens_Amber", "Lens_Green", "Screen_Lens", "Bezel",
    "Sensor_Eye", "Set_Key", "Wall_Plate", "P_Sign", "Screw_1", "Screw_2", "Screw_3"],
    "covers": {"Set_Key": "button_p10"}}
REVIEW_CLOSEUPS = ["Signal_Bezel", "Screen_Lens", "Sensor_Eye"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them; test_kit_examples_r280 builds
# this file with each knob at its min and at its max, one at a time.
WIDTH = 96.0       # RESTYLE 81.5..110.5 width: the pod across (x); 81.5: the hoods on the panel
HEIGHT = 170.0     # RESTYLE 144.5..195.5 height: the pod (z); 144.5: the board and the red hood
DEPTH = 30.0       # RESTYLE 25.5..34.5 length: the pod front to the wall (y)
CORNER = 18.0      # RESTYLE 15..21 radius: the pod's corners, seen from the front
WALL = 2.5         # RESTYLE 2.1..2.9 wall
# end RESTYLE
# Pod frame: x across (the viewer's right +), y from the car (-) to the
# wall (+), z up; the plate's bottom on z = 0.
X0, X1 = 30.0 - WIDTH / 2, 30.0 + WIDTH / 2     # the board's centre line x = 30
PB = 10.0                        # the pod's bottom (the plate's chin below it)
ZT = PB + HEIGHT                 # the pod's top
YF = -12.5 - WALL                # the front: its inner face 2.6 mm in front of the modules
YB = YF + DEPTH                  # the back (on the wall plate)
EDGE = 3.0                       # the rolled front edge
BZ = PB + WALL + 12.0            # the board's bottom: room for the USB-C pocket below
PLATE_T, PLATE_OUT = 6.0, 6.0    # the wall plate's thickness, how far it stands out round the pod
SIGN = 30.0                      # the blue "P" sign on the plate above the pod
LENS_R, HOOD = 13.0, (1.5, 11.0)  # lens radius; hood wall, reach
SCREEN_WIN = (22.0, 38.0, 3.0)   # smoked lens over the screen (portrait: 13.5 x 25.6 active)
BEZEL = 4.0
EYE = (30.0, 18.0)               # the sensor's black eye; its open slot 18 x 10 (>= 10 x 6)
SLOT = (18.0, 10.0)
KEY_D = 12.0
SCREW = "M2.5"
COLOURS = {"Front": "matte_white", "Back": "matte_white", "Signal_Bezel": "matte_black",
           "Lens_Red": "led_red", "Lens_Amber": "#ffb020", "Lens_Green": "led_green",
           "Screen_Lens": "smoked", "Bezel": "matte_black", "Sensor_Eye": "matte_black",
           "Set_Key": "coral", "Wall_Plate": "graphite", "P_Sign": "toy_blue", "Screw": "chrome"}


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
lights = {"Lens_Green": ap.seat(doc, "light", 2),   # the traffic light, bottom to top
          "Lens_Amber": ap.seat(doc, "light", 4),
          "Lens_Red": ap.seat(doc, "light", 6)}
tof = ap.seat(doc, "distance_sensor", 9)          # bottom left: low, toward the bumper
key = ap.seat(doc, "button", 10)
scr = ap.seat(doc, "screen", (13, 14))            # top left, portrait
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


def yslab(w, h, r, cx, cz, y0, y1):
    """A rounded rectangle w x h (x, z), corner r, from y0 to y1."""
    return cad.rounded_box(w, abs(y1 - y0), h, r, at=(cx - w / 2, min(y0, y1), cz - h / 2), edges="y")


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


# ------------------------------------------------------------ the pod
pod = cad.rounded_box(WIDTH, DEPTH, HEIGHT, CORNER, at=(X0, YF, PB), edges="y")
pod = cad.fillet_safe(pod, EDGE, edges=[e for e in pod.Edges if e.BoundBox.YMax < YF + 0.01])
pod = cad.fillet_safe(pod, 1.0, edges=[e for e in pod.Edges if e.BoundBox.YMin > YB - 0.01])
# the core keeps SHARP inner edges (a filleted core reads as clip channels)
core = cad.rounded_box(WIDTH - 2 * WALL, DEPTH - 2 * WALL, HEIGHT - 2 * WALL, CORNER - WALL,
                       at=(X0 + WALL, YF + WALL, PB + WALL), edges="y")
shell = cad.cut(pod, core)
tick("pod")
# the split stays behind the modules (their slide paths) and in front of
# the board's back: the back is the fixed half
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
# the wall plate: proud of the pod all round, the sign above it, rolled
# front edges
plate = cad.rounded_box(WIDTH + 2 * PLATE_OUT, PLATE_T, ZT + SIGN + 12.0, CORNER + PLATE_OUT,
                        at=(X0 - PLATE_OUT, YB, 0.0), edges="y")
plate = cad.fillet_safe(plate, 2.0, edges=[e for e in plate.Edges if e.BoundBox.YMax < YB + 0.01])


def screw_at(sx, sz):
    """A screw on the corner's diagonal, its sleeve 1.5 mm inside the
    rounded inner wall (it follows CORNER and WALL)."""
    cx = (X0 + CORNER) if sx < 0 else (X1 - CORNER)
    cz = (PB + CORNER) if sz < 0 else (ZT - CORNER)
    d = (CORNER - WALL - 4.5) / math.sqrt(2.0)
    return cx + sx * d, cz + sz * d


# three M2.5 screws from the wall side: through the plate and the back
# into insert bosses in the front (top right: the signal panel is there)
SCREWS = [screw_at(-1, -1), screw_at(1, -1), screw_at(-1, 1)]
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
front = cad.fuse_one(front, box(29, 31, YF + WALL - 0.5, BB.YMin - 0.2, BZ + 50, BZ + 62))
tick("back + screws")

# ------------------------------------------------------------ the face
# the traffic light: a black signal panel that fills its opening in the
# front (an insert), a round lens in it over each light (an insert in the
# panel), its light pipe back to 0.4 mm off the LEDs
lx = centre(lights["Lens_Red"])[0]
PZ0, PZ1 = BZ + 8.0, min(BZ + 132.0, ZT - EDGE - 1.5)
PX1 = X1 - EDGE - 1.5
front, panel = insert(front, cad.rounded_box(PX1 - 34.0, WALL + 2, PZ1 - PZ0, 8.0, at=(34.0, YF - 1, PZ0),
                                            edges="y"))
lenses = {}
for nm, m in lights.items():
    cx, _cy, cz = centre(m)
    mb = ap.bbox(m)
    panel, lens = insert(panel, cyl(LENS_R, (cx, YF + WALL + 1, cz), WALL + 2))
    dome = Part.makeSphere(LENS_R * 3, V(cx, YF - 0.8 + LENS_R * 3, cz))
    lens = cad.fuse_one(lens, dome.common(cyl(LENS_R, (cx, YF + 0.5, cz), 2.0)),
                        cyl(9.6, (cx, mb.YMin - 0.4, cz), (mb.YMin - 0.4) - (YF + WALL - 0.3)))
    lenses[nm] = lens
# the screen: a smoked lens in a black bezel (both inserts), 2.9 mm in
# front of the screen
sx, _sy, sz = centre(scr)
front, bezel = insert(front, yslab(SCREEN_WIN[0] + 2 * BEZEL, SCREEN_WIN[1] + 2 * BEZEL, SCREEN_WIN[2] + BEZEL,
                                   sx, sz, YF - 1, YF + WALL + 1))
bezel, screen_lens = insert(bezel, yslab(SCREEN_WIN[0], SCREEN_WIN[1], SCREEN_WIN[2], sx, sz, YF - 1, YF + WALL + 1))
# the distance sensor: a black eye (an insert) with an OPEN slot - no
# glass over a ToF sensor
tx, _ty, tz = centre(tof)
front, eye = insert(front, yslab(EYE[0], EYE[1], EYE[1] / 2 - 0.01, tx, tz, YF - 1, YF + WALL + 1))
eye = cad.cut(eye, yslab(SLOT[0], SLOT[1], SLOT[1] / 2 - 0.01, tx, tz, YF - 2, YF + WALL + 2))
# the SET key: a cap through the front, flange 0.1 mm behind the wall, a
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
# a hood over each lens: the top half of a tube standing out of the panel
for nm, m in lights.items():
    cx, _cy, cz = centre(m)
    tube = cad.cut(cyl(LENS_R + HOOD[0], (cx, YF, cz), HOOD[1]), cyl(LENS_R, (cx, YF + 1, cz), HOOD[1] + 2))
    panel = cad.fuse_one(panel, tube.common(box(cx - 30, cx + 30, YF - 30, YF + 1, cz - 1.0, cz + 30)))
# the front / back reveal, a raised ring round the key, legends
front = cad.groove_ring(front, "Y", SPLIT_Y - 2.0, w=0.8, depth=0.6)
front = cad.fuse_one(front, cad.cut(cyl(KEY_D / 2 + 3.0, (kx, YF + 0.5, kz), 1.1),
                                    cyl(KEY_D / 2 + 1.6, (kx, YF + 1.0, kz), 2.0)))
front = cad.text(front, "SET", (kx, YF, kz + KEY_D / 2 + 6.5), (0, -1, 0), 4, depth=0.4, mode="deboss")
# the blue "P" sign on the plate above the pod (an insert in a 1.2 mm
# recess), the P raised on it; "ATECH" on the plate's chin
PZ = ZT + (SIGN + 12.0) / 2
plate, sign = insert(plate, cad.rounded_box(SIGN, 3.0, SIGN, 4.0, at=(30 - SIGN / 2, YB - 1.8, PZ - SIGN / 2),
                                            edges="y"))
sign = cad.text(sign, "P", (30, YB, PZ), (0, -1, 0), 0.6 * SIGN, depth=0.8, mode="emboss")
plate = cad.text(plate, "ATECH", (30, YB, PB / 2), (0, -1, 0), 4.5, depth=0.4, mode="deboss")
# two keyholes in the plate's back (blind: the wall screw's head goes in
# the round hole, the plate drops onto it; the head runs in a pocket)
for kxh in (30 - 0.3 * WIDTH, 30 + 0.3 * WIDTH):
    kz0 = PZ - 4.0
    plate = cad.cut(plate, [cyl(4.2, (kxh, YB + PLATE_T + 1, kz0), 5.5),
                            box(kxh - 2.2, kxh + 2.2, YB + PLATE_T + 1, YB + PLATE_T - 2.0, kz0, kz0 + 9),
                            box(kxh - 4.2, kxh + 4.2, YB + PLATE_T - 2.0, YB + PLATE_T - 4.5, kz0, kz0 + 9)])
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour=None):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    o.ViewObject.ShapeColor = cad.color(COLOURS[colour or name])
    return o


for nm, sh in (("Back", back), ("Front", front), ("Signal_Bezel", panel), ("Bezel", bezel),
               ("Sensor_Eye", eye), ("Wall_Plate", plate), ("P_Sign", sign)):
    part(nm, sh)
part("Set_Key", cap)
for nm, sh in lenses.items():
    o = part(nm, sh)
    o.ViewObject.Transparency = cad.transparency("glass")
o = part("Screen_Lens", screen_lens)
o.ViewObject.Transparency = cad.transparency("smoked")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
