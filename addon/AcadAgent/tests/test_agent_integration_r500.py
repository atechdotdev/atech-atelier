"""R500-R506: agent integration (PRD "Agent integration", wave 2).

    R500  document_brief lists what the user did and what the Atech side
          holds: kept measurements, hidden parts, hand edits, cabled modules
          with each cable's length, stale modules, free parts - within
          BRIEF_MAX_CHARS, the solids list giving way first.
    R501  Undo follows the chat: a FreeCAD undo of an agent build rolls the
          workspace model.py and the panel's build record back ("Build
          undone"); a redo brings them forward; every build card has "Go
          back to this build".
    R502  Ask about this view: the camera exactly as framed (no named view,
          no fit), the composer opens with the image and keeps the draft,
          the reply runs read-only (plan mode, Read/Glob/Grep, $3) and
          changes no workspace file.
    R503  Settings: Projects folder, the appearance panel embedded, "Use
          mode default" for the budget, effort labels of both modes,
          $ATECH_AGENT_EFFORT read by claude_cli.agent_settings, "Clear old
          chats" keeps the chat folders of saved projects.
    R504  AgentPanel.start_from_example(path, title) and focus_composer().
    R505  Past chats per project: "New chat" keeps the old one in a list.

Every item has a sabotage case: the same scenario with the fix taken out
must fail the item's check.

RUN (the interpreter that ships; its path has a space, so a symlink to it
is what the fake `claude` shebang needs):
    QT_QPA_PLATFORM=offscreen <app>/Contents/Resources/bin/python \\
        -m unittest addon/AcadAgent/tests/test_agent_integration_r500.py -v
The headless half (R500, R501 against FreeCAD's real undo stack) runs in
the bundled freecadcmd (found like test_measure; ATECH_FREECADCMD wins) and
is skipped without it.
"""
import json
import os

os.environ.setdefault("ATECH_PROMPT_MODE", "fast")
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_chat_robustness as tcr  # noqa: E402  (sets HOME, Qt, settings)
import test_ws_chat_panel as twp  # noqa: E402
import test_ws_chat_round5 as tr5  # noqa: E402

from PySide6 import QtWidgets  # noqa: E402

from acadagent import build, capture, claude_cli, panel  # noqa: E402
from acadagent import settings as cfgmod  # noqa: E402

wait_until = tcr.wait_until
APP = tcr.APP
ADDON = tcr.ADDON
REPO = os.path.normpath(os.path.join(ADDON, "..", ".."))
_Obj, _Doc = twp._Obj, twp._Doc


def _find_fc():
    cands = [os.environ.get("ATECH_FREECADCMD"),
             os.path.join(REPO, "dist", "build-macos-arm64", "Atech Atelier.app",
                          "Contents", "Resources", "bin", "freecadcmd"),
             os.path.join(REPO, "dist", "build", "squashfs-root", "usr", "bin",
                          "freecadcmd"),
             shutil.which("freecadcmd")]
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


FC = _find_fc()


