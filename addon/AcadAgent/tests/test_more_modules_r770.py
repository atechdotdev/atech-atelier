"""R770: more Atech modules in the library, from the atech-module-simready
dataset (0ba167be): big_screen and camera (Atech CAD), soil_sensor,
load_cell and power_jack (derived). micro_sd_card is left out on purpose
(projects/import_simready.py NOT_IMPORTED).

The library facts run in plain Python; seating runs fc_more_modules_r770.py
under freecadcmd (ATECH_FREECADCMD).
"""
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
from test_modules_page_r300 import FC, LIB, MODELS  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
NEW = ("big_screen", "camera", "soil_sensor", "load_cell", "power_jack")


class TestLibrary(unittest.TestCase):

    def test_meshes_and_provenance(self):
        with open(os.path.join(REPO, "models", "SIMREADY.json"), encoding="utf-8") as fh:
            rec = json.load(fh)
        self.assertEqual(rec["revision"], "0ba167be220e32f61f1fdcada519a65fc7e366e0")
        for n in NEW:
            self.assertIn(n, rec["modules"])
            self.assertTrue(os.path.isfile(os.path.join(REPO, "models", "stl", n + ".stl")), n)
        self.assertNotIn("micro_sd_card", rec["modules"])

    def test_presets_and_maps(self):
        from acadagent import board_look as bl
        from acadagent.agent_kit import atech_firmware as fw
        with open(os.path.join(REPO, "models", "presets.yaml"), encoding="utf-8") as fh:
            keys = re.findall(r"^([a-z0-9_]+):\s*$", fh.read(), re.M)
        for n in NEW:
            self.assertIn(n, keys)
            self.assertIn(n, bl.SLUG)
            self.assertIn(n, bl.OFFSETS_MM)
            # No SDK driver yet: no firmware entry, not an unknown module.
            self.assertIn(n, fw.SDK_ID)
            self.assertIsNone(fw.SDK_ID[n])
        self.assertEqual(fw.plan([{"module": "soil_sensor", "ports": [3]},
                                  {"module": "button", "ports": [1]}], cat={"modules": {}}),
                         [{"id": "button", "instance": "btn", "cad": "button", "ports": [1]}])

    def test_micro_sd_left_out_with_reason(self):
        with open(os.path.join(REPO, "projects", "import_simready.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("NOT_IMPORTED", src)
        self.assertIn('"micro_sd_card"', src.split("NOT_IMPORTED")[1][:200])


@unittest.skipIf(not (FC and LIB), "needs freecadcmd and the module library")
class TestInFreeCAD(unittest.TestCase):

    def test_r770(self):
        env = dict(os.environ, ATECH_ARTIFACTS=MODELS, QT_QPA_PLATFORM="offscreen")
        out = subprocess.run([FC, os.path.join(HERE, "fc_more_modules_r770.py")],
                             env=env, capture_output=True, text=True,
                             timeout=900).stdout
        fails = [ln for ln in out.splitlines() if ln.startswith("CHECK ")
                 and " FAIL " in ln]
        self.assertEqual(fails, [], out[-3000:])
        m = re.search(r"R770_TESTS=(\d+)", out)
        self.assertTrue(m and m.group(1) == "0", out[-3000:])
        self.assertGreaterEqual(out.count(" PASS "), 11, out[-3000:])


if __name__ == "__main__":
    unittest.main()
