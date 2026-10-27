"""R270-R279: the product examples are forkable, showcase-grade templates.

    cd addon/AcadAgent/tests && python3 -m unittest test_kit_examples_r270

Source checks (no FreeCAD):
  R270 every product example has the three section markers, in order:
       PARAMETERS, STAGE A (hardware, shell, openings, fasteners), STAGE B
       (details); its docstring says 'fork this file for a <archetype>;
       change PARAMETERS and the outlines' (WS1's prompt depends on it)
       and names its archetype on an ARCHETYPE: line; it prints TIME ticks
       and lists REVIEW_CLOSEUPS (1-4 labels it builds).
  R271 ATECH_PRODUCTS.md's ARCHETYPE TABLE names every example on disk
       that places Atech hardware (examples/*.py importing atech_ports).
  R272 the reference has the handheld and lamp recipes, the 'cable for
       ergonomics' and 'robust body recipes' sections; TRAPS.md has the
       round-1 traps.
  Each source gate has a sabotage test (the gate fails on a copy with the
  thing removed).
FreeCAD-backed (skip without freecadcmd - set ATECH_FREECADCMD):
  R275 ./check on every product example, as the agent's workspace runs it
       (model.py, intent.json from INTENT, the eval prompt as the turn's
       request): CHECK PASS in under 180 s (ATECH_EXAMPLE_LIMIT_S), no
       module sealed, no WARNING about an opening, cover, fastener pilot
       or clip channel.
  R276 sabotage: the screen window made opaque (the robot's visor, the
       handheld's cover glass) - the same ./check FAILS, naming the
       sealed screen.
"""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)

from acadagent import sandbox  # noqa: E402

KIT = sandbox.KIT_DIR
EXAMPLES = os.path.join(KIT, "examples")
REFERENCE = os.path.join(KIT, "reference", "ATECH_PRODUCTS.md")
TRAPS = os.path.join(EXAMPLES, "TRAPS.md")
PROJECTS = os.path.normpath(os.path.join(ADDON, "..", "..", "projects"))
FC = sandbox.find_freecadcmd()

# example -> (archetype label (build.ARCHETYPES), the eval prompt, the
# screen-window part when it has a screen)
PRODUCTS = {
    "toy_car.py": ("vehicle", "a toy car", None),
    "desk_robot.py": ("robot or character", "a little desk robot", "Face_Plate"),
    "smart_speaker.py": ("speaker", "a smart speaker", None),
    "handheld_console.py": ("handheld", "a handheld game console", "Cover_Glass"),
    "bedside_lamp.py": ("lamp", "a bedside lamp", None),
    # R410 / R411: the seeds for two archetypes round 1 never built
    "alarm_clock.py": ("clock", "an alarm clock", "Lens"),
    "desk_fan.py": ("fan", "a small desk fan", None),
    # R412 / R413
    "weather_station.py": ("weather station", "a weather station", "Lens"),
    "rc_tank.py": ("vehicle", "an RC tank", None),
    # R802: the ten starter examples (2026-10-27)
    'smart_planter.py': ('planter', 'a smart desk planter', 'Lens'),
    'pet_feeder.py': ('feeder', 'a countertop pet feeder', 'Lens'),
    'video_doorbell.py': ('doorbell', 'a video doorbell', None),
    'mini_arcade.py': ('arcade', 'a mini arcade cabinet', 'Glass'),
    'music_box.py': ('music box', 'a music box', None),
    'parking_sensor.py': ('parking sign', 'a garage parking assistant', 'Screen_Lens'),
    'desk_organizer.py': ('organizer', 'a smart desk organizer', 'Lens'),
    'photo_frame.py': ('frame', 'a smart photo frame', None),
    'metronome.py': ('metronome', 'a digital metronome', 'Lens'),
    'macro_pad.py': ('macro pad', 'a macro pad', 'Label_Window'),
    # R803: the five Atech-hardware examples (2026-10-27)
    'rover.py': ('vehicle', 'a 4WD explorer rover', None),
    'air_monitor.py': ('air monitor', 'a room air quality monitor', None),
    'motion_light.py': ('motion light', 'a motion-sensing night light', None),
    'arm_dock.py': ('robot arm dock', 'a robot arm dock', None),
    'balance_bot.py': ('balancing robot', 'a self-balancing robot', None),
}
MARKERS = ("# === PARAMETERS (restyle here) ===",
           "# === STAGE A: hardware, shell, every working-face opening, fasteners ===",
           "# === STAGE B: details ===")
