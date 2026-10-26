"""projects_store inside freecadcmd (R360-R372) - real documents, real
saves. Run by test_projects_store.py:

    <freecadcmd> fc_projects_store.py

Environment:
  ATECH_PROJ_DIR        a fresh scratch folder (required)
  ATECH_PROJ_MODE       "checks" (default) or "autosave_kill": create a
                        project, change it, let the autosave tick save it,
                        then SIGKILL this process (the crash test).
  ATECH_PROJ_SABOTAGE   breaks one feature so the suite must fail:
                          rekey     re-keying does nothing (copies keep the id)
                          chat      no chat is written into the file
                          strip     export keeps the agent scripts

Prints PASS/FAIL lines and ends with ATECH_PROJ_TESTS=<failures>.
"""
import json
import os
import shutil
import signal
import sys
import traceback
import types
import zipfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import FreeCAD as App  # noqa: E402

from acadagent import build, projects_store as ps  # noqa: E402

TMP = os.environ["ATECH_PROJ_DIR"]
FOLDER = os.path.join(TMP, "Atech Projects")
os.makedirs(FOLDER, exist_ok=True)
ps.STATE_PATH = os.path.join(TMP, "projects.json")
ps.SESSIONS_PATH = os.path.join(TMP, "agent", "sessions.json")
os.makedirs(os.path.dirname(ps.SESSIONS_PATH), exist_ok=True)
build._trust_path = lambda: os.path.join(TMP, "trusted_builds.json")
os.environ["ATECH_PROJECTS_DIR"] = FOLDER

SAB = os.environ.get("ATECH_PROJ_SABOTAGE", "")
if SAB == "rekey":
    ps.rekey = lambda doc, reason, new=None, notify=True: (ps.doc_id(doc),
                                                           ps.doc_id(doc))
elif SAB == "chat":
    ps.append_chat = lambda path, members: False
elif SAB == "strip":
    build.strip_scripts = lambda doc: 0

# A stand-in FreeCADGui: only the Modified flag the autosave reads.
_MOD = {}
gui = types.ModuleType("FreeCADGui")
gui.getDocument = lambda n: types.SimpleNamespace(
    Modified=_MOD.get(n, False))
sys.modules["FreeCADGui"] = gui

FAILS = []


def check(name, ok, detail=""):
    print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                       (": " + str(detail)) if not ok and detail else ""))
    if not ok:
        FAILS.append(name)


def fid(path):
    return ps.file_id(path)


def members(path):
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def box(doc, name="Box"):
    o = doc.addObject("Part::Box", name)
    doc.recompute()
    return o


def autosave_kill():
    ps.install_observer()
    doc = ps.create_project("Crash test")
    box(doc)
    _MOD[doc.Name] = True
    saved = ps.autosave_tick()
    print("AUTOSAVED %s" % saved)
    sys.stdout.flush()
    box(doc, "NotSaved")            # changed after the tick: lost on kill
    os.kill(os.getpid(), signal.SIGKILL)


