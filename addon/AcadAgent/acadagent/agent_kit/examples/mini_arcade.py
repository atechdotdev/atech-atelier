"""Example: "a mini arcade cabinet" - a tabletop arcade: marquee, leaning screen, control deck.

fork this file for an arcade cabinet / tabletop console (a bartop arcade, a
retro cabinet, a jukebox - anything with a deck of controls in front of a
leaning screen under a sign); change PARAMETERS and the outlines.
ARCHETYPE: arcade

How it is built (R270):
  * STAGE A - hardware, shell, every working-face opening, fasteners: the
    board FLAT under the control deck, its long side across the cabinet;
    on its front edge the KNOB on the pair (1, 2) - a spinner left of the
    centre, its cap turning in a hole in the deck, flush with it (the deck
    stands at the cap's top: no module may stand out of the body; the
    buttons and the light reach up to it on long plungers) - a LIGHT on port 3 under a
    START lens, two BUTTONS on ports 4 and 5 under big round caps: every
    deck control SEATED, facing up; USB-C on port 7 in a pocket in the left
    side. The SCREEN and the SPEAKER are CABLED from the back-edge pairs
    (10, 11) and (13, 14) up the leaning panel (each module tilted with
    it): the screen's ribbons loop up and forward over the board's back
    strip and climb the panel into its bottom edge, the speaker's rise
    behind the screen into the speaker above it. Each ribbon only bends
    round its width or shifts sideways in its own plane, so none twists,
    and the pairs never cross. The cabinet is ONE side profile (kick panel,
    deck, leaning panel, marquee, roof, back: corners filleted) extruded
    across and hollowed with its own inset profile (faceted inside
    corners: no concave arcs to read as clip channels), split just under
    the board into the fixed Base (it carries the board: pads, end fences)
    and the Shell (fitted after the modules: their slide paths run through
    its walls); four M2.5 screws from below into blocks in the Shell.
  * STAGE B - details: side art inlays inside a black border (the
    T-molding look), the marquee sign with lettering, a smoked glass over
    a gloss-black mask with the screen's window, a coin door on the kick
    panel, a raised trim round the spinner, rubber feet.
RESTYLE (R425): WIDTH, HEIGHT, DEPTH, CORNER and WALL drive the profile
and every cutter; the hardware (the board across the deck, the screen and
speaker up the panel) sets a floor the cabinet never shrinks below
(printed as FLOOR). The hardware frame (the board, the panel's slope and
the modules on it) is the board's own: never move it with a knob.
DETAILS (visible, 30): 1 kick panel; 2 flat control deck; 3 leaning screen
panel; 4 overhanging marquee; 5 roof; 6 rounded outside corners; 7-8 side
art inlays in a black border; 9 marquee sign; 10 "ATECH" on it; 11 smoked
screen glass; 12 gloss-black mask; 13 the screen's window in it; 14 round
speaker grille; 15 speaker chamber to the driver; 16 spinner through the
deck; 17 raised spinner trim; 18-19 two big round button caps with
plungers; 20 START lens; 21 coin door; 22-23 two coin slots; 24 USB-C
pocket with liner; 25 rib onto the board's spine; 26 board pads and end
fences; 27 four screws from below into blocks; 28 four rubber feet;
29 ribs either side of the screen and the speaker; 30 lip keying the
Shell onto the Base.
Materials: graphite cabinet, signal-red side art and buttons, toy-yellow
marquee, smoked glass, gloss-black mask, chrome coin door and screws,
rubber feet.
MEASURED (R500, 2026-10-27): see test_kit_examples_r500 (TIMINGS line).
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
    "Shell", "Glass", "Mask", "Marquee", "Side_Art_L", "Side_Art_R", "Coin_Door", "Spinner_Ring",
    "Cap_A", "Cap_B", "Start_Lens",
    "screen_10_11_cable_p10", "screen_10_11_cable_p11", "speaker_13_14_cable_p13", "speaker_13_14_cable_p14",
    "Screw_1", "Screw_2", "Screw_3", "Screw_4"],
    # the caps press the buttons, the lens carries the light (declared covers)
    "covers": {"Cap_A": "button_p4", "Cap_B": "button_p5", "Start_Lens": "light_p3"}}
REVIEW_CLOSEUPS = ["Cap_A", "Glass", "Marquee"]


def tick(what, t=[time.time()]):
    print("TIME %-22s %5.1f s" % (what, time.time() - t[0]))
    t[0] = time.time()


# === PARAMETERS (restyle here) ===
# RESTYLE (R425) - the knobs a restyle turns. Every outline and every
# cutter in the stages is derived from them. The hardware sets a floor
# under WIDTH, HEIGHT and DEPTH: below it the cabinet keeps the smallest
# size that still holds it (printed as FLOOR).
WIDTH = 142.0      # RESTYLE 120..164 width: across the cabinet (x)
HEIGHT = 196.0     # RESTYLE 166..226 height: the desk to the roof (z)
DEPTH = 110.0      # RESTYLE 93..127 length: the kick panel to the back (y)
CORNER = 6.0       # RESTYLE 5..7 radius: the profile's outside corners
WALL = 2.4         # RESTYLE 2.0..2.8 wall
# end RESTYLE
# Cabinet frame: x across, y from the player (-Y) to the back, z up from
# the desk. The hardware frame (fixed: the board and the panel decide it):
FOOT = 2.0                     # rubber feet under the base
TILT = 12.0                    # the screen panel leans back this much
Y_P = 30.0                     # the leaning panel's foot (behind the deck controls)
S_SCR = 40.0                   # the screen's centre up the panel (its ribbons shift 20 mm below it)
S_SPK = 94.0                   # the speaker's centre up the panel (above the screen)
OVERHANG = 16.0                # the marquee stands this far out over the panel
CAP_D = 16.0                   # the button caps
GRILLE_D = 34.0                # the speaker grille
SCREW = "M2.5"
COLOURS = {"Shell": "graphite", "Base": "matte_black", "Art": "signal_red", "Marquee": "toy_yellow",
           "Glass": "smoked", "Mask": "#0b0c0e", "Cap": "signal_red", "Trim": "chrome",
           "Lens": "led_white", "Foot": "rubber", "Screw": "chrome"}


# === STAGE A: hardware, shell, every working-face opening, fasteners ===
Z_BOT = FOOT                                     # the base's underside
LIFT = Z_BOT + WALL + 1.0                        # the board's underside (1 mm of pads under it)
FLAT = Rotation(Vector(1, 0, 0), 90)
ACROSS = Rotation(Vector(0, 0, 1), 90).multiply(FLAT)     # long side along X, port 1 front-left
board = ap.board_object(doc)
board.Placement = Placement(Vector(), ACROSS)
_b = ap.bbox(board)
board.Placement = Placement(Vector(-_b.XMin, -_b.YMin, LIFT - _b.ZMin), ACROSS)   # x 0..120, y 0..60
BB = ap.bbox(board)
knob = ap.seat(doc, "knob", (1, 2))              # front left: the spinner
start = ap.seat(doc, "light", 3)                 # the START lens
btn_a = ap.seat(doc, "button", 4)
btn_b = ap.seat(doc, "button", 5)
usb = ap.seat(doc, "usbc", 7)                    # left end, mouth -X
AX = (BB.XMin + BB.XMax) / 2                     # the cabinet's centre line: the board's middle
TS, TC = math.sin(math.radians(TILT)), math.cos(math.radians(TILT))
UP = (TS, TC)                                    # up the panel, in (y, z)
INN = (TC, -TS)                                  # into the cabinet, square to the panel
Z_DECK = ap.bbox(knob).ZMax                      # the deck's top face, flush with the spinner's cap (no
                                                 # module may stand out of the body) = the panel's foot
PANEL = Placement(V(0, Y_P, Z_DECK), Rotation(V(1, 0, 0), 90 - TILT))   # x, up the panel, out of it


def on_panel(s, depth):
    """(y, z) of the point s up the panel's outer face and depth behind it."""
    return (Y_P + s * UP[0] + depth * INN[0], Z_DECK + s * UP[1] + depth * INN[1])


