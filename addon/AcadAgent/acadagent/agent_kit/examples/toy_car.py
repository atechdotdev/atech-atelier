"""Example: "a toy car" - a low, sporty toy coupe around real Atech hardware.

fork this file for a toy car / vehicle (a truck, a rover, a tank hull, a
racer - anything on wheels); change PARAMETERS and the outlines.
ARCHETYPE: vehicle

How it is built (R270, resculpted R610):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT under the floor, nose at the port-8 end (-Y), its height set
    by the wheel radius (shaft centre = PCB top + 10.14); a dc_motor per
    wheel, each driving it directly through a soft-square hole: ports 1
    and 9 seated (rear), ports 5 and 13 CABLED (front - R700: the rear pair
    moved up the wheelbase, each in two U-saddles on the chassis floor); the
    headlights and the ToF CABLED to the nose (ap.cable), each held by two
    ribs down from the hood; every ribbon on its own lane (lane(): the
    motors' over the board and the front motors, the headlights' under
    them, the ToF's over the top); USB-C on port 7 in a pocket in the
    rounded tail.
    R610: the body is ONE sculpted surface (cad.profile_body with SPLINE
    side and plan outlines): a wedge side - a low rounded nose rising
    along the hood to a flat shoulder line, a rear deck falling to a
    rounded tail - and a plan
    that swells over each axle and pinches at the doors, so the wheel
    arches are cut INTO the body (wells, each with its own 2 mm liner),
    not bolted on. It is hollowed with its own inset core and split (lip)
    into the fixed Chassis (a cradle holds the board; it carries the chin,
    the sills and the bumpers) and the Body_Shell. The cabin is a LOFT
    (cad.loft, ruled) from the shoulder to a smaller roof: a raked
    windscreen, a fastback, a greenhouse narrower than the body, keyed into
    the tub by a lip and pinned by four pegs into bored bosses (a lip
    alone lifts off), with a rib down onto the board's spine; headlight
    lenses in chrome bezels, a grille insert with a clear ToF lens; four
    M2 screws from below into insert bosses - done BEFORE the details;
    one wheel build copied four times.
  * STAGE B - details: windows (smoked inserts, cut square to their
    sloped faces), tail lights, door seams, the hood panel line,
    lettering, wrap-around bumpers, the parting-line reveal (the mirrors
    and door handles ride in STAGE A's batched booleans).
  R610 TRAPS on a spline shell (MEASURED): every boolean costs 1-7 s, so
  cuts and fuses are batched (one call, many tools) and screw_through runs
  on a local piece; Shape.Volume differences are tens of mm3 of noise, so
  cuts are proven by probe points; a groove made of moved copies of the
  surface came back empty or as a crumb - grooves are the band less the
  body inset 0.5 mm (skin05).
DETAILS (visible, 34): 1 one-piece spline body, 4.5 mm edges; 2 wedge side
profile (low nose, rising hood); 3 shoulder line (the deck the cabin sits
on); 4 sloping rear deck; 5-8 four wheel arches in the body, lined;
9 Coke-bottle plan (haunches over the axles, pinched doors); 10 two-tone
lofted cabin keyed by a lip; 11 raked windscreen; 12 fastback rear
window; 13-14 side windows (smoked inserts); 15 A/C pillars; 16 four
soft-square shaft holes, a motor in every wheel; 17-18 headlight lenses with retaining flanges; 19 chrome
bezels in counterbores; 20 recessed grille insert; 21 five grille slots;
22 clear ToF lens in the middle slot; 23 red tail lights; 24 USB-C pocket
with liner; 25 door seams both sides; 26 door handle recesses; 27 hood
panel line; 28 "ATECH" on the tail; 29 side mirrors on stalks;
30 wrap-around bumpers on brackets; 31 board cradle and front motor
saddles; 32 four screws into
insert bosses; 33 parting-line reveal round the tub; 34 block-tread tyres
with five-window rims and centre caps.
Materials: yellow body, white cabin, graphite chassis, black grille,
smoked glass, clear lenses, chrome bezels and screws, red tail lights,
rubber tyres, aluminium rims.
MEASURED (R610, 2026-10-26): see test_kit_examples_r270 (TIMINGS line).
R700 (2026-10-27): four motors - ./check 142 s here (110 s with two).
"""
import time
import Part
import atech_ports as ap
import atech_cad as cad
from FreeCAD import Vector, Placement, Rotation
V = Vector
T0 = time.time()

# intent.json for this example (./check reads intent.json, never this):
# every part fitted after the modules - only the chassis is fixed.
INTENT = {"board": "flat", "fitted_after": [
    "Body_Shell", "Hardtop", "Grille", "ToF_Lens", "Windscreen", "Rear_Window", "Side_Window_L",
    "Side_Window_R", "Headlight_L", "Headlight_R", "Bezel_L", "Bezel_R", "Tail_Light_L",
    "Tail_Light_R", "Screw_1", "Screw_2", "Screw_3", "Screw_4", "Tyre_RL", "Tyre_FL",
    "Tyre_RR", "Tyre_FR", "Rim_RL", "Rim_FL", "Rim_RR", "Rim_FR"]}
