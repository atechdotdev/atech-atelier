"""R760: install parts from NVIDIA SimReady (projects/simready.py,
simready_usd2stl.py, the shipped simready_index.json, the Modules page's
"Install from NVIDIA SimReady..." dialog).

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_simready_r760

The converter tests need usd-core: $ATELIER_USD_DIR (a folder holding pxr)
or one importable here; they skip without it. ATELIER_NET_TESTS=1 adds a
real install from the Hub (needs freecadcmd, network; ~1 MB).
"""
import hashlib
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

import simready as sr  # noqa: E402

try:
    from PySide6 import QtCore, QtWidgets
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from acadagent import simready_dialog as sd
except ImportError:                                    # no Qt here
    sd = None

from test_modules_page_r300 import FC, MODELS  # noqa: E402


def _usd_dir():
    d = os.environ.get("ATELIER_USD_DIR")
    if d and os.path.isdir(os.path.join(d, "pxr")):
        return d
    return None


USD = _usd_dir()

FAKE = {"revision": "f" * 40, "count": 4, "assets": {
    "power_battery_9v_a01": {"size_mm": [17.5, 53.4, 27.0], "mass_kg": 0.2,
                             "thumb": "simready_usd/.thumbs/x_thumbnail.png"},
    "consumable_fuse_midi_yellow_a01": {"size_mm": [5.2, 22.2, 18.7]},
    "box_printer_white_b04": {"size_mm": [223.4, 204.0, 278.6]},
    "IV_pole_a01": {"size_mm": [722.1, 1799.4, 570.9]},
}}


class FakeIndex(object):
    def setUp(self):
        self._old = sr._INDEX
        sr._INDEX = FAKE

    def tearDown(self):
        sr._INDEX = self._old


class TestPure(FakeIndex, unittest.TestCase):

    def test_files_needed(self):
        n = "power_battery_9v_a01"
        self.assertTrue(sr.is_root_usd(n, n + "/simready_usd/sm_power_battery_9v_a01_01.usd"))
        self.assertFalse(sr.is_root_usd(n, n + "/simready_usd/payloads/geometries.usd"))
        self.assertTrue(sr.needed(n, n + "/simready_usd/payloads/geometries.usd"))
        self.assertTrue(sr.needed(n, n + "/simready_usd/payloads/PhysX/enabled.usda"))
        for no in ("/simready_usd/Textures/t.png", "/simready_usd/source_assets/a.usd",
                   "/simready_usd/.thumbs/x.usd", "/.metadata/LICENSE.txt",
                   "/com.nvidia.simready.packaging.json"):
            self.assertFalse(sr.needed(n, n + no), no)

    def test_names_never_paths(self):
        sr.check_asset_name("power_battery_9v_a01")
        for bad in ("../etc", "a/b", "", "x" * 200, "a b"):
            with self.assertRaises(sr.SimReadyError):
                sr.check_asset_name(bad)
        d = tempfile.mkdtemp()
        try:
            with self.assertRaises(sr.SimReadyError):
                sr._safe_join(d, "../outside.usd")
            self.assertTrue(sr._safe_join(d, "a/b.usd").startswith(os.path.realpath(d)))
        finally:
            shutil.rmtree(d)

    def test_usd_core_pinned(self):
        self.assertEqual(sr.USD_CORE, "usd-core==26.8")
        for f, h in sr.USD_WHEELS.items():
            self.assertIn("cp311", f)                   # the app's Python
            self.assertRegex(h, r"^[0-9a-f]{64}$")
        self.assertTrue(any("macosx" in f for f in sr.USD_WHEELS))
        self.assertTrue(any("manylinux" in f and "x86_64" in f for f in sr.USD_WHEELS))

    def test_https_only(self):
        with self.assertRaises(sr.SimReadyError):
            sr._get("http://huggingface.co/x")

    def test_verify(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "f")
            with open(p, "wb") as fh:
                fh.write(b"hello")
            sha = hashlib.sha256(b"hello").hexdigest()
            blob = hashlib.sha1(b"blob 5\0hello").hexdigest()
            self.assertIsNone(sr._verify(p, {"size": 5, "sha256": sha}))
            self.assertIsNone(sr._verify(p, {"size": 5, "git_oid": blob}))
            self.assertIn("sha256", sr._verify(p, {"size": 5, "sha256": "0" * 64}))
            self.assertIn("size", sr._verify(p, {"size": 6, "sha256": sha}))
            self.assertIn("no hash", sr._verify(p, {"size": 5}))
        finally:
            shutil.rmtree(d)

    def test_extents_frame(self):
        # Z-up metres -> mm, Y up: height goes to y.
        self.assertEqual(sr.to_library_extents([0.0175, 0.027, 0.0534], 1.0, "Z"),
                         [17.5, 53.4, 27.0])
        self.assertEqual(sr.to_library_extents([1.0, 2.0, 3.0], 0.01, "Y"),
                         [10.0, 20.0, 30.0])

    def test_words(self):
        self.assertEqual(sr.label("power_battery_9v_a01"), "Power battery 9v (a01)")
        self.assertEqual(sr.label("electricalSystem_battery_c01"),
                         "Electrical system battery (c01)")
        self.assertTrue(sr.is_electrical("power_battery_9v_a01"))
        self.assertFalse(sr.is_electrical("box_printer_white_b04"))
        self.assertFalse(sr.is_electrical("IV_pole_a01"))
        self.assertEqual(sr.guess_category("power_battery_9v_a01"), "power")
        self.assertEqual(sr.guess_category("factory_bolt_m04_loose"), "mechanical")
        self.assertEqual(sr.guess_category("detector_camera_a01"), "electronics")

    def test_part_name(self):
        import user_parts
        for a in ("power_battery_9v_a01", "IV_pole_a01",
                  "equipment_rolling_tool_chest_cabinet_combo_d01"):
            n = sr.part_name(a)
            user_parts.check_name(n)
            self.assertTrue(n.startswith("sr_"))

    def test_search(self):
        names = [n for n, _ in sr.search()]
        self.assertEqual(names[0], "consumable_fuse_midi_yellow_a01")     # smallest first
        self.assertEqual([n for n, _ in sr.search("battery 9v")], ["power_battery_9v_a01"])
        self.assertEqual({n for n, _ in sr.search(electrical=True)},
                         {"power_battery_9v_a01", "consumable_fuse_midi_yellow_a01"})
        self.assertNotIn("IV_pole_a01", [n for n, _ in sr.search(max_mm=300)])


