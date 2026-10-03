"""WS-CHAT round 2, the panel half, headless against the REAL AgentPanel
with the fake `claude` of test_chat_robustness (extended here with a
`fixture` mode that replays an NDJSON file).

Items: S16/S10/R78 (argv through the panel), R35 (stdin, 0600 system
prompt file), S17 (read-only library copies), R67, R70, R73, R74, R75, R76,
R77, R81, S02, S04, S07, S26, R24, R53, R54, R56, R36.

RUN (the interpreter that ships):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest addon/AcadAgent/tests/test_ws_chat_panel.py -v
"""
import json
import os
import stat
import sys
import tempfile
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_chat_robustness as tcr  # noqa: E402  (sets HOME, Qt, settings)

from PySide6 import QtGui, QtWidgets  # noqa: E402

from acadagent import build, capture, claude_cli, engine, panel  # noqa: E402
from acadagent import settings as cfgmod  # noqa: E402

# A replay mode for the shared fake: FAKE_FIXTURE names an NDJSON file.
if 'mode == "fixture"' not in tcr.FAKE:
    tcr.FAKE = tcr.FAKE.replace(
        'elif mode == "weird":',
        'elif mode == "fixture":\n'
        '    out.write(open(os.environ["FAKE_FIXTURE"], encoding="utf-8")'
        '.read()); out.flush()\n'
        'elif mode == "weird":')

wait_until = tcr.wait_until


# ------------------------------------------------------------ FreeCAD stub
class _Obj(object):
    def __init__(self, name, typeid="Part::Feature", shape=True):
        self.Name = self.Label = name
        self.TypeId = typeid
        if shape:
            self.Shape = object()


class _Doc(object):
    def __init__(self, name, uid, objects=()):
        self.Name = self.Label = name
        self.Uid = uid
        self.Objects = list(objects)

    def getObject(self, name):                         # noqa: N802
        for o in self.Objects:
            if o.Name == name:
                return o
        return None


class FCStub(object):
    """The handful of FreeCAD calls the panel makes."""

    def __init__(self):
        self.docs = {}
        self.mod = types.ModuleType("FreeCAD")
        self.mod.ActiveDocument = None
        self.mod.listDocuments = lambda: dict(self.docs)
        self.mod.getDocument = lambda n: self.docs[n]
        self.mod.setActiveDocument = self._set
        self.mod.newDocument = self._new
        self.mod.Console = types.SimpleNamespace(
            PrintLog=lambda *a: None, PrintMessage=lambda *a: None)
        self.created = []

    def _set(self, n):
        self.mod.ActiveDocument = self.docs[n]

    def _new(self, name="Unnamed"):
        d = _Doc(name, "uid-new-%d" % len(self.created))
        self.created.append(d)
        self.docs[name] = d
        self.mod.ActiveDocument = d
        return d

    def add(self, doc, active=True):
        self.docs[doc.Name] = doc
        if active:
            self.mod.ActiveDocument = doc
        return doc

    def close(self, doc):
        self.docs.pop(doc.Name, None)
        if self.mod.ActiveDocument is doc:
            self.mod.ActiveDocument = None


class Case(tcr.PanelBase):
    """A panel with a FreeCAD stub (no document unless a test opens one)."""

    def setUp(self):
        self.fc = FCStub()
        sys.modules["FreeCAD"] = self.fc.mod
        self._saved = {}
        super().setUp()

    def tearDown(self):
        super().tearDown()
        for (obj, name), val in self._saved.items():
            setattr(obj, name, val)
        sys.modules.pop("FreeCAD", None)

    def patch(self, obj, name, value):
        if (obj, name) not in self._saved:
            self._saved[(obj, name)] = getattr(obj, name)
        setattr(obj, name, value)

    def fixture(self, records):
        path = os.path.join(self.tmp, "fixture.ndjson")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("".join(json.dumps(r) + "\n" for r in records))
        os.environ["FAKE_MODE"] = "fixture"
        os.environ["FAKE_FIXTURE"] = path

    def cards(self, title=None):
        out = []
        for c in self.p.findChildren(panel.ToolCard):
            if c.isHidden():
                continue
            name = c.findChild(QtWidgets.QLabel, "ToolName").text()
            if title is None or name == title:
                out.append(c)
        return out

    def bubbles(self):
        return [b.label.text() for b in self.p.findChildren(panel.Bubble)
                if not b.isHidden()]

    def turn_state(self, ws=None, key="uid-t", doc=None):
        """A ChatState as if a turn were in flight."""
        doc = doc or self.fc.add(_Doc("Part", key))
        st = panel.ChatState(key, doc.Name, ws or build.new_workspace())
        self.p._docs[key] = st
        self.p._cur = st
        self.p._applied = {}
        self.p._before = {}
        self.p._busy = True
        self.p._stopped = False
        self.p._build_card = None
        self.p._build_sig = None
        self.p._turn_failed = False
        return st


def _now(res):
    """build.start stand-in (R93): a PendingBuild that is already done."""
    return lambda *a, **k: build.PendingBuild(res)


def _ok_result(n=1, vol=1000.0):
    return build.Result(True, "model.py", created=["Box"], measurements=[
        {"name": "Box", "label": "Box", "volume_mm3": vol, "solids": 1,
         "bbox_bound": [10, 10, 10]}] * n, doc="Part")


