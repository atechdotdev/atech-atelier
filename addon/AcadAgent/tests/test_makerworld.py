"""R900 MakerWorld: From MakerWorld... and Publish to MakerWorld...

  TestGeometry   fc_makerworld.py under freecadcmd: a Bambu Studio 3MF
                 read and added, the bundle made and refused
  TestPure       links, the newest download, licences carried over, the
                 description text
  TestWindows    the two windows, offscreen Qt, no FreeCAD; the menus

    QT_QPA_PLATFORM=offscreen python -m unittest -v test_makerworld
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

from acadagent import makerworld as mw                    # noqa: E402

try:
    from PySide6 import QtWidgets
    APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except ImportError:
    QtWidgets = None


def _fc():
    try:
        from acadagent import sandbox
        return sandbox.find_freecadcmd()
    except Exception:                                      # noqa: BLE001
        return os.environ.get("ATECH_FREECADCMD")


FC = _fc()


@unittest.skipIf(FC is None, "freecadcmd not found (set ATECH_FREECADCMD)")
class TestGeometry(unittest.TestCase):
    def test_fc_makerworld(self):
        home = tempfile.mkdtemp(prefix="atech-mw-")
        env = {"HOME": home, "FREECAD_USER_HOME": home, "PATH": "/usr/bin:/bin"}
        p = subprocess.run([FC, os.path.join(HERE, "fc_makerworld.py")], env=env,
                           cwd=home, capture_output=True, text=True, timeout=300)
        line = [ln for ln in (p.stdout + p.stderr).splitlines()
                if ln.startswith("MAKERWORLD_RESULT=")]
        self.assertTrue(line, (p.stdout + p.stderr)[-2000:])
        r = json.loads(line[-1].split("=", 1)[1])
        failed = [k for k, v in r["checks"].items() if not v]
        self.assertTrue(r["ok"], (failed, r["errors"]))
        self.assertGreaterEqual(len(r["checks"]), 15)


class TestPure(unittest.TestCase):
    def test_parse_link(self):
        i = mw.parse_link("look: https://makerworld.com/en/models/123456-cable-clip-v2#profileId-9")
        self.assertEqual(i["id"], "123456")
        self.assertEqual(i["title"], "Cable clip v2")
        self.assertEqual(i["url"], "https://makerworld.com/en/models/123456-cable-clip-v2")
        self.assertEqual(mw.parse_link("https://makerworld.com/models/77")["url"],
                         "https://makerworld.com/en/models/77")
        self.assertEqual(mw.parse_link("https://makerworld.com/zh-hans/models/5-x")["id"], "5")
        self.assertTrue(mw.parse_link("https://makerworld.com.cn/zh/models/9")["url"]
                        .startswith("https://makerworld.com.cn/"))
        for bad in ("", "https://printables.com/model/1", "https://makerworld.com/en/u/me",
                    "https://evil.com/makerworld.com/models/1x"):
            # the link must be on MakerWorld's own host
            self.assertIsNone(mw.parse_link(bad), bad)

    def test_newest_download(self):
        d = tempfile.mkdtemp()
        old = os.path.join(d, "old.stl")
        new = os.path.join(d, "new.3mf")
        part = os.path.join(d, "half.3mf.crdownload")
        for p in (old, new, part):
            open(p, "w").close()
        os.utime(old, (time.time() - 100, time.time() - 100))
        self.assertEqual(mw.newest_download(0, d), new)
        self.assertIsNone(mw.newest_download(time.time() + 50, d))
        self.assertIsNone(mw.newest_download(0, os.path.join(d, "nope")))

    def test_licence_terms_carry_over(self):
        self.assertTrue(mw._at_least("cc-by-nc-sa", "cc-by-sa"))
        self.assertTrue(mw._at_least("cc-by-sa", "cc-by"))
        self.assertFalse(mw._at_least("cc-by", "cc-by-sa"))
        self.assertFalse(mw._at_least("cc-by-sa", "cc-by-nc"))
        self.assertFalse(mw._at_least("sdfl", "cc-by"))

    def test_description(self):
        t = mw.description("Clip", "Holds cables.", {
            "remix": ["Clip by Ana (CC BY), https://makerworld.com/en/models/1"],
            "licence": "cc-by"})
        self.assertTrue(t.startswith("Clip\n\nHolds cables.\n"))
        self.assertIn("Remix of:\n- Clip by Ana", t)
        self.assertIn("Licence: CC BY", t)
        self.assertIn(mw.MADE_WITH, t)


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestWindows(unittest.TestCase):
    def test_import_dialog(self):
        opened = []
        d = mw.ImportDialog(None, opener=opened.append)
        try:
            self.assertFalse(d.btn_page.isEnabled())
            self.assertFalse(d.ok.isEnabled())
            d.link.setText("https://makerworld.com/en/models/42-cable-clip")
            self.assertTrue(d.btn_page.isEnabled())
            d.btn_page.click()
            self.assertEqual(opened, ["https://makerworld.com/en/models/42-cable-clip"])
            p = os.path.join(tempfile.mkdtemp(), "clip.3mf")
            open(p, "w").close()
            d.file.setText(p)
            self.assertTrue(d.ok.isEnabled())
            d.author.setText("Ana")
            v = d.values()
            self.assertEqual(v["label"], "Cable clip")
            self.assertEqual(v["source"]["author"], "Ana")
            self.assertEqual(v["source"]["url"], "https://makerworld.com/en/models/42-cable-clip")
            d.licence.setCurrentIndex(d.licence.findData("sdfl"))
            self.assertIn("cannot be published", d.status.text())
            d.link.setText("https://printables.com/model/1")
            self.assertFalse(d.ok.isEnabled())
        finally:
            d.close()

    def test_publish_dialog_without_document(self):
        opened = []
        d = mw.PublishDialog(None, doc=None, opener=opened.append)
        try:
            self.assertFalse(d.btn_make.isEnabled())
            self.assertIn("Open a design first", d.checks.text())
            self.assertFalse(d.btn_folder.isEnabled())
            d.btn_site.click()
            self.assertEqual(opened, [mw.UPLOAD_URL])
        finally:
            d.close()

    def test_menu_commands(self):
        from acadagent import shell
        self.assertIn("mwimport", {c[3] for c in shell.TOOL_COMMANDS})
        self.assertIn("mwpublish", {c[3] for c in shell.EXPORT_COMMANDS})
        ids = [c[0] for c in shell.TOOL_COMMANDS + shell.EXPORT_COMMANDS]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
