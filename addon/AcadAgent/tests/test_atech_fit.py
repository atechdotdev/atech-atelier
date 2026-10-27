"""T1: agent_kit/atech_fit.py, the one source of the Atech print-fit numbers.

Runs under system python (atech_fit imports no FreeCAD):
    cd addon/AcadAgent/tests && python3 -m unittest test_atech_fit
"""
import copy
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(os.path.dirname(HERE), "acadagent", "agent_kit")
sys.path.insert(0, KIT)

import atech_fit  # noqa: E402

# Placeholders in the plan's rule texts R6-R12 and procedure 4.1
# (PLAN_FINAL.md section 3.4 and 4.1), copied here so the test does not
# depend on the scratch plan file.
PLAN_PLACEHOLDERS = (
    # R7
    "stop", "slide",
    # R9
    "usbc_open", "usbc_r", "usbc_keepout",
    # R11
    "ribbon_gap", "ribbon_channel", "fold_allow", "ribbon_bend_r",
    "ribbon_clamp",
    # R12
    "layer", "hole_z", "pin_min", "material",
    # 4.1 steps 3-11
    "corner_keepout", "wall", "wall_min", "air_speaker", "fence", "rib",
    "fence_top_mod", "pad_min", "preload_tip", "preload", "backlash_max",
    "lip_loose", "boss_od_rule", "snap_strain",
)

# R7 / R9 / R11 / R12 sentences with their placeholders, verbatim from the
# plan, to prove they format.
PLAN_SNIPPETS = (
    "Something printed must stand in front of every seated module's outboard "
    "face, {stop} mm off it. A cabled module sits in a pocket with {slide} mm "
    "clearance.",
    "It cuts a {usbc_open} opening rounded r {usbc_r} through the full wall. "
    "It keeps {usbc_keepout} mm clear outward.",
    "at least {ribbon_gap} mm from every part, in a channel {ribbon_channel} "
    "mm wide. allowing {fold_allow} mm per fold, no bend tighter than "
    "{ribbon_bend_r} mm. clamp rib {ribbon_clamp} mm over the ribbon",
    "Gaps are 0 or at least {layer} mm. +{hole_z} mm in Z. No horizontal pin "
    "thinner than {pin_min} mm. Material is {material}.",
)

# Board and module numbers the FIT table must carry, each with the line of
# the measurement inventory it comes from (scratchpad fitplan/
# MEASUREMENTS.md table A, and mods.out for the modules).
MEASURED = {
    # "| Outline (carrier frame) | 59.975 x 119.975, X 0.013-59.988,
    #  Z 0.013-119.988 | GLB frame + STL bbox | H |"
    "board_x": (0.013, 59.988),
    "board_z": (0.013, 119.988),
    # "| Total thickness | 7.00 (Y -2.50 to +4.50) in the GLB; 6.49 ... STL"
    "board_y": (-2.50, 4.50),
    "board_thickness": 7.00,
    # "| Outline plan corner radius | r 3.0 (all four corners ...)"
    "board_corner_r": 3.0,
    # "| Outline edge rounding | top outer edge about r 0.8 ...; bottom edge
    #  about r 0.6"
    "board_edge_r": 0.8,
    "board_edge_r_bottom": 0.6,
    # "| Underside | flat at Y -2.5 over the whole footprint"
    "board_underside_y": -2.50,
    # "| PCB alone | 57.97 x 1.60 x 117.97, Y -1.60 to 0, ... corner r 2.0"
    "pcb_thickness": 1.60,
    "pcb_corner_r": 2.0,
    # "| Mounting holes | four 3.2 holes in the PCB at (25, 25), (35, 25),
    #  (25, 95), (35, 95) ... covered by the spine"
    "board_hole_d": 3.2,
    "board_holes": ((25.0, 25.0), (35.0, 25.0), (25.0, 95.0), (35.0, 95.0)),
    # "| Raised spine, plateau | Y 4.50 over X 21-39, Z 21-99; 45 deg
    #  chamfer 1 mm to Y 3.5 at X 20/40, Z 20/100"
    "spine_top_y": 4.50,
    "spine_plateau_x": (21.0, 39.0),
    "spine_plateau_z": (21.0, 99.0),
    "spine_frame_x": (20.0, 40.0),
    "spine_frame_z": (20.0, 100.0),
    "spine_chamfer": 1.0,
    # "| Spine ledges | Y 2.50"
    "spine_ledge_y": 2.50,
    # "| Seated module overhang past the board edge | 0.37-0.67 (speaker
    #  20.6, dc_motor body 20.4, shaft tip 29.2)"
    "module_proud": (0.37, 0.67),
    "speaker_overhang": 20.6,
    "motor_overhang": 20.4,
    # mods.out "===== usbc ... 'proud_mm': 0.25, 'section_mm': (10.0, 3.5)"
    "usbc_mouth": (10.0, 3.5),
    # mods.out "===== dc_motor ... 'proud_mm': 8.8, 'section_mm': (3.0, 3.0)"
    "motor_shaft": (3.0, 8.8),
    # mods.out screen "comp r 6.45..32.05 u 1.60..3.60 d 3.25..16.75
    #  size [25.6 2. 13.5]"
    ("face_screen", "active"): (25.6, 13.5),
    # MEASUREMENTS.md: "The case top is h 9.54 unless the table says otherwise"
    "module_h": 9.54,
}

