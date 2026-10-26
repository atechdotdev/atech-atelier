"""Example: "a little desk robot" - a deep-bodied robot whose face is a screen.

fork this file for a desk robot / character product (a robot, a pet, a
mascot speaker, a figure with a face); change PARAMETERS and the outlines.
ARCHETYPE: robot or character

How it is built (R270):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board LANDSCAPE in the torso, modules facing the front (-Y): speaker
    (1, 2) behind the belly grille, button (3) under a key cap, microphone
    (4, 5) behind pin holes, USB-C (7) in a pocket in the left side; the
    SCREEN CABLED up the neck into the head (from the top-row pair 11/12,
    its ribbons jog forward inside the neck) right behind a big smoked
    visor. Torso (deep: depth / width 0.6, a crowned belly) and head from
    a front silhouette and a top outline (cad.profile_body), hollowed with
    their own cores, split front / back with a lip; the torso screwed
    together from behind into insert bosses, the head halves too (two
    screws in the side bands beside the visor); the screen held by ribs
    down from the head's top wall.
  * STAGE B - details: the visor bezel, a neck pivot collar, ears, arms,
    feet, an antenna, the belly speaker chamber, lettering.
DETAILS (visible, 30): 1 deep torso, crowned belly; 2 big head (the hero)
3 smoked visor over the screen; 4 raised visor bezel; 5 neck pivot collar
(brushed metal turntable); 6 collar groove; 7 round belly speaker grille;
8 speaker chamber to the driver; 9 mic pin holes; 10 mic seal ring;
11 raised ring round the mic; 12 key cap with flange and plunger;
13 raised ring round the key; 14 USB-C pocket with liner; 15 "ATECH"
on the chest; 16 rib onto the board's spine; 17 board ledges and
standoffs; 18 two screws from behind into insert bosses; 19 hex vents on
the back; 20 "ATECH" on the back; 21 front / back parting-line lip;
22 parting-line reveal round the head; 23-24 ear discs with pins;
25 antenna with a ball; 26-27 arms (one waving) on shoulder discs;
28 round hands; 29-30 long feet pinned into the torso.
Materials: white shells, sky backs and arms, smoked visor, black bezel,
brushed collar, coral ears and key, graphite feet, chrome screws.
MEASURED (R270, 2026-10-20): see test_kit_examples_r270 (TIMINGS line).
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
    "Torso_Front", "Head_Front", "Head_Back", "Face_Plate", "Face_Bezel", "Neck_Collar",
    "Arm_L", "Arm_R", "Foot_L", "Foot_R", "Ear_L", "Ear_R", "Button_Cap", "Screw_1", "Screw_2",
    "Screw_3", "Screw_4"],
    # the key cap presses the button through its opening (a declared cover)
    "covers": {"Button_Cap": "button_p3"}}
REVIEW_CLOSEUPS = ["Face_Plate", "Torso_Front", "Neck_Collar"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# R270: torso and head are each a front silhouette (x, z) and a top
# outline (x, y); every number below drives them. Front = -Y.
WALL = 2.0
TX0, TX1, TZ0, TZ1 = -7.0, 127.0, 9.9, 103.0     # torso box (5 mm round the hardware)
TY_BACK = 52.0                                   # torso back (depth / width = 0.6+)
TORSO_R = 14.0                                   # front silhouette corner radius
# the torso's top outline: lines and ONE arc - a crowned belly 5 mm proud at
# the middle (R270 robust recipe: a spline plan with a long straight back
# made every grille cut on the front INVALID, MEASURED); the speaker needs
# the inner wall at y <= -21.2 in front of it
BELLY_EDGE, BELLY_MID = -25.0, -30.0
TORSO_PLAN = [(-12, BELLY_EDGE), ("arc", (60, BELLY_MID), (132, BELLY_EDGE)), (132, TY_BACK), (-12, TY_BACK)]
NECK_Z = 10.0                                    # gap torso top -> head bottom (the collar)
HX0, HX1, HY0, HY1 = -6.0, 126.0, -34.0, 36.0    # head box in plan (the hero: wider than deep)
HEAD_H, HEAD_R = 90.0, 28.0                      # head height (>= 40 % of the robot), corner radius
VISOR = (100.0, 60.0, 12.0)                      # smoked visor w, h, corner r
SCREEN_Y = -24.5                                 # screen centre: right behind the visor
COLOURS = {"Torso_Back": "sky", "Torso_Front": "matte_white", "Head_Front": "matte_white",
           "Head_Back": "sky", "Face_Plate": "smoked", "Face_Bezel": "matte_black",
           "Neck_Collar": "brushed_alu", "Button_Cap": "coral", "Arm": "sky", "Ear": "coral",
           "Foot": "graphite", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
LANDSCAPE_UP = Rotation(Vector(0, 0, 1), 180).multiply(Rotation(Vector(0, 1, 0), -90))
board = ap.board_object(doc)


def place_board(rot, x0=0.0, y0=None, z0=0.0):
    board.Placement = Placement(Vector(), rot)
    bb = ap.bbox(board)
    board.Placement = Placement(Vector(x0 - bb.XMin, 0 if y0 is None else y0 - bb.YMin,
                                       z0 - bb.ZMin), rot)


place_board(LANDSCAPE_UP, 0, None, 36)        # x 0..120, z 36..96, modules face -Y
spk = ap.seat(doc, "speaker", (1, 2))          # hangs 20.6 below the board (belly)
btn = ap.seat(doc, "button", 3)
mic = ap.seat(doc, "microphone", (4, 5))
usb = ap.seat(doc, "usbc", 7)                  # left end, mouth -X
BB = ap.bbox(board)
HZ0 = TZ1 + NECK_Z
HZ1 = HZ0 + HEAD_H
SCREEN_Z = (HZ0 + HZ1) / 2
# the screen's ribbons rise from the top-row pair and jog forward up the
# neck (one shared route; each ribbon keeps its plug's offset)
scr, scr_ribs = ap.cable(doc, "screen", (11, 12), ap.module_placement(
    "screen", (60, SCREEN_Y, SCREEN_Z), face="-Y", cable="-Z"),
    via=[(60, -4, TZ1 - 6), (60, -12, HZ0 + 6)])
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, d, h):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def inset_pts(pts, plane, d, n):
    """A spline outline moved d inward, as fresh knots (a fillet on an OCCT
    offset curve fails - MEASURED down to 0.6 mm)."""
    w = cad.spline_wire(pts, plane=plane)
    o = w.makeOffset2D(-d, join=0)
    if o.Length > w.Length:
        o = w.makeOffset2D(d, join=0)
    return [(p.x, p.z) if plane == "XZ" else (p.x, p.y) for p in o.discretize(n)[:-1]]


def front_y(shape, x, z, back=False, nth=0):
    """The front (or back) surface's y at (x, z), measured with a ray;
    nth=1 gives the next face in (the front wall's inner face)."""
    s = shape.section(Part.makeLine(V(x, -200, z), V(x, 200, z)))
    ys = sorted(v.Point.y for v in s.Vertexes)
    return ys[-1 - nth] if back else ys[nth]


def insert(shell, cutter):
    """(shell with the opening, the piece it removed): a plate that fills
    its opening exactly. Exact booleans first, fuzzy (0.01 mm) after."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1:
        piece, rest = shell.common(cutter, 0.01), shell.cut(cutter, 0.01)
    if piece.Volume < 1 or not rest.isValid() or len(rest.Solids) != len(shell.Solids):
        raise cad.CadError("insert: the cutter does not cleanly cross the wall")
    return rest, piece


def hollow_profile(side_w, plan_pts, wall, r):
    """(shell, core): profile_body hollowed with its own core - the side
    wire offset (arcs stay arcs) and the plan re-knotted 2 mm in."""
    body = cad.profile_body(side_w, plan_pts, fillet=r)
    core = cad.profile_body(side_w.makeOffset2D(-wall, join=0), inset_pts(plan_pts, "XY", wall, 64),
                            fillet=r - wall)
    return cad.cut(body, core), core


def zprism(wire, z0, z1):
    f = Part.Face(wire)
    f.translate(V(0, 0, z0))
    return f.extrude(V(0, 0, z1 - z0))


# ------------------------------------------------------------ torso
torso_side = cad.rounded_rect_wire(TX1 - TX0, TZ1 - TZ0, TORSO_R, ((TX0 + TX1) / 2, 0, (TZ0 + TZ1) / 2), "Y")
torso = cad.profile_body(torso_side, TORSO_PLAN, spline=False, fillet=6)
torso = cad.hollow(torso, WALL, core=lambda t: cad.profile_body(torso_side, TORSO_PLAN, spline=False, fillet=6,
                                                                inset=t))
print("TORSO depth / width = %.2f" % ((TY_BACK - BELLY_MID) / (TX1 - TX0)))
tick("torso")
# the split stays behind the modules (their slide paths) and in front of
# the back edges' fillet zone (a lip needs a plain wall there)
SPLIT_Y = BB.YMax - 0.3
torso_f, torso_b = cad.split(torso, "Y", at=SPLIT_Y, lip=1.2)
tick("torso split")

# ------------------------------------------------------------ head + neck
head_side = cad.rounded_rect_wire(HX1 - HX0, HEAD_H, HEAD_R, ((HX0 + HX1) / 2, 0, (HZ0 + HZ1) / 2), "Y")
cx_h = (HX0 + HX1) / 2
head_plan = [(HX0 - 4, HY0 + 10), (HX0 + 10, HY0 + 2.5), (cx_h, HY0), (HX1 - 10, HY0 + 2.5),
             ("corner", (HX1 + 4, HY0 + 10)), ("line", (HX1 + 4, HY1)), ("line", (HX0 - 4, HY1))]
head, head_core = hollow_profile(head_side, head_plan, WALL, 8)
head_screws = []
NECK_Y = -10.0                                   # the neck sits forward: the collar wraps it
neck_o = cad.rounded_rect_wire(48, 20, 6, (60, NECK_Y, 0), "Z")     # carries both ribbons
neck_i = neck_o.makeOffset2D(-1.5, join=0)
neck = cad.cut(zprism(neck_o, TZ1 - 2.3, HZ0 + 1.0), zprism(neck_i, TZ1 - 5, HZ0 + 3))
head = cad.cut(head, zprism(neck_i, HZ0 - 1, HZ0 + 3))           # the ribbons' way in
# the neck's opening runs back to the split, so no sliver of wall is left
torso_f = cad.cut(torso_f, box(31.0, 89.0, NECK_Y - 14, SPLIT_Y + 1.5, TZ1 - 6, TZ1 + 1))
HSPLIT = 4.0
head_f, head_b = cad.split(head, "Y", at=HSPLIT, lip=1.2)
head_f = cad.fuse_one(head_f, neck)                              # the neck stays in front of the split
# R500: the head halves are SCREWED together like the torso (a lip only
# locates them): two M2.5 from the back, in the straight side bands
# between the side walls and the visor (clear of the ear pins, the bezel
# and the screen), into insert bosses that run forward to the front wall
HEAD_SCREWS = ((HX0 + 10, SCREEN_Z), (HX1 - 10, SCREEN_Z))
yb = HY1 - WALL - 0.1
for x, z in HEAD_SCREWS:
    head_b, head_f = cad.screw_through(head_b, head_f, (x, HY1, z), size="M2.5", ribs=0)
    head_screws.append(cad.screw("csk_phillips", "M2.5", 10, at=(x, HY1, z), axis="-Y"))
# R500: the cabled screen is HELD - ribs down from the head's top wall
# either side of it, 0.3 mm off (its face, -Y, and its ribbons, -Z, clear)
# (behind the visor's cutter, which ends at HY0 + 10: the visor plate
# sits 0.6 mm back from there). The ribs and both insert sleeves in ONE
# fuse, both insert pockets in ONE cut (TRAPS 12: each boolean on the
# curved head costs seconds)
sb_ = ap.bbox(scr)
ry0 = max(sb_.YMin + 1.0, HY0 + 10.0 + 0.8)
head_f = cad.fuse_one(head_f, *[box(x0, x1, ry0, sb_.YMax - 0.5, sb_.ZMin + 3.0, HZ1 - 1.0)
                                for x0, x1 in ((sb_.XMin - 1.6, sb_.XMin - 0.3),
                                               (sb_.XMax + 0.3, sb_.XMax + 1.6))],
                      *[cyl(3.0, (x, yb, z), (0, -1, 0), 10.0) for x, z in HEAD_SCREWS])
head_f = cad.cut(head_f, [cyl(1.8, (x, yb + 0.5, z), (0, -1, 0), 9.5) for x, z in HEAD_SCREWS])
tick("head")

# ------------------------------------------------------------ torso back: holds the board
# ledges under and over the board's long edges (0.3 mm clear), standoffs
# 0.1 mm behind it; two M2.5 screws from behind into insert bosses
TY1 = TY_BACK
ledges = [box(4, 116, 0.6, TY1 - WALL + 0.5, BB.ZMin - 2.3, BB.ZMin - 0.3),
          box(4, 116, 0.6, TY1 - WALL + 0.5, BB.ZMax + 0.3, BB.ZMax + 2.3)]
ledges += [box(x, x + 6, BB.YMax + 0.1, TY1 - WALL + 0.5, z, z + 6) for x in (8, 57, 106) for z in (43, 83)]
torso_b = cad.fuse_one(torso_b, *ledges)
screws = []
for x, z in ((52, 24), (108, 24)):
    torso_b, torso_f = cad.screw_through(torso_b, torso_f, (x, TY1, z), size="M2.5", ribs=0)
    # R270: a heat-set insert pocket (1.4 d + 0.1) in a sleeve at the
    # boss's end - the kit's pilot (= d) gives the screw nothing to bite
    yb = TY1 - WALL - 0.1
    torso_f = cad.fuse_one(torso_f, cyl(3.0, (x, yb, z), (0, -1, 0), 10.0))
    torso_f = cad.cut(torso_f, cyl(1.8, (x, yb + 0.5, z), (0, -1, 0), 9.5))
    screws.append(cad.screw("csk_phillips", "M2.5", 10, at=(x, TY1, z), axis="-Y"))
# a hex vent field, clear of the screws and standoffs (MEASURED R270: a
# slot field on this deep back made the cut INVALID; hex holes did not)
torso_b = cad.grille(torso_b, (60, TY1, 58), (0, 1, 0), (44, 12), kind="hex", hole=3.0, pitch=4.5)
tick("torso back")

# ------------------------------------------------------------ torso front: openings
sb, mb, bb_ = ap.bbox(spk), ap.bbox(mic), ap.bbox(btn)
sc, mc, bc = [((b.XMin + b.XMax) / 2, (b.ZMin + b.ZMax) / 2) for b in (sb, mb, bb_)]
y_spk, y_mic, y_btn, y_rib, y_txt = [front_y(torso_f, x, z) for x, z in (sc, mc, bc, (60, 66), (60, 86))]
# board retention: a rib from the front wall onto the spine (0.2 mm off)
torso_f = cad.fuse_one(torso_f, box(58, 62, y_rib + 1.6, BB.YMin - 0.2, 60, 72))
# speaker: a round grille over the measured surround, then a chamber
# tube from the wall to 0.5 mm off the driver (the sound goes out, not in)
torso_f = cad.speaker_grille(torso_f, (sc[0], y_spk, sc[1]), (0, -1, 0), 32, ring_pitch=2.6, hole=1.5)
torso_f = cad.fuse_one(torso_f, cad.cut(cyl(19.0, (sc[0], sb.YMin - 0.5, sc[1]), (0, -1, 0), (sb.YMin - 0.5) - (y_spk + 1.0)),
                                        cyl(17.4, (sc[0], sb.YMin, sc[1]), (0, -1, 0), 40)))
# microphone: a pin-hole cluster, then a ring rib that seals it to the mic
torso_f = cad.speaker_grille(torso_f, (mc[0], y_mic, mc[1]), (0, -1, 0), 14, ring_pitch=2.4, hole=1.5)
y_back = mb.YMin - 0.3                           # 0.3 mm in front of the mic face
torso_f = cad.fuse_one(torso_f, cad.cut(cyl(8.6, (mc[0], y_back, mc[1]), (0, -1, 0), y_back - (y_mic + 1.0)),
                                        cyl(7.4, (mc[0], y_back + 1, mc[1]), (0, -1, 0), 40)))
# the button: a key cap through the wall, flange behind it, a plunger to
# 0.16 mm off the module's own cap
# the flange 0.1 mm behind the wall's inner face, measured across the
# flange (the crowned front slopes: 0.27 mm over 14 mm, MEASURED)
y_base = max(front_y(torso_f, bc[0] + dx, bc[1], nth=1) for dx in (-8, 0, 8)) + 0.9
cap = cad.button_cap(12, y_base - (y_btn - 1.6), dome=0.8, flange=1.5, at=(bc[0], y_base, bc[1]), axis="-Y")
torso_f = cad.opening_for(torso_f, cap, clearance=0.25, chamfer=0.4, axis="-Y")
cap = cad.fuse_one(cap, cyl(3.0, (bc[0], bb_.YMin - 0.16, bc[1]), (0, -1, 0), (bb_.YMin - 0.16) - y_base + 0.5))
# USB-C on the left side: a pocket brings the wall to 0.25 mm off the
# socket mouth (a real plug reaches it), then the measured opening
ub = ap.bbox(usb)
uy, uz = -5.9, (ub.ZMin + ub.ZMax) / 2         # the receptacle: 5.9 mm above the PCB top


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


def pin_hole(x0, x1, y, z, a):
    """A soft-square hole 2a across through a side wall, for a round pin."""
    return xprism(y - a, y + a, z - a, z + a, x0, x1, 0.8 * a)


pocket = xprism(uy - 6.5, uy + 6.0, uz - 5.5, uz + 5.5, TX0 - 5, ub.XMin - 1.3, 3)
liner = cad.cut(xprism(uy - 8.5, min(uy + 8.0, SPLIT_Y - 0.6), uz - 7.5, uz + 7.5, ub.XMin - 0.25, TX0 + 1, 4),
                pocket)
torso_f = cad.fuse_one(cad.cut(torso_f, pocket), liner)
torso_f = cad.socket_opening(torso_f, usb, margin=1.5)
# the visor: a smoked plate cut out of the head's front (an insert that
# fills its opening), set 0.6 mm back; the screen sits right behind it
VZ = SCREEN_Z
head_f, face = insert(head_f, cad.rounded_box(VISOR[0], 20, VISOR[1], VISOR[2], at=(cx_h - VISOR[0] / 2, HY0 - 10,
                                                                                VZ - VISOR[1] / 2), edges="y"))
face.translate(V(0, 0.6, 0))
print("VISOR %.0f x %.0f in a %.0f x %.0f head front (%.0f %%)" % (
    VISOR[0], VISOR[1], HX1 - HX0, HEAD_H, 100 * VISOR[0] * VISOR[1] / ((HX1 - HX0) * HEAD_H)))
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# the visor bezel: a black frame round the visor that REPLACES the head
# wall there (an insert: it fills its ring exactly) and stands 1.6 mm
# proud of the head's most forward point
ring_o = cad.rounded_box(VISOR[0] + 10, 40, VISOR[1] + 10, VISOR[2] + 5,
                         at=(cx_h - VISOR[0] / 2 - 5, HY0 - 20, VZ - VISOR[1] / 2 - 5), edges="y")
ring_i = cad.rounded_box(VISOR[0], 50, VISOR[1], VISOR[2], at=(cx_h - VISOR[0] / 2, HY0 - 25, VZ - VISOR[1] / 2),
                         edges="y")
frame = cad.cut(ring_o, ring_i).common(box(-100, 300, HY0 - 1.6, HY0 + 12, 0, 400))
head_f = cad.cut(head_f, frame)
bezel = cad.cut(frame, head_core)
# the neck pivot collar: a brushed turntable plate on the torso top, its
# spigot down in the torso's neck opening, a groove round its rim
plate = zprism(cad.rounded_rect_wire(68, 36, 12, (60, NECK_Y, 0), "Z"), TZ1, TZ1 + 4.0)
spigot = box(31.2, 88.8, NECK_Y - 13.8, SPLIT_Y - 0.3, TZ1 - 3.0, TZ1 + 0.5)   # walls >= 3 mm round the neck
collar = cad.cut(cad.fuse_one(plate, spigot), zprism(neck_o.makeOffset2D(0.4, join=0), TZ1 - 5, TZ1 + 6))
collar = cad.groove_ring(collar, "Z", TZ1 + 2.0, w=0.6, depth=0.5)
# a parting-line reveal round the head, lettering on chest and back
head_f = cad.groove_ring(head_f, "Y", HSPLIT - 2.5, w=0.8, depth=0.6)
torso_f = cad.text(torso_f, "ATECH", (60, y_txt, 86), (0, -1, 0), 7, depth=0.5, mode="deboss")
torso_b = cad.text(torso_b, "ATECH", (60, TY1, 74), (0, 1, 0), 7, depth=0.5, mode="deboss")
# raised rings round the button and the mic (0.6 mm proud)
torso_f = cad.fuse_one(torso_f, *[cad.soften(cad.cut(cyl(r + 1.1, (cx, y + 0.8, cz), (0, -1, 0), 1.4),
                                                     cyl(r, (cx, y + 1.0, cz), (0, -1, 0), 2)), 0.3)
                                  for (cx, cz), y, r in ((bc, y_btn, 8.0), (mc, y_mic, 9.0))])
# antenna; holes the arms, ears and feet are pinned into (soft squares)
head_f = cad.fuse_one(head_f, cad.pipe([(60, -12, HZ1 - 1.5), (60.5, -12, HZ1 + 7), (62, -12, HZ1 + 15)], r=1.6),
                      Part.makeSphere(4.6, V(62, -12, HZ1 + 17)))
EAR_Y, EAR_Z = -12.0, VZ
head_f = cad.cut(head_f, [pin_hole(HX0 - 1, HX0 + WALL + 1, EAR_Y, EAR_Z, 2.65),
                          pin_hole(HX1 + 1, HX1 - WALL - 1, EAR_Y, EAR_Z, 2.65)])
ARM_Y = -10.0
torso_f = cad.cut(torso_f, [pin_hole(TX0 - 1, TX0 + WALL + 1, ARM_Y, 84, 3.15),
                            pin_hole(TX1 + 1, TX1 - WALL - 1, ARM_Y, 84, 3.15)])
for x in (30, 90):
    torso_f = cad.hole(torso_f, (x, -9, TZ0), "+Z", 6.3, through="wall")
# arms, ears and feet: each pinned into its hole (0.15 mm clear)
arms = {}
for nm, x0, d, path in (("Arm_L", TX0, -1, [(-12.5, ARM_Y, 85), (-17, ARM_Y, 97), (-21, ARM_Y, 112)]),
                        ("Arm_R", TX1, 1, [(132.5, ARM_Y, 83), (137, ARM_Y, 71), (139, ARM_Y, 55)])):
    disc = cyl(11, (x0, ARM_Y, 84), (d, 0, 0), 4)
    peg = cyl(3.0, (x0 - 2.5 * d, ARM_Y, 84), (d, 0, 0), 7)
    hand = Part.makeSphere(7.5, V(*path[-1]) + V(d * 1.0, 0, 5 if d < 0 else -5))
    arms[nm] = cad.fuse_one(cad.soften(disc, 1.2), peg, cad.pipe(path, r=5.0), hand)
ears = {}
for nm, x0, d in (("Ear_L", HX0, -1), ("Ear_R", HX1, 1)):
    disc = cad.soften(cyl(12, (x0, EAR_Y, EAR_Z), (d, 0, 0), 5.0), 1.5)
    ears[nm] = cad.fuse_one(disc, cyl(2.5, (x0 - 3 * d, EAR_Y, EAR_Z), (d, 0, 0), 5))
feet = {}
for nm, x in (("Foot_L", 30), ("Foot_R", 90)):
    f = cad.soften(cad.rounded_box(34, 84, TZ0, 12, at=(x - 17, -40, 0)), 2.5)
    feet[nm] = cad.fuse_one(f, cyl(3.0, (x, -9, TZ0 - 1.0), (0, 0, 1), 4.5))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o


for nm, sh in (("Torso_Back", torso_b), ("Torso_Front", torso_f), ("Head_Front", head_f),
               ("Head_Back", head_b), ("Face_Bezel", bezel), ("Neck_Collar", collar)):
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS[nm])
o = part("Face_Plate", face)
o.ViewObject.ShapeColor = cad.color(COLOURS["Face_Plate"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Face_Plate"])
o = part("Button_Cap", cap)
o.ViewObject.ShapeColor = cad.color(COLOURS["Button_Cap"])
for nm, sh in arms.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Arm"])
for nm, sh in ears.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Ear"])
for nm, sh in feet.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Foot"])
for i, sh in enumerate(screws + head_screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
print("TOTAL %.1f s" % (time.time() - T0))
