"""Projects as files (projects_store.py, navbar.py, the lifecycle parts of
panel.py): R360-R372, PRD "Projects" 1-9 and the data side of "Opening".

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_projects_store

Three layers:
  TestStore*      pure Python on synthetic .FCStd zips (no FreeCAD, no Qt)
  TestNavbar / TestPanel*   offscreen Qt with a FreeCAD stub (skip without
                  PySide6)
  TestFreeCAD     real documents in freecadcmd (fc_projects_store.py): Save
                  As / Save a Copy / Finder copies get their own id, the chat
                  is written into the file, rename / duplicate / trash /
                  export, autosave, and the kill -9 crash test (skip without
                  the built app)
Each feature has a sabotage case that breaks it and expects the check to
fail.
"""
import base64
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from acadagent import migrate, projects_store as ps  # noqa: E402

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    _APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from acadagent import navbar
except ImportError:                                    # no Qt here
    navbar = None

APP_BIN = os.path.join(REPO, "dist", "build-macos-arm64", "Atech Atelier.app",
                       "Contents", "Resources", "bin")
FREECADCMD = os.path.join(APP_BIN, "freecadcmd")

DOC_XML = """<?xml version='1.0' encoding='utf-8'?>
<Document SchemaVersion="4" ProgramVersion="1.1" FileVersion="1">
    <Properties Count="4" TransientCount="0">
        <Property name="AtechProjectFile" type="App::PropertyString" group="Atech" status="1">
            <String value="%(file)s"/>
        </Property>
        <Property name="AtechProjectId" type="App::PropertyString" group="Atech" status="1">
            <String value="%(pid)s"/>
        </Property>
        <Property name="Label" type="App::PropertyString">
            <String value="%(label)s"/>
        </Property>
        <Property name="Uid" type="App::PropertyUUID" status="1">
            <Uuid value="%(uid)s"/>
        </Property>
    </Properties>
    <Objects Count="1">
        <Object type="Part::Feature" name="Board" id="1"/>
    </Objects>
    <ObjectData Count="1">
        <Object name="Board">
            <Properties Count="1" TransientCount="0">
                %(role)s
            </Properties>
        </Object>
    </ObjectData>
</Document>
"""
ROLE = ('<Property name="AtechRole" type="App::PropertyString" '
        'group="Atech"><String value="board"/></Property>')
PNG = base64.b64decode(  # a real 1 x 1 PNG
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC")


def make_fcstd(path, uid="uid-1", pid=None, file=None, role=False,
               thumb=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Document.xml", DOC_XML % {
            "uid": uid, "pid": uid if pid is None else pid,
            "file": file if file is not None else os.path.realpath(path),
            "label": os.path.splitext(os.path.basename(path))[0],
            "role": ROLE if role else ""})
        zf.writestr("Board.Shape.brp", b"brep" * 10)
        if thumb:
            zf.writestr("thumbnails/Thumbnail.png", PNG)
    return path


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="projstore-"))
        self._saved = (ps.STATE_PATH, ps.SESSIONS_PATH,
                       os.environ.get("ATECH_PROJECTS_DIR"))
        ps.STATE_PATH = os.path.join(self.tmp, "state", "projects.json")
        ps.SESSIONS_PATH = os.path.join(self.tmp, "agent", "sessions.json")
        self.folder = os.path.join(self.tmp, "Atech Projects")
        os.makedirs(self.folder)
        os.environ["ATECH_PROJECTS_DIR"] = self.folder
        ps._info_cache.clear()
        self._fc = sys.modules.pop("FreeCAD", None)

    def tearDown(self):
        ps.STATE_PATH, ps.SESSIONS_PATH, env = self._saved
        if env is None:
            os.environ.pop("ATECH_PROJECTS_DIR", None)
        else:
            os.environ["ATECH_PROJECTS_DIR"] = env
        if self._fc is not None:
            sys.modules["FreeCAD"] = self._fc
        shutil.rmtree(self.tmp, ignore_errors=True)