REVIEW_CLOSEUPS = ["Grille", "Rim_FL"]          # each close-up costs ./check 2-5 s


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# R500/R610: NOSE stretches the hood and the wheelbase (the front axle, the
# nose hardware and everything on the nose move forward by it). The
# haunches reach the tyres' outer faces (137 mm wide), so 34 keeps the car
# over ./check's 1.5 x length / width (a shorter one reads as a box on wheels)
NOSE = 34.0
WALL, R_OUT = 2.0, 4.5            # body wall, body edge fillet (5: its inset core will not fillet)
# R270: the body frame has x = length (nose at +x), y = width, z = height;
# W() turns it into the world (nose at -Y, centred on the board's x = 30).
R = 24.0                          # wheel radius (sets the board height)
WHEEL_W, WHEELBASE = 14.0, 100.0 + NOSE
REAR_X, FRONT_X = 10.0, 10.0 + WHEELBASE          # the axles in the body frame
TOP = 57.0                        # the shoulder line: the deck the cabin sits on
NF = 144.0 + NOSE                 # the nose face (body x)
# R610: the SIDE outline (x, z) - a wedge: the flat chin, a vertical nose
# face for the lamps, the hood rising on a spline to the shoulder, the flat
# deck under the cabin, a rear deck falling to a rounded tail (the USB-C
# and the tail lights sit in it)
SIDE = [("line", (-15.5, 7.5)), ("line", (NF - 5, 7.5)), ("line", (NF, 12.5)), ("line", (NF, 41.0)),
        (NF - 2.2, 46.5), (NF - 12, 51.5), (NF - 30, 55.2), (NF - 53, 56.6), (102, TOP),
        ("line", (-1, TOP)), (-8.0, 56.3), (-15.0, 53.8), (-19.6, 47.5), (-20.6, 34.0), (-19.4, 17.0)]
# R610: the PLAN outline (x, y), one side; mirrored below. Haunches over the
# axles (|y| 68.6, 1 mm past the tyres), pinched doors, a rounded tail and
# a flat nose (the lamps' face) with rounded corners.
PLAN_HALF = [(-25.0, 0.0), (-24.4, 24.0), (-21.0, 39.0), (-15.5, 50.0), (-7.0, 58.5), (2.0, 65.0),
             (REAR_X, 68.4), (22.0, 68.0), (35.0, 64.5), (50.0, 58.5), (70.0, 56.0), (92.0, 58.0),
             (110.0, 64.0), (FRONT_X - 12, 68.2), (FRONT_X, 68.6), (FRONT_X + 13, 66.2),
             (NF - 12, 61.0), (NF - 4, 53.5), ("corner", (NF + 2, 45.5))]
PLAN = PLAN_HALF + [("line", (NF + 2, -45.5))] + [(x, -y) for x, y in reversed(PLAN_HALF[1:-1])]
WELL_R, LINER = R + 4.0, 2.0      # arch radius (2.6 mm round the 25.4 mm tread); liner wall
WELL_Y = 52.7                     # the wells' inner face (|y|): the tyres run 0.8 mm outboard
CORE_Y = WELL_Y - LINER           # the hollow's side inside the arches
SPLIT_Z = 11.5                    # chassis / shell seam (lip top 13.0, under the slide corridors)
# R610: the cabin - a ruled loft from the shoulder (FOOT) to a smaller,
# lower roof (ROOF): raked windscreen, fastback, tumblehome
CABIN_H = 19.0
HT_Z1 = TOP + CABIN_H             # the roof
Z0 = TOP + 1.5                    # a 1.5 mm upright skirt, then the slopes (a 25 deg face
                                  # straight off the deck leaves a knife edge at its foot)
FOOT = (0.0, 95.0, 46.0, 14.0)    # (x rear, x front, half width, corner r) at z = TOP
ROOF = (22.0, 66.0, 35.0, 12.0)   # the same at z = HT_Z1
# glass openings (the inserts fill them), cut square to each sloped
# face: the world x (screens) or y (sides) span at the foot and the top
GLASS_Z = (60.5, 72.5)
WINDSCREEN = ((1, 59), (7, 53))
REAR_WINDOW = ((2, 58), (8, 52))
SIDE_WINDOWS = ((-18, -76), (-31, -58))
GRILLE = [(13, 13), (47, 13), (47, 40), (13, 40)]                  # (x, z) on the nose
SLOTS = ((17.5, 4.4), (23.75, 4.4), (30, 6.6), (36.25, 4.4), (42.5, 4.4))   # (x, w); the middle one: the ToF
HL = 31.0                         # headlights at x = 30 -+ HL (the bezels clear the grille)
LAMP_Z, EYE_Z = 14.0, 14.0        # R610: lamps / ToF centres over the PCB top (low nose);
                                  # R700: the ToF's ribbon leaves its top - 14 keeps it under the hood
