#!/usr/bin/env python3
"""R88: the Tasks overlay panel's title bar is styled, in both themes.

What the GUI pass found (Part_Primitives, dogfood rig): "Tasks" twice, the
title-bar buttons shrunk to specks, one of them a solid bright-green square,
and a stray "x" beside the panel. MEASURED causes, each pinned here:

1. OverlayToolButtons are fixed 17 px squares; the application sheet's
   generic QToolButton rule gave them 4 px padding + 1 px border, leaving
   7 px for the icon. -> the app sheets carry a Gui--OverlayToolButton rule
   with zero padding.
2. The overlay panel takes a SEPARATE sheet (MainWindow/
   OverlayActiveStyleSheet). Upstream's fills a checked button with
   @ThemeAccentColor1 = our accent. A widget's own sheet beats the app sheet,
   so only a sheet of our own can change that. -> "Atech Overlay.qss" ships,
   the template selects it, every colour in it is a theme token both YAMLs
   define, and no checked rule fills with ThemeAccentColor1.
3. FreeCAD 1.1.3 draws the dock's own caption inside the panel as well as
   the panel's (the stock AppImage does it too). -> the dock caption inside
   an overlay is drawn in no colour.
4. The right panel defaults to transparent mode, which makes every child
   WA_NoSystemBackground: the 3D view's axis label shows through the gaps.
   -> the template seeds OverlayRight/Transparent = 0.

The checks read the WRITTEN files (sheets, YAMLs, template) as text, not the
generators' tables, so they cannot agree with the generator by construction.
The GUI half (screenshots, both themes) is in the R88 evidence.

    python3 branding/tests/test_overlay_sheet.py   -> OVERLAY_SHEET_TESTS_OK
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ASSETS = os.path.join(REPO, "brand", "assets")
OVERLAY = os.path.join(ASSETS, "Atech Overlay.qss")
THEMES = os.path.join(REPO, "branding", "assets", "theme")
TEMPLATE = os.path.join(REPO, "branding", "assets", "atech_user_template.cfg")
BUILT_IN = {"ThemeAccentColor1", "ThemeAccentColor2", "ThemeAccentColor3"}
TOKEN = re.compile(r"@([A-Za-z0-9_]+)")
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def body(path):
    with open(path, encoding="utf-8") as fh:
        return re.sub(r"/\*.*?\*/", "", fh.read(), flags=re.S)


def rules(text):
    """[(selector text, declarations text)] of a QSS body."""
    return [(s.strip(), d) for s, d in re.findall(r"([^{}]+)\{([^{}]*)\}",
                                                  text)]


def decls_for(text, selector):
    """Declarations of every rule whose selector list names `selector`."""
    out = []
    for sel, d in rules(text):
        if selector in [x.strip() for x in sel.split(",")]:
            out.append(d)
    return "\n".join(out)


def yaml_keys(path):
    keys = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if ":" in line and not line.startswith(("#", " ", "\t")):
                keys.add(line.split(":", 1)[0].strip())
    return keys


class AppSheets(unittest.TestCase):
    def test_overlay_buttons_have_no_padding(self):
        for name in ("AtechLight.qss", "AtechDark.qss"):
            with self.subTest(sheet=name):
                d = decls_for(body(os.path.join(ASSETS, name)),
                              "Gui--OverlayToolButton")
                self.assertRegex(d, r"padding:\s*0",
                                 "%s: overlay buttons inherit QToolButton "
                                 "padding (icons shrink to 7 px)" % name)

    def test_spin_boxes_have_step_buttons(self):
        # Every number in a task panel is a Gui::QuantitySpinBox; styled with
        # a border but no ::up-button rule, the steps were blank slots.
        for name in ("AtechLight.qss", "AtechDark.qss"):
            text = body(os.path.join(ASSETS, name))
            for sub in ("::up-arrow", "::down-arrow"):
                with self.subTest(sheet=name, sub=sub):
                    self.assertIn("image", decls_for(
                        text, "Gui--QuantitySpinBox" + sub))

    def test_task_boxes_have_a_surface_and_text(self):
        for name in ("AtechLight.qss", "AtechDark.qss"):
            text = body(os.path.join(ASSETS, name))
            with self.subTest(sheet=name):
                self.assertIn("background", decls_for(
                    text, 'QSint--ActionGroup QFrame[class="content"]'))
                self.assertIn("color", decls_for(
                    text, 'QSint--ActionGroup QToolButton[class="header"]'))


class OverlaySheet(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(OVERLAY), "not built: %s" % OVERLAY)
        self.text = body(OVERLAY)

    def test_no_colour_literals(self):
        # One file serves both modes; a hex literal cannot follow the theme.
        self.assertEqual(sorted(set(HEX.findall(self.text))), [])

    def test_every_token_defined_in_both_themes(self):
        want = set(TOKEN.findall(self.text)) - BUILT_IN
        self.assertTrue(want, "overlay sheet references no tokens at all")
        for mode in ("Light", "Dark"):
            path = os.path.join(THEMES, "Atech Atelier %s.yaml" % mode)
            with self.subTest(theme=mode):
                self.assertEqual(sorted(want - yaml_keys(path)), [])

    def test_checked_button_is_not_an_accent_fill(self):
        for sel in ("Gui--OverlayToolButton:checked",
                    "Gui--OverlayToolButton:pressed"):
            d = decls_for(self.text, sel)
            with self.subTest(selector=sel):
                self.assertTrue(d, "no rule for %s" % sel)
                fill = re.findall(r"background(?:-color)?:\s*([^;]+);", d)
                self.assertTrue(fill)
                for v in fill:
                    self.assertNotIn("Accent", v,
                                     "%s filled with an accent: %s" % (sel, v))
                self.assertIn("@AccentColor", d,
                              "checked state lost its accent outline")

    def test_dock_caption_hidden_inside_overlay(self):
        d = decls_for(self.text,
                      "Gui--OverlayTabWidget QDockWidget > Gui--OverlayTitleBar")
        self.assertRegex(d, r"color:\s*transparent")
        # ...and ONLY inside an overlay: the panel's own bar keeps its text.
        panel = decls_for(self.text, "Gui--OverlayTitleBar")
        self.assertNotRegex(panel, r"color:\s*transparent")

    def test_buttons_have_no_padding(self):
        self.assertRegex(decls_for(self.text, "Gui--OverlayToolButton"),
                         r"padding:\s*0")

    def test_generator_gate_catches_a_literal(self):
        # The build gate (build_qss.verify_overlay) must fail a sheet with a
        # hand-typed colour. Proven on a copy, never on the real file.
        sys.path.insert(0, os.path.join(REPO, "brand", "tools"))
        import build_qss
        with open(OVERLAY, encoding="utf-8") as fh:
            src = fh.read()
        self.assertTrue(build_qss.verify_overlay(OVERLAY)["ok"])
        with tempfile.NamedTemporaryFile("w", suffix=".qss", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(src.replace("@AccentColor", "#0FF2B2", 1))
            broken = fh.name
        try:
            v = build_qss.verify_overlay(broken)
            self.assertFalse(v["ok"])
            self.assertIn("#0ff2b2", v["why"])
        finally:
            os.unlink(broken)


# --------------------------------------------------------------------- R118
# Upstream's icon files, which the sheets reference by name and which our
# generator cannot agree with by construction: the glyph colour is read out
# of the SVG itself. Not tracked, so the R118 icon checks SKIP (not pass) on
# a clean clone, as test_theme_tokens.py does.
STYLESHEET_DIRS = [
    os.environ.get("ATECH_STYLESHEETS", ""),
    os.path.join(REPO, "dist", "build", "squashfs-root", "usr", "share",
                 "Gui", "Stylesheets"),
    os.path.join(REPO, "dist", "test-root", "usr", "share", "Gui",
                 "Stylesheets"),
    os.path.join(REPO, "tools", "freecad-src", "src", "Gui", "Stylesheets"),
]
BUTTONS = ("OBTN Float", "OBTN Overlay", "OBTN AutoMode", "OBTN Transparent")
SVG_HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def stylesheet_dir():
    for d in STYLESHEET_DIRS:
        if d and os.path.isfile(os.path.join(d, "images_classic",
                                             "close-white.svg")):
            return d
    return None


def yaml_values(path):
    """{key: value} of a flat theme YAML ("Key: "#hex"" or "Key: word")."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if ":" not in line or line.startswith(("#", " ", "\t")):
                continue
            k, _, v = line.partition(":")
            v = v.strip()
            if v[:1] in ("'", '"'):
                v = v[1:v.index(v[0], 1)]
            else:
                v = v.split("#", 1)[0].strip()
            out[k.strip()] = v
    return out


def luminance(hexcol):
    h = hexcol.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
         for v in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def resolve(url, values, sdir):
    """File behind url(qss:...) with @Tokens substituted, or None."""
    m = re.search(r"url\(qss:([^)]+)\)", url)
    if not m:
        return None
    rel = TOKEN.sub(lambda t: values.get(t.group(1), "@" + t.group(1)),
                    m.group(1))
    return os.path.join(sdir, rel)


def glyph_contrast(svg, ground):
    """Best contrast of any colour the SVG paints against `ground`: the
    glyph's own colour, since the outlines some upstream icons carry are
    black on every variant."""
    with open(svg, encoding="utf-8") as fh:
        cols = {"#" + m for m in SVG_HEX.findall(fh.read())}
    return max((contrast(c, ground) for c in cols), default=0.0)


class Icons(unittest.TestCase):
    """R118: the dark overlay's title-bar icons and the task dialog's Close
    icon read on their ground; task boxes let no default-palette pixel
    through at their rounded corners.

    MEASURED before the fix (isolated offscreen instance, dark theme,
    Part_Primitives): the dock's Float button max luma 0 (built-in black
    glyph, no rule), its Overlay button 136 (upstream lightgray, #888), the
    Close icon mean luma 21, header corner pixels 221/230 on a 25 ground.
    After: 255, 255, 255 and 21/18.

    Criteria, each against a reference outside the generator: WCAG 1.4.11
    non-text contrast (3:1) for every resting icon in both modes, and in the
    dark mode at least the contrast of the muted caption drawn beside the
    buttons (the lightgray glyph was the dimmest thing on the bar)."""

    def setUp(self):
        self.sdir = stylesheet_dir()
        if not self.sdir:
            self.skipTest("no built tree / upstream Stylesheets dir")
        self.vals = {m: yaml_values(os.path.join(
            THEMES, "Atech Atelier %s.yaml" % m.capitalize()))
            for m in ("light", "dark")}
        self.overlay = body(OVERLAY)

    def _bar(self, mode):
        v = self.vals[mode]
        return v["AtechPanelColor"], v["AtechMutedColor"]

    def _check_icon(self, url, mode, where):
        ground, muted = self._bar(mode)
        path = resolve(url, self.vals[mode], self.sdir)
        self.assertIsNotNone(path, "%s: no url(qss:...) in %r" % (where, url))
        self.assertTrue(os.path.isfile(path), "%s: %s does not exist"
                        % (where, path))
        c = glyph_contrast(path, ground)
        self.assertGreaterEqual(c, 3.0, "%s: %s is %.2f:1 on %s"
                                % (where, os.path.basename(path), c, ground))
        if mode == "dark":
            floor = contrast(muted, ground)
            self.assertGreaterEqual(
                c, floor, "%s: %s (%.2f:1) reads fainter than the caption "
                "(%.2f:1)" % (where, os.path.basename(path), c, floor))

    def test_overlay_buttons_have_readable_resting_icons(self):
        for name in BUTTONS:
            d = decls_for(self.overlay,
                          'Gui--OverlayToolButton[objectName="%s"]' % name)
            m = re.search(r"image:\s*([^;]+);", d)
            for mode in ("light", "dark"):
                with self.subTest(button=name, mode=mode):
                    self.assertIsNotNone(m, "overlay sheet: no resting image "
                                            "for %s (built-in glyph)" % name)
                    self._check_icon(m.group(1), mode, "overlay " + name)

    def test_app_sheets_style_dock_buttons(self):
        # Docks that are not overlaid take the application sheet only, and
        # it replaces FreeCAD.qss, where upstream's icon rules live.
        for mode in ("light", "dark"):
            text = body(os.path.join(ASSETS,
                                     "Atech%s.qss" % mode.capitalize()))
            for name in ("OBTN Float", "OBTN Overlay"):
                with self.subTest(button=name, mode=mode):
                    d = decls_for(
                        text, 'Gui--OverlayToolButton[objectName="%s"]' % name)
                    m = re.search(r"image:\s*([^;]+);", d)
                    self.assertIsNotNone(m, "no resting image for " + name)
                    self._check_icon(m.group(1), mode, "app sheet " + name)

    def test_close_icon_reads_on_buttons(self):
        for mode in ("light", "dark"):
            ground = self.vals[mode]["AtechPanelColor"]  # QPushButton ground
            sheets = [("overlay", self.overlay),
                      ("app", body(os.path.join(
                          ASSETS, "Atech%s.qss" % mode.capitalize())))]
            for label, text in sheets:
                with self.subTest(sheet=label, mode=mode):
                    d = decls_for(text, "QDialogButtonBox")
                    m = re.search(
                        r"(?<![\w-])dialog-close-icon:\s*([^;]+);", d)
                    self.assertIsNotNone(m, "%s sheet: no dialog-close-icon, "
                                            "Qt's black X stays" % label)
                    path = resolve(m.group(1), self.vals[mode], self.sdir)
                    self.assertTrue(path and os.path.isfile(path), path)
                    self.assertGreaterEqual(glyph_contrast(path, ground), 4.5)

    def test_criterion_rejects_the_old_dark_icon(self):
        # The pre-R118 resting glyph (upstream lightgray) must FAIL the dark
        # criterion, or the checks above prove nothing.
        ground, muted = self._bar("dark")
        old = os.path.join(self.sdir, "images_classic",
                           "overlay-lightgray.svg")
        self.assertLess(glyph_contrast(old, ground), contrast(muted, ground))

    def test_task_box_ground_is_transparent(self):
        for name in ("AtechLight.qss", "AtechDark.qss"):
            with self.subTest(sheet=name):
                d = decls_for(body(os.path.join(ASSETS, name)),
                              "QSint--ActionGroup")
                self.assertRegex(d, r"background:\s*transparent")


class Template(unittest.TestCase):
    def setUp(self):
        self.root = ET.parse(TEMPLATE).getroot()

    def _group(self, *path):
        g = self.root
        for name in ("Root",) + path:
            g = g.find("FCParamGroup[@Name='%s']" % name)
            self.assertIsNotNone(g, "template lacks group %s" % "/".join(path))
        return g

    def test_selects_the_atech_overlay_sheet(self):
        mw = self._group("BaseApp", "Preferences", "MainWindow")
        e = mw.find("FCText[@Name='OverlayActiveStyleSheet']")
        self.assertIsNotNone(e)
        self.assertEqual(e.text, os.path.basename(OVERLAY))

    def test_right_overlay_starts_opaque(self):
        g = self._group("BaseApp", "MainWindow", "DockWindows", "OverlayRight")
        e = g.find("FCBool[@Name='Transparent']")
        self.assertIsNotNone(e)
        self.assertEqual(e.get("Value"), "0")


class BuildScript(unittest.TestCase):
    def test_installs_the_overlay_sheet(self):
        with open(os.path.join(REPO, "branding", "build_appimage.sh"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"$BA/Atech Overlay.qss" "$QSSDIR/overlay/Atech Overlay.qss"',
                      src)
        r = subprocess.run(["bash", "-n",
                            os.path.join(REPO, "branding", "build_appimage.sh")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    if r.wasSuccessful() and not r.skipped:
        print("OVERLAY_SHEET_TESTS_OK")
    sys.exit(0 if r.wasSuccessful() else 1)
