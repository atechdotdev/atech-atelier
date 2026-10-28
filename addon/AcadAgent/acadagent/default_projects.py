"""default_projects - the projects Atech Atelier comes with (R450-R456).

branding/make_default_projects.py builds them at packaging time from the
showcase examples (agent_kit/examples/) and the build scripts ship them in
the bundle as Mod/AcadAgent/default_projects/: one .FCStd per product (real
tagged Atech hardware, the parts' colours and AtechAgentScript, a
thumbnail and a starter chat) plus manifest.json.

  R451 install_defaults()   copies each shipped project into the projects
                            folder (projects_store.projects_dir()) on the
                            first run and again whenever the manifest's
                            version grows - but only the titles it never
                            installed before: a file the user changed is
                            never overwritten, a file the user deleted is
                            never put back, and a file of the same name
                            the user made is left alone. What was installed
                            is recorded in default_projects.json next to
                            projects_store's own projects.json.
  R452 fresh ids            every copy gets a new AtechProjectId (= Uid),
                            written into the file, so two copies never
                            share a chat; the starter chat's id follows.
  R453 trusted scripts      the copy's build ids and script hashes (from
                            the manifest, and only for a copy whose sha256
                            matches it) go into the build trust store under
                            the new id, so the agent edits the shipped
                            design instead of asking the user to review a
                            "script from elsewhere".
  R454 new_from_default()   a fresh copy (its own id, "Toy car 2" when
                            "Toy car" is taken) opened as a new project:
                            Home's "Start from an example" row.
  R455 start-up             schedule_install() starts install_defaults on a
                            worker thread from a zero-length QTimer, so it
                            never slows the launch or freezes the window;
                            the trust records and Home's refresh follow on
                            the GUI thread. projects_store.install() calls
                            it.

Never raises out of install_defaults / schedule_install: a default project
that cannot be copied is logged and skipped.
"""
import hashlib
import json
import os
import shutil
import time

from . import projects_store

MANIFEST = "manifest.json"
STATE_NAME = "default_projects.json"
SHIPPED_DIR = None           # tests: the folder holding manifest.json
STATE_PATH = None            # tests: the install record
ENV_SHIPPED = "ATECH_DEFAULT_PROJECTS_DIR"
ENV_OFF = "ATECH_NO_DEFAULT_PROJECTS"

_SCHEDULED = {}


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[AcadAgent defaults] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


# ------------------------------------------------------------- shipped
def shipped_dir():
    """Mod/AcadAgent/default_projects/ (the bundle's), or the override."""
    if SHIPPED_DIR:
        return SHIPPED_DIR
    env = os.environ.get(ENV_SHIPPED)
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "default_projects")


