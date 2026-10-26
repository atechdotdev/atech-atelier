"""Example: "a smart speaker" - a volumetric revolved puck with a light ring.

fork this file for a smart speaker / round table-top gadget (a puck, a
pebble, a tall cylinder); change PARAMETERS and the outlines.
TALL = True gives the tall-cylinder variant (176 mm tall: 1.2 x its width).
ARCHETYPE: speaker

How it is built (R270):
  * STAGE A - hardware, shell, every working-face opening, fasteners:
    the board FLAT at the puck's axis; ONE closed (radius, height) section
    of tangent arcs (a rolled top edge, a barrel side, a tucked step, a dark
    plinth) that already holds the 2 mm walls - revolved, it is hollow (no
    core, no boolean, a fair surface); split into the fixed Base and the
    Shell by a lip; the light ring parts the aluminium Top from the shell;
    every module's opening (speaker grille, mic pin holes, key caps, light
    pipes, USB-C pocket); three M2.5 screws from below into bosses (the
    pilot is the kit's tapped pilot, the shank 0.1 mm undersize).
  * STAGE B - details: fabric grooves, the parting-line reveal, a driver
    chamber with a rubber gasket up to the grille, a mic seal ring, raised
    rings round the keys, lettering, feet in recesses.
DETAILS (visible, 30): 1 barrel side (tangent arcs, no spline wiggle);
2 rolled top edge; 3 floating dark plinth; 4 chamfered step underside;
5 fabric grooves round the band; 6 parting-line reveal over the plinth;
7 frosted light ring (the lens of all five lights); 8 a light pipe per
light; 9 brushed aluminium top as its own part; 10 round speaker grille;
11 driver chamber tube; 12 rubber gasket on the driver; 13 mic pin-hole
cluster; 14 mic seal ring rib; 15-16 volume key caps with flanges;
17 plungers; 18 raised - and + icons; 19 raised rings round the keys;
20 "ATECH" debossed on the top; 21 rib onto the board's spine; 22 three
screw bosses; 23 three countersunk screws from below; 24 lip keying shell
to base; 25 board standoffs; 26 edge fences; 27 USB-C pocket with liner;
28 three rubber feet in recesses; 29 "ATECH" under the base; 30 a cable
notch under the USB-C pocket.
Materials: cream shell, brushed aluminium top, graphite base and keys,
frosted ring, rubber feet and gasket, chrome screws.
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

INTENT = {"board": "flat", "fitted_after": [
    "Shell", "Top", "Light_Ring", "Gasket", "Cap_Minus", "Cap_Plus", "Foot_1", "Foot_2",
    "Foot_3", "Screw_1", "Screw_2", "Screw_3"],
    # each key cap presses its button (a declared cover, see ./check)
    "covers": {"Cap_Minus": "button_p2", "Cap_Plus": "button_p3"}}
REVIEW_CLOSEUPS = ["Light_Ring", "Cap_Plus", "Top"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# R270: every outline below is driven from these numbers - a fork changes
# the silhouette here, never in the stages.
TALL = False               # True: the tall-cylinder variant
WALL = 2.0
FOOT = 1.5                 # rubber feet under the base
SPLIT = 7.0                # base / shell seam, on the plinth
STEP = 10.5                # top of the shell's step floor (the plinth's shoulder)
L = STEP + 0.3 + 2.5       # PCB top: the board's corners (r 67) clear the step by 0.3
R_MID = 72.0               # the barrel's widest radius (board corners need >= 70)
R_PL = 62.0                # plinth radius (the dark recessed foot)
RT, RB = 10.0, 3.0         # rolled top edge radius, step edge radius
TOP = 174.0 if TALL else 62.0      # top (>= L + 24.2); TALL: 1.2 x the width
BARREL_R = 1400.0 if TALL else 320.0   # side bulge radius (bigger = straighter)
RING = (48.5, 58.5)        # light-ring radii (all five lights sit at r 50.6-54.1)
FABRIC = (17.0, TOP - 16.0, 6.0 if TALL else 3.5)  # groove band z0, z1, pitch
REVEAL_Z = STEP + 2.6      # parting-line reveal groove on the barrel's foot
SCREW = "M2.5"
FEET_R = 50.0
COLOURS = {"Base": "graphite", "Shell": "cream", "Top": "brushed_alu",
           "Light_Ring": "frosted", "Cap": "graphite", "Foot": "rubber",
           "Gasket": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
FLAT = Rotation(Vector(1, 0, 0), 90)
board = ap.board_object(doc)
board.Placement = Placement(Vector(0, 0, L), FLAT)     # x 0..60, y -120..0
spk = ap.seat(doc, "speaker", (11, 12))
mic = ap.seat(doc, "microphone", (4, 5))
vol_dn = ap.seat(doc, "button", 2)
vol_up = ap.seat(doc, "button", 3)
usb = ap.seat(doc, "usbc", 7)                          # back, mouth +Y
lights = [ap.seat(doc, "light", n) for n in (1, 6, 8, 9, 14)]
BB = ap.bbox(board)
CX, CY = (BB.XMin + BB.XMax) / 2, (BB.YMin + BB.YMax) / 2   # the puck's axis
tick("hardware")


def centre(m):
    b = ap.bbox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, h, d=(0, 0, 1)):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def annulus(r0, r1, z0, z1, c=None):
    c = c or (CX, CY)
    return cad.cut(cyl(r1, (c[0], c[1], z0), z1 - z0), cyl(r0, (c[0], c[1], z0 - 1), z1 - z0 + 2))


def arc(c, r, a0, a1):
    """('arc', mid, end) of the circle (c, r) from angle a0 to a1 (deg)."""
    am, a1 = math.radians((a0 + a1) / 2), math.radians(a1)
    return ("arc", (c[0] + r * math.cos(am), c[1] + r * math.sin(am)),
            (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1)))


# The section: tangent arcs only (a fair surface). The barrel's centre CB;
# the top roll and the step edge are tangent to it, so the inside (every
# radius - WALL about the same centres) is an exact 2 mm offset.
ZM = (STEP + TOP) / 2
CB = (R_MID - BARREL_R, ZM)
PHI_T = math.degrees(math.asin((TOP - RT - ZM) / (BARREL_R - RT)))
PHI_B = math.degrees(math.asin((STEP - 2 + RB - ZM) / (BARREL_R - RB)))


def on_barrel(rr, deg):
    """The centre of a roll of radius rr tangent inside the barrel at deg."""
    a = math.radians(deg)
    return (CB[0] + (BARREL_R - rr) * math.cos(a), CB[1] + (BARREL_R - rr) * math.sin(a))


CT, CS = on_barrel(RT, PHI_T), on_barrel(RB, PHI_B)    # top roll, step edge centres


def barrel(rad, a0, a1):
    return arc(CB, rad, a0, a1)


def grooved_barrel(grooves):
    """The barrel side from PHI_T down to PHI_B with each groove (z, w,
    depth) notched INTO the section - one revolve gives every fabric
    groove and the reveal, no boolean (R270, MEASURED: groove_ring on the
    revolved barrel made 12767 faces and 100 s)."""
    out, a = [], PHI_T
    for z, w, d in sorted(grooves, reverse=True):
        a_hi = math.degrees(math.asin((z + w / 2 - ZM) / BARREL_R))
        a_lo = math.degrees(math.asin((z - w / 2 - ZM) / BARREL_R))
        out.append(barrel(BARREL_R, a, a_hi))
        for ang in (a_hi, a_lo):
            q = math.radians(ang)
            out.append((CB[0] + (BARREL_R - d) * math.cos(q), CB[1] + (BARREL_R - d) * math.sin(q)))
        q = math.radians(a_lo)
        out.append((CB[0] + BARREL_R * math.cos(q), CB[1] + BARREL_R * math.sin(q)))
        a = a_lo
    return out + [barrel(BARREL_R, a, PHI_B)]


# fabric-like grooves round the band and the parting-line reveal just above
# the plinth seam (a crisp shadow line where the shell meets the base)
GROOVES = [(FABRIC[0] + i * FABRIC[2], 0.8, 0.6)
           for i in range(int((FABRIC[1] - FABRIC[0]) / FABRIC[2] + 1e-6) + 1)]
GROOVES.append((REVEAL_Z, 1.0, 0.7))
section = [
    (0, TOP), (CT[0], TOP), arc(CT, RT, 90, PHI_T),                     # top, rolled edge
    *grooved_barrel(GROOVES), arc(CS, RB, PHI_B, -90),                  # barrel side, step edge
    (R_PL + 1.5, STEP - 2), (R_PL, STEP - 3), (R_PL, FOOT + 2),         # step underside, plinth
    arc((R_PL - 2, FOOT + 2), 2, 0, -90), (0, FOOT),                     # plinth foot edge
    (0, FOOT + WALL), (R_PL - WALL, FOOT + WALL), (R_PL - WALL, STEP),   # inside: floor, plinth
    (CS[0], STEP), arc(CS, RB - WALL, -90, PHI_B),                      # step floor
    barrel(BARREL_R - WALL, PHI_B, PHI_T), arc(CT, RT - WALL, PHI_T, 90),
    (0, TOP - WALL),
]
assert CT[0] > RING[1] + 1.5, "the flat top must carry the light ring"


def r_in(z):
    """The barrel's inside radius at height z (for liners and bosses)."""
    return CB[0] + math.sqrt((BARREL_R - WALL) ** 2 - (z - ZM) ** 2)