# ------------------------------------------------------ argv via the panel
class TestLaunchThroughPanel(Case):

    def test_s16_r78_s10_r35_isolated_launch(self):
        self.send("-5 mm thinner")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        a = t["argv"]
        # R35: prompt on stdin, intact even with a leading "-".
        self.assertTrue(t["stdin"].startswith("-5 mm thinner\n\n---\n"))
        self.assertNotIn("-5 mm thinner", " ".join(a))
        self.assertIn("--append-system-prompt-file", a)
        self.assertNotIn("--append-system-prompt", a)
        self.assertIn("CAD agent inside Atech Atelier", t["sp"])
        # S16 / R78: the isolating flags, from agent_argv.
        for flag in ("--strict-mcp-config", "--disable-slash-commands",
                     "--exclude-dynamic-system-prompt-sections",
                     "--include-partial-messages"):
            self.assertIn(flag, a)
        self.assertEqual(a[a.index("--tools") + 1],
                         "Read,Write,Edit,Bash,Glob,Grep")
        self.assertEqual(a[a.index("--setting-sources") + 1], "")
        self.assertEqual(a[a.index("--max-budget-usd") + 1], "3.00")
        # S10: exactly ./check.
        i = a.index("--allowedTools")
        self.assertEqual(a[i + 1:i + 3], ["Bash(./check)", "Bash(./check *)"])
        # R14: one --add-dir, the workspace.
        self.assertEqual([a[k + 1] for k, x in enumerate(a)
                          if x == "--add-dir"], [t["cwd"]])
        self.assertNotIn("--model", a)          # S26 default
        print("\n  [S16] panel argv: %s" % " ".join(
            x if len(x) < 60 else "<%d chars>" % len(x) for x in a))

    def test_s26_model_and_effort_reach_argv(self):
        cfgmod.update(agent_model="sonnet", agent_effort="high",
                      agent_budget_usd=0)
        self.send("x")
        self.assertTrue(self.idle())
        a = self.turns()[-1]["argv"]
        self.assertEqual(a[a.index("--model") + 1], "sonnet")
        self.assertEqual(a[a.index("--effort") + 1], "high")
        self.assertNotIn("--max-budget-usd", a)

    def test_s16_r125_permission_denials_are_logged_not_shown(self):
        # S16 made denials visible; R125 (D48) moved them to the log: an
        # agent's refused exploratory `ls` read to users as an error.
        logged = []
        self.patch(panel, "_log", logged.append)
        self.fixture([
            {"type": "system", "subtype": "init", "session_id": "s-d"},
            {"type": "result", "subtype": "success", "is_error": False,
             "result": "Done.", "duration_ms": 1000,
             "permission_denials": [{"tool_name": "Bash", "tool_use_id": "t",
                                     "tool_input": {"command": "ls ~"}}]}])
        self.send("list my home")
        self.assertTrue(self.idle())
        text = "\n".join(c.body.text() for c in self.cards("Designing"))
        self.assertNotIn("not allowed", text)
        self.assertTrue(any("Bash ls ~" in m for m in logged), logged)

    def test_s17_library_copies_are_readonly_in_one_workspace(self):
        lib = tempfile.mkdtemp(prefix="lib-", dir=self.tmp)
        for name in ("atech_ports.py", "atech_modules.py"):
            with open(os.path.join(lib, name), "w") as fh:
                fh.write("# %s\n" % name)
        self.patch(build, "_projects_dir", lambda: lib)
        self.send("seat a button")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        a = t["argv"]
        self.assertEqual([a[k + 1] for k, x in enumerate(a)
                          if x == "--add-dir"], [t["cwd"]])
        self.assertNotIn(lib, " ".join(a))
        for name in ("atech_ports.py", "atech_modules.py"):
            copy = os.path.join(t["cwd"], "reference", name)
            self.assertTrue(os.path.isfile(copy), copy)
            self.assertEqual(stat.S_IMODE(os.stat(copy).st_mode), 0o444)
            self.assertIn(copy, t["sp"])
        # Every turn refreshes the copy, even over a read-only file.
        self.send("again")
        self.assertTrue(self.idle())


# ------------------------------------------------------------- R73 / R70
class TestWelcomeAndNewChat(Case):

    def test_r73_nodoc_examples_fill_the_input(self):
        self.assertIsNone(self.fc.mod.ActiveDocument)
        w = self.p._welcome("nodoc")
        w.picked.emit("Make a 60 x 40 x 20 mm box with 2 mm walls")
        self.assertEqual(self.p.input.toPlainText(),
                         "Make a 60 x 40 x 20 mm box with 2 mm walls")
        w.rows[1].click()
        self.assertEqual(self.p.input.toPlainText(), w.rows[1].text())

    def test_r70_new_chat(self):
        doc = self.fc.add(_Doc("Part", "uid-n", [_Obj("Body")]))
        os.environ["FAKE_SID"] = "sid-1"
        self.send("a box")
        self.assertTrue(self.idle())
        ws1 = self.turns()[-1]["cwd"]
        self.send("taller")
        self.assertTrue(self.idle())
        self.assertIn("--resume", self.turns()[-1]["argv"])
        self.assertTrue(self.bubbles())
        self.p.new_chat()
        tcr.APP.processEvents()
        self.assertEqual(self.bubbles(), [])
        self.assertIsNotNone(self.p._empty, "the Welcome is back")
        self.send("a cylinder")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        self.assertNotIn("--resume", t["argv"])
        self.assertNotEqual(t["cwd"], ws1)
        self.assertEqual([o.Name for o in doc.Objects], ["Body"])
        self.assertEqual(self.p._attempt, 0)


# ------------------------------------------------------------------ R67
class TestSetupFailures(Case):

    def test_r67_new_workspace_raising_restores_the_input(self):
        def boom():
            raise OSError(28, "No space left on device")
        self.patch(build, "new_workspace", boom)
        self.send("keep me")
        self.assertFalse(self.p._busy)
        self.assertEqual(self.p.input.toPlainText(), "keep me")
        self.assertIn("Could not start the agent", self.titles())
        self.assertEqual(self.turns(), [])

    def test_r67_deleted_workspace_is_recreated(self):
        import shutil
        self.fc.add(_Doc("Part", "uid-del"))
        os.environ["FAKE_SID"] = "sid-del"
        self.send("a box")
        self.assertTrue(self.idle())
        ws1 = self.turns()[-1]["cwd"]
        shutil.rmtree(ws1)
        self.send("taller")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        # A new folder (new_workspace names by the second, so within the
        # same second it may reuse the freed name - it is still new).
        self.assertTrue(os.path.isdir(t["cwd"]))
        # A session lives in its working folder; it is not resumed from a
        # different one.
        self.assertNotIn("--resume", t["argv"])
        self.assertNotIn("Could not start the agent", self.titles())


# ------------------------------------------------------ R74 / R75 / R76
TB_5K = ("x" * 99 + "\n") * 50 + (
    'Traceback (most recent call last):\n'
    '  File "/opt/Atech/usr/Mod/AcadAgent/acadagent/runner.py", line 122, '
    'in run\n    exec(code, env)\n'
    '  File "/home/u/ws/model.py", line 7, in <module>\n'
    '    box = Part.makeBox(a, 2, 3)\n'
    "NameError: name 'a' is not defined\n")