def tilt(p, c):
    """Point p turned back TILT about the X axis through c (as the panel)."""
    dy, dz = p[1] - c[1], p[2] - c[2]
    return (p[0], c[1] + dy * TC + dz * TS, c[2] - dy * TS + dz * TC)


def panel_box(x0, x1, s0, s1, d0, d1):
    """A box in the panel's frame: x, s up the panel, d behind its face."""
    b = Part.makeBox(x1 - x0, s1 - s0, d1 - d0, V(x0, s0, -d1))
    b.Placement = PANEL.multiply(b.Placement)
    return b


TILT_ROT = Rotation(Vector(1, 0, 0), -TILT)
# the screen: its face 0.4 mm behind the glass, its pins DOWN the panel;
# the speaker: its face 0.8 mm behind the panel, its pins DOWN the panel
SCR_C = (AX,) + on_panel(S_SCR, WALL + 0.4 + 4.82)
SPK_C = (AX,) + on_panel(S_SPK, WALL + 0.8 + 10.1)
SCR_LEAD = [tilt((SCR_C[0] + dx, SCR_C[1] + 3.55, SCR_C[2] - 12.89), SCR_C) for dx in (-10, 10)]   # MEASURED
SPK_LEAD = [tilt((SPK_C[0] + dx, SPK_C[1] + 8.83, SPK_C[2] - 22.64), SPK_C) for dx in (-10, 10)]   # MEASURED
PLUG_Y, PLUG_Z = BB.YMax + 3.25, LIFT + 3.77     # each back-edge plug's lead end: MEASURED


