"""make_default_projects - build the default projects Atech Atelier ships
with (R450), from the showcase examples in agent_kit/examples/.

Runs INSIDE freecadcmd (FreeCAD's own Python), never system python:

    HOME=<scratch> ATECH_ARTIFACTS=<repo>/models \
        <freecadcmd> branding/make_default_projects.py --pass \
        <examples_dir> <out_dir>

(freecadcmd tries to open every extra argument as a file; after "--pass"
it leaves them alone. Without "--pass" the last two arguments are used.
ATECH_DEFAULTS_EXAMPLES / ATECH_DEFAULTS_OUT work too.)

For each example of CURATED it builds the way Studio builds an example
(shell.open_example): a fresh document, the example as model.py in a
workspace, its INTENT literal as intent.json, build.prepare_workspace,
then build.apply - the production build, sandboxed child and all. So the
board and modules are the library's real tagged Atech parts, and every
agent part carries its AtechAgentScript. Then:

  * the document is named from TITLES ("Toy car") and saved as
    <out_dir>/<Title>.FCStd, with a fresh AtechProjectId (= Uid) and the
    AtechProjectFile property projects_store keeps;
  * GuiDocument.xml + one ShapeAppearance list per object are written into
    the zip (freecadcmd has no view providers, so FreeCAD would save
    none): the colours, transparency and visibility model.py recorded,
    and an isometric camera;
  * thumbnails/Thumbnail.png (512 x 512): the review renderer's 3/4 hero
    view (agent_kit/review.py), where FreeCAD and the Home grid read it;
  * AtechChat/chat.json (projects_store.pack_chat's format): one agent
    message - what the product is, which Atech modules sit on which ports,
    two things to ask next.

manifest.json lists, per project: title, file, sha256, bytes, example,
hardware, trust (the build ids and script hashes default_projects.py
records for each installed copy) and seconds. A failing or missing
example is skipped and reported. The last line is

    DEFAULT_PROJECTS=<n ok>/<n tried>

ATECH_DEFAULTS_ONLY=toy_car,rc_tank limits the run (tests).
An example whose build passes but whose own check fails (build.failures)
is skipped too, unless ATECH_DEFAULTS_ALLOW_FAILING=1.
ATECH_DEFAULTS_SABOTAGE (tests: each must make the checks fail):
    nohw      the hardware tags are stripped before the save
    nothumb   no thumbnail is embedded
    nochat    no chat is embedded
    noid      the AtechProjectId property is not written
"""
import ast
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import traceback
import uuid
import zipfile

sys.dont_write_bytecode = True

MANIFEST_VERSION = 3            # default_projects.py re-installs when this grows
THUMB_PX = 512
THUMB = "thumbnails/Thumbnail.png"
GUI_XML = "GuiDocument.xml"

#: (example key, display title). The order is the Home grid's order.
CURATED = (
    ("toy_car", "Toy car"),
    ("desk_robot", "Desk robot"),
    ("smart_speaker", "Smart speaker"),
    ("bedside_lamp", "Bedside lamp"),
    ("handheld_console", "Handheld console"),
    ("alarm_clock", "Alarm clock"),
    ("desk_fan", "Desk fan"),
    ("weather_station", "Weather station"),
    ("rc_tank", "RC tank"),
    ('smart_planter', 'Smart planter'),
    ('pet_feeder', 'Pet feeder'),
    ('video_doorbell', 'Video doorbell'),
    ('mini_arcade', 'Mini arcade'),
    ('music_box', 'Music box'),
    ('parking_sensor', 'Parking sensor'),
    ('desk_organizer', 'Desk organizer'),
    ('photo_frame', 'Photo frame'),
    ('metronome', 'Metronome'),
    ('macro_pad', 'Macro pad'),
    ('rover', 'Explorer rover'),
    ('air_monitor', 'Air monitor'),
    ('motion_light', 'Motion night light'),
    ('arm_dock', 'Robot arm dock'),
    ('balance_bot', 'Balance bot'),
    ('sesame_atech', 'Sesame walker'),
)
#: R820: the starter projects - small, simple starting points (Home's
#: "Start simple" row), built and checked like the products above but never
#: copied into the user's projects folder; manifest "kind": "starter". A
#: starter needs the tagged board but no module (the first one shows the
#: board alone). Their scripts live in agent_kit/starters/ (beside
#: examples/), NOT in examples/: the agent's workspace gets examples/ to
#: fork products from, and a plain box round the board is not one.
STARTERS = (
    ("starter_board", "Just the board"),
    ("starter_case", "Board in a case"),
    ("starter_wheels", "Two-wheel base"),
)
TITLES = dict(CURATED + STARTERS)
STARTER_KEYS = frozenset(k for k, _t in STARTERS)