FORK_RE = r"fork this file for an? [^;]{1,200}; change PARAMETERS and the outlines"
# R500: results over speed - the bound is the sandbox's quality timeout
LIMIT_S = float(os.environ.get("ATECH_EXAMPLE_LIMIT_S", "180"))
CHECK_TIMEOUT_S = 180            # quality mode's build / ./check timeout
TIMINGS = {}
FORBIDDEN_WARNINGS = ("sealed", "OPEN", "pilot", "channel", "limited to", "left out",
                      "cover", "only touches", "falls off")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def literal(src, name):
    """The module-level `name = <literal>` of a source, or None."""
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name
                                                for t in node.targets):
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


# ------------------------------------------------------------ the gates
def section_problems(src):
    """R270: [] when the three markers are there, once each, in order."""
    bad = []
    at = []
    for m in MARKERS:
        n = src.count(m)
        if n != 1:
            bad.append("%r appears %d times" % (m, n))
        at.append(src.find(m))
    if not bad and at != sorted(at):
        bad.append("the markers are out of order")
    return bad


def docstring_problems(src, archetype):
    """R270: the docstring is 'Example: "..."', says how to fork it, and
    names its archetype."""
    doc = ast.get_docstring(ast.parse(src)) or ""
    bad = []
    if not doc.startswith('Example: "'):
        bad.append("docstring does not start 'Example: \"'")
    if not re.search(FORK_RE, doc):
        bad.append("no 'fork this file for a <archetype>; change PARAMETERS and the outlines'")
    m = re.search(r"^ARCHETYPE:\s*(.+?)\s*$", doc, re.M)
    if not m or m.group(1) != archetype:
        bad.append("ARCHETYPE: line is %r, want %r" % (m and m.group(1), archetype))
    return bad


def staging_problems(src):
    """R270: TIME ticks printed, REVIEW_CLOSEUPS a list of 1-4 labels the
    file builds, an INTENT literal."""
    bad = []
    if 'print("TIME ' not in src or src.count("tick(") < 3:
        bad.append("no TIME ticks")
    closeups = literal(src, "REVIEW_CLOSEUPS")
    if not isinstance(closeups, list) or not 1 <= len(closeups) <= 4:
        bad.append("REVIEW_CLOSEUPS is not a list of 1-4 labels")
    else:
        for lab in closeups:
            if '"%s"' % lab not in src.split("REVIEW_CLOSEUPS", 1)[1]:
                bad.append("REVIEW_CLOSEUPS names %s, which the file never builds" % lab)
    if not isinstance(literal(src, "INTENT"), dict):
        bad.append("no INTENT literal")
    return bad


def archetype_table(text):
    """R271: the ARCHETYPE TABLE section of ATECH_PRODUCTS.md."""
    m = re.search(r"\n## 0A\. ARCHETYPE TABLE.*?(?=\n## )", text, re.S)
    return m.group(0) if m else ""


def hardware_examples(folder=EXAMPLES):
    """Every example on disk that places Atech hardware."""
    return sorted(n for n in os.listdir(folder) if n.endswith(".py")
                  and "import atech_ports" in read(os.path.join(folder, n)))


def table_problems(text, names):
    table = archetype_table(text)
    if not table:
        return ["no '## 0A. ARCHETYPE TABLE' section"]
    return ["the table does not name examples/%s" % n for n in names
            if "examples/%s" % n not in table]