# ----------------------------------------------------------- R360, R361
class TestStoreNames(StoreCase):
    def test_r360_projects_folder_default_env_and_setting(self):
        os.environ.pop("ATECH_PROJECTS_DIR")
        self.assertEqual(ps.projects_dir(), os.path.join(
            os.path.expanduser("~"), "Documents", "Atech Projects"))
        ps.set_projects_dir(os.path.join(self.tmp, "Elsewhere"))
        self.assertEqual(ps.projects_dir(), os.path.join(self.tmp, "Elsewhere"))
        ps.set_projects_dir(None)
        self.assertTrue(ps.projects_dir().endswith("Atech Projects"))
        os.environ["ATECH_PROJECTS_DIR"] = self.folder
        self.assertEqual(ps.projects_dir(), self.folder)

    def test_r361_names(self):
        self.assertEqual(ps.clean_name("  My   lamp.FCStd "), "My lamp")
        self.assertEqual(ps.clean_name("a/b:c"), "a b c")
        self.assertEqual(ps.clean_name("..hidden"), "hidden")
        self.assertEqual(ps.clean_name("   "), "")
        self.assertEqual(len(ps.clean_name("x" * 300)), ps.NAME_MAX)
        self.assertEqual(ps.default_name(self.folder), "Untitled 1")
        make_fcstd(os.path.join(self.folder, "Untitled 1.FCStd"))
        self.assertEqual(ps.default_name(self.folder), "Untitled 2")
        self.assertEqual(ps.default_name(self.folder, taken={"Untitled 2"}),
                         "Untitled 3")
        self.assertIn("already", ps.name_problem("Untitled 1", self.folder))
        self.assertEqual(ps.name_problem("Untitled 1", self.folder,
                                         current=os.path.join(
                                             self.folder, "Untitled 1.FCStd")),
                         "")
        self.assertIn("Type a name", ps.name_problem(" ", self.folder))
        self.assertEqual(ps.unique_name("Untitled 1", self.folder),
                         "Untitled 1 copy")


# ------------------------------------------------------------- R365 ids
class TestStoreIds(StoreCase):
    def test_r365_read_and_rekey_a_file(self):
        p = make_fcstd(os.path.join(self.folder, "a.FCStd"), uid="u-old")
        self.assertEqual(ps.read_file_ids(p),
                         ("u-old", "u-old", os.path.realpath(p)))
        q = os.path.join(self.folder, "b.FCStd")
        shutil.copy(p, q)
        old = ps.rekey_file(q, "u-new")
        self.assertEqual(old, "u-old")
        self.assertEqual(ps.read_file_ids(q),
                         ("u-new", "u-new", os.path.realpath(q)))
        self.assertEqual(ps.file_id(p), "u-old")          # original untouched
        with zipfile.ZipFile(q) as zf:                    # still a full file
            self.assertEqual(sorted(zf.namelist()),
                             ["Board.Shape.brp", "Document.xml",
                              "thumbnails/Thumbnail.png"])

    def test_r365_legacy_file_id_is_its_uid(self):
        p = make_fcstd(os.path.join(self.folder, "old.FCStd"), uid="u-leg",
                       pid="")
        self.assertEqual(ps.file_id(p), "u-leg")

    def test_r365_doc_id_and_key_of_a_stub_document(self):
        d = types.SimpleNamespace(Name="D", Uid="u-1")
        self.assertEqual(ps.doc_id(d), "u-1")
        self.assertEqual(ps.doc_key(d), "u-1")    # not stampable: unchanged
        d.AtechProjectId = "p-9"
        self.assertEqual(ps.doc_id(d), "p-9")
        self.assertIsNone(ps.doc_id(None))