SCRATCH = os.environ.get("ATECH_FITPLAN_DIR", "")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _get(fit, key):
    if isinstance(key, tuple):
        return fit[key[0]][0][key[1]]
    return fit[key][0]


def _close(a, b):
    if isinstance(a, (tuple, list)):
        return isinstance(b, (tuple, list)) and len(a) == len(b) \
            and all(_close(x, y) for x, y in zip(a, b))
    return abs(float(a) - float(b)) < 1e-6


def datum_mismatches(fit):
    """[(key, have, measured)] for every MEASURED datum `fit` gets wrong."""
    bad = []
    for key, want in MEASURED.items():
        try:
            have = _get(fit, key)
        except (KeyError, TypeError):
            bad.append((key, None, want))
            continue
        if not _close(have, want):
            bad.append((key, have, want))
    return bad


class FitKeys(unittest.TestCase):

    def test_every_rule_placeholder_exists(self):
        missing = [k for k in PLAN_PLACEHOLDERS if k not in atech_fit.FIT]
        self.assertEqual(missing, [])
        self.assertEqual(set(atech_fit.RULE_KEYS), set(PLAN_PLACEHOLDERS))

    def test_plan_file_placeholders_exist_when_present(self):
        path = os.path.join(SCRATCH, "PLAN_FINAL.md") if SCRATCH else ""
        if not path or not os.path.isfile(path):
            self.skipTest("set ATECH_FITPLAN_DIR to the scratch fitplan dir")
        text = _read(path)
        rules = text[text.index("**R6 FIT"):text.index("**R13")]
        proc = text[text.index("### 4.1"):text.index("### 4.2")]
        found = set(re.findall(r"\{([a-z_0-9]+)\}", rules + proc))
        self.assertEqual(sorted(found - set(atech_fit.FIT)), [])

    def test_snippets_format(self):
        vals = atech_fit.prompt_values()
        for s in PLAN_SNIPPETS:
            out = s.format(**vals)
            self.assertNotIn("{", out)
        self.assertIn("13.5 x 7.5", PLAN_SNIPPETS[1].format(**vals))

    def test_entries_are_triples_with_valid_tags(self):
        for key, entry in atech_fit.FIT.items():
            self.assertEqual(len(entry), 3, key)
            _, tag, note = entry
            parts = tag.split("/")
            self.assertTrue(parts and all(p in atech_fit.TAGS for p in parts),
                            "%s: bad tag %r" % (key, tag))
            self.assertTrue(isinstance(note, str) and note.strip(), key)

    def test_table_keys_exist(self):
        for key, t in atech_fit.TABLE.items():
            self.assertIn(key, atech_fit.FIT)
            self.assertIn(t, "ABCD")
        for key in atech_fit.KIT_APPLIED:
            self.assertIn(key, atech_fit.FIT)

    def test_value_and_text(self):
        self.assertEqual(atech_fit.value("stop"), 0.20)
        self.assertEqual(atech_fit.text("usbc_open"), "13.5 x 7.5")
        self.assertEqual(atech_fit.text("board_x"), "0.013..59.988")
        with self.assertRaises(KeyError):
            atech_fit.value("no_such_key")

    def test_face_thresholds(self):
        th = atech_fit.value("face_open")
        self.assertEqual(th["light"], 0.60)
        self.assertEqual(th["button"], 0.60)
        self.assertEqual(th["speaker"], 0.25)
        self.assertEqual(th["screen"], 1.00)
        for m in ("screen", "distance_sensor", "light", "button", "speaker",
                  "microphone", "temp_humidity", "orientation", "dc_motor"):
            self.assertIn("face_" + m, atech_fit.FIT)