# ======================================================================
# R500 + R501 headless: the real brief and FreeCAD's real undo stack
# ======================================================================
PROBE = r'''
import json, os, sys, tempfile, traceback
sys.dont_write_bytecode = True
sys.path.insert(0, os.environ["R500_ADDON"])
sys.path.insert(0, os.path.join(os.environ["R500_REPO"], "projects"))
import FreeCAD as App, Part
from acadagent import build, measure, inspect_tools, export_tools
FAILS = [0]

def check(name, ok, detail=""):
    if not ok:
        FAILS[0] += 1
    print("CHECK %s %s %s" % (name, "PASS" if ok else "FAIL",
                              str(detail).replace("\n", " | ")[:600]))

def run(name, fn):
    try:
        fn()
    except Exception:
        check(name, False, traceback.format_exc())

ws = tempfile.mkdtemp(prefix="r500-")
doc = App.newDocument("R500")
doc.UndoMode = 1                 # what the GUI gives every document
App.setActiveDocument(doc.Name)
BOX = ("import Part\no = doc.addObject('Part::Feature', 'Case')\n"
       "o.Shape = Part.makeBox(%s, 10, 10)\n")

def write(code):
    with open(os.path.join(ws, build.SCRIPT), "w") as fh:
        fh.write(code)

def body(text):
    return text.split("<document_data>")[1].split("</document_data>")[0]

# ------------------------------------------------------------- R501 undo
def t_undo():
    from acadagent import panel
    write(BOX % 20)
    r1 = build.apply(ws, [build.SCRIPT], None, mode=build.IN_PROCESS)
    base = {"script": None, "intent": None, "record": None}
    n1 = panel.record_build(ws, r1.record(), r1.undo_count, "h1", base)
    write(BOX % 30)
    r2 = build.apply(ws, [build.SCRIPT], r1.record(), mode=build.IN_PROCESS)
    n2 = panel.record_build(ws, r2.record(), r2.undo_count, "h2")
    data = panel.load_builds(ws)
    check("R501_history", [e["n"] for e in data["builds"]] == [0, n1, n2]
          and (n1, n2) == (1, 2), data["builds"])
    ev = panel.undo_event(doc.UndoCount, doc.UndoNames, doc.RedoNames, data)
    check("R501_no_event_before_undo", ev is None, ev)
    # a hand edit after the build, then undo it: the build is still there
    doc.openTransaction("Move")
    doc.getObject("Case").Placement.Base = App.Vector(1, 0, 0)
    doc.commitTransaction()
    doc.undo()
    ev = panel.undo_event(doc.UndoCount, doc.UndoNames, doc.RedoNames, data)
    check("R501_hand_edit_undo_is_not_a_build_undo", ev is None,
          (doc.UndoCount, list(doc.RedoNames)))
    doc.undo()                   # the agent's build 2
    ev = panel.undo_event(doc.UndoCount, doc.UndoNames, doc.RedoNames, data)
    check("R501_undo_seen", ev is not None and ev[0] == "undo"
          and ev[1]["n"] == n2, (ev, doc.UndoCount, list(doc.RedoNames)))
    case = doc.getObject("Case")
    check("R501_doc_is_build_1", abs(case.Shape.BoundBox.XLength - 20) < 1e-6)
    data["undone"].append(data["builds"].pop())
    ok = panel.restore_build(ws, data["builds"][-1])
    with open(os.path.join(ws, build.SCRIPT)) as fh:
        code = fh.read()
    check("R501_model_py_rolled_back", ok and code == BOX % 20, code)
    doc.redo()
    ev = panel.undo_event(doc.UndoCount, doc.UndoNames, doc.RedoNames, data)
    check("R501_redo_seen", ev is not None and ev[0] == "redo"
          and ev[1]["n"] == n2, (ev, doc.UndoCount, list(doc.UndoNames)))
    # Sabotage: the rule without the transaction-name check would fire on
    # a reopened file (UndoCount 0, nothing to redo).
    def naive(uc, un, rn, d):
        top = d["builds"][-1]
        return ("undo", top) if uc < top["undo_count"] else None
    data2 = panel.load_builds(ws)
    check("R501_reopened_file_no_event",
          panel.undo_event(0, [], [], data2) is None)
    check("R501_sabotage_naive_rule_fires", naive(0, [], [], data2) is not None)

# ------------------------------------------------------------- R500 brief
def t_brief():
    import atech_ports as ap
    from acadagent import projects
    b = ap.board_object(doc)
    ap.seat(doc, "button", 3)
    hl, rib = ap.cable(doc, "light", 7, ap.module_placement(
        "light", (15, 22, 16), face="+Y", cable="-Z"))
    projects.place_free_part(doc, "knob")
    measure.record(doc, measure.measure("size", [], doc))
    lid = doc.addObject("Part::Feature", "Lid")
    lid.Shape = Part.makeBox(5, 5, 5)
    lid.Visibility = False
    doc.recompute()
    export_tools.record_override(doc, doc.getObject("Case"), transparency=40)
    text = build.document_brief(doc, selection=[])
    t = body(text)
    print("BRIEF_BEGIN\n%s\nBRIEF_END" % t)
    length = round(float(rib[0].AtechCableLength), 1)
    check("R500_cabled_with_length", "light_7: module light cabled to port 7"
          in t and ("%.1f mm long" % length) in t, length)
    check("R500_cable_not_a_user_solid", "%s: volume" % rib[0].Label not in t)
    check("R500_seated_still_listed", "button_p3: module button on port 3" in t)
    check("R500_free_part", "FREE PARTS" in t and "knob: library part knob" in t)
    check("R500_measurement", "Measurements the user kept" in t
          and "Size of the whole model" in t)
    check("R500_hidden", "HIDDEN by the user" in t and "\n  Lid" in t)
    check("R500_hand_edit", "Hand edits the user made" in t
          and "transparency 40 %" in t)
    check("R500_no_stale_yet", "STALE" not in t)
    b.Placement = App.Placement(App.Vector(5, 0, 0), App.Rotation())
    t = body(build.document_brief(doc, selection=[]))
    check("R500_stale_after_board_move", "STALE ATECH MODULES" in t
          and "button_p3: seated for where the board was" in t
          and "light_7: its cable was made for another" in t, t[-900:])
    b.Placement = App.Placement()
    # The cap: 300 more solids; the sections after the solids list stay.
    for i in range(300):
        o = doc.addObject("Part::Feature", "Rib%03d" % i)
        o.Label = "Rib%03d_" % i + "x" * 70      # long labels fill the cap
        o.Shape = Part.makeBox(1, 1, 1 + i * 0.01)
        o.Visibility = i >= 20                     # the user hid 20 of them
    doc.recompute()
    t = body(build.document_brief(doc, selection=[], cache={}))
    check("R500_within_cap", len(t) <= build.BRIEF_MAX_CHARS + 40, len(t))
    keep = ("HIDDEN by the user", "Hand edits the user made",
            "Measurements the user kept", "light_7: module light cabled",
            "FREE PARTS", "more shape objects not listed")
    check("R500_sections_survive_the_cap", all(k in t for k in keep),
          [k for k in keep if k not in t])
    # Sabotage 1: without the user-state sections the checks above fail.
    saved = build._user_state_lines
    build._user_state_lines = lambda d: []
    try:
        t2 = body(build.document_brief(doc, selection=[], cache={}))
    finally:
        build._user_state_lines = saved
    check("R500_sabotage_no_user_state_caught", "HIDDEN by the user" not in t2)
    # Sabotage 2: the old tail cut (solids first, then cut at the cap).
    saved = build._fit_brief
    def tail_cut(head, solid_lines, more, extras):
        s = "\n".join(head + solid_lines + extras)
        return s[:build.BRIEF_MAX_CHARS]
    build._fit_brief = tail_cut
    try:
        t3 = body(build.document_brief(doc, selection=[], cache={}))
    finally:
        build._fit_brief = saved
    check("R500_sabotage_tail_cut_loses_sections",
          not all(k in t3 for k in keep[:3]), (len(t3), t3[-300:]))

run("R501", t_undo)
run("R500", t_brief)
print("R500_FAILS=%d" % FAILS[0])
'''