#: What each product is (one sentence) and two things to ask next.
BLURBS = {
    "toy_car": ("A chunky toy 4x4 built around the Atech board: four DC "
                "motors, one in every wheel; the headlights and a "
                "distance sensor sit in the nose.",
                ["Make the wheels bigger", "Turn it into a pickup truck "
                 "with an open bed"]),
    "desk_robot": ("A little desk robot whose face is a screen, with a "
                   "speaker and a microphone to talk and listen and a "
                   "button on its head.",
                   ["Give it a wider head with antenna ears",
                    "Make the body shorter and rounder"]),
    "smart_speaker": ("A round smart speaker: a revolved puck with a light "
                      "ring, two buttons on top, a speaker and a "
                      "microphone inside.",
                      ["Make it taller, like a cylinder",
                       "Add a fabric grille pattern around the side"]),
    "bedside_lamp": ("A turned column bedside lamp with a frosted globe, "
                     "three lights inside and a touch button on the "
                     "base.",
                     ["Make the globe bigger", "Give the column a "
                      "fluted pattern"]),
    "handheld_console": ("A landscape handheld game console with sculpted "
                         "grips, one big screen, a D-pad and A / B "
                         "buttons.",
                         ["Make the grips deeper",
                          "Add shoulder buttons on top"]),
    "alarm_clock": ("A clock radio that leans back on a wedge foot: a big "
                    "screen face, a speaker, a snooze bar and keys on "
                    "top.",
                    ["Make the snooze bar wider",
                     "Give it rounder corners and a softer look"]),
    "desk_fan": ("A small desk fan: a guarded fan head on a stem, driven "
                 "by a DC motor, with a button and a light on its long "
                 "foot.",
                 ["Make the fan head bigger", "Give it five blades "
                  "instead of the current set"]),
    "weather_station": ("A weather station: a display slab on a wedge "
                        "foot, with a louvred hut on top for the "
                        "temperature / humidity sensor.",
                        ["Make the screen bigger",
                         "Add more louvres to the hut"]),
    "rc_tank": ("A tracked RC tank around the Atech board: two DC motors "
                "drive the tracks, lights and a distance sensor look "
                "ahead from the hull.",
                ["Make the turret bigger", "Make the tracks wider"]),
    'smart_planter': ('A smart desk planter: a soft-backed pot whose flat front shows the soil and air readout, a temperature / humidity sensor behind a vent and a status glow, with a terracotta inner pot standing in a drip tray.',
        ['Make the pot taller and narrower', 'Give the back rounder corners']),
    'pet_feeder': ('A countertop pet feeder: a hopper bin with a window and a hinged lid on a base unit whose motor turns a six-pocket rotor, dropping each portion down a curved spout into the bowl, with a FEED key, a status light and the schedule on the screen.',
        ['Make the hopper taller for more food', 'Give it a bigger bowl']),
    'video_doorbell': ('A video doorbell on a wall plate: a big round button in a frosted glow ring, a distance sensor and a microphone behind a smoked visor, a speaker grille up top.',
        ['Make the button ring bigger', 'Give the slab a slimmer, rounder shape']),
    'mini_arcade': ('A tabletop arcade cabinet: a spinner and two big buttons on the deck, a screen leaning back under a speaker grille, a lettered marquee and side art in a black border.',
        ['Lean the screen back further', 'Make the marquee taller and add more side art']),
    'music_box': ('A walnut-look music box with a lid line and brass hinges: a domed brass speaker grille, a frosted lit LED window, a knurled knob on a glowing ring and a brass key on the lid.',
        ['Make the lid taller with a curved top', 'Turn the grille into a fabric panel across the front']),
    'parking_sensor': ('A wall-mounted garage parking assistant: a distance sensor ranges the bumper, a red / amber / green traffic light with hooded lenses and a screen show how close the car is, on a sign plate with a blue P.',
        ['Make the traffic lights bigger and round the pod', 'Add a second screen that shows STOP']),
    'desk_organizer': ('A smart desk organizer on one tray: a display block with a screen for the time and temperature, a temperature / humidity sensor behind a vent and a key, three pen cups of different heights and a phone dock with a cable channel.',
        ['Make the pen cups taller', 'Add a fourth cup for scissors']),
    'photo_frame': ('A 5 x 7 wood photo frame round a small portrait screen in a bevelled mat, leaning back on a fold-out kickstand, with a key in the bottom rail, a backlight glowing on the wall behind and an orientation sensor inside.',
        ['Make the moulding wider', 'Give the frame rounder corners']),
    'metronome': ('A classic pyramid metronome: a tempo dial in a brass-rimmed pod, a click speaker, a BPM screen and a beat light behind one smoked lens, and a big brass tap key near the top.',
        ['Make it taller and slimmer', 'Give the tap key a bigger brass cap']),
    'macro_pad': ('A stream-deck style macro pad on a low wedge: two big keys under a label screen, a frosted status strip and a volume dial in its own crown.',
        ['Make the keys bigger', 'Give the dial crown a brighter metal rim']),
    'rover': ('A 4WD explorer rover: four motor-driven block-tread wheels under flared fenders, a stepped orange hull with a ToF eye and a headlight in the nose, a caged amber beacon, a solar panel, a camera mast and a roll bar with an antenna.',
        ['Make the wheels bigger', 'Give it a taller camera mast']),
    'air_monitor': ('A desk air-quality monitor: a soft slab leaning back in a wedge plinth, the CO2 and temperature / humidity sensors in a walled-off chamber that breathes through a slotted vent panel and top exhaust slots, beside a smoked readout, a frosted status light and a MODE key.',
        ['Make the vent panel wider with more slots', 'Lean the face back further on a taller plinth']),
    'motion_light': ('A motion-sensing wall night light: an arched pebble whose big frosted moon glows from four LED grids, with a black PIR eye (an open window under a little visor) watching the hallway and a mode key beside it.',
        ['Make the moon bigger and the pebble rounder', 'Add a speaker grille for a soft chime']),
    'arm_dock': ('A heavy desk dock for an SO-101 robot arm: a sloped control deck with a joint-angle screen, REC / PLAY keys and a jog dial, and a raised podium with a brushed bolt-on arm plate, its servo cable leaving through a rubber grommet.',
        ['Make the arm podium longer', 'Make the podium taller']),
    'sesame_atech': ('Sesame, the open-source walking robot, refitted for Atech: its own frame, legs and eight servos unchanged, and a new deck and lid that carry the Atech board over the legs, with the screen as its face, an IMU for heading and USB-C at the back.',
        ['Make the lid taller with a carry handle', 'Give the face a smoked visor and a bezel']),
    "starter_board": ("The Atech board lying flat in a printed tray, nothing "
                      "on it yet: the place to start your own design.",
                      ["Add a button and a light", "Put it in a case with a "
                       "lid"]),
    "starter_case": ("The Atech board lying flat in a simple two-part "
                   "case, a base and a rounded cover held by four screws, "
                   "with a button and a light under openings in the top.",
                   ["Add a speaker beside the light", "Make the case "
                    "taller with rounder corners"]),
    "starter_wheels": ("A simple rolling base: the Atech board flat on a "
                       "printed deck, two DC motors driving two wheels and "
                       "a skid at the back.",
                       ["Add a distance sensor at the front", "Make the "
                        "wheels bigger"]),
    'balance_bot': ('A two-wheeled self-balancing robot: a tall white body between big block-tread wheels, the orientation sensor at axle height on its centre line, a screen face with a glowing status eye, a START key, a carry handle and a parking foot so it rests upright.',
        ['Make the wheels bigger', 'Give the head a wider face window']),
}

