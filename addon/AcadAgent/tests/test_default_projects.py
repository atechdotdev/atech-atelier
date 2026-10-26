"""The default projects Atech AI CAD comes with (R450-R456), headless.

    R450  branding/make_default_projects.py: each curated example built by
          the production build into <Title>.FCStd with tagged Atech
          hardware, AtechAgentScript, a 512 px thumbnail, a starter chat,
          GuiDocument.xml colours and a fresh AtechProjectId; manifest.json
          with matching sha256s; no build-machine path in any file. The
          build gate's row (default_projects.check_shipped).
    R451  install_defaults: first-run copy, idempotent, a deleted default
          stays deleted, a user-edited file is never overwritten, a newer
          manifest adds only new titles.
    R452  every copy has a fresh project id (the chat's id follows).
    R453  the copy's shipped builds are trusted under its new id.
    R454  new_from_default: a fresh copy ("Toy car 2") opened as a project.
    R455  start-up: projects_store.install() schedules it from a QTimer.
    R456  the old starter projects are gone from the UI: the picker's
          submenu, the Atech menu's "New Project", and Home's example row
          uses default_projects.

Every gate has a sabotage test that must see it fail.

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_default_projects

The generator tests run the bundled freecadcmd (skipped when the app is not
built) with a scratch HOME; nothing touches the user's profile or projects.
"""
import ast
import hashlib
import inspect
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import types
import unittest
import zipfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
for _p in (ADDON, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6 import QtCore, QtWidgets
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
except ImportError:                                    # no Qt here
    QtCore = QtWidgets = None

from acadagent import build, default_projects as dp, projects_store as ps  # noqa: E402

APP_BIN = os.path.join(REPO, "dist", "build-macos-arm64", "Atech Atelier.app",
                       "Contents", "Resources", "bin")
FREECADCMD = os.environ.get("ATECH_FREECADCMD") or os.path.join(APP_BIN, "freecadcmd")
GENERATOR = os.path.join(REPO, "branding", "make_default_projects.py")
EXAMPLES = os.path.join(ADDON, "acadagent", "agent_kit", "examples")
VERIFY = os.path.join(REPO, "branding", "verify_tree.py")

DOC_XML = """<?xml version='1.0' encoding='utf-8'?>
<Document SchemaVersion="4" ProgramVersion="1.1" FileVersion="1">
    <Properties Count="3" TransientCount="0">
        <Property name="AtechProjectFile" type="App::PropertyString" group="Atech" status="1">
            <String value=""/>
        </Property>
        <Property name="AtechProjectId" type="App::PropertyString" group="Atech" status="1">
            <String value="%(id)s"/>
        </Property>
        <Property name="Uid" type="App::PropertyUUID" status="1">
            <Uuid value="%(id)s"/>
        </Property>
    </Properties>
    <Objects Count="1">
        <Object type="Part::Feature" name="Body"/>
    </Objects>
    <ObjectData Count="1">
        <Object name="Body">
            <Properties Count="1">
                <Property name="AtechRole" type="App::PropertyString">
                    <String value="board"/>
                </Property>
            </Properties>
        </Object>
    </ObjectData>
</Document>
"""


# ---------------------------------------------------------------- helpers
def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def make_shipped(folder, titles, version=1, trust=True):
    """A shipped folder of synthetic project files + manifest.json."""
    os.makedirs(folder, exist_ok=True)
    rows = []
    for i, t in enumerate(titles):
        pid = "ship-%02d-0000-0000-0000-000000000000" % i
        path = os.path.join(folder, t + ".FCStd")
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("Document.xml", DOC_XML % {"id": pid})
            zf.writestr("thumbnails/Thumbnail.png", b"\x89PNG fake")
            zf.writestr(ps.CHAT_JSON, json.dumps({
                "v": 1, "id": pid, "transcript": {"entries": [
                    {"kind": "bubble", "role": "agent", "text": t}]}}))
        rows.append({"title": t, "file": os.path.basename(path), "id": pid,
                     "example": t.lower().replace(" ", "_"),
                     "summary": "A %s." % t.lower(), "sha256": _sha(path),
                     "trust": {"b%d" % i: {"sha": "s%d" % i, "n": 1}} if trust else {}})
    with open(os.path.join(folder, dp.MANIFEST), "w") as fh:
        json.dump({"version": version, "projects": rows}, fh)
    return rows


def ids_of(paths):
    return [ps.read_file_ids(p) for p in paths]


def fresh_id_problems(paths, shipped_ids):
    """[problem] when two copies share an id, a copy kept a shipped id, the
    Uid differs from AtechProjectId, or the chat's id does not follow."""
    out, seen = [], {}
    for p in paths:
        uid, pid, where = ps.read_file_ids(p)
        if not pid or pid != uid:
            out.append("%s: id %r / Uid %r" % (os.path.basename(p), pid, uid))
        if pid in shipped_ids:
            out.append("%s kept the shipped id" % os.path.basename(p))
        if pid in seen:
            out.append("%s shares its id with %s" % (os.path.basename(p), seen[pid]))
        seen[pid] = os.path.basename(p)
        chat = ps.read_chat(p) or {}
        if chat.get("id") != pid:
            out.append("%s: chat id %r" % (os.path.basename(p), chat.get("id")))
        if os.path.realpath(where or "/nowhere") != os.path.realpath(p):
            out.append("%s: AtechProjectFile %r" % (os.path.basename(p), where))
    return out


class Isolated(unittest.TestCase):
    """Temp projects folder, state files and trust store."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="atech-dp-"))
        self.ship = os.path.join(self.tmp, "ship")
        self.folder = os.path.join(self.tmp, "Atech Projects")
        self._saved = (ps.STATE_PATH, dp.STATE_PATH, dp.SHIPPED_DIR,
                       os.environ.get("ATECH_PROJECTS_DIR"), build._trust_path)
        ps.STATE_PATH = os.path.join(self.tmp, "state", "projects.json")
        dp.STATE_PATH = None                    # derived: next to projects.json
        dp.SHIPPED_DIR = self.ship
        os.environ["ATECH_PROJECTS_DIR"] = self.folder
        self.trust = os.path.join(self.tmp, "trusted_builds.json")
        build._trust_path = lambda: self.trust
        self.rows = make_shipped(self.ship, ["Toy car", "Desk robot", "RC tank"])
        self.shipped_ids = {r["id"] for r in self.rows}

    def tearDown(self):
        (ps.STATE_PATH, dp.STATE_PATH, dp.SHIPPED_DIR, env,
         build._trust_path) = self._saved
        if env is None:
            os.environ.pop("ATECH_PROJECTS_DIR", None)
        else:
            os.environ["ATECH_PROJECTS_DIR"] = env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def files(self):
        return sorted(n for n in os.listdir(self.folder) if n.endswith(".FCStd")) \
            if os.path.isdir(self.folder) else []

    def path(self, title):
        return os.path.join(self.folder, title + ".FCStd")


# ------------------------------------------------------------ R451-R453
class TestInstall(Isolated):
    def test_r451_first_run_copies_every_project(self):
        res = dp.install_defaults()
        self.assertEqual(res["installed"], ["Toy car", "Desk robot", "RC tank"])
        self.assertEqual(self.files(), ["Desk robot.FCStd", "RC tank.FCStd",
                                        "Toy car.FCStd"])
        # the record sits next to projects_store's own state, never in ~
        self.assertEqual(os.path.dirname(dp.state_path()),
                         os.path.dirname(ps.STATE_PATH))
        st = dp.load_state()
        self.assertEqual(st["version"], 1)
        self.assertEqual(sorted(st["titles"]), ["Desk robot", "RC tank", "Toy car"])
        # Home lists newest first: the curated order is kept
        m = [os.path.getmtime(self.path(t)) for t in ("Toy car", "Desk robot", "RC tank")]
        self.assertEqual(m, sorted(m, reverse=True))

    def test_r451_default_folder_is_projects_store_s(self):
        dp.install_defaults()
        self.assertEqual(os.path.realpath(ps.projects_dir()), self.folder)
        self.assertTrue(os.path.isfile(self.path("Toy car")))

    def test_r452_every_copy_has_a_fresh_id(self):
        dp.install_defaults()
        paths = [self.path(t) for t in ("Toy car", "Desk robot", "RC tank")]
        self.assertEqual(fresh_id_problems(paths, self.shipped_ids), [])
        # the shipped files themselves are untouched
        for r in self.rows:
            self.assertEqual(_sha(os.path.join(self.ship, r["file"])), r["sha256"])

    def test_r452_sabotage_no_rekey_is_caught(self):
        with mock.patch.object(ps, "rekey_file", lambda path, new, fp=None: ""), \
                mock.patch.object(dp, "_rekey_chat", lambda path, pid: None):
            dp.install_defaults()
        paths = [self.path(t) for t in ("Toy car", "Desk robot", "RC tank")]
        probs = fresh_id_problems(paths, self.shipped_ids)
        self.assertTrue(any("kept the shipped id" in p for p in probs), probs)

    def test_r451_rerun_is_idempotent(self):
        dp.install_defaults()
        before = {n: (_sha(os.path.join(self.folder, n)),
                      os.path.getmtime(os.path.join(self.folder, n))) for n in self.files()}
        res = dp.install_defaults()
        self.assertFalse(res["ran"])
        self.assertEqual(res["installed"], [])
        after = {n: (_sha(os.path.join(self.folder, n)),
                     os.path.getmtime(os.path.join(self.folder, n))) for n in self.files()}
        self.assertEqual(before, after)

    def test_r451_deleted_default_stays_deleted(self):
        dp.install_defaults()
        os.remove(self.path("Desk robot"))
        dp.install_defaults()
        self.assertNotIn("Desk robot.FCStd", self.files())
        # not even when the manifest's version grows
        make_shipped(self.ship, ["Toy car", "Desk robot", "RC tank"], version=2)
        dp.install_defaults()
        self.assertNotIn("Desk robot.FCStd", self.files())

    def test_r451_sabotage_forgetful_record_re_adds(self):
        """The record is what keeps a deleted default deleted: without it
        (a sabotaged _save_state) the next run puts the file back."""
        with mock.patch.object(dp, "_save_state", lambda data: True):
            dp.install_defaults()
            os.remove(self.path("Desk robot"))
            dp.install_defaults()
        self.assertIn("Desk robot.FCStd", self.files(), "the sabotage was not seen")

    def test_r451_user_edited_file_untouched(self):
        dp.install_defaults()
        with zipfile.ZipFile(self.path("Toy car"), "a") as zf:
            zf.writestr("user-edit.txt", "mine")
        mine = _sha(self.path("Toy car"))
        make_shipped(self.ship, ["Toy car", "Desk robot", "RC tank"], version=2)
        dp.install_defaults()
        self.assertEqual(_sha(self.path("Toy car")), mine)

    def test_r451_user_file_of_the_same_name_untouched(self):
        os.makedirs(self.folder)
        with open(self.path("RC tank"), "wb") as fh:
            fh.write(b"the user's own tank")
        res = dp.install_defaults()
        self.assertIn("RC tank", res["skipped"])
        with open(self.path("RC tank"), "rb") as fh:
            self.assertEqual(fh.read(), b"the user's own tank")
        self.assertEqual(sorted(res["installed"]), ["Desk robot", "Toy car"])

    def test_r451_newer_manifest_adds_only_new_titles(self):
        dp.install_defaults()
        os.remove(self.path("Toy car"))
        make_shipped(self.ship, ["Toy car", "Desk robot", "RC tank", "Desk fan"],
                     version=2)
        res = dp.install_defaults()
        self.assertEqual(res["installed"], ["Desk fan"])
        self.assertNotIn("Toy car.FCStd", self.files())
        self.assertEqual(dp.load_state()["version"], 2)
        # same version again: nothing
        self.assertFalse(dp.install_defaults()["ran"])

    def test_r451_damaged_shipped_file_is_skipped(self):
        with open(os.path.join(self.ship, "Toy car.FCStd"), "ab") as fh:
            fh.write(b"junk")
        res = dp.install_defaults()
        self.assertIn("damaged", res["skipped"]["Toy car"])
        self.assertNotIn("Toy car.FCStd", self.files())

    def test_r451_nothing_shipped_does_nothing(self):
        dp.SHIPPED_DIR = os.path.join(self.tmp, "none")
        res = dp.install_defaults()
        self.assertEqual((res["installed"], res["ran"]), ([], False))
        self.assertEqual(self.files(), [])

    def test_r453_shipped_builds_trusted_under_the_new_id(self):
        dp.install_defaults()
        with open(self.trust) as fh:
            store = json.load(fh)
        pid = ps.file_id(self.path("Toy car"))
        self.assertEqual(store[pid]["builds"]["b0"]["sha"], "s0")
        for r in self.rows:
            self.assertNotIn(r["id"], store)

    def test_r453_damaged_copy_is_not_trusted(self):
        rec = dict(self.rows[0], sha256="0" * 64)
        dest = os.path.join(self.tmp, "x.FCStd")
        pid = dp.copy_fresh(os.path.join(self.ship, "Toy car.FCStd"), dest, rec)
        store = json.load(open(self.trust)) if os.path.exists(self.trust) else {}
        self.assertNotIn(pid, store)

    def test_r454_new_from_default_is_a_fresh_copy(self):
        dp.install_defaults()
        opened = []
        fc = types.ModuleType("FreeCAD")
        fc.openDocument = opened.append
        with mock.patch.dict(sys.modules, {"FreeCAD": fc}):
            a = dp.new_from_default("Toy car")
            b = dp.new_from_default("Toy car")
        self.assertEqual([os.path.basename(a), os.path.basename(b)],
                         ["Toy car 2.FCStd", "Toy car 3.FCStd"])
        self.assertEqual(opened, [a, b])
        paths = [self.path("Toy car"), a, b]
        self.assertEqual(fresh_id_problems(paths, self.shipped_ids), [])
        self.assertIsNone(dp.new_from_default("No such project", open_doc=False))

    def test_r454_never_overwrites(self):
        os.makedirs(self.folder)
        with open(self.path("Desk robot"), "wb") as fh:
            fh.write(b"mine")
        with self.assertRaises(ps.ProjectError):
            dp.copy_fresh(os.path.join(self.ship, "Desk robot.FCStd"),
                          self.path("Desk robot"))
        with open(self.path("Desk robot"), "rb") as fh:
            self.assertEqual(fh.read(), b"mine")
        p = dp.new_from_default("Desk robot", open_doc=False)
        self.assertEqual(os.path.basename(p), "Desk robot 2.FCStd")

    def _appear_during_copy(self, dest):
        """A user file at `dest` appears after copy_fresh's exists check
        (while it rewrites the zip). Returns the file's bytes after."""
        real = ps.rekey_file

        def rekey(*a, **k):
            out = real(*a, **k)
            with open(dest, "wb") as fh:
                fh.write(b"mine, made meanwhile")
            return out
        with mock.patch.object(ps, "rekey_file", rekey):
            try:
                dp.copy_fresh(os.path.join(self.ship, "Toy car.FCStd"), dest)
            except ps.ProjectError:
                pass
        with open(dest, "rb") as fh:
            return fh.read()

    def test_r451_file_appearing_meanwhile_is_never_overwritten(self):
        dest = os.path.join(self.tmp, "race.FCStd")
        self.assertEqual(self._appear_during_copy(dest), b"mine, made meanwhile")
        self.assertEqual([n for n in os.listdir(self.tmp) if "atech-default" in n], [])

    def test_r451_sabotage_plain_replace_overwrites(self):
        """With os.link failing and the exists re-check gone (a bare
        os.replace), the race test sees the user's file lost."""
        real_exists = os.path.exists
        dest = os.path.join(self.tmp, "race.FCStd")
        calls = {"n": 0}

        def exists(p):
            if p == dest:
                calls["n"] += 1
                if calls["n"] > 1:          # the re-check after the rewrite
                    return False
            return real_exists(p)
        with mock.patch.object(dp.os, "link", side_effect=PermissionError), \
                mock.patch.object(dp.os.path, "exists", exists):
            got = self._appear_during_copy(dest)
        self.assertNotEqual(got, b"mine, made meanwhile", "the sabotage was not seen")

    def test_entries_and_thumbnail(self):
        self.assertEqual([t for t, _k, _s in dp.entries()],
                         ["Toy car", "Desk robot", "RC tank"])
        self.assertEqual(dp.thumbnail("RC tank"), b"\x89PNG fake")
        os.remove(os.path.join(self.ship, "RC tank.FCStd"))
        self.assertEqual([t for t, _k, _s in dp.entries()], ["Toy car", "Desk robot"])


# ------------------------------------------------- the build gate (R450)
class TestCheckShipped(Isolated):
    def test_ok(self):
        make_shipped(self.ship, ["A", "B", "C", "D", "E", "F"])
        self.assertEqual(dp.check_shipped(self.ship), (True, "6 projects"))

    def test_sabotage_too_few(self):
        ok, why = dp.check_shipped(self.ship)          # 3 shipped
        self.assertFalse(ok)
        self.assertIn("6 needed", why)

    def test_sabotage_wrong_sha(self):
        make_shipped(self.ship, ["A", "B", "C", "D", "E", "F"])
        with open(os.path.join(self.ship, "C.FCStd"), "ab") as fh:
            fh.write(b"!")
        ok, why = dp.check_shipped(self.ship)
        self.assertFalse(ok)
        self.assertIn("C.FCStd sha256 differs", why)

    def test_sabotage_missing_file_and_manifest(self):
        make_shipped(self.ship, ["A", "B", "C", "D", "E", "F"])
        os.remove(os.path.join(self.ship, "F.FCStd"))
        self.assertEqual(dp.check_shipped(self.ship), (False, "F.FCStd missing"))
        os.remove(os.path.join(self.ship, dp.MANIFEST))
        self.assertFalse(dp.check_shipped(self.ship)[0])

    def test_verify_tree_has_the_row(self):
        src = open(VERIFY, encoding="utf-8").read()
        self.assertIn("check_shipped", src)
        self.assertIn('key="default-projects"', src)
        sab = open(os.path.join(REPO, "branding", "tests",
                                "test_verify_sabotage.sh")).read()
        self.assertIn("'default-projects'", sab)

    def test_build_scripts_run_the_generator_after_the_addon(self):
        for name in ("build_macos.sh", "build_appimage.sh"):
            src = open(os.path.join(REPO, "branding", name), encoding="utf-8").read()
            i_addon = src.index('say "addon bundled"')
            i_gen = src.index("make_default_projects.py")
            self.assertLess(i_addon, i_gen, name)
            self.assertIn('DP_DST="$AA/default_projects"', src, name)
            self.assertIn('-ge 6 ]]', src, name)
            # session 74's GLB step is still there
            self.assertIn("models/glb/*.glb", src, name)


# ------------------------------------------------------------ R455
@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestStartup(Isolated):
    def setUp(self):
        super().setUp()
        dp._SCHEDULED.clear()
        os.environ.pop(dp.ENV_OFF, None)

    def tearDown(self):
        dp._SCHEDULED.clear()
        super().tearDown()

    def wait_result(self, limit=10):
        t0 = time.time()
        while "result" not in dp._SCHEDULED and time.time() - t0 < limit:
            _APP.processEvents()
            time.sleep(0.01)
        return dp._SCHEDULED.get("result")

    def test_r455_deferred_never_inline(self):
        self.assertTrue(dp.schedule_install())
        self.assertEqual(self.files(), [], "installed inline, not from the timer")
        res = self.wait_result()
        self.assertEqual(res and res["installed"], ["Toy car", "Desk robot", "RC tank"])
        self.assertEqual(len(self.files()), 3)
        # the trust records were written (on the GUI thread) under the new ids
        with open(self.trust) as fh:
            store = json.load(fh)
        self.assertIn(ps.file_id(self.path("Toy car")), store)
        self.assertFalse(dp.schedule_install(), "scheduled twice in one session")

    def _slow_copy(self, seconds):
        real = dp.copy_fresh

        def slow(*a, **k):
            time.sleep(seconds)
            return real(*a, **k)
        return slow

    def test_r455_gui_thread_stays_free_while_copying(self):
        """Each copy takes 0.4 s here (about the real ones); the event loop
        must keep turning (a 50 ms timer) all through the install."""
        ticks, gaps, last = [], [], [time.time()]

        def tick():
            now = time.time()
            gaps.append(now - last[0])
            last[0] = now
            ticks.append(now)
        t = QtCore.QTimer()
        t.setInterval(50)
        t.timeout.connect(tick)
        with mock.patch.object(dp, "copy_fresh", self._slow_copy(0.4)):
            t.start()
            self.assertTrue(dp.schedule_install())
            last[0] = time.time()
            res = self.wait_result()
            t.stop()
        self.assertEqual(len(res["installed"]), 3)
        self.assertLess(max(gaps), 0.3, "the GUI thread was blocked %.2fs" % max(gaps))

    def test_r455_sabotage_install_on_the_gui_thread_is_caught(self):
        """The same measure sees a blocked event loop when the install runs
        on the GUI thread (the earlier QTimer-only version)."""
        gaps, last = [], [time.time()]

        def tick():
            now = time.time()
            gaps.append(now - last[0])
            last[0] = now
        t = QtCore.QTimer()
        t.setInterval(50)
        t.timeout.connect(tick)
        with mock.patch.object(dp, "copy_fresh", self._slow_copy(0.4)):
            t.start()
            QtCore.QTimer.singleShot(0, dp.install_defaults)
            t0 = time.time()
            last[0] = t0
            while time.time() - t0 < 2:
                _APP.processEvents()
                time.sleep(0.01)
            t.stop()
        self.assertEqual(len(self.files()), 3)
        self.assertGreater(max(gaps), 0.3, "the sabotage was not seen")

    def test_r455_nothing_shipped_schedules_nothing(self):
        dp.SHIPPED_DIR = os.path.join(self.tmp, "none")
        self.assertFalse(dp.schedule_install())

    def test_r455_off_switch(self):
        with mock.patch.dict(os.environ, {dp.ENV_OFF: "1"}):
            self.assertFalse(dp.schedule_install())

    def test_r455_projects_store_install_is_the_one_call_site(self):
        src = inspect.getsource(ps.install)
        self.assertIn("default_projects.schedule_install()", src)
        hits = []
        pkg = os.path.join(ADDON, "acadagent")
        for root, _d, fs in os.walk(pkg):
            for f in fs:
                if f.endswith(".py") and f != "default_projects.py":
                    s = open(os.path.join(root, f), encoding="utf-8").read()
                    if "schedule_install(" in s or "install_defaults(" in s:
                        hits.append(f)
        self.assertEqual(hits, ["projects_store.py"])

    def test_r455_sabotage_inline_install_is_caught(self):
        """The deferral test sees an inline install."""
        def inline(delay_ms=0):
            dp.install_defaults()
            return True
        with mock.patch.object(dp, "schedule_install", inline):
            dp.schedule_install()
        self.assertNotEqual(self.files(), [], "the sabotage was not seen")


# ------------------------------------------------------------ R456
def _menu_texts(menu):
    out = []
    for a in menu.actions():
        out.append(a.text())
        if a.menu() is not None:
            out.append("<submenu %s>" % a.text())
            out.extend(_menu_texts(a.menu()))
    return out


@unittest.skipIf(QtWidgets is None, "PySide6 not installed")
class TestNoStarters(unittest.TestCase):
    def picker_texts(self):
        from acadagent import navbar
        pk = navbar.ProjectPicker()
        try:
            pk._fill()
            return _menu_texts(pk.menu())
        finally:
            pk.deleteLater()

    def test_r456_picker_has_no_starter_submenu(self):
        texts = self.picker_texts()
        self.assertIn("New project", texts)
        self.assertFalse([t for t in texts if "starter" in t.lower()
                          or t.startswith("<submenu")], texts)

    def test_r456_sabotage_starter_entry_is_seen(self):
        from acadagent import navbar
        real = navbar.project_entries

        def with_starter(*a, **k):
            return real(*a, **k) + [("starter", [("x", "X")],
                                     "Atech starter projects", False)]
        with mock.patch.object(navbar, "project_entries", with_starter):
            texts = self.picker_texts()
        self.assertTrue([t for t in texts if "starter" in t.lower()])

    def test_r456_project_entries_ignore_starters(self):
        from acadagent import navbar
        out = navbar.project_entries([], None, [], [("motion-rig", "Motion Rig")])
        self.assertEqual([k for k, *_ in out], ["sep", "new", "file"])

    def test_r456_no_new_project_menu_source(self):
        init = open(os.path.join(ADDON, "InitGui.py"), encoding="utf-8").read()
        code = "\n".join(l for l in init.splitlines() if not l.strip().startswith("#"))
        self.assertNotIn('"New Project"', code)
        self.assertNotIn("project_command_ids", code)
        cmds = open(os.path.join(ADDON, "acadagent", "commands.py"),
                    encoding="utf-8").read()
        tree = ast.parse(cmds)
        names = {n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
        self.assertFalse(names & {"NewModuleProject", "project_command_ids"}, names)
        self.assertNotIn("AcadAgent_Project_", cmds)
        nav = open(os.path.join(ADDON, "acadagent", "navbar.py"), encoding="utf-8").read()
        self.assertNotIn("def _starters", nav)
        self.assertNotIn("on_starter", nav)
        sh = open(os.path.join(ADDON, "acadagent", "shell.py"), encoding="utf-8").read()
        self.assertNotIn("_new_starter_project", sh)
        self.assertNotIn("on_starter", sh)

    def test_r456_projects_py_kept_for_its_other_users(self):
        """projects.py's build code stays: the Atech modules page, build
        and board_look still import it."""
        users = []
        pkg = os.path.join(ADDON, "acadagent")
        for f in os.listdir(pkg):
            if f.endswith(".py") and f != "projects.py":
                if re.search(r"from \. import projects\b(?!_)",
                             open(os.path.join(pkg, f), encoding="utf-8").read()):
                    users.append(f)
        self.assertTrue(users)
        self.assertTrue(os.path.isfile(os.path.join(pkg, "projects.py")))


try:
    from test_shell_round12 import Case as _ShellCase
except Exception:                                      # noqa: BLE001
    _ShellCase = None


@unittest.skipIf(_ShellCase is None, "shell fakes unavailable")
class TestHomeRow(_ShellCase if _ShellCase else unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.ship = os.path.join(self.tmp, "ship")
        make_shipped(self.ship, ["Toy car", "Desk robot", "RC tank"])
        self._ship = dp.SHIPPED_DIR

    def tearDown(self):
        dp.SHIPPED_DIR = self._ship
        super().tearDown()

    def test_r456_home_uses_the_default_projects(self):
        dp.SHIPPED_DIR = self.ship
        home = self.shell.HomeView()
        self.assertEqual([c.default_title for c in home.example_cards],
                         ["Toy car", "Desk robot", "RC tank"])
        got = []
        with mock.patch.object(dp, "new_from_default",
                               lambda t: got.append(t) or "/x/%s.FCStd" % t):
            home.example_cards[2].clicked.emit()
        self.assertEqual(got, ["RC tank"])
        home.close()

    def test_r456_sabotage_missing_project_says_so(self):
        dp.SHIPPED_DIR = self.ship
        self.shell.install()
        with mock.patch.object(dp, "new_from_default", lambda t: None):
            self.assertIsNone(self.shell.open_default("Toy car"))
        self.assertEqual(self.shell.chat_panel().notices[-1][0],
                         "Example not available")

    def test_r456_no_defaults_falls_back_to_building_examples(self):
        dp.SHIPPED_DIR = os.path.join(self.tmp, "none")
        home = self.shell.HomeView()
        self.assertEqual([c.example_key for c in home.example_cards],
                         ["toy_car", "desk_robot", "smart_speaker"])
        self.assertEqual([c.default_title for c in home.example_cards],
                         [None, None, None])
        home.close()


# ----------------------------------------------- R450 the generator, real
CHECK_FC = r'''
import json, os, sys, zipfile
import FreeCAD as App
out = {}
for p in json.loads(os.environ["DP_FILES"]):
    d = App.openDocument(p)
    roles = [getattr(o, "AtechRole", "") for o in d.Objects]
    out[os.path.basename(p)] = {
        "board": roles.count("board"), "modules": roles.count("module"),
        "modules_named": sorted(getattr(o, "AtechModule", "") for o in d.Objects
                                if getattr(o, "AtechRole", "") == "module"),
        "scripted": sum(1 for o in d.Objects if getattr(o, "AtechAgentScript", "")),
        "id": getattr(d, "AtechProjectId", ""), "uid": str(d.Uid),
        "label": d.Label, "objects": [o.Name for o in d.Objects]}
    App.closeDocument(d.Name)
print("DPCHECK " + json.dumps(out))
'''


def run_fc(script, env_extra, timeout=900):
    home = os.path.realpath(tempfile.mkdtemp(prefix="atech-dp-home-"))
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONPATH", "PYTHONHOME")}
    env.update(HOME=home, FREECAD_USER_HOME=home, QT_QPA_PLATFORM="offscreen",
               ATECH_ARTIFACTS=os.path.join(REPO, "models"))
    env.update(env_extra)
    try:
        p = subprocess.run([FREECADCMD] + script, env=env, capture_output=True,
                           text=True, timeout=timeout, cwd=home,
                           stdin=subprocess.DEVNULL)
    finally:
        shutil.rmtree(home, ignore_errors=True)
    return p.stdout + p.stderr


def generate(out, only, sabotage=""):
    log = run_fc([GENERATOR, "--pass", EXAMPLES, out],
                 {"ATECH_DEFAULTS_ONLY": only, "ATECH_DEFAULTS_SABOTAGE": sabotage})
    m = re.findall(r"DEFAULT_PROJECTS=(\d+)/(\d+)", log)
    return (tuple(int(x) for x in m[-1]) if m else None), log


def file_problems(path, rec):
    """What a shipped default project must have, read off the zip."""
    probs = []
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        xml = zf.read("Document.xml")
        if not re.search(rb'<Property name="AtechRole"[^>]*>\s*<String value="board"', xml):
            probs.append("no tagged board")
        if not re.search(rb'<Property name="AtechRole"[^>]*>\s*<String value="module"', xml):
            probs.append("no tagged module")
        if b'name="AtechAgentScript"' not in xml:
            probs.append("no AtechAgentScript")
        if "thumbnails/Thumbnail.png" not in names:
            probs.append("no thumbnail")
        else:
            png = zf.read("thumbnails/Thumbnail.png")
            if png[:8] != b"\x89PNG\r\n\x1a\n" or \
                    struct.unpack(">II", png[16:24]) != (512, 512):
                probs.append("thumbnail is not a 512 x 512 PNG")
        if ps.CHAT_JSON not in names:
            probs.append("no starter chat")
        else:
            meta = json.loads(zf.read(ps.CHAT_JSON))
            ents = meta["transcript"]["entries"]
            text = ents[0].get("text", "") if ents else ""
            if len(ents) != 1 or ents[0].get("role") != "agent":
                probs.append("chat is not one agent message")
            if "port" not in text or "Try asking" not in text or text.count('- "') < 2:
                probs.append("chat lacks ports or two suggestions")
            if meta.get("id") != rec.get("id"):
                probs.append("chat id differs")
        if "GuiDocument.xml" not in names:
            probs.append("no GuiDocument.xml")
        else:
            import xml.etree.ElementTree as ET
            g = ET.fromstring(zf.read("GuiDocument.xml"))
            vps = g.findall("./ViewProviderData/ViewProvider")
            files = [m.get("file") for m in g.iter("MaterialList")]
            if not vps or any(f not in names for f in files) or not files:
                probs.append("GuiDocument.xml incomplete")
        pid = ps._prop_value(ps._doc_head(xml), ps.PROJECT_PROP)
        if not pid or pid != rec.get("id"):
            probs.append("AtechProjectId %r" % pid)
        for n in names:
            b = zf.read(n)
            if re.search(rb"/Users/[A-Za-z0-9._-]+/|/private/tmp/|/tmp/claude-", b):
                probs.append("build-machine path in %s" % n)
                break
    if _sha(path) != rec.get("sha256"):
        probs.append("sha256 differs from the manifest")
    return probs


@unittest.skipUnless(os.path.isfile(FREECADCMD), "built app not found")
class TestGenerator(unittest.TestCase):
    ONLY = "bedside_lamp,weather_station"

    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.realpath(tempfile.mkdtemp(prefix="atech-dpgen-"))
        cls.out = os.path.join(cls.tmp, "out")
        t0 = time.time()
        cls.counts, cls.log = generate(cls.out, cls.ONLY)
        cls.seconds = time.time() - t0
        try:
            with open(os.path.join(cls.out, "manifest.json")) as fh:
                cls.man = json.load(fh)
        except (OSError, ValueError):
            cls.man = None

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_r450_marker_and_manifest(self):
        self.assertEqual(self.counts, (2, 2), self.log[-3000:])
        self.assertEqual([p["title"] for p in self.man["projects"]],
                         ["Bedside lamp", "Weather station"])
        for p in self.man["projects"]:
            self.assertGreater(p["seconds"], 0)
            self.assertTrue(p["hardware"] and p["hardware"][0]["module"] == "board")
            self.assertTrue(p["trust"])
            self.assertTrue(p["summary"])
        sys.stderr.write("\n[generator %.0fs] %s\n" % (self.seconds, ", ".join(
            "%s %.1fs %d KB" % (p["title"], p["seconds"], p["bytes"] // 1024)
            for p in self.man["projects"])))

    def test_r450_files_have_everything(self):
        for p in self.man["projects"]:
            self.assertEqual(file_problems(os.path.join(self.out, p["file"]), p), [],
                             p["title"])
        self.assertEqual(dp.check_shipped(self.out, minimum=2), (True, "2 projects"))

    def test_r450_reopen_in_freecad(self):
        files = [os.path.join(self.out, p["file"]) for p in self.man["projects"]]
        script = os.path.join(self.tmp, "check_fc.py")
        with open(script, "w") as fh:
            fh.write(CHECK_FC)
        log = run_fc([script], {"DP_FILES": json.dumps(files)})
        lines = [l for l in log.splitlines() if l.startswith("DPCHECK ")]
        self.assertTrue(lines, log[-2000:])
        got = json.loads(lines[-1][8:])
        for p in self.man["projects"]:
            g = got[p["file"]]
            self.assertEqual(g["board"], 1, p["title"])
            self.assertEqual(g["modules"], len(p["hardware"]) - 1, p["title"])
            self.assertEqual(g["modules_named"], sorted(
                h["module"] for h in p["hardware"][1:]))
            self.assertGreater(g["scripted"], 5)
            self.assertEqual(g["id"], p["id"])
            self.assertEqual(g["uid"], p["id"])
            self.assertEqual(g["label"], p["title"])
            # GuiDocument.xml names exactly these objects
            with zipfile.ZipFile(os.path.join(self.out, p["file"])) as zf:
                vps = re.findall(rb'<ViewProvider name="([^"]+)"', zf.read("GuiDocument.xml"))
            self.assertEqual([v.decode() for v in vps], g["objects"])

    def test_r450_install_the_real_files(self):
        tmp = os.path.join(self.tmp, "install")
        saved = (ps.STATE_PATH, dp.STATE_PATH, dp.SHIPPED_DIR, build._trust_path)
        try:
            ps.STATE_PATH = os.path.join(tmp, "projects.json")
            dp.STATE_PATH = None
            dp.SHIPPED_DIR = self.out
            build._trust_path = lambda: os.path.join(tmp, "trust.json")
            res = dp.install_defaults(projects_dir=os.path.join(tmp, "P"))
            self.assertEqual(res["installed"], ["Bedside lamp", "Weather station"])
            paths = [os.path.join(tmp, "P", t + ".FCStd") for t in res["installed"]]
            self.assertEqual(fresh_id_problems(
                paths, {p["id"] for p in self.man["projects"]}), [])
            with open(os.path.join(tmp, "trust.json")) as fh:
                store = json.load(fh)
            for path, p in zip(paths, self.man["projects"]):
                self.assertEqual(store[ps.file_id(path)]["builds"], {
                    b: dict(v, t=store[ps.file_id(path)]["builds"][b]["t"])
                    for b, v in p["trust"].items()})
        finally:
            ps.STATE_PATH, dp.STATE_PATH, dp.SHIPPED_DIR, build._trust_path = saved


#: Builds (two plain boxes) but fails the build's own overlap check.
FAILING_EXAMPLE = """import Part
from FreeCAD import Vector
a = doc.addObject("Part::Feature", "Box_A")
a.Shape = Part.makeBox(20, 20, 20)
b = doc.addObject("Part::Feature", "Box_B")
b.Shape = Part.makeBox(20, 20, 20, Vector(10, 0, 0))
"""


@unittest.skipUnless(os.path.isfile(FREECADCMD), "built app not found")
class TestGeneratorSabotage(unittest.TestCase):
    """Each sabotaged run must fail file_problems (or the marker)."""

    def test_sabotage_each_feature_is_caught(self):
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="atech-dpsab-"))
        try:
            for sab, must in (("nohw", "no tagged board"), ("nothumb", "no thumbnail"),
                              ("nochat", "no starter chat"), ("noid", "AtechProjectId")):
                out = os.path.join(tmp, sab)
                counts, log = generate(out, "weather_station", sab)
                self.assertEqual(counts, (1, 1), log[-2000:])
                with open(os.path.join(out, "manifest.json")) as fh:
                    man = json.load(fh)
                p = man["projects"][0]
                probs = file_problems(os.path.join(out, p["file"]), p)
                self.assertTrue(any(must in x for x in probs), (sab, probs))
            # a missing example is skipped and reported, never fatal
            out = os.path.join(tmp, "missing")
            ex = os.path.join(tmp, "examples")
            os.makedirs(ex)
            log = run_fc([GENERATOR, "--pass", ex, out],
                         {"ATECH_DEFAULTS_ONLY": "toy_car",
                          "ATECH_ADDON_DIR": ADDON})
            self.assertIn("DEFAULT_PROJECTS=0/1", log, log[-2000:])
            with open(os.path.join(out, "manifest.json")) as fh:
                man = json.load(fh)
            self.assertEqual(man["skipped"][0]["example"], "toy_car")
            self.assertIn("missing", man["skipped"][0]["error"])
            self.assertNotIn(tmp, json.dumps(man), "a build-machine path in the manifest")
            self.assertFalse(dp.check_shipped(out, minimum=1)[0])
            # an example that builds but fails its own check is not shipped
            with open(os.path.join(ex, "toy_car.py"), "w") as fh:
                fh.write(FAILING_EXAMPLE)
            out = os.path.join(tmp, "failing")
            log = run_fc([GENERATOR, "--pass", ex, out],
                         {"ATECH_DEFAULTS_ONLY": "toy_car",
                          "ATECH_ADDON_DIR": ADDON})
            self.assertIn("DEFAULT_PROJECTS=0/1", log, log[-2000:])
            with open(os.path.join(out, "manifest.json")) as fh:
                man = json.load(fh)
            self.assertIn("its own check fails", man["skipped"][0]["error"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