@unittest.skipUnless(FC, "needs the bundled freecadcmd (ATECH_FREECADCMD)")
class TestHeadlessBriefAndUndo(unittest.TestCase):
    """R500 + R501 in freecadcmd: one run, every CHECK line asserted."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp(prefix="r500-fc-")
        cls.tmp = tmp
        probe = os.path.join(tmp, "probe.py")
        with open(probe, "w", encoding="utf-8") as fh:
            fh.write(PROBE)
        env = dict(os.environ)
        for k in ("PYTHONPATH", "PYTHONHOME"):
            env.pop(k, None)
        env.update(HOME=os.path.join(tmp, "home"), R500_ADDON=ADDON,
                   R500_REPO=REPO, QT_QPA_PLATFORM="offscreen",
                   ATECH_ARTIFACTS=env.get("ATECH_ARTIFACTS")
                   or os.path.join(REPO, "models"))
        os.makedirs(env["HOME"])
        out = subprocess.run([FC, probe], capture_output=True, text=True,
                             timeout=900, env=env, stdin=subprocess.DEVNULL,
                             cwd=tmp)
        cls.log = (out.stdout or "") + (out.stderr or "")
        cls.checks = {}
        for line in cls.log.splitlines():
            if line.startswith("CHECK "):
                parts = line.split(" ", 3)
                cls.checks[parts[1]] = (parts[2], parts[3] if len(parts) > 3
                                        else "")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _check(self, name):
        self.assertIn(name, self.checks, "check %s did not run:\n%s"
                      % (name, "\n".join(self.log.splitlines()[-40:])))
        verdict, detail = self.checks[name]
        self.assertEqual(verdict, "PASS", "%s: %s" % (name, detail))

    def test_r500_brief_sections(self):
        for name in ("R500_cabled_with_length", "R500_cable_not_a_user_solid",
                     "R500_seated_still_listed", "R500_free_part",
                     "R500_measurement", "R500_hidden", "R500_hand_edit",
                     "R500_no_stale_yet", "R500_stale_after_board_move"):
            self._check(name)

    def test_r500_cap(self):
        self._check("R500_within_cap")
        self._check("R500_sections_survive_the_cap")

    def test_r500_sabotage(self):
        self._check("R500_sabotage_no_user_state_caught")
        self._check("R500_sabotage_tail_cut_loses_sections")

    def test_r501_real_undo_stack(self):
        for name in ("R501_history", "R501_no_event_before_undo",
                     "R501_hand_edit_undo_is_not_a_build_undo",
                     "R501_undo_seen", "R501_doc_is_build_1",
                     "R501_model_py_rolled_back", "R501_redo_seen",
                     "R501_reopened_file_no_event",
                     "R501_sabotage_naive_rule_fires"):
            self._check(name)
        self.assertIn("R500_FAILS=0", self.log)


# ======================================================================
# offscreen panel cases
# ======================================================================
class _UndoDoc(_Doc):
    """A stub document with FreeCAD's undo-stack attributes."""

    def __init__(self, name, uid, objects=()):
        super().__init__(name, uid, objects)
        self.UndoCount = 0
        self.UndoNames = []
        self.RedoNames = []

    def commit(self, name):
        self.UndoNames.insert(0, name)
        self.UndoCount += 1
        self.RedoNames = []

    def undo(self):
        self.RedoNames.insert(0, self.UndoNames.pop(0))
        self.UndoCount -= 1

    def redo(self):
        self.UndoNames.insert(0, self.RedoNames.pop(0))
        self.UndoCount += 1