def arc_pts(c, r, a0, a1, x, n=6):
    """n points of an arc in the YZ plane at x (no start point)."""
    return [(x, c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(1, n + 1)]


def ease(x0, x1, n):
    """n x values eased from x0 to x1 (an S: the ribbon shifts sideways in
    its own plane, so its width comes back square - no twist)."""
    return [x0 + (x1 - x0) * (0.5 - 0.5 * math.cos(math.pi * i / n)) for i in range(1, n + 1)]


def screen_route(xp, lead, ru=4.0, ra=6.0):
    """Plug at x = xp -> the screen's socket lead end: a loop up and forward
    over the board's back strip, a run forward, an arc onto the panel's
    slope, then up the panel shifting sideways to the socket's x. (R500,
    MEASURED: the API's spline takes its end tangent at the whole cable's
    scale - the last point sits 0.1 mm short of the lead end, or the
    ribbon loops out of the cabinet.)"""
    pts = arc_pts((PLUG_Y, PLUG_Z + ru), ru, -90, 90, xp, 8)
    z_run = PLUG_Z + 2 * ru
    end_off = (-ra * TC, ra + ra * TS)                       # the arc's end - (y_a, z_run)
    L = (lead[2] - (z_run + end_off[1])) / UP[1]             # the straight up the panel
    y_a = lead[1] - L * UP[0] - end_off[0]
    pts += [(xp, PLUG_Y - (PLUG_Y - y_a) * i / 3, z_run) for i in range(1, 4)]
    pts += arc_pts((y_a, z_run + ra), ra, -90, -180 - TILT, xp, 8)
    y0, z0 = pts[-1][1], pts[-1][2]
    n = max(4, int(L / 3.0))
    xs = ease(xp, lead[0], n)
    pts += [(xs[i - 1], y0 + (L - 0.1) * UP[0] * i / n, z0 + (L - 0.1) * UP[1] * i / n) for i in range(1, n + 1)]
    return pts


def speaker_route(xp, lead, r1=4.0):
    """Plug at x = xp -> the speaker's socket lead end: a quarter turn up
    behind the board, a rise behind the screen that shifts sideways to the
    socket's x (in the ribbon's own plane), a lean onto the panel's slope."""
    pts = arc_pts((PLUG_Y, PLUG_Z + r1), r1, -90, 0, xp, 5)
    y_r, z0 = PLUG_Y + r1, PLUG_Z + r1
    z_lean = lead[2] - 12.0
    n = 12
    xs = ease(xp, lead[0], n)
    pts += [(xs[i - 1], y_r, z0 + (z_lean - z0) * i / n) for i in range(1, n + 1)]
    # (0.2 mm short of the lead end - MEASURED: 0.1 left the plug, ribbon and
    # socket unfusable at WALL 2.0)
    yl, zl = lead[1] - 0.2 * UP[0], lead[2] - 0.2 * UP[1]
    pts += [(lead[0], y_r + (yl - y_r) * f * f, z_lean + (zl - z_lean) * f) for f in (0.4, 0.75, 1.0)]
    return pts


scr, scr_ribs = ap.cable(doc, "screen", (10, 11), Placement(Vector(), TILT_ROT, Vector(*SCR_C)).multiply(
    ap.module_placement("screen", SCR_C, face="-Y", cable="-Z")),
    via={10: screen_route(BB.XMin + 30.0, SCR_LEAD[0]), 11: screen_route(BB.XMin + 50.0, SCR_LEAD[1])})
spk, spk_ribs = ap.cable(doc, "speaker", (13, 14), Placement(Vector(), TILT_ROT, Vector(*SPK_C)).multiply(
    ap.module_placement("speaker", SPK_C, face="-Y", cable="-Z")),
    via={13: speaker_route(BB.XMin + 90.0, SPK_LEAD[0]), 14: speaker_route(BB.XMin + 110.0, SPK_LEAD[1])})
RIBS = scr_ribs + spk_ribs
tick("hardware")


def box(x0, x1, y0, y1, z0, z1):
    return Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def cyl(r, p, d, h):
    return Part.makeCylinder(r, h, V(*p), V(*d))


def centre(m):
    b = ap.bbox(m)
    return (b.XMin + b.XMax) / 2, (b.YMin + b.YMax) / 2, (b.ZMin + b.ZMax) / 2


def top_z(shape, x, y, nth=0):
    """The deck's top (nth=0) or inner (nth=1) face z at (x, y), by a ray."""
    s = shape.section(Part.makeLine(V(x, y, 400), V(x, y, -50)))
    zs = sorted((v.Point.z for v in s.Vertexes), reverse=True)
    return zs[nth]


def insert(shell, cutter):
    """(shell with the opening, the piece that fills it exactly)."""
    piece, rest = shell.common(cutter), shell.cut(cutter)
    if piece.Volume < 1:
        piece, rest = shell.common(cutter, 0.01), shell.cut(cutter, 0.01)
    if piece.Volume < 1 or not rest.isValid() or len(rest.Solids) != len(shell.Solids):
        raise cad.CadError("insert: the cutter does not cleanly cross the wall")
    return rest, piece


def xprism(y0, y1, z0, z1, x0, x1, r):
    w = cad.rounded_rect_wire(y1 - y0, z1 - z0, r, (x0, (y0 + y1) / 2, (z0 + z1) / 2), "X")
    return Part.Face(w).extrude(V(x1 - x0, 0, 0))


# ------------------------------------------------------------ the cabinet's size
# R425: the knobs, never below what the hardware needs. The kick panel
# stands 1 mm in front of the spinner; the back 0.8 mm behind the speaker
# and the ribbons; the sides leave room for the screw blocks at the ends.
kb, sb = ap.bbox(knob), ap.bbox(spk)
REAR = max(sb.YMax, max(r_.Shape.BoundBox.YMax for r_ in RIBS)) + 0.8
Y_FRONT = kb.YMin - 1.0 - WALL
Y_BACK = Y_FRONT + max(DEPTH, REAR + WALL - Y_FRONT)
W = max(WIDTH, 2 * (BB.XMax - AX + 7.0 + WALL))
X0, X1 = AX - W / 2, AX + W / 2
S_TOP = S_SPK + 20.0 + 7.0                        # the panel's top: over the speaker
Y_PT, Z_PT = on_panel(S_TOP, 0)
Y_M = Y_PT - OVERHANG                             # the marquee's face
Z_TOP = max(HEIGHT, Z_PT + 30.0, sb.ZMax + 10.0)
R = CORNER
print("FLOOR cabinet %.1f x %.1f x %.1f (knobs %.1f x %.1f x %.1f)" % (W, Y_BACK - Y_FRONT, Z_TOP, WIDTH, DEPTH,
                                                                      HEIGHT))
# the side profile (y, z), going round: corner radii (outside corners R,
# inside 3, the base's 2)
PROFILE = [((Y_BACK, Z_BOT), 2.0), ((Y_FRONT, Z_BOT), 2.0), ((Y_FRONT, Z_DECK), R), ((Y_P, Z_DECK), 3.0),
           ((Y_PT, Z_PT), 3.0), ((Y_M, Z_PT), R), ((Y_M, Z_TOP), R), ((Y_BACK, Z_TOP), R)]


def offset_poly(pts, d):
    """The polygon pts moved d inward: each corner where its two
    neighbours' offset edges meet."""
    n, out = len(pts), []
    area = sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(n))
    d = d if area > 0 else -d                        # inward is left of a counter-clockwise run
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        e1 = (b[0] - a[0], b[1] - a[1])
        e2 = (c[0] - b[0], c[1] - b[1])
        l1, l2 = math.hypot(*e1), math.hypot(*e2)
        n1, n2 = (-e1[1] / l1 * d, e1[0] / l1 * d), (-e2[1] / l2 * d, e2[0] / l2 * d)   # left = inward
        p1, p2 = (a[0] + n1[0], a[1] + n1[1]), (b[0] + n2[0], b[1] + n2[1])
        den = e1[0] * e2[1] - e1[1] * e2[0]
        t = ((p2[0] - p1[0]) * e2[1] - (p2[1] - p1[1]) * e2[0]) / den
        out.append((p1[0] + e1[0] * t, p1[1] + e1[1] * t))
    return out


