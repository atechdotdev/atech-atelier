"""R51 render check: dropdown tool buttons must not draw a black menu bar.

Runs under the image's own Python (it needs PySide6, which only the image
has), offscreen, against the generated brand/assets/Atech{Light,Dark}.qss:

    QT_QPA_PLATFORM=offscreen \
      dist/build/squashfs-root/usr/bin/python \
      branding/tests/render_toolbutton_menu.py [sheet.qss ...]

It lays out a QToolButton in MenuButtonPopup mode (what Undo/Redo and the
Part primitives use), applies the sheet, grabs the widget and counts pixels
in the right-hand menu-button strip that differ from the toolbar
background. The light sheet before the fix measured a solid black bar
there (dogfood D15). The "qss:" search path is set to the image's
Gui/Stylesheets, exactly as FreeCAD's StartupProcess does, so the arrow
image must actually resolve.

The verdict is the RENDER_TOOLBUTTON_FAILURES=<n> line; the exit code
follows it.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDir, QSize, Qt  # noqa: E402
from PySide6.QtGui import QColor, QIcon, QPixmap  # noqa: E402
from PySide6.QtWidgets import (QApplication, QMenu, QToolBar,  # noqa: E402
                               QToolButton, QWidget, QVBoxLayout)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
IMAGE = os.path.join(sys.prefix, "share", "Gui", "Stylesheets")


def _luma(c):  # noqa: D103
    return 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()


def measure(sheet_path):
    """(dark_pixels, strip_pixels, bg_luma) for the menu-button strip."""
    with open(sheet_path, encoding="utf-8") as fh:
        qss = fh.read()
    app = QApplication.instance()
    app.setStyleSheet(qss)

    host = QWidget()
    lay = QVBoxLayout(host)
    bar = QToolBar()
    bar.setIconSize(QSize(24, 24))
    btn = QToolButton()
    pm = QPixmap(24, 24)
    pm.fill(QColor(0, 0, 0, 0))
    btn.setIcon(QIcon(pm))
    btn.setPopupMode(QToolButton.MenuButtonPopup)
    menu = QMenu(btn)
    menu.addAction("one")
    btn.setMenu(menu)
    bar.addWidget(btn)
    lay.addWidget(bar)
    host.resize(200, 80)
    host.show()
    app.processEvents()

    # Grab the opaque host, not the button: the button's own background is
    # transparent, and a transparent pixel reads back as black.
    full = host.grab().toImage()
    geo = btn.geometry().translated(btn.parentWidget().mapTo(host, btn.pos())
                                    - btn.pos())
    img = full.copy(geo)
    if os.environ.get("RENDER_TOOLBUTTON_SAVE"):
        img.save(os.path.join(os.environ["RENDER_TOOLBUTTON_SAVE"],
                              os.path.basename(sheet_path) + ".png"))
    w, h = img.width(), img.height()
    # The button is transparent, so its top-left interior is the toolbar's
    # own background -- the colour the menu strip must blend into.
    ref = QColor(img.pixel(2, 2))
    # The menu-button sub-control is the right-hand strip of the button.
    x0 = max(0, w - 12)
    off = total = 0
    for x in range(x0, w - 1):
        for y in range(2, h - 2):
            total += 1
            c = QColor(img.pixel(x, y))
            if max(abs(c.red() - ref.red()), abs(c.green() - ref.green()),
                   abs(c.blue() - ref.blue())) > 10:
                off += 1
    host.close()
    return off, total, _luma(ref)


def main(argv):
    QDir.setSearchPaths("qss", [IMAGE])
    app = QApplication(sys.argv[:1])  # noqa: F841 (kept alive)
    sheets = argv or [os.path.join(REPO, "brand", "assets", n)
                      for n in ("AtechLight.qss", "AtechDark.qss")]
    failures = 0
    for s in sheets:
        off, total, bg = measure(s)
        # Arrow glyph pixels are allowed; a bar is not. MEASURED: the
        # pre-fix sheets filled 100 % (light) and 87 % (dark) of the strip;
        # the fixed ones 5 %, the arrow alone.
        frac = off / float(total or 1)
        ok = frac < 0.25
        failures += 0 if ok else 1
        print("%-5s %s off-background=%d/%d (%.0f%%) bg_luma=%.0f" % (
            "OK" if ok else "FAIL", os.path.basename(s), off, total,
            100 * frac, bg))
    # the qss: path must resolve the arrow the sheet names
    arrow = QDir.searchPaths("qss")[0] + "/images_classic/arrow-down-darkgray.svg"
    if not os.path.isfile(arrow):
        failures += 1
        print("FAIL arrow image missing: %s" % arrow)
    print("RENDER_TOOLBUTTON_FAILURES=%d" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    rc = main(sys.argv[1:])
    sys.stdout.flush()
    os._exit(rc)  # skip Qt teardown; flush first or the verdict is lost