class TestBuildCards(Case):

    def test_r74_fix_message_starts_with_the_exception(self):
        self.assertGreater(len(TB_5K), 5000)
        for msg in (panel._fix_report(TB_5K), self.p._fix_message(TB_5K)):
            body = msg.split("\n", 1)[1] if msg.startswith("The script") \
                else msg
            self.assertTrue(body.startswith("NameError: name 'a' is not "
                                            "defined"), body[:80])
            self.assertLessEqual(len(body), 1700)
        card = panel._card_error(TB_5K)
        self.assertEqual(card, "model.py line 7: NameError: name 'a' is not "
                               "defined")
        self.assertNotIn("/usr/Mod/", card)

    def test_r76_five_identical_previews_one_card(self):
        self.turn_state()
        self.patch(build, "start", _now(_ok_result()))
        for _ in range(5):
            self.p._run_build(["model.py"], preview=True)
        cards = self.cards("Building the model")
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].body.text().count("Box"), 1)
        # A changed result updates the same card in place.
        self.patch(build, "start", _now(_ok_result(vol=2000.0)))
        self.p._run_build(["model.py"], preview=True)
        self.assertEqual(len(self.cards("Building the model")), 1)
        self.assertIn("2 000.0", cards[0].body.text())

    def test_r75_failed_build_demotes_the_reply(self):
        st = self.turn_state()
        with open(os.path.join(st.ws, "model.py"), "w") as fh:
            fh.write("x = 1\n")
        self.patch(build, "start", _now(build.Result(
            False, "model.py", error=TB_5K)))
        sent = []
        self.patch(self.p, "_send_fix", sent.append)
        self.p._on_claude_done("Built an 18-tooth pinion.", {})
        self.assertNotIn("Built an 18-tooth pinion.", self.bubbles())
        body = self.cards("Building the model")[0].body.text()
        self.assertIn("Agent: Built an 18-tooth pinion.", body)
        self.assertEqual(len(sent), 1)
        self.assertTrue(sent[0].split("\n", 1)[1].startswith("NameError"))

    def test_r75_good_build_keeps_the_reply(self):
        st = self.turn_state()
        with open(os.path.join(st.ws, "model.py"), "w") as fh:
            fh.write("x = 1\n")
        self.patch(build, "start", _now(_ok_result()))
        self.patch(build, "failures", lambda res: "")
        self.p._on_claude_done("Built a box.", {})
        self.assertIn("Built a box.", self.bubbles())

    def test_r81_closed_document_is_not_rebuilt_into_untitled(self):
        st = self.turn_state()
        self.fc.close(self.fc.docs["Part"])
        called = []
        self.patch(build, "start", lambda *a, **k: called.append(a))
        self.p._run_build(["model.py"], preview=True)
        self.assertEqual(called, [])
        self.assertEqual(self.fc.created, [])
        self.assertIn("The document was closed", self.titles())
        self.assertFalse(self.p._busy)
        self.assertEqual(st.key, "uid-t")


# ------------------------------------------------------------------ S19
class TestStreaming(Case):

    def test_s19_partial_text_and_writing_line_on_the_card(self):
        sys.path.insert(0, HERE)
        from test_ws_chat_cli import PARTIAL_WRITE
        self.fixture(PARTIAL_WRITE)
        seen = []
        real = panel.ToolCard.set_progress

        def spy(card, text):
            seen.append(text)
            real(card, text)
        self.patch(panel.ToolCard, "set_progress", spy)
        self.send("write it")
        self.assertTrue(self.idle())
        self.assertIn("writing model.py: 3 lines", seen)
        self.assertIn("DONE", seen)
        card = self.cards("Designing")[-1]
        self.assertTrue(card.progress.isHidden(), "live line left behind")


