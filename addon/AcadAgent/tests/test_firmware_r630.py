"""R630: the firmware half of an Atech product (agent_kit/atech_firmware.py).

Runs under SYSTEM python (no FreeCAD, no PyYAML, no `atech`): the bridge
reads the kit's snapshot of the Atech SDK catalog ($ATECH_SDK_CATALOG=
snapshot), so these numbers are the snapshot's.

What is pinned:
  - the snapshot is the SDK's 14-port board (ports 8 and 12 reserved, the
    SDK's 2-port pairs) and every CAD -> SDK id in SDK_ID exists in it
  - plan(): usbc carries no firmware, instances are named, port order
  - issues(): the SDK's placement rules (reserved port, pair, size, unknown)
  - project_yaml -> read_project -> compare round-trips; compare and
    lint_code catch a wrong port, an extra module, Serial reads, a long
    delay(), a GPIO number and a method the SDK does not have
  - reference/ATECH_FIRMWARE.md is written read-only into the workspace and
    the Atech card carries the FIRMWARE rule unless the switch is off
  - with `atech` installed, the live catalog has the snapshot's shape
"""
import os
import stat
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
sys.path.insert(0, ADDON)
os.environ["ATECH_SDK_CATALOG"] = "snapshot"

from acadagent import build  # noqa: E402

KIT = os.path.join(ADDON, "acadagent", "agent_kit")
sys.path.insert(0, KIT)
import atech_firmware as fw  # noqa: E402


class TestSnapshot(unittest.TestCase):

    def setUp(self):
        self.cat = fw.catalog(refresh=True)

    def test_snapshot_loads(self):
        self.assertIsNotNone(self.cat)
        self.assertEqual(self.cat["source"], "snapshot")
        self.assertTrue(self.cat["sdk_version"])
        self.assertIn("## project.yaml", self.cat["guide"])

    def test_14port_is_the_sdks(self):
        b = self.cat["boards"]["14port"]
        self.assertEqual(b["reserved"], [8, 12])
        self.assertNotIn("8", b["ports"])
        self.assertIn([13, 14], b["adjacent"])
        self.assertNotIn([11, 12], b["adjacent"])

    def test_every_sdk_id_exists(self):
        for cad, sid in fw.SDK_ID.items():
            if sid is not None:
                self.assertIn(sid, self.cat["modules"], cad)

    def test_methods_are_the_public_api(self):
        m = self.cat["modules"]["button"]["methods"]
        self.assertIn("wasPressed", m)
        for mods in self.cat["modules"].values():
            self.assertFalse([n for n in mods["methods"]
                              if n.startswith("_") or n[0].isupper()])


SEATED = [{"module": "screen", "ports": [12, 11]},
          {"module": "usbc", "ports": [7]},
          {"module": "button", "ports": [3]},
          {"module": "button", "ports": [2]},
          {"module": "speaker", "ports": [13, 14]}]


class TestPlan(unittest.TestCase):

    def test_plan(self):
        p = fw.plan(SEATED)
        self.assertEqual([(e["id"], e["instance"], e["ports"]) for e in p], [
            ("button", "btn", [2]), ("button", "btn2", [3]),
            ("st7735_tft", "screen", [11, 12]), ("speaker", "spk", [13, 14])])

    def test_issues_reserved_port(self):
        out = fw.issues(fw.plan(SEATED))
        self.assertEqual(len(out), 2, out)          # port 12 reserved + 11+12 no pair
        self.assertTrue(any("port 12 is reserved" in l for l in out), out)
        self.assertTrue(any("not a 2-port pair" in l for l in out), out)

    def test_issues_clean(self):
        self.assertEqual(fw.issues(fw.plan([
            {"module": "screen", "ports": [9, 10]},
            {"module": "speaker", "ports": [13, 14]},
            {"module": "dc_motor", "ports": [1]}])), [])

    def test_robot_arm_needs_uart(self):
        out = fw.issues(fw.plan([{"module": "robot_arm", "ports": [1]}]))
        self.assertTrue(any("needs uart" in l and "3, 4" in l for l in out), out)
        self.assertEqual(fw.issues(fw.plan([{"module": "robot_arm", "ports": [3]}])), [])

    def test_issues_size_and_unknown(self):
        out = fw.issues(fw.plan([{"module": "knob", "ports": [3]},
                                 {"module": "warp_drive", "ports": [4]}]))
        self.assertTrue(any("takes 2 port(s)" in l for l in out), out)
        self.assertTrue(any("no firmware module" in l for l in out), out)

    def test_sabotage_a_board_without_reserved_ports_passes_port_12(self):
        cat = dict(fw.catalog())
        b = dict(cat["boards"]["14port"], reserved=[])
        b["ports"] = dict(b["ports"], **{"12": ["gpio"]})
        cat["boards"] = {"14port": b}
        out = fw.issues(fw.plan([{"module": "button", "ports": [12]}]), cat=cat)
        self.assertEqual(out, [])