class TestShippedIndex(unittest.TestCase):

    def test_index(self):
        with open(sr.INDEX, encoding="utf-8") as fh:
            idx = json.load(fh)
        self.assertEqual(len(idx["revision"]), 40)
        self.assertEqual(idx["count"], len(idx["assets"]))
        self.assertGreater(idx["count"], 500)
        for name, e in idx["assets"].items():
            sr.check_asset_name(name)
            self.assertTrue(e["root"].startswith("simready_usd/"), name)
            if e.get("size_mm") is not None:
                self.assertEqual(len(e["size_mm"]), 3, name)
                self.assertTrue(all(v >= 0 for v in e["size_mm"]), name)


# A Z-up stage in millimetres: one quad (10 x 20 mm, 0..5 mm tall via a
# second quad), drawn through an instance; a guide-purpose collision box and
# an invisible mesh that must both be left out.
USDA = '''#usda 1.0
(
    metersPerUnit = 0.001
    upAxis = "Z"
    defaultPrim = "Root"
)

class "Proto"
{
    def Mesh "Shape"
    {
        int[] faceVertexCounts = [4, 4]
        int[] faceVertexIndices = [0, 1, 2, 3, 4, 5, 6, 7]
        point3f[] points = [(0, 0, 0), (10, 0, 0), (10, 20, 0), (0, 20, 0),
                            (0, 0, 5), (10, 0, 5), (10, 20, 5), (0, 20, 5)]
    }
}

def Xform "Root"
{
    def Xform "Part" (
        instanceable = true
        inherits = </Proto>
    )
    {
        double3 xformOp:translate = (100, 0, 0)
        uniform token[] xformOpOrder = ["xformOp:translate"]
    }

    def Mesh "Collision"
    {
        uniform token purpose = "guide"
        int[] faceVertexCounts = [3]
        int[] faceVertexIndices = [0, 1, 2]
        point3f[] points = [(0, 0, 0), (900, 0, 0), (0, 900, 0)]
    }

    def Mesh "Hidden"
    {
        token visibility = "invisible"
        int[] faceVertexCounts = [3]
        int[] faceVertexIndices = [0, 1, 2]
        point3f[] points = [(0, 0, 0), (0, 0, 700), (0, 700, 0)]
    }
}
'''


@unittest.skipIf(USD is None, "usd-core not available (set ATELIER_USD_DIR)")
class TestConverter(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="r760_usd_")
        self.env = os.environ.get("ATELIER_USD_DIR")
        os.environ["ATELIER_USD_DIR"] = USD

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)
        if self.env is None:
            os.environ.pop("ATELIER_USD_DIR", None)
        else:
            os.environ["ATELIER_USD_DIR"] = self.env

    def test_convert(self):
        src = os.path.join(self.d, "part.usda")
        with open(src, "w") as fh:
            fh.write(USDA)
        out = os.path.join(self.d, "part.stl")
        rep = sr.convert(src, out)
        self.assertEqual(rep["triangles"], 4, rep)         # two quads, fanned
        self.assertEqual(rep["meshes"], 1, rep)            # the instance only
        self.assertGreaterEqual(rep["skipped"], 2, rep)    # guide + invisible
        self.assertEqual(rep["up_axis"], "Z")
        self.assertEqual(rep["size_mm"], [10.0, 5.0, 20.0], rep)   # Y up
        with open(out, "rb") as fh:
            data = fh.read()
        self.assertEqual(len(data), 84 + 50 * 4)
        import struct
        xs = [struct.unpack_from("<12f", data, 84 + 50 * i)[3::3] for i in range(4)]
        self.assertTrue(all(100.0 <= x <= 110.0 for row in xs for x in row), xs)

    def test_no_mesh(self):
        src = os.path.join(self.d, "empty.usda")
        with open(src, "w") as fh:
            fh.write('#usda 1.0\ndef Xform "Root"\n{\n}\n')
        with self.assertRaises(sr.SimReadyError) as cm:
            sr.convert(src, os.path.join(self.d, "x.stl"))
        self.assertIn("no drawn mesh", str(cm.exception))


