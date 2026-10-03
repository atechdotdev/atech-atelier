#!/usr/bin/env python3
"""R39 / ADR-006: one version from the repo's VERSION, stamped where the build says.

Unit checks of release_meta.py and of the release wiring in build_appimage.sh,
plus the real validators on the stamped output when they are installed
(desktop-file-validate, appstreamcli): a stamp the validators reject would
fail the build at section 4.

    python3 branding/tests/test_release_meta.py   -> RELEASE_META_TESTS_OK
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
BRANDING = os.path.dirname(HERE)
REPO = os.path.dirname(BRANDING)
sys.path.insert(0, BRANDING)

import release_meta as rm  # noqa: E402

APP_ID = "dev.atech.Atelier"
BUILD = os.path.join(BRANDING, "build_appimage.sh")
METAINFO = os.path.join(BRANDING, APP_ID + ".metainfo.xml")
DESKTOP = os.path.join(BRANDING, APP_ID + ".desktop")


def _read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def _stamped_metainfo(urls=()):
    xml = rm.stamp_metainfo(_read(METAINFO), rm.read_version(), "2026-10-04")
    return rm.stamp_screenshots(xml, list(urls))


class ReleaseMeta(unittest.TestCase):
    def test_version_is_the_repo_root_file(self):
        self.assertEqual(os.path.realpath(rm.VERSION_FILE),
                         os.path.realpath(os.path.join(REPO, "VERSION")))
        self.assertEqual(rm.read_version(), _read(os.path.join(REPO, "VERSION")).strip())
        # The retired second copy must not come back: two files can disagree.
        self.assertFalse(os.path.exists(os.path.join(BRANDING, "VERSION")))

    def test_bad_versions_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ("", "1.0", "v1.0.0", "1.0.0\n2.0.0\n", "latest"):
                p = os.path.join(d, "VERSION")
                with open(p, "w") as fh:
                    fh.write(bad)
                with self.assertRaises(ValueError, msg=repr(bad)):
                    rm.read_version(p)

    def test_out_name_carries_version(self):
        self.assertEqual(rm.out_name("1.2.3"), "AtechAtelier-1.2.3-x86_64.AppImage")

    def test_build_release_wiring(self):
        src = _read(BUILD)
        self.assertIn('release_meta.py" outname', src)
        self.assertIn('APP_ID="%s"' % APP_ID, src)
        self.assertNotIn("AtechStudio-", src)
        self.assertNotIn('APP_ID="dev.atech.Studio"', src)
        # update info: the decided channel, embedded only when -u is accepted
        self.assertIn('gh-releases-zsync|$GH_OWNER|$GH_REPO|latest|AtechAtelier-*x86_64.AppImage.zsync', src)
        self.assertIn('GH_OWNER="atechdotdev"', src)
        self.assertIn('GH_REPO="atech-atelier"', src)
        self.assertIn('"$HERE/repack.sh" "$ROOT" "$OUT"', src)
        self.assertIn('ATECH_DEFAULT_UPDATE_INFO="$DEFAULT_UPDATE_INFO"', src)
        # appimagetool is never fetched: no URL to it in either script
        rp = _read(os.path.join(BRANDING, "repack.sh"))
        for text in (src, rp):
            self.assertNotRegex(text, r"https?://\S*appimagetool")
        # the branches themselves are exercised by tests/test_repack.sh
        # doc dir renamed; every release licence file is installed
        self.assertIn('DOC_NAME="atech-atelier"', src)
        self.assertIn("LICENSE_FILES=(LICENSE LICENSE-models.md NOTICE)", src)
        self.assertIn('"$AA/data/models/LICENSE-models.md"', src)

    def test_desktop_template(self):
        t = _read(DESKTOP)
        self.assertIn("\nName=Atech Atelier\n", t)
        self.assertIn("\nIcon=%s\n" % APP_ID, t)
        self.assertNotIn("Studio", t)

    def test_desktop_stamp(self):
        d = rm.stamp_desktop(_read(DESKTOP), "1.2.3")
        self.assertEqual(d.count("X-AppImage-Version="), 1)
        self.assertIn("\nX-AppImage-Version=1.2.3\n", d)
        # restamping replaces, never duplicates
        d2 = rm.stamp_desktop(d, "1.2.4")
        self.assertEqual(d2.count("X-AppImage-Version="), 1)
        self.assertIn("X-AppImage-Version=1.2.4", d2)
        # stays inside [Desktop Entry] when another group follows
        g = rm.stamp_desktop("[Desktop Entry]\nName=x\n[Desktop Action a]\nName=y\n", "1.0.0")
        self.assertLess(g.index("X-AppImage-Version"), g.index("[Desktop Action"))

    def test_metainfo_stamp(self):
        xml = _read(METAINFO)
        out = rm.stamp_metainfo(xml, "1.2.3", "2026-09-25")
        self.assertIn('<release version="1.2.3" date="2026-09-25">', out)
        self.assertNotIn(rm.MARKER, out)
        with self.assertRaises(ValueError):
            rm.stamp_metainfo(out, "1.2.3", "2026-09-25")   # marker gone
        with self.assertRaises(ValueError):
            rm.stamp_metainfo(xml, "1.2.3", "25/09/2026")

    def test_metainfo_fields(self):
        root = ET.fromstring(_stamped_metainfo())
        self.assertEqual(root.findtext("id"), APP_ID)
        self.assertEqual(root.findtext("name"), "Atech Atelier")
        self.assertEqual(root.findtext("project_license"),
                         "LGPL-2.1-or-later AND CC-BY-NC-4.0")
        self.assertEqual(root.findtext("launchable"), APP_ID + ".desktop")
        self.assertEqual(root.find("url[@type='homepage']").text,
                         "https://github.com/atechdotdev/atech-atelier")
        self.assertIsNotNone(root.find("content_rating[@type='oars-1.1']"))
        rel = root.find("releases/release")
        self.assertEqual(rel.get("version"), rm.read_version())

    def test_screenshots_placeholder_is_flagged(self):
        out = _stamped_metainfo()
        self.assertIn("SCREENSHOTS: PLACEHOLDER", out)
        self.assertIsNone(ET.fromstring(out).find("screenshots"))
        two = _stamped_metainfo(["https://example.org/a.png", "https://example.org/b.jpg"])
        shots = ET.fromstring(two).findall("screenshots/screenshot")
        self.assertEqual([s.get("type") for s in shots], ["default", None])
        for bad in (["http://example.org/a.png"], ["https://example.org/a.gif"],
                    ["https://example.org/a b.png"]):
            with self.assertRaises(ValueError, msg=bad):
                _stamped_metainfo(bad)

    @unittest.skipUnless(shutil.which("desktop-file-validate"), "no desktop-file-validate")
    def test_desktop_validates(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, APP_ID + ".desktop")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(rm.stamp_desktop(_read(DESKTOP), rm.read_version()))
            r = subprocess.run(["desktop-file-validate", p], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((r.stdout + r.stderr).strip(), "")

    @unittest.skipUnless(shutil.which("appstreamcli"), "no appstreamcli")
    def test_metainfo_validates(self):
        for urls in ((), ("https://example.org/main.png",)):
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, APP_ID + ".metainfo.xml")
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(_stamped_metainfo(urls))
                r = subprocess.run(["appstreamcli", "validate", "--no-net", p],
                                   capture_output=True, text=True)
                out = r.stdout + r.stderr
                self.assertEqual(r.returncode, 0, out)
                self.assertNotRegex(out, r"(?m)^[EW]:", out)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    if r.wasSuccessful():
        print("RELEASE_META_TESTS_OK")
    sys.exit(0 if r.wasSuccessful() else 1)
