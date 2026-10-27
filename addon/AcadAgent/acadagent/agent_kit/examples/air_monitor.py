"""Example: "a room air quality monitor" - a soft slab leaning back in a wedge plinth, a vented sensor chamber beside the readout.

fork this file for a room sensor / air monitor (a CO2 meter, a radon
monitor, a hygrometer, any sensor that breathes room air beside a
readout); change PARAMETERS and the outlines.
ARCHETYPE: air monitor

How it is built (R803):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board LANDSCAPE_UP in the body (modules facing the front, -Y): the
    screen (10, 11) behind a smoked lens in a recessed black bezel tray
    (CO2 / temperature / humidity readout), the status light (2) behind a
    frosted light pipe, the MODE key (3) under a key cap with a plunger,
    USB-C (7) in a pocket in the left side - all at the left, away from
    the sensors. The scd40_air_quality CO2 sensor (6) and temp_humidity
    (14) sit at the right end in a SENSOR CHAMBER: a partition at x 90
    (ports 5 / 13 left empty for it) walls them off from the board, the
    screen and the USB-C - a front piece to 0.3 mm off the port housings
    and the spine, a back piece behind the board. Room air comes in low
    through the slots of a graphite vent panel (an insert in the face)
    over the CO2 sensor, rises past both sensors and leaves through the
    panel's upper slots and slots in the top wall (a chimney). The body:
    one rounded slab (cad.rounded_box, CORNER corners seen from the
    front, the face's edge rolled EDGE, the back's softer), hollowed with
    a sharp core, split FRONT / BACK behind the board with a lip; the back
    carries the board on ledges and standoffs; four M2.5 screws from the
    back into heat-set insert bosses on the front (the right pair on the
    partition). The whole monitor LEANS BACK TILT degrees as one Placement
    (TP: built upright, the board placed through it) and stands sunk in a
    wedge plinth (a stadium in plan, its top parallel to the body's
    bottom), pinned into the back half.
  * STAGE B - details: a chrome halo ring round the status light, a
    green / amber / red pip legend beside it, MODE and CO2 legends, a hex
    heat vent and lettering on the back, lettering on the plinth, rubber
    feet.
RESTYLE (R803): WIDTH, HEIGHT, DEPTH, CORNER and WALL drive every outline
and every cutter below; the front's inner face stays 2.4 mm in front of
the CO2 sensor whatever the wall (YF), the vent panel and the top slots
follow the right corner, the plinth and its feet follow the body. The
hardware frame (the board at x 0..120, z 16..76 before the lean) is the
board's own: never move it with a knob.
DETAILS (visible, 28): 1 soft slab body with big corners; 2 rolled face
edge; 3 softer rolled back edge; 4 front / back parting reveal; 5 the face
leaning back 12 deg; 6 a wedge plinth, a stadium in plan; 7 the body sunk
in its pocket; 8 smoked display lens; 9 recessed black bezel round it;
10 black mask with the screen window; 11 frosted status light pipe;
12 chrome halo ring round it; 13-15 green / amber / red legend pips;
16 sage MODE key cap; 17 "MODE" legend; 18 graphite vent panel; 19 low
inlet slots over the CO2 sensor; 20 high slots over temp / humidity;
21 "CO2" on the panel; 22 exhaust slots in the top wall; 23 USB-C pocket
with liner in the left side; 24 hex heat vent on the back; 25 "ATECH" on
the back; 26 "ATECH" on the plinth; 27 four countersunk screws in the
back; 28 four rubber feet.
Inside: the sensor-chamber partition (front and back pieces), heat-set
insert bosses, board ledges and standoffs, a rib onto the board's spine,
the front / back lip, two pins from the plinth into the back half, a
plunger on the key, the light pipe's flange.
Materials: warm white body, sand plinth, graphite vent panel, smoked
lens, black bezel, frosted light pipe, chrome halo and screws, sage key,
green / amber / red pips, rubber feet.
MEASURED (R803, 2026-10-27): ./check CHECK PASS, see test_kit_examples_r500 (TIMINGS line).
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
    "Front", "Bezel", "Lens", "Status_Lens", "Mode_Key", "Vent_Panel", "Halo", "Pip_Green", "Pip_Amber",
    "Pip_Red", "Plinth", "Rubber_1", "Rubber_2", "Rubber_3", "Rubber_4",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    "covers": {"Mode_Key": "button_p3"}}
REVIEW_CLOSEUPS = ["Vent_Panel", "Lens", "Status_Lens"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them (the hardware frame below is
# the board's own: never move it with a knob).
WIDTH = 160.0      # RESTYLE 136..184 width: the body across (x), centred on the board
HEIGHT = 108.0     # RESTYLE 91.5..124.5 height: the body, bottom to top (z, before the lean)
DEPTH = 38.0       # RESTYLE 32..44 length: front face to back (y)
CORNER = 22.0      # RESTYLE 18.5..25.5 radius: the body's corners seen from the front
WALL = 2.4         # RESTYLE 2.0..2.8 wall
# end RESTYLE
# Body frame: x across, y front (-) to back, z up, the body's bottom on
# z = 0. The finished monitor LEANS BACK TILT degrees about its back-bottom
# edge and stands LIFT mm up in a wedge plinth (TP: body frame -> world).
# The hardware frame (fixed: the board decides it):
ZB = 16.0                            # board bottom (board x 0..120, z 16..76)
Y_IN = -13.0                         # the front wall's inner face (2.4 mm off the CO2 sensor)
TILT, LIFT, SINK = 12.0, 7.5, 3.5    # the lean, the body's back-bottom over the desk, sunk in the plinth
RUB = 1.5                            # the plinth stands on rubber feet RUB high
EDGE = 3.0                           # the soft fillet round the face and the back
X0, X1 = 60.0 - WIDTH / 2, 60.0 + WIDTH / 2
YF = Y_IN - WALL                     # the face
YB = YF + DEPTH                      # the back
ZT = HEIGHT
LENS_HW, LENS_HH, LENS_R, BEZEL, RECESS = 18.0, 12.0, 3.0, 3.5, 1.0
SCREEN_WIN = (28.0, 16.0)            # mask window over the screen (active area 25.6 x 13.5)
PART_X = 90.0                        # the chamber partition (between empty ports 5 / 13)
PANEL_X0 = 94.5                      # the vent panel's left edge (clear of the screw bosses on the partition)
SCREW = "M2.5"
SCREW_X = (10.0, PART_X)             # screw columns over and under the board (clear of the bezel)
COLOURS = {"Front": "#eeeae2", "Back": "#eeeae2", "Bezel": "matte_black", "Lens": "smoked",
           "Status_Lens": "frosted", "Mode_Key": "#7f9c8a", "Vent_Panel": "graphite",
           "Plinth": "#c9b8a0", "Halo": "chrome", "Pip_Green": "led_green", "Pip_Amber": "#ffb020",
           "Pip_Red": "led_red", "Rubber": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
LANDSCAPE_UP = Rotation(Vector(0, 0, 1), 180).multiply(Rotation(Vector(0, 1, 0), -90))
TP = Placement(V(0, 0, LIFT), Rotation(V(1, 0, 0), -TILT), V(0, YB, 0))   # body frame -> world
board = ap.board_object(doc)
board.Placement = Placement(V(), LANDSCAPE_UP)
_b = ap.bbox(board)
upright = Placement(V(-_b.XMin, 0, ZB - _b.ZMin), LANDSCAPE_UP)          # x 0..120, z 16..76
board.Placement = upright
BB = ap.bbox(board)                             # in the body frame
board.Placement = TP.multiply(upright)          # the board leans; the modules seat on it
scr = ap.seat(doc, "screen", (10, 11))          # top row, left of centre: the readout
status = ap.seat(doc, "light", 2)               # bottom row, under the screen's left: the status light
key = ap.seat(doc, "button", 3)                 # bottom row, under its right: MODE (cycle / silence)
co2 = ap.seat(doc, "scd40_air_quality", 6)      # bottom row, right end: the chamber's inlet side
th = ap.seat(doc, "temp_humidity", 14)          # top row, right end: over it in the chamber
usb = ap.seat(doc, "usbc", 7)                   # left end, mouth -X: far from the sensors
tick("hardware")


def ibox(m):
    """A module's box in the UPRIGHT body frame."""
    g = (m.Mesh if hasattr(m, "Mesh") else m.Shape).copy()
    g.Placement = TP.inverse().multiply(g.Placement)
    return g.BoundBox


