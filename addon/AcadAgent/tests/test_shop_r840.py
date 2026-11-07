"""R840: links to the Atech shop at atech.dev.

  TestShop     (no Qt) every module in models/presets.yaml that the shop
               sells has its slug, and every slug is one the site knows
               (its src/lib/pricing.ts, when the site's tree is next to
               this one); the cart link counts modules and adds the board.
  TestHome     Home's "Atech shop" and its atech.dev / Shop /
               Credits links open the right page (the browser is a stub).
  TestModules  the Modules page's "Get it made" (R840 "Buy modules") is
               hidden on an empty board, and opens the Get it made window
               (R850), or the cart with the board and its modules.

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_shop_r840
"""
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

from acadagent import shop  # noqa: E402

try:
    from PySide6 import QtGui, QtWidgets
    APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except ImportError:
    QtWidgets = None

#: presets.yaml modules the shop does not sell on their own
NOT_SOLD = {"pir", "stepper_motor", "n20_wheel", "nema17_stepper"}
SITE_PRICING = os.path.join(os.path.dirname(REPO), "studio", "frontend", "src", "lib", "pricing.ts")


def preset_names():
    with open(os.path.join(REPO, "models", "presets.yaml"), encoding="utf-8") as fh:
        return re.findall(r"^([a-z0-9_]+):\s*$", fh.read(), re.M)


class TestShop(unittest.TestCase):
    def test_every_module_is_sold_or_listed(self):
        names = preset_names()
        self.assertIn("screen", names)
        for n in names:
            self.assertTrue(n in shop.SHOP_SLUGS or n in NOT_SOLD, n)
        for n in shop.SHOP_SLUGS:
            self.assertIn(n, names)

    @unittest.skipUnless(os.path.isfile(SITE_PRICING), "the site's tree is not next to this one")
    def test_slugs_are_the_sites(self):
        with open(SITE_PRICING, encoding="utf-8") as fh:
            site = set(re.findall(r"slug: '([a-z0-9-]+)'|'([a-z0-9-]+)': MODULE_PRICES", fh.read()))
        site = {a or b for a, b in site}
        for s in shop.SHOP_SLUGS.values():
            self.assertIn(s, site, s)

    def test_cart_link(self):
        url = shop.cart_url(["screen", "dc_motor", "dc_motor", "pir", "load_cell"])
        self.assertEqual(url, "https://atech.dev/cart?add=frame-2,screen,dc-motor:2&from=atelier")
        want, unsold = shop.bill(["pir", "orientation"])
        self.assertEqual(dict(want), {"frame-2": 1, "orientation-sensor": 1})
        self.assertEqual(unsold, ["pir"])
        self.assertEqual(shop.cart_url([], board=False), shop.SHOP)

    def test_module_page(self):
        self.assertEqual(shop.module_url("scd40_air_quality"), "https://atech.dev/modules/co2-sensor")
        self.assertEqual(shop.module_url("pir"), "https://atech.dev/modules")


class _Browser(object):
    """QDesktopServices.openUrl, recorded instead of opened."""

    def __enter__(self):
        self.urls = []
        self._real = QtGui.QDesktopServices.openUrl
        QtGui.QDesktopServices.openUrl = lambda u: self.urls.append(u.toString()) or True
        return self

    def __exit__(self, *_):
        QtGui.QDesktopServices.openUrl = self._real


@unittest.skipIf(QtWidgets is None, "PySide6 not available (run with the bundled python)")
class TestHome(unittest.TestCase):
    def test_links(self):
        from acadagent import shell
        home = shell.HomeView()
        home.restyle()
        self.assertIn('href="https://atech.dev"', home.credit.text())
        with _Browser() as b:
            home.btn_shop.click()
            home.credit.linkActivated.emit("https://atech.dev")
        self.assertEqual(b.urls, ["https://atech.dev/modules", "https://atech.dev"])
        opened = []
        real = shell._open_credits
        shell._open_credits = lambda link=None: opened.append(link)
        try:
            home.credit.linkActivated.emit("credits")
        finally:
            shell._open_credits = real
        self.assertEqual(opened, ["credits"])


class _Obj(object):
    def __init__(self, name, module, ports):
        self.Name, self.Label, self.AtechModule, self.AtechPorts = name, name, module, ports


@unittest.skipIf(QtWidgets is None, "PySide6 not available (run with the bundled python)")
class TestModules(unittest.TestCase):
    def test_buy_button(self):
        from acadagent import modules_page
        page = modules_page.ModulesPage.__new__(modules_page.ModulesPage)
        QtWidgets.QWidget.__init__(page)
        page.btn_buy = QtWidgets.QPushButton()
        page._specs = {}
        page._sync_buy({})
        self.assertTrue(page.btn_buy.isHidden())
        scr = _Obj("Screen", "screen", [10, 11])
        occ = {10: scr, 11: scr, 2: _Obj("Motor", "dc_motor", [2]), 3: _Obj("Pir", "pir", [3])}
        page._sync_buy(occ)
        self.assertFalse(page.btn_buy.isHidden())
        self.assertIn("1 × screen", page.btn_buy.toolTip())
        self.assertIn("Not sold on its own: pir", page.btn_buy.toolTip())
        page._occupied = lambda: occ
        # R850: it opens the Get it made window ...
        from acadagent import print_order
        opened = []
        real = print_order.OrderDialog
        print_order.OrderDialog = lambda parent=None, *a, **k: opened.append(parent) or \
            types.SimpleNamespace(show=lambda: None)
        try:
            with _Browser() as b:
                page._buy()
        finally:
            print_order.OrderDialog = real
        self.assertEqual((len(opened), b.urls), (1, []))
        # ... and the cart link at once when that window cannot open
        print_order.OrderDialog = lambda *a, **k: 1 / 0
        try:
            with _Browser() as b:
                page._buy()
        finally:
            print_order.OrderDialog = real
        self.assertEqual(b.urls, ["https://atech.dev/cart?add=frame-2,screen,dc-motor&from=atelier"])


if __name__ == "__main__":
    unittest.main()