def rounded(pts, radii, facets=0, concave_facets=3):
    """Points for yz_face: each corner filleted at its radius, as an
    ('arc', mid, end) - or as straight facets: `facets` on the outward
    corners, `concave_facets` on the inward ones (R7: a concave arc reads as
    an open clip channel to ./check)."""
    n, out = len(pts), []
    area = sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(n))
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        u1 = (a[0] - b[0], a[1] - b[1])
        u2 = (c[0] - b[0], c[1] - b[1])
        l1, l2 = math.hypot(*u1), math.hypot(*u2)
        u1, u2 = (u1[0] / l1, u1[1] / l1), (u2[0] / l2, u2[1] / l2)
        half = math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))) / 2
        r = radii[i]
        k = r / math.tan(half)                       # the tangent points' distance from the corner
        t1, t2 = (b[0] + u1[0] * k, b[1] + u1[1] * k), (b[0] + u2[0] * k, b[1] + u2[1] * k)
        bis = (u1[0] + u2[0], u1[1] + u2[1])
        lb = math.hypot(*bis)
        cc = (b[0] + bis[0] / lb * r / math.sin(half), b[1] + bis[1] / lb * r / math.sin(half))
        mid = (cc[0] - bis[0] / lb * r, cc[1] - bis[1] / lb * r)
        out.append(t1)
        turn = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        nf = facets if turn * area > 0 else concave_facets
        if nf:
            a1, a2 = math.atan2(t1[1] - cc[1], t1[0] - cc[0]), math.atan2(t2[1] - cc[1], t2[0] - cc[0])
            da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
            out += [(cc[0] + r * math.cos(a1 + da * j / nf), cc[1] + r * math.sin(a1 + da * j / nf))
                    for j in range(1, nf)]
            out.append(t2)
        else:
            out.append(("arc", mid, t2))
    return out