# ----------------------------------------------------------- R366 chat
class TestStoreChat(StoreCase):
    def ws(self):
        ws = os.path.join(self.tmp, "agent", "chat-20260101-000000")
        os.makedirs(ws)
        with open(os.path.join(ws, "view-1.png"), "wb") as fh:
            fh.write(PNG)
        with open(os.path.join(ws, "intent.json"), "w") as fh:
            fh.write('{"product": "lamp"}')
        with open(os.path.join(ws, "model.py"), "w") as fh:
            fh.write("print('script')")
        return ws

    def transcript(self, ws):
        return {"entries": [
            {"kind": "bubble", "text": "make a lamp", "role": "user"},
            {"kind": "card", "name": "Build", "args": "model.py",
             "mono": True, "body": "ok", "status": "built",
             "status_kind": "ok", "tip": "", "caveat": "",
             "caveat_text": "", "info_text": ""},
            {"kind": "notice", "title": "Note", "body": "Body",
             "actions": [("Retry", print)], "detail": None,
             "tag": ("budget", None), "enabled": [True]},
            {"kind": "shot", "path": os.path.join(ws, "view-1.png"),
             "caption": "front"},
            {"kind": "weird", "x": 1}],
            "last_text": "make a lamp", "shots": ["/x"], "captions": {}}

    def test_r366_pack_append_read_unpack(self):
        ws = self.ws()
        p = make_fcstd(os.path.join(self.folder, "lamp.FCStd"))
        members = ps.pack_chat(self.transcript(ws), ws, "u-1")
        self.assertIn(ps.CHAT_JSON, members)
        self.assertNotIn(ps.CHAT_FILES + "model.py", members)
        json.dumps(json.loads(members[ps.CHAT_JSON]))      # plain JSON
        self.assertTrue(ps.append_chat(p, members))
        self.assertTrue(ps.append_chat(p, members))         # replaced, not doubled
        with zipfile.ZipFile(p) as zf:
            names = zf.namelist()
        self.assertEqual(names.count(ps.CHAT_JSON), 1)
        got = ps.read_chat(p)
        self.assertEqual(sorted(got["files"]), ["intent.json", "view-1.png"])
        kinds = [e["kind"] for e in got["transcript"]["entries"]]
        self.assertEqual(kinds, ["bubble", "card", "notice", "shot"])
        # Unpacked elsewhere (another computer): the shot follows, no
        # intent.json from a file this computer does not know.
        ws2 = os.path.join(self.tmp, "agent", "chat-new")
        kept = ps.unpack_chat(got, ws2, allow_intent=False)
        self.assertEqual(sorted(os.listdir(ws2)), ["view-1.png"])
        shot = kept["entries"][-1]
        self.assertEqual(shot["path"], os.path.join(ws2, "view-1.png"))
        notice = kept["entries"][2]
        self.assertEqual(notice["actions"], [])
        self.assertEqual(kept["last_text"], "make a lamp")
        ps.unpack_chat(got, ws2, allow_intent=True)
        self.assertTrue(os.path.isfile(os.path.join(ws2, "intent.json")))
        self.assertTrue(ps.strip_chat(p))
        self.assertIsNone(ps.read_chat(p))

    def test_r366_hostile_member_names_stay_in_the_folder(self):
        p = make_fcstd(os.path.join(self.folder, "evil.FCStd"))
        meta = {"v": 1, "transcript": {"entries": []}, "files": []}
        with zipfile.ZipFile(p, "a") as zf:
            zf.writestr(ps.CHAT_JSON, json.dumps(meta))
            zf.writestr(ps.CHAT_FILES + "../../escape.png", PNG)
            zf.writestr(ps.CHAT_FILES + "model.py", b"import os")
        got = ps.read_chat(p)
        self.assertEqual(sorted(got["files"]), ["escape.png"])
        ws = os.path.join(self.tmp, "w")
        ps.unpack_chat(got, ws)
        self.assertEqual(os.listdir(ws), ["escape.png"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escape.png")))

    def test_r366_size_caps(self):
        ws = self.ws()
        big = os.path.join(ws, "view-big.png")
        with open(big, "wb") as fh:
            fh.truncate(ps.MAX_EMBED_FILE + 1)
        members = ps.pack_chat({"entries": []}, ws)
        self.assertNotIn(ps.CHAT_FILES + "view-big.png", members)


# ------------------------------------------------- R370 recents, R372 Home
class TestStoreRecentsAndHome(StoreCase):
    def test_r370_realpath_dedupe_limit_and_missing(self):
        real = os.path.join(self.tmp, "real")
        link = os.path.join(self.tmp, "link")
        a = make_fcstd(os.path.join(real, "hub.FCStd"))
        os.symlink(real, link)
        ps.note_recent(os.path.join(link, "hub.FCStd"))
        ps.note_recent(a)
        gone = os.path.join(self.tmp, "gone.FCStd")
        out = ps.recent_files(extra=[os.path.join(link, "hub.FCStd"), gone])
        self.assertEqual(out, [os.path.realpath(a)])
        for i in range(14):
            ps.note_recent(make_fcstd(os.path.join(real, "p%d.FCStd" % i)))
        out = ps.recent_files(extra=[])
        self.assertEqual(len(out), 10)
        self.assertEqual(os.path.basename(out[0]), "p13.FCStd")
        ps.forget_recent(out[0])
        self.assertNotIn(out[0], ps.recent_files(extra=[]))

    def test_r370_sabotage_without_realpath_shows_one_file_twice(self):
        real = os.path.join(self.tmp, "real")
        link = os.path.join(self.tmp, "link")
        make_fcstd(os.path.join(real, "hub.FCStd"))
        os.symlink(real, link)
        saved = ps._real
        ps._real = lambda p: os.path.abspath(p) if p else ""
        try:
            out = ps.recent_files(extra=[os.path.join(link, "hub.FCStd"),
                                         os.path.join(real, "hub.FCStd")])
        finally:
            ps._real = saved
        self.assertEqual(len(out), 2, "sabotage did not break the dedupe")

    def test_r372_list_projects(self):
        make_fcstd(os.path.join(self.folder, "old.FCStd"), uid="u-old")
        time.sleep(0.01)
        make_fcstd(os.path.join(self.folder, "board.FCStd"), uid="u-b",
                   role=True, thumb=False)
        with open(os.path.join(self.folder, "old.20260101.FCBak"), "w") as fh:
            fh.write("x")
        os.utime(os.path.join(self.folder, "old.FCStd"), (1, 1))
        rows = ps.list_projects(self.folder)
        self.assertEqual([r["name"] for r in rows], ["board", "old"])
        self.assertTrue(rows[0]["has_electronics"])
        self.assertIsNone(rows[0]["thumbnail"])
        self.assertFalse(rows[1]["has_electronics"])
        self.assertEqual(rows[1]["thumbnail"], PNG)
        self.assertEqual(rows[1]["id"], "u-old")
        self.assertEqual(set(rows[0]), {"name", "path", "mtime", "id",
                                        "has_electronics", "thumbnail",
                                        "open"})

    def test_r372_hundred_projects_under_a_second(self):
        for i in range(100):
            make_fcstd(os.path.join(self.folder, "p%03d.FCStd" % i),
                       uid="u-%d" % i, role=(i % 3 == 0))
        ps._info_cache.clear()
        t = time.time()
        rows = ps.list_projects(self.folder)
        dt = time.time() - t
        print("\n  [R372] list_projects: 100 projects in %.0f ms" % (dt * 1000))
        self.assertEqual(len(rows), 100)
        self.assertLess(dt, 1.0)
        self.assertEqual(sum(r["has_electronics"] for r in rows), 34)


# --------------------------------------------- R371 sessions + migration
class TestStoreSessions(StoreCase):
    def chat(self, name):
        p = os.path.join(self.tmp, "agent", name)
        os.makedirs(p)
        return p

    def test_r371_prune(self):
        live = make_fcstd(os.path.join(self.folder, "live.FCStd"), uid="k1")
        other = make_fcstd(os.path.join(self.folder, "other.FCStd"),
                           uid="someone-else")
        now = time.time()
        data = {
            "k1": {"ws": self.chat("chat-1"), "path": live, "saved": now},
            "k2": {"ws": self.chat("chat-2"), "path": os.path.join(
                self.folder, "deleted.FCStd"), "saved": now},
            "k3": {"ws": self.chat("chat-3"), "path": other, "saved": now},
            "k4": {"ws": self.chat("chat-4"), "saved": now},
            "k5": {"ws": os.path.join(self.tmp, "gone"), "saved": now},
            "k6": {"ws": self.chat("chat-6"), "saved": now - 40 * 86400},
            "k7": {"ws": os.path.join(self.tmp, "gone"), "saved": 0},
        }
        ps.write_sessions(data)
        gone = ps.prune_sessions(open_ids={"k7"}, now=now)
        self.assertEqual(sorted(gone), ["k2", "k3", "k5", "k6"])
        self.assertEqual(sorted(ps.load_sessions()), ["k1", "k4", "k7"])
        # Folders are left to "Clear old chats".
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "agent",
                                                   "chat-2")))

    def test_r371_forget_removes_only_our_chat_folder(self):
        mine = self.chat("chat-9")
        theirs = os.path.join(self.tmp, "important")
        os.makedirs(theirs)
        ps.write_sessions({"a": {"ws": mine}, "b": {"ws": theirs}})
        self.assertTrue(ps.forget_project("a"))
        self.assertFalse(os.path.exists(mine))
        self.assertTrue(ps.forget_project("b"))
        self.assertTrue(os.path.isdir(theirs))     # not a chat-* of ours
        self.assertFalse(ps.forget_project("missing"))

    def test_r371_record_path(self):
        p = make_fcstd(os.path.join(self.folder, "x.FCStd"))
        ps.write_sessions({"k": {"ws": "/w", "sid": "s"}})
        ps.record_path("k", p)
        rec = ps.load_sessions()["k"]
        self.assertEqual((rec["ws"], rec["sid"], rec["path"]),
                         ("/w", "s", os.path.realpath(p)))
        self.assertEqual(ps.record_for_path(p), "k")
        self.assertIsNone(ps.record_for_path(os.path.join(self.tmp, "n")))

    def test_r365_migrate_sessions_v1_to_v2(self):
        ws = self.chat("chat-1")
        data = {
            "uid-a": {"ws": ws, "sid": "s", "prev": {"uid": "uid-a",
                                                     "names": ["B"]}},
            "uid-gone": {"ws": os.path.join(self.tmp, "nope"), "sid": None},
            "bad": "not a record",
        }
        ps.write_sessions(data)
        out = migrate.migrate_sessions(ps.sessions_path())
        self.assertEqual(out["migrated"], 1)
        self.assertEqual(sorted(out["dropped"]), ["bad", "uid-gone"])
        rec = ps.load_sessions()["uid-a"]
        self.assertEqual((rec["v"], rec["path"], rec["ws"], rec["sid"]),
                         (2, "", ws, "s"))
        again = migrate.migrate_sessions(ps.sessions_path())
        self.assertEqual(again, {"migrated": 0, "dropped": []})
        self.assertEqual(migrate.migrate_sessions(
            os.path.join(self.tmp, "none.json")),
            {"migrated": 0, "dropped": []})


