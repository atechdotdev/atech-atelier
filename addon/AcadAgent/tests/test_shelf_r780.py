"""R780: off-the-shelf parts from the FreeCAD Parts Library
(projects/shelf.py, shelf_step2stl.py, the shipped shelf_index.json, the
Modules page's "Add off-the-shelf part..." dialog).

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_shelf_r780

The mesher test needs freecadcmd (ATECH_FREECADCMD). ATELIER_NET_TESTS=1
adds a real install from GitHub (network; one small part).
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
for p in (ADDON, os.path.join(REPO, "projects")):
    if p not in sys.path:
        sys.path.insert(0, p)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shelf  # noqa: E402
import user_parts  # noqa: E402

try:
    from PySide6 import QtWidgets
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from acadagent import shelf_dialog as sdlg
except ImportError:                                    # no Qt here
    sdlg = None

from test_modules_page_r300 import FC, MODELS  # noqa: E402

FAKE = {"revision": "f" * 40, "licence": "CC BY 3.0", "count": 3, "parts": {
    "sg90_servo": {"group": "motors", "display_name": "SG90 micro servo",
                   "description": "Micro hobby servo.", "path": "a/Servo-sg90.step",
                   "git_oid": "0" * 40, "bytes": 1500000, "category": "motor",
                   "size_mm": [32.2, 31.0, 12.2], "authors": ["Gafeju"],
                   "electrical": {"interface": "pwm", "voltage_v": 5}, "thumb": None},
    "battery_aa": {"group": "power", "display_name": "AA battery", "description": "AA cell.",
                   "path": "b/battery-AA.step", "git_oid": "1" * 40, "bytes": 14000,
                   "category": "power", "size_mm": [14.5, 50.5, 14.5], "authors": ["X"],
                   "thumb": None},
    "arduino_nano": {"group": "boards", "display_name": "Arduino Nano (Rev3)",
                     "description": "Small microcontroller board.", "path": "c/Nano.step",
                     "git_oid": "2" * 40, "bytes": 2000000, "category": "electronics",
                     "size_mm": [43.2, 18.5, 7.0], "authors": [], "thumb": None},
}}


class FakeIndex(object):
    def setUp(self):
        self._idx = shelf._INDEX
        shelf._INDEX = json.loads(json.dumps(FAKE))

    def tearDown(self):
        shelf._INDEX = self._idx


class TestPure(FakeIndex, unittest.TestCase):

    def test_search(self):
        keys = [k for k, _ in shelf.search()]
        self.assertEqual(keys, ["arduino_nano", "sg90_servo", "battery_aa"])  # by group
        self.assertEqual([k for k, _ in shelf.search("servo")], ["sg90_servo"])
        self.assertEqual([k for k, _ in shelf.search("micro")], ["arduino_nano", "sg90_servo"])
        self.assertEqual([k for k, _ in shelf.search(group="power")], ["battery_aa"])

    def test_keys_never_paths(self):
        for bad in ("../x", "sg90_servo/..", "nope", "", None):
            with self.assertRaises(shelf.ShelfError):
                shelf.check_key(bad)
        self.assertEqual(shelf.check_key("sg90_servo"), "sg90_servo")

    def test_urls_pinned(self):
        u = shelf.file_url("Electrical Parts/Servos/SG-90/Servo-sg90.step")
        self.assertTrue(u.startswith("https://raw.githubusercontent.com/FreeCAD/"
                                     "FreeCAD-library/" + shelf.REVISION + "/"))
        self.assertIn("Electrical%20Parts", u)
        with self.assertRaises(shelf.ShelfError):
            shelf._get("http://example.com/x")

    def test_fetch_checks_blob_and_size(self):
        data = b"ISO-10303-21;\nHEADER;\n"
        good = shelf.blob_id(data)
        # git's own id of these bytes (git hash-object)
        self.assertEqual(len(good), 40)
        real = shelf._get

        class R(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        shelf._get = lambda url, timeout=0: R(data)
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "x.step")
            self.assertEqual(shelf.fetch("x.step", good, len(data), p), p)
            os.remove(p)
            with self.assertRaises(shelf.ShelfError) as cm:
                shelf.fetch("x.step", "0" * 40, len(data), p)
            self.assertIn("blob id", str(cm.exception))
            self.assertFalse(os.path.exists(p))
            with self.assertRaises(shelf.ShelfError):
                shelf.fetch("x.step", good, len(data) + 1, p)
            self.assertFalse(os.path.exists(p))
        finally:
            shelf._get = real
            shutil.rmtree(d, ignore_errors=True)

    def test_attribution(self):
        a = shelf.attribution(FAKE["parts"]["sg90_servo"])
        self.assertIn("SG90 micro servo", a)
        self.assertIn("Gafeju", a)
        self.assertIn("CC BY 3.0", a)
        self.assertIn("its authors", shelf.attribution(FAKE["parts"]["arduino_nano"]))

    def test_picture_never_outside_its_folder(self):
        shelf._INDEX["parts"]["sg90_servo"]["picture"] = "../shelf.py"
        real = shelf._get
        shelf._get = lambda *a, **k: self.fail("no thumb to download")
        try:
            self.assertIsNone(shelf.thumbnail("sg90_servo", tempfile.gettempdir()))
        finally:
            shelf._get = real

    def test_part_name(self):
        self.assertEqual(shelf.part_name("sg90_servo"), "ots_sg90_servo")
        self.assertTrue(user_parts.NAME_RE.match(shelf.part_name("tactile_button_right_angle")))


class TestShippedIndex(unittest.TestCase):

    def test_index(self):
        with open(shelf.INDEX, encoding="utf-8") as fh:
            idx = json.load(fh)
        self.assertEqual(idx["revision"], shelf.REVISION)
        self.assertEqual(idx["licence"], "CC BY 3.0")
        parts = idx["parts"]
        self.assertGreaterEqual(len(parts), 70)
        groups = dict(shelf.GROUPS)
        for key, e in parts.items():
            self.assertRegex(key, r"^[a-z][a-z0-9_]{1,40}$")
            self.assertTrue(user_parts.NAME_RE.match(shelf.part_name(key)), key)
            self.assertIn(e["group"], groups, key)
            self.assertIn(e["category"], user_parts.CATEGORIES, key)
            self.assertRegex(e["git_oid"], r"^[0-9a-f]{40}$", key)
            self.assertGreater(e["bytes"], 0, key)
            self.assertTrue(e["path"].lower().endswith((".step", ".stp")), key)
            self.assertTrue(e["authors"], key)              # CC BY needs a name
            lo, hi = user_parts.SANE_MM
            self.assertTrue(lo <= max(e["size_mm"]) <= hi, (key, e["size_mm"]))
            iface = (e.get("electrical") or {}).get("interface")
            self.assertTrue(iface is None or iface in user_parts.INTERFACES, key)
            if e.get("thumb"):
                self.assertTrue(e["thumb"].startswith("thumbnails/"), key)
        for g in groups:                                 # every group offers parts
            self.assertTrue(any(e["group"] == g for e in parts.values()), g)

    def test_pictures_shipped_and_offline(self):
        with open(shelf.INDEX, encoding="utf-8") as fh:
            parts = json.load(fh)["parts"]
        for key, e in parts.items():
            self.assertEqual(e.get("picture"), "shelf_pictures/%s.png" % key, key)
            p = os.path.join(REPO, "projects", e["picture"])
            with open(p, "rb") as fh:
                self.assertEqual(fh.read(8), b"\x89PNG\r\n\x1a\n", key)
        real = shelf._get
        shelf._get = lambda *a, **k: self.fail("no download for a shipped picture")
        try:
            self.assertEqual(shelf.thumbnail("sg90_servo", tempfile.gettempdir()),
                             os.path.join(REPO, "projects", "shelf_pictures", "sg90_servo.png"))
        finally:
            shelf._get = real

    def test_mains_parts_say_so(self):
        with open(shelf.INDEX, encoding="utf-8") as fh:
            parts = json.load(fh)["parts"]
        for key in ("irm60_psu", "switching_psu"):
            self.assertIn("MAINS", parts[key]["agent_notes"])


@unittest.skipIf(not FC, "needs freecadcmd")
class TestMesher(unittest.TestCase):

    def test_step_in_child(self):
        d = tempfile.mkdtemp(prefix="r780_mesh_")
        try:
            step = os.path.join(d, "box.step")
            mk = os.path.join(d, "mk.py")
            with open(mk, "w") as fh:
                fh.write("import Part\nPart.makeBox(12, 7, 30).exportStep(%r)\n" % step)
            subprocess.run([FC, mk], capture_output=True, timeout=300)
            self.assertTrue(os.path.isfile(step))
            stl = os.path.join(d, "box.stl")
            rep = shelf.tessellate(step, stl, freecadcmd=FC)
            self.assertEqual(rep["size_mm"], [12.0, 7.0, 30.0])
            self.assertEqual(rep["triangles"], 12)
            self.assertTrue(os.path.getsize(stl) > 84)
            with open(os.path.join(d, "bad.step"), "w") as fh:
                fh.write("not a step file")
            with self.assertRaises(shelf.ShelfError):
                shelf.tessellate(os.path.join(d, "bad.step"), stl + "2", freecadcmd=FC)
        finally:
            shutil.rmtree(d, ignore_errors=True)


@unittest.skipIf(sdlg is None, "needs PySide6")
class TestDialog(FakeIndex, unittest.TestCase):

    def _fake(self, install):
        class Fake(object):
            GROUPS = shelf.GROUPS
            search = staticmethod(shelf.search)
            index = staticmethod(shelf.index)
            installed = staticmethod(lambda: {"battery_aa": "ots_battery_aa"})
            thumbnail = staticmethod(lambda k, d: None)
        Fake.install = staticmethod(install)
        return Fake

    def _wait(self, cond):
        t0 = time.time()
        while not cond() and time.time() - t0 < 10:
            _APP.processEvents()
            time.sleep(0.01)

    def test_browse_and_install(self):
        calls, done = [], []

        def install(key, progress=None, freecadcmd=None):
            progress("Downloading", None)
            calls.append((key, freecadcmd))
            return "ots_" + key, {}
        d = sdlg.ShelfDialog(None, on_done=done.append, shelf=self._fake(install),
                             freecadcmd="/x/freecadcmd")
        rows = [d.list.item(i).text() for i in range(d.list.count())]
        self.assertEqual(len(rows), 3, rows)
        self.assertTrue(rows[0].startswith("Arduino Nano"), rows)
        self.assertTrue(any("installed" in r for r in rows), rows)
        d.group.setCurrentIndex(d.group.findData("motors"))
        self.assertEqual(d.list.count(), 1)
        info = d.info.text()
        self.assertIn("32.2 × 31 × 12.2 mm", info)
        self.assertIn("PWM · 5 V", info)
        self.assertIn("By Gafeju · CC BY 3.0", info)
        d.group.setCurrentIndex(0)
        d.query.setText("aa")
        self.assertEqual(d.list.count(), 1)
        d.query.setText("servo")
        d.install()
        self._wait(lambda: done)
        self.assertEqual(calls, [("sg90_servo", "/x/freecadcmd")])
        self.assertEqual(done, ["ots_sg90_servo"])
        self.assertIn("Installed", d.status.text())

    def test_failure_is_shown(self):
        def install(key, progress=None, freecadcmd=None):
            raise shelf.ShelfError("x.step: blob id abc, expected def - not installed")
        d = sdlg.ShelfDialog(None, shelf=self._fake(install), freecadcmd="")
        d.install()
        self._wait(lambda: "not installed" in d.status.text())
        self.assertIn("not installed", d.status.text())
        self.assertTrue(d.list.isEnabled())

    def test_wiring_text(self):
        self.assertEqual(sdlg.wiring_text({"interface": "i2c", "voltage_v": 3.3,
                                           "wiring": "addr 0x37"}), "I2C · 3.3 V · addr 0x37")
        self.assertEqual(sdlg.wiring_text({"interface": "other", "connectors": "CSI"}), "CSI")
        self.assertEqual(sdlg.wiring_text(None), "")


@unittest.skipIf(not (os.environ.get("ATELIER_NET_TESTS") and FC),
                 "set ATELIER_NET_TESTS=1 (needs network and freecadcmd)")
class TestRealInstall(unittest.TestCase):

    def test_aa_battery(self):
        d = tempfile.mkdtemp(prefix="r780_net_")
        script = os.path.join(d, "run.py")
        with open(script, "w") as fh:
            fh.write("import sys, json\nsys.path.insert(0, %r)\n"
                     "import shelf, atech_modules as am\n"
                     "n, sp = shelf.install('battery_aa', freecadcmd=%r)\n"
                     "print('R780=' + json.dumps([n, sp['dimensions_mm'], sp['licence'], "
                     "sp['shelf']['attribution'], am.is_user_part(n), "
                     "shelf.installed()]))\n"
                     % (os.path.join(REPO, "projects"), FC))
        try:
            env = dict(os.environ, ATELIER_PARTS=os.path.join(d, "parts"),
                       ATECH_ARTIFACTS=MODELS)
            out = subprocess.run([FC, script], env=env, capture_output=True,
                                 text=True, timeout=900).stdout
        finally:
            shutil.rmtree(d, ignore_errors=True)
        line = [ln for ln in out.splitlines() if ln.startswith("R780=")]
        self.assertTrue(line, out[-2000:])
        n, dims, lic, attr, mine, have = json.loads(line[0][5:])
        self.assertEqual(n, "ots_battery_aa")
        size = sorted((dims["x"], dims["y"], dims["z"]))
        self.assertAlmostEqual(size[2], 50.5, delta=1.0)    # an AA cell: 50.5 x 14.5
        self.assertAlmostEqual(size[0], 14.5, delta=0.6)
        self.assertEqual(lic, "CC BY 3.0")
        self.assertIn("FreeCAD Parts Library", attr)
        self.assertTrue(mine)
        self.assertEqual(have, {"battery_aa": "ots_battery_aa"})


if __name__ == "__main__":
    unittest.main()