def T(s):
    """Body frame -> world (the lean)."""
    s = s.copy()
    s.Placement = TP.multiply(s.Placement)
    return s


def box(x0, x1, y0, y1, z0, z1):
    (x0, x1), (y0, y1), (z0, z1) = sorted((x0, x1)), sorted((y0, y1)), sorted((z0, z1))
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, -1, 0)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(m):
    b = ibox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


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


# ------------------------------------------------------------ the body
# the face: a soft rounded rectangle (CORNER) extruded front to back, the
# face's edge rolled EDGE, the back's edge rolled softer (BACK_R)
BACK_R = min(7.0, 0.18 * DEPTH)
outer = cad.rounded_box(WIDTH, DEPTH, HEIGHT, CORNER, at=(X0, YF, 0.0), edges="y")
outer = cad.fillet_safe(outer, EDGE, edges=[e for e in outer.Edges if e.BoundBox.YMax < YF + 0.01])
outer = cad.fillet_safe(outer, BACK_R, edges=[e for e in outer.Edges if e.BoundBox.YMin > YB - 0.01])


def slab(t):
    """The body moved t in all round, sharp edges (the core, the skin)."""
    return cad.rounded_box(WIDTH - 2 * t, DEPTH - 2 * t, HEIGHT - 2 * t, CORNER - t, at=(X0 + t, YF + t, t),
                           edges="y")