class R270Sources(unittest.TestCase):
    """No FreeCAD: the files the agent forks are laid out to be forked."""

    def test_every_product_example_is_staged(self):
        for ex, (arch, _prompt, _win) in PRODUCTS.items():
            with self.subTest(example=ex):
                src = read(os.path.join(EXAMPLES, ex))
                self.assertEqual(section_problems(src), [])
                self.assertEqual(docstring_problems(src, arch), [])
                self.assertEqual(staging_problems(src), [])
                compile(src, ex, "exec")
                # real hardware, placed with the library
                self.assertIn("import atech_ports as ap", src)
                self.assertIn('"usbc"', src)

    def test_parameters_drive_the_outlines(self):
        # the parameter block holds the restyle numbers: every example
        # defines a COLOURS map and at least one outline / size constant
        # there, and STAGE A uses them
        for ex in PRODUCTS:
            with self.subTest(example=ex):
                src = read(os.path.join(EXAMPLES, ex))
                params = src.split(MARKERS[0], 1)[1].split(MARKERS[1], 1)[0]
                stage_a = src.split(MARKERS[1], 1)[1]
                self.assertIn("COLOURS = {", params)
                names = re.findall(r"^([A-Z][A-Z0-9_]*)\s*(?:,\s*[A-Z][A-Z0-9_]*\s*)*=", params, re.M)
                self.assertGreaterEqual(len(names), 5, names)
                used = [n for n in names if re.search(r"\b%s\b" % n, stage_a)]
                self.assertGreaterEqual(len(used), 4, (names, used))

    def test_table_names_every_example(self):
        text = read(REFERENCE)
        names = hardware_examples()
        for ex in PRODUCTS:
            self.assertIn(ex, names)
        self.assertEqual(table_problems(text, names), [])
        # each product row also says where the hero element is
        table = archetype_table(text)
        for ex in PRODUCTS:
            row = next((ln for ln in table.splitlines() if "examples/%s" % ex in ln), "")
            self.assertGreaterEqual(row.count("|"), 8, row)

    def test_reference_sections(self):
        text = read(REFERENCE)
        for needle in ('examples/handheld_console.py, CHECK PASS', 'examples/bedside_lamp.py, CHECK PASS',
                       "## 9. Cable for ergonomics", "## 10. Robust body recipes", "cad.shell_body",
                       "FALL BACK"):
            self.assertIn(needle, text)
        self.assertNotIn("/private/tmp", text)

    def test_traps_round1(self):
        text = read(TRAPS)
        for needle in ("spline-on-spline", "split on a solid section", "cusp offset",
                       "fitted_after listing unbuilt parts", "screws list never added to the document"):
            self.assertIn(needle.lower(), text.lower())


class R270SourceSabotage(unittest.TestCase):
    """Every source gate fails on a copy with its subject removed."""

    def setUp(self):
        self.src = read(os.path.join(EXAMPLES, "handheld_console.py"))

    def test_missing_marker_is_caught(self):
        for m in MARKERS:
            with self.subTest(marker=m):
                self.assertTrue(section_problems(self.src.replace(m, "# details")))
        swapped = self.src.replace(MARKERS[1], "@@A@@").replace(MARKERS[2], MARKERS[1]).replace("@@A@@", MARKERS[2])
        self.assertTrue(section_problems(swapped))

    def test_docstring_without_fork_line_is_caught(self):
        bad = self.src.replace("change PARAMETERS and the outlines", "copy the patterns")
        self.assertTrue(docstring_problems(bad, "handheld"))
        self.assertTrue(docstring_problems(self.src, "lamp"))          # wrong archetype

    def test_staging_without_ticks_or_closeups_is_caught(self):
        self.assertTrue(staging_problems(self.src.replace('print("TIME ', 'print("T ')))
        self.assertTrue(staging_problems(self.src.replace("REVIEW_CLOSEUPS = [", "REVIEW_CLOSEUPS = ['Nope', ")))

    def test_table_missing_an_example_is_caught(self):
        text = read(REFERENCE)
        self.assertTrue(table_problems(text.replace("examples/bedside_lamp.py", "examples/x.py"),
                                       hardware_examples()))
        self.assertTrue(table_problems(text, hardware_examples() + ["new_product.py"]))
        self.assertTrue(table_problems(text.replace("## 0A. ARCHETYPE TABLE", "## 0A. Table"),
                                       hardware_examples()))