def load_manifest(folder=None):
    """The shipped manifest ({"version", "projects": [...]}) with only the
    entries whose file is there, or None when nothing is shipped."""
    folder = folder or shipped_dir()
    try:
        with open(os.path.join(folder, MANIFEST), encoding="utf-8") as fh:
            man = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(man, dict) or not isinstance(man.get("projects"), list):
        return None
    good = []
    for p in man["projects"]:
        if not isinstance(p, dict):
            continue
        title, fn = p.get("title"), p.get("file")
        if not isinstance(title, str) or not isinstance(fn, str) or \
                os.path.basename(fn) != fn or not fn.endswith(projects_store.SUFFIX):
            continue
        if os.path.isfile(os.path.join(folder, fn)):
            good.append(p)
    try:
        version = int(man.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    return {"version": version, "projects": good, "folder": folder}


def entries(folder=None):
    """[(title, example key, summary)] of the shipped projects, in order."""
    man = load_manifest(folder)
    if not man:
        return []
    return [(p["title"], p.get("example") or "", p.get("summary") or "")
            for p in man["projects"]]


def thumbnail(title, folder=None):
    """The shipped project's thumbnail PNG bytes, or None."""
    rec = _record(title, folder)
    if not rec:
        return None
    return projects_store.thumbnail_bytes(rec[1])


def _record(title, folder=None):
    man = load_manifest(folder)
    for p in (man or {}).get("projects") or ():
        if p["title"] == title:
            return p, os.path.join(man["folder"], p["file"])
    return None


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


MIN_SHIPPED = 6


def check_shipped(folder=None, minimum=MIN_SHIPPED):
    """The build gate's row (verify_tree.py): (ok, detail). OK when
    manifest.json lists at least `minimum` projects and every listed file
    is there with the manifest's sha256 - the raw manifest is read, so an
    entry whose file is missing counts as a failure, not as absent."""
    folder = folder or shipped_dir()
    try:
        with open(os.path.join(folder, MANIFEST), encoding="utf-8") as fh:
            man = json.load(fh)
    except (OSError, ValueError) as exc:
        return False, "no manifest.json (%s)" % exc.__class__.__name__
    rows = man.get("projects") if isinstance(man, dict) else None
    if not isinstance(rows, list):
        return False, "manifest.json has no project list"
    bad = []
    for p in rows:
        fn = p.get("file") if isinstance(p, dict) else None
        if not isinstance(fn, str) or os.path.basename(fn) != fn:
            bad.append("bad entry")
            continue
        path = os.path.join(folder, fn)
        if not os.path.isfile(path):
            bad.append("%s missing" % fn)
        elif sha256_file(path) != p.get("sha256"):
            bad.append("%s sha256 differs" % fn)
    if bad:
        return False, "; ".join(bad[:3])
    if len(rows) < minimum:
        return False, "%d project(s), %d needed" % (len(rows), minimum)
    return True, "%d projects" % len(rows)


# ---------------------------------------------------------------- state
def state_path():
    return STATE_PATH or os.path.join(
        os.path.dirname(projects_store.state_path()), STATE_NAME)


def load_state():
    try:
        with open(state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {"version": 0, "titles": {}}
    if not isinstance(data, dict):
        return {"version": 0, "titles": {}}
    if not isinstance(data.get("titles"), dict):
        data["titles"] = {}
    return data


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
        _log("install record not saved: %r" % (exc,))
        return False


# ----------------------------------------------------------------- copy
def _rekey_chat(path, pid):
    """The embedded chat.json's "id" follows the file's new id."""
    def edit(name, data):
        if name != projects_store.CHAT_JSON:
            return data
        try:
            meta = json.loads(data.decode("utf-8"))
            meta["id"] = pid
            return json.dumps(meta, ensure_ascii=False).encode("utf-8")
        except (ValueError, UnicodeDecodeError, TypeError):
            return data
    projects_store._rewrite_zip(path, edit)


def _trust(pid, trust):
    """R453: the shipped builds of a copy are Studio's own."""
    if not pid or not isinstance(trust, dict) or not trust:
        return False
    try:
        from . import build
        store = build._load_trust()
        now = time.time()
        rec = store.setdefault(pid, {"builds": {}})
        rec["t"] = now
        builds = rec.setdefault("builds", {})
        for bid, b in trust.items():
            if isinstance(b, dict) and isinstance(b.get("sha"), str):
                builds[str(bid)] = {"sha": b["sha"], "n": int(b.get("n") or 0),
                                    "t": now}
        build._save_trust(store)
        return True
    except Exception as exc:                           # noqa: BLE001
        _log("trust for %s: %r" % (pid, exc))
        return False


def copy_fresh(src, dest, rec=None, trust_later=None):
    """Copy shipped project `src` to `dest` (which must not exist) with a
    new project id. Returns the new id. With a list `trust_later`, the
    trust record is appended to it as (id, trust) instead of written (the
    start-up worker thread leaves the trust store to the GUI thread)."""
    if os.path.exists(dest):
        raise projects_store.ProjectError(
            "A project called “%s” already exists." %
            os.path.splitext(os.path.basename(dest))[0])
    folder = os.path.dirname(dest)
    os.makedirs(folder, exist_ok=True)
    tmp = os.path.join(folder, ".%s.atech-default" % os.path.basename(dest))
    shutil.copyfile(src, tmp)
    try:
        pid = projects_store.new_id()
        projects_store.rekey_file(tmp, pid, dest)
        _rekey_chat(tmp, pid)
        # Never over a file that appeared meanwhile (the user's own, or a
        # copy Home's "Start from an example" made while the start-up
        # install ran): a hard link fails when `dest` exists; os.replace
        # would not. Folders without hard links fall back to check + move.
        try:
            os.link(tmp, dest)
        except FileExistsError:
            raise projects_store.ProjectError(
                "%s appeared while copying" % dest)
        except OSError:
            if os.path.exists(dest):
                raise projects_store.ProjectError(
                    "%s appeared while copying" % dest)
            os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    rec = rec or {}
    if rec.get("trust") and rec.get("sha256") == sha256_file(src):
        if trust_later is not None:
            trust_later.append((pid, rec["trust"]))
        else:
            _trust(pid, rec["trust"])
    return pid


# -------------------------------------------------------------- install
def install_defaults(projects_dir=None, shipped=None, now=None,
                     trust_later=None):
    """R451: copy the shipped projects in (first run / a newer manifest).
    `trust_later`: see copy_fresh.

    Returns {"installed": [titles], "skipped": {title: why}, "version":
    the manifest's, "ran": False when there was nothing to do}."""
    out = {"installed": [], "skipped": {}, "version": 0, "ran": False}
    try:
        man = load_manifest(shipped)
        if not man or not man["projects"]:
            return out
        out["version"] = man["version"]
        state = load_state()
        try:
            have = int(state.get("version") or 0)
        except (TypeError, ValueError):
            have = 0
        if have >= man["version"] and state.get("titles"):
            return out
        out["ran"] = True
        folder = projects_dir or projects_store.ensure_projects_dir()
        os.makedirs(folder, exist_ok=True)
        titles = state["titles"]
        t = time.time() if now is None else now
        for i, p in enumerate(man["projects"]):
            title = p["title"]
            if title in titles:
                out["skipped"][title] = "installed before"
                continue
            src = os.path.join(man["folder"], p["file"])
            name = projects_store.clean_name(title)
            if not name:
                out["skipped"][title] = "bad name"
                continue
            dest = os.path.join(folder, name + projects_store.SUFFIX)
            if os.path.exists(dest):
                # the user's own file of that name: never overwritten, and
                # recorded so a later run does not try again
                titles[title] = {"sha256": p.get("sha256"), "skipped": "exists",
                                 "t": int(t)}
                out["skipped"][title] = "a file of that name exists"
                continue
            if p.get("sha256") and sha256_file(src) != p["sha256"]:
                out["skipped"][title] = "damaged (sha256 differs)"
                continue
            try:
                pid = copy_fresh(src, dest, p, trust_later)
            except Exception as exc:                   # noqa: BLE001
                out["skipped"][title] = "copy failed: %s" % exc
                continue
            try:
                # Home lists newest first: keep the curated order.
                os.utime(dest, (t - i, t - i))
            except OSError:
                pass
            titles[title] = {"sha256": p.get("sha256"), "file": dest,
                             "id": pid, "t": int(t)}
            out["installed"].append(title)
        state["version"] = max(have, man["version"])
        _save_state(state)
    except Exception as exc:                           # noqa: BLE001
        _log("install defaults: %r" % (exc,))
    return out


def new_from_default(title, folder=None, open_doc=True, shipped=None):
    """R454: a fresh copy of shipped project `title` in the projects
    folder, opened as a new project. Returns its path (None when the
    project is not shipped)."""
    rec = _record(title, shipped)
    if rec is None:
        return None
    p, src = rec
    folder = folder or projects_store.ensure_projects_dir()
    name = projects_store.clean_name(title) or "Project"
    if os.path.exists(os.path.join(folder, name + projects_store.SUFFIX)):
        name = projects_store.unique_name(name, folder, suffix="")   # "Toy car 2"
    dest = os.path.join(folder, name + projects_store.SUFFIX)
    copy_fresh(src, dest, p)
    projects_store.note_recent(dest)
    if open_doc:
        import FreeCAD
        FreeCAD.openDocument(dest)
    return dest


# -------------------------------------------------------------- start-up
def schedule_install(delay_ms=0):
    """R455: install_defaults once per session, from a QTimer after the
    launch has finished (never inline). False when not scheduled."""
    if _SCHEDULED.get("done") or os.environ.get(ENV_OFF):
        return False
    if not os.path.isfile(os.path.join(shipped_dir(), MANIFEST)):
        return False
    try:
        from PySide6 import QtCore, QtWidgets
        if QtWidgets.QApplication.instance() is None:
            return False
    except Exception:                                  # noqa: BLE001
        return False
    _SCHEDULED["done"] = True
    import threading

    def finish(res, trust):
        # GUI thread: the trust store (shared with build.py) and Home.
        for pid, tr in trust:
            _trust(pid, tr)
        _SCHEDULED["result"] = res
        if res.get("installed"):
            _log("installed %s" % ", ".join(res["installed"]))
            try:
                from . import shell
                home = getattr(shell, "_refresh_home", None)
                if callable(home):
                    home()
            except Exception:                          # noqa: BLE001
                pass

    def run():
        # The copy is ~1 s of zip rewriting per project (MEASURED: 9.5 s
        # for the nine shipped ones), so it runs on a worker thread - pure
        # file work, no FreeCAD calls - and a GUI-thread timer picks the
        # result up. Inline on the timer it froze the window after launch.
        box, trust = {}, []

        def work():
            try:
                box["res"] = install_defaults(trust_later=trust)
            except Exception as exc:                   # noqa: BLE001
                _log("install defaults: %r" % (exc,))
                box["res"] = {"installed": []}

        th = threading.Thread(target=work, name="atech-default-projects",
                              daemon=True)
        poll = QtCore.QTimer()
        poll.setInterval(100)

        def check():
            if th.is_alive():
                return
            poll.stop()
            _SCHEDULED.pop("poll", None)
            finish(box.get("res") or {"installed": []}, trust)
        poll.timeout.connect(check)
        _SCHEDULED["poll"] = poll
        th.start()
        poll.start()
    QtCore.QTimer.singleShot(int(delay_ms), run)
    return True