# the core keeps SHARP inner edges (a filleted core's concave rounds read
# to ./check as open clip channels - the handheld's lesson)
# - its back edges rounded concentric with the back's (BACK_R - WALL), or
# the sharp core corner would cut through the soft back edge
core, skin = slab(WALL), slab(0.5)
core = cad.fillet_safe(core, BACK_R - WALL, edges=[e for e in core.Edges if e.BoundBox.YMin > YB - WALL - 0.01])
hull = cad.cut(outer, core)
# the parting-line reveal goes in BEFORE the split (it needs a closed ring)
SPLIT_Y = BB.YMax + 0.3
hull = cad.groove_ring(hull, "Y", SPLIT_Y - 2.0, w=0.8, depth=0.6)
front, back = cad.split(hull, "Y", at=SPLIT_Y, lip=1.2)
tick("body")

# ------------------------------------------------------------ back: holds the board
YI = YB - WALL + 0.5                            # into the back wall
# (the top ledge in two runs, clear of the top screw columns)
ledges = [box(4, 116, 0.6, YI, BB.ZMin - 2.3, BB.ZMin - 0.3)]
ledges += [box(a, b, 0.6, YI, BB.ZMax + 0.3, BB.ZMax + 2.3) for a, b in ((SCREW_X[0] + 5, PART_X - 5), (PART_X + 5, 116))]
ledges += [box(x, x + 6, BB.YMax + 0.1, YI, BB.ZMin + z, BB.ZMin + z + 6) for x in (8, 57, 106) for z in (7, 47)]
back = cad.fuse_one(back, *[lg.common(skin) for lg in ledges])
# four M2.5 screws from behind into insert bosses on the front (columns
# over and under the board; the right pair rides the chamber partition)
INSERT_D = {"M2": 3.2, "M2.5": 3.6, "M3": 4.3}[SCREW]
SCREW_Z = (BB.ZMin - 6.5, (BB.ZMax + 0.4 + ZT - BACK_R) / 2)    # the heads on the back's flat
SCREWS = [(x, z) for x in SCREW_X for z in SCREW_Z]
screws = []
for x, z in SCREWS:
    back, front = cad.screw_through(back, front, (x, YB, z), size=SCREW, ribs=0)
    yb = YB - WALL - 0.1
    front = cad.fuse_one(front, cyl(INSERT_D / 2 + 1.2, (x, yb, z), 10.0))
    front = cad.cut(front, cyl(INSERT_D / 2, (x, yb + 0.5, z), 9.5))
    screws.append(cad.screw("csk_phillips", SCREW, round(WALL + 8.0), at=(x, YB, z), axis="-Y"))
# board retention: a rib from the front wall onto the spine (0.2 mm off)
front = cad.fuse_one(front, box(58, 62, Y_IN - 0.5, BB.YMin - 0.2, 40, 52))
tick("back + screws")