# ------------------------------------------------------------ FreeCAD builds
def build(example, request, extra_code=""):
    """./check on a fresh workspace holding the example as model.py, the
    request as the turn's message. Returns (result, output, wall s)."""
    ws = tempfile.mkdtemp(prefix="atech-r270-")
    try:
        src = read(os.path.join(EXAMPLES, example))
        with open(os.path.join(ws, "model.py"), "w", encoding="utf-8") as fh:
            fh.write(src + extra_code)
        with open(os.path.join(ws, "intent.json"), "w", encoding="utf-8") as fh:
            json.dump(literal(src, "INTENT"), fh)
        with open(os.path.join(ws, ".atech_turn.json"), "w", encoding="utf-8") as fh:
            json.dump({"fix": False, "request": request}, fh)
        env = dict(os.environ,
                   ATECH_CHECK_SCRIPT=os.path.join(ws, "model.py"),
                   ATECH_CHECK_PNG="",                    # the gate only
                   ATECH_CHECK_PATH=PROJECTS,
                   ATECH_CHECK_TIMEOUT=str(CHECK_TIMEOUT_S))
        t0 = time.time()
        p = subprocess.run([FC, os.path.join(KIT, "check.py")], env=env, capture_output=True,
                           text=True, timeout=1200, cwd=ws)
        wall = time.time() - t0
        out = p.stdout + p.stderr
        res = None
        for line in reversed(out.splitlines()):
            if line.startswith("ATECH_CHECK="):
                res = json.loads(line[len("ATECH_CHECK="):])
                break
        return res, out, wall
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def verdict(out):
    lines = [ln for ln in out.splitlines() if ln.startswith("CHECK ")]
    return lines[-1] if lines else ""


@unittest.skipIf(FC is None, "bundled freecadcmd not found (set ATECH_FREECADCMD)")
@unittest.skipUnless(os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")),
                     "Atech library (projects/atech_ports.py) not found")
