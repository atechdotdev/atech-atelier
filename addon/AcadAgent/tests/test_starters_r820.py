"""R820: starter projects - small, simple starting points on Home.

    kinds      manifest entries of "kind": "starter" are offered by
               default_projects.entries(kind="starter") and opened by
               new_from_default like the products, never copied into the
               projects folder by install_defaults; entries() stays the
               products.
    Home       a "Start simple" row of starter cards (shipped: a fresh copy;
               source tree: shell.STARTERS built by open_example); the
               example row keeps only the products.
    generator  branding/make_default_projects.py builds the three starters
               (agent_kit/starters/: starter_board, starter_case,
               starter_wheels - not examples/, which the agent forks
               products from) with the production build: each passes its own check, carries the
               tagged board, its AtechAgentScript, a thumbnail and a
               starter chat; the two-wheel base simulates (two motors turn
               their tyres and rims).

Every gate has a sabotage test that must see it fail.

    QT_QPA_PLATFORM=offscreen ATECH_FREECADCMD=<freecadcmd> \
        <bundled python> -m unittest -v test_starters_r820
"""
import ast
import json
import os
import re
import shutil
import tempfile
import time
import unittest
from unittest import mock

import test_default_projects as tdp
from test_default_projects import (ADDON, EXAMPLES, FREECADCMD, GENERATOR,
                                   Isolated, dp, ps, make_shipped)

STARTER_TITLES = ["Just the board", "Board in a case", "Two-wheel base"]
STARTER_KEYS = ["starter_board", "starter_case", "starter_wheels"]


def mark_starters(folder, titles):
    """Give the shipped entries named `titles` "kind": "starter"."""
    path = os.path.join(folder, dp.MANIFEST)
    with open(path) as fh:
        man = json.load(fh)
    for p in man["projects"]:
        if p["title"] in titles:
            p["kind"] = "starter"
            p["example"] = STARTER_KEYS[STARTER_TITLES.index(p["title"])] \
                if p["title"] in STARTER_TITLES else p["example"]
    with open(path, "w") as fh:
        json.dump(man, fh)


def ship_with_starters(folder):
    make_shipped(folder, ["Toy car", "Desk robot"] + STARTER_TITLES)
    mark_starters(folder, STARTER_TITLES)


# ------------------------------------------------------------------ kinds
class TestKinds(Isolated):
    def setUp(self):
        super().setUp()
        shutil.rmtree(self.ship)
        ship_with_starters(self.ship)

    def test_entries_split_by_kind(self):
        self.assertEqual([t for t, _k, _s in dp.entries()], ["Toy car", "Desk robot"])
        self.assertEqual([t for t, _k, _s in dp.entries(kind="starter")],
                         STARTER_TITLES)
        self.assertEqual([k for _t, k, _s in dp.entries(kind="starter")],
                         STARTER_KEYS)

    def test_install_copies_only_the_products(self):
        res = dp.install_defaults()
        self.assertEqual(res["installed"], ["Toy car", "Desk robot"])
        self.assertEqual(self.files(), ["Desk robot.FCStd", "Toy car.FCStd"])

    def test_sabotage_kind_ignored_copies_starters(self):
        with mock.patch.object(dp, "kind_of", lambda p: "product"):
            dp.install_defaults()
        self.assertIn("Just the board.FCStd", self.files(),
                      "the sabotage was not seen")

    def test_new_from_a_starter_is_a_fresh_copy(self):
        path = dp.new_from_default("Two-wheel base", open_doc=False)
        self.assertEqual(os.path.basename(path), "Two-wheel base.FCStd")
        again = dp.new_from_default("Two-wheel base", open_doc=False)
        self.assertEqual(os.path.basename(again), "Two-wheel base 2.FCStd")
        ids = {ps.read_file_ids(p)[1] for p in (path, again)}
        self.assertEqual(len(ids), 2)
        self.assertFalse(ids & self.shipped_ids)


# ------------------------------------------------------------------- Home
@unittest.skipIf(tdp._ShellCase is None, "shell fakes unavailable")
class TestHomeStarters(tdp._ShellCase if tdp._ShellCase else unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.ship = os.path.join(self.tmp, "ship")
        ship_with_starters(self.ship)
        self._ship = dp.SHIPPED_DIR

    def tearDown(self):
        dp.SHIPPED_DIR = self._ship
        super().tearDown()

    def test_start_simple_row_opens_a_fresh_copy(self):
        dp.SHIPPED_DIR = self.ship
        home = self.shell.HomeView()
        self.assertEqual([c.default_title for c in home.starter_cards], STARTER_TITLES)
        self.assertEqual([c.default_title for c in home.example_cards],
                         ["Toy car", "Desk robot"])
        self.assertEqual(home.sec_starters.text(), "START SIMPLE")
        self.assertFalse(home.sec_starters.isHidden())
        self.assertTrue(all(c in home.cards for c in home.starter_cards))
        got = []
        with mock.patch.object(dp, "new_from_default",
                               lambda t: got.append(t) or "/x/%s.FCStd" % t):
            home.starter_cards[2].clicked.emit()
        self.assertEqual(got, ["Two-wheel base"])
        home.close()

    def test_sabotage_kind_ignored_mixes_the_rows(self):
        dp.SHIPPED_DIR = self.ship
        real = dp.entries
        with mock.patch.object(dp, "entries", lambda folder=None, kind="product":
                               real(folder, "product") + real(folder, "starter")):
            home = self.shell.HomeView()
        self.assertIn("Just the board", [c.default_title for c in home.example_cards],
                      "the sabotage was not seen")
        home.close()

    def test_source_tree_builds_the_starter_examples(self):
        dp.SHIPPED_DIR = os.path.join(self.tmp, "none")
        home = self.shell.HomeView()
        self.assertEqual([c.example_key for c in home.starter_cards], STARTER_KEYS)
        self.assertEqual([c.default_title for c in home.starter_cards],
                         [None, None, None])
        got = []
        # the card's lambda looks open_example up when clicked
        with mock.patch.object(self.shell, "open_example", lambda k: got.append(k)):
            home.starter_cards[0].clicked.emit()
        self.assertEqual(got, ["starter_board"])
        home.close()

    def test_no_starters_hides_the_row(self):
        dp.SHIPPED_DIR = os.path.join(self.tmp, "none")
        with mock.patch.object(self.shell, "STARTERS", ()):
            home = self.shell.HomeView()
        self.assertEqual(home.starter_cards, [])
        self.assertTrue(home.sec_starters.isHidden())
        home.close()


# ----------------------------------------------------------------- source
def _literal(path, name):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == name
                                             for t in n.targets):
            return ast.literal_eval(n.value)
    raise KeyError(name)