# ------------------------------------------------------------ the sensor chamber
# a partition at PART_X walls the sensors (right end) off the board, the
# screen and the USB-C: a front piece to 0.3 mm off the board (port
# housings, the spine), a back piece behind the board
zi0, zi1 = WALL - 0.5, ZT - WALL + 0.5
pf = cad.cut(box(PART_X - 1, PART_X + 1, Y_IN - 0.5, 0.6, zi0, zi1),
             [box(PART_X - 2, PART_X + 2, -2.8, 1, BB.ZMin - 0.3, BB.ZMax + 0.3),
              box(PART_X - 2, PART_X + 2, BB.YMin - 0.3, 1, BB.ZMin + 18.7, BB.ZMin + 41.3)])
pf = pf.common(skin).common(outer)
front = cad.fuse_one(front, pf)
# (the front's screw columns cross it: they cut it into pieces, each one
# standing on the back's floor or hanging from its top - fused one by one)
pb = box(PART_X - 1, PART_X + 1, 0.6, YI, zi0, zi1).cut(box(PART_X - 2, PART_X + 2, 0, BB.YMax + 0.1,
                                                            BB.ZMin - 0.3, BB.ZMax + 0.3))
pb = pb.common(skin).common(outer).cut(Part.makeCompound([cyl(INSERT_D / 2 + 1.5, (PART_X, YB + 1, z), DEPTH) for z in SCREW_Z])).cut(front)
back = cad.fuse_one(back, *[s_ for s_ in pb.Solids if s_.Volume > 5.0])
tick("partition")

# ------------------------------------------------------------ the face
# the readout: a black bezel tray set RECESS back in its opening, holding
# the smoked lens, its back the mask with the screen window (0.36 mm off
# the screen)
sx, _sy, sz = centre(scr)
lx0, lx1, lz0, lz1 = sx - LENS_HW, sx + LENS_HW, sz - LENS_HH, sz + LENS_HH
front = cad.cut(front, yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, YF - 6, Y_IN + 1))
yt0, yt1 = YF + RECESS, Y_IN + 3.0
tray = cad.fuse_one(yprism(lx0 - BEZEL, lx1 + BEZEL, lz0 - BEZEL, lz1 + BEZEL, LENS_R + BEZEL, yt0, Y_IN + 1),
                    yprism(lx0 - 2, lx1 + 2, lz0 - 2, lz1 + 2, LENS_R + 2, Y_IN + 0.5, yt1))
y_lens1 = Y_IN + 1.7
tray = cad.cut(tray, yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 - 1, y_lens1))
lens = yprism(lx0, lx1, lz0, lz1, LENS_R, yt0 + 0.6, y_lens1 - 0.3)          # 0.3 mm air before the mask
tray = cad.cut(tray, cad.rounded_box(SCREEN_WIN[0], 10, SCREEN_WIN[1], 1.5,
                                     at=(sx - SCREEN_WIN[0] / 2, yt1 - 5, sz - SCREEN_WIN[1] / 2), edges="y"))
# the status light: a frosted light pipe from 0.4 mm off the LEDs to
# 0.8 mm proud, a flange behind the wall
gx, _gy, gz = centre(status)
gb = ibox(status)
pipe = cad.lens(16.0, (gb.YMin - 0.4) - (YF - 0.8), dome=0.8, at=(gx, gb.YMin - 0.4, gz), axis="-Y")
front = cad.opening_for(front, pipe, clearance=0.2, chamfer=0.0, axis="-Y")
pipe = cad.fuse_one(pipe, cyl(9.6, (gx, Y_IN + 0.9, gz), 0.8))
# MODE: a cap through the face, flange 0.1 mm behind the wall, a plunger
# to 0.16 mm off the module's own cap
kx, _ky, kz = centre(key)
kb = ibox(key)
y_base = Y_IN + 0.9
cap = cad.button_cap(12.0, y_base - (YF - 1.6), dome=0.8, flange=1.5, at=(kx, y_base, kz), axis="-Y")
front = cad.opening_for(front, cap, clearance=0.25, chamfer=0.4, axis="-Y")
cap = cad.fuse_one(cap, cyl(3.0, (kx, kb.YMin - 0.16, kz), (kb.YMin - 0.16) - y_base + 0.5))
# the chamber's face: a graphite vent panel (an insert filling its opening
# in the face), vertical slots over both sensors - low over the CO2 sensor
# (the inlet), high over temp / humidity - and slots in the top wall over
# the chamber (the outlet: room air rises through it like a chimney)
PE = EDGE + 3.0
px1, pz0, pz1 = X1 - PE, PE, ZT - PE
pr = min(CORNER - PE, 0.5 * (px1 - PANEL_X0) - 0.5)
pcut = cad.rounded_box(px1 - PANEL_X0, Y_IN + 1 - (YF - 1), pz1 - pz0, pr, at=(PANEL_X0, YF - 1, pz0), edges="y")
panel, front = front.common(pcut), front.cut(pcut)
cb, tb = ibox(co2), ibox(th)
vx = (cb.XMin + cb.XMax) / 2
vw = min(cb.XMax - cb.XMin + 2.0, 2 * (px1 - vx) - 1.0, 2 * (vx - PANEL_X0) - 1.0)
panel = cad.grille(panel, (vx, YF, (pz0 + 2 + cb.ZMax) / 2), (0, -1, 0), (vw, cb.ZMax - pz0 - 2),
                   kind="slot", hole=2.0, pitch=3.4)