REVEAL_Z = 13.8                   # parting-line reveal round the tub
SCREWS = [(-14, -95), (74, -95), (-4.5, 8.5), (64.5, 8.5)]
COLOURS = {"Chassis": "graphite", "Body_Shell": "toy_yellow", "Hardtop": "matte_white",
           "Grille": "matte_black", "Glass": "smoked", "Lens": "glass", "Bezel": "chrome",
           "Tail": "led_red", "Screw": "chrome", "Tyre": "rubber", "Rim": "brushed_alu"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
FLAT = Rotation(Vector(1, 0, 0), 90)
board = ap.board_object(doc)
L = R - 10.14                     # PCB top: shaft centre 10.14 above it = R
board.Placement = Placement(Vector(0, 0, L), FLAT)     # nose -Y (port 8 end)
mot_l = ap.seat(doc, "dc_motor", 1)                    # rear wheels
mot_r = ap.seat(doc, "dc_motor", 9)
usb = ap.seat(doc, "usbc", 7)                          # rear, mouth +Y
mb = ap.bbox(mot_l)
SHAFT_Y = (mb.YMin + mb.YMax) / 2                      # rear axle, measured
FRONT_Y = SHAFT_Y - WHEELBASE
EYE_Y, LAMP_Y = -131.4 - NOSE, -132.0 - NOSE           # the nose modules' centres (y)


def lane(*corners, step=1.5):
    """R700: the via list for ap.cable - the polyline through corners
    (x, y, z, r), its two ends the ribbon's lead points, each corner
    rounded at r, sampled every `step` mm and 0.5 mm from each end.
    MEASURED: a few far-apart vias let the ribbon's spline (OCCT scales
    its end tangents) loop 15-30 mm past them; points this dense keep it
    within 0.1 mm of the path."""
    P = [V(*c[:3]) for c in corners]
    rr = [0.0] + [float(c[3]) for c in corners[1:-1]] + [0.0]
    for i in range(len(P) - 1):                       # two corners share a leg
        ln = (P[i + 1] - P[i]).Length
        if rr[i] + rr[i + 1] > 0.95 * ln:
            k = 0.95 * ln / (rr[i] + rr[i + 1])
            rr[i], rr[i + 1] = rr[i] * k, rr[i + 1] * k
    pts = [P[0]]
    for i in range(1, len(P) - 1):
        a, p, b = P[i - 1], P[i], P[i + 1]
        p0, p1 = p + (a - p).normalize() * rr[i], p + (b - p).normalize() * rr[i]
        pts += [p0 * (1 - t) ** 2 + p * (2 * t * (1 - t)) + p1 * t * t for t in [k / 8.0 for k in range(9)]]
    pts.append(P[-1])
    clean = [pts[0]]
    for q in pts[1:]:
        if (q - clean[-1]).Length > 1e-6:
            clean.append(q)
    D = Part.makePolygon(clean).discretize(Distance=0.5)
    k = max(1, int(round(step / 0.5)))
    return [tuple(q) for q in [D[1]] + D[k:-k:k] + [D[-2]]]


def mx(c):
    """A lane corner mirrored to the right side (the board's middle, x = 30)."""
    return (60.0 - c[0],) + tuple(c[1:])


# R700: a dc_motor per wheel. The front pair is the rear pair moved up the
# wheelbase (shaft on the front axle, its end out into the wheel), CABLED
# from ports 5 and 13 (the SDK reserves 8 and 12), each in a chassis
# saddle. The ribbons keep to their own layers (MEASURED, each lane
# probed against the others): the motors' over the board and the front
# motors' tops, down into the gap between the motors to the sockets; the
# headlights' under the front motors (a tunnel between the saddles); the
# ToF's up its riser between the board and the motors, over the top.
# PLUG: measured - where each ribbon's straight lead out of its port ends
# (the board does not move with the knobs); PZ: the plugs' and the motor
# sockets' pin height
PLUG = {5: (-3.28, -90.1), 6: (-3.23, -110.0), 8: (30.0, -123.23), 13: (63.23, -90.0), 14: (63.23, -110.0)}
PZ = L + 1.27
OVER = mb.ZMax + 4.5              # the motor ribbons over the front motors' tops
TUN = mb.ZMin - 2.2               # the headlight ribbons under them
YB, YF = mb.YMax - WHEELBASE, mb.YMin - WHEELBASE      # the front motors' back / front faces


def moved(o, dy):
    p = Placement(o.Placement)
    p.Base = p.Base + V(0, dy, 0)
    return p


m_lead = (mb.XMax + 3.14, FRONT_Y, PZ)                 # measured: each socket's lead, 3.14 out
m_mid = [(-7.5, PLUG[5][1], PZ, 3), (-7.5, PLUG[5][1], PZ + 14, 3), (8.5, PLUG[5][1], PZ + 14, 10),
         (8.5, FRONT_Y, OVER, 10), (m_lead[0] + 5.2, FRONT_Y, OVER, 3), (m_lead[0] + 5.2, FRONT_Y, PZ, 3)]
mot_fl, mfl_rib = ap.cable(doc, "dc_motor", 5, moved(mot_l, -WHEELBASE),
                           via=lane(PLUG[5] + (PZ,), *m_mid, m_lead))
mot_fr, mfr_rib = ap.cable(doc, "dc_motor", 13, moved(mot_r, -WHEELBASE),
                           via=lane(PLUG[13] + (PZ,), *[mx(c) for c in m_mid], mx(m_lead)))
# R700: the ToF looks out of the grille 6 mm lower (EYE_Z 14), its ribbon
# out of its top (+Z) - under it the front motors' ribbons come together
eye_lead = (30.0, EYE_Y + 3.5, L + EYE_Z + 12.89)      # measured, 3.14 over its socket
RY = (PLUG[8][1] + YB) / 2 - 0.5                       # the riser, between the board and the motors
eye, eye_rib = ap.cable(doc, "distance_sensor", 8, ap.module_placement(
    "distance_sensor", (30, EYE_Y, L + EYE_Z), face="-Y", cable="+Z"),
    via=lane(PLUG[8] + (PZ,), (30, RY, PZ, 4), (30, RY, OVER + 7, 5), (30, eye_lead[1], OVER + 7, 3), eye_lead))
l_lead = (30 - HL, LAMP_Y + 3.5, L + LAMP_Z - 12.89)  # measured, 3.14 under its socket
# up and back over its plug, round onto the lamp's line, down under the
# motor: every leg in one plane, so the ribbon reaches the tunnel flat
# (MEASURED: a lane drifting 7 mm sideways on its way down tilted it 12 deg
# there, into the motor)
l_mid = [(-14, PLUG[6][1], PZ, 3), (-14, PLUG[6][1], PZ + 7, 3), (l_lead[0], PLUG[6][1], PZ + 7, 9),
         (l_lead[0], -122, PZ + 7, 6), (l_lead[0], YB + 1.25, TUN, 6), (l_lead[0], l_lead[1], TUN, 3)]
head_l, hl_rib = ap.cable(doc, "light", 6, ap.module_placement(
    "light", (30 - HL, LAMP_Y, L + LAMP_Z), face="-Y", cable="-Z"), via=lane(PLUG[6] + (PZ,), *l_mid, l_lead))
head_r, hr_rib = ap.cable(doc, "light", 14, ap.module_placement(
    "light", (30 + HL, LAMP_Y, L + LAMP_Z), face="-Y", cable="-Z"),
    via=lane(PLUG[14] + (PZ,), *[mx(c) for c in l_mid], mx(l_lead)))
LZ = ap.bbox(head_l).ZMin + ap.bbox(head_l).ZLength / 2
tick("hardware")


def W(s):
    """Body frame (x = length, nose at +x) -> world (nose at -Y, centred on x = 30)."""
    s = s.copy()
    s.rotate(V(0, 0, 0), V(0, 0, 1), -90)
    s.translate(V(30, 0, 0))
    return s


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, d, h):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def soft_wire(pts3, r):
    """A closed wire round a polygon (3D points in one plane) with every
    corner softened (radius ~r, three facets) - straight lines only.
    R270: the spline version (cad.spline_wire through corner knots) gave
    prisms that OCCT booleans read inside out after a kit change (a
    pocket cut from a liner removed the whole liner, MEASURED) - lines and
    arcs have no such failure."""
    import math
    P = [V(*q) for q in pts3]
    n = len(P)
    tp = []
    for i in range(n):
        p, a, b = P[i], P[i - 1], P[(i + 1) % n]
        ua, ub = (a - p).normalize(), (b - p).normalize()
        half = 0.5 * math.acos(max(-1.0, min(1.0, ua.dot(ub))))
        t = r / math.tan(half)
        bis = (ua + ub).normalize()
        c = p + bis * (r / math.sin(half))
        tp.append((p + ua * t, c - bis * r, p + ub * t))
    # each round corner as 3 straight facets: no cylindrical face, so a
    # window corner never reads to ./check as an open clip channel
    pts = []
    for i in range(n):
        a0, mid, a1 = tp[i]
        pts += [a0, (a0 + mid) * 0.5 + (mid - (a0 + a1) * 0.5) * 0.4, (mid + a1) * 0.5
                + (mid - (a0 + a1) * 0.5) * 0.4, a1]
    return Part.makePolygon(pts + [pts[0]])