class BoardDatums(unittest.TestCase):

    def test_datums_match_measurements(self):
        self.assertEqual(datum_mismatches(atech_fit.FIT), [])

    def test_sabotaged_datum_is_caught(self):
        fit = copy.deepcopy(atech_fit.FIT)
        _, tag, note = fit["board_corner_r"]
        fit["board_corner_r"] = (1.0, tag, note)    # ATECH_PRODUCTS.md's ~1
        bad = datum_mismatches(fit)
        self.assertEqual([b[0] for b in bad], ["board_corner_r"])
        with self.assertRaises(AssertionError):
            self.assertEqual(bad, [])
        fit = copy.deepcopy(atech_fit.FIT)
        fit["board_thickness"] = (6.49, "CAD", "the STL")
        self.assertEqual([b[0] for b in datum_mismatches(fit)],
                         ["board_thickness"])

    def test_thickness_conflict_is_recorded(self):
        note = atech_fit.FIT["board_thickness"][2]
        self.assertIn("6.49", note)
        self.assertAlmostEqual(atech_fit.value("board_y")[1]
                               - atech_fit.value("board_y")[0],
                               atech_fit.value("board_thickness"))

    def test_holes_are_under_the_spine(self):
        x0, x1 = atech_fit.value("spine_frame_x")
        z0, z1 = atech_fit.value("spine_frame_z")
        for x, z in atech_fit.value("board_holes"):
            self.assertTrue(x0 < x < x1 and z0 < z < z1)
        self.assertIn("not usable", atech_fit.FIT["board_holes"][2])

    def test_inventory_file_agrees_when_present(self):
        path = os.path.join(SCRATCH, "MEASUREMENTS.md") if SCRATCH else ""
        if not path or not os.path.isfile(path):
            self.skipTest("set ATECH_FITPLAN_DIR to the scratch fitplan dir")
        text = _read(path)
        self.assertIn("**r 3.0**", text)
        self.assertIn("**7.00** (Y −2.50 to +4.50)", text)
        self.assertIn("Y **4.50** over X 21–39, Z 21–99", text)
        self.assertIn("(25, 25), (35, 25), (25, 95), (35, 95)", text)
        self.assertIn("**1.60**", text)
        mods = _read(os.path.join(SCRATCH, "mods.out"))
        self.assertIn("'proud_mm': 0.25, 'section_mm': (10.0, 3.5)", mods)
        self.assertIn("'proud_mm': 8.8, 'section_mm': (3.0, 3.0)", mods)
        self.assertIn("size [25.6  2.  13.5]", mods)


class Forks(unittest.TestCase):

    def test_plan_table(self):
        cases = {
            "a little RC car": "toy_car",
            "build me a tank": "rc_tank",
            "a robot that waves": "desk_robot",
            "a desk pet": "desk_robot",
            "a smart speaker": "smart_speaker",
            "a desk fan": "desk_fan",
            "a desk fan with lights": "desk_fan",
            "a weather station": "weather_station",
            "a thermometer": "weather_station",
            "a speaker robot": "desk_robot",
            "a kitchen timer": "alarm_clock",
            "a bedside lamp": "bedside_lamp",
            "a night light": "bedside_lamp",
            "an alarm clock": "alarm_clock",
            "a handheld game console": "handheld_console",
            # R802: a pencil holder is a desk organizer now there is one
            "a pencil holder": "desk_organizer",
            "a pet feeding station": "pet_feeder",
            "an arcade game": "mini_arcade",
            "a photo frame with a light": "photo_frame",
            "a garage parking sensor for my car": "parking_sensor",
            "a jukebox speaker": "music_box",
            "a plant pot with a grow light": "smart_planter",
            # R803: the five Atech-hardware examples
            "a 4WD explorer rover": "rover",
            "a mars rover with lights": "rover",
            "a CO2 monitor for my office": "air_monitor",
            "an air quality sensor with a screen": "air_monitor",
            "a motion sensor night light": "motion_light",
            "a PIR lamp for the hallway": "motion_light",
            "a base for my SO-101 robot arm": "arm_dock",
            "a robotic arm controller": "arm_dock",
            "a self-balancing robot": "balance_bot",
            "a balance bot with a screen face": "balance_bot",
            "a teapot": "atech_case",
            "": "atech_case",
        }
        for req, want in cases.items():
            self.assertEqual(atech_fit.fork_for(req), want, req)
        self.assertEqual(atech_fit.fork_for(None), "atech_case")

    def test_word_boundaries_and_order(self):
        self.assertEqual(atech_fit.fork_for("a cartoon mug"), "atech_case")
        self.assertEqual(atech_fit.fork_for("a car with headlights"),
                         "toy_car")
        self.assertEqual(atech_fit.fork_for("SPEAKER"), "smart_speaker")

    def test_forks_name_existing_examples(self):
        ex = os.path.join(KIT, "examples")
        for _, name in atech_fit.FORKS + [(None, atech_fit.DEFAULT_FORK)]:
            self.assertTrue(os.path.isfile(os.path.join(ex, name + ".py")),
                            name)