# ------------------------------------------------------------------ R36
class TestAskInChat(Case):

    def test_r36_ask_in_chat_captures_and_sends(self):
        from acadagent import vision
        shots = []

        def fake_c2p(p, view_name=None, **_k):
            path = p.capture_path()
            with open(path, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            p.add_shot(path, view_name)
            shots.append(path)
            return path
        self.patch(capture, "capture_to_panel", fake_c2p)
        self.assertTrue(vision.ask_in_chat("what is this?",
                                           views=("Isometric", "Front"),
                                           panel=self.p))
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        self.assertEqual(len(set(shots)), 2, "two views, two files")
        for path in shots:
            self.assertEqual(os.path.dirname(path), t["cwd"])
            self.assertIn(path, t["stdin"])
        self.assertTrue(t["stdin"].startswith("what is this?"))


# ------------------------------------------------------------------ S02
class TestPreviewGate(Case):

    def test_s02_content_hash_and_compile_gate(self):
        st = self.turn_state()
        script = os.path.join(st.ws, "model.py")
        self.p._preview_hash = None
        with open(script, "w") as fh:
            fh.write("def broken(:\n")
        self.assertEqual(self.p._preview_files(), [])     # does not compile
        with open(script, "w") as fh:
            fh.write("x = 1\n")
        self.assertEqual(self.p._preview_files(), ["model.py"])
        self.p._applied = build.snapshot(st.ws)
        time.sleep(0.02)
        with open(script, "w") as fh:
            fh.write("x = 1\n")                           # same bytes
        os.utime(script, None)
        self.assertEqual(self.p._preview_files(), [])
        self.assertEqual(build.changed(st.ws, self.p._applied), [],
                         "an identical rewrite must not rebuild at turn end")
        with open(script, "w") as fh:
            fh.write("x = 2\n")
        self.assertEqual(self.p._preview_files(), ["model.py"])


    def test_s02_fix_turn_rebuilds_an_identical_failed_script(self):
        # Review round 2: the pre-turn script counts as "already built" only
        # when it is the last one that built cleanly. A fix turn starts from
        # a FAILED script; rewriting it byte for byte must still be built.
        st = self.turn_state()
        with open(os.path.join(st.ws, "model.py"), "w") as fh:
            fh.write("x = 1\n")
        st.good_hash = None                      # its last build failed
        st.prev = {"doc": "Part", "names": ["Box"], "labels": {},
                   "uid": "uid-t", "preview": True, "undo_count": 3}
        self.patch(claude_cli, "ClaudeRun", _NoRun)
        self.p._busy = False
        self.assertTrue(self.p._send_claude("fix it", state=st))
        self.assertIsNone(self.p._preview_hash)
        self.assertNotIn("preview", st.prev,
                         "an earlier turn's preview must not be merged into")
        os.utime(os.path.join(st.ws, "model.py"), None)
        self.p._applied = {}
        self.assertEqual(self.p._preview_files(), ["model.py"])
        # ... while a script that DID build cleanly is skipped.
        st.good_hash = self.p._script_hash(st.ws)
        self.p._busy = False
        self.assertTrue(self.p._send_claude("again", state=st))
        self.p._applied = {}
        self.assertEqual(self.p._preview_files(), [])


class _NoRun(object):
    """A ClaudeRun that never starts a process."""

    @classmethod
    def shutdown_all(cls, *a, **k):
        return True

    def __init__(self, *a, **k):
        from PySide6 import QtCore

        class _Sig(object):
            def connect(self, *a):
                pass
        for n in ("started_session", "text", "tool", "delta", "progress",
                  "finished_ok", "failed"):
            setattr(self, n, _Sig())
        self.dropped = []
        self._qt = QtCore

    def start(self):
        pass

    def isRunning(self):
        return False

    def flags(self):
        return None


# ------------------------------------------------------------- R77 / S04
class TestDocPill(Case):

    def test_r77_counts_modules_and_pluralises(self):
        objs = [_Obj("Board", "Mesh::Feature", shape=False),
                _Obj("Button", "Mesh::Feature", shape=False),
                _Obj("Speaker", "Mesh::Feature", shape=False),
                _Obj("Case_Top"), _Obj("Case_Bottom"),
                _Obj("Sketch", "App::FeaturePython", shape=False)]
        self.fc.add(_Doc("Clock", "uid-c", objs))
        self.p.refresh_doc_pill()
        self.assertEqual(self.p.doc_meta.text(), "5 objects")
        self.fc.add(_Doc("One", "uid-1", [_Obj("Box")]))
        self.p.refresh_doc_pill()
        self.assertEqual(self.p.doc_meta.text(), "1 object")

    def test_s04_pill_only_recounts_on_change(self):
        class CountingDoc(_Doc):
            iterations = 0

            @property
            def Objects(self):
                CountingDoc.iterations += 1
                return self._objs

            @Objects.setter
            def Objects(self, v):
                self._objs = v
        d = CountingDoc("Big", "uid-big", [_Obj("B%d" % i)
                                           for i in range(500)])
        self.fc.add(d)
        self.p.refresh_doc_pill()
        n0, u0 = CountingDoc.iterations, self.p.stats["pill_updates"]
        t0 = time.perf_counter()
        for _ in range(75):                 # one minute of 800 ms polls
            self.p.refresh_doc_pill()
        dt = (time.perf_counter() - t0) / 75 * 1e6
        self.assertEqual(self.p.stats["pill_updates"], u0)
        # One cheap len(doc.Objects) per poll, no per-object scan.
        self.assertEqual(CountingDoc.iterations - n0, 75)
        d.Objects = d._objs + [_Obj("New")]
        self.p.refresh_doc_pill()
        self.assertEqual(self.p.doc_meta.text(), "501 objects")
        print("\n  [S04] unchanged 500-object doc: %.1f us per poll, "
              "0 recounts in 75 polls" % dt)


# ------------------------------------------------------- R53 / R54 / R56
class TestEmptyStates(Case):

    def test_r53_logo_marks_repaint_on_restyle(self):
        w = self.p._welcome("nodoc")
        self.p._add(w)
        marks = self.p.findChildren(QtWidgets.QLabel, "LogoMark")
        self.assertTrue(marks)
        seen = []

        def fake_logo(h, m=None):
            pm = QtGui.QPixmap(h + 3, h + 3)
            seen.append(h)
            return pm
        self.patch(panel.style, "logo_pixmap", fake_logo)
        self.p.restyle()
        for mark in marks:
            h = int(mark.property("logo_h"))
            self.assertEqual(mark.pixmap().width(), h + 3)
        self.assertIn(28, seen)

    def test_r54_crane_notice_goes_when_the_crane_opens(self):
        n = self.p.show_notice("Sample crane not available",
                               "Not in this installation.")
        self.assertFalse(n.isHidden())
        self.fc.add(_Doc("SampleCrane", "uid-crane"))
        self.p.refresh_doc_pill()
        self.assertTrue(n.isHidden())
        self.assertNotIn("Sample crane not available", self.titles())

    def test_r56_reference_button_only_with_the_crane(self):
        # viewport imports FreeCADGui; a stand-in with only crane_parts.
        import acadagent
        viewport = types.ModuleType("acadagent.viewport")
        viewport.crane_parts = lambda: []
        saved = sys.modules.get("acadagent.viewport")
        sys.modules["acadagent.viewport"] = viewport
        self.addCleanup(lambda: sys.modules.__setitem__(
            "acadagent.viewport", saved) if saved else sys.modules.pop(
                "acadagent.viewport", None))
        if hasattr(acadagent, "viewport"):
            self.patch(acadagent, "viewport", viewport)

        def labels(w):
            return [b.text() for b in w.findChildren(QtWidgets.QPushButton)]
        self.patch(viewport, "crane_parts", lambda: [])
        self.p._crane_ok = None
        self.assertNotIn("Sample crane",
                         labels(self.p._welcome("nodoc")))
        self.patch(viewport, "crane_parts", lambda: ["/x/boom.brep"])
        self.p._crane_ok = None
        # R89: one name for one action, the start card's.
        self.assertIn("Sample crane", labels(self.p._welcome("nodoc")))
        self.assertNotIn("Open reference model",
                         labels(self.p._welcome("nodoc")))


# ------------------------------------------------------------------ S07
class TestSessionContinuity(Case):

    def test_s07_restart_resumes_the_documents_chat(self):
        self.fc.add(_Doc("Bracket", "uid-s07"))
        os.environ["FAKE_SID"] = "sid-s07"
        self.send("a bracket")
        self.assertTrue(self.idle())
        ws = self.turns()[-1]["cwd"]
        rec = panel.load_sessions()["uid-s07"]
        self.assertEqual((rec["ws"], rec["sid"]), (ws, "sid-s07"))
        self.assertEqual(stat.S_IMODE(os.stat(panel.sessions_path())
                                      .st_mode), 0o600)
        # "Restart": a brand-new panel, same document.
        p2 = panel.AgentPanel()
        try:
            wait_until(lambda: p2._backend_state != "checking", 10)
            p2.input.setPlainText("make it 10 mm taller")
            p2._on_send()
            self.assertTrue(wait_until(lambda: not p2._busy, 15))
            t = self.turns()[-1]
            self.assertEqual(t["cwd"], ws)
            self.assertEqual(t["argv"][t["argv"].index("--resume") + 1],
                             "sid-s07")
        finally:
            claude_cli.ClaudeRun.shutdown_all(3000)
            p2.deleteLater()

    def test_s07_new_chat_forgets_the_stored_session(self):
        self.fc.add(_Doc("Bracket", "uid-s07b"))
        self.send("a bracket")
        self.assertTrue(self.idle())
        self.assertIn("uid-s07b", panel.load_sessions())
        self.p.new_chat()
        self.assertNotIn("uid-s07b", panel.load_sessions())


# ------------------------------------------------------------------ R24
class TestDevEngines(tcr.Base):

    def dialog(self):
        return cfgmod.SettingsDialog()

    def test_r24_public_build_offers_one_engine(self):
        os.environ.pop("ATECH_DEV_ENGINES", None)
        d = self.dialog()
        try:
            self.assertEqual(d.engine.count(), 1)
            self.assertEqual(d.engine.itemData(0), engine.CLAUDE)
            self.assertFalse(d._form.isRowVisible(d.backend))
            self.assertFalse(d._form.isRowVisible(d.key))
        finally:
            d.deleteLater()

    def test_r24_dev_flag_offers_all_three(self):
        os.environ["ATECH_DEV_ENGINES"] = "1"
        try:
            d = self.dialog()
            self.assertEqual(d.engine.count(), 3)
            self.assertTrue(d._form.isRowVisible(d.backend))
            d.deleteLater()
        finally:
            os.environ.pop("ATECH_DEV_ENGINES", None)

    def test_r24_key_only_over_https_or_loopback(self):
        ok = cfgmod.key_url_ok
        self.assertTrue(ok("http://127.0.0.1:4096")[0])
        self.assertTrue(ok("http://localhost:4096")[0])
        self.assertTrue(ok("https://agent.example.com")[0])
        self.assertFalse(ok("http://agent.example.com:4096")[0])
        self.assertFalse(ok("http://10.0.0.5:4096")[0])
        self.assertFalse(ok("ftp://127.0.0.1")[0])
        good, msg = cfgmod.set_api_key("http://evil.example:4096",
                                       "anthropic", "sk-ant-x")
        self.assertFalse(good)
        self.assertIn("not sent", msg)

    def test_r24_stop_is_not_offline(self):
        p = panel.AgentPanel()
        try:
            p._stopped = True
            p._busy = True
            p._on_chat_failed("URLError: connection reset")
            self.assertEqual(p._backend_state, "idle")
        finally:
            p.deleteLater()


# ------------------------------------------------------------ R36 / R35
class TestVisionAndCaptures(unittest.TestCase):

    def test_r36_no_dev_wording(self):
        with open(os.path.join(tcr.ADDON, "acadagent", "vision.py"),
                  encoding="utf-8") as fh:
            self.assertNotIn("bin/cad", fh.read())

    def test_r36_ask_about_view_runs_in_the_chat_workspace(self):
        from acadagent import vision
        ws = tempfile.mkdtemp(prefix="ws-", dir=tcr._TMP)
        fake_panel = types.SimpleNamespace(
            capture_path=lambda: os.path.join(ws, "view.png"))
        saved = (vision._chat_panel, capture.capture, claude_cli.available)

        def fake_capture(path=None, **_k):
            with open(path, "wb") as fh:
                fh.write(b"\x89PNG\r\n\x1a\n")
            return path
        vision._chat_panel = lambda: fake_panel
        capture.capture = fake_capture
        claude_cli.available = lambda: True
        try:
            run = vision.ask_about_view("what is this?", cwd="/home/nobody")
            self.assertEqual(run._cwd, ws)
            self.assertEqual(run._agent["ws"], ws)
            self.assertEqual(run._agent["allowed"], ())
            self.assertTrue(all(os.path.dirname(p) == ws
                                for p in run._images))
            claude_cli.ClaudeRun._LIVE.discard(run)
        finally:
            vision._chat_panel, capture.capture, claude_cli.available = saved

    def test_r35_session_capture_dir_is_private_and_removed(self):
        d = capture.session_dir()
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        self.assertIs(capture.session_dir(), d)
        capture.cleanup_session_dir()
        self.assertFalse(os.path.exists(d))


# ------------------------------------------------- round 3 (WS-CHAT)
class _SlowJob(object):
    """A sandbox job that finishes after `secs` (build.start's child)."""

    def __init__(self, secs, res):
        self.t_end = time.monotonic() + secs
        self.res = res
        self.cancelled = False
        self.polls = 0

    def poll(self):
        self.polls += 1
        if self.cancelled or time.monotonic() < self.t_end:
            return None
        return self.res

    def cancel(self):
        self.cancelled = True


class _Untouched(object):
    def untouched(self, source, error):
        return build.Result(False, source, error=error)


def _slow(secs, res, jobs=None):
    def start(*a, **k):
        job = _SlowJob(secs, res)
        if jobs is not None:
            jobs.append((job, k))
        return build.PendingBuild(finish=lambda r: r, job=job,
                                  build=_Untouched(), source="model.py")
    return start


class Round3(Case):

    def setUp(self):
        super().setUp()
        self.atech_calls = []
        self.patch(build, "atech_check", self._fake_atech)
        self.verdicts = {}

    def _fake_atech(self, res):
        self.atech_calls.append(res)
        res.atech_verdicts = dict(self.verdicts)
        return res.atech_verdicts

    def viewport(self):
        """A stand-in acadagent.viewport that records what the panel asks."""
        import acadagent
        vp = types.ModuleType("acadagent.viewport")
        vp.calls = []
        vp.set_mesh_quality = lambda objs, final=False, gui=None: \
            vp.calls.append(("mesh", [o.Name for o in objs], final))
        vp.frame_if_needed = lambda objs, first=False, doc=None: \
            vp.calls.append(("frame", [o.Name for o in objs], first,
                             getattr(doc, "Name", None)))
        vp.axonometric = lambda: vp.calls.append(("axonometric",))
        vp.fit_all = lambda *a, **k: vp.calls.append(("fit_all",))
        vp.crane_parts = lambda: []
        saved = sys.modules.get("acadagent.viewport")
        sys.modules["acadagent.viewport"] = vp
        self.addCleanup(lambda: sys.modules.__setitem__(
            "acadagent.viewport", saved) if saved else sys.modules.pop(
                "acadagent.viewport", None))
        had = hasattr(acadagent, "viewport")
        old = getattr(acadagent, "viewport", None)
        acadagent.viewport = vp
        self.addCleanup(lambda: setattr(acadagent, "viewport", old) if had
                        else delattr(acadagent, "viewport"))
        return vp

    def script(self, st, text="x = 1\n"):
        with open(os.path.join(st.ws, "model.py"), "w") as fh:
            fh.write(text)

    def box_doc(self, key="uid-t"):
        return self.fc.add(_Doc("Part", key, [_Obj("Box")]))


class TestAsyncBuild(Round3):
    """R93: build.start() + PendingBuild.poll() from a QTimer."""

    def test_r93_gui_never_blocks_while_the_build_runs(self):
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        self.patch(build, "start", _slow(0.6, _ok_result()))
        gaps, last = [], [time.monotonic()]

        def tick():
            now = time.monotonic()
            gaps.append(now - last[0])
            last[0] = now
        t = panel.QtCore.QTimer()
        t.setInterval(10)
        t.timeout.connect(tick)
        t.start()
        t0 = time.monotonic()
        self.p._run_build(["model.py"], preview=True)
        returned = time.monotonic() - t0
        self.assertIsNotNone(self.p._pending, "the build is in flight")
        self.assertEqual(self.cards("Building the model")[0].status.text(),
                         "building")
        self.assertTrue(wait_until(lambda: self.p._pending is None, 5))
        t.stop()
        self.assertLess(returned, 0.05, "_run_build waited on the build")
        self.assertLess(max(gaps), 0.1, "event loop stalled %.3fs" % max(gaps))
        self.assertEqual(self.cards("Building the model")[0].status.text(),
                         "1 built")
        self.assertEqual(st.prev["doc"], "Part")
        print("\n  [R93] _run_build returned in %.1f ms; 0.6 s build; "
              "max event-loop gap %.1f ms over %d ticks"
              % (returned * 1000, max(gaps) * 1000, len(gaps)))

    def test_r93_turn_end_waits_for_the_preview_in_flight(self):
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        jobs = []
        self.patch(build, "start", _slow(0.3, _ok_result(), jobs))
        self.p._run_build(["model.py"], preview=True)
        self.p._applied = build.snapshot(st.ws)
        self.p._on_claude_done("Built a box.", {})
        self.assertTrue(self.p._busy, "turn ended before its build was in")
        self.assertNotIn("Built a box.", self.bubbles())
        self.assertTrue(self.idle(5))
        self.assertIn("Built a box.", self.bubbles())
        # The final script is the one the preview built: not built twice.
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0][1].get("preview"), True)

    def test_r93_preview_during_a_build_is_retried_after_it(self):
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        jobs = []
        self.patch(build, "start", _slow(0.2, _ok_result(), jobs))
        self.p._watch_workspace()
        self.p._preview_hash = None
        self.p._on_ws_changed()
        self.assertEqual(len(jobs), 1)
        self.script(st, "x = 2\n")
        self.p._on_ws_changed()             # while the first one runs
        self.assertEqual(len(jobs), 1, "two builds at once")
        self.assertTrue(wait_until(lambda: len(jobs) == 2, 5))
        self.assertTrue(wait_until(lambda: self.p._pending is None, 5))

    def test_r93_stop_cancels_the_build(self):
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        jobs = []
        self.patch(build, "start", _slow(30, _ok_result(), jobs))
        self.p._run_build(["model.py"], preview=True)
        self.p._on_stop()
        self.assertTrue(jobs[0][0].cancelled)
        self.assertIsNone(self.p._pending)
        self.assertIsNone(st.prev, "a cancelled build changed the chat")
        self.assertEqual(self.cards("Building the model")[0].status.text(),
                         "cancelled")

    def test_r112_quit_cancels_the_build_in_flight(self):
        # R93 reviewer fix: AgentPanel.__init__ connects aboutToQuit to
        # _cancel_build, so quitting mid-build kills the sandbox child
        # instead of leaving it running to its timeout. Emit the real
        # signal (what QApplication.quit() emits) and measure the cancel on
        # the REAL PendingBuild, wrapped only to count the call.
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        jobs, cancels = [], []
        self.patch(build, "start", _slow(30, _ok_result(), jobs))
        real_cancel = build.PendingBuild.cancel

        def counted(pb):
            cancels.append(pb)
            return real_cancel(pb)
        self.patch(build.PendingBuild, "cancel", counted)
        self.p._run_build(["model.py"], preview=True)
        pb = self.p._pending[0]
        self.assertIsInstance(pb, build.PendingBuild)
        self.assertFalse(jobs[0][0].cancelled)
        QtWidgets.QApplication.instance().aboutToQuit.emit()
        self.assertIn(pb, cancels, "aboutToQuit did not reach "
                                   "PendingBuild.cancel()")
        self.assertTrue(jobs[0][0].cancelled, "the sandbox child was left "
                                              "running on quit")
        self.assertIsNone(self.p._pending)
        self.assertIsNone(st.prev, "a cancelled build changed the chat")
        self.assertEqual(self.cards("Building the model")[0].status.text(),
                         "cancelled")

    def test_r93_document_closed_while_the_final_build_runs(self):
        # build.sandboxed() reports a closed document as a failed build;
        # that must end the turn (R81), never send the agent a fix turn.
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        closed = build.Result(False, "model.py", error=(
            "the document was closed while the build ran; nothing was "
            "built"), doc="", uid="")
        self.patch(build, "start", _slow(0.2, closed))
        sent = []
        self.patch(self.p, "_send_fix", sent.append)
        self.p._on_claude_done("Built a box.", {})
        self.assertTrue(self.p._busy)
        self.fc.close(self.fc.docs["Part"])
        self.assertTrue(wait_until(lambda: self.p._pending is None, 5))
        self.assertEqual(sent, [], "a closed document became a fix turn")
        self.assertIn("The document was closed", self.titles())
        self.assertFalse(self.p._busy)