#: Home's card subtitle per project (manifest "summary").
SUMMARIES = {
    "toy_car": "A chunky 4x4 with driven wheels and lights.",
    "desk_robot": "A little robot whose face is a screen.",
    "smart_speaker": "A round speaker with a light ring and buttons.",
    "bedside_lamp": "A turned column lamp with a frosted globe.",
    "handheld_console": "A game console with grips and a big screen.",
    "alarm_clock": "A clock radio leaning back on a wedge foot.",
    "desk_fan": "A guarded fan head on a stem, motor-driven.",
    "weather_station": "A display slab with a louvred sensor hut.",
    "rc_tank": "A tracked tank with motors, lights and a sensor.",
    'smart_planter': 'A desk planter with a readout and an inner pot.',
    'pet_feeder': 'A hopper feeder with a rotary dispenser and a bowl.',
    'video_doorbell': 'A wall slab with a big ring button and a sensor visor.',
    'mini_arcade': 'A tabletop cabinet with a spinner, buttons and a marquee.',
    'music_box': 'A walnut music box with a knob and a lit window.',
    'parking_sensor': 'A wall traffic light that tells you when to stop.',
    'desk_organizer': 'A tray with pen cups, a phone dock and a display.',
    'photo_frame': 'A wood photo frame on a kickstand, a screen in its mat.',
    'metronome': 'A pyramid metronome with a dial, a screen and a tap key.',
    'macro_pad': 'A wedge keypad with big keys, a label screen and a dial.',
    'rover': 'A 4WD rover with a mast, beacon and solar panel.',
    'air_monitor': 'A leaning CO2 monitor with a vented sensor chamber.',
    'motion_light': 'A wall pebble night light with a frosted moon and PIR eye.',
    'arm_dock': 'A robot arm dock with a control deck and arm plate.',
    'balance_bot': 'A balance bot with a screen face on two big wheels.',
    'sesame_atech': 'The Sesame walking robot with an Atech board and screen.',
    "starter_board": "The Atech board in a tray, ready for your modules.",
    "starter_case": "The board in a screwed case, a button and a light.",
    "starter_wheels": "Two motor-driven wheels under the board.",
}