class Case(twp.Case):

    def write(self, ws, name, text):
        with open(os.path.join(ws, name), "w", encoding="utf-8") as fh:
            fh.write(text)

    def read(self, ws, name=build.SCRIPT):
        try:
            with open(os.path.join(ws, name), encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None

    def fake_builds(self, doc):
        """build.start stand-in: an agent build commits one undo step on
        `doc` and returns an ok Result carrying the UndoCount."""
        calls = []

        def start(ws, files, previous, preview=False):
            calls.append((ws, list(files)))
            doc.commit(build.BUILD_TXN)
            res = build.Result(True, "model.py", created=["Case"],
                               measurements=[{"name": "Case", "label": "Case",
                                              "volume_mm3": 1000.0,
                                              "solids": 1,
                                              "bbox_bound": [10, 10, 10]}],
                               doc=doc.Name, uid=doc.Uid,
                               labels={"Case": "Case"},
                               undo_count=doc.UndoCount)
            return build.PendingBuild(res)
        self.patch(build, "start", start)
        return calls

    def final_build(self, st):
        self.p._cur = st
        self.p._build_card = None
        self.p._build_sig = None
        self.p._run_build([build.SCRIPT])
        self.assertTrue(wait_until(lambda: self.p._pending is None, 10))
        return self.p._build_card


class TestR501UndoFollowsTheChat(Case):

    def setUp(self):
        super().setUp()
        self.doc = self.fc.add(_UndoDoc("Part", "uid-undo"))
        self.st = self.turn_state(key="uid-undo", doc=self.doc)
        self.calls = self.fake_builds(self.doc)
        self.p._busy = False
        self.p._keep_base(self.st)

    def two_builds(self):
        self.write(self.st.ws, build.SCRIPT, "v1\n")
        c1 = self.final_build(self.st)
        self.write(self.st.ws, build.SCRIPT, "v2\n")
        c2 = self.final_build(self.st)
        return c1, c2

    def test_r501_cards_and_history(self):
        c1, c2 = self.two_builds()
        for card, n in ((c1, 1), (c2, 2)):
            self.assertEqual(card.go_back, n)
            self.assertEqual(card.action_btn.text(), panel.GO_BACK_TEXT)
            self.assertFalse(card.action_btn.isHidden())
        data = panel.load_builds(self.st.ws)
        self.assertEqual([e["n"] for e in data["builds"]], [0, 1, 2])
        self.assertEqual([e["undo_count"] for e in data["builds"]],
                         [None, 1, 2])

    def test_r501_undo_rolls_model_py_and_record_back(self):
        self.two_builds()
        rec1 = panel.load_builds(self.st.ws)["builds"][1]["record"]
        self.doc.undo()
        self.assertEqual(self.p._check_undo(), "undo")
        self.assertEqual(self.read(self.st.ws), "v1\n")
        self.assertEqual(self.st.prev["names"], rec1["names"])
        self.assertIn(panel.BUILD_UNDONE, self.titles())
        self.assertIsNone(self.p._check_undo(), "one notice per undo")
        # undo build 1 too: the workspace before the first build (none)
        self.doc.undo()
        self.assertEqual(self.p._check_undo(), "undo")
        self.assertIsNone(self.read(self.st.ws))
        self.assertIsNone(self.st.prev)
        # redo both
        self.doc.redo()
        self.assertEqual(self.p._check_undo(), "redo")
        self.assertEqual(self.read(self.st.ws), "v1\n")
        self.doc.redo()
        self.assertEqual(self.p._check_undo(), "redo")
        self.assertEqual(self.read(self.st.ws), "v2\n")
        self.assertIn(panel.BUILD_REDONE, self.titles())

    def test_r501_sabotage_hand_edit_undo_changes_nothing(self):
        """Undoing the user's own step must NOT roll the chat back. After
        a build, the file is reopened (an empty undo stack), the user
        moves a part and undoes that: UndoCount (0) is below the build's
        (1), but the step on the redo stack is the "Move"."""
        self.write(self.st.ws, build.SCRIPT, "v1\n")
        self.final_build(self.st)
        self.doc.UndoCount, self.doc.UndoNames, self.doc.RedoNames = 0, [], []
        self.doc.commit("Move")
        self.doc.undo()
        self.assertIsNone(self.p._check_undo())
        self.assertEqual(self.read(self.st.ws), "v1\n")
        self.assertNotIn(panel.BUILD_UNDONE, self.titles())
        # Sabotage: any undone step taken for an agent build fires.
        self.patch(panel, "UNDO_TXNS", panel.UNDO_TXNS + ("Move",))
        self.assertEqual(self.p._check_undo(), "undo")

    def test_r501_go_back_to_a_build(self):
        c1, _c2 = self.two_builds()
        self.p._cur = None
        c1.action_btn.click()
        self.assertTrue(wait_until(lambda: self.p._pending is None, 10))
        self.assertEqual(self.read(self.st.ws), "v1\n")
        self.assertEqual(len(self.calls), 3, "rebuilt from build 1's script")
        self.assertIn(build.SCRIPT, self.calls[-1][1])
        data = panel.load_builds(self.st.ws)
        self.assertEqual([e["n"] for e in data["builds"]], [0, 1, 2, 3])
        self.assertIn("Going back to build 1", self.titles())
        # the current build: no rebuild
        n = len(self.calls)
        self.assertFalse(self.p.go_back_to_build(3))
        self.assertEqual(len(self.calls), n)

    def test_r501_go_back_survives_a_transcript_restore(self):
        c1, _ = self.two_builds()
        snap = self.p._snapshot("uid-undo")
        gb = [e.get("go_back") for e in snap["entries"] if e["kind"] == "card"]
        self.assertIn(1, gb)
        self.p._clear_transcript()
        self.p._restore(snap)
        backs = [c for c in self.p.findChildren(panel.ToolCard)
                 if getattr(c, "go_back", None) == 1 and not c.isHidden()]
        self.assertTrue(backs)
        self.assertEqual(backs[-1].action_btn.text(), panel.GO_BACK_TEXT)


class TestR502AskAboutThisView(Case):

    def capture_fake(self):
        seen = []

        def fake_c2p(p, view_name=capture.AUTO, fit=True, **_k):
            seen.append((view_name, fit))
            path = p.capture_path()
            with open(path, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            p.add_shot(path, "view")
            return path
        self.patch(capture, "capture_to_panel", fake_c2p)
        return seen

    def test_r502_camera_as_framed_with_the_real_capture(self):
        """capture.capture with what ask_in_chat asks for: no turn, no fit,
        only the save (the round-5 view stub records every camera call)."""
        from acadagent import vision
        v = tr5._View()
        gui = types.ModuleType("FreeCADGui")
        gui.ActiveDocument = types.SimpleNamespace(ActiveView=v)
        saved = sys.modules.get("FreeCADGui")
        sys.modules["FreeCADGui"] = gui
        try:
            self.fc.add(_Doc("Part", "uid-v", [_Obj("Body")]))
            self.assertTrue(vision.ask_in_chat(panel=self.p))
        finally:
            if saved is not None:
                sys.modules["FreeCADGui"] = saved
            else:
                sys.modules.pop("FreeCADGui", None)
        self.assertEqual([c[0] for c in v.calls], ["stop", "save"], v.calls)
        # Sabotage: the pre-R500 call (views_for, fitted) turns and fits.
        v2 = tr5._View()
        gui.ActiveDocument = types.SimpleNamespace(ActiveView=v2)
        sys.modules["FreeCADGui"] = gui
        try:
            capture.capture_to_panel(self.p, view_name="Isometric")
        finally:
            if saved is not None:
                sys.modules["FreeCADGui"] = saved
            else:
                sys.modules.pop("FreeCADGui", None)
        self.assertIn("fit", [c[0] for c in v2.calls])

    def test_r502_composer_keeps_the_draft_and_runs_read_only(self):
        from acadagent import vision
        os.environ["ATECH_PROMPT_MODE"] = "quality"     # design: $25, xhigh
        self.addCleanup(os.environ.__setitem__, "ATECH_PROMPT_MODE", "fast")
        seen = self.capture_fake()
        self.fc.add(_Doc("Part", "uid-v", [_Obj("Body")]))
        self.p.input.setPlainText("is the lid too thin")
        self.assertTrue(vision.ask_in_chat(panel=self.p))
        self.assertEqual(seen, [(None, False)])
        self.assertEqual(self.p.input.toPlainText(), "is the lid too thin",
                         "the draft is kept")
        self.assertEqual(self.turns(), [], "nothing sent by itself")
        self.assertEqual(self.p.input.placeholderText(),
                         self.p.VIEW_PLACEHOLDER)
        ws = self.p._docs["uid-v"].ws
        before = build.snapshot(ws)
        self.p._on_send()
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        a = t["argv"]
        self.assertEqual(a[a.index("--permission-mode") + 1], "plan")
        self.assertEqual(a[a.index("--tools") + 1], claude_cli.VIEW_TOOLS)
        self.assertNotIn("--allowedTools", a)
        self.assertNotIn("--append-system-prompt-file", a)
        self.assertEqual(a[a.index("--max-budget-usd") + 1], "3.00")
        self.assertNotIn("--effort", a)
        self.assertIn(os.path.basename(self.p._turn_shots[0]), t["stdin"])
        self.assertEqual(build.snapshot(ws), before,
                         "no workspace file changed")
        self.assertEqual(self.cards("Looking at the view")[-1].spec[0],
                         "Looking at the view")
        # The next message is a design turn again.
        self.send("make it taller")
        self.assertTrue(self.idle())
        a2 = self.turns()[-1]["argv"]
        self.assertEqual(a2[a2.index("--permission-mode") + 1], "acceptEdits")
        # Sabotage: the same send as a design turn has write tools, a
        # system prompt and copies reference files into the workspace.
        self.assertNotEqual(a2[a2.index("--tools") + 1], claude_cli.VIEW_TOOLS)
        self.assertIn("--append-system-prompt-file", a2)


class TestR503Settings(tcr.Base):

    def setUp(self):
        super().setUp()
        mode = os.environ.get("ATECH_PROMPT_MODE")
        os.environ.pop("ATECH_PROMPT_MODE", None)     # the settings decide
        self.addCleanup(os.environ.__setitem__, "ATECH_PROMPT_MODE",
                        mode or "fast")

    def dialog(self):
        dlg = cfgmod.SettingsDialog()
        self.addCleanup(dlg.deleteLater)
        return dlg

    def test_r503_budget_use_mode_default(self):
        cfgmod.update(agent_quality="quality", agent_budget_usd=7.5,
                      agent_budget_user=True)
        self.assertEqual(claude_cli.agent_settings()["budget"], 7.5)
        dlg = self.dialog()
        self.assertEqual(dlg.agent_budget.value(), 7.5)
        dlg.budget_default.click()
        self.assertEqual(dlg.agent_budget.value(), claude_cli.QUALITY_BUDGET_USD)
        dlg._on_save()
        cfg = cfgmod.load()
        self.assertIsNone(cfg["agent_budget_usd"])
        self.assertFalse(cfg["agent_budget_user"])
        self.assertEqual(claude_cli.agent_settings()["budget"],
                         claude_cli.QUALITY_BUDGET_USD)
        # an untouched budget follows a mode change in the dialog
        dlg2 = self.dialog()
        dlg2.agent_quality.setCurrentIndex(dlg2.agent_quality.findData(
            cfgmod.FAST))
        self.assertEqual(dlg2.agent_budget.value(),
                         claude_cli.DEFAULT_BUDGET_USD)
        # Sabotage: Save without the reset keeps the user's budget.
        cfgmod.update(agent_budget_usd=7.5, agent_budget_user=True)
        dlg3 = self.dialog()
        dlg3._on_save()
        self.assertEqual(cfgmod.load()["agent_budget_usd"], 7.5)

    def test_r503_effort_labels_and_env(self):
        os.environ["ATECH_AGENT_EFFORT"] = "high"
        self.addCleanup(os.environ.pop, "ATECH_AGENT_EFFORT", None)
        cfgmod.update(agent_quality="quality", agent_effort="")
        self.assertEqual(claude_cli.agent_settings()["effort"], "high")
        label = self.dialog().agent_effort.itemText(0)
        self.assertIn("quality: high", label)
        self.assertIn("fast:", label)
        # the user's own effort wins; fast mode forces none
        cfgmod.update(agent_effort="low")
        self.assertEqual(claude_cli.agent_settings()["effort"], "low")
        cfgmod.update(agent_effort="", agent_quality="fast")
        self.assertFalse(claude_cli.agent_settings()["effort"])
        # Sabotage: an unknown level is not passed on.
        os.environ["ATECH_AGENT_EFFORT"] = "turbo"
        cfgmod.update(agent_quality="quality")
        self.assertEqual(claude_cli.agent_settings()["effort"],
                         claude_cli.QUALITY_EFFORT)

    def test_r503_projects_folder_row(self):
        from acadagent import projects_store
        os.environ.pop("ATECH_PROJECTS_DIR", None)
        dlg = self.dialog()
        self.assertEqual(dlg.projects_folder.text(),
                         projects_store.projects_dir())
        new = os.path.join(self.tmp, "My Projects")
        dlg.projects_folder.setText(new)
        dlg._on_save()
        self.assertEqual(projects_store.projects_dir(), new)
        projects_store.set_projects_dir(None)

    def test_r503_appearance_embedded(self):
        """The dialog embeds shell.appearance_panel (its real body needs
        FreeCAD's viewport, so a stand-in widget is handed out here); a
        panel that cannot be built leaves the dialog working."""
        from acadagent import shell
        made = []

        def fake(parent=None):
            w = QtWidgets.QWidget(parent)
            w.setObjectName("AppearancePanel")
            made.append(w)
            return w
        saved = shell.appearance_panel
        shell.appearance_panel = fake
        try:
            dlg = self.dialog()
        finally:
            shell.appearance_panel = saved
        self.assertIs(dlg.appearance, made[0])
        self.assertIs(dlg.appearance.parent(), dlg)

        def boom(parent=None):
            raise RuntimeError("no viewport")
        shell.appearance_panel = boom
        try:
            dlg2 = self.dialog()
        finally:
            shell.appearance_panel = saved
        self.assertIsNone(dlg2.appearance)
        self.assertIsNotNone(dlg2.projects_folder)

    def test_r503_clear_keeps_saved_projects_chats(self):
        root = os.path.join(self.tmp, "agent")
        dirs = {n: os.path.join(root, "chat-%s" % n) for n in "abcd"}
        for d in dirs.values():
            os.makedirs(d)
        saved_file = os.path.join(self.tmp, "Lamp.FCStd")
        with open(saved_file, "w") as fh:
            fh.write("x")
        with open(os.path.join(root, "sessions.json"), "w") as fh:
            json.dump({"k1": {"ws": dirs["a"], "path": saved_file},
                       "k2": {"ws": dirs["b"], "path":
                              os.path.join(self.tmp, "gone.FCStd")}}, fh)
        with open(os.path.join(root, "past_chats.json"), "w") as fh:
            json.dump({"k1": [{"ws": dirs["c"]}], "k2": [{"ws": dirs["d"]}]},
                      fh)
        removed, failed = cfgmod.clear_workspaces(root=root)
        self.assertEqual((removed, failed), (2, 0))
        self.assertTrue(os.path.isdir(dirs["a"]))
        self.assertTrue(os.path.isdir(dirs["c"]))
        self.assertFalse(os.path.isdir(dirs["b"]))
        self.assertFalse(os.path.isdir(dirs["d"]))
        # Sabotage: the project file gone -> its chats go too.
        os.unlink(saved_file)
        self.assertEqual(cfgmod.clear_workspaces(root=root), (2, 0))


class TestR504ExampleAndFocus(Case):

    def test_r504_start_from_example_builds_through_the_chat(self):
        from acadagent import shell
        path = shell.example_path(shell.EXAMPLES[0][0])
        if path is None:
            self.skipTest("no example in this tree")
        doc = _UndoDoc("Ex", "uid-ex")

        def new(name="Unnamed"):
            doc.Name = name
            self.fc.docs[name] = doc
            self.fc.mod.ActiveDocument = doc
            return doc
        self.fc.mod.newDocument = new
        calls = self.fake_builds(doc)
        self.patch(build, "prepare_workspace", lambda *a, **k: None)
        st = self.p.start_from_example(path, "Desk robot")
        self.assertIsNotNone(st)
        self.assertTrue(wait_until(lambda: self.p._pending is None, 10))
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(self.read(st.ws), fh.read())
        self.assertEqual(doc.Label, "Desk robot")
        self.assertIs(self.p._docs["uid-ex"], st)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], st.ws)
        self.assertIn("Starting from the desk robot example", self.titles())
        intent = shell._example_intent(path)
        if intent is not None:
            with open(os.path.join(st.ws, build.INTENT)) as fh:
                self.assertEqual(json.load(fh), intent)
        self.assertEqual([e["n"] for e in panel.load_builds(st.ws)["builds"]],
                         [0, 1])
        # shell.open_example hands over to the panel (the W6 hook)
        seen = []
        self.patch(self.p, "start_from_example",
                   lambda p, t: seen.append((p, t)) or "ok")
        self.patch(shell, "chat_panel", lambda: self.p)
        self.assertEqual(shell.open_example(shell.EXAMPLES[0][0]), "ok")
        self.assertEqual(seen[0][0], path)

    def test_r504_focus_composer_keeps_the_draft(self):
        self.p.input.setPlainText("half a thought")
        self.assertTrue(self.p.focus_composer())
        self.assertEqual(self.p.input.toPlainText(), "half a thought")
        self.assertEqual(self.p.input.textCursor().position(),
                         len("half a thought"))