# --------------------------------------------- R364 transient, R367 ops
class TestStoreFilesystem(StoreCase):
    def test_r364_cleanup_only_empty_transient_folders(self):
        root = os.path.join(self.tmp, "Cache")
        for i in range(5):
            os.makedirs(os.path.join(root, "Atech Atelier_Doc_%d" % i))
        with open(os.path.join(root, "Atech Atelier_Doc_0", "rec.xml"),
                  "w") as fh:
            fh.write("recovery")
        os.makedirs(os.path.join(root, "Other_Doc_1"))
        n = ps.cleanup_transient_dirs(root, prefix="Atech Atelier_Doc_",
                                      keep=[os.path.join(
                                          root, "Atech Atelier_Doc_4")])
        self.assertEqual(n, 3)
        self.assertEqual(sorted(os.listdir(root)),
                         ["Atech Atelier_Doc_0", "Atech Atelier_Doc_4",
                          "Other_Doc_1"])

    def test_r367_duplicate_rename_trash_closed_files(self):
        p = make_fcstd(os.path.join(self.folder, "lamp.FCStd"), uid="u-l")
        ps.note_recent(p)
        ws = os.path.join(self.tmp, "agent", "chat-1")
        os.makedirs(ws)
        ps.write_sessions({"u-l": {"ws": ws, "path": p}})
        d = ps.duplicate_project(p)
        self.assertEqual(os.path.basename(d), "lamp copy.FCStd")
        self.assertNotIn(ps.file_id(d), ("", "u-l"))
        self.assertEqual(ps.read_file_ids(d)[2], os.path.realpath(d))
        self.assertEqual(os.path.basename(ps.duplicate_project(p)),
                         "lamp copy 2.FCStd")
        with self.assertRaises(ps.ProjectError):
            ps.rename_project(p, "lamp copy")
        new = ps.rename_project(p, "desk lamp")
        self.assertFalse(os.path.exists(p))
        self.assertEqual(ps.load_sessions()["u-l"]["path"], new)
        self.assertIn(new, ps.recent_files(extra=[]))
        trashed = []
        pid = ps.trash_project(new, trash=lambda x: trashed.append(x) or
                               os.remove(x) or True)
        self.assertEqual((pid, trashed), ("u-l", [new]))
        self.assertNotIn("u-l", ps.load_sessions())
        self.assertFalse(os.path.exists(ws))
        self.assertNotIn(new, ps.recent_files(extra=[]))

    def test_r367_trash_failure_keeps_everything(self):
        p = make_fcstd(os.path.join(self.folder, "keep.FCStd"), uid="u-k")
        ps.write_sessions({"u-k": {"ws": "/w", "path": p}})
        with self.assertRaises(ps.ProjectError):
            ps.trash_project(p, trash=lambda x: False)
        self.assertTrue(os.path.isfile(p))
        self.assertIn("u-k", ps.load_sessions())

    def test_r367_reveal_in_finder(self):
        calls = []
        ps.reveal_in_finder("/p/x.FCStd", runner=calls.append)
        if sys.platform == "darwin":
            self.assertEqual(calls, [["open", "-R", "/p/x.FCStd"]])
        else:
            self.assertEqual(calls, [["xdg-open", "/p"]])