SAB = os.environ.get("ATECH_DEFAULTS_SABOTAGE", "")


def say(msg):
    sys.stdout.write("[defaults] %s\n" % msg)
    sys.stdout.flush()


# ------------------------------------------------------------------ args
def parse_args(argv):
    a = list(argv)
    if "--pass" in a:
        rest = a[a.index("--pass") + 1:]
    else:
        here = os.path.realpath(__file__)
        rest = [x for x in a[1:] if os.path.realpath(x) != here
                and not x.endswith(".py")][-2:]
    ex = os.environ.get("ATECH_DEFAULTS_EXAMPLES") or (rest[0] if rest else "")
    out = os.environ.get("ATECH_DEFAULTS_OUT") or (rest[1] if len(rest) > 1 else "")
    if not ex or not out:
        raise SystemExit("usage: freecadcmd make_default_projects.py --pass "
                         "<examples_dir> <out_dir>")
    return os.path.abspath(ex), os.path.abspath(out)


def addon_of(examples_dir):
    """<addon>/acadagent/agent_kit/examples -> <addon>."""
    env = os.environ.get("ATECH_ADDON_DIR")
    if env:
        return os.path.abspath(env)
    return os.path.normpath(os.path.join(examples_dir, "..", "..", ".."))


def starters_of(examples_dir):
    """<kit>/examples -> <kit>/starters (R820)."""
    return os.path.join(os.path.dirname(os.path.normpath(examples_dir)), "starters")


