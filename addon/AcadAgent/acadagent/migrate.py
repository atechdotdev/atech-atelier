"""migrate — carry the addon's own data over from "Atech Studio" once.

WHY THIS EXISTS
    FreeCAD keys the user-data folder on branding.xml's ExeName. The product
    was renamed from "Atech Studio" to "Atech Atelier" (ADR-005, owner
    decision 2026-10-03), so FreeCAD.getUserAppDataDir() moves from
        ~/.local/share/Atech Studio/v1-1/
    to
        ~/.local/share/Atech Atelier/v1-1/
    and everything the addon kept under the old one would look lost.

WHAT IS COPIED (and only this)
    AcadAgent/trusted_builds.json   the trust store (build._trust_path):
                                    which agent-built objects ran from a
                                    script the user accepted (R11)
    agent/sessions.json             the chat index (panel.sessions_path):
                                    document Uid -> chat folder + Claude
                                    session, so a reopened document continues
                                    its chat (S07)
    The chat folders themselves are NOT copied: sessions.json stores absolute
    paths, and the old tree is never deleted, so the copied index keeps
    pointing at folders that still exist (panel._restore_state only checks
    os.path.isdir).

WHAT DOES NOT NEED IT
    The addon's settings file (settings.CONFIG_PATH, ~/.config/acadagent/
    settings.json: engine, model, budget, privacy acknowledgement) is not
    keyed on ExeName and does not move.

WHAT THE LAUNCHER DOES FIRST, AND WHY THIS STILL EXISTS
    The AppImage's AppRun (branding/apprun_migrate_block.sh) copies the
    whole old data and config trees before FreeCAD starts, but only when the
    new folder does not exist yet; it is also the only place FreeCAD's own
    preferences (user.cfg, read before any addon runs) can be carried over.
    This module covers what that leaves: a new folder that already existed
    (FreeCAD created it on a start without that block - a dev launch, an
    image built before it) but holds none of the addon's data.
    ATECH_MIGRATE=0 turns this off too, as it does the AppRun block. After AppRun copied a tree this finds the addon data already in
    place and only records "skipped".

RULES
    - Copy, never move; the old tree is never modified or deleted.
    - Once: a marker file (MARKER, in <new>/AcadAgent/) records the outcome.
      A run that could not copy everything says "partial" and the next start
      retries only what is still missing.
    - If the new folder already holds addon data and there is no marker, the
      user has been working in the new folder: nothing is copied (an old file
      would overwrite newer state) and the marker says "skipped".
    - Never raises: a failed migration costs the user their old chats, never
      the start of the app.
"""
import json
import os
import shutil
import time

OLD_NAME = "Atech Studio"
MARKER = "migrated_from_atech_studio.json"
ITEMS = (os.path.join("AcadAgent", "trusted_builds.json"),
         os.path.join("agent", "sessions.json"))

DONE, PARTIAL, SKIPPED = "done", "partial", "skipped"


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[AcadAgent migrate] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def new_root():
    """FreeCAD's user data dir for this ExeName, or None outside FreeCAD."""
    try:
        import FreeCAD
        return FreeCAD.getUserAppDataDir()
    except Exception:                                  # noqa: BLE001
        return None


def old_root_for(new, old_name=OLD_NAME):
    """The "Atech Studio" folder matching `new`, or None when `new` IS that
    folder (the image still carries the old ExeName).

    FreeCAD 1.1 appends a version folder: .../<ExeName>/v1-1. The same
    version folder is used under the old name; an unversioned `new` maps to
    the unversioned old folder."""
    if not new:
        return None
    new = os.path.normpath(new)
    leaf, parent = os.path.basename(new), os.path.dirname(new)
    if leaf.startswith("v") and leaf[1:2].isdigit():
        if os.path.basename(parent) == old_name:
            return None
        return os.path.join(os.path.dirname(parent), old_name, leaf)
    if leaf == old_name:
        return None
    return os.path.join(parent, old_name)


def marker_path(new):
    return os.path.join(new, "AcadAgent", MARKER)


def read_marker(new):
    try:
        with open(marker_path(new), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _write_marker(new, record):
    path = marker_path(new)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        _log("marker not written: %r" % (exc,))
        return False


def _copy(src, dst):
    """Copy one file atomically (tmp + replace), keeping its mode: the trust
    store and the chat index are written 0600 and stay that way."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".migrating"
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _is_file(p):
    return os.path.isfile(p) and not os.path.islink(p)


def migrate(new=None, old=None, items=ITEMS):
    """Run the one-time copy. Returns a record dict; its "status" is one of
    "done", "partial", "skipped", or "nothing" (no old data, or no rename),
    or "already" (a marker from an earlier run said done/skipped)."""
    try:
        return _migrate(new, old, items)
    except Exception as exc:                           # noqa: BLE001
        _log("migration failed: %r" % (exc,))
        return {"status": "error", "error": repr(exc)}


def _migrate(new, old, items):
    if os.environ.get("ATECH_MIGRATE", "1") == "0":
        return {"status": "nothing", "why": "ATECH_MIGRATE=0"}
    new = new or new_root()
    if not new:
        return {"status": "nothing", "why": "no user data dir"}
    old = old or old_root_for(new)
    if not old or os.path.normpath(old) == os.path.normpath(new):
        return {"status": "nothing", "why": "user data dir not renamed"}
    prev = read_marker(new)
    if prev and prev.get("status") in (DONE, SKIPPED):
        return {"status": "already", "marker": prev}
    have_old = [i for i in items if _is_file(os.path.join(old, i))]
    if not have_old:
        return {"status": "nothing", "why": "no addon data in %s" % old}
    have_new = [i for i in items if os.path.exists(os.path.join(new, i))]
    record = {"from": os.path.normpath(old), "to": os.path.normpath(new),
              "t": int(time.time()),
              "copied": [], "kept_new": [], "failed": []}
    if have_new and prev is None:
        # The user already works in the new folder: never overwrite it.
        record.update(status=SKIPPED, kept_new=have_new)
        _write_marker(new, record)
        _log("not migrated: %s already holds %s" % (new, ", ".join(have_new)))
        return record
    if prev:                                 # a partial run: keep its copies
        record["copied"] = list(prev.get("copied") or [])
    for item in have_old:
        dst = os.path.join(new, item)
        if os.path.exists(dst):
            if item not in record["copied"]:
                record["kept_new"].append(item)
            continue
        try:
            _copy(os.path.join(old, item), dst)
            record["copied"].append(item)
        except OSError as exc:
            record["failed"].append(item)
            _log("could not copy %s: %r" % (item, exc))
    record["status"] = PARTIAL if record["failed"] else DONE
    _write_marker(new, record)
    _log("migrated from %s: %s" % (old, record))
    return record