# ------------------------------------------------------- FreeCAD stub
class _Doc(object):
    def __init__(self, name, uid, file=""):
        self.Name = self.Label = name
        self.Uid = uid
        self.FileName = file
        self.Objects = []

    def getObject(self, name):                         # noqa: N802
        return None


def fc_stub(docs, active=None):
    mod = types.ModuleType("FreeCAD")
    mod.listDocuments = lambda: {d.Name: d for d in docs}
    mod.getDocument = lambda n: {d.Name: d for d in docs}[n]
    mod.ActiveDocument = active
    mod.Console = types.SimpleNamespace(PrintLog=lambda *a: None,
                                        PrintMessage=lambda *a: None)
    return mod


def gui_stub(modified):
    mod = types.ModuleType("FreeCADGui")
    mod.getDocument = lambda n: types.SimpleNamespace(
        Modified=modified.get(n, False))
    return mod


@unittest.skipIf(navbar is None, "PySide6 not installed")
class TestNavbar(StoreCase):
    def setUp(self):
        super().setUp()
        self.mod = {}
        self._gui = sys.modules.get("FreeCADGui")
        sys.modules["FreeCADGui"] = gui_stub(self.mod)

    def tearDown(self):
        sys.modules.pop("FreeCAD", None)
        if self._gui is None:
            sys.modules.pop("FreeCADGui", None)
        else:
            sys.modules["FreeCADGui"] = self._gui
        super().tearDown()

    def open(self, doc):
        sys.modules["FreeCAD"] = fc_stub([doc], doc)
        return doc

    def test_r362_project_actions_as_data(self):
        self.assertEqual(navbar.project_actions(False, False), [])
        acts = navbar.project_actions(True, False)
        self.assertEqual([k for k, _t, _o in acts],
                         ["save", "rename", "duplicate", "reveal", "export",
                          "trash"])
        self.assertEqual([o for _k, _t, o in acts],
                         [True, False, False, False, False, False])
        self.assertTrue(all(o for _k, _t, o in navbar.project_actions(True,
                                                                     True)))
        self.assertEqual(navbar.RECENT_MAX, 10)

    def test_r362_unsaved_dot_and_save_button(self):
        doc = self.open(_Doc("Lamp", "u-1", "/p/Lamp.FCStd"))
        pk = navbar.ProjectPicker()
        row = navbar.picker_row(pk)
        btn = row.save_button
        row.resize(300, 40)
        self.assertFalse(pk.modified())
        self.assertFalse(btn.isEnabled())
        self.assertEqual(btn.accessibleName(), "Save project")
        self.mod[doc.Name] = True
        pk.refresh()
        self.assertTrue(pk.modified())
        self.assertTrue(btn.isEnabled())
        self.assertEqual(pk.accessibleDescription(), "Unsaved changes")
        self.assertIn("unsaved", pk.toolTip())
        img = pk.grab().toImage()
        r = pk.dot_rect().toRect()
        c = img.pixelColor(r.center())
        want = QtGui.QColor(navbar.style.tokens()["warn"])
        self.assertLess(abs(c.red() - want.red()) + abs(c.green() -
                                                        want.green()), 40,
                        (c.name(), want.name()))
        self.mod[doc.Name] = False
        pk.refresh()
        self.assertFalse(pk.modified())
        # A document with no file yet can always be saved (gets a name).
        self.open(_Doc("Unnamed", "u-2", ""))
        btn.refresh()
        self.assertTrue(btn.isEnabled())

    def test_r362_sabotage_dot_never_painted(self):
        doc = self.open(_Doc("Lamp", "u-1", "/p/Lamp.FCStd"))
        self.mod[doc.Name] = True
        saved = navbar.projects_store.is_modified
        navbar.projects_store.is_modified = lambda d: False
        try:
            pk = navbar.ProjectPicker()
            pk.resize(260, 36)
            self.assertFalse(pk.modified(), "sabotage did not hide the dot")
        finally:
            navbar.projects_store.is_modified = saved

    def test_r361_new_project_flow_asks_again_on_a_taken_name(self):
        make_fcstd(os.path.join(self.folder, "Lamp.FCStd"))
        asked, warned, made = [], [], []
        answers = iter(["Lamp", "  Lamp 2 "])
        saved = ps.create_project
        ps.create_project = lambda n, f=None: made.append((n, f)) or "doc"
        try:
            got = navbar.new_project_flow(
                ask=lambda d: asked.append(d) or next(answers),
                warn=lambda t, x: warned.append(x), folder=self.folder)
        finally:
            ps.create_project = saved
        self.assertEqual(got, "doc")
        self.assertEqual(asked, ["Untitled 1", "Lamp"])
        self.assertIn("already", warned[0])
        self.assertEqual(made, [("  Lamp 2 ", self.folder)])
        self.assertIsNone(navbar.new_project_flow(
            ask=lambda d: None, folder=self.folder))

    def test_r367_picker_actions_call_the_store(self):
        doc = self.open(_Doc("Lamp", "u-1",
                             os.path.join(self.folder, "Lamp.FCStd")))
        pk = navbar.ProjectPicker()
        calls, warned = [], []
        pk.warn = lambda t, x: warned.append(x)
        pk.ask_name = lambda t, l, d: "Desk lamp"
        pk.confirm = lambda t, x, o: calls.append(("confirm", x)) or True
        pk.reveal = lambda p: calls.append(("reveal", p))
        saved = {k: getattr(ps, k) for k in ("rename_project",
                                             "trash_project")}
        ps.rename_project = lambda d, n: calls.append(("rename", n)) or "/new"
        ps.trash_project = lambda d: calls.append(("trash", d.Name)) or "u-1"
        try:
            self.assertEqual(pk.act("rename"), "/new")
            self.assertEqual(pk.act("trash"), "u-1")
            pk.act("reveal")
            ps.rename_project = lambda d, n: (_ for _ in ()).throw(
                ps.ProjectError("A project named X is already there."))
            self.assertIsNone(pk.act("rename"))
        finally:
            for k, v in saved.items():
                setattr(ps, k, v)
        self.assertEqual([c[0] for c in calls],
                         ["rename", "confirm", "trash", "reveal"])
        self.assertIn("Lamp", calls[1][1])
        self.assertEqual(warned, ["A project named X is already there."])
        # The menu lists the section with the current project's actions.
        pk._fill()
        names = [a.objectName() for a in pk.menu().actions()]
        for key, _t in navbar.PROJECT_ACTIONS:
            self.assertIn("project-" + key, names)
        save = [a for a in pk.menu().actions()
                if a.objectName() == "project-save"][0]
        self.assertEqual(save.shortcut(),
                         QtGui.QKeySequence(QtGui.QKeySequence.Save))
        del doc

    def test_r369_export_refuses_to_overwrite_the_project(self):
        p = make_fcstd(os.path.join(self.folder, "Lamp.FCStd"))
        self.open(_Doc("Lamp", "u-1", p))
        pk = navbar.ProjectPicker()
        warned = []
        pk.warn = lambda t, x: warned.append(x)
        pk.ask_save_path = lambda t, s: p
        self.assertIsNone(pk.act("export"))
        self.assertIn("must not replace", warned[0])