def yz_face(items, x):
    """A face in the plane x = const from rounded()'s points and arcs."""
    edges, prev = [], items[0]
    for it in list(items[1:]) + [items[0]]:
        if isinstance(it[0], str):
            edges.append(Part.Arc(V(x, *prev), V(x, *it[1]), V(x, *it[2])).toShape())
            prev = it[2]
        else:
            if math.dist(prev, it) > 1e-6:
                edges.append(Part.makeLine(V(x, *prev), V(x, *it)))
            prev = it
    return Part.Face(Part.Wire(edges))


def prism(items, x0, x1):
    return yz_face(items, x0).extrude(V(x1 - x0, 0, 0))


corners = [p for p, _r in PROFILE]
radii = [r for _p, r in PROFILE]
outer = prism(rounded(corners, radii), X0, X1)
inner_c = offset_poly(corners, WALL)
core = prism(rounded(inner_c, [max(0.6, r - WALL) if r > 2.5 else 0.6 for r in radii], facets=3, concave_facets=0),
             X0 + WALL, X1 - WALL)
cabinet = cad.cut(outer, core)
tick("cabinet")
Z_SPLIT = LIFT + 0.4                              # just over the board's underside: in the cavity
base, shell = cad.split(cabinet, "Z", at=Z_SPLIT, lip=1.2)
tick("split")

# ------------------------------------------------------------ the Base: board
# pads 0.1 mm under the board, fences off its ends (under the modules'
# slide paths: those start 2.5 mm over the board's underside)
FLOOR = Z_BOT + WALL
pads = [box(x, x + 8, y, y + 8, FLOOR - 0.5, BB.ZMin - 0.1) for x in (BB.XMin + 6, BB.XMax - 14)
        for y in (BB.YMin + 4, BB.YMax - 12)]