class R270Builds(unittest.TestCase):
    """R275: every product example passes ./check, fast, nothing sealed."""

    def _check(self, ex):
        _arch, prompt, _win = PRODUCTS[ex]
        res, out, wall = build(ex, prompt)
        if res and "LibraryMissing" in (res.get("error") or ""):
            self.skipTest("library code without its data here")
        self.assertIsNotNone(res, out[-3000:])
        TIMINGS[ex] = {"model_s": res.get("run_seconds"), "check_s": round(wall, 1)}
        self.assertTrue(res["ok"], res.get("error"))
        self.assertEqual(verdict(out), "CHECK PASS",
                         "\n".join(ln for ln in out.splitlines()
                                   if ln.startswith(("PROBLEM", "CHECK")))[-3000:])
        for o in res["objects"]:
            self.assertTrue(o["valid"], o)
            self.assertEqual(o["solids"], 1, o)
        # nothing sealed: every module with a working face sees out
        rows = res.get("face_open") or []
        self.assertTrue(rows, "no OPEN rows")
        sealed = [r["label"] for r in rows if r.get("kind") and not r.get("open")]
        self.assertEqual(sealed, [])
        card = res.get("scorecard") or {}
        self.assertEqual(card.get("sealed") or [], [])
        # no WARNING about an opening, a cover, a fastener or a clip; the
        # wall probe's thin spots (a time-capped random sample) are listed
        bad = [w for w in res.get("warnings") or ()
               if any(k in w for k in FORBIDDEN_WARNINGS)]
        self.assertEqual(bad, [])
        TIMINGS[ex]["warnings"] = len(res.get("warnings") or ())
        self.assertLess(wall, LIMIT_S, "./check took %.1f s" % wall)
        return res

    def test_toy_car(self):
        self._check("toy_car.py")

    def test_desk_robot(self):
        res = self._check("desk_robot.py")
        labels = {o["label"] for o in res["objects"]}
        for want in ("Face_Plate", "Face_Bezel", "Neck_Collar", "Torso_Front", "Torso_Back"):
            self.assertIn(want, labels)
        # R270: the deep torso and the head as the hero, measured
        size = {o["label"]: o["size"] for o in res["objects"]}
        tf, tb = size["Torso_Front"], size["Torso_Back"]
        depth = max(o["bbox_max"][1] for o in res["objects"] if o["label"].startswith("Torso")) - \
            min(o["bbox_min"][1] for o in res["objects"] if o["label"].startswith("Torso"))
        self.assertGreaterEqual(depth / max(tf[0], tb[0]), 0.6)
        whole = res["whole_size"][2]
        head = size["Head_Front"][2]
        self.assertGreaterEqual(head / whole, 0.35)

    def test_smart_speaker(self):
        self._check("smart_speaker.py")

    def test_handheld_console(self):
        res = self._check("handheld_console.py")
        size = {o["label"]: o["size"] for o in res["objects"]}
        glass = size["Cover_Glass"]
        face = res["whole_size"]
        self.assertGreaterEqual(glass[0] * glass[1] / ((face[0] - 6) * (face[1] - 2)), 0.38)
        self.assertLess(face[2], 30.0)                       # under 30 mm where held

    def test_bedside_lamp(self):
        self._check("bedside_lamp.py")

    def test_alarm_clock(self):
        # R410: a landscape clock radio, its face tilted back, the display
        # (lens) at least half the front, a snooze key on a cabled button
        res = self._check("alarm_clock.py")
        labels = {o["label"] for o in res["objects"]}
        for want in ("Front", "Back", "Bezel", "Lens", "Snooze_Key", "Foot", "Grille_Trim"):
            self.assertIn(want, labels)
        size = res["whole_size"]
        self.assertGreaterEqual(size[0] / size[2], 1.4)          # landscape (tilted: z grows)
        arch = res.get("archetype") or {}
        self.assertEqual(arch.get("label"), "clock")
        self.assertGreaterEqual((arch.get("facts") or {}).get("screen_share", 0), 0.5)
        rows = {r["label"]: r for r in res.get("face_open") or []}
        self.assertTrue(rows.get("button_2", {}).get("open"), rows.get("button_2"))
        held = {r["module"]: r["held"] for r in res.get("holders") or []}
        self.assertTrue(held.get("button_2"), res.get("holders"))

    def test_weather_station(self):
        # R412: the sensor in its own louvred hut, above the slab, held
        res = self._check("weather_station.py")
        box = {o["label"]: (o["bbox_min"], o["bbox_max"]) for o in res["objects"]}
        for want in ("Hut", "Hut_Roof", "Bezel", "Lens", "Foot", "Front", "Back"):
            self.assertIn(want, box)
        self.assertGreater(box["Hut"][0][2], box["Front"][1][2] - 3.0)     # the hut stands over the slab
        held = {r["module"]: r["held"] for r in res.get("holders") or []}
        self.assertTrue(held.get("temp_humidity_13"), res.get("holders"))
        rows = {r["label"]: r for r in res.get("face_open") or []}
        self.assertTrue(rows.get("temp_humidity_13", {}).get("open"), rows.get("temp_humidity_13"))

    def test_rc_tank(self):
        # R413: two tracks the full length, a turret with a barrel
        res = self._check("rc_tank.py")
        labels = {o["label"] for o in res["objects"]}
        for want in ("Track_L", "Track_R", "Treads_L", "Treads_R", "Sprocket_L", "Idler_L",
                     "Road_Wheels_L", "Turret", "Turret_Ring", "Hull_Upper", "Hull_Lower"):
            self.assertIn(want, labels)
        facts = (res.get("archetype") or {}).get("facts") or {}
        self.assertGreaterEqual(facts.get("length_ratio", 0), 1.5)
        held = {r["module"]: r["held"] for r in res.get("holders") or []}
        for m in ("distance_sensor_8", "light_6", "light_14"):
            self.assertTrue(held.get(m), res.get("holders"))

    def test_desk_fan(self):
        # R411: a guarded rotor on a stem, the motor cabled up it and held
        res = self._check("desk_fan.py")
        labels = {o["label"] for o in res["objects"]}
        for want in ("Rotor", "Guard_Front", "Guard_Rear", "Pod", "Stem", "Collar", "Base"):
            self.assertIn(want, labels)
        held = {r["module"]: r["held"] for r in res.get("holders") or []}
        self.assertTrue(held.get("dc_motor_7"), res.get("holders"))
        self.assertGreaterEqual(((res.get("archetype") or {}).get("facts") or {}).get("guard_share", 0), 0.5)
        size = {o["label"]: o["size"] for o in res["objects"]}
        g = size["Guard_Front"]
        whole = res["whole_size"]
        # the guard disc covers >= 60 % of the front (width x height)
        self.assertGreaterEqual(3.14159 * g[0] * g[2] / 4 / (whole[0] * whole[2]), 0.6)


@unittest.skipIf(FC is None, "bundled freecadcmd not found (set ATECH_FREECADCMD)")
@unittest.skipUnless(os.path.isfile(os.path.join(PROJECTS, "atech_ports.py")),
                     "Atech library (projects/atech_ports.py) not found")