# --------------------------------------------------- panel lifecycle
try:
    import test_ws_chat_panel as twp
    from acadagent import panel
except Exception:                                      # noqa: BLE001
    twp = panel = None


@unittest.skipIf(twp is None or navbar is None, "panel tests unavailable")
class TestPanelLifecycle(twp.Case if twp is not None else unittest.TestCase):
    def doc(self, name, uid, file=""):
        d = twp._Doc(name, uid)
        d.FileName = file
        return d

    def test_r365_save_as_moves_the_chat_to_the_new_id(self):
        d = self.fc.add(self.doc("Lamp", "u-a"))
        st = self.p._state_for(d)
        st.prev = {"uid": "u-a", "names": ["B"]}
        self.p._remember(st)
        self.p._transcripts["u-a"] = {"entries": []}
        self.p._shown_key = "u-a"
        self.p._on_project_rekey("u-a", "u-b", d, "save_as")
        self.assertIs(self.p._docs.get("u-b"), st)
        self.assertNotIn("u-a", self.p._docs)
        self.assertEqual((st.key, st.prev["uid"]), ("u-b", "u-b"))
        self.assertEqual(self.p._shown_key, "u-b")
        self.assertIn("u-b", self.p._transcripts)
        recs = panel.load_sessions()
        self.assertIn("u-b", recs)
        self.assertNotIn("u-a", recs)
        # A copy opened beside its original never takes the original's chat.
        other = self.fc.add(self.doc("Copy", "u-c"))
        self.p._on_project_rekey("u-b", "u-c", other, "duplicate_open")
        self.assertIs(self.p._docs.get("u-b"), st)

    def test_r365_sabotage_without_the_listener_the_chat_is_lost(self):
        d = self.fc.add(self.doc("Lamp", "u-a"))
        st = self.p._state_for(d)
        saved = self.p._on_project_rekey
        self.p._on_project_rekey = lambda *a: None
        try:
            self.p._on_project_rekey("u-a", "u-b", d, "save_as")
        finally:
            self.p._on_project_rekey = saved
        self.assertIsNot(self.p._docs.get("u-b"), st,
                         "sabotage still moved the chat")

    def file_with_chat(self, name, text):
        p = make_fcstd(os.path.join(self.tmp, "proj", name + ".FCStd"))
        ws = os.path.join(self.tmp, "srcws")
        os.makedirs(ws, exist_ok=True)
        shot = os.path.join(ws, "view-1.png")
        with open(shot, "wb") as fh:
            fh.write(PNG)
        ps.append_chat(p, ps.pack_chat({"entries": [
            {"kind": "bubble", "text": text, "role": "user"},
            {"kind": "bubble", "text": "Built it.", "role": "assistant"},
            {"kind": "shot", "path": shot, "caption": "front"}]}, ws, "u-f"))
        return p

    def bubbles(self):
        return [w.raw_text for w in self.p.findChildren(panel.Bubble)
                if not w.isHidden()]

    def test_r366_reopened_file_shows_its_chat(self):
        p = self.file_with_chat("lamp", "make a lamp")
        d = self.fc.add(self.doc("Lamp", "u-f", p))
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.bubbles(), ["make a lamp", "Built it."])
        shots = [w for w in self.p.findChildren(panel.Shot)
                 if not w.isHidden()]
        st = self.p._docs["u-f"]
        self.assertEqual(len(shots), 1)
        self.assertTrue(os.path.isfile(os.path.join(st.ws, "view-1.png")))
        # Saving again carries the chat on screen.
        got = self.p._chat_for_file(d)
        self.assertEqual([e["text"] for e in got["transcript"]["entries"]
                          if e["kind"] == "bubble"],
                         ["make a lamp", "Built it."])
        self.assertEqual(got["ws"], st.ws)

    def test_r366_sabotage_without_seeding_the_chat_is_empty(self):
        p = self.file_with_chat("lamp", "make a lamp")
        self.fc.add(self.doc("Lamp", "u-f", p))
        self.p._seed_transcript = lambda doc, key: False
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.bubbles(), [], "sabotage still showed it")

    def test_r366_unread_file_chat_is_never_overwritten(self):
        p = self.file_with_chat("other", "keep me")
        d = self.fc.add(self.doc("Other", "u-o", p), active=False)
        self.assertIsNone(self.p._chat_for_file(d))

    def test_r366_two_documents_keep_their_own_file_chats(self):
        a = self.file_with_chat("a", "chat of a")
        b = self.file_with_chat("b", "chat of b")
        da = self.fc.add(self.doc("A", "u-a", a))
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.bubbles()[0], "chat of a")
        self.fc.add(self.doc("B", "u-b", b))
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.bubbles()[0], "chat of b")
        self.fc.mod.ActiveDocument = da
        self.p.refresh_doc_pill(force=True)
        self.assertEqual(self.bubbles()[0], "chat of a")

    # R368 quit guard
    def guarded(self, answer):
        win = QtWidgets.QWidget()
        win.resize(200, 100)
        win.show()
        guard = self.p.install_quit_guard(win)
        self.p.ask_quit = lambda: answer
        saved = []
        self.p.save_partial = lambda: saved.append(1)
        return win, guard, saved

    def test_r368_quit_during_a_turn_asks(self):
        win, guard, saved = self.guarded(False)
        self.p._busy = True
        try:
            self.assertFalse(win.close())
            self.assertTrue(win.isVisible())
            self.assertEqual((guard.asked, saved), (1, []))
            self.p.ask_quit = lambda: True
            self.assertTrue(win.close())
            self.assertEqual((guard.asked, saved), (2, [1]))
        finally:
            self.p._busy = False

    def test_r368_idle_quit_does_not_ask(self):
        win, guard, saved = self.guarded(False)
        self.assertTrue(win.close())
        self.assertEqual((guard.asked, saved), (0, []))

    def test_r368_sabotage_unguarded_window_closes_mid_turn(self):
        win = QtWidgets.QWidget()
        win.show()
        self.p._busy = True
        try:
            self.assertTrue(win.close(), "an unguarded window refused")
        finally:
            self.p._busy = False

    def test_r368_save_partial_stops_and_records(self):
        d = self.fc.add(self.doc("Lamp", "u-q"))
        st = self.p._state_for(d)
        st.sid = "sid-q"
        saved = ps.save_open_projects
        ps.save_open_projects = lambda: ["Lamp"]
        try:
            self.assertEqual(self.p.save_partial(), ["Lamp"])
        finally:
            ps.save_open_projects = saved
        self.assertEqual(panel.load_sessions()["u-q"]["sid"], "sid-q")


