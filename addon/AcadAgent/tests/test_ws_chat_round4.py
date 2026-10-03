"""WS-CHAT round 4, headless against the REAL AgentPanel (same fakes as
test_ws_chat_panel): R110, R123, R94 (module face, D50), R87 (900x600),
R105, R113, R124, R125.

RUN (the interpreter that ships):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \\
        -m unittest addon/AcadAgent/tests/test_ws_chat_round4.py -v
"""
import os
import re
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import test_chat_robustness as tcr  # noqa: E402  (sets HOME, Qt, settings)
import test_ws_chat_panel as twp  # noqa: E402

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from acadagent import backend, build, capture, panel, shell  # noqa: E402

wait_until = tcr.wait_until
_Doc, _Obj = twp._Doc, twp._Obj

ATECH_SECTION = "ATECH MODULES AND BOARDS (this is the complete reference)"


# ------------------------------------------------------------------ R110
class TestR110AtechPrompt(twp.Round3):

    def setUp(self):
        super().setUp()
        # The library probe needs the real meshes and FreeCAD; the prompt
        # choice is what is under test, so the library counts as present.
        self.patch(build, "library_available", lambda *a, **k: True)

    def test_r110_atech_request_in_an_empty_document(self):
        doc = self.fc.add(_Doc("Unnamed", "uid-empty"))
        ws = build.new_workspace()
        # Before the fix: system_prompt(ws) alone reads only the document
        # and model.py - an empty document gets the pointer.
        self.assertNotIn(ATECH_SECTION, build.system_prompt(ws))
        sp, _agent = self.p._turn_args(
            ws, text="Seat a button module on port 2 of the Atech board",
            doc=doc)
        self.assertIn(ATECH_SECTION, sp)
        print("\n  [R110] Atech request, empty document: prompt %d chars, "
              "Atech section present" % len(sp))

    def test_r110_both_regexes_count(self):
        # build.mentions_atech knows "button module"; the panel's own regex
        # did not. One verdict now drives the prompt and the copy.
        doc = self.fc.add(_Doc("Unnamed", "uid-empty2"))
        ws = build.new_workspace()
        sp, _a = self.p._turn_args(ws, text="add a speaker module", doc=doc)
        self.assertIn(ATECH_SECTION, sp)

    def test_r110_plain_request_keeps_the_pointer(self):
        doc = self.fc.add(_Doc("Unnamed", "uid-empty3"))
        ws = build.new_workspace()
        sp, _a = self.p._turn_args(ws, text="a 20 mm cube with a 5 mm hole",
                                   doc=doc)
        self.assertNotIn(ATECH_SECTION, sp)
        self.assertIn("not provided: this request does not involve Atech",
                      sp)