panel = cad.grille(panel, (vx, YF, (tb.ZMin + pz1 - 2) / 2), (0, -1, 0), (vw, pz1 - 2 - tb.ZMin),
                   kind="slot", hole=2.0, pitch=3.4)
tx1 = min(X1 - CORNER, px1 - 4.0)
front = cad.grille(front, ((PANEL_X0 + tx1) / 2, (Y_IN - 0.5) / 2, ZT), (0, 0, 1),
                   (tx1 - PANEL_X0 + 1.0, -0.5 - Y_IN), kind="slot", hole=2.0, pitch=3.4)
# USB-C on the left side: a pocket brings the wall to 0.25 mm off the
# socket mouth, then the measured opening (cut by hand in the body frame)
ub = ibox(usb)
uy, uz = -5.9, (ub.ZMin + ub.ZMax) / 2
pocket = xprism(uy - 4.5, uy + 4.5, uz - 6.5, uz + 6.5, X0 - 5, ub.XMin - 1.3, 3)
liner = cad.cut(xprism(Y_IN - 0.4, min(uy + 6.5, SPLIT_Y - 0.6), uz - 8.0, uz + 8.0, ub.XMin - 0.25, X0 + WALL - 0.5,
                       3.0), pocket)
front = cad.fuse_one(cad.cut(front, pocket), liner)
front = cad.cut(front, xprism(uy - 3.25, uy + 3.25, uz - 6.5, uz + 6.5, ub.XMin - 2.0, ub.XMin - 0.1, 1.5))
tick("face")

# ------------------------------------------------------------ the lean and the plinth
front, back, tray, lens, pipe, cap, panel = [T(s_) for s_ in (front, back, tray, lens, pipe, cap, panel)]
screws = [T(s_) for s_ in screws]
# a wedge plinth in the WORLD: its top parallel to the leaning body's
# bottom, SINK over it; the body's own bottom cut out of it (a pocket)
tn = math.tan(math.radians(TILT))
yfw = YB + (YF - YB) * math.cos(math.radians(TILT))          # the face's foot, world y
PF, PBK = 7.0, 5.0                                           # the plinth past the face / the back
pzt = lambda y: LIFT + SINK - (y - YB) * tn                  # noqa: E731
PX0, PX1 = X0 + 0.35 * CORNER, X1 - 0.35 * CORNER
sec = [(yfw - PF - 1, RUB - 1.0), (YB + PBK + 1, RUB - 1.0), (YB + PBK + 1, pzt(YB + PBK + 1)),
       (yfw - PF - 1, pzt(yfw - PF - 1))]
wedge = Part.Face(Part.makePolygon([V(PX0 - 1, y, z) for y, z in sec + sec[:1]])).extrude(V(PX1 - PX0 + 2, 0, 0))
PL_R = 0.5 * (YB + PBK - (yfw - PF)) - 0.5         # round ends in plan (a stadium)
plinth = cad.rounded_box(PX1 - PX0, YB + PBK - (yfw - PF), pzt(yfw - PF) + 1.0 - RUB, PL_R,
                         at=(PX0, yfw - PF, RUB)).common(wedge)