body = cad.revolve_profile(section, at=(CX, CY, 0))
tick("body")
base, shell = cad.split(body, "Z", at=SPLIT, lip=1.2)
tick("split")

# the fixed base holds the board: standoffs under it (0.1 mm below), fences
# 0.3 mm off its long edges - all below the modules' slide paths
PCB0 = L - 2.5
holders = [box(x - 3, x + 3, y - 3, y + 3, FOOT + 1.5, PCB0 - 0.1)
           for x in (BB.XMin + 12, BB.XMax - 12) for y in (BB.YMax - 12, BB.YMin + 12)]
holders += [box(x0, x1, y - 4, y + 4, FOOT + 1.5, L - 1.0)
            for x0, x1 in ((BB.XMin - 1.8, BB.XMin - 0.3), (BB.XMax + 0.3, BB.XMax + 1.8))
            for y in (CY + 20, CY - 20)]
base = cad.fuse_one(base, *holders)
# board retention rib: from the top down onto the board's spine (0.2 mm off)
RIB_X = CX - 7.0                                        # on the spine (x 20..40), clear of the chamber
shell = cad.fuse_one(shell, box(RIB_X - 1, RIB_X + 1, CY - 15, CY + 15, L + 4.5 + 0.2, TOP - 1.5))
# fasteners: three M2.5 up through the floor into bosses hanging from the
# top (ribs=0 next to modules). R270: each boss gets a HEAT-SET INSERT
# pocket (1.4 d + 0.1) in a thicker sleeve - a pilot of d (the kit's tapped
# size) gives a thread-forming screw nothing to bite (./check's pilot line)
SCREWS = [(BB.XMin - 14, CY), (BB.XMax + 3.5, CY + 29), (BB.XMax + 3.5, CY - 29)]
INSERT_D = {"M2": 3.2, "M2.5": 3.6, "M3": 4.3}[SCREW]
screws = []
for x, y in SCREWS:
    shell = cad.screw_boss(shell, (x, y, FOOT + 2.1), axis="+Z", size=SCREW, ribs=0)
    shell = cad.fuse_one(shell, cyl(INSERT_D / 2 + 1.2, (x, y, FOOT + 2.1), 10.0))
    shell = cad.cut(shell, cyl(INSERT_D / 2, (x, y, FOOT + 2.0), 9.0))
    base = cad.countersink(base, (x, y, FOOT), "+Z", 2.9, 5.6, 90.0)
    screws.append(cad.screw("csk_phillips", SCREW, 10, at=(x, y, FOOT), axis="+Z"))