# ------------------------------------------------------------------ R123
class TestR123ChildVerdicts(twp.Round3):

    def test_r123_child_verdicts_skip_the_gui_thread_check(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        res = twp._ok_result()
        res.atech_checked = True
        res.atech_verdicts = {"Button": {"seated": "FAIL"}}
        self.patch(build, "start", twp._now(res))
        sent = []
        self.patch(self.p, "_send_fix", sent.append)
        self.p._run_build(["model.py"])
        self.assertEqual(self.atech_calls, [], "atech_check ran on the GUI "
                                               "thread")
        self.assertEqual(len(sent), 1)
        self.assertIn("Atech Button: seated FAIL", sent[0])

    def test_r123_child_checked_nothing_is_still_the_answer(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        res = twp._ok_result()
        res.atech_checked = True            # no module: verdicts {}
        self.patch(build, "start", twp._now(res))
        self.p._run_build(["model.py"])
        self.assertEqual(self.atech_calls, [])
        self.assertEqual(self.cards("Building the model")[0].status.text(),
                         "1 built")

    def test_r123_fallback_when_the_result_carries_none(self):
        self.viewport()
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        self.patch(build, "start", twp._now(twp._ok_result()))
        self.p._run_build(["model.py"])
        self.assertEqual(len(self.atech_calls), 1)

    def test_r123_child_verdicts_contract(self):
        r = build.Result(True, "model.py")
        self.assertIsNone(panel.AgentPanel.child_verdicts(r))
        r.atech_checked = True
        self.assertEqual(panel.AgentPanel.child_verdicts(r), {})
        r2 = build.Result(True, "model.py")
        r2.atech_verdicts = {"Knob": {"seated": "PASS"}}
        self.assertEqual(panel.AgentPanel.child_verdicts(r2),
                         {"Knob": {"seated": "PASS"}})


# ------------------------------------------------------------ R94 / D50
class TestR94ModuleFace(twp.Round3):

    def test_r94_turns_to_the_module_face_once_it_exists(self):
        vp = self.viewport()
        faces = [None, (0.6, 1.0, 0.5), (0.6, 1.0, 0.5)]
        vp.module_face_direction = lambda doc: faces.pop(0)
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        self.patch(build, "start", twp._now(twp._ok_result()))
        # 1: a placeholder, no module yet -> isometric (first build)
        self.p._run_build(["model.py"], preview=True)
        QtWidgets.QApplication.processEvents()
        # 2: board + module land -> turn to the module face, once
        self.script(st, "x = 2\n")
        self.p._run_build(["model.py"], preview=True)
        QtWidgets.QApplication.processEvents()
        # 3: the final build keeps the user's view
        self.p._run_build(["model.py"])
        wait_until(lambda: len([c for c in vp.calls
                                if c[0] == "frame"]) == 3, 2)
        frame = [c[2] for c in vp.calls if c[0] == "frame"]
        self.assertEqual(frame, [True, True, False])
        self.assertTrue(st.faced)


# ------------------------------------------------------------------ R87
class TestR87At900x600(twp.Round3):
    """The chat in a 900x600 window, docked the way shell.py docks it."""

    def test_r87_cards_and_placeholder_at_900x600(self):
        want = shell.sidebar_width_for(900)
        mw = QtWidgets.QMainWindow()
        mw.setCentralWidget(QtWidgets.QWidget())
        dock = QtWidgets.QDockWidget()
        dock.setTitleBarWidget(QtWidgets.QWidget())
        self.p.setMinimumWidth(min(self.p.minimumWidth(), want))  # shell
        dock.setWidget(self.p)
        mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
        mw.resize(900, 600)
        mw.show()
        mw.resizeDocks([dock], [want], QtCore.Qt.Horizontal)
        self.p.new_chat()
        for _ in range(5):
            QtWidgets.QApplication.processEvents()
        w = self.p._empty
        wait_until(lambda: all(
            r.label.height() >= r.label.heightForWidth(r.label.width())
            for r in w.rows), 2)
        out = []
        for r in w.rows:
            lab = r.label
            fm = lab.fontMetrics()
            self.assertEqual(lab.text(), r.text(), "elided")
            self.assertGreaterEqual(lab.height(),
                                    lab.heightForWidth(lab.width()), r.text())
            widest = max(fm.horizontalAdvance(x) for x in r.text().split())
            self.assertLessEqual(widest, lab.width(), "a word wider than "
                                 "the card is cut mid-word")
            self.assertLessEqual(r.mapTo(self.p, QtCore.QPoint(
                r.width(), 0)).x(), self.p.width())
            out.append((lab.width(), lab.height()))
        e = self.p.input
        lines = e.placeholder_lines()
        self.assertGreaterEqual(e.height(), lines * e.fontMetrics()
                                .lineSpacing())
        print("\n  [R87] 900x600: sidebar %d px (want %d), cards (w,h) %s, "
              "placeholder %d line(s) in a %d px box"
              % (self.p.width(), want, out, lines, e.height()))
        mw.hide()
        dock.setWidget(None)
        self.p.setParent(None)
        mw.deleteLater()


# ------------------------------------------------------------------ R113
class TestR113ReviewAgain(twp.Round3):

    def _untrusted(self, name="Shared", uid="uid-sh"):
        o = _Obj("Gear")
        o.AtechAgentBuilt = True
        o.AtechAgentScript = "x = 1\n"
        return self.fc.add(_Doc(name, uid, [o]))

    def test_r113_not_now_leaves_a_way_back(self):
        self.p.show()
        doc = self._untrusted()
        self.p.refresh_doc_pill(force=True)
        st = self.p._docs["uid-sh"]
        title = "This file contains a design script from elsewhere"
        QtWidgets.QApplication.processEvents()     # queued show
        n = [w for w in self.notices() if w.findChild(
            QtWidgets.QLabel, "NoticeTitle").text() == title][0]
        n.buttons[1].click()                            # Not now
        self.assertFalse(n.buttons[0].isEnabled())
        self.assertTrue(self.p.btn_review.isVisible())
        # It fits the 300 px sidebar of a 900x600 window beside "New chat".
        self.p.setMinimumWidth(shell.sidebar_width_for(900))
        self.p.resize(shell.sidebar_width_for(900), 600)
        QtWidgets.QApplication.processEvents()
        for b in (self.p.btn_review, self.p.btn_new):
            right = b.mapTo(self.p, QtCore.QPoint(b.width(), 0)).x()
            self.assertLessEqual(right, self.p.width(), b.text())
            self.assertGreaterEqual(b.width(), b.sizeHint().width() - 1,
                                    b.text())
        print("\n  [R113] context line at %d px: 'Review script' %d px, "
              "'New chat' %d px, document name %d px" % (
                  self.p.width(), self.p.btn_review.width(),
                  self.p.btn_new.width(), self.p.doc_name.width()))
        # A new chat clears the transcript; the way back stays.
        self.p.new_chat()
        self.p.refresh_doc_pill(force=True)
        self.assertTrue(self.p.btn_review.isVisible())
        self.p.btn_review.click()
        dlg = self.p._review_dialog
        self.assertIn("x = 1", dlg.text.toPlainText())
        trusted = []
        self.patch(build, "trust_script",
                   lambda d, ws=None: trusted.append(d.Name) or 1)
        self.patch(build, "adopt", lambda d, ws: {
            "doc": d.Name, "uid": d.Uid, "names": ["Gear"],
            "untrusted_script": False})
        dlg.accept()
        self.assertEqual(trusted, ["Shared"])
        self.assertFalse(self.p.btn_review.isVisible())
        self.assertTrue(self.p._needs_review(st), "the old chat changed")
        self.assertFalse(self.p._needs_review(self.p._docs["uid-sh"]))
        del doc
        self.p.hide()

    def test_r113_hidden_for_other_documents(self):
        self.p.show()
        self._untrusted()
        self.p.refresh_doc_pill(force=True)
        self.assertTrue(self.p.btn_review.isVisible())
        self.fc.add(_Doc("Plain", "uid-plain"))
        self.p.refresh_doc_pill(force=True)
        self.assertFalse(self.p.btn_review.isVisible())
        self.p.hide()


# ------------------------------------------------------------------ R124
class TestR124Tables(twp.Round3):

    TABLE = ("Clearances:\n\n"
             "| Interface | Gap |\n"
             "|---|---:|\n"
             "| Board/module sides to interior walls | 0.5 mm |\n"
             "| Module face to window | 1.0 mm |\n\n"
             "All pass.")

    def test_r124_table_detection(self):
        self.assertTrue(panel.has_md_table(self.TABLE))
        self.assertTrue(panel.has_md_table("a | b\n--- | ---\n1 | 2"))
        self.assertTrue(panel.has_md_table("| a | b |\n| :-- | :-: |\n"))
        self.assertFalse(panel.has_md_table("x | y is a pipe"))
        self.assertFalse(panel.has_md_table("a heading\n---\ntext"))
        self.assertFalse(panel.has_md_table(""))

    def test_r124_agent_table_renders_as_a_table(self):
        b = self.p.say(self.TABLE)
        self.assertEqual(b.label.textFormat(), QtCore.Qt.RichText)
        shown = QtGui.QTextDocument()
        shown.setHtml(b.label.text())
        self.assertEqual(len([f for f in shown.rootFrame().childFrames()
                              if isinstance(f, QtGui.QTextTable)]), 1)
        self.assertNotIn("|---", shown.toPlainText())
        doc = QtGui.QTextDocument()
        doc.setMarkdown(self.TABLE)
        tables = [f for f in doc.rootFrame().childFrames()
                  if isinstance(f, QtGui.QTextTable)]
        self.assertEqual(len(tables), 1)
        self.assertEqual((tables[0].rows(), tables[0].columns()), (3, 2))
        self.assertNotIn("|---", doc.toPlainText())
        # Offscreen render for the record.
        self.p.resize(360, 600)
        self.p.show()
        for _ in range(3):
            QtWidgets.QApplication.processEvents()
        path = os.path.join(os.environ.get("WS_CHAT_SHOTS", tcr._TMP),
                            "r124_table.png")
        b.grab().save(path)
        print("\n  [R124] table bubble %dx%d px -> %s"
              % (b.width(), b.height(), path))
        self.p.hide()

    def test_r124_angle_brackets_stay_literal(self):
        # Qt.MarkdownText parses raw HTML: "<port>" ate the rest of the
        # message, table included (measured "Use the" and nothing else).
        b = self.p.say("Use the <port> field.\n\n" + self.TABLE)
        shown = QtGui.QTextDocument()
        shown.setHtml(b.label.text())
        plain = shown.toPlainText()
        self.assertIn("Use the <port> field.", plain)
        self.assertIn("Module face to window", plain)
        self.assertIn("All pass.", plain)
        self.assertNotIn("font-family", b.label.text().split("<body", 1)[1]
                         .split(">", 1)[0])

    def test_r124_other_text_keeps_its_format(self):
        b = self.p.say("A box, 20 mm | 30 mm.")
        self.assertEqual(b.label.textFormat(), QtCore.Qt.AutoText)
        u = self.p.say(self.TABLE, role="user")
        self.assertNotEqual(u.label.textFormat(), QtCore.Qt.RichText)


# ------------------------------------------------------------------ R125
class TestR125Denials(twp.Round3):

    def test_r125_isolation_warning_stays_on_the_card(self):
        st = self.turn_state(doc=self.box_doc())
        self.script(st)
        self.p._applied = build.snapshot(st.ws)
        self.p._before = dict(self.p._applied)
        self.p._card = panel.ToolCard("Designing", "Claude Code", mono=False)
        self.p._add(self.p._card)
        self.p._chat = types.SimpleNamespace(
            flags=lambda: ["-p"], dropped=["--strict-mcp-config"])
        self.p._on_claude_session("sid")
        self.assertIn("cannot isolate the agent", self.p._card.body.text())
        logged = []
        self.patch(panel, "_log", logged.append)
        self.p._on_claude_done("", {"permission_denials": [
            {"tool_name": "Bash", "tool_input": {
                "command": "cd /tmp/x && sed -n 1,5p a.py"}}]})
        card = self.cards("Designing")[-1]
        self.assertNotIn("not allowed", card.body.text())
        self.assertIn("cannot isolate the agent", card.body.text())
        self.assertTrue(any("refused by the allowlist (1)" in m
                            for m in logged), logged)


# ------------------------------------------------------------------ R105
def _fake_proc(root, rows, procs):
    """A /proc tree: rows = net/tcp lines, procs = {pid: (ppid, cmd, inodes)}."""
    os.makedirs(os.path.join(root, "net"))
    with open(os.path.join(root, "net", "tcp"), "w") as fh:
        fh.write("  sl  local_address rem_address   st tx_queue rx_queue tr "
                 "tm->when retrnsmt   uid  timeout inode\n")
        for r in rows:
            fh.write(r + "\n")
    for pid, (ppid, cmd, inodes) in procs.items():
        d = os.path.join(root, str(pid))
        os.makedirs(os.path.join(d, "fd"))
        with open(os.path.join(d, "stat"), "w") as fh:
            fh.write("%d (%s) S %d 0 0\n" % (pid, cmd.split()[0], ppid))
        with open(os.path.join(d, "cmdline"), "wb") as fh:
            fh.write(cmd.replace(" ", "\0").encode() + b"\0")
        for i, ino in enumerate(inodes):
            os.symlink("socket:[%d]" % ino, os.path.join(d, "fd", str(i + 3)))


def _row(addr, port, uid, inode, st="0A"):
    return ("   0: %s:%04X 00000000:0000 %s 00000000:00000000 00:00000000 "
            "00000000  %d        0 %d 1 0000000000000000 100 0 0 10 0"
            % (addr, port, st, uid, inode))


class TestR105Listener(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="proc-", dir=tcr._TMP)
        self.uid = os.getuid()

    def test_r105_parse_and_classify(self):
        _fake_proc(self.root, [
            _row("0100007F", 4096, self.uid, 555),
            _row("0100007F", 4097, self.uid, 556, st="01"),   # not LISTEN
            _row("0200A8C0", 4096, self.uid, 557)],           # not loopback
            {100: (1, "systemd --user", []),
             200: (100, "opencode serve --port 4096", [555]),
             300: (50, "freecad", []),
             50: (1, "bash AppRun", [])})
        info = backend.listener(4096, proc=self.root)
        self.assertEqual(info["pid"], 200)
        self.assertEqual(info["ppid"], 100)
        self.assertEqual(info["cmd"], "opencode serve --port 4096")
        # The D6 orphan: parent systemd --user, not us.
        self.assertEqual(backend.classify(info, me=300, parent=50,
                                          uid=self.uid, proc=self.root),
                         backend.USER)
        self.assertIn("left running by an earlier session",
                      backend.describe(info))
        # Our child / our AppRun sibling: ours.
        self.assertEqual(backend.classify(info, me=100, parent=1,
                                          uid=self.uid, proc=self.root),
                         backend.OWN)
        self.assertEqual(backend.classify(info, me=300, parent=100,
                                          uid=self.uid, proc=self.root),
                         backend.OWN)
        self.assertEqual(backend.classify(dict(info, uid=self.uid + 1),
                                          me=300, parent=50, uid=self.uid,
                                          proc=self.root),
                         backend.OTHER_USER)
        self.assertIsNone(backend.listener(4097, proc=self.root))

    def _sup(self, kind, info, shake=True, env=None):
        sup = backend.Supervisor()
        saved = (backend.listener, backend.classify, backend.handshake)
        backend.listener = lambda port: info
        backend.classify = lambda i: kind
        backend.handshake = lambda h, p: shake
        old = os.environ.pop("ATECH_AGENT_ADOPT", None)
        if env is not None:
            os.environ["ATECH_AGENT_ADOPT"] = env
        try:
            return sup, sup._adopt()
        finally:
            backend.listener, backend.classify, backend.handshake = saved
            os.environ.pop("ATECH_AGENT_ADOPT", None)
            if old is not None:
                os.environ["ATECH_AGENT_ADOPT"] = old

    def test_r105_adopt_decisions(self):
        info = {"pid": 7, "uid": self.uid, "ppid": 1,
                "cmd": "opencode serve", "parent_cmd": ""}
        sup, r = self._sup(backend.OWN, info)
        self.assertEqual(r, (backend.IDLE, "adopted"))
        self.assertIsNone(sup.foreign)
        sup, r = self._sup(backend.USER, info)
        self.assertEqual(r, (backend.IDLE, "adopted-foreign"))
        self.assertEqual(sup.foreign["pid"], 7)
        sup, r = self._sup(backend.USER, info, env="0")
        self.assertEqual(r, (backend.OFFLINE, "foreign-refused"))
        self.assertFalse(sup.adopted)
        sup, r = self._sup(backend.USER, info, shake=False)
        self.assertEqual(r, (backend.OFFLINE, "port-busy"))
        sup, r = self._sup(backend.OTHER_USER, info)
        self.assertEqual(r, (backend.OFFLINE, "foreign-user"))
        # An adopted foreign backend is never reaped.
        sup, r = self._sup(backend.USER, info)
        self.assertFalse(sup.shutdown())

    def test_r105_live_listener_if_any(self):
        """Measured on this machine: who is on 127.0.0.1:4096 right now."""
        info = backend.listener(4096)
        print("\n  [R105] 127.0.0.1:4096 -> %s, %s" % (
            backend.classify(info) if info else "free",
            backend.describe(info) if info else "-"))


class TestR105Panel(twp.Round3):

    def test_r105_foreign_backend_is_said_once(self):
        info = {"pid": 2580988, "uid": os.getuid(), "ppid": 7849,
                "cmd": "opencode serve --port 4096 --hostname 127.0.0.1",
                "parent_cmd": "/usr/lib/systemd/systemd --user"}
        self.p._note_foreign_backend((backend.USER, info))
        self.p._note_foreign_backend((backend.USER, info))
        self.assertEqual(self.titles().count(backend.FOREIGN_TITLE), 1)
        body = [w for w in self.notices() if w.findChild(
            QtWidgets.QLabel, "NoticeTitle").text() ==
            backend.FOREIGN_TITLE][0].findChild(
                QtWidgets.QLabel, "NoticeBody").text()
        self.assertIn("pid 2580988", body)
        self.assertIn("will not stop it", body)
        self.p._note_foreign_backend((backend.OWN, dict(info, pid=1)))
        self.assertEqual(self.titles().count(backend.FOREIGN_TITLE), 1)

    def test_r105_worker_refuses_other_account_and_adopt_0(self):
        """The panel's own probe (not only Supervisor) refuses a backend of
        another account, and any foreign one under ATECH_AGENT_ADOPT=0."""
        info = {"pid": 9, "uid": os.getuid() + 1, "ppid": 1, "cmd": "x",
                "parent_cmd": ""}
        w = panel.HealthWorker("http://127.0.0.1:4096")
        self.assertTrue(w._refuse((backend.OTHER_USER, info)))
        self.assertEqual(w.refused, backend.OTHER_USER)
        w = panel.HealthWorker("http://127.0.0.1:4096")
        self.assertFalse(w._refuse((backend.USER, info)))
        self.assertFalse(w._refuse((backend.OWN, info)))
        old = os.environ.get("ATECH_AGENT_ADOPT")
        os.environ["ATECH_AGENT_ADOPT"] = "0"
        try:
            self.assertTrue(w._refuse((backend.USER, info)))
            self.assertFalse(panel.HealthWorker("x")._refuse(
                (backend.OWN, info)))
        finally:
            if old is None:
                os.environ.pop("ATECH_AGENT_ADOPT", None)
            else:
                os.environ["ATECH_AGENT_ADOPT"] = old
        # The panel says why, once, and does not call it "in use".
        self.p._health = w
        w.owner = (backend.USER, dict(info, uid=os.getuid()))
        self.p._on_health(False)
        self.p._on_health(False)
        self.assertEqual(self.titles().count(backend.NOTICE_TITLE), 1)
        self.assertEqual(self.titles().count(backend.FOREIGN_TITLE), 0)


def setUpModule():
    os.makedirs(os.path.join(tcr._TMP, "home"), exist_ok=True)
    os.environ["HOME"] = os.path.join(tcr._TMP, "home")
    capture.cleanup_session_dir()


def tearDownModule():
    tcr.tearDownModule()


if __name__ == "__main__":
    unittest.main()