class TestProject(unittest.TestCase):

    def write(self, text):
        d = tempfile.mkdtemp()
        p = os.path.join(d, fw.PROJECT)
        with open(p, "w") as fh:
            fh.write(text)
        return p

    def entries(self):
        return fw.plan([{"module": "button", "ports": [3]},
                        {"module": "speaker", "ports": [13, 14]}])

    def test_round_trip(self):
        e = self.entries()
        text = fw.project_yaml("alarm clock", e, loop="if (btn.wasPressed()) {\n"
                               "  spk.playTone(880, 100);\n}")
        proj = fw._parse(text)
        self.assertEqual(proj["board"], "14port")
        self.assertEqual(proj["name"], "alarm_clock")
        self.assertIn("spk.playTone", proj["code"]["loop"])
        self.assertEqual(fw.compare(proj, e), [])
        self.assertEqual(fw.lint_code(proj), [])
        self.assertEqual(fw.compare(fw.read_project(self.write(text)), e), [])

    def test_block_style_modules(self):
        proj = fw._parse("board: 14port\nmodules:\n  - id: button\n"
                         "    instance: btn\n    port: 3\n  - id: speaker\n"
                         "    instance: spk\n    ports: [13, 14]\n")
        self.assertEqual(fw.compare(proj, self.entries()), [])

    def test_compare_catches(self):
        proj = fw._parse("board: 10port\nmodules:\n"
                         "  - {id: button, instance: btn, port: 4}\n"
                         "  - {id: pir, instance: pir, port: 5}\n")
        out = " | ".join(fw.compare(proj, self.entries()))
        self.assertIn("board is '10port'", out)
        self.assertIn("no button on port(s) 3", out)
        self.assertIn("it has it on 4", out)
        self.assertIn("no speaker on port(s) 13+14", out)
        self.assertIn("lists pir", out)

    def test_lint(self):
        code = ("board: 14port\nmodules:\n  - {id: button, instance: btn, port: 3}\n"
                "code:\n  loop: |\n    if (Serial.available()) {}\n"
                "    delay(500);\n    digitalWrite(5, HIGH);\n"
                "    if (btn.wasDoubleClicked()) {}\n")
        out = " | ".join(fw.lint_code(fw._parse(code)))
        self.assertIn("reads Serial", out)
        self.assertIn("delay(500)", out)
        self.assertIn("GPIO number", out)
        self.assertIn("btn.wasDoubleClicked() is not in the SDK", out)

    def test_empty_code_does_nothing(self):
        out = fw.lint_code(fw._parse(fw.project_yaml("x", self.entries())))
        self.assertEqual(len(out), 1)
        self.assertIn("does nothing", out[0])

    def test_report(self):
        d = tempfile.mkdtemp()
        r = fw.report(SEATED, d)
        self.assertFalse(r["project_found"])
        self.assertIn("{id: speaker, instance: spk, ports: [13, 14]}", r["yaml"])
        with open(os.path.join(d, fw.PROJECT), "w") as fh:
            fh.write(r["yaml"])
        r = fw.report(SEATED, d)
        self.assertTrue(r["project_found"])
        self.assertEqual(len(r["project"]), 1)       # code: is still empty


class TestReference(unittest.TestCase):

    def test_reference_md(self):
        md = fw.reference_md()
        self.assertIn("| light | neopixel | 1 |", md)
        self.assertIn("Reserved (no module can be built there): port 8, port 12", md)
        self.assertIn("## Rules for the `code:` block (from the SDK guide)", md)
        self.assertIn("### robot_arm", md)
        self.assertIn("| robot_arm | robot_arm | 1 |", md)
        self.assertNotIn("no CAD model yet", md)        # all 14 have CAD now
        self.assertIn("**CAUTION:**", md)
        self.assertNotIn("{{ instance }}", md)

    def test_workspace_gets_it_read_only(self):
        ws = tempfile.mkdtemp()
        self.assertEqual(build._write_firmware_reference(ws),
                         ["reference/" + build.FIRMWARE_MD])
        p = os.path.join(ws, "reference", build.FIRMWARE_MD)
        self.assertFalse(os.stat(p).st_mode & stat.S_IWUSR)
        self.assertEqual(build._write_firmware_reference(ws), [])   # unchanged

    def test_switch_off(self):
        old = os.environ.get("ATECH_PROMPT_OFF")
        os.environ["ATECH_PROMPT_OFF"] = "firmware"
        try:
            self.assertFalse(build.firmware_on())
            self.assertEqual(build._write_firmware_reference(tempfile.mkdtemp()), [])
        finally:
            if old is None:
                os.environ.pop("ATECH_PROMPT_OFF")
            else:
                os.environ["ATECH_PROMPT_OFF"] = old

    @unittest.skipUnless(build.library_available(), "no Atech module library")
    def test_card_carries_the_rule(self):
        build._CARD = None
        self.assertIn("FIRMWARE: also write project.yaml", build._api_card())
        old = os.environ.get("ATECH_PROMPT_OFF")
        os.environ["ATECH_PROMPT_OFF"] = "firmware"
        try:
            build._CARD = None
            self.assertNotIn("FIRMWARE: also write", build._api_card())
        finally:
            build._CARD = None
            if old is None:
                os.environ.pop("ATECH_PROMPT_OFF")
            else:
                os.environ["ATECH_PROMPT_OFF"] = old

    def test_level_lines(self):
        lv = build._levels()
        on = lv.level_text(1, module_plan=True, firmware=True)
        self.assertIn("firmware job", on)
        self.assertNotIn("firmware job", lv.level_text(1, module_plan=True))
        self.assertIn("project.yaml", lv.level_text(2, module_plan=True, firmware=True))


class TestLive(unittest.TestCase):

    def test_installed_sdk_has_the_snapshots_shape(self):
        try:
            import atech
        except Exception:                              # noqa: BLE001
            self.skipTest("the atech SDK is not installed in this python")
        live, snap = fw.from_sdk(atech), fw._snapshot()
        self.assertEqual(sorted(live), sorted(k for k in snap if k != "source"))
        self.assertEqual(sorted(live["boards"]["14port"]),
                         sorted(snap["boards"]["14port"]))


if __name__ == "__main__":
    unittest.main()