fences = [box(BB.XMin - 1.8, BB.XMin - 0.3, BB.YMax - 14, BB.YMax - 4, FLOOR - 0.5, BB.ZMin + 1.6),
          box(BB.XMax + 0.3, BB.XMax + 1.8, BB.YMin + 4, BB.YMin + 14, FLOOR - 0.5, BB.ZMin + 1.6)]
base = cad.fuse_one(base, *pads, *fences)
# board retention from above: a rib from the deck onto the board's spine
# (0.2 mm off it), between the START light and the first button
rib_x = (ap.bbox(start).XMax + ap.bbox(btn_a).XMin) / 2
shell = cad.fuse_one(shell, box(rib_x - 6, rib_x + 6, 22, 28, BB.ZMax + 0.2, Z_DECK - WALL + 0.5))

# ------------------------------------------------------------ fasteners
# four M2.5 screws up through the base into blocks hanging in the Shell's
# corners (clear of the spinner, the ribbons and the USB-C socket), each
# a heat-set insert pocket (1.4 d + 0.1)
# (each boss 1.5 mm clear of the walls: the base's lip stands 1 mm in)
SCREWS = [(X0 + WALL + 4.4, Y_FRONT + WALL + 7.0), (X1 - WALL - 4.4, Y_FRONT + WALL + 7.0),
          (X0 + WALL + 4.4, Y_BACK - WALL - 7.0), (X1 - WALL - 4.4, Y_BACK - WALL - 7.0)]
BLOCK_Z0 = FLOOR + 11.0                           # the boss below it takes the pilot (4 d + 1)
blocks = []
for x, y in SCREWS:
    yw = Y_FRONT if y < 0 else Y_BACK             # each block on its end wall and its side wall
    zt = Z_DECK - WALL + 0.5 if y < 0 else BLOCK_Z0 + 12.0
    y0, y1 = sorted((y + (3.2 if y < 0 else -3.2), yw + (1 if y < 0 else -1) * (WALL - 0.5)))
    x0, x1 = sorted((x + (3.2 if x > AX else -3.2), (X0 + WALL - 0.5) if x < AX else (X1 - WALL + 0.5)))
    blocks.append(box(x0, x1, y0, y1, BLOCK_Z0, zt))
shell = cad.fuse_one(shell, *blocks)
screws = []
for x, y in SCREWS:
    base, shell = cad.screw_through(base, shell, (x, y, Z_BOT), size=SCREW, ribs=0)
    # the length screw_through prints: through the floor into the pilot
    reach = BLOCK_Z0 - (FLOOR + 0.1)
    length = int(min(WALL + 0.85 * reach, WALL + 0.1 + min(reach, 4.0 * 2.5 + 1.0) - 0.3))
    screws.append(cad.screw("csk_phillips", SCREW, length, at=(x, y, Z_BOT), axis="+Z"))
tick("base + screws")

# ------------------------------------------------------------ the deck: controls
# the spinner: its shaft through a round hole (the module came in from the
# front before the Shell went on), a chrome trim round it
kx, ky, _kz = centre(knob)
SPIN_R = 6.5                                      # the spinner's cap (r 6.0) turns in this hole
shell = cad.cut(shell, cyl(SPIN_R, (kx, ky, Z_DECK - WALL - 1), (0, 0, 1), WALL + 2))
# the buttons: big round caps through the deck, flange 0.1 mm under it, a
# plunger to 0.16 mm over each module
caps = {}
base_z = Z_DECK - WALL - 0.9
for nm, m in (("Cap_A", btn_a), ("Cap_B", btn_b)):
    x, y, _z = centre(m)
    cap = cad.button_cap(CAP_D, (Z_DECK + 3.0) - base_z, dome=1.0, flange=1.2, at=(x, y, base_z), axis="+Z")
    shell = cad.opening_for(shell, cap, clearance=0.25, chamfer=0.5, axis="+Z")
    mz = ap.bbox(m).ZMax
    caps[nm] = cad.fuse_one(cap, cyl(3.0, (x, y, mz + 0.16), (0, 0, 1), base_z - mz + 0.34))