class TestR505PastChats(Case):

    def test_r505_new_chat_keeps_the_old_one(self):
        self.fc.add(_Doc("Lamp", "uid-lamp", [_Obj("Body")]))
        os.environ["FAKE_SID"] = "sid-first"
        self.send("a bedside lamp")
        self.assertTrue(self.idle())
        first = self.p._docs["uid-lamp"]
        self.assertTrue(self.p.new_chat())
        past = self.p.past_chats()
        self.assertEqual([c["title"] for c in past], ["a bedside lamp"])
        self.assertEqual(past[0]["ws"], first.ws)
        self.assertEqual(past[0]["sid"], "sid-first")
        self.assertFalse(self.p.btn_past.isHidden())
        os.environ["FAKE_SID"] = "sid-second"
        self.send("a desk fan")
        self.assertTrue(self.idle())
        self.assertTrue(self.p.new_chat())
        self.assertEqual([c["title"] for c in self.p.past_chats()],
                         ["a desk fan", "a bedside lamp"])
        # persisted
        with open(panel.past_chats_path(), encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)["uid-lamp"]), 2)
        # open the first again: its folder, session and transcript
        self.assertTrue(self.p.open_past_chat(1))
        st = self.p._docs["uid-lamp"]
        self.assertEqual(st.ws, first.ws)
        self.assertEqual(st.sid, "sid-first")
        self.assertIn("a bedside lamp", self.bubbles())
        self.assertNotIn("a desk fan", self.bubbles())
        self.send("make it taller")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        self.assertEqual(t["argv"][t["argv"].index("--resume") + 1],
                         "sid-first")
        self.assertIn(first.ws, self.p.workspaces())
        # Sabotage: a New chat that keeps nothing leaves no past chat.
        self.patch(self.p, "_archive_chat", lambda *a, **k: False)
        self.p._past = {}
        self.assertTrue(self.p.new_chat())
        self.assertEqual(self.p.past_chats(), [])


if __name__ == "__main__":
    unittest.main()
