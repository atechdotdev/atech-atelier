#!/usr/bin/env python3
"""R52: every @Token a shipped stylesheet asks for is defined by our themes.

FreeCAD resolves @Token references in every sheet it loads -- the main
StyleSheet AND the overlay sheet (OverlayManager.cpp:141) -- through
StyleParameters::ParameterManager, and logs "Requested non-existent style
parameter token '<name>'" for each one no source defines
(ParameterManager.cpp:355). MEASURED in the dogfood rig (a tree built before
build_theme.py inherited upstream's keys): 52 such lines in 13 minutes for
IconsLocationFolderName / StylesheetIconsColor / GeneralGridLinesColor, all
from overlay/"Freecad Overlay.qss", and the notification badge grew on every
stylesheet reload.

The reference is upstream's own sheets, which our generator cannot agree
with by construction (CLAUDE.md P2). Found in, in order: a built tree
(dist/build/squashfs-root/usr/share/Gui/Stylesheets) or the pinned source
checkout (tools/freecad-src/src/Gui/Stylesheets). Neither is tracked, so the
test SKIPS -- it does not pass -- on a clean clone.

    python3 branding/tests/test_theme_tokens.py   -> THEME_TOKENS_TESTS_OK
"""
import glob
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
THEMES = os.path.join(REPO, "branding", "assets", "theme")
CANDIDATES = [
    os.path.join(REPO, "dist", "build", "squashfs-root", "usr", "share",
                 "Gui", "Stylesheets"),
    os.path.join(REPO, "tools", "freecad-src", "src", "Gui", "Stylesheets"),
]
# Defined by BuiltInParameterSource from BaseApp/Preferences/Themes, not by
# any YAML (StyleParameters/ParameterManager.h:283-286, FreeCAD 1.1.3).
BUILT_IN = {"ThemeAccentColor1", "ThemeAccentColor2", "ThemeAccentColor3"}
# Same token grammar FreeCAD's regex accepts for "@Name" (letters, digits, _).
TOKEN = re.compile(r"@([A-Za-z0-9_]+)")


def upstream_dir():
    for d in CANDIDATES:
        if os.path.isfile(os.path.join(d, "FreeCAD.qss")):
            return d
    return None


def sheets(updir):
    out = [os.path.join(updir, "FreeCAD.qss")]
    out += sorted(glob.glob(os.path.join(updir, "overlay", "*.qss")))
    out += sorted(glob.glob(os.path.join(REPO, "brand", "assets",
                                         "Atech*.qss")))
    return out


def referenced(path):
    with open(path, encoding="utf-8") as fh:
        text = re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)
    return set(TOKEN.findall(text))


def defined_and_used(yaml_path):
    """(keys defined, tokens referenced by the values) of a theme YAML."""
    keys, used = set(), set()
    with open(yaml_path, encoding="utf-8") as fh:
        for line in fh:
            if line.lstrip().startswith("#") or ":" not in line:
                continue
            if line.startswith((" ", "\t")):
                continue
            k, v = line.split(":", 1)
            keys.add(k.strip())
            used |= set(TOKEN.findall(v))
    return keys, used


def missing(yaml_path, sheet_paths):
    keys, used = defined_and_used(yaml_path)
    want = set(used)
    for s in sheet_paths:
        want |= referenced(s)
    return sorted(want - keys - BUILT_IN)


class ThemeTokens(unittest.TestCase):
    def setUp(self):
        self.up = upstream_dir()
        if not self.up:
            self.skipTest("no upstream Gui/Stylesheets (build the tree or "
                          "check out tools/freecad-src)")
        self.sheets = sheets(self.up)
        self.themes = sorted(glob.glob(os.path.join(THEMES, "*.yaml")))
        self.assertEqual(len(self.themes), 2, self.themes)

    def test_overlay_sheet_is_scanned(self):
        # The three R52 tokens live in the overlay sheet; a scan that skips
        # it passes over exactly the defect it exists for.
        names = [os.path.basename(s) for s in self.sheets]
        self.assertIn("Freecad Overlay.qss", names)

    def test_every_token_resolves(self):
        for t in self.themes:
            with self.subTest(theme=os.path.basename(t)):
                self.assertEqual(missing(t, self.sheets), [],
                                 "%s leaves tokens undefined" % t)

    def test_r52_tokens_defined(self):
        for t in self.themes:
            keys, _ = defined_and_used(t)
            for k in ("IconsLocationFolderName", "StylesheetIconsColor",
                      "GeneralGridLinesColor"):
                self.assertIn(k, keys, "%s lacks %s" % (t, k))

    def test_sabotage_is_caught(self):
        # Drop one R52 token from a copy: the check must name it.
        import tempfile
        src = self.themes[0]
        with open(src, encoding="utf-8") as fh:
            lines = [ln for ln in fh
                     if not ln.startswith("IconsLocationFolderName:")]
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False,
                                         encoding="utf-8") as fh:
            fh.writelines(lines)
            broken = fh.name
        try:
            self.assertIn("IconsLocationFolderName",
                          missing(broken, self.sheets))
        finally:
            os.unlink(broken)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    ok = r.wasSuccessful() and not r.skipped
    if ok:
        print("THEME_TOKENS_TESTS_OK")
    elif r.wasSuccessful():
        print("THEME_TOKENS_TESTS_SKIPPED")
    sys.exit(0 if r.wasSuccessful() else 1)