# the START lens: a light pipe from 0.4 mm over the light up through the deck
lx, ly, _lz = centre(start)
lz0 = ap.bbox(start).ZMax + 0.4
lens = cad.lens(9.0, (Z_DECK + 1.2) - lz0, dome=0.8, at=(lx, ly, lz0), axis="+Z")
shell = cad.opening_for(shell, lens, clearance=0.2, chamfer=0.4, axis="+Z")
# USB-C in the left side: a pocket brings the wall to 0.25 mm off the
# mouth, a liner round it, then the measured opening
ub = ap.bbox(usb)
uy, uz = (ub.YMin + ub.YMax) / 2, BB.ZMin + 2.5 + 5.9   # the receptacle: 5.9 mm over the PCB top
pocket = xprism(uy - 7.5, uy + 7.5, uz - 3.75, uz + 3.75, X0 - 5, ub.XMin - 1.3, 3)
liner = cad.cut(xprism(uy - 9.5, uy + 9.5, max(uz - 5.75, Z_SPLIT + 2.0), uz + 5.75, X0 + 1.0, ub.XMin - 0.25, 3.5),
                pocket)
shell = cad.fuse_one(cad.cut(shell, pocket), liner)
shell = cad.socket_opening(shell, usb, margin=1.5)
tick("deck")

# ------------------------------------------------------------ the panel: screen, speaker
# the speaker: a round grille through the panel, a chamber tube from the
# wall to 0.5 mm off the driver, ribs either side 0.3 mm off (R442)
spk_face = on_panel(S_SPK, 0)
shell = cad.speaker_grille(shell, (AX, spk_face[0], spk_face[1]), (0, -TC, TS), GRILLE_D, ring_pitch=2.6, hole=1.6)
d_face = WALL + 0.8                               # the speaker's face behind the panel's face
chamber = cad.cut(panel_box(AX - 19.5, AX + 19.5, S_SPK - 19.5, S_SPK + 19.5, WALL - 0.5, d_face - 0.5),
                  panel_box(AX - 17.5, AX + 17.5, S_SPK - 17.5, S_SPK + 17.5, 0, d_face + 1))
spk_ribs_ = [panel_box(x0, x1, S_SPK - 14, S_SPK + 14, WALL - 0.5, d_face + 14) for x0, x1 in
             ((sb.XMin - 2.0, sb.XMin - 0.3), (sb.XMax + 0.3, sb.XMax + 2.0))]
shell = cad.fuse_one(shell, chamber, *spk_ribs_)
# the screen: ribs either side 0.3 mm off; the glass and its mask are an
# insert in the panel (STAGE B cuts the window)
scb = ap.bbox(scr)
# (each rib hangs from tabs above and below the glass: the glass's
# opening must not leave it an island)
GLASS = (78.0, 30.0)                              # the glass over the screen: w, h up the panel
GS = GLASS[1] / 2
scr_ribs_ = []
for x0, x1 in ((scb.XMin - 2.0, scb.XMin - 0.3), (scb.XMax + 0.3, scb.XMax + 2.0)):
    scr_ribs_ += [panel_box(x0, x1, S_SCR - GS - 4, S_SCR + GS + 4, WALL + 0.3, WALL + 0.4 + 9.0)]
    scr_ribs_ += [panel_box(x0, x1, S_SCR + k * GS + (0.5 if k > 0 else -4), S_SCR + k * GS + (4 if k > 0 else -0.5),
                            WALL - 0.5, WALL + 0.5) for k in (-1, 1)]
shell = cad.fuse_one(shell, *scr_ribs_)
glass_cut = cad.rounded_box(GLASS[0], GLASS[1], 10 + WALL + 0.3, 4.0, at=(-GLASS[0] / 2, -GS, -(WALL + 0.3)))
glass_cut.Placement = PANEL.multiply(Placement(V(AX, S_SCR, 0), Rotation())).multiply(glass_cut.Placement)
shell, glass = insert(shell, glass_cut)
tick("stage A")