class TestSource(unittest.TestCase):
    def test_one_list_of_starters(self):
        gen = _literal(GENERATOR, "STARTERS")
        sh = _literal(os.path.join(ADDON, "acadagent", "shell.py"), "STARTERS")
        self.assertEqual([k for k, _t in gen], STARTER_KEYS)
        self.assertEqual([(k, t) for k, t, _s, _i in sh], list(gen))
        starters = os.path.join(os.path.dirname(EXAMPLES), "starters")
        for k in STARTER_KEYS:
            self.assertTrue(os.path.isfile(os.path.join(starters, k + ".py")), k)
            # never among the examples the agent forks products from
            self.assertFalse(os.path.exists(os.path.join(EXAMPLES, k + ".py")), k)
        blurbs = _literal(GENERATOR, "BLURBS")
        sums = _literal(GENERATOR, "SUMMARIES")
        for k in STARTER_KEYS:
            self.assertIn(k, blurbs)
            self.assertIn(k, sums)


# -------------------------------------------------------------- generator
SIM_FC = r'''
import json, os, sys
sys.path[:0] = [os.environ["ATECH_ADDON"], os.path.join(os.environ["ATECH_ADDON"],
                "acadagent", "agent_kit"), os.path.join(os.environ["ATECH_REPO"], "projects")]
import FreeCAD as App
from acadagent import simulate as sm
doc = App.openDocument(os.environ["ATECH_FILE"])
p = sm.plan(doc)
print("SIMPLAN " + json.dumps({"motors": len(p["motors"]),
    "driven": sorted(n for m in p["motors"] for n in m["drives"])}))
'''


@unittest.skipUnless(os.path.isfile(FREECADCMD), "built app not found")
class TestGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.realpath(tempfile.mkdtemp(prefix="atech-starters-"))
        cls.out = os.path.join(cls.tmp, "out")
        t0 = time.time()
        cls.counts, cls.log = tdp.generate(cls.out, ",".join(STARTER_KEYS))
        cls.seconds = time.time() - t0
        try:
            with open(os.path.join(cls.out, "manifest.json")) as fh:
                cls.man = json.load(fh)
        except (OSError, ValueError):
            cls.man = None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_three_starters_built_and_passing(self):
        self.assertEqual(self.counts, (3, 3), self.log[-3000:])
        rows = self.man["projects"]
        self.assertEqual([p["title"] for p in rows], STARTER_TITLES)
        for p in rows:
            self.assertEqual(p["kind"], "starter")
            self.assertEqual(p["check_failures"], "", p["title"])
            self.assertEqual(p["hardware"][0]["module"], "board")
            self.assertTrue(p["trust"] and p["summary"])
        self.assertEqual([len(p["hardware"]) - 1 for p in rows], [0, 2, 2])
        import sys
        sys.stderr.write("\n[starters %.0fs] %s\n" % (self.seconds, ", ".join(
            "%s %.1fs" % (p["title"], p["seconds"]) for p in rows)))

    def test_files_are_complete(self):
        for p in self.man["projects"]:
            probs = tdp.file_problems(os.path.join(self.out, p["file"]), p)
            if p["example"] == "starter_board":
                # the board alone: no module, so no port in the chat either
                probs = [x for x in probs if x not in (
                    "no tagged module", "chat lacks ports or two suggestions")]
            self.assertEqual(probs, [], p["title"])

    def test_chat_says_starter(self):
        import zipfile
        for p in self.man["projects"]:
            with zipfile.ZipFile(os.path.join(self.out, p["file"])) as zf:
                text = json.loads(zf.read(ps.CHAT_JSON))["transcript"]["entries"][0]["text"]
            self.assertIn("a starter project", text)
            self.assertEqual(text.count('- "'), 2)

    def test_two_wheel_base_simulates(self):
        path = os.path.join(self.out, "Two-wheel base.FCStd")
        script = os.path.join(self.tmp, "simplan.py")
        with open(script, "w", encoding="utf-8") as fh:
            fh.write(SIM_FC)
        log = tdp.run_fc([script], {"ATECH_FILE": path, "ATECH_ADDON": ADDON,
                                         "ATECH_REPO": tdp.REPO}, timeout=300)
        m = re.findall(r"SIMPLAN (.*)", log)
        self.assertTrue(m, log[-2000:])
        got = json.loads(m[-1])
        self.assertEqual(got["motors"], 2)
        self.assertEqual(got["driven"], ["Rim_L", "Rim_R", "Tyre_L", "Tyre_R"])


if __name__ == "__main__":
    unittest.main()