SHOWCASE = os.path.join(HERE, "eval", "prompts_showcase.json")


def showcase_mismatches(forks):
    """R414: [(prompt, got, want)] for every showcase prompt whose fork
    (with the table `forks`) is not its own archetype's example - the
    prompt id names it ('showcase_toy_car' -> toy_car)."""
    import json
    with open(SHOWCASE, encoding="utf-8") as fh:
        prompts = json.load(fh)["prompts"]
    saved = atech_fit.FORKS
    atech_fit.FORKS = forks
    try:
        bad = []
        for p in prompts:
            want = p["id"].replace("showcase_", "")
            got = atech_fit.fork_for(p["prompt"])
            if got != want:
                bad.append((p["prompt"], got, want))
        return bad
    finally:
        atech_fit.FORKS = saved


class ShowcaseForks(unittest.TestCase):
    """R414: every showcase prompt seeds from its own archetype."""

    def test_every_showcase_prompt_forks_its_own_example(self):
        self.assertEqual(showcase_mismatches(atech_fit.FORKS), [])
        n = len(__import__("json").loads(_read(SHOWCASE))["prompts"])
        self.assertGreaterEqual(n, 9)

    def test_sabotaged_table_is_caught(self):
        # an alarm clock sent to the handheld (round 1's table) must fail
        bad = [(r"\b(clocks?|alarms?)\b", "handheld_console")] + list(atech_fit.FORKS)
        got = showcase_mismatches(bad)
        self.assertIn(("an alarm clock", "handheld_console", "alarm_clock"), got)
        with self.assertRaises(AssertionError):
            self.assertEqual(got, [])

    def test_reference_table_agrees(self):
        # ATECH_PRODUCTS.md section 0A names the same example per archetype
        ref = _read(os.path.join(KIT, "reference", "ATECH_PRODUCTS.md"))
        m = re.search(r"\n## 0A\. ARCHETYPE TABLE.*?(?=\n## )", ref, re.S)
        self.assertTrue(m)
        rows = [ln for ln in m.group(0).splitlines() if ln.startswith("|")]
        for word, ex in (("clock", "alarm_clock"), ("fan", "desk_fan"), ("weather", "weather_station"),
                         ("tank", "rc_tank")):
            row = next((r for r in rows if word in r.split("|")[1].lower()), "")
            self.assertIn("examples/%s.py" % ex, row.split("|")[2] if row else "", (word, row))


class StagesAndTables(unittest.TestCase):

    def test_stages(self):
        self.assertEqual(atech_fit.STAGES,
                         {"A": 0, "B": 12, "C": 28, "STOP": 48})
        self.assertEqual(atech_fit.stage_at(0), "A")
        self.assertEqual(atech_fit.stage_at(12), "B")
        self.assertEqual(atech_fit.stage_at(30), "C")
        self.assertEqual(atech_fit.stage_at(55), "STOP")

    def test_render_tables_short_and_complete(self):
        out = atech_fit.render_tables()
        self.assertLess(len(out), 2600, len(out))
        for title in ("A.", "B.", "C.", "D."):
            self.assertIn("\n" + title, out)
        for key in atech_fit.KIT_APPLIED:
            self.assertNotRegex(out, r"(^|[\s;-])%s " % re.escape(key))
        for key in ("slide", "stop", "usbc_open", "board_corner_r",
                    "spine_top_y", "ribbon_channel"):
            self.assertIn(key, out)
        self.assertIn("board_corner_r 3", out)
        self.assertIn("6.49", out)

    def test_board_first(self):
        self.assertIs(atech_fit.BOARD_FIRST, True)
        self.assertIn("ap.board_object(doc)", atech_fit.__doc__)
        self.assertIn("FLAT", atech_fit.PRESETS)

    def test_no_freecad_import(self):
        src = _read(atech_fit.__file__)
        self.assertNotRegex(src, r"(?m)^\s*(import|from)\s+(FreeCAD|Part)\b")


if __name__ == "__main__":
    unittest.main()