# === STAGE B: details ===
# (a fork may stop after STAGE A, run ./check, then add these one by one)
# the glass is 1 mm of smoked glass over a gloss-black mask; the mask's
# window sits exactly over the screen's 25.6 x 13.5 active area (+0.4)
glass, mask = insert(glass, panel_box(-500, 500, -500, 500, 1.0, 50))
ACTIVE = (25.6 + 0.8, 13.5 + 0.8)
mask = cad.cut(mask, panel_box(AX - ACTIVE[0] / 2, AX + ACTIVE[0] / 2, S_SCR - ACTIVE[1] / 2, S_SCR + ACTIVE[1] / 2,
                               -1, 20))
# the marquee sign: an insert in the marquee's face, lettered
shell, marquee = insert(shell, cad.rounded_box(X1 - X0 - 16, WALL + 5.3, Z_TOP - Z_PT - 12, 4.0,
                                               at=(X0 + 8, Y_M - 5, Z_PT + 6), edges="y"))
marquee = cad.text(marquee, "ATECH", (AX, Y_M, (Z_PT + Z_TOP) / 2), (0, -1, 0), min(12.0, (Z_TOP - Z_PT) * 0.4),
                   depth=0.5, mode="deboss")
# side art: an inlay in each side, the profile 7 mm in - the black border
# round it reads as the T-molding
# (it starts over the USB-C pocket, so the plug still gets in)
Z_ART0 = uz + 9.5 + 3.0
art_face = yz_face(rounded(offset_poly(corners, 7.0), [max(0.8, r - 4.0) for r in radii], facets=3), 0.0)
art_face = art_face.common(box(-1, 1, -500, 500, Z_ART0, 1000)).Faces[0]
side_art = {}
for nm, x in (("Side_Art_L", X0), ("Side_Art_R", X1)):
    f = art_face.copy()
    f.translate(V(x, 0, 0))
    shell, side_art[nm] = cad.inlay(shell, f.OuterWire, depth=1.0, flange=0)
# a coin door in the kick panel: a chrome plate that fills its opening
# (an insert through the wall), two coin slots through it
door_z = (Z_SPLIT + 2.0 + Z_DECK - WALL) / 2
shell, door = insert(shell, cad.rounded_box(30, WALL + 1.3, 16, 2.0, at=(AX - 15, Y_FRONT - 1, door_z - 8),
                                            edges="y"))
door = cad.cut(door, [cad.rounded_box(1.8, WALL + 3, 8, 0.8, at=(AX + dx - 0.9, Y_FRONT - 1.5, door_z - 4), edges="y")
                      for dx in (-7, 7)])
# a raised chrome trim round the spinner's hole
ring = cad.cut(cyl(SPIN_R + 4.0, (kx, ky, Z_DECK - 0.5), (0, 0, 1), 1.5),
               cyl(SPIN_R, (kx, ky, Z_DECK - 1), (0, 0, 1), 3))
shell = cad.cut(shell, ring)
# rubber feet in recesses under the base
feet = []
for x in (X0 + 14, X1 - 14):
    for y in (Y_FRONT + 14, Y_BACK - 14):
        base = cad.cut(base, cyl(3.1, (x, y, Z_BOT - 1), (0, 0, 1), 2.0))
        feet.append(cad.foot(6, Z_BOT + 0.9, style="dome", at=(x, y, Z_BOT + 0.9)))
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
o = part("Glass", glass)
o.ViewObject.ShapeColor = cad.color(COLOURS["Glass"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Glass"])
o = part("Mask", mask)
o.ViewObject.ShapeColor = cad.color(COLOURS["Mask"])
o = part("Marquee", marquee)
o.ViewObject.ShapeColor = cad.color(COLOURS["Marquee"])
for nm, sh in side_art.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Art"])
o = part("Coin_Door", door)
o.ViewObject.ShapeColor = cad.color(COLOURS["Trim"])
o = part("Spinner_Ring", ring)
o.ViewObject.ShapeColor = cad.color(COLOURS["Trim"])
for nm, sh in caps.items():
    o = part(nm, sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Cap"])
o = part("Start_Lens", lens)
o.ViewObject.ShapeColor = cad.color(COLOURS["Lens"])
o.ViewObject.Transparency = cad.transparency(COLOURS["Lens"])
for i, sh in enumerate(feet):
    o = part("Foot_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Foot"])
for i, sh in enumerate(screws):
    o = part("Screw_%d" % (i + 1), sh)
    o.ViewObject.ShapeColor = cad.color(COLOURS["Screw"])
print("TOTAL %.1f s" % (time.time() - T0))
