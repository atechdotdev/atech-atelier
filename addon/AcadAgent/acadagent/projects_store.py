"""projects_store - Atech projects as files: where they live, who they are,
and the chat that travels with them (PRD "Projects" 1-9, R360-R372).

A project is one .FCStd file. This module owns everything about that file
that FreeCAD does not:

  R360 the projects folder      ~/Documents/Atech Projects/ unless the user
                                chose another (projects_dir / set_projects_dir;
                                ATECH_PROJECTS_DIR overrides, for tests).
  R361 a named new project      create_project(name) makes the document and
                                saves it into that folder at once, so a
                                project is never an invisible "Unnamed".
  R362 unsaved state            is_modified(doc) (FreeCAD's Gui flag).
  R363 autosave                 Autosaver: every 60 s, every open project
                                that has a file and unsaved changes; and
                                request_save(doc) after an agent build.
  R364 recovery + transient     ensure_recovery_on() turns FreeCAD's own
                                crash recovery on unless the user turned it
                                off; cleanup_transient_dirs() removes the
                                EMPTY "<ExeName>_Doc_*" folders killed runs
                                leave in the cache.
  R365 one id per file          AtechProjectId, a document property, is the
                                project's identity and the chat's key. It is
                                kept equal to doc.Uid, so build.py (which
                                finds a chat's document by Uid) and the trust
                                store follow it too. FreeCAD copies Uid into
                                Save As, Save a Copy and Finder copies; this
                                module gives each of those a new id:
                                  Save As to a new file   the open document
                                                          gets a new id (the
                                                          old file keeps its
                                                          own); the chat moves
                                                          with the document
                                  Save a Copy             the copy is written
                                                          with a new id
                                  Duplicate               ditto
                                  opening a file whose id is in use by an open
                                  document, or whose id belongs to a file that
                                  is still at its recorded place (a Finder
                                  copy)                   the newcomer gets a
                                                          new id
                                AtechProjectFile records where the file was
                                last saved, which is how a copy is told from a
                                move.
  R366 the chat in the file     On every save the chat transcript, intent.json
                                and the captured views are appended to the
                                .FCStd as extra zip members (AtechChat/...).
                                FreeCAD ignores members it does not know and
                                rewrites the zip on each save, so they are
                                appended again after each save (and carried
                                over from the file on disk when the chat panel
                                has nothing newer). read_doc_chat/unpack_chat
                                bring them back on open. model.py is never
                                restored from the file: an agent script is
                                only ever loaded through build.adopt and its
                                trust check (R11).
  R367 rename / duplicate / delete (to the Trash) / reveal in Finder.
  R369 export for sharing        a copy with every agent script emptied
                                (build.strip_scripts), no chat, a new id.
  R370 recents                  up to 10, deduped by realpath, existing only.
  R371 orphan sessions          prune_sessions() drops sessions.json records
                                whose project file is gone.
  R372 list_projects()          the Home grid's data (name, path, mtime,
                                thumbnail bytes, has_electronics).

Never raises out of an observer slot: a failed bookkeeping step costs a
chat its history, never the user's save.
"""
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import weakref
import zipfile

PROJECT_PROP = "AtechProjectId"
FILE_PROP = "AtechProjectFile"
SUFFIX = ".FCStd"
CHAT_DIR = "AtechChat/"
CHAT_JSON = CHAT_DIR + "chat.json"
CHAT_FILES = CHAT_DIR + "files/"
CHAT_VERSION = 1
#: What of a chat workspace travels in the file. Captured views and the
#: check render are images; intent.json is the design brief. Never model.py.
CHAT_FILE_EXT = (".png", ".jpg", ".jpeg")
INTENT = "intent.json"
#: Caps: a project file must not balloon because of captures.
MAX_EMBED_FILE = 8 * 1024 * 1024
MAX_EMBED_TOTAL = 24 * 1024 * 1024
MAX_UNPACK_TOTAL = 64 * 1024 * 1024
RECENT_MAX = 10
AUTOSAVE_MS = 60 * 1000
DEFAULT_FOLDER_NAME = "Atech Projects"
NAME_MAX = 80
RECENT_PARAM = "User parameter:BaseApp/Preferences/RecentFiles"
DOC_PARAM = "User parameter:BaseApp/Preferences/Document"

#: Tests point the state file elsewhere.
STATE_PATH = None
SESSIONS_PATH = None


class ProjectError(Exception):
    """A project operation that cannot be done; the message is for users."""


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[AcadAgent projects] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def _fc():
    try:
        import FreeCAD
        return FreeCAD
    except Exception:                                  # noqa: BLE001
        return None


def _real(path):
    return os.path.realpath(os.path.expanduser(path)) if path else ""


# ------------------------------------------------------------ state file
def _data_root():
    try:
        from . import settings as cfgmod
        return os.path.dirname(cfgmod.chat_workspace_root())
    except Exception:                                  # noqa: BLE001
        from . import fallback_data_root
        return fallback_data_root()


def state_path():
    return STATE_PATH or os.path.join(_data_root(), "AcadAgent",
                                      "projects.json")