# ------------------------------------------------------------ the parts
def example_intent(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == "INTENT" for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def module_specs():
    try:
        import atech_modules as am
        return am.specs() or {}
    except Exception:                                   # noqa: BLE001
        return {}


def hardware_of(doc, specs=None):
    """[{module, name, ports, cabled, label}] of the seated Atech modules,
    plus the board first, read off the document's tags."""
    specs = module_specs() if specs is None else specs
    out = []
    for o in doc.Objects:
        role = getattr(o, "AtechRole", "") or ""
        if role == "board":
            out.insert(0, {"module": "board", "name": "Atech board",
                           "ports": [], "cabled": False, "label": o.Label})
        elif role == "module":
            mod = getattr(o, "AtechModule", "") or ""
            try:
                ports = sorted(int(n) for n in getattr(o, "AtechPorts", []) or [])
            except (TypeError, ValueError):
                ports = []
            out.append({
                "module": mod,
                "name": ((specs.get(mod) or {}).get("display_name") or mod),
                "ports": ports,
                "cabled": (getattr(o, "AtechJoint", "") or "") == "cable",
                "label": o.Label})
    return out


def _ports(ns):
    ns = [int(n) for n in ns]
    if not ns:
        return "no port"
    if len(ns) == 1:
        return "port %d" % ns[0]
    return "ports %s and %d" % (", ".join(str(n) for n in ns[:-1]), ns[-1])


def chat_text(key, title, hw):
    """The starter chat's one agent message."""
    what, asks = BLURBS.get(key, ("A %s built from real Atech modules."
                                  % title.lower(), ["Make it bigger",
                                                    "Change the colours"]))
    mods = [h for h in hw if h["module"] != "board"]
    kind = "a starter project" if key in STARTER_KEYS else "a default project"
    lines = ["**%s** - %s, built by the agent's own kit from "
             "real Atech hardware." % (title, kind), "", what, "",
             "Atech modules on the board:"]
    for h in mods:
        lines.append("- %s on %s%s" % (h["name"], _ports(h["ports"]),
                                       " (on a cable)" if h["cabled"] else ""))
    if not mods:
        lines.append("- none")
    lines += ["", "Try asking:"] + ['- "%s"' % a for a in asks]
    lines += ["", "Every part is in the design script; ask for a change and "
              "I rebuild and re-check it."]
    return "\n".join(lines)


def chat_members(pid, text):
    from acadagent import projects_store as ps
    snap = {"entries": [{"kind": "bubble", "role": "agent", "text": text}],
            "last_text": text}
    return ps.pack_chat(snap, ws=None, pid=pid)


# ------------------------------------------------- GuiDocument.xml + co
def _pack(rgb, alpha=1.0):
    """FreeCAD 1.1's packed colour: 0xRRGGBBAA, AA = opacity
    (MEASURED: the default LineColor 0.098/0.098/0.1 saves as 421075455 =
    0x19191AFF)."""
    r, g, b = (max(0, min(255, int(round(float(c) * 255)))) for c in rgb[:3])
    a = max(0, min(255, int(round(float(alpha) * 255))))
    return (r << 24) | (g << 16) | (b << 8) | a


def material_list(colors, transparency=0.0):
    """A ShapeAppearance member (App::PropertyMaterialList, version 3), the
    layout MEASURED from a file FreeCAD 1.1.3 saved: uint32 count, then per
    material ambient, diffuse, specular, emissive (uint32 LE, 0xRRGGBBAA),
    shininess, transparency (float32) and three empty strings (image,
    image path, uuid; uint32 length 0 each)."""
    out = [struct.pack("<I", len(colors))]
    for c in colors:
        alpha = 1.0 - float(transparency)
        out.append(struct.pack("<IIII", 0x555555FF, _pack(c, alpha),
                               0x888888FF, 0x000000FF))
        out.append(struct.pack("<ff", 0.9, float(transparency)))
        out.append(struct.pack("<III", 0, 0, 0))
    return b"".join(out)


def _xml(s):
    return (str(s).replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def iso_camera(doc):
    """An orthographic camera on FreeCAD's isometric view, fitted to the
    visible shapes."""
    import FreeCAD as App
    bb = None
    for o in doc.Objects:
        sh = getattr(o, "Shape", None)
        if not getattr(o, "Visibility", True) or sh is None or sh.isNull():
            m = getattr(o, "Mesh", None)
            if m is None or not getattr(o, "Visibility", True):
                continue
            b = m.BoundBox
        else:
            b = sh.BoundBox
        if not b.isValid():
            continue
        bb = App.BoundBox(b) if bb is None else bb.united(b)
    if bb is None:
        return None
    rot = App.Rotation(0.424708, 0.17592, 0.339645, 0.820473)   # FreeCAD's iso
    ax = rot.Axis
    diag = max(bb.DiagonalLength, 1.0)
    c = bb.Center
    d = rot.multVec(App.Vector(0, 0, 1))
    pos = c + d * (diag * 2)
    return ("OrthographicCamera {\n  viewportMapping ADJUST_CAMERA\n"
            "  position %.6g %.6g %.6g\n  orientation %.6g %.6g %.6g  %.6g\n"
            "  nearDistance %.6g\n  farDistance %.6g\n  aspectRatio 1\n"
            "  focalDistance %.6g\n  height %.6g\n\n}\n" % (
                pos.x, pos.y, pos.z, ax.x, ax.y, ax.z, rot.Angle,
                diag * 0.5, diag * 3.5, diag * 2, diag * 1.15))


def gui_members(doc, view):
    """{member: bytes}: GuiDocument.xml and its ShapeAppearance lists."""
    files = {}
    vps = []
    for i, o in enumerate(doc.Objects):
        rec = view.get(o.Name) or {}
        vis = bool(getattr(o, "Visibility", True))
        trans = rec.get("Transparency", 0) or 0
        try:
            trans = max(0, min(100, int(trans)))
        except (TypeError, ValueError):
            trans = 0
        cols = None
        dif = rec.get("DiffuseColor")
        if isinstance(dif, (list, tuple)) and dif and \
                isinstance(dif[0], (list, tuple)):
            cols = [tuple(c) for c in dif]
        elif rec.get("ShapeColor") is not None:
            cols = [tuple(rec["ShapeColor"])]
        else:
            role = getattr(o, "AtechRole", "") or ""
            if role == "board":
                cols = [(0.16, 0.17, 0.20)]
            elif role == "module":
                cols = [(0.30, 0.31, 0.34)]
        props = ['                <Property name="Visibility" '
                 'type="App::PropertyBool" status="1">\n'
                 '                    <Bool value="%s"/>\n'
                 '                </Property>' % ("true" if vis else "false")]
        if cols:
            fn = "ShapeAppearance%d" % (i + 1) if i else "ShapeAppearance"
            files[fn] = material_list(cols, trans / 100.0)
            props.insert(0, '                <Property name="ShapeAppearance" '
                         'type="App::PropertyMaterialList" status="1">\n'
                         '                    <MaterialList file="%s" '
                         'version="3"/>\n                </Property>' % fn)
            props.insert(1, '                <Property name="Transparency" '
                         'type="App::PropertyPercent" status="1">\n'
                         '                    <Integer value="%d"/>\n'
                         '                </Property>' % trans)
        vps.append('        <ViewProvider name="%s" expanded="0" '
                   'treeRank="-1">\n            <Properties Count="%d" '
                   'TransientCount="0">\n%s\n            </Properties>\n'
                   '        </ViewProvider>' % (_xml(o.Name), len(props),
                                                 "\n".join(props)))
    cam = iso_camera(doc)
    xml = ("<?xml version='1.0' encoding='utf-8'?>\n"
           '<Document SchemaVersion="1" HasExpansion="1">\n    <Expand />\n'
           '    <ViewProviderData Count="%d">\n%s\n    </ViewProviderData>\n'
           '%s</Document>\n' % (len(vps), "\n".join(vps),
                                '    <Camera settings="%s"/>\n'
                                % _xml(cam).replace("\n", "&#10;")
                                if cam else ""))
    files[GUI_XML] = xml.encode("utf-8")
    return files


# --------------------------------------------------------------- render
def review_items(review, doc, ends, view):
    """The objects the hero view draws, coloured by check.py's rule (as
    tests/eval/fc_build.review_items): the recorded colour, else the Atech
    role colour, else Studio's palette order."""
    items, free = [], 0
    bodies = [o for o in ends if o.TypeId != "Mesh::Feature"
              and getattr(o, "Shape", None) is not None
              and not o.Shape.isNull() and getattr(o, "Visibility", True)]
    for o in bodies:
        rec = view.get(o.Name) or {}
        col = rec.get("ShapeColor")
        dif = rec.get("DiffuseColor")
        if col is None and isinstance(dif, (list, tuple)) and dif:
            col = dif[0] if isinstance(dif[0], (list, tuple)) else dif
        role = getattr(o, "AtechRole", None)
        kind = "body"
        if getattr(o, "AtechCableModule", None):
            kind, col = "cable", col or review.CABLE
        elif role:
            kind = "board" if role == "board" else "module"
            col = col or (review.BOARD if role == "board" else review.MODULE)
        if col is None:
            col = review.PALETTE[free % len(review.PALETTE)] \
                if len(bodies) > 1 else review.DEFAULT
            free += 1
        items.append({"label": o.Label, "shape": o.Shape,
                      "color": tuple(float(c) for c in col)[:3],
                      "kind": kind, "problem": False})
    for o in doc.Objects:
        role = getattr(o, "AtechRole", None)
        if o.TypeId == "Mesh::Feature" and role:
            items.append({"label": o.Label, "mesh": o.Mesh,
                          "kind": "board" if role == "board" else "module",
                          "color": review.BOARD if role == "board"
                          else review.MODULE, "problem": False})
    return items


def hero_png(items, path, px=THUMB_PX):
    """The review renderer's 3/4 hero view alone, px x px, as PNG."""
    import numpy as np
    import review
    from PIL import Image
    why = review.available()
    if why:
        raise RuntimeError(why)
    scene = review.scene_from(items)
    if scene is None:
        raise RuntimeError("nothing to draw")
    shadow = review.ShadowMap(scene, review.KEY)
    diag = float(np.linalg.norm(scene["max"] - scene["min"]))
    ctr = (scene["min"] + scene["max"]) / 2
    _name, v, up, persp = review.HERO
    cam = review.camera(v, up, ctr, diag, persp)
    img, _scale = review.render_view(scene, cam, px, px, shadow, ss=2,
                                     margin=0.06)
    Image.fromarray((np.clip(img, 0, 1) * 255).astype("uint8")).save(path)
    return path


# ---------------------------------------------------------------- build
def _capture_view(build, seen):
    """build.apply hands the recorded ViewObject props only to
    build._colour (a no-op headless): wrap it so they are kept. The same
    wrap tests/eval/fc_build.py uses; production code is not changed."""
    orig = getattr(build._colour, "_defaults_orig", build._colour)

    def _colour(ends, view):
        seen.clear()
        seen.update(view or {})
        return orig(ends, view)
    _colour._defaults_orig = orig
    build._colour = _colour


#: What the shipped files must never carry (verify_tree.py's personal-data
#: row scans the bundle, but only the raw, compressed bytes).
PRIVATE = re.compile(rb"/home/(?!runner/)[A-Za-z0-9._-]+/|/Users/[A-Za-z0-9._-]+/"
                     rb"|/private/(?:tmp|var)/|/tmp/claude-|@gmail\.com")


def private_paths(path):
    """'member: text' of the first build-machine path inside the zip, else
    ''. Every member is read decompressed."""
    extra = [os.path.expanduser("~").encode()] if os.path.expanduser("~") \
        not in ("", "/") else []
    with zipfile.ZipFile(path) as zf:
        for n in zf.namelist():
            b = zf.read(n)
            m = PRIVATE.search(b)
            if m is None:
                m = next((re.search(re.escape(e), b) for e in extra
                          if len(e) > 5 and e in b), None)
            if m is not None:
                return "%s: %r" % (n, b[max(0, m.start() - 20):m.end() + 40])
    return ""


def append_members(path, members):
    with zipfile.ZipFile(path) as zf:
        have = set(zf.namelist())
    clash = have & set(members)
    if clash:
        from acadagent import projects_store as ps
        ps._rewrite_zip(path, lambda n, d: None if n in clash else d)
    with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def build_one(key, title, examples_dir, out_dir, work):
    import FreeCAD as App
    from acadagent import build, projects_store as ps
    import review                                        # noqa: F401 (kit)
    t0 = time.time()
    src = os.path.join(starters_of(examples_dir) if key in STARTER_KEYS
                       else examples_dir, key + ".py")
    if not os.path.isfile(src):
        raise FileNotFoundError("%s/%s.py is missing" % (
            "starters" if key in STARTER_KEYS else "examples", key))
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    doc = App.newDocument(re.sub(r"\W", "_", title) or "Project")
    doc.Label = title
    App.setActiveDocument(doc.Name)
    ws = os.path.join(work, key)
    shutil.rmtree(ws, ignore_errors=True)
    os.makedirs(ws)
    shutil.copyfile(src, os.path.join(ws, build.SCRIPT))
    intent = example_intent(src)
    if intent is not None:
        with open(os.path.join(ws, build.INTENT), "w", encoding="utf-8") as fh:
            json.dump(intent, fh)
    build.prepare_workspace(ws, reset_intent=False, doc=doc)
    seen = {}
    _capture_view(build, seen)
    res = build.apply(ws, [build.SCRIPT],
                      previous={"uid": build._doc_key(doc)})
    t_build = time.time() - t0
    if res is None:
        raise RuntimeError("nothing to build")
    if not res.ok:
        raise RuntimeError("build failed: %s" % (res.error or "")[-600:])
    fails = build.failures(res)
    if fails and not os.environ.get("ATECH_DEFAULTS_ALLOW_FAILING"):
        # A default project must open as a passing design: one that fails
        # its own check would greet the user with "the build still fails".
        raise RuntimeError("its own check fails: %s" % " ".join(
            str(fails).split())[:300])
    hw = hardware_of(doc)
    starter = key in STARTER_KEYS
    if not any(h["module"] == "board" for h in hw) or \
            (len(hw) < 2 and not starter):
        raise RuntimeError("no tagged Atech board + modules in the document")
    scripted = [o for o in doc.Objects if getattr(o, "AtechAgentScript", "")]
    if not scripted:
        raise RuntimeError("no part carries its AtechAgentScript")
    trust = {}
    for o in doc.Objects:
        if getattr(o, "AtechAgentBuilt", False) and \
                getattr(o, "AtechAgentBuildId", ""):
            trust.setdefault(o.AtechAgentBuildId, {
                "sha": hashlib.sha256((o.AtechAgentScript or "").encode(
                    "utf-8", "replace")).hexdigest(),
                "n": int(getattr(o, "AtechAgentBuild", 0) or 0)})
    # hero thumbnail
    t1 = time.time()
    ends = [o for o in doc.Objects if o.Name in set(res.created)] or \
        list(doc.Objects)
    ends = build._results(ends)
    thumb = os.path.join(ws, "thumb.png")
    hero_png(review_items(sys.modules["review"], doc, ends, seen), thumb)
    t_thumb = time.time() - t1
    # identity + save
    pid = str(uuid.uuid4())
    path = os.path.join(out_dir, title + ps.SUFFIX)
    if os.path.exists(path):
        os.remove(path)
    if SAB != "noid":
        ps._set_id(doc, pid)
        # AtechProjectFile exists (so projects_store.rekey_file fills it in
        # on install) but names no path of the build machine.
        ps._set_prop(doc, ps.FILE_PROP, "")
    if SAB == "nohw":
        for o in doc.Objects:
            if getattr(o, "AtechRole", ""):
                o.AtechRole = ""
    doc.saveAs(path)
    members = gui_members(doc, seen)
    if SAB != "nothumb":
        with open(thumb, "rb") as fh:
            members[THUMB] = fh.read()
    if SAB != "nochat":
        members.update(chat_members(pid, chat_text(key, title, hw)))
    append_members(path, members)
    App.closeDocument(doc.Name)
    leak = private_paths(path)
    if leak:
        raise RuntimeError("the file names a path of this machine: %s" % leak)
    return {"title": title, "file": os.path.basename(path), "example": key,
            "kind": "starter" if starter else "product",
            "summary": SUMMARIES.get(key, ""),
            "id": pid, "sha256": sha256_file(path),
            "bytes": os.path.getsize(path), "hardware": hw, "trust": trust,
            "parts": len(scripted), "check_failures": fails or "",
            "seconds": round(time.time() - t0, 1),
            "build_seconds": round(t_build, 1),
            "thumb_seconds": round(t_thumb, 1)}


def main(argv):
    examples_dir, out_dir = parse_args(argv)
    addon = addon_of(examples_dir)
    for p in (addon, os.path.join(addon, "acadagent", "agent_kit")):
        if p not in sys.path:
            sys.path.insert(0, p)
    from acadagent import build
    # The build's own bookkeeping (trust store, chat folders) goes to a
    # scratch folder, never the user's profile.
    work = tempfile.mkdtemp(prefix="atech-defaults-")
    build._trust_path = lambda: os.path.join(work, "trusted_builds.json")
    if not build.library_available():
        say("the Atech module library is not available (ATECH_ARTIFACTS?)")
    os.makedirs(out_dir, exist_ok=True)
    only = [k for k in (os.environ.get("ATECH_DEFAULTS_ONLY") or "").split(",")
            if k.strip()]
    wanted = [(k, t) for k, t in CURATED + STARTERS if not only or k in only]
    done, skipped = [], []
    t_all = time.time()
    try:
        for key, title in wanted:
            t0 = time.time()
            try:
                rec = build_one(key, title, examples_dir, out_dir, work)
                done.append(rec)
                say("OK   %-17s %6.1fs  %7.1f KB  %d modules  %s" % (
                    title, rec["seconds"], rec["bytes"] / 1024.0,
                    len(rec["hardware"]) - 1, rec["file"]))
            except Exception as exc:                    # noqa: BLE001
                err = "%s: %s" % (type(exc).__name__, exc)
                for d, tag in ((out_dir, "<out>"), (examples_dir, "<examples>"),
                               (addon, "<addon>"), (work, "<work>"),
                               (os.path.expanduser("~"), "~")):
                    if d and len(d) > 1:
                        err = err.replace(d, tag)
                skipped.append({"example": key, "title": title,
                                "error": err,
                                "seconds": round(time.time() - t0, 1)})
                say("SKIP %-17s %6.1fs  %s" % (title, time.time() - t0,
                                                skipped[-1]["error"][:300]))
                if os.environ.get("ATECH_DEFAULTS_TRACE"):
                    traceback.print_exc()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    manifest = {"version": MANIFEST_VERSION, "generated": int(time.time()),
                "projects": done, "skipped": skipped,
                "seconds": round(time.time() - t_all, 1)}
    with open(os.path.join(out_dir, "manifest.json"), "w",
              encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)
    print("DEFAULT_PROJECTS=%d/%d" % (len(done), len(wanted)))
    sys.stdout.flush()
    return 0 if done else 1


# freecadcmd runs a script under its file name, not "__main__" (MEASURED).
if __name__ in ("__main__", "make_default_projects"):
    main(sys.argv)
