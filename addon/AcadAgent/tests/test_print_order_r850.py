"""R850: get a design made by Atech: its modules and its 3D prints.

  TestPlan      (no Qt, no FreeCAD) how a part fits one 3D print voucher,
                packing parts into as few vouchers as they need, the
                filament estimate, the cart link with vouchers.
  TestSite      the voucher's size, weight and the kits' free vouchers are
                the site's (src/lib/pricing.ts, when the site's tree is
                next to this one).
  TestFreeCAD   (bundled freecadcmd) a design's printed parts measured laid
                flat, Atech hardware left out, one 3MF per voucher print
                and order.txt saved.
  TestDialog    (offscreen Qt) the Get it made window: hardware, prints,
                Add to cart with and without the vouchers, Send my prints,
                Ask the agent to split.

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_print_order_r850
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest
from collections import Counter
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

from acadagent import shop  # noqa: E402

try:
    from PySide6 import QtWidgets
    APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except ImportError:
    QtWidgets = None

SITE = os.path.join(os.path.dirname(REPO), "studio", "frontend", "src", "lib")
BUNDLE = "/Applications/Atech Atelier.app/Contents/Resources/bin"
FC = os.environ.get("ATECH_FREECADCMD") or os.path.join(BUNDLE, "freecadcmd")


def part(label, w, d, h, g=50.0):
    return {"label": label, "size": (w, d, h), "grams": g}


class TestPlan(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(shop.fit((120, 80, 60), 80), "ok")
        self.assertEqual(shop.fit((300, 330, 20)), "ok")              # turned on the bed
        self.assertEqual(shop.fit((330, 340, 20)), "on its side")     # a plate stood on edge
        self.assertEqual(shop.fit((100, 50, 345)), "on its side")     # tall: laid down, corner to corner
        self.assertEqual(shop.fit((380, 20, 20)), "diagonal")
        self.assertEqual(shop.fit((500, 20, 20)), "too big")
        self.assertEqual(shop.fit((100, 100, 100), 501), "too heavy")

    def test_packing(self):
        plan = shop.plan_prints([part("Shell", 150, 100, 80, 120), part("Lid", 150, 100, 5, 40),
                                 part("Wing L", 150, 100, 5, 30), part("Wing R", 150, 100, 5, 30),
                                 part("Mast", 380, 20, 20, 60), part("Beam", 500, 20, 20)])
        self.assertEqual(plan["vouchers"], 2)
        self.assertEqual(plan["prints"][0]["labels"], ["Shell", "Lid", "Wing L", "Wing R"])
        self.assertEqual(plan["prints"][0]["grams"], 220.0)
        self.assertEqual(plan["prints"][1]["labels"], ["Mast"])       # corner to corner: its own
        self.assertEqual(plan["split"], ["Beam"])
        self.assertEqual(shop.plan_prints([])["vouchers"], 0)

    def test_weight_starts_a_new_print(self):
        plan = shop.plan_prints([part("A", 50, 50, 50, 300), part("B", 50, 50, 50, 300)])
        self.assertEqual([p["labels"] for p in plan["prints"]], [["A"], ["B"]])

    def test_plate(self):
        spots = shop.plate([(300, 100, 10), (300, 100, 10), (100, 300, 10)])
        self.assertIsNotNone(spots)
        boxes = []
        for (cx, cy, turned), (w, d, _h) in zip(spots, [(300, 100, 10), (300, 100, 10), (100, 300, 10)]):
            w, d = (d, w) if turned else (w, d)
            boxes.append((cx - w / 2, cy - d / 2, cx + w / 2, cy + d / 2))
        for b in boxes:
            self.assertTrue(b[0] >= 0 and b[1] >= 0 and b[2] <= 340 and b[3] <= 320, b)
        for i, a in enumerate(boxes):                    # no two overlap
            for b in boxes[i + 1:]:
                self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
        self.assertIsNone(shop.plate([(300, 300, 10), (300, 300, 10)]))
        self.assertEqual(shop.diagonal_angle(300, 20), 0.0)
        self.assertGreater(shop.diagonal_angle(380, 20), 0.0)

    def test_tight_beds(self):
        # a metronome's parts (76 % of the bed) on one voucher
        parts = [part("Back", 151.8, 228.1, 68.9, 141), part("Plinth", 166.1, 108.9, 15, 81),
                 part("Front", 153.6, 93.3, 228.2, 103), part("Bezel", 90.2, 60, 4, 9),
                 part("Lens", 82.4, 52, 1.3, 6)]
        self.assertEqual(shop.plan_prints(parts)["vouchers"], 1)

    def test_bed_fills_up(self):
        plan = shop.plan_prints([part("P%d" % i, 160, 150, 10, 10) for i in range(5)])
        self.assertEqual([len(p["labels"]) for p in plan["prints"]], [4, 1])

    def test_grams(self):
        self.assertAlmostEqual(shop.print_grams(1000.0, 1000.0), 1.24)       # all skin
        solid = 100.0 ** 3
        self.assertLess(shop.print_grams(solid, 6 * 100.0 ** 2), solid / 1000 * 1.24 / 3)

    def test_cart_with_vouchers(self):
        self.assertEqual(shop.cart_url(["screen"], prints=2),
                         "https://atech.dev/cart?add=frame-2,screen,print-voucher:2&from=atelier")
        self.assertEqual(shop.cart_url([], board=False, prints=1),
                         "https://atech.dev/cart?add=print-voucher&from=atelier")

    def test_agent_is_told(self):
        from acadagent import build
        rule = " ".join(build.VOUCHER_RULE.split())
        self.assertIn("340 x 320 x 340 mm and 350 g", rule)
        self.assertEqual((340.0, 320.0, 340.0, 350.0), shop.VOUCHER_MM + (shop.VOUCHER_GRAMS,))
        self.assertIn("Get it made by Atech", rule)

    def test_words(self):
        self.assertIn("Big Kit comes with one", shop.kit_note(1))
        self.assertIn("Chunky Kit comes with three", shop.kit_note(2))
        self.assertIn("no printed parts", shop.kit_note(0))
        self.assertEqual(shop.mailto_url("A b", "c&d"), "mailto:hello@atech.dev?subject=A%20b&body=c%26d")


class TestRequest(unittest.TestCase):
    """shop.send_print_request: the multipart POST the site's route reads."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="r850req_")
        self.f = os.path.join(self.tmp, "Rocket print 1 of 1.3mf")
        with open(self.f, "wb") as fh:
            fh.write(b"PK\x03\x04 3D/3dmodel.model")

    def test_posts_fields_and_files(self):
        seen = {}

        class R(object):
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"ok": true, "prints": 1}'

        def opener(req, timeout):
            seen["url"], seen["ct"], seen["body"] = req.full_url, req.get_header("Content-type"), req.data
            return R()
        out = shop.send_print_request("me@example.com", [self.f], design="Rocket", sheet="S",
                                      note="red", order="A-1", opener=opener)
        self.assertEqual(out, {"ok": True, "status": 200, "message": ""})
        self.assertEqual(seen["url"], "https://atech.dev/api/print-request")
        self.assertTrue(seen["ct"].startswith("multipart/form-data; boundary="))
        body = seen["body"]
        for part in (b'name="email"\r\n\r\nme@example.com', b'name="order"\r\n\r\nA-1',
                     b'name="file"; filename="Rocket print 1 of 1.3mf"', b"3D/3dmodel.model"):
            self.assertIn(part, body)

    def test_errors(self):
        import io
        import urllib.error

        def refused(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 400, "Bad", {},
                                         io.BytesIO(b'{"error": "x.3mf is not a 3MF file."}'))

        def offline(req, timeout):
            raise urllib.error.URLError("no route")
        self.assertEqual(shop.send_print_request("me@example.com", [self.f], opener=refused),
                         {"ok": False, "status": 400, "message": "x.3mf is not a 3MF file."})
        self.assertEqual(shop.send_print_request("me@example.com", [self.f], opener=offline)["status"], 0)
        self.assertTrue(shop.valid_email("a@b.co"))
        self.assertFalse(shop.valid_email("a@b"))