tick("base + screws")

# the light ring (frosted - the lens of every light) parts the top disc
# (with the rib and the bosses) from the shell: the disc is the Top part
cutter = annulus(RING[0], RING[1], TOP - 3, TOP + 1)
ring = shell.common(cutter)
pieces = sorted(cad.cut(shell, cutter).Solids, key=lambda q: q.BoundBox.DiagonalLength)
top, shell = pieces[0], pieces[-1]
# a light pipe from the ring down to 0.5 mm above each light module
pipes = [cyl(6.0, (x, y, L + 9.54 + 0.5), (TOP - 2.05) - (L + 9.54 + 0.5)) for x, y in map(centre, lights)]
pipes += [cyl(6.0, (x, y, TOP - 2.1), 0.6).common(annulus(RING[0] + 0.1, RING[1] - 0.1, TOP - 3, TOP))
          for x, y in map(centre, lights)]
ring = cad.fuse_one(ring, *pipes)
# speaker: a round grille over the measured surround
sx, sy = centre(spk)
top = cad.speaker_grille(top, (sx, sy, TOP), (0, 0, 1), 34, ring_pitch=2.6, hole=1.6)
# microphone: a pin-hole cluster over the mic (15 across: >= 3 % open)
mx, my = centre(mic)
mtop = ap.bbox(mic).ZMax
top = cad.speaker_grille(top, (mx, my, TOP), (0, 0, 1), 15, ring_pitch=2.5, hole=1.6)
# volume keys: caps through the top, flange 0.1 mm under it, a plunger to
# 0.16 mm above the module's own cap
caps = {}
for nm, m in (("Cap_Minus", vol_dn), ("Cap_Plus", vol_up)):
    x, y = centre(m)
    mz = ap.bbox(m).ZMax
    base_z = TOP - WALL - 0.9
    cap = cad.button_cap(11.5, (TOP + 1.4) - base_z, dome=0.6, flange=1.5, at=(x, y, base_z), axis="+Z")
    top = cad.opening_for(top, cap, clearance=0.25, chamfer=0.4, axis="+Z")
    caps[nm] = cad.fuse_one(cap, cyl(3.0, (x, y, mz + 0.16), base_z - (mz + 0.16) + 0.5))
