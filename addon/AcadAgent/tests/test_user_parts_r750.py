"""R750: parts that are not Atech modules (projects/user_parts.py, the
Modules page's "Import part..." dialog, the agent's API card).

Pure parts need PyYAML (and PySide6 for the page's words):

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_user_parts_r750

The FreeCAD part runs fc_user_parts_r750.py under freecadcmd (found through
ATECH_FREECADCMD or the dist build) against a scratch parts folder, and
skips without freecadcmd or the module library.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
for p in (ADDON, os.path.join(REPO, "projects")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import yaml  # noqa: F401
    import user_parts as up
except ImportError:
    up = None

try:
    from PySide6 import QtWidgets
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from acadagent import import_part as ip
    from acadagent import modules_page as mp
except ImportError:                                    # no Qt here
    ip = mp = None

from test_modules_page_r300 import FC, LIB, MODELS  # noqa: E402


@unittest.skipIf(up is None, "PyYAML not installed")
class TestCatalog(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="r750_")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_dir_from_env(self):
        self.assertEqual(up.parts_dir({"ATELIER_PARTS": self.d}), self.d)

    def test_names(self):
        self.assertEqual(up.slug("Arduino Nano 33 IoT"), "arduino_nano_33_iot")
        self.assertEqual(up.slug("18650 holder"), "part_18650_holder")
        up.check_name("arduino_nano")
        for bad in ("Arduino", "a", "1x", "has space", "x" * 49):
            with self.assertRaises(up.PartError):
                up.check_name(bad)
        with self.assertRaises(up.PartError):
            up.check_name("button", reserved={"button"})

    def test_empty_and_reload(self):
        self.assertEqual(up.specs(self.d), {})
        with open(os.path.join(self.d, "parts.yaml"), "w") as fh:
            fh.write("format: 1\npi: {category: electronics, file: pi.stl}\n")
        self.assertEqual(set(up.specs(self.d)), {"pi"})
        self.assertTrue(up.specs(self.d)["pi"]["user"])
        self.assertIsNone(up.stl_path("pi", self.d))         # mesh missing
        os.makedirs(os.path.join(self.d, "stl"))
        open(os.path.join(self.d, "stl", "pi.stl"), "w").close()
        self.assertTrue(up.stl_path("pi", self.d).endswith("pi.stl"))
        with open(os.path.join(self.d, "parts.yaml"), "w") as fh:
            fh.write("format: 1\npi: {category: power, file: pi.stl}\n"
                     "cell: {category: power}\n")
        self.assertEqual(set(up.specs(self.d)), {"pi", "cell"})

    def test_write_round_trip(self):
        up._write({"pi": {"category": "electronics", "user": True}}, self.d)
        text = open(os.path.join(self.d, "parts.yaml")).read()
        self.assertNotIn("user:", text)
        self.assertEqual(up.specs(self.d)["pi"]["category"], "electronics")

    def test_electrical_line(self):
        self.assertEqual(up.electrical_line({}), "")
        self.assertEqual(up.electrical_line({"electrical": {
            "interface": "uart", "voltage_v": 3.3, "current_ma": 80,
            "connectors": "JST-PH 4-pin"}}), "uart; 3.3V; 80 mA; JST-PH 4-pin")

    def test_unknown_file_type(self):
        p = os.path.join(self.d, "x.dwg")
        open(p, "w").close()
        with self.assertRaises(up.PartError):
            up.read_mesh(p)


@unittest.skipIf(ip is None, "PySide6 not installed")
class TestDialogWords(unittest.TestCase):

    def test_answers(self):
        kw = ip.answers_to_kwargs({
            "display_name": " Pi Zero ", "category": "electronics",
            "interface": "i2c", "voltage": "5", "current": "120,5",
            "wiring": "Qwiic", "notes": "keep SD slot open", "units_scale": 25.4,
            "recentre": False})
        self.assertEqual(kw["display_name"], "Pi Zero")
        self.assertEqual(kw["electrical"], {"interface": "i2c", "voltage_v": 5,
                                            "current_ma": 120.5, "wiring": "Qwiic"})
        self.assertEqual(kw["scale"], 25.4)
        self.assertFalse(kw["recentre"])
        self.assertIsNone(ip.answers_to_kwargs({"display_name": "x"})["electrical"])
        with self.assertRaises(ValueError):
            ip.answers_to_kwargs({"voltage": "five"})

    def test_tooltip(self):
        self.assertEqual(mp.free_part_tooltip({"description": "Wheel"}, "W"), "Wheel")
        t = mp.free_part_tooltip({"description": "Nano", "user": True,
                                  "electrical": {"interface": "i2c", "voltage_v": 5}},
                                 "Nano")
        self.assertIn("Your part", t)
        self.assertIn("Wiring: i2c; 5V", t)

    def test_dialog_imports_through_user_parts(self):
        calls = []

        class Fake:
            @staticmethod
            def import_part(path, **kw):
                calls.append((path, kw))
                return {"file": "pi_zero.stl"}
        done = []
        d = ip.ImportPartDialog(None, path="/x/Pi Zero.step",
                                on_done=done.append, user_parts=Fake)
        self.assertEqual(d.name.text(), "Pi Zero")
        d.voltage.setText("bad")
        d.run()
        self.assertEqual(calls, [])
        self.assertIn("not a number", d.status.text())
        d.voltage.setText("5")
        d.interface.setCurrentIndex(d.interface.findData("i2c"))
        d.run()
        self.assertEqual(done, ["pi_zero"])
        self.assertEqual(calls[0][1]["electrical"], {"interface": "i2c", "voltage_v": 5})


@unittest.skipIf(not (FC and LIB), "needs freecadcmd and the module library")
class TestInFreeCAD(unittest.TestCase):

    def test_r750(self):
        d = tempfile.mkdtemp(prefix="r750_parts_")
        try:
            env = dict(os.environ, ATELIER_PARTS=d, ATECH_ARTIFACTS=MODELS,
                       QT_QPA_PLATFORM="offscreen")
            out = subprocess.run([FC, os.path.join(HERE, "fc_user_parts_r750.py")],
                                 env=env, capture_output=True, text=True,
                                 timeout=600).stdout
        finally:
            shutil.rmtree(d, ignore_errors=True)
        fails = [ln for ln in out.splitlines() if ln.startswith("CHECK ")
                 and " FAIL " in ln]
        self.assertEqual(fails, [], out[-3000:])
        m = re.search(r"R750_TESTS=(\d+)", out)
        self.assertTrue(m and m.group(1) == "0", out[-3000:])
        self.assertGreaterEqual(out.count(" PASS "), 20, out[-3000:])


if __name__ == "__main__":
    unittest.main()