plinth = cad.fillet_safe(plinth, 3.0, edges=[e for e in plinth.Edges if e.BoundBox.ZMin > 1.0])
plinth = cad.cut(plinth, T(outer.common(box(X0 - 5, X1 + 5, YF - 5, YB + 5, -1, 25))))
pins_xy = [(20.0, (SPLIT_Y + 2.5 + YB - WALL) / 2), (100.0, (SPLIT_Y + 2.5 + YB - WALL) / 2)]
plinth = cad.fuse_one(plinth, *[T(cyl(1.2, (x, y, -0.5), WALL + 1.5, (0, 0, 1))) for x, y in pins_xy])
back = cad.cut(back, [T(cyl(1.35, (x, y, -1), WALL + 3, (0, 0, 1))) for x, y in pins_xy])
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)


def W_(p):
    """A body-frame point in the world."""
    return TP.multVec(V(*p))


def Wn(n):
    return TP.Rotation.multVec(V(*n))


OUT, UP, BACKN = Wn((0, -1, 0)), Wn((0, 0, 1)), Wn((0, 1, 0))
# the status light: a raised halo ring round its pipe, and a three-dot
# traffic-light legend beside it (green / amber / red pips, each an
# insert filling a 0.8 mm pocket, 0.4 mm proud)
# (the halo: a chrome ring filling a 0.8 mm annular pocket, 0.6 mm proud)
ring_cut = cad.cut(cyl(11.0, (gx, YF + 0.8, gz), 2.0), cyl(9.4, (gx, YF + 1.0, gz), 3.0))
front = cad.cut(front, T(ring_cut))
halo = T(cad.soften(cad.cut(cyl(11.0, (gx, YF + 0.8, gz), 1.4), cyl(9.4, (gx, YF + 1.0, gz), 3.0)), 0.3, None))
pips = {}
for nm, dz in (("Pip_Green", -5.5), ("Pip_Amber", 0.0), ("Pip_Red", 5.5)):
    pc = (gx - 15.5, YF, gz + dz)
    pocket = cyl(1.6, (pc[0], YF + 0.8, pc[2]), 2.0)
    front = cad.cut(front, T(pocket))
    pip = cad.soften(cyl(1.6, (pc[0], YF + 0.8, pc[2]), 1.2), 0.3, None)
    pips[nm] = T(pip)
# legends: MODE over the key, CO2 on the vent panel's solid band
at = W_((kx, YF, kz + 10.5))
front = cad.text(front, "MODE", at, OUT, 3.2, depth=0.4, mode="deboss", up=UP)
at = W_((vx, YF, (cb.ZMax + tb.ZMin) / 2))
panel = cad.text(panel, "CO2", at, OUT, 6.0, depth=0.5, mode="deboss", up=UP)
# the back: a hex heat vent behind the board, between its standoffs (its
# warmth leaves at the back, never through the sensor chamber), ATECH
back = cad.grille(back, W_((60.0, YB, ZB + 35.0)), BACKN, (56.0, 18.0), kind="hex",
                  hole=3.0, pitch=4.5)
back = cad.text(back, "ATECH", W_((60.0, YB, ZB + 14.0)), BACKN, 7, depth=0.5, mode="deboss", up=UP)
plinth = cad.text(plinth, "ATECH", (60.0, yfw - PF, 0.55 * pzt(yfw - PF)), (0, -1, 0), 4.5, depth=0.4,
                  mode="deboss")
# rubber feet in recesses under the plinth
feet = []
for x in (PX0 + PL_R, PX1 - PL_R):
    for y in (yfw - PF + 0.5 * PL_R, YB + PBK - 0.5 * PL_R):
        plinth = cad.cut(plinth, cyl(4.6, (x, y, RUB - 1), 2.2, (0, 0, 1)))
        feet.append(cad.foot(9, RUB + 1.2, style="dome", at=(x, y, RUB + 1.2)))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape, colour=None):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    c = COLOURS[colour or name]
    o.ViewObject.ShapeColor = cad.color(c)
    if c in ("smoked", "frosted", "glass"):
        o.ViewObject.Transparency = cad.transparency(c)
    return o


for nm, sh in (("Back", back), ("Front", front), ("Bezel", tray), ("Lens", lens), ("Status_Lens", pipe),
               ("Mode_Key", cap), ("Vent_Panel", panel), ("Plinth", plinth)):
    part(nm, sh)
part("Halo", halo)
for nm, sh in pips.items():
    part(nm, sh)
for i, sh in enumerate(feet):
    part("Rubber_%d" % (i + 1), sh, "Rubber")
for i, sh in enumerate(screws):
    part("Screw_%d" % (i + 1), sh, "Screw")
print("TOTAL %.1f s" % (time.time() - T0))