# USB-C at the back: a pocket brings the wall to 0.25 mm off the mouth
ub = ap.bbox(usb)
uz = L + 5.9
pocket = cad.rounded_box(18, 40, 10, 3, at=(CX - 9, ub.YMax + 1.3, uz - 5), edges="y")
liner = cad.cut(cad.rounded_box(22, R_MID, 14, 4, at=(CX - 11, ub.YMax + 0.25, uz - 7), edges="y")
                .common(cyl(r_in(uz) + 1.0, (CX, CY, 0), TOP)), pocket)
shell = cad.fuse_one(cad.cut(shell, pocket), liner)
shell = cad.socket_opening(shell, usb, margin=1.5)
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# (the fabric grooves and the parting-line reveal are in the section, A)
# the driver chamber: a tube from the top down round the speaker surround,
# and a rubber gasket pressed into its foot 0.2 mm over the driver
stop = ap.bbox(spk).ZMax
CH_R0, CH_R1 = 17.6, 19.6
tube = annulus(CH_R0, CH_R1, stop + 0.2, TOP - 1.0, (sx, sy))
gasket = tube.common(annulus(CH_R0 + 0.5, CH_R1 - 0.5, stop + 0.1, stop + 1.6, (sx, sy)))
tube = cad.cut(tube, [annulus(CH_R0 + 0.5, CH_R1 - 0.5, stop + 0.1, stop + 1.6, (sx, sy)),
                      annulus(RING[0] - 0.4, RING[1] + 0.4, TOP - 3.5, TOP + 1)])   # clear of the ring
top = cad.fuse_one(top, tube)
# mic: a ring rib from the top sealing the pin holes onto the mic
top = cad.fuse_one(top, annulus(8.4, 9.6, mtop + 0.3, TOP - 1.5, (mx, my)))
# raised rings round the keys (0.5 proud), lettering, - and +
for nm, m in (("Cap_Minus", vol_dn), ("Cap_Plus", vol_up)):
    x, y = centre(m)
    top = cad.fuse_one(top, annulus(6.6, 8.0, TOP - 0.5, TOP + 0.5, (x, y)))
caps["Cap_Minus"] = cad.text(caps["Cap_Minus"], "-", (centre(vol_dn)[0], centre(vol_dn)[1], TOP + 1.4),
                             (0, 0, 1), 8.5, depth=0.4, mode="emboss", up=(0, 1, 0))
caps["Cap_Plus"] = cad.text(caps["Cap_Plus"], "+", (centre(vol_up)[0], centre(vol_up)[1], TOP + 1.4),
                            (0, 0, 1), 8.5, depth=0.4, mode="emboss", up=(0, 1, 0))
top = cad.text(top, "ATECH", (CX, CY - 40, TOP), (0, 0, 1), 6, depth=0.5, mode="deboss", up=(0, 1, 0))
# underside: lettering, a cable notch from the USB-C pocket, feet recesses
base = cad.text(base, "ATECH", (CX, CY - 20, FOOT), (0, 0, -1), 7, depth=0.4, mode="deboss", up=(0, -1, 0))
feet = []
for ang in (90, 210, 330):
    x, y = CX + FEET_R * math.cos(math.radians(ang)), CY + FEET_R * math.sin(math.radians(ang))
    base = cad.cut(base, cyl(4.6, (x, y, FOOT - 1), 2.2))
    feet.append(cad.foot(9, FOOT + 1.2, style="dome", at=(x, y, FOOT + 1.2)))
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o


o = part("Base", base)
o.ViewObject.ShapeColor = cad.color(COLOURS["Base"])
o = part("Shell", shell)
o.ViewObject.ShapeColor = cad.color(COLOURS["Shell"])
o = part("Top", top)
o.ViewObject.ShapeColor = cad.color(COLOURS["Top"])
o = part("Light_Ring", ring)
o.ViewObject.ShapeColor = cad.color(COLOURS["Light_Ring"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Light_Ring"])
o = part("Gasket", gasket)
o.ViewObject.ShapeColor = cad.color(COLOURS["Gasket"])
for nm, sh in caps.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Cap"])
for i, sh in enumerate(feet):
    o = part("Foot_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Foot"])
for i, sh in enumerate(screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
print("TOTAL %.1f s" % (time.time() - T0))