class TestViewAndAtechCheck(Round3):
    """R94: frame_if_needed, set_mesh_quality, atech_check once."""

    def test_r94_preview_coarse_final_fine_framed_once(self):
        vp = self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        self.patch(build, "start", _now(_ok_result()))
        self.p._run_build(["model.py"], preview=True)
        self.script(st, "x = 2\n")
        self.p._run_build(["model.py"], preview=True)
        self.p._run_build(["model.py"])                 # the final build
        wait_until(lambda: len([c for c in vp.calls
                                if c[0] == "frame"]) == 3, 2)
        mesh = [c for c in vp.calls if c[0] == "mesh"]
        frame = [c for c in vp.calls if c[0] == "frame"]
        self.assertEqual([m[2] for m in mesh], [False, False, True])
        self.assertEqual([f[2] for f in frame], [True, False, False])
        self.assertEqual(frame[0][1], ["Box"])
        self.assertEqual(frame[0][3], "Part")
        self.assertNotIn(("axonometric",), vp.calls)
        self.assertNotIn(("fit_all",), vp.calls)
        self.assertEqual(len(self.atech_calls), 1, "check only after final")
        self.assertFalse(self.atech_calls[0].preview)

    def test_r94_atech_fail_goes_back_to_the_agent(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        self.verdicts = {"Button": {"seated": "FAIL", "clearance": "PASS"}}
        self.patch(build, "start", _now(_ok_result()))
        sent = []
        self.patch(self.p, "_send_fix", sent.append)
        self.p._run_build(["model.py"])
        self.assertEqual(len(sent), 1)
        self.assertIn("Atech Button: seated FAIL", sent[0])
        self.assertEqual(self.cards("Building the model")[0].status.text(),
                         "check failed")

    def test_r94_skipped_final_still_gets_the_check_and_fine_mesh(self):
        vp = self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        jobs = []
        self.patch(build, "start", _slow(0.0, _ok_result(), jobs))
        self.p._run_build(["model.py"], preview=True)
        self.assertTrue(wait_until(lambda: self.p._pending is None, 2))
        self.p._applied = build.snapshot(st.ws)
        self.assertEqual(self.atech_calls, [])
        self.p._on_claude_done("Seated a button.", {})
        self.assertTrue(self.idle(3))
        self.assertEqual(len(jobs), 1, "the final build was not skipped")
        self.assertEqual(len(self.atech_calls), 1)
        self.assertEqual([c[2] for c in vp.calls if c[0] == "mesh"],
                         [False, True])
        self.assertIn("Seated a button.", self.bubbles())


class TestBudgetStop(Round3):
    """R101: elapsed time, plain budget notice, Continue, keep the preview,
    ATECH_ASSEMBLY.md only for Atech chats."""

    BUDGET_FIXTURE = [
        {"type": "system", "subtype": "init", "session_id": "s-budget"},
        {"type": "result", "subtype": "error_max_budget_usd",
         "is_error": True, "duration_ms": 895000, "total_cost_usd": 3.01,
         "errors": ["Reached maximum budget ($3)"]}]

    def test_r101_classify(self):
        self.assertEqual(claude_cli.classify_failure(
            "Reached maximum budget ($3)"), claude_cli.BUDGET)
        msg = claude_cli.ClaudeRun._judge(
            {"subtype": "error_max_budget_usd", "is_error": True},
            True, 0, None, 1, "")
        self.assertEqual(claude_cli.classify_failure(msg[1]),
                         claude_cli.BUDGET)

    def test_r101_elapsed_time_on_the_designing_card(self):
        self.patch(claude_cli, "ClaudeRun", _NoRun)
        self.box_doc()
        self.assertTrue(self.p._send_claude("a box"))
        card = self.cards("Designing")[-1]
        self.assertEqual(card.status.text(), "working 0s")
        self.p._turn_t0 -= 65
        self.p._on_tick()
        self.assertEqual(card.status.text(), "working 1m 05s")
        self.assertIn("$3 limit", card.status.toolTip())
        self.p._on_stop()

    def test_r101_budget_stop_end_to_end(self):
        src = os.path.join(self.tmp, "ATECH_ASSEMBLY.md")
        with open(src, "w") as fh:
            fh.write("# Atech assembly\n")
        self.patch(build, "assembly_doc", lambda: src)
        self.box_doc()
        self.fixture(self.BUDGET_FIXTURE)
        self.send("a phone stand")
        self.assertTrue(self.idle())
        t = self.turns()[-1]
        self.assertFalse(os.path.exists(os.path.join(
            t["cwd"], "ATECH_ASSEMBLY.md")), "copied into a plain chat")
        self.assertNotIn(src, t["sp"])
        self.assertIn("Stopped at the $3 limit", self.titles())
        n = [w for w in self.notices() if w.findChild(
            QtWidgets.QLabel, "NoticeTitle").text() ==
            "Stopped at the $3 limit"][0]
        body = n.findChild(QtWidgets.QLabel, "NoticeBody").text()
        self.assertIn("Stopped at the $3 limit for one message — Settings > "
                      "Budget per reply", body)
        self.assertNotIn("Something went wrong", body)
        self.assertEqual([b.text() for b in n.buttons],
                         ["Continue", "Settings…"])
        self.assertEqual(self.p.input.toPlainText(), "",
                         "the message went; Continue picks it up")
        # Continue: the same chat and Claude session, a new turn.
        n.buttons[0].click()
        self.assertTrue(self.idle())
        t2 = self.turns()[-1]
        self.assertEqual(t2["cwd"], t["cwd"])
        self.assertEqual(t2["argv"][t2["argv"].index("--resume") + 1],
                         "s-budget")
        self.assertTrue(t2["stdin"].startswith("Continue where you stopped"))
        # An Atech request in a new chat does get the read-only copy.
        self.p.new_chat()
        self.send("seat an Atech speaker on ports 9 and 10")
        self.assertTrue(self.idle())
        self.assertTrue(os.path.isfile(os.path.join(
            self.turns()[-1]["cwd"], "ATECH_ASSEMBLY.md")))

    def test_r101_last_preview_is_kept_and_newer_script_built(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        calls = []

        def start(*a, **k):
            calls.append(k.get("preview"))
            return build.PendingBuild(_ok_result())
        self.patch(build, "start", start)
        self.p._run_build(["model.py"], preview=True)     # built mid-turn
        self.p._applied = build.snapshot(st.ws)
        good = dict(st.prev)
        # The agent wrote a newer script, then the budget ran out before
        # the debounce built it.
        time.sleep(0.02)
        self.script(st, "x = 3\n")
        self.p._turn_budget = 3.0
        self.p._card = self.p._add(panel.ToolCard("Designing", "Claude Code"))
        self.p._on_claude_failed("Reached maximum budget ($3)")
        self.assertEqual(calls, [True, True], "newer script not kept")
        self.assertEqual(st.prev["doc"], good["doc"])
        self.assertIn("Stopped at the $3 limit", self.titles())
        body = [w for w in self.notices()][-1].findChild(
            QtWidgets.QLabel, "NoticeBody").text()
        self.assertIn("The last preview that built stays in the document",
                      body)
        self.assertEqual(self.cards("Designing")[-1].status.text(),
                         "budget limit")

    def test_r101_newer_script_built_after_the_preview_in_flight(self):
        # The budget stop lands while a preview builds and the agent has
        # already written a newer script: that one is built after it.
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        jobs = []
        self.patch(build, "start", _slow(0.2, _ok_result(), jobs))
        self.p._preview_hash = None
        self.p._on_ws_changed()
        self.assertEqual(len(jobs), 1)
        time.sleep(0.02)
        self.script(st, "x = 3\n")
        self.p._turn_budget = 3.0
        self.p._card = self.p._add(panel.ToolCard("Designing", "Claude Code"))
        self.p._on_claude_failed("Reached maximum budget ($3)")
        self.assertTrue(wait_until(lambda: len(jobs) == 2, 5),
                        "the newer script was never built")
        self.assertTrue(jobs[1][1].get("preview"))
        self.assertTrue(wait_until(lambda: self.p._pending is None, 5))


class TestTrustReview(Round3):
    """R98: the review action for a design script from elsewhere, and a fix
    turn that changes nothing is not a success."""

    def test_r98_untrusted_script_review_then_trust(self):
        o = _Obj("Gear")
        o.AtechAgentBuilt = True
        o.AtechAgentScript = "import os\nos.system('echo pwned')\n"
        trusted = []

        def trust(doc, ws=None):
            trusted.append((doc.Name, ws))
            with open(os.path.join(ws, "model.py"), "w") as fh:
                fh.write(o.AtechAgentScript)
            return 1
        self.patch(build, "trust_script", trust)
        doc = self.fc.add(_Doc("Shared", "uid-shared", [o]))
        self.p.refresh_doc_pill(force=True)
        st = self.p._docs["uid-shared"]
        self.assertTrue(st.prev["untrusted_script"])
        self.assertFalse(os.path.exists(os.path.join(st.ws, "model.py")),
                         "an untrusted script reached model.py")
        title = "This file contains a design script from elsewhere"
        self.assertIn(title, self.titles())
        # Offered once, not on every poll.
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.titles().count(title), 1)
        n = [w for w in self.notices() if w.findChild(
            QtWidgets.QLabel, "NoticeTitle").text() == title][0]
        self.assertEqual([b.text() for b in n.buttons],
                         ["Review script…", "Not now"])
        n.buttons[0].click()
        dlg = self.p._review_dialog
        self.assertIn("os.system('echo pwned')", dlg.text.toPlainText())
        self.assertTrue(dlg.text.isReadOnly())
        self.assertEqual(trusted, [], "trusted before the user accepted")
        self.patch(build, "adopt", lambda d, ws: {
            "doc": d.Name, "uid": d.Uid, "names": ["Gear"],
            "labels": {"Gear": "Gear"}, "script_adopted": True,
            "untrusted_script": False})
        dlg.accept()
        self.assertEqual(trusted, [("Shared", st.ws)])
        self.assertTrue(st.prev["script_adopted"])
        self.assertIn("Design script accepted", self.titles())
        self.assertFalse(n.buttons[0].isEnabled())
        del doc

    def test_r98_rejected_review_trusts_nothing(self):
        o = _Obj("Gear")
        o.AtechAgentBuilt = True
        o.AtechAgentScript = "x = 1\n"
        trusted = []
        self.patch(build, "trust_script", lambda *a, **k: trusted.append(a))
        self.fc.add(_Doc("Shared", "uid-shared2", [o]))
        self.p.refresh_doc_pill(force=True)
        st = self.p._docs["uid-shared2"]
        dlg = self.p._review_script(st)
        dlg.reject()
        self.assertEqual(trusted, [])

    def test_r75_fix_turn_without_a_change_is_not_a_success(self):
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        self.patch(build, "start", _now(build.Result(
            False, "model.py", error=TB_5K)))
        sent = []
        self.patch(self.p, "_send_fix", sent.append)
        self.p._on_claude_done("Built a pinion.", {})      # fails
        self.assertEqual(len(sent), 1)
        self.assertIsNotNone(st.failed)
        # The fix turn: the agent answers but leaves model.py as it was.
        self.p._busy = True
        self.p._fix_turn = True
        self.p._turn_failed = False
        self.p._build_card = None
        self.p._build_sig = None
        self.p._applied = build.snapshot(st.ws)
        self.p._before = dict(self.p._applied)
        self.p._on_claude_done("Fixed: the pinion now builds.", {})
        self.assertNotIn("Fixed: the pinion now builds.", self.bubbles())
        self.assertEqual(len(sent), 2, "the failure was not sent back")
        self.assertEqual(sent[1], sent[0])
        card = self.cards("Building the model")[-1]
        self.assertEqual(card.status.text(), "unchanged: still fails")
        self.assertIn("Agent: Fixed: the pinion now builds.", card.body.text())

    def test_r75_user_question_after_a_failure_is_answered(self):
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        st.failed = (self.p._script_hash(st.ws), "fix me")
        self.p._fix_turn = False            # the user asked something
        self.p._applied = build.snapshot(st.ws)
        self.p._before = dict(self.p._applied)
        sent = []
        self.patch(self.p, "_send_fix", sent.append)
        self.p._on_claude_done("The volume is 1000 mm3.", {})
        self.assertIn("The volume is 1000 mm3.", self.bubbles())
        self.assertEqual(sent, [])


class TestNarrowChat(Round3):
    """R87: at 900x600 the chat sidebar is at its minimum width."""

    def test_r87_try_asking_cards_wrap_not_cut(self):
        self.p.resize(320, 560)
        self.p.show()
        self.p.new_chat()
        panel.QtWidgets.QApplication.processEvents()
        w = self.p._empty
        self.assertIsNotNone(w)
        # Height-for-width settles over a few layout passes.
        wait_until(lambda: all(
            r.label.height() >= r.label.heightForWidth(r.label.width())
            for r in w.rows), 2)
        wrapped = 0
        for r in w.rows:
            self.assertIsInstance(r, panel.SuggestButton)
            lab = r.label
            self.assertTrue(lab.wordWrap())
            self.assertEqual(lab.text(), r.text())      # never elided
            need = lab.heightForWidth(lab.width())
            self.assertGreaterEqual(lab.height(), need, r.text())
            fm = lab.fontMetrics()
            if fm.horizontalAdvance(r.text()) > lab.width():
                wrapped += 1
                self.assertGreater(lab.height(), fm.lineSpacing() * 1.5)
            self.assertLessEqual(r.geometry().right(), w.width())
        long_w = panel.SuggestButton("A round knob, 30 mm across, for a 6 mm "
                                     "D-shaft with a grip ring and a pointer")
        self.assertGreater(long_w.heightForWidth(200),
                           long_w.heightForWidth(1000))
        print("\n  [R87] %d of %d cards wrap at width %d; label heights %s"
              % (wrapped, len(w.rows), w.width(),
                 [r.label.height() for r in w.rows]))
        self.p.hide()

    def test_r87_placeholder_is_never_clipped(self):
        e = self.p.input
        self.assertGreaterEqual(e.placeholder_lines(120), 2)
        self.p.resize(320, 560)
        self.p.show()
        panel.QtWidgets.QApplication.processEvents()
        lines = e.placeholder_lines()
        fm = e.fontMetrics()
        self.assertGreaterEqual(e.height(), lines * fm.lineSpacing())
        empty_h, vw = e.height(), e.viewport().width()
        # Once text is typed the box follows the text again.
        e.setPlainText("x")
        self.assertEqual(e.height(), fm.lineSpacing() + 8)
        print("\n  [R87] placeholder: %d line(s) at %d px; empty box %d px "
              "(one line of text: %d px)" % (lines, vw, empty_h, e.height()))
        self.p.hide()


def setUpModule():
    """Run after test_chat_robustness in one process, its tearDownModule
    has already removed the private tree and put the real HOME back. Make
    both private again, so nothing here touches the real user folders."""
    os.makedirs(os.path.join(tcr._TMP, "home"), exist_ok=True)
    os.environ["HOME"] = os.path.join(tcr._TMP, "home")
    capture.cleanup_session_dir()


def tearDownModule():
    tcr.tearDownModule()


if __name__ == "__main__":
    unittest.main()