@unittest.skipUnless(os.path.isfile(os.path.join(SITE, "pricing.ts")), "the site's tree is not next to this one")
class TestQuote(unittest.TestCase):
    """shop.quote / price_line: the site's /api/quote, worded as the cart."""

    def test_asks_the_site(self):
        import io
        seen = []

        class R(io.BytesIO):
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        body = json.dumps({"total": {"amount": 100, "text": "$1"}, "kit": None}).encode()
        q = shop.quote(shop.SITE + "/cart?add=screen,print-voucher:2&from=atelier",
                       opener=lambda req, timeout: seen.append((req.full_url, timeout)) or R(body))
        self.assertEqual(q["total"]["text"], "$1")
        self.assertEqual(seen, [(shop.SITE + "/api/quote?add=screen,print-voucher:2&from=atelier", 8)])
        self.assertIsNone(shop.quote(shop.SHOP))
        self.assertIsNone(shop.quote(shop.SITE + "/cart?add=screen", opener=lambda *a, **k: 1 / 0))
        self.assertIsNone(shop.quote(shop.SITE + "/cart?add=screen", opener=lambda *a, **k: R(b"[]")))

    def test_words(self):
        t = {"total": {"text": "1,334 SEK"}}
        self.assertEqual(shop.price_line(t), "About 1,334 SEK on atech.dev, before shipping.")
        self.assertEqual(shop.price_line(None), "")
        t["kit"] = {"name": "Chunky Kit", "total": {"text": "$399"}, "more": {"amount": 0},
                    "freeVouchers": 3, "extra": 30}
        self.assertTrue(shop.price_line(t).endswith(
            "Cheaper as the Chunky Kit: every module here and 3 free 3D print vouchers, for $399."))
        t["kit"].update(name="Small Kit", freeVouchers=0, more={"amount": 500, "text": "$5"}, extra=8)
        self.assertTrue(shop.price_line(t).endswith("For $5 more, the Small Kit has every module "
                                                    "here, 8 more modules."))