@unittest.skipIf(sd is None, "PySide6 not installed")
class TestDialog(FakeIndex, unittest.TestCase):

    def test_browse_and_install(self):
        calls = []

        class Fake(object):
            label = staticmethod(sr.label)
            search = staticmethod(sr.search)
            index = staticmethod(sr.index)

            @staticmethod
            def installed():
                return {"power_battery_9v_a01": "sr_power_battery_9v_a01"}

            @staticmethod
            def thumbnail(name, d):
                return None

            @staticmethod
            def install(name, progress=None):
                progress("Downloading %s" % name, 0.5)
                calls.append(name)
                return "sr_" + name, {}
        done = []
        d = sd.SimReadyDialog(None, on_done=done.append, sr=Fake)
        rows = [d.list.item(i).text() for i in range(d.list.count())]
        self.assertEqual(len(rows), 2, rows)               # electrical + desk
        self.assertTrue(any("installed" in r for r in rows), rows)
        d.only_desk.setChecked(False)
        d.only_elec.setChecked(False)
        self.assertEqual(d.list.count(), 4)
        d.query.setText("fuse")
        self.assertEqual(d.list.count(), 1)
        self.assertIn("5.2 × 22.2 × 18.7 mm", d.info.text())
        d.install()
        t0 = time.time()
        while not done and time.time() - t0 < 10:
            _APP.processEvents()
            time.sleep(0.01)
        self.assertEqual(calls, ["consumable_fuse_midi_yellow_a01"])
        self.assertEqual(done, ["sr_consumable_fuse_midi_yellow_a01"])
        self.assertIn("Installed", d.status.text())

    def test_failure_is_shown(self):
        class Fake(object):
            label = staticmethod(sr.label)
            search = staticmethod(sr.search)
            index = staticmethod(sr.index)
            installed = staticmethod(lambda: {})
            thumbnail = staticmethod(lambda n, d: None)

            @staticmethod
            def install(name, progress=None):
                raise sr.SimReadyError("sha256 abc, expected def - not installed")
        d = sd.SimReadyDialog(None, sr=Fake)
        d.install()
        t0 = time.time()
        while "not installed" not in d.status.text() and time.time() - t0 < 10:
            _APP.processEvents()
            time.sleep(0.01)
        self.assertIn("not installed", d.status.text())
        self.assertTrue(d.list.isEnabled())


@unittest.skipIf(not (os.environ.get("ATELIER_NET_TESTS") and FC and USD),
                 "set ATELIER_NET_TESTS=1 (needs network, freecadcmd, usd-core)")
class TestRealInstall(unittest.TestCase):

    def test_fuse(self):
        d = tempfile.mkdtemp(prefix="r760_net_")
        script = os.path.join(d, "run.py")
        with open(script, "w") as fh:
            fh.write("import sys, json\nsys.path.insert(0, %r)\n"
                     "import simready, atech_modules as am\n"
                     "n, sp = simready.install('consumable_fuse_midi_yellow_a01')\n"
                     "print('R760=' + json.dumps([n, sp['dimensions_mm'], "
                     "sp['licence'], am.is_user_part(n)]))\n"
                     % os.path.join(REPO, "projects"))
        try:
            env = dict(os.environ, ATELIER_PARTS=os.path.join(d, "parts"),
                       ATELIER_USD_DIR=USD, ATECH_ARTIFACTS=MODELS)
            out = subprocess.run([FC, script], env=env, capture_output=True,
                                 text=True, timeout=900).stdout
        finally:
            shutil.rmtree(d, ignore_errors=True)
        line = [ln for ln in out.splitlines() if ln.startswith("R760=")]
        self.assertTrue(line, out[-2000:])
        n, dims, lic, mine = json.loads(line[0][5:])
        self.assertEqual(n, "sr_consumable_fuse_midi_yellow_a01")
        self.assertAlmostEqual(dims["y"], 22.2, delta=0.2)
        self.assertEqual(lic, "CC BY 4.0")
        self.assertTrue(mine)


if __name__ == "__main__":
    unittest.main()