def soft_prism(w, vec):
    s = Part.Face(w).extrude(vec)
    if s.Volume < 0:
        s.reverse()
    return s


def prism_y(pts_xz, r, y0, y1):
    """A soft-cornered outline in (x, z) extruded along Y from y0 to y1."""
    return soft_prism(soft_wire([(x, y0, z) for x, z in pts_xz], r), V(0, y1 - y0, 0))


def prism_x(pts_yz, r, x0, x1):
    return soft_prism(soft_wire([(x0, y, z) for y, z in pts_yz], r), V(x1 - x0, 0, 0))


def insert(shell, cutter):
    """(shell with the opening, the piece it removed): a pane or a grille
    that fills its opening exactly - they share faces, no overlap. Exact
    booleans first, then fuzzy (0.01 mm) as the fallback (MEASURED R230: 0 mm3
    from the exact one for a spline-cornered window through two walls).
    R610: proven by points (each piece's middle is air in the rest), not by
    the volume removed - on the 1.2 l spline shell a volume difference is
    noise of tens of mm3 (MEASURED)."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1:
        piece, rest = shell.common(cutter, 0.01), shell.cut(cutter, 0.01)
    ok = piece.Volume >= 1 and rest.isValid() and len(rest.Solids) == len(shell.Solids)
    for sol in piece.Solids if ok else ():
        c = sol.CenterOfMass
        if sol.isInside(c, 1e-4, False) and rest.isInside(c, 1e-4, True):
            ok = False
    if not ok:
        raise cad.CadError("insert: the cutter does not cleanly cross the wall (piece %.1f mm3)"
                           % piece.Volume)
    return rest, piece


def ray(shape, p0, p1):
    """R610: where the segment p0 -> p1 crosses the shape's surface
    (points) - the curved body has no number to read a wall off."""
    return [v.Point for v in shape.section(Part.makeLine(V(*p0), V(*p1))).Vertexes]


def outer_y(shape, x, z, sign):
    """The half width of a body-frame shape at (x, z), on side sign."""
    return max(abs(p.y) for p in ray(shape, (x, 0, z), (x, sign * 120, z)))


def under_z(shape, x, y):
    """The lowest point of the shape's top over (x, y) (body frame): for
    the core, the inner face of the hood or the deck."""
    return max(p.z for p in ray(shape, (x, y, 0), (x, y, 120)))


def to_body(xw, yw):
    return -yw, xw - 30.0


# ------------------------------------------------------------ body
# R610: ONE sculpted surface: the spline side x the spline plan, filleted.
# Its core is the exact inset (2 mm walls) less a keep-out round each
# arch, so every well keeps a 2 mm liner (a cylinder and its inner end
# wall) and the hollow haunches stay closed.
# R610 (MEASURED): the filleted spline body fails OCCT's BOP check
# (InvalidCurveOnSurface on a side face) and every later boolean on it was
# a coin toss (a groove "left the surface untouched", a fuse came back
# INVALID); a 0.01 mm tolerance on its edges passes the check
body_l = cad.profile_body(SIDE, PLAN, fillet=R_OUT)
body_l.fixTolerance(0.01)
core_l = cad.profile_body(SIDE, PLAN, fillet=R_OUT, inset=WALL)     # (fixTolerance breaks this one)
skin05 = W(cad.profile_body(SIDE, PLAN, fillet=R_OUT, inset=0.5))   # 0.5 mm under the skin (its edges
                                                                     # stay sharp: use it off the edges)
keep = [cyl(WELL_R + LINER, (xa, sg * CORE_Y, R), (0, sg, 0), 40) for xa in (REAR_X, FRONT_X) for sg in (1, -1)]
core_l = cad.cut(core_l, keep)
tub = W(cad.cut(body_l, core_l))
chassis, tub = cad.split(tub, "Z", at=SPLIT_Z, lip=1.5)
# the arches: through the haunches only, down to the floor
wells = [W(cyl(WELL_R, (xa, sg * WELL_Y, R), (0, sg, 0), 40)) for xa in (REAR_X, FRONT_X) for sg in (1, -1)]
chassis = cad.cut(chassis, wells)
tick("body + split")

# ------------------------------------------------------------ cabin
# R610: a ruled loft from the foot (on the shoulder) to the roof; its
# core is the same loft with every face moved WALL in along its own
# normal (a sloped face needs WALL / sin(slope) sideways), the floor open


def rr(x0, x1, hw, r, z):
    return cad.rounded_rect_wire(x1 - x0, 2 * hw, r, ((x0 + x1) / 2, 0, z), "Z")


def cabin_at(z, t):
    """(x rear, x front, half width, r) of the cabin section at height z,
    every face t in (normal to it); under Z0 the upright skirt."""
    import math
    k = max(0.0, z - Z0) / (HT_Z1 - Z0)
    lerp = [a + (b - a) * k for a, b in zip(FOOT, ROOF)]
    sl = [math.atan2(HT_Z1 - Z0, abs(b - a)) for a, b in zip(FOOT[:3], ROOF[:3])]
    return (lerp[0] + t / math.sin(sl[0]), lerp[1] - t / math.sin(sl[1]),
            lerp[2] - t / math.sin(sl[2]), max(1.0, lerp[3] - t))


ht = cad.loft([rr(*FOOT, TOP), rr(*FOOT, Z0), rr(*ROOF, HT_Z1)], ruled=True)
roof_edges = [e for e in ht.Edges if abs(e.BoundBox.ZMin - HT_Z1) < 1e-3 and e.BoundBox.ZLength < 1e-3]
ht = cad.fillet_safe(ht, 5.0, edges=roof_edges)
z_low = TOP - 3
ht_core = cad.loft([rr(*cabin_at(Z0, WALL), z_low), rr(*cabin_at(Z0, WALL), Z0),
                    rr(*cabin_at(HT_Z1 - WALL, WALL), HT_Z1 - WALL)], ruled=True)
ht = cad.cut(ht, ht_core)
foot = Part.Face(rr(*FOOT, 0.0))


def foot_prism(d, z0, z1):
    f = foot if d == 0 else Part.Face(foot.makeOffset2D(-d, join=0).Wires[0])
    f = f.copy()
    f.translate(V(0, 0, z0))
    return f.extrude(V(0, 0, z1 - z0))


lip = cad.cut(foot_prism(1.0, TOP - 3.5, TOP + 0.5), foot_prism(WALL, TOP - 4, TOP + 1))
ht = W(cad.fuse_one(ht, lip))
# R500: the hardtop is PINNED to the tub, not only keyed: four pegs hang
# from its lip into blind bores (0.1 mm clear) in bosses on the tub's side
# walls, the boss tops 0.1 mm under the lip (a lip only locates it).
# R610: over an arch a boss meets the arch's liner; between the arches it
# reaches out 1 mm into the curved side wall (measured)
PEG_R, PEG_X, PEG_YS = 1.5, (-14.5, 74.5), (-25.0, -65.0)
LIP_Z0 = TOP - 3.5
ht = cad.fuse_one(ht, *[cyl(PEG_R, (x, y, LIP_Z0 - 4.0), (0, 0, 1), 4.6)
                         for x in PEG_X for y in PEG_YS])
peg_bosses = []
for y in PEG_YS:
    xb = -y
    for sg in (-1, 1):
        reach = CORE_Y + 0.5 if xb < REAR_X + WELL_R + LINER else outer_y(core_l, xb, LIP_Z0 - 4, sg) + 1.0
        xa, xi = 30 + sg * reach, 30 + sg * 18.0
        peg_bosses.append(box(min(xa, xi), max(xa, xi), y - 3.5, y + 3.5, LIP_Z0 - 9.0, LIP_Z0 - 0.1))
peg_bores = [cyl(PEG_R + 0.1, (x, y, LIP_Z0 - 5.0), (0, 0, 1), 5.0) for x in PEG_X for y in PEG_YS]
# board retention: a rib from the roof onto the board's spine (0.2 mm above it)
SPINE = L + 4.5
ht = cad.fuse_one(ht, box(29, 31, -58, -44, SPINE + 0.2, HT_Z1 - 1.0))   # behind the windscreen cutter
tick("hardtop")

# ------------------------------------------------------------ motors and axles
# a hole for each motor shaft, rear and front (soft squares, not round
# holes: coaxial round holes in both walls would read as one hole drilled
# through two walls)


def shaft_hole(a, x0, x1, y=SHAFT_Y, z=R):
    return prism_x([(y - a, z - a), (y + a, z - a), (y + a, z + a), (y - a, z + a)], 0.9 * a, x0, x1)


# R610: every cut and every fuse on the sculpted shell is BATCHED - one
# boolean with many tools (a spline shell costs 1-7 s per boolean)
tub = cad.cut(tub, wells + [W(foot_prism(0.85, TOP - 3, TOP + 1))]
              + [shaft_hole(2.7, x0, x1, y=y) for y in (SHAFT_Y, FRONT_Y) for x0, x1 in ((-19.0, -25.0), (79.0, 85.0))])
# the hood panel line (a STAGE B detail cut here: with the holders fused
# under the hood its band's common with the shell came back EMPTY, MEASURED)
tub = cad.groove_outline(tub, soft_wire([(-4, -104, 80), (64, -104, 80), (64, -NF + 10, 80), (-4, -NF + 10, 80)], 5),
                         view="+Z", w=0.6, depth=0.5, both_sides=False)
adds = []
for xs, d in ((-21.7, -1), (81.7, 1)):
    for y in (SHAFT_Y, FRONT_Y):                                             # hub spacers
        adds.append(cad.cut(cyl(4.2, (xs, y, R), (d, 0, 0), 1.5), shaft_hole(2.75, xs - d, xs + 4 * d, y=y)))
tick("arches + axles")

# ------------------------------------------------------------ chassis + fasteners
# board cradle: a ledge under the board's edge (0.1 mm below it, 0.3 mm
# round it) with a rim, notched where the nose sensor's ribbon passes
bb = ap.bbox(board)
PCB0 = L - 2.5
cradle = cad.cut(box(bb.XMin - 2.3, bb.XMax + 2.3, bb.YMin - 2.3, bb.YMax + 2.3, 9.3, PCB0 + 1.4),
                 [box(bb.XMin - 0.3, bb.XMax + 0.3, bb.YMin - 0.3, bb.YMax + 0.3, PCB0 - 0.1, 20),
                  box(bb.XMin + 6, bb.XMax - 6, bb.YMin + 6, bb.YMax - 6, 9, 20),
                  box(18, 42, bb.YMin - 5, bb.YMin + 2, PCB0 - 0.1, 20)])
# screw pads high in the tail corners, clear of the hardtop's lip, 1 mm
# into the tail wall (measured)
pads = [box(x0, x0 + 5, 6.0, 30.0, 40, 51).common(skin05) for x0 in (-7, 62)]
tub = cad.fuse_one(tub, *pads)                  # before the screws: the rear bosses reach them
# four M2 screws up through the chassis floor into bosses in the tub,
# BEFORE the openings and details; each
# boss gets a heat-set insert pocket (1.4 d + 0.1) in a sleeve - the kit's
# pilot (= d) gives a thread-forming screw nothing to bite (R270).
# R610: screw_through runs on the shell's piece round each screw (a local
# box) - on the whole spline shell it cost 6-7 s a screw - and the bosses
# it grows go into the batched fuse below
screws, bosses, csks = [], [], []
for x, y in SCREWS:
    for h in (9.0, 10.3, 7.7, 11.6):            # a box face grazing a wall gives an invalid piece
        lb = box(x - h, x + h, y - h, y + h, 0, 80)
        c0, t0 = chassis.common(lb), tub.common(lb)
        if c0.isValid() and t0.isValid():
            break
    c1, t1 = cad.screw_through(c0, t0, (x, y, 7.5), size="M2")
    bosses.append(t1.cut(t0))
    csks.append(c0.cut(c1))
    screws.append(cad.screw("csk_phillips", "M2", 10, at=(x, y, 7.5), axis="+Z"))
# R700: the front motors' saddles - two U-brackets under each, either side
# of the headlight ribbon's tunnel: a pad 0.1 mm under the motor, ribs
# 0.3 mm off its back and front faces, standing 0.5 mm into the floor
saddles = []
for xa, xb in ((-19.0, -10.0), (12.5, mb.XMax - 0.5)):
    for x0, x1 in ((xa, xb), (60.0 - xb, 60.0 - xa)):
        saddles.append(cad.cut(box(x0, x1, YF - 1.9, YB + 1.9, 7.5 + WALL - 0.5, mb.ZMin + 12.0),
                               box(x0 - 1, x1 + 1, YF - 0.3, YB + 0.3, mb.ZMin - 0.1, 60)))
chassis = cad.fuse_one(cad.cut(chassis, csks), cradle, *saddles)
z_boss = 7.5 + WALL + 0.1 + 0.6                 # 0.1 over the floor, clear of its fillet
sleeves = [cyl(2.8, (x, y, z_boss), (0, 0, 1), 9.4) for x, y in SCREWS]
pockets = [cyl(1.6, (x, y, z_boss), (0, 0, 1), 9.5) for x, y in SCREWS]
tick("chassis + screws")

# ------------------------------------------------------------ lights, ToF, USB-C
# headlights: a clear light pipe with a retaining flange behind the wall,
# in a chrome bezel sitting in a counterbore
FACE_Y = -NF                                          # the body's vertical nose face
lenses, bezels, holes = [], [], []
for m in (head_l, head_r):
    b = ap.bbox(m)
    cx = (b.XMin + b.XMax) / 2
    y0 = b.YMin - 0.4                           # 0.4 mm in front of the LEDs
    pipe_ = cad.lens(17.6, (y0 - FACE_Y) + 1.2, dome=1.2, at=(cx, y0, LZ), axis="-Y")
    flange = cyl(9.5, (cx, FACE_Y + 2.0 + 0.9, LZ), (0, -1, 0), 0.8)        # 0.1 mm behind the inner face
    lenses.append(cad.fuse_one(pipe_, flange))
    holes.append(cyl(12.4, (cx, FACE_Y - 1, LZ), (0, 1, 0), 2.1))           # bezel counterbore 1.1 deep
    holes.append(cyl(8.8 + 0.2, (cx, FACE_Y - 1, LZ), (0, 1, 0), 4.0))      # the pipe's opening, 0.2 clear
    bezel = cad.cut(cyl(12.1, (cx, FACE_Y + 1.1, LZ), (0, -1, 0), 2.6), cyl(9.3, (cx, FACE_Y + 3, LZ), (0, -1, 0), 8))
    bezels.append(cad.soften(bezel, 0.5))
# R500: the cabled modules' holders - ribs down from the hood either side
# of the ToF and of each headlight, 0.3 mm off (the lens / grille in
# front, the ribbon below stay clear). R610: the hood slopes - each rib
# stands 1 mm into the hood's lowest point over it (measured)
holders = []
for m in (eye, head_l, head_r):
    b = ap.bbox(m)
    for x0, x1 in ((b.XMin - 1.6, b.XMin - 0.3), (b.XMax + 0.3, b.XMax + 1.6)):
        y0_, y1_ = b.YMin + 1.0, b.YMax - 1.0
        top = min(under_z(core_l, *to_body(xx, yy)) for xx in (x0, x1) for yy in (y0_, y1_)) + 1.0
        holders.append(box(x0, x1, y0_, y1_, b.ZMin + 3.0, top))
# USB-C: a pocket in the tail brings the wall to 0.25 mm in front of
# the socket mouth (a real plug reaches), then the measured opening
pocket = prism_y([(21, 15.4), (39, 15.4), (39, 25.6), (21, 25.6)], 2.5, 2.1, 30)
liner = cad.cut(prism_y([(19, 13.4), (41, 13.4), (41, 27.6), (19, 27.6)], 3.5, ap.bbox(usb).YMax + 0.25,
                        -min(p.x for p in ray(core_l, (-40, 0, 20.5), (0, 0, 20.5))) + 1.0), pocket)
# side mirrors on stalks from the shoulder, by the A-pillars (fused with
# the rest; STAGE B detail)
mir = cad.fuse_one(cad.pipe([(-17.5, -88.5, TOP - 0.6), (-21.5, -88.5, TOP + 2.5), (-25.5, -88.5, TOP + 4.5)], r=1.1),
                   cad.rounded_box(3, 8, 5.5, 1.2, at=(-28.5, -92.5, TOP + 3.5), edges="x"))
# ONE fuse, then ONE cut, on the shell
tub = cad.fuse_one(tub, *(adds + peg_bosses + bosses + sleeves + holders + [liner, mir, cad.mirror(mir, "YZ", (30, 0, 0))]))
# door handles: 1 mm recesses in the measured side (STAGE B detail)
handles = []
for sg in (-1, 1):
    hy = outer_y(body_l, 52.0, 47.2, sg)
    handles.append(box(30 + sg * (hy - 1.0) - (3.0 if sg > 0 else 0), 30 + sg * (hy - 1.0) + (0 if sg > 0 else 3.0),
                       -55, -49, 46, 48.4))
tub = cad.cut(tub, peg_bores + pockets + holes + handles + [pocket])
tub = cad.socket_opening(tub, usb, margin=1.5)
# grille: a recessed black insert with five slots; the middle one holds a
# clear lens in front of the ToF (it sees through glass - ./check R250)
tub, grille = insert(tub, prism_y(GRILLE, 3.5, FACE_Y + 6, FACE_Y - 6))
grille.translate(V(0, 0.8, 0))                 # 0.8 mm behind the face
slots = []
for x, w in SLOTS:
    slots.append(cad.rounded_box(w, 20, 23.4, w / 2 - 0.05, at=(x - w / 2, FACE_Y - 6, 15), edges="y"))
tof_lens = grille.common(slots[2])
grille = cad.cut(grille, slots)
tick("lights + grille + usb")

# ------------------------------------------------------------ wheels
# ONE wheel build (about 2 s): the left rear; mirrored for the right side,
# copied to the front stubs. Its cap is pressed 0.6 mm into the hub
# pocket and fused: tyre + rim per wheel.
w = cad.wheel(2 * R, WHEEL_W, spokes=5, tread="block", tread_n=22, bore=3.3, axis="-X", at=(30 - 60.5, SHAFT_Y, R))
cap = w["cap"].copy()
cap.translate(V(0.6, 0, 0))
rim = cad.fuse_one(w["rim"], cap)
wheels = {}
for sd, (ty, rm) in (("L", (w["tyre"], rim)),
                     ("R", (cad.mirror(w["tyre"], "YZ", (30, 0, 0)), cad.mirror(rim, "YZ", (30, 0, 0))))):
    for ax_n, y in (("R", SHAFT_Y), ("F", FRONT_Y)):
        for kk, sh in (("Tyre", ty), ("Rim", rm)):
            s_ = sh.copy()
            s_.translate(V(0, y - SHAFT_Y, 0))
            wheels["%s_%s%s" % (kk, ax_n, sd)] = s_
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one;
# the mirrors and door handles went into STAGE A's batched booleans)
# glass: windscreen, side and rear windows - smoked panes that fill their
# openings exactly (cut from the hardtop, so no overlap and no gap)
panes = {}
# R610: each cutter is extruded along its face's normal - a cutter along
# Y through the 25 deg windscreen left the pane a 0.01 mm knife edge


def glass_cutter(kind, spans, sg=1):
    """A soft-cornered cutter square to the cabin's `kind` face ('front',
    'rear', 'side' on side sg), through its wall, over the spans at GLASS_Z."""
    (a0, b0), (a1, b1) = spans
    (xr0, xf0, hw0, _r), (xr1, xf1, hw1, _r) = cabin_at(TOP, 0.0), cabin_at(HT_Z1, 0.0)
    pts = []
    for (a, b), z in zip(((a0, b0), (b1, a1)), GLASS_Z):
        xr, xf, hw, _r = cabin_at(z, 0.0)
        for u in (a, b):
            pts.append({"front": (u, -xf, z), "rear": (u, -xr, z), "side": (30 + sg * hw, u, z)}[kind])
    h = HT_Z1 - Z0
    n = {"front": V(0, -h, xf0 - xf1), "rear": V(0, h, xr1 - xr0), "side": V(sg * h, 0, hw0 - hw1)}[kind]
    n.normalize()
    w_ = soft_wire(pts, 3)
    w_.translate(n * -3.0)
    return soft_prism(w_, n * 6.0)


ht, panes["Windscreen"] = insert(ht, glass_cutter("front", WINDSCREEN))
for sd, sg in (("L", -1), ("R", 1)):
    ht, panes["Side_Window_" + sd] = insert(ht, glass_cutter("side", SIDE_WINDOWS, sg))
ht, panes["Rear_Window"] = insert(ht, glass_cutter("rear", REAR_WINDOW))
# tail lights: red inserts in the tail's corners - ONE insert for both
tub, tl = insert(tub, Part.makeCompound([prism_y([(x0, 30), (x0 + 8, 30), (x0 + 8, 46), (x0, 46)], 2.2, 10, 25)
                                         for x0 in (-16.5, 68.5)]))
tails = sorted(tl.Solids, key=lambda s_: s_.BoundBox.XMin)
tick("glass + tails")
# door seams (both sides) between the arches. R610: cut as the seam's
# band less the body inset 0.5 mm - the slab outside that inset surface -
# so no tool face lies ON the shell (cad.groove_outline's moved copies of
# the side came back as a 1.6 mm crumb from OCCT here, MEASURED)
SEAM_Z = (16.0, 51.0)
seam = soft_wire([(0, -44, SEAM_Z[0]), (0, -106, SEAM_Z[0]), (0, -106, SEAM_Z[1]), (0, -44, SEAM_Z[1])], 4)
band = Part.Face(seam.makeOffset2D(0.3, join=0)).cut(Part.Face(seam.makeOffset2D(-0.3, join=0)))
band.translate(V(-60, 0, 0))


def skin_cut(shape, region, probes, what):
    """shape less the part of `region` outside skin05 (a 0.5 mm deep
    groove), proven by probe points (material before, air after)."""
    res = shape.cut(region.cut(skin05))
    if not (res.isValid() and len(res.Solids) == 1 and res.BoundBox.XLength > 100
            and all(shape.isInside(p_, 1e-4, True) and not res.isInside(p_, 1e-4, True) for p_ in probes)):
        raise cad.CadError("%s: the groove did not cut (probes %s)" % (what, probes))
    return res


tub = skin_cut(tub, band.extrude(V(180, 0, 0)),
               [V(30 + sg * (outer_y(body_l, 44.0, 30.0, sg) - 0.25), -44.0, 30.0) for sg in (-1, 1)], "door seams")
tub = cad.text(tub, "ATECH", (30, -min(p.x for p in ray(body_l, (-40, 0, 38.0), (0, 0, 38.0))), 38.0), (0, 1, 0),
               5.0, depth=0.5, mode="deboss")
# the parting-line reveal: a groove round the tub just above the seam
tub = skin_cut(tub, box(-100, 160, -250, 100, REVEAL_Z - 0.4, REVEAL_Z + 0.4),
               [V(30 + sg * (outer_y(body_l, 70.0, REVEAL_Z, sg) - 0.25), -70.0, REVEAL_Z) for sg in (-1, 1)],
               "parting-line reveal")
tick("tub details")
# wrap-around bumpers (below the split, on the chassis): their ends run
# into the chassis' corners, a bracket each side of the middle
parts_c = [cad.pipe([(30 - 50, -NF + 6, 9.0), (30 - 40, -NF - 3.5, 9.0), (30, -NF - 4.5, 9.0),
                     (30 + 40, -NF - 3.5, 9.0), (30 + 50, -NF + 6, 9.0)], r=2.4),
           cad.pipe([(30 - 46, 10.0, 9.0), (30 - 38, 22.0, 9.0), (30, 24.0, 9.0),
                     (30 + 38, 22.0, 9.0), (30 + 46, 10.0, 9.0)], r=2.4)]
for x in (6, 48):
    parts_c.append(box(x, x + 6, -NF - 3.5, -NF + 6, 7.8, 10.6))
    parts_c.append(box(x, x + 6, 12.0, 23.0, 7.8, 10.6))
chassis = cad.fuse_one(chassis, *parts_c)
tick("stage B")


# ------------------------------------------------------------ parts
def part(name, shape):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    return o


for nm, sh in (("Chassis", chassis), ("Body_Shell", tub), ("Hardtop", ht), ("Grille", grille)):
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS[nm])
o = part("ToF_Lens", tof_lens)
o.ViewObject.ShapeColor = cad.color(COLOURS["Lens"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Lens"])
for nm, sh in panes.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Glass"])
    o.ViewObject.Transparency = cad.transparency(COLOURS["Glass"])
for i, sd in enumerate("LR"):
    o = part("Headlight_" + sd, lenses[i])
    o.ViewObject.ShapeColor = cad.color(COLOURS["Lens"])
    o.ViewObject.Transparency = cad.transparency(COLOURS["Lens"])
    o = part("Bezel_" + sd, bezels[i])
    o.ViewObject.ShapeColor = cad.color(COLOURS["Bezel"])
    o = part("Tail_Light_" + sd, tails[i])
    o.ViewObject.ShapeColor = cad.color(COLOURS["Tail"])
    o.ViewObject.Transparency = cad.transparency(COLOURS["Tail"])
for i, sh in enumerate(screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
for nm, sh in wheels.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Tyre"] if nm.startswith("Tyre") else COLOURS["Rim"])
print("TOTAL %.1f s" % (time.time() - T0))