class TestSite(unittest.TestCase):
    def test_voucher_is_the_sites(self):
        with open(os.path.join(SITE, "pricing.ts"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("PRINT_VOUCHER = '%s'" % shop.VOUCHER, src)
        m = re.search(r"PRINT_VOUCHER_SIZE = \{ cm: '([\d.]+) × ([\d.]+) × ([\d.]+)', grams: (\d+) \}", src)
        self.assertIsNotNone(m)
        self.assertEqual(tuple(float(v) * 10 for v in m.groups()[:3]), shop.VOUCHER_MM)
        self.assertEqual(float(m.group(4)), shop.VOUCHER_GRAMS)
        free = dict(re.findall(r"name: '(\w+ Kit)',(?:(?!name:).)*?printVouchers: (\d+)", src, re.S))
        self.assertEqual({k: int(v) for k, v in free.items()},
                         {k: v for k, v in shop.KIT_VOUCHERS.items() if v})
        self.assertNotRegex(src, r"name: 'Small Kit',(?:(?!name:).)*?printVouchers")

    def test_names_are_the_sites(self):
        with open(os.path.join(SITE, "pricing.ts"), encoding="utf-8") as fh:
            src = fh.read()
        site = {}
        for a, b in re.findall(r"name: '([^']*)'[^}]*?slug: '([a-z0-9-]+)'", src):
            site.setdefault(b, a)
        for b, a in re.findall(r"slug: '([a-z0-9-]+)', name: '([^']*)'", src):
            site.setdefault(b, a)
        site[shop.VOUCHER] = "3D print voucher"
        for slug, name in shop.SHOP_NAMES.items():
            self.assertEqual(site.get(slug), name, slug)


FC_SCRIPT = r'''
import sys, json, os
sys.path.insert(0, os.environ["R850_ADDON"])
import FreeCAD, Part
from acadagent import print_order, export_tools as et
doc = FreeCAD.newDocument("Rocket")
def box(name, x, y, z, hollow=False, role=None, module=None):
    o = doc.addObject("Part::Feature", name)
    s = Part.makeBox(x, y, z)
    if hollow:
        s = s.cut(Part.makeBox(x - 4, y - 4, z - 2, FreeCAD.Vector(2, 2, 2)))
    o.Shape = s
    if role:
        o.addProperty("App::PropertyString", "AtechRole"); o.AtechRole = role
    if module:
        o.addProperty("App::PropertyString", "AtechModule"); o.AtechModule = module
    return o
box("Shell", 120, 80, 60, True)
box("Lid", 120, 80, 3)
box("Fin", 10, 60, 300)                 # stands tall: laid flat
box("Beam", 20, 20, 500)
box("Board", 50, 50, 2, role="board")
box("Screen", 30, 20, 5, role="module", module="screen")
box("Motor", 20, 10, 10, role="module", module="dc_motor")
box("Motor001", 20, 10, 10, role="module", module="dc_motor")
box("Servo", 20, 10, 20, role="part", module="sg90")
doc.recompute()
o = print_order.order(doc)
res = print_order.save_prints(doc, o, out_dir=os.environ["R850_OUT"])
objs = et.read_3mf(res["files"][0])
pts = [p for ob in objs for p in ob["points"]]
extent = [max(p[k] for p in pts) - min(p[k] for p in pts) for k in range(3)]
box = [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]
json.dump({"plan": o["plan"], "modules": dict(o["modules"]), "parts": o["parts"],
           "url": print_order.cart_url(o), "url_no_prints": print_order.cart_url(o, prints=False),
           "files": res["files"], "sheet": res["sheet"],
           "in_3mf": sorted(ob["name"] for ob in objs), "extent": extent, "box": box, "zmin": min(p[2] for p in pts),
           "order_txt": open(os.path.join(res["dir"], "order.txt")).read(),
           "mail": print_order.email_url(doc, o, res["files"])},
          open(os.environ["R850_JSON"], "w"), default=str)
'''


@unittest.skipUnless(os.path.isfile(FC), "no freecadcmd (set ATECH_FREECADCMD)")
class TestFreeCAD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="r850_")
        script = os.path.join(cls.tmp, "run.py")
        with open(script, "w") as fh:
            fh.write(FC_SCRIPT)
        out = os.path.join(cls.tmp, "result.json")
        env = dict(os.environ, R850_ADDON=ADDON, R850_OUT=os.path.join(cls.tmp, "prints"),
                   R850_JSON=out)
        subprocess.run([FC, script], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=300)
        with open(out) as fh:
            cls.r = json.load(fh)

    def test_parts_measured_laid_flat(self):
        by = {p["label"]: p for p in self.r["plan"]["parts"]}
        self.assertEqual(set(by), {"Shell", "Lid", "Fin", "Beam"})     # no hardware
        self.assertEqual(sorted(by["Fin"]["size"])[0], 10.0)
        self.assertEqual(by["Fin"]["size"][2], 10.0)                    # lies on its side
        self.assertEqual(by["Beam"]["fit"], "too big")
        self.assertLess(by["Shell"]["grams"], 100)

    def test_order(self):
        self.assertEqual(self.r["plan"]["vouchers"], 1)
        self.assertEqual(self.r["plan"]["split"], ["Beam"])
        self.assertEqual(self.r["modules"], {"frame-2": 1, "screen": 1, "dc-motor": 2})
        self.assertEqual(sum(self.r["parts"].values()), 1)              # the servo: not sold
        self.assertEqual(self.r["url"],
                         "https://atech.dev/cart?add=frame-2,screen,dc-motor:2,print-voucher&from=atelier")
        self.assertNotIn("print-voucher", self.r["url_no_prints"])

    def test_files(self):
        self.assertEqual(len(self.r["files"]), 1)
        self.assertTrue(self.r["files"][0].endswith("Rocket print 1 of 1.3mf"))
        self.assertGreater(os.path.getsize(self.r["files"][0]), 1000)
        self.assertEqual(self.r["in_3mf"], ["Fin", "Lid", "Shell"])
        w, d, h = self.r["extent"]                      # side by side on one voucher's bed
        self.assertLessEqual(max(w, d), 340)
        self.assertLessEqual(min(w, d), 320)
        self.assertLessEqual(h, 60.01)
        self.assertAlmostEqual(self.r["zmin"], 0.0, places=3)
        x0, y0, x1, y1 = self.r["box"]                  # on the voucher's bed, centred
        self.assertGreaterEqual(min(x0, y0), 0.0)
        self.assertLessEqual(x1, 340.0)
        self.assertLessEqual(y1, 320.0)
        self.assertAlmostEqual((x0 + x1) / 2, 170.0, delta=0.5)
        self.assertIn("Print 1, about", self.r["order_txt"])
        self.assertRegex(self.r["order_txt"], r"Print 1, about \d+ g: Fin, Shell, Lid\n")
        self.assertIn("split before printing): Beam", self.r["order_txt"])
        self.assertIn("1 x 14-Port Motherboard, 1 x Screen, 2 x DC Motor", self.r["order_txt"])
        self.assertTrue(self.r["mail"].startswith("mailto:hello@atech.dev?subject=3D%20print%20voucher"))


@unittest.skipIf(QtWidgets is None, "PySide6 not available (run with the bundled python)")
class TestDialog(unittest.TestCase):
    ORDER = {"names": ["screen", "dc_motor", "dc_motor", "pir"],
             "modules": Counter({"frame-2": 1, "screen": 1, "dc-motor": 2}),
             "unsold": ["pir"], "parts": {"SG90 servo": 8},
             "plan": shop.plan_prints([part("Shell", 150, 100, 80, 120), part("Mast", 380, 20, 20, 60),
                                       part("Beam", 500, 20, 20)])}

    def make(self, order=None, answer=None):
        from acadagent import print_order
        self.urls, self.shown, self.asked, self.requests = [], [], [], []
        doc = types.SimpleNamespace(Label="Rocket")
        panel = types.SimpleNamespace(ask=lambda t: self.asked.append(t) or True)
        answer = answer or {"ok": True, "status": 200, "message": ""}
        # the real settings file is never read or written here
        self.stored = []
        p = [mock.patch.object(print_order, "order", lambda d: order or self.ORDER),
             mock.patch.object(print_order, "_stored_email", lambda: "maker@example.com"),
             mock.patch.object(print_order, "_store_email", self.stored.append)]
        for x in p:
            x.start()
            self.addCleanup(x.stop)
        self.quoted = []
        return print_order.OrderDialog(None, lambda: doc, opener=self.urls.append,
                                       revealer=self.shown.append, panel_fn=lambda: panel,
                                       sender=lambda **r: self.requests.append(r) or answer,
                                       background=False,
                                       quoter=lambda u: self.quoted.append(u) or self.QUOTE)

    QUOTE = {"currency": "USD", "total": {"amount": 21600, "text": "$216"},
             "kit": {"id": "big", "name": "Big Kit", "total": {"amount": 23700, "text": "$237"},
                     "more": {"amount": 2100, "text": "$21"}, "freeVouchers": 1, "extra": 15}}

    RES = {"dir": os.path.expanduser("~/Documents/Atech Prints/Rocket"),
           "files": ["/x/Rocket print 1 of 2.3mf", "/x/Rocket print 2 of 2.3mf"], "sheet": "SHEET"}

    def send(self, d):
        from acadagent import print_order
        with mock.patch.object(print_order, "save_prints", lambda doc, o: self.RES):
            d.send.click()

    def test_window(self):
        d = self.make()
        self.assertEqual(d.hardware.text(), "1 \u00d7 14-Port Motherboard\n1 \u00d7 Screen\n2 \u00d7 DC Motor")
        self.assertEqual(d.table.rowCount(), 3)
        self.assertEqual(d.table.item(0, 3).text(), "Print 1")
        self.assertEqual(d.table.item(1, 3).text(), "Print 2 (corner to corner)")
        self.assertEqual(d.table.item(2, 3).text(), "Too big: split it")
        self.assertIn("2 3D print vouchers", d.note.text())
        self.assertTrue(d.with_prints.isChecked())
        d.voucher_link.linkActivated.emit(shop.VOUCHER_URL)
        self.assertEqual(self.urls, ["https://atech.dev/#print-voucher"])

    def test_cart(self):
        d = self.make()
        d.cart.click()
        self.assertIn("come back here and press Send my prints", d.status.text())
        d.with_prints.setChecked(False)
        d.cart.click()
        self.assertNotIn("come back", d.status.text())
        self.assertEqual(self.urls, [
            "https://atech.dev/cart?add=frame-2,screen,dc-motor:2,print-voucher:2&from=atelier",
            "https://atech.dev/cart?add=frame-2,screen,dc-motor:2&from=atelier"])

    def test_send_prints(self):
        d = self.make()
        self.assertEqual(d.email.text(), "maker@example.com")
        d.order_no.setText("A-1042")
        d.wishes.setText("red")
        self.send(d)
        self.assertEqual(self.requests, [{"email": "maker@example.com", "files": self.RES["files"],
                                          "design": "Rocket", "sheet": "SHEET", "note": "red",
                                          "order": "A-1042"}])
        self.assertEqual(self.stored, ["maker@example.com"])
        self.assertEqual((self.urls, self.shown), ([], []))
        self.assertIn("Sent to Atech: 2 prints. We reply to maker@example.com", d.status.text())
        self.assertIn("~/Documents/Atech Prints/Rocket", d.status.text())
        self.assertEqual(d.send.text(), "Send again")

    def test_sends_in_the_background(self):
        import time
        from PySide6 import QtCore
        from acadagent import print_order
        d = self.make()
        d._background = True
        with mock.patch.object(print_order, "save_prints", lambda doc, o: self.RES):
            real = print_order.OrderDialog
            d2 = real(None, lambda: types.SimpleNamespace(Label="Rocket"), opener=self.urls.append,
                      revealer=self.shown.append, quoter=lambda u: None,
                      sender=lambda **r: time.sleep(0.2) or {"ok": True, "status": 200, "message": ""})
            d2.send.click()
            self.assertFalse(d2.send.isEnabled())
            self.assertIn("Sending 2 prints to Atech", d2.status.text())
            end = time.time() + 5
            while "Sent to Atech" not in d2.status.text() and time.time() < end:
                QtCore.QCoreApplication.processEvents()
                time.sleep(0.02)
        self.assertIn("Sent to Atech", d2.status.text())
        self.assertTrue(d2.send.isEnabled())

    def test_price(self):
        d = self.make()
        self.assertEqual(d.price.text(), "About $216 on atech.dev, before shipping. For $21 more, "
                         "the Big Kit has every module here, 15 more modules and a free 3D print voucher.")
        self.assertFalse(d.price.isHidden())
        d.with_prints.setChecked(False)
        d.with_prints.setChecked(True)
        # each cart asked once: ticking back uses the answer it has
        self.assertEqual(self.quoted, [
            "https://atech.dev/cart?add=frame-2,screen,dc-motor:2,print-voucher:2&from=atelier",
            "https://atech.dev/cart?add=frame-2,screen,dc-motor:2&from=atelier"])

    def test_price_offline(self):
        self.QUOTE = None                                 # no answer: no line
        d = self.make()
        self.assertTrue(d.price.isHidden())
        self.assertEqual(len(self.quoted), 1)

    def test_send_needs_an_email(self):
        d = self.make()
        d.email.setText("nope")
        self.send(d)
        self.assertEqual(self.requests, [])
        self.assertIn("Type the email you ordered with", d.status.text())

    def test_not_open_yet_falls_back_to_an_email(self):
        d = self.make(answer={"ok": False, "status": 503, "message": "not yet"})
        self.send(d)
        self.assertEqual(len(self.urls), 1)
        self.assertTrue(self.urls[0].startswith(
            "mailto:hello@atech.dev?subject=3D%20print%20voucher%3A%20Rocket%20%282%20prints%29"))
        self.assertEqual(self.shown, ["/x/Rocket print 1 of 2.3mf"])
        self.assertIn("An email to hello@atech.dev is open", d.status.text())

    def test_refused_says_why(self):
        d = self.make(answer={"ok": False, "status": 429, "message": "Too many requests."})
        self.send(d)
        self.assertEqual(self.urls, [])
        self.assertEqual(d.status.text(), "Atech could not take them: Too many requests.")

    def test_split(self):
        d = self.make()
        d.split.click()
        self.assertEqual(len(self.asked), 1)
        self.assertIn("Split Beam into pieces", self.asked[0])
        self.assertIn("340 x 320 x 340 mm", self.asked[0])

    def test_fewer_vouchers(self):
        plan = shop.plan_prints([part("Body", 330, 310, 80, 300), part("Pin", 20, 10, 5, 2)])
        self.assertEqual((plan["vouchers"], plan["light"]), (2, ["Pin"]))
        d = self.make(dict(self.ORDER, plan=plan))
        self.assertIsNone(d.split)
        self.assertEqual(d.fewer.text(), "Ask the agent to fit it on 1")
        d.fewer.click()
        self.assertIn("the last print holds only Pin. Make them fit on 1", self.asked[0])
        self.assertEqual(shop.plan_prints([part("A", 330, 310, 80, 300), part("B", 330, 310, 80, 300)])["light"], [])

    def test_nothing_to_print(self):
        d = self.make(dict(self.ORDER, plan=shop.plan_prints([])))
        self.assertFalse(d.send.isEnabled())
        self.assertTrue(d.with_prints.isHidden())
        self.assertIsNone(d.split)
        d.cart.click()
        self.assertEqual(self.urls, ["https://atech.dev/cart?add=frame-2,screen,dc-motor:2&from=atelier"])


if __name__ == "__main__":
    unittest.main()