class R270BuildSabotage(unittest.TestCase):
    """R276: an example with its screen window removed (made opaque)
    fails the same ./check - the gate can fail."""

    def _sabotage(self, ex, request):
        part = PRODUCTS[ex][2]
        res, out, _wall = build(ex, request, extra_code=(
            "\n_win = doc.getObject(%r)\n_win.ViewObject.Transparency = 0\n" % part))
        self.assertIsNotNone(res, out[-3000:])
        v = verdict(out)
        self.assertTrue(v.startswith("CHECK FAIL"), v)
        self.assertIn("screen", v)
        self.assertIn("sealed", v)

    def test_robot_without_its_visor_window(self):
        self._sabotage("desk_robot.py", "a little desk robot with a screen face")

    def test_handheld_without_its_window(self):
        self._sabotage("handheld_console.py", "a handheld game console with a screen")

    def test_clock_without_its_display_window(self):
        # R410: the smoked lens made opaque seals the screen behind it
        self._sabotage("alarm_clock.py", "an alarm clock with a screen")

    def _fails(self, ex, request, code, *words):
        res, out, _wall = build(ex, request, extra_code=code)
        self.assertIsNotNone(res, out[-3000:])
        v = verdict(out)
        self.assertTrue(v.startswith("CHECK FAIL"), v)
        for w in words:
            self.assertIn(w, v)

    def test_clock_without_its_snooze_holder(self):
        # R410: the cabled snooze button with its bracket cut away hangs on
        # its ribbon (R442 holder gate)
        self._fails("alarm_clock.py", "an alarm clock", (
            "\n_b = doc.getObject('Back')\n_m = ap.bbox(snz)\n"
            "_b.Shape = _b.Shape.cut(Part.makeBox(_m.XLength + 5, _m.YLength + 5, _m.ZLength + 3, "
            "V(_m.XMin - 2.5, _m.YMin - 2.5, _m.ZMin - 2.5)))\n"), "holder")

    def test_fan_with_a_closed_guard(self):
        # R411 / R504: the guard's openings filled by a solid disc that is
        # the front-most face (nothing of the rotor shows). The R440
        # archetype gates are never PROBLEMs since R500 (style, not
        # function) and NOTE lines since R600, so the check is not failed -
        # but the fan gate must SEE it: a guard share near 0 and the "guard
        # opening" NOTE (before R504 the
        # fan's forward foot made the whole solid guard read 91 % open)
        res, out, _wall = build("desk_fan.py", "a small desk fan", (
            "\ndoc.removeObject('Badge')\n_g = doc.getObject('Guard_Front')\n"
            "_g.Shape = cad.fuse_one(_g.Shape, ycyl(GUARD_R, gf_back, gf_face - 1.6))\n"))
        self.assertIsNotNone(res, out[-3000:])
        facts = (res.get("archetype") or {}).get("facts") or {}
        self.assertLess(facts.get("guard_share", 1.0), 0.2, facts)
        # R600: the miss is a NOTE line (a design note), never a WARNING
        self.assertTrue([n for n in res.get("notes") or ()
                         if n.startswith("ARCHETYPE ") and "guard opening" in n
                         and "a design note, not a gate" in n], res.get("notes"))
        self.assertFalse([w for w in res.get("warnings") or ()
                          if w.startswith("ARCHETYPE ")], res.get("warnings"))

    def test_weather_station_without_its_display_window(self):
        # R412: the smoked lens made opaque seals the screen
        self._sabotage("weather_station.py", "a weather station with a screen")

    def test_tank_with_its_glacis_closed(self):
        # R413: the ToF's aperture filled - the sensor is sealed
        self._fails("rc_tank.py", "an RC tank with a distance sensor", (
            "\n_u = doc.getObject('Hull_Upper')\n_e = ap.bbox(eye)\n"
            "_cx, _cz = (_e.XMin + _e.XMax) / 2, (_e.ZMin + _e.ZMax) / 2\n"
            "_u.Shape = cad.fuse_one(_u.Shape, Part.makeBox(16, 11, 12, "
            "V(_cx - 8, _e.YMin - 12, _cz - 6)))\n"), "sealed")

    def test_fan_with_its_glow_lens_opaque(self):
        # R411: the light under a solid cap is sealed
        self._fails("desk_fan.py", "a small desk fan with a night light",
                    "\ndoc.getObject('Glow_Lens').ViewObject.Transparency = 0\n", "light", "sealed")


def tearDownModule():
    if TIMINGS:
        print("\nR270_TIMINGS=" + json.dumps(TIMINGS, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