def run():
    ps.install_observer()
    events = []
    ps.add_rekey_listener(lambda o, n, d, r: events.append((o, n, d.Name, r)))

    # R361 + R360: a named project is a file in the projects folder at once.
    check("default name", ps.default_name(FOLDER) == "Untitled 1",
          ps.default_name(FOLDER))
    doc = ps.create_project("Desk Lamp")
    path = os.path.join(FOLDER, "Desk Lamp.FCStd")
    check("new project saved at once", os.path.isfile(path), path)
    check("new project label", doc.Label == "Desk Lamp", doc.Label)
    check("id stamped and equal to Uid",
          doc.AtechProjectId and doc.AtechProjectId == doc.Uid,
          (doc.AtechProjectId, doc.Uid))
    check("file carries the id", fid(path) == doc.AtechProjectId,
          (fid(path), doc.AtechProjectId))
    check("recent first", ps.recent_files()[:1] == [os.path.realpath(path)],
          ps.recent_files())
    ps.create_project("Untitled 1")
    check("default name skips taken",
          ps.default_name(FOLDER) == "Untitled 2", ps.default_name(FOLDER))
    try:
        ps.create_project("Desk Lamp")
        check("same name refused", False)
    except ps.ProjectError as exc:
        check("same name refused", "already" in str(exc), exc)

    # R366: the chat goes into the file, never model.py.
    ws = os.path.join(TMP, "agent", "chat-20260101-000000")
    os.makedirs(ws, exist_ok=True)
    shot = os.path.join(ws, "view-1.png")
    with open(shot, "wb") as fh:
        fh.write(b"\x89PNG fake")
    with open(os.path.join(ws, "intent.json"), "w") as fh:
        fh.write('{"product": "lamp"}')
    with open(os.path.join(ws, "model.py"), "w") as fh:
        fh.write("print('agent script')\n")
    chats = {}

    class Provider(object):
        def get(self, d):
            return chats.get(ps.doc_id(d))
    prov = Provider()
    ps.set_chat_provider(prov.get)
    chats[doc.AtechProjectId] = {
        "transcript": {"entries": [
            {"kind": "bubble", "text": "make a lamp", "role": "user"},
            {"kind": "notice", "title": "T", "body": "B",
             "actions": [("Retry", print)], "detail": None},
            {"kind": "shot", "path": shot, "caption": "front"}],
            "last_text": "make a lamp"},
        "ws": ws}
    box(doc)
    doc.save()
    got = ps.read_chat(path)
    check("chat in file", got is not None and
          [e.get("text") for e in got["transcript"]["entries"]
           if e["kind"] == "bubble"] == ["make a lamp"], got)
    names = sorted((got or {}).get("files") or {})
    check("views and intent in file, no model.py",
          names == ["intent.json", "view-1.png"], names)
    check("chat names the id", got and got["id"] == doc.AtechProjectId,
          got and got["id"])
    # A save with nothing newer from the panel keeps the file's chat.
    chats.clear()
    doc.save()
    got2 = ps.read_chat(path)
    check("chat survives a save without the panel",
          got2 is not None and len(got2["transcript"]["entries"]) == 3,
          got2 and got2["transcript"])
    # Unpacked into a new folder: shots point there; intent only if local.
    ws2 = os.path.join(TMP, "agent", "chat-restored")
    kept = ps.unpack_chat(got2, ws2, allow_intent=False)
    check("unpack: shot path in the new folder",
          kept and kept["entries"][-1]["path"] == os.path.join(ws2,
                                                               "view-1.png")
          and os.path.isfile(os.path.join(ws2, "view-1.png")), kept)
    check("unpack: no intent from elsewhere, never model.py",
          not os.path.exists(os.path.join(ws2, "intent.json")) and
          not os.path.exists(os.path.join(ws2, "model.py")),
          os.listdir(ws2))
    # App can still open the file with the extra members.
    App.closeDocument(doc.Name)
    d = App.openDocument(path)
    check("file with chat opens", len(d.Objects) == 1, len(d.Objects))
    check("reopen keeps the id", d.AtechProjectId == fid(path))
    doc = d
    first_id = doc.AtechProjectId
    ps.record_path(first_id, path)

    # R365: Save As -> the open document is a new project.
    events[:] = []
    path_b = os.path.join(FOLDER, "Desk Lamp v2.FCStd")
    doc.saveAs(path_b)
    check("save as: document has a new id", doc.AtechProjectId != first_id,
          doc.AtechProjectId)
    check("save as: Uid follows", doc.Uid == doc.AtechProjectId)
    check("save as: old file keeps its id", fid(path) == first_id,
          fid(path))
    check("save as: new file has the new id",
          fid(path_b) == doc.AtechProjectId, fid(path_b))
    check("save as: listener told", [e[3] for e in events] == ["save_as"],
          events)
    check("save as: chat carried", ps.read_chat(path_b) is not None)

    # Save a Copy -> the copy is new, the document stays itself.
    b_id = doc.AtechProjectId
    path_c = os.path.join(FOLDER, "Lamp copy.FCStd")
    doc.saveCopy(path_c)
    check("save a copy: document keeps id", doc.AtechProjectId == b_id and
          doc.Uid == b_id, (doc.AtechProjectId, b_id))
    check("save a copy: copy has its own id",
          fid(path_c) not in ("", b_id), fid(path_c))
    check("save a copy: copy knows its place",
          ps.read_file_ids(path_c)[2] == os.path.realpath(path_c),
          ps.read_file_ids(path_c))
    check("save a copy: document still at its file",
          os.path.realpath(doc.AtechProjectFile) == os.path.realpath(path_b),
          doc.AtechProjectFile)

    # A Finder copy opened beside its original.
    path_f = os.path.join(FOLDER, "Lamp finder copy.FCStd")
    shutil.copy(path_b, path_f)
    f = App.openDocument(path_f)
    check("finder copy beside original: new id",
          f.AtechProjectId != b_id and f.Uid == f.AtechProjectId,
          (f.AtechProjectId, b_id))
    check("original keeps id", doc.AtechProjectId == b_id)
    App.closeDocument(f.Name)
    # A Finder copy opened alone, the original still in place.
    App.closeDocument(doc.Name)
    path_g = os.path.join(FOLDER, "Lamp second copy.FCStd")
    shutil.copy(path_b, path_g)
    g = App.openDocument(path_g)
    check("finder copy alone: new id", g.AtechProjectId != b_id,
          g.AtechProjectId)
    App.closeDocument(g.Name)
    # ... and the same copy opened again keeps the id it was given.
    g_id = ps.record_for_path(path_g)
    g = App.openDocument(path_g)
    check("copy reopened before saving: same new id",
          g_id and g.AtechProjectId == g_id, (g.AtechProjectId, g_id))
    App.closeDocument(g.Name)
    # A moved file (original gone) keeps its id.
    path_m = os.path.join(FOLDER, "Moved.FCStd")
    shutil.move(path_c, path_m)
    c_id = fid(path_m)
    m = App.openDocument(path_m)
    check("moved file keeps its id", m.AtechProjectId == c_id,
          (m.AtechProjectId, c_id))
    App.closeDocument(m.Name)

    # R367: duplicate (open and closed), rename, trash.
    doc = App.openDocument(path_b)
    dup = ps.duplicate_project(doc)
    check("duplicate open: file beside",
          os.path.basename(dup) == "Desk Lamp v2 copy.FCStd", dup)
    check("duplicate open: own id", fid(dup) not in ("", b_id), fid(dup))
    check("duplicate open: chat copied", ps.read_chat(dup) is not None)
    dup2 = ps.duplicate_project(path)
    check("duplicate closed: own id",
          fid(dup2) not in ("", first_id), (fid(dup2), first_id))
    d2 = App.openDocument(dup2)
    check("duplicate closed: opens with that id",
          d2.AtechProjectId == fid(dup2) and d2.Uid == fid(dup2),
          (d2.AtechProjectId, d2.Uid, fid(dup2)))
    App.closeDocument(d2.Name)
    new = ps.rename_project(doc, "Bedside Lamp")
    check("rename open: new file, old gone",
          os.path.isfile(new) and not os.path.exists(path_b), new)
    check("rename open: id kept", doc.AtechProjectId == b_id and
          fid(new) == b_id, (doc.AtechProjectId, fid(new)))
    check("rename open: label", doc.Label == "Bedside Lamp", doc.Label)
    check("rename: recents follow",
          os.path.realpath(new) in ps.recent_files() and
          os.path.realpath(path_b) not in ps.recent_files(),
          ps.recent_files())
    new2 = ps.rename_project(dup2, "Closed rename")
    check("rename closed", os.path.isfile(new2) and
          not os.path.exists(dup2), new2)
    try:
        ps.rename_project(new2, "Bedside Lamp")
        check("rename onto another project refused", False)
    except ps.ProjectError:
        check("rename onto another project refused", True)

    # R369: export for sharing.
    o = box(doc, "Agent")
    build._ensure_props(o)
    o.AtechAgentBuilt = True
    o.AtechAgentScript = "print('secret design script')"
    doc.save()
    share = os.path.join(TMP, "share", "Lamp (shared).FCStd")
    os.makedirs(os.path.dirname(share), exist_ok=True)
    n = ps.export_for_sharing(doc, share)
    check("export: scripts removed", n >= 1, n)
    with zipfile.ZipFile(share) as zf:
        xml = zf.read("Document.xml").decode("utf-8", "replace")
    check("export: no script text in the copy",
          "secret design script" not in xml)
    check("export: no chat in the copy",
          not any(m_.startswith("AtechChat/") for m_ in members(share)),
          members(share))
    check("export: own id", fid(share) not in ("", doc.AtechProjectId),
          fid(share))
    check("export: original untouched",
          doc.getObject("Agent").AtechAgentScript ==
          "print('secret design script')")
    check("export: only one document open of it",
          sum(1 for nm in App.listDocuments()
              if App.getDocument(nm).FileName == share) == 0)

    # Trash: file to the trash, record and chat folder gone.
    trash_dir = os.path.join(TMP, "Trash")
    os.makedirs(trash_dir, exist_ok=True)
    chat_ws = os.path.join(TMP, "agent", "chat-20260101-111111")
    os.makedirs(chat_ws)
    data = ps.load_sessions()
    data[doc.AtechProjectId] = {"ws": chat_ws, "path": os.path.realpath(new)}
    ps.write_sessions(data)
    pid = ps.trash_project(
        doc, trash=lambda p: shutil.move(p, trash_dir) or True)
    check("trash: file moved",
          not os.path.exists(new) and
          os.path.isfile(os.path.join(trash_dir, "Bedside Lamp.FCStd")))
    check("trash: record and chat folder gone",
          pid not in ps.load_sessions() and not os.path.exists(chat_ws))
    check("trash: not in recents",
          os.path.realpath(new) not in ps.recent_files())

    # R362/R363: autosave saves only modified projects with a file.
    d = ps.create_project("Autosaved")
    box(d)
    _MOD.clear()
    check("autosave skips unmodified", ps.autosave_tick() == [])
    _MOD[d.Name] = True
    check("autosave saves modified", ps.autosave_tick() == [d.Name])
    with zipfile.ZipFile(d.FileName) as zf:
        check("autosave wrote the box",
              b'name="Box"' in zf.read("Document.xml"))

    # R372: the Home grid's data.
    rows = ps.list_projects(FOLDER)
    names = [r["name"] for r in rows]
    check("list_projects: newest first",
          rows == sorted(rows, key=lambda r: -r["mtime"]), names)
    check("list_projects: fields",
          all(set(r) >= {"name", "path", "mtime", "thumbnail",
                         "has_electronics", "id"} for r in rows), rows[:1])
    check("list_projects: no backups",
          not any(r["path"].endswith(".FCBak") for r in rows))

    print("ATECH_PROJ_TESTS=%d" % len(FAILS))


try:
    if os.environ.get("ATECH_PROJ_MODE") == "autosave_kill":
        autosave_kill()
    else:
        run()
except Exception:                                      # noqa: BLE001
    traceback.print_exc()
    print("ATECH_PROJ_TESTS=crash")
sys.stdout.flush()