# --------------------------------------------------- real FreeCAD
def _run_fc(env_extra, timeout=300):
    tmp = os.path.realpath(tempfile.mkdtemp(prefix="projfc-"))
    env = dict(os.environ, ATECH_PROJ_DIR=tmp,
               ATECH_ARTIFACTS=os.path.join(REPO, "models"))
    env.update(env_extra)
    p = subprocess.run([FREECADCMD, os.path.join(HERE, "fc_projects_store.py")],
                       env=env, capture_output=True, text=True,
                       timeout=timeout)
    return p, tmp


@unittest.skipUnless(os.path.isfile(FREECADCMD), "built app not found")
class TestFreeCAD(unittest.TestCase):
    def result(self, out):
        lines = [ln for ln in out.splitlines() if ln.startswith(("PASS",
                                                                "FAIL",
                                                                "ATECH_PROJ"))]
        return lines, [ln for ln in lines if ln.startswith("ATECH_PROJ")]

    def test_r360_r372_real_documents(self):
        p, tmp = _run_fc({})
        lines, end = self.result(p.stdout)
        try:
            self.assertEqual(end, ["ATECH_PROJ_TESTS=0"],
                             "\n".join(lines) + p.stderr[-2000:])
            self.assertGreater(len(lines), 50)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sabotage_each_feature_fails(self):
        for sab, must in (("rekey", "FAIL save as: document has a new id"),
                          ("chat", "FAIL chat in file"),
                          ("strip", "FAIL export: scripts removed")):
            p, tmp = _run_fc({"ATECH_PROJ_SABOTAGE": sab})
            try:
                lines, end = self.result(p.stdout)
                self.assertNotEqual(end, ["ATECH_PROJ_TESTS=0"], sab)
                self.assertTrue(any(ln.startswith(must) for ln in lines),
                                (sab, lines))
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    def test_r363_autosave_survives_kill_9(self):
        p, tmp = _run_fc({"ATECH_PROJ_MODE": "autosave_kill"})
        try:
            self.assertEqual(p.returncode, -signal.SIGKILL, p.stdout[-500:])
            self.assertIn("AUTOSAVED ['Crash_test']", p.stdout)
            path = os.path.join(tmp, "Atech Projects", "Crash test.FCStd")
            with zipfile.ZipFile(path) as zf:
                xml = zf.read("Document.xml")
            self.assertIn(b'name="Box"', xml)            # saved by the tick
            self.assertNotIn(b'name="NotSaved"', xml)    # after it: lost
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