def _load_state():
    try:
        with open(state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(data):
    path = state_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        _log("state not saved: %r" % (exc,))
        return False


# ------------------------------------------------------- projects folder
def default_projects_dir():
    return os.path.join(os.path.expanduser("~"), "Documents",
                        DEFAULT_FOLDER_NAME)


def projects_dir():
    """R360: where new projects go."""
    env = os.environ.get("ATECH_PROJECTS_DIR")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    folder = _load_state().get("folder")
    if isinstance(folder, str) and folder.strip():
        return os.path.abspath(os.path.expanduser(folder))
    return default_projects_dir()


def set_projects_dir(path):
    """The Settings page's "Projects folder". None/"" resets the default."""
    data = _load_state()
    if path:
        data["folder"] = os.path.abspath(os.path.expanduser(path))
    else:
        data.pop("folder", None)
    return _save_state(data)


def ensure_projects_dir():
    folder = projects_dir()
    os.makedirs(folder, exist_ok=True)
    return folder


# ----------------------------------------------------------------- names
_BAD_NAME = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')


def clean_name(name):
    """A project name as a file stem: no path separators or control
    characters, single spaces, no leading dots, at most NAME_MAX
    characters. "" when nothing usable is left."""
    s = str(name or "").strip()
    if s.lower().endswith(SUFFIX.lower()):
        s = s[:-len(SUFFIX)]
    s = _BAD_NAME.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip().lstrip(".").strip()
    return s[:NAME_MAX].rstrip()


def name_problem(name, folder=None, current=None):
    """Why `name` cannot be used in `folder` (a sentence), or ""."""
    n = clean_name(name)
    if not n:
        return "Type a name for the project."
    folder = folder or projects_dir()
    path = os.path.join(folder, n + SUFFIX)
    if os.path.exists(path) and not (current and _same(path, current)):
        return "A project named “%s” is already in that folder." % n
    return ""


def _same(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return _real(a) == _real(b)


def default_name(folder=None, taken=()):
    """R361: "Untitled N", the first N free in `folder` and among open
    documents' labels."""
    folder = folder or projects_dir()
    labels = set(taken)
    fc = _fc()
    try:
        for d in (fc.listDocuments().values() if fc else ()):
            labels.add(getattr(d, "Label", ""))
    except Exception:                                  # noqa: BLE001
        pass
    n = 1
    while True:
        cand = "Untitled %d" % n
        if cand not in labels and not os.path.exists(
                os.path.join(folder, cand + SUFFIX)):
            return cand
        n += 1


def unique_name(stem, folder, suffix=" copy"):
    """`stem copy`, `stem copy 2`, ... free in `folder`."""
    base = clean_name(stem + suffix) or "Project copy"
    cand, n = base, 1
    while os.path.exists(os.path.join(folder, cand + SUFFIX)):
        n += 1
        cand = "%s %d" % (base, n)
    return cand


# -------------------------------------------------------------- identity
def new_id():
    return str(uuid.uuid4())


def _stampable(doc):
    return doc is not None and hasattr(doc, "addProperty") and \
        hasattr(doc, "PropertiesList")


def doc_id(doc):
    """The project id of an open document, read only: AtechProjectId when
    stamped, else its Uid (what every chat was keyed by before R365), else
    its Name."""
    if doc is None:
        return None
    try:
        pid = getattr(doc, PROJECT_PROP, "")
    except Exception:                                  # noqa: BLE001
        pid = ""
    if isinstance(pid, str) and pid:
        return pid
    return getattr(doc, "Uid", None) or getattr(doc, "Name", None)


def _set_prop(doc, name, value):
    if name not in doc.PropertiesList:
        doc.addProperty("App::PropertyString", name, "Atech",
                        "Atech project bookkeeping")
        try:
            doc.setPropertyStatus(name, ["Hidden"])
        except Exception:                              # noqa: BLE001
            pass
    if getattr(doc, name, None) != value:
        setattr(doc, name, value)


def _set_id(doc, pid):
    _set_prop(doc, PROJECT_PROP, pid)
    try:
        if str(doc.Uid) != pid:
            doc.Uid = pid
    except Exception as exc:                           # noqa: BLE001
        _log("Uid of %s not set: %r" % (getattr(doc, "Name", "?"), exc))


def _open_docs():
    fc = _fc()
    if fc is None:
        return []
    try:
        return [fc.getDocument(n) for n in fc.listDocuments()]
    except Exception:                                  # noqa: BLE001
        return []


def _file_of(doc):
    try:
        return getattr(doc, "FileName", "") or ""
    except Exception:                                  # noqa: BLE001
        return ""


def open_doc_for(path):
    """The open document saved at `path`, or None."""
    if not path:
        return None
    for d in _open_docs():
        f = _file_of(d)
        if f and _same(f, path):
            return d
    return None


_listeners = []


def add_rekey_listener(fn):
    """fn(old_id, new_id, doc, reason) after a document got a new id.
    reason: "save_as", "duplicate_open", "copied_file". Held weakly when a
    bound method (the chat panel)."""
    try:
        ref = weakref.WeakMethod(fn)
    except TypeError:
        ref = (lambda f=fn: f)
    _listeners.append(ref)


def _notify(old, new, doc, reason):
    for ref in list(_listeners):
        fn = ref()
        if fn is None:
            _listeners.remove(ref)
            continue
        try:
            fn(old, new, doc, reason)
        except Exception as exc:                       # noqa: BLE001
            _log("rekey listener: %r" % (exc,))


_needs_save = set()          # doc Names re-keyed since their last save


def rekey(doc, reason, new=None, notify=True):
    """Give `doc` a new project id (and Uid). The trust records of the old
    id are copied: the same scripts the user accepted in this file stay
    accepted under the new id (they are still checked by sha, R11).
    Returns (old, new)."""
    old = doc_id(doc)
    new = new or new_id()
    _set_id(doc, new)
    copy_trust(old, new)
    if notify:
        _needs_save.add(getattr(doc, "Name", ""))
        _mark_modified(doc)
        _notify(old, new, doc, reason)
    _log("%s: new project id %s (was %s, %s)"
         % (getattr(doc, "Name", "?"), new, old, reason))
    return old, new


def _owner_of(pid, docs):
    """Of several open documents sharing `pid`, the one that keeps it: the
    one at the path sessions.json recorded for it, else one still at the
    path it was saved at, else the first opened."""
    rec = load_sessions().get(pid) or {}
    rpath = rec.get("path") if isinstance(rec, dict) else None
    if rpath:
        for d in docs:
            if _file_of(d) and _same(_file_of(d), rpath):
                return d
    for d in docs:
        f = _file_of(d)
        if f and _real(getattr(d, FILE_PROP, "") or "") == _real(f):
            return d
    return docs[0]


def ensure_id(doc):
    """The project id of `doc`, stamping it first (R365). A document that
    shares its id with another open one gets a new id unless it is the
    one that owns it (_owner_of)."""
    if not _stampable(doc):
        return doc_id(doc)
    if getattr(doc, "Name", None) not in _opened:
        on_opened(doc)                  # opened before the observer saw it
    try:
        pid = getattr(doc, PROJECT_PROP, "") or str(doc.Uid) or new_id()
        same = [d for d in _open_docs() if doc_id(d) == pid]
        if doc not in same:
            same.append(doc)
        if len(same) > 1 and _owner_of(pid, same) is not doc:
            return rekey(doc, "duplicate_open")[1]
        if getattr(doc, PROJECT_PROP, "") != pid or str(doc.Uid) != pid:
            _set_id(doc, pid)
        f = _file_of(doc)
        if f and not getattr(doc, FILE_PROP, ""):
            _set_prop(doc, FILE_PROP, _real(f))
        return pid
    except Exception as exc:                           # noqa: BLE001
        _log("ensure_id: %r" % (exc,))
        return doc_id(doc)


def doc_key(doc):
    """The chat key of a document: its project id (stamped on first use)."""
    return ensure_id(doc) if _stampable(doc) else doc_id(doc)


def _mark_modified(doc):
    try:
        import FreeCADGui
        g = FreeCADGui.getDocument(doc.Name)
        if g is not None:
            g.Modified = True
    except Exception:                                  # noqa: BLE001
        pass


def is_modified(doc):
    """R362: unsaved changes (FreeCAD's Gui flag), or a new id not saved."""
    if doc is None:
        return False
    if getattr(doc, "Name", None) in _needs_save:
        return True
    try:
        import FreeCADGui
        g = FreeCADGui.getDocument(doc.Name)
        return bool(getattr(g, "Modified", False)) if g is not None else False
    except Exception:                                  # noqa: BLE001
        return False


# --------------------------------------------------------- file contents
_DOC_PROPS_END = re.compile(rb"<Objects\b|</Properties>")


def _doc_xml(zf):
    try:
        return zf.read("Document.xml")
    except KeyError:
        return b""


def _doc_head(xml):
    """The document-level <Properties> block (before the objects)."""
    m = _DOC_PROPS_END.search(xml)
    return xml[:m.end()] if m else xml


def _prop_value(head, name):
    m = re.search(rb'<Property name="' + name.encode() +
                  rb'"[^>]*>\s*<(?:String|Uuid) value="([^"]*)"', head)
    return m.group(1).decode("utf-8", "replace") if m else ""


def read_file_ids(path):
    """(Uid, AtechProjectId, AtechProjectFile) of a saved project, read
    from its Document.xml without FreeCAD. ("", "", "") when unreadable."""
    try:
        with zipfile.ZipFile(path) as zf:
            head = _doc_head(_doc_xml(zf))
    except (OSError, zipfile.BadZipFile, KeyError):
        return "", "", ""
    return (_prop_value(head, "Uid"), _prop_value(head, PROJECT_PROP),
            _prop_value(head, FILE_PROP))


def file_id(path):
    uid, pid, _f = read_file_ids(path)
    return pid or uid


def _xml_attr(s):
    return (s.replace("&", "&amp;").replace('"', "&quot;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _rewrite_zip(path, edit_members):
    """Rewrite the zip at `path`; edit_members(name, bytes) -> bytes or None
    (None drops the member). Atomic (tmp + replace)."""
    tmp = path + ".atech-tmp"
    with zipfile.ZipFile(path) as src, \
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = edit_members(info.filename, src.read(info))
            if data is None:
                continue
            ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            dst.writestr(ni, data)
    shutil.copystat(path, tmp)
    os.replace(tmp, path)


def rekey_file(path, new, file_path=None):
    """Write project id `new` (and Uid) into the saved file at `path`, and
    where it now lives (AtechProjectFile). Returns the old id."""
    old = file_id(path)
    where = _real(file_path or path)

    def edit(name, data):
        if name != "Document.xml":
            return data
        head = _doc_head(data)
        rest = data[len(head):]
        head = re.sub(rb'(<Property name="Uid"[^>]*>\s*<Uuid value=")[^"]*(")',
                      lambda m: m.group(1) + new.encode() + m.group(2), head,
                      count=1)
        for prop, val in ((PROJECT_PROP, new), (FILE_PROP, where)):
            pat = re.compile(rb'(<Property name="' + prop.encode() +
                             rb'"[^>]*>\s*<String value=")[^"]*(")')
            enc = _xml_attr(val).encode("utf-8")
            if pat.search(head):
                head = pat.sub(lambda m, e=enc: m.group(1) + e + m.group(2),
                               head, count=1)
        return head + rest
    _rewrite_zip(path, edit)
    return old


# ------------------------------------------------------------ trust store
def copy_trust(old, new):
    """Copy the trust store's record of `old` to `new` (build.py's file,
    written through its own helpers)."""
    if not old or not new or old == new:
        return False
    try:
        from . import build
        store = build._load_trust()
        rec = store.get(old)
        if not isinstance(rec, dict):
            return False
        store[new] = json.loads(json.dumps(rec))
        store[new]["t"] = time.time()
        build._save_trust(store)
        return True
    except Exception as exc:                           # noqa: BLE001
        _log("trust copy: %r" % (exc,))
        return False


def is_local(pid):
    """This computer knows the project: a chat record or trust record."""
    if not pid:
        return False
    if pid in load_sessions():
        return True
    try:
        from . import build
        return pid in build._load_trust()
    except Exception:                                  # noqa: BLE001
        return False


# ---------------------------------------------------------- sessions.json
def sessions_path():
    if SESSIONS_PATH:
        return SESSIONS_PATH
    try:
        from . import settings as cfgmod
        return os.path.join(cfgmod.chat_workspace_root(), "sessions.json")
    except Exception:                                  # noqa: BLE001
        return os.path.join(_data_root(), "agent", "sessions.json")


def load_sessions(path=None):
    try:
        with open(path or sessions_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_sessions(data, path=None):
    path = path or sessions_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
        os.replace(tmp, path)
        return True
    except (OSError, TypeError, ValueError) as exc:
        _log("session store: %r" % (exc,))
        return False


def record_path(pid, path, sessions=None):
    """Remember where project `pid` lives (merged into its record)."""
    if not pid or not path:
        return False
    data = load_sessions(sessions)
    rec = data.get(pid)
    rec = dict(rec) if isinstance(rec, dict) else {}
    real = _real(path)
    if rec.get("path") == real:
        return True
    rec["path"] = real
    rec.setdefault("saved", int(time.time()))
    data[pid] = rec
    return write_sessions(data, sessions)


def record_for_path(path, sessions=None):
    """The id whose record says it lives at `path`, or None."""
    real = _real(path)
    if not real:
        return None
    for k, rec in load_sessions(sessions).items():
        if isinstance(rec, dict) and rec.get("path") == real:
            return k
    return None


def _chat_root(sessions=None):
    return os.path.dirname(sessions or sessions_path())


def _remove_chat_folder(ws, sessions=None, keep=()):
    """Delete a chat-* folder of ours (never anything else)."""
    if not isinstance(ws, str) or not ws:
        return False
    root = _real(_chat_root(sessions))
    real = _real(ws)
    if os.path.dirname(real) != root or \
            not os.path.basename(real).startswith("chat-") or \
            real in {_real(k) for k in keep}:
        return False
    shutil.rmtree(real, ignore_errors=True)
    return not os.path.exists(real)


def forget_project(pid, sessions=None, remove_chat=True, keep=()):
    """Drop `pid`'s record (and its chat folder)."""
    data = load_sessions(sessions)
    rec = data.pop(pid, None)
    if rec is None:
        return False
    write_sessions(data, sessions)
    if remove_chat and isinstance(rec, dict):
        used = {r.get("ws") for r in data.values() if isinstance(r, dict)}
        if rec.get("ws") not in used:
            _remove_chat_folder(rec.get("ws"), sessions, keep)
    return True


def prune_sessions(sessions=None, open_ids=(), now=None,
                   max_untitled_days=30):
    """R371: drop records nothing can come back to:
      - a record whose project file is gone (deleted, or holds another
        project now);
      - a record of a never-saved document whose chat folder is gone, or
        that is older than `max_untitled_days`.
    Open documents' records are kept. Chat folders are left to "Clear old
    chats" (a file on an unmounted disk is not gone for good). Returns the
    dropped ids."""
    now = now or time.time()
    data = load_sessions(sessions)
    keep = set(open_ids)
    gone = []
    for k, rec in list(data.items()):
        if k in keep:
            continue
        if not isinstance(rec, dict):
            gone.append(k)
            continue
        path = rec.get("path")
        if path:
            if not os.path.isfile(path) or file_id(path) not in ("", k):
                gone.append(k)
            continue
        ws = rec.get("ws")
        age = now - float(rec.get("saved") or 0)
        if not (isinstance(ws, str) and os.path.isdir(ws)) or \
                age > max_untitled_days * 86400:
            gone.append(k)
    if gone:
        for k in gone:
            data.pop(k, None)
        write_sessions(data, sessions)
    return gone


# ----------------------------------------------------------- chat payload
_chat_provider = [None]


def set_chat_provider(fn):
    """fn(doc) -> {"transcript": {...}, "ws": folder} or None (None: the
    panel has nothing newer than the file; the file's chat is kept)."""
    try:
        _chat_provider[0] = weakref.WeakMethod(fn)
    except TypeError:
        _chat_provider[0] = (lambda f=fn: f)


def _provided(doc):
    ref = _chat_provider[0]
    fn = ref() if ref is not None else None
    if fn is None:
        return None
    try:
        return fn(doc)
    except Exception as exc:                           # noqa: BLE001
        _log("chat provider: %r" % (exc,))
        return None


_ENTRY_FIELDS = {
    "bubble": ("text", "role"),
    "card": ("name", "args", "mono", "body", "status", "status_kind", "tip",
             "caveat", "caveat_text", "info_text"),
    "notice": ("title", "body", "detail"),
    "shot": ("path", "caption", "file"),
}


def _plain(v):
    if v is None or isinstance(v, (str, bool, int, float)):
        return v
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return str(v)


def serialize_transcript(snap):
    """The panel's kept transcript (R190 snapshot) as plain JSON data:
    bubbles, tool cards, notices (without their buttons) and shots."""
    out = []
    for e in (snap or {}).get("entries") or ():
        kind = e.get("kind") if isinstance(e, dict) else None
        if kind not in _ENTRY_FIELDS:
            continue
        rec = {"kind": kind}
        for f in _ENTRY_FIELDS[kind]:
            if f in e:
                rec[f] = _plain(e[f])
        out.append(rec)
    return {"entries": out,
            "last_text": str((snap or {}).get("last_text") or "")}


def pack_chat(transcript, ws=None, pid=None):
    """{member name: bytes} for the file: chat.json, intent.json and the
    images the transcript shows or the workspace holds (capped)."""
    tr = serialize_transcript(transcript)
    files, total = {}, 0

    def add(src, name):
        nonlocal total
        try:
            size = os.path.getsize(src)
        except OSError:
            return None
        if size > MAX_EMBED_FILE or total + size > MAX_EMBED_TOTAL:
            return None
        if name in files:
            return name
        with open(src, "rb") as fh:
            files[name] = fh.read()
        total += size
        return name

    for e in tr["entries"]:
        if e["kind"] == "shot":
            p = e.pop("path", "") or ""
            if p and os.path.isfile(p) and \
                    p.lower().endswith(CHAT_FILE_EXT):
                e["file"] = add(p, os.path.basename(p))
    if ws and os.path.isdir(ws):
        if os.path.isfile(os.path.join(ws, INTENT)):
            add(os.path.join(ws, INTENT), INTENT)
        imgs = sorted((n for n in os.listdir(ws)
                       if n.lower().endswith(CHAT_FILE_EXT)),
                      key=lambda n: -os.path.getmtime(os.path.join(ws, n)))
        for n in imgs:
            add(os.path.join(ws, n), n)
    meta = {"v": CHAT_VERSION, "id": pid, "saved": int(time.time()),
            "transcript": tr, "files": sorted(files)}
    out = {CHAT_JSON: json.dumps(meta, ensure_ascii=False).encode("utf-8")}
    for n, data in files.items():
        out[CHAT_FILES + n] = data
    return out


def chat_members(path):
    """The AtechChat/ members of a saved file, {name: bytes}."""
    out = {}
    try:
        with zipfile.ZipFile(path) as zf:
            total = 0
            for info in zf.infolist():
                if not info.filename.startswith(CHAT_DIR):
                    continue
                total += info.file_size
                if info.file_size > MAX_EMBED_FILE * 2 or \
                        total > MAX_UNPACK_TOTAL:
                    break
                out[info.filename] = zf.read(info)
    except (OSError, zipfile.BadZipFile):
        return {}
    return out


def append_chat(path, members):
    """Add the chat members to a saved file (FreeCAD wrote it without them).
    Members already there are replaced."""
    if not members or not path or not os.path.isfile(path):
        return False
    try:
        with zipfile.ZipFile(path) as zf:
            have = {i.filename for i in zf.infolist()}
        if have & set(members):
            _rewrite_zip(path, lambda n, d: None if n.startswith(CHAT_DIR)
                         else d)
        with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as zf:
            for name, data in members.items():
                zf.writestr(name, data)
        return True
    except (OSError, zipfile.BadZipFile) as exc:
        _log("chat not embedded in %s: %r" % (path, exc))
        return False


def strip_chat(path):
    """Remove the AtechChat/ members from a saved file."""
    try:
        _rewrite_zip(path, lambda n, d: None if n.startswith(CHAT_DIR) else d)
        return True
    except (OSError, zipfile.BadZipFile) as exc:
        _log("strip chat %s: %r" % (path, exc))
        return False


def read_chat(path):
    """The chat saved in a project file: {"transcript": {...}, "files":
    {name: bytes}, "id": ...} or None."""
    members = chat_members(path) if path else {}
    raw = members.get(CHAT_JSON)
    if not raw:
        return None
    try:
        meta = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    tr = meta.get("transcript") if isinstance(meta.get("transcript"),
                                              dict) else {}
    files = {}
    for name, data in members.items():
        if name.startswith(CHAT_FILES):
            base = os.path.basename(name)
            if base == INTENT or base.lower().endswith(CHAT_FILE_EXT):
                files[base] = data
    return {"transcript": serialize_transcript(tr), "files": files,
            "id": meta.get("id"), "saved": meta.get("saved")}


def read_doc_chat(doc):
    f = _file_of(doc)
    return read_chat(f) if f and os.path.isfile(f) else None


def unpack_chat(bundle, ws, allow_intent=True):
    """Write a file's chat files into chat folder `ws` (never overwriting
    what is there) and return its transcript in the panel's kept form
    (R190), shots pointing into `ws`."""
    if not bundle:
        return None
    os.makedirs(ws, exist_ok=True)
    for name, data in (bundle.get("files") or {}).items():
        name = os.path.basename(name)
        if not name or name.startswith("."):
            continue
        if name == INTENT and not allow_intent:
            continue
        dst = os.path.join(ws, name)
        if os.path.exists(dst):
            continue
        try:
            with open(dst, "wb") as fh:
                fh.write(data)
        except OSError as exc:
            _log("unpack %s: %r" % (name, exc))
    entries = []
    for e in (bundle.get("transcript") or {}).get("entries") or ():
        e = dict(e)
        if e.get("kind") == "shot":
            fn = e.pop("file", None)
            if not fn:
                continue
            e["path"] = os.path.join(ws, os.path.basename(fn))
            e.setdefault("caption", "")
        entries.append(e)
    for e in entries:
        if e.get("kind") == "notice":
            e.setdefault("actions", [])
            e.setdefault("detail", None)
            e.setdefault("enabled", [])
            e.setdefault("tag", None)
        elif e.get("kind") == "card":
            for f in _ENTRY_FIELDS["card"]:
                e.setdefault(f, "" if f not in ("mono",) else False)
            e["status_kind"] = e.get("status_kind") or "idle"
    return {"entries": entries, "shots": [], "captions": {},
            "last_text": (bundle.get("transcript") or {}).get("last_text")
            or ""}


# ------------------------------------------------------- save observer
_flags = {}                  # suspended behaviours (see _suspend)
_pending = {}                # doc Name -> what to finish after its save


@contextlib.contextmanager
def _suspend(*names):
    """keep_id: no re-key on this save; no_chat: write no chat; quiet: the
    observer does nothing at all."""
    for n in names:
        _flags[n] = _flags.get(n, 0) + 1
    try:
        yield
    finally:
        for n in names:
            _flags[n] -= 1


def _bundle_for(doc, on_disk):
    """What chat goes into the file being saved: the panel's, else what the
    file on disk already carries (so a save never drops it)."""
    got = _provided(doc)
    if got is not None:
        try:
            return pack_chat(got.get("transcript"), got.get("ws"),
                             doc_id(doc))
        except Exception as exc:                       # noqa: BLE001
            _log("pack chat: %r" % (exc,))
    if on_disk and os.path.isfile(on_disk):
        return chat_members(on_disk)
    return {}


def on_start_save(doc, filename):
    if _flags.get("quiet") or not _stampable(doc):
        return
    real = _real(filename)
    cur = _real(_file_of(doc))
    prev = getattr(doc, FILE_PROP, "") or ""
    ensure_id(doc)
    is_copy = real != cur
    # The chat as it is BEFORE any re-key, from the panel or the file.
    chat = {} if _flags.get("no_chat") else \
        _bundle_for(doc, prev if prev and os.path.isfile(prev) else cur)
    job = {"chat": chat, "copy": None}
    if is_copy:
        # Save a Copy: the copy is a new project; the document stays itself.
        old = doc_id(doc)
        if not _flags.get("keep_id"):
            rekey(doc, "copy", notify=False)
        job["copy"] = (old, prev)
        _set_prop(doc, FILE_PROP, real)
    else:
        if prev and _real(prev) != real and os.path.isfile(prev) and \
                not _flags.get("keep_id") and file_id(prev) == doc_id(doc):
            # Save As to a new file while the old one stays: two projects.
            rekey(doc, "save_as")
        _set_prop(doc, FILE_PROP, real)
    _pending[doc.Name] = job


def on_finish_save(doc, filename):
    if _flags.get("quiet") or not _stampable(doc):
        return
    job = _pending.pop(getattr(doc, "Name", ""), None) or {}
    if job.get("chat"):
        chat = dict(job["chat"])
        if CHAT_JSON in chat:
            # The chat names the id of the file it is written into.
            try:
                meta = json.loads(chat[CHAT_JSON].decode("utf-8"))
                meta["id"] = doc_id(doc)
                chat[CHAT_JSON] = json.dumps(meta, ensure_ascii=False).encode()
            except (ValueError, UnicodeDecodeError):
                pass
        append_chat(filename, chat)
    if job.get("copy"):
        old, prev = job["copy"]
        _set_id(doc, old)
        _set_prop(doc, FILE_PROP, prev or "")
        return
    _needs_save.discard(doc.Name)
    record_path(doc_id(doc), filename)
    note_recent(filename)


_opened = set()              # doc Names on_opened has seen


def on_opened(doc):
    """R365 on open: stamp the id, or give a copy its own. Once per open
    document (FreeCAD 1.1 has no restore signal for Python observers: the
    activation that follows a load, or the first ensure_id, calls this)."""
    if _flags.get("quiet") or not _stampable(doc):
        return None
    _opened.add(getattr(doc, "Name", None))
    try:
        real = _real(_file_of(doc))
        pid = getattr(doc, PROJECT_PROP, "") or str(doc.Uid)
        prev = _real(getattr(doc, FILE_PROP, "") or "")
        others = [d for d in _open_docs() if d is not doc and doc_id(d) == pid]
        claimed = record_for_path(real) if real else None
        reason = None
        if claimed and claimed != pid and not any(
                doc_id(d) == claimed for d in _open_docs() if d is not doc):
            # This very file was given a new id earlier that was not saved
            # yet: it is that project again.
            _set_id(doc, claimed)
            _needs_save.add(doc.Name)
            pid = claimed
        elif others:
            reason = "duplicate_open"
        elif real and prev and prev != real and os.path.isfile(prev) and \
                file_id(prev) == pid:
            reason = "copied_file"
        else:
            rec = load_sessions().get(pid)
            rp = rec.get("path") if isinstance(rec, dict) else None
            if real and rp and rp != real and os.path.isfile(rp) and \
                    file_id(rp) == pid:
                reason = "copied_file"
        if reason:
            pid = rekey(doc, reason)[1]
        else:
            _set_id(doc, pid)
        if real:
            _set_prop(doc, FILE_PROP, real)
            record_path(pid, real)
            note_recent(real)
        return reason
    except Exception as exc:                           # noqa: BLE001
        _log("on_opened: %r" % (exc,))
        return None


class _Observer(object):
    """FreeCAD document observer (App level)."""

    def slotStartSaveDocument(self, doc, filename):    # noqa: N802
        try:
            on_start_save(doc, filename)
        except Exception as exc:                       # noqa: BLE001
            _log("start save: %r" % (exc,))

    def slotFinishSaveDocument(self, doc, filename):   # noqa: N802
        try:
            on_finish_save(doc, filename)
        except Exception as exc:                       # noqa: BLE001
            _log("finish save: %r" % (exc,))

    def slotActivateDocument(self, doc):               # noqa: N802
        if getattr(doc, "Name", None) not in _opened:
            on_opened(doc)

    slotFinishRestoreDocument = slotActivateDocument   # where it exists

    def slotDeletedDocument(self, doc):                # noqa: N802
        name = getattr(doc, "Name", "")
        _needs_save.discard(name)
        _pending.pop(name, None)
        _opened.discard(name)


_observer = [None]


def install_observer():
    """Idempotent. False outside FreeCAD."""
    if _observer[0] is not None:
        return True
    fc = _fc()
    if fc is None or not hasattr(fc, "addDocumentObserver"):
        return False
    obs = _Observer()
    fc.addDocumentObserver(obs)
    _observer[0] = obs
    for d in _open_docs():
        ensure_id(d)
    return True


def uninstall_observer():
    obs, _observer[0] = _observer[0], None
    fc = _fc()
    if obs is not None and fc is not None:
        try:
            fc.removeDocumentObserver(obs)
        except Exception:                              # noqa: BLE001
            pass


# --------------------------------------------------------------- recents
def note_recent(path):
    """R370: put `path` first in Atech's own recent list."""
    if not path:
        return
    real = _real(path)
    data = _load_state()
    rec = [r for r in data.get("recent") or ()
           if isinstance(r, dict) and _real(r.get("path")) != real]
    rec.insert(0, {"path": real, "t": int(time.time())})
    data["recent"] = rec[:50]
    _save_state(data)


def forget_recent(path):
    real = _real(path)
    data = _load_state()
    data["recent"] = [r for r in data.get("recent") or ()
                      if isinstance(r, dict) and _real(r.get("path")) != real]
    _save_state(data)


def _replace_recent(old, new):
    real_old, real_new = _real(old), _real(new)
    data = _load_state()
    out = []
    for r in data.get("recent") or ():
        if isinstance(r, dict):
            p = _real(r.get("path"))
            if p == real_old:
                r = dict(r, path=real_new)
            out.append(r)
    data["recent"] = out
    _save_state(data)


def freecad_recent():
    """FreeCAD's own MRU list (File > Recent files), as stored."""
    fc = _fc()
    if fc is None or not hasattr(fc, "ParamGet"):
        return []
    try:
        grp = fc.ParamGet(RECENT_PARAM)
        n = max(grp.GetInt("RecentFiles", 0) or 10, 10)
        return [p for p in (grp.GetString("MRU%d" % i, "") for i in range(n))
                if p]
    except Exception:                                  # noqa: BLE001
        return []


def recent_files(limit=RECENT_MAX, extra=None):
    """R370: Atech's recents, then FreeCAD's, deduped by realpath, existing
    .FCStd files only, at most `limit`."""
    own = [r.get("path") for r in _load_state().get("recent") or ()
           if isinstance(r, dict)]
    out, seen = [], set()
    for p in own + list(freecad_recent() if extra is None else extra):
        if not p or not isinstance(p, str):
            continue
        real = _real(p)
        if real in seen or not os.path.isfile(real) or \
                not real.lower().endswith(SUFFIX.lower()):
            continue
        seen.add(real)
        out.append(real)
        if len(out) >= limit:
            break
    return out


# ------------------------------------------------------------ Home data
_info_cache = {}


def _file_info(path, st):
    key = (path, st.st_mtime, st.st_size)
    hit = _info_cache.get(path)
    if hit and hit[0] == key:
        return hit[1]
    info = {"id": "", "has_electronics": False, "thumbnail": False}
    try:
        with zipfile.ZipFile(path) as zf:
            xml = _doc_xml(zf)
            head = _doc_head(xml)
            info["id"] = _prop_value(head, PROJECT_PROP) or \
                _prop_value(head, "Uid")
            info["has_electronics"] = bool(re.search(
                rb'<Property name="AtechRole"[^>]*>\s*<String value="[^"]+"',
                xml))
            info["thumbnail"] = "thumbnails/Thumbnail.png" in zf.namelist()
    except (OSError, zipfile.BadZipFile):
        pass
    _info_cache[path] = (key, info)
    return info


def thumbnail_bytes(path):
    """The PNG FreeCAD saved into the file (SaveThumbnail), or None."""
    try:
        with zipfile.ZipFile(path) as zf:
            return zf.read("thumbnails/Thumbnail.png")
    except (OSError, KeyError, zipfile.BadZipFile):
        return None


def list_projects(folder=None, with_thumbnails=True, recent=True):
    """R372: the Home grid's projects, newest first: every .FCStd in the
    projects folder plus the recent files elsewhere. Each is a dict:
    name, path, mtime, thumbnail (PNG bytes or None), has_electronics, id,
    open (an open document has it)."""
    folder = folder or projects_dir()
    paths = []
    try:
        for n in os.listdir(folder):
            if n.lower().endswith(SUFFIX.lower()) and not n.startswith("."):
                paths.append(os.path.join(folder, n))
    except OSError:
        pass
    if recent:
        paths += recent_files(RECENT_MAX)
    open_paths = {_real(_file_of(d)) for d in _open_docs() if _file_of(d)}
    out, seen = [], set()
    for p in paths:
        real = _real(p)
        if real in seen:
            continue
        seen.add(real)
        try:
            st = os.stat(real)
        except OSError:
            continue
        info = _file_info(real, st)
        out.append({
            "name": os.path.splitext(os.path.basename(real))[0],
            "path": real, "mtime": st.st_mtime, "id": info["id"],
            "has_electronics": info["has_electronics"],
            "thumbnail": thumbnail_bytes(real)
            if with_thumbnails and info["thumbnail"] else None,
            "open": real in open_paths})
    out.sort(key=lambda r: -r["mtime"])
    return out


# ------------------------------------------------------------ operations
def create_project(name=None, folder=None):
    """R361: a new document named `name` (default "Untitled N"), saved at
    once into the projects folder. Returns the document."""
    folder = folder or ensure_projects_dir()
    os.makedirs(folder, exist_ok=True)
    name = clean_name(name) or default_name(folder)
    why = name_problem(name, folder)
    if why:
        raise ProjectError(why)
    import FreeCAD
    install_observer()
    doc = FreeCAD.newDocument(re.sub(r"\W", "_", name) or "Project")
    doc.Label = name
    ensure_id(doc)
    path = os.path.join(folder, name + SUFFIX)
    doc.saveAs(path)
    doc.Label = name
    note_recent(path)
    return doc


def save(doc):
    """Save `doc` to its file. False for a document that has no file yet
    (the caller asks for a name: save_new)."""
    if doc is None or not _file_of(doc):
        return False
    install_observer()
    doc.save()
    _needs_save.discard(doc.Name)
    _clear_modified(doc)
    return True


def save_new(doc, name, folder=None):
    """Give an unsaved document a name and a file in the projects folder."""
    folder = folder or ensure_projects_dir()
    name = clean_name(name)
    why = name_problem(name, folder)
    if why:
        raise ProjectError(why)
    install_observer()
    path = os.path.join(folder, name + SUFFIX)
    doc.saveAs(path)
    doc.Label = name
    _clear_modified(doc)
    return path


def _clear_modified(doc):
    try:
        import FreeCADGui
        g = FreeCADGui.getDocument(doc.Name)
        if g is not None:
            g.Modified = False
    except Exception:                                  # noqa: BLE001
        pass


def _target(target):
    """(path, open doc or None) for a path or a document."""
    if isinstance(target, str):
        return _real(target), open_doc_for(target)
    return _real(_file_of(target)), target


def rename_project(target, new_name):
    """R367: rename a project's file (and its document's label). Returns the
    new path."""
    path, doc = _target(target)
    if not path:
        raise ProjectError("Save the project first, then rename it.")
    name = clean_name(new_name)
    folder = os.path.dirname(path)
    why = name_problem(name, folder, current=path)
    if why:
        raise ProjectError(why)
    new = os.path.join(folder, name + SUFFIX)
    pid = doc_id(doc) if doc is not None else file_id(path)
    if doc is not None:
        install_observer()
        with _suspend("keep_id"):
            doc.saveAs(new)
        doc.Label = name
        if os.path.exists(path) and not _same(path, new):
            os.remove(path)
        _clear_modified(doc)
    else:
        os.rename(path, new)
    if pid:
        data = load_sessions()
        if isinstance(data.get(pid), dict):
            data[pid]["path"] = _real(new)
            write_sessions(data)
    _replace_recent(path, new)
    return _real(new)


def duplicate_project(target, new_name=None):
    """R367: a copy beside the original, with its own id and the chat so
    far. Returns the copy's path."""
    path, doc = _target(target)
    if not path or not os.path.isfile(path):
        raise ProjectError("Save the project first, then duplicate it.")
    folder = os.path.dirname(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    name = clean_name(new_name) if new_name else unique_name(stem, folder)
    why = name_problem(name, folder)
    if why:
        raise ProjectError(why)
    dest = os.path.join(folder, name + SUFFIX)
    if doc is not None and install_observer():
        doc.saveCopy(dest)              # the observer re-keys the copy
    else:
        shutil.copy2(path, dest)
        old = rekey_file(dest, new_id(), dest)
        copy_trust(old, file_id(dest))
    note_recent(dest)
    return _real(dest)


def move_to_trash(path):
    """Move `path` to the Trash. True on success."""
    try:
        from PySide6 import QtCore
        got = QtCore.QFile.moveToTrash(path)
        ok = got[0] if isinstance(got, tuple) else bool(got)
        if ok:
            return True
    except Exception:                                  # noqa: BLE001
        pass
    if sys.platform == "darwin":
        trash = os.path.expanduser("~/.Trash")
        if os.path.isdir(trash):
            base = os.path.basename(path)
            dst, n = os.path.join(trash, base), 1
            stem, ext = os.path.splitext(base)
            while os.path.exists(dst):
                n += 1
                dst = os.path.join(trash, "%s %d%s" % (stem, n, ext))
            shutil.move(path, dst)
            return True
    return False


def trash_project(target, trash=None, keep_chats=()):
    """R367: close the project if open, move its file to the Trash, and
    forget its chat (sessions.json record and chat folder) and recents
    entry. Returns the id it had."""
    path, doc = _target(target)
    pid = doc_id(doc) if doc is not None else file_id(path)
    if doc is not None:
        import FreeCAD
        FreeCAD.closeDocument(doc.Name)
    if path and os.path.exists(path):
        if not (trash or move_to_trash)(path):
            raise ProjectError("The file could not be moved to the Trash.")
    if pid:
        forget_project(pid, keep=keep_chats)
    if path:
        forget_recent(path)
    return pid


def reveal_in_finder(path, runner=None):
    """R367: show the file in Finder (its folder elsewhere)."""
    run = runner or subprocess.Popen
    if sys.platform == "darwin":
        return run(["open", "-R", path])
    return run(["xdg-open", os.path.dirname(path) or "."])


def export_for_sharing(target, dest):
    """R369: a copy at `dest` with every agent script emptied
    (build.strip_scripts), no chat, and a new id. The original is not
    touched. Returns how many scripts were removed."""
    import FreeCAD
    from . import build
    path, doc = _target(target)
    tmpdir = tempfile.mkdtemp(prefix="atech-share-")
    tmp = os.path.join(tmpdir, "share" + SUFFIX)
    try:
        with _suspend("quiet"):
            if doc is not None:
                doc.saveCopy(tmp)
            else:
                shutil.copy2(path, tmp)
            d = FreeCAD.openDocument(tmp, True)
            try:
                n = build.strip_scripts(d)
                if _stampable(d):
                    _set_id(d, new_id())
                    _set_prop(d, FILE_PROP, _real(dest))
                d.saveAs(dest)
            finally:
                FreeCAD.closeDocument(d.Name)
        strip_chat(dest)
        return n
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --------------------------------------------------------------- autosave
def request_save(doc):
    """R363: save now (after an agent build). Only a project with a file."""
    try:
        if doc is not None and _file_of(doc):
            return save(doc)
    except Exception as exc:                           # noqa: BLE001
        _log("autosave %s: %r" % (getattr(doc, "Name", "?"), exc))
    return False


def autosave_tick(docs=None):
    """R363: save every open project that has a file and unsaved changes.
    Returns the names saved."""
    saved = []
    for d in (_open_docs() if docs is None else docs):
        try:
            if not _file_of(d) or not os.path.isdir(
                    os.path.dirname(_file_of(d))):
                continue
            if not is_modified(d):
                continue
            if save(d):
                saved.append(d.Name)
        except Exception as exc:                       # noqa: BLE001
            _log("autosave %s: %r" % (getattr(d, "Name", "?"), exc))
    return saved


def save_open_projects():
    """Save every open project that has a file (the quit guard)."""
    return autosave_tick()


def make_autosaver(parent=None, interval_ms=AUTOSAVE_MS):
    """A started QTimer running autosave_tick every minute."""
    from PySide6 import QtCore
    t = QtCore.QTimer(parent)
    t.setObjectName("AtechAutosave")
    t.setInterval(interval_ms)
    t.timeout.connect(lambda: autosave_tick())
    t.start()
    return t


def ensure_recovery_on():
    """R364: FreeCAD's crash recovery on, unless the user turned it off."""
    fc = _fc()
    if fc is None or not hasattr(fc, "ParamGet"):
        return False
    try:
        grp = fc.ParamGet(DOC_PARAM)
        if "AutoSaveEnabled" not in (grp.GetBools() or []):
            grp.SetBool("AutoSaveEnabled", True)
        if "AutoSaveTimeout" not in (grp.GetInts() or []):
            grp.SetInt("AutoSaveTimeout", 2)
        return grp.GetBool("AutoSaveEnabled", True)
    except Exception as exc:                           # noqa: BLE001
        _log("recovery prefs: %r" % (exc,))
        return False


def transient_root():
    fc = _fc()
    try:
        return fc.getUserCachePath() if fc is not None else None
    except Exception:                                  # noqa: BLE001
        return None


def cleanup_transient_dirs(root=None, prefix=None, keep=()):
    """R364: remove the EMPTY "<ExeName>_Doc_*" folders under the cache
    (a folder with anything in it may hold recovery data and stays).
    Returns how many were removed."""
    root = root or transient_root()
    if not root or not os.path.isdir(root):
        return 0
    if prefix is None:
        fc = _fc()
        exe = ""
        try:
            exe = fc.ConfigGet("ExeName") if fc is not None else ""
        except Exception:                              # noqa: BLE001
            pass
        prefix = (exe or "Atech Atelier") + "_Doc_"
    keep = {_real(k) for k in keep}
    for d in _open_docs():
        try:
            keep.add(_real(d.TransientDir))
        except Exception:                              # noqa: BLE001
            pass
    n = 0
    for name in os.listdir(root):
        if not name.startswith(prefix):
            continue
        p = os.path.join(root, name)
        if _real(p) in keep or not os.path.isdir(p) or os.path.islink(p):
            continue
        try:
            os.rmdir(p)                 # only succeeds when empty
            n += 1
        except OSError:
            pass
    return n


_installed = {}


def install(parent=None):
    """Everything at start, once: the save/open observer, the session
    migration and pruning, the transient cleanup, recovery on, and the
    60 s autosave. Returns False outside FreeCAD."""
    if _installed.get("done"):
        return True
    if not install_observer():
        return False
    _installed["done"] = True
    try:
        from . import migrate
        migrate.migrate_sessions(sessions_path())
    except Exception as exc:                           # noqa: BLE001
        _log("session migration: %r" % (exc,))
    try:
        prune_sessions(open_ids={doc_id(d) for d in _open_docs()})
    except Exception as exc:                           # noqa: BLE001
        _log("prune sessions: %r" % (exc,))
    try:
        n = cleanup_transient_dirs()
        if n:
            _log("removed %d empty transient folders" % n)
    except Exception as exc:                           # noqa: BLE001
        _log("transient cleanup: %r" % (exc,))
    ensure_recovery_on()
    try:
        from PySide6 import QtWidgets
        if QtWidgets.QApplication.instance() is not None:
            _installed["timer"] = make_autosaver(parent)
    except Exception as exc:                           # noqa: BLE001
        _log("autosave timer: %r" % (exc,))
    # R455: the shipped default projects, copied in from a QTimer once the
    # launch is done (never inline: it must not slow the start).
    try:
        from . import default_projects
        default_projects.schedule_install()
    except Exception as exc:                           # noqa: BLE001
        _log("default projects: %r" % (exc,))
    return True
