"""chrome — strips FreeCAD's toolbar rows while the agent workbench is active.

Every command stays reachable from the menu bar (File, Edit, View, Atech
...); only the icon/text rows above the viewport go. Deactivating the
workbench puts back exactly the toolbars this module hid, so switching to
Part or Sketcher gets FreeCAD's normal chrome.

PERSISTENCE TRAP. FreeCAD saves each toolbar's visibility to
User parameter:BaseApp/MainWindow/Toolbars and re-applies it on every
workbench switch. MEASURED: hiding File/Edit/View here and switching to Part
left them hidden in Part, because FreeCAD had recorded File=False etc.

So the whole Toolbars group is SNAPSHOTTED before anything is hidden, and
written back on deactivate AND at quit (R30). The snapshot is also kept in
our own parameter group until it has been written back, so a session that
crashes inside Atech (no deactivate, no aboutToQuit) still restores the
user's toolbars on the next deactivate instead of re-snapshotting the
polluted False values. A clean write-back clears it: kept longer, it goes
stale and undoes changes the user makes in other workbenches.

Hiding is event-driven (S03): each toolbar gets an event filter that hides
it again when FreeCAD shows it, and the main window is watched for new
toolbars. Nothing is hidden while the chrome is inactive, so a deferred
hide cannot fire into the next workbench (R30).
"""
import json

from PySide6 import QtCore, QtWidgets

_HIDDEN = []      # QToolBar objects we hid
_NAMES = set()    # their objectNames, which is the parameter key
_ACTIVE = [False]  # hide only while the Atech chrome is installed
_FILTER = []      # the one live _ToolbarFilter, if any

_PARAM = "User parameter:BaseApp/MainWindow/Toolbars"
_OWN = "User parameter:BaseApp/Preferences/Mod/AcadAgent"
_SNAP_KEY = "ToolbarsSnapshot"


def _main_window():
    import FreeCADGui
    return FreeCADGui.getMainWindow()


# ------------------------------------------------------------ snapshot
def _read_group():
    """{name: bool} of the Toolbars group, or {} when it cannot be read."""
    try:
        import FreeCAD
        rows = FreeCAD.ParamGet(_PARAM).GetContents() or []
    except Exception:                                  # noqa: BLE001
        return {}
    return {name: bool(val) for kind, name, val in rows if kind == "Boolean"}


def snapshot():
    """Record the Toolbars group before we hide anything. A snapshot left
    over from a session that never wrote it back (crash, kill) wins: the
    live values would already carry our False."""
    try:
        import FreeCAD
        own = FreeCAD.ParamGet(_OWN)
        if own.GetString(_SNAP_KEY, ""):
            return saved_snapshot()
        snap = _read_group()
        own.SetString(_SNAP_KEY, json.dumps(snap, sort_keys=True))
        return snap
    except Exception:                                  # noqa: BLE001
        return {}


def saved_snapshot():
    try:
        import FreeCAD
        raw = FreeCAD.ParamGet(_OWN).GetString(_SNAP_KEY, "")
        data = json.loads(raw) if raw else None
        return data if isinstance(data, dict) else None
    except Exception:                                  # noqa: BLE001
        return None


def write_back(clear=True):
    """Write the snapshot back into the Toolbars group.

    A toolbar present in the snapshot gets its recorded value, so a bar the
    user had hidden stays hidden. A toolbar we hid that the snapshot does
    not know gets True (FreeCAD's default). Returns the names written."""
    snap = saved_snapshot()
    try:
        import FreeCAD
        grp = FreeCAD.ParamGet(_PARAM)
    except Exception:                                  # noqa: BLE001
        return set()
    written = set()
    if snap is not None:
        for name, val in snap.items():
            grp.SetBool(name, bool(val))
            written.add(name)
    for name in _NAMES:
        if snap is None or name not in snap:
            grp.SetBool(name, True)
            written.add(name)
    if clear:
        try:
            FreeCAD.ParamGet(_OWN).RemString(_SNAP_KEY)
        except Exception:                                  # noqa: BLE001
            pass
    return written


# --------------------------------------------------------------- hiding
class _ToolbarFilter(QtCore.QObject):
    """Re-hides a toolbar the moment FreeCAD shows it, and watches the main
    window for toolbars added later (a workbench loading its own)."""

    def eventFilter(self, obj, ev):                    # noqa: N802
        t = ev.type()
        if not _ACTIVE[0]:
            return False
        if t == QtCore.QEvent.Show and isinstance(obj, QtWidgets.QToolBar):
            QtCore.QTimer.singleShot(0, hide_now)
        elif t == QtCore.QEvent.ChildAdded and \
                isinstance(ev.child(), QtWidgets.QToolBar):
            ev.child().installEventFilter(self)
            QtCore.QTimer.singleShot(0, hide_now)
        return False


def _filter():
    if not _FILTER:
        _FILTER.append(_ToolbarFilter())
    return _FILTER[0]


def hide_toolbars():
    """Hide every visible toolbar and keep them hidden until restore.

    Deferred once as well: FreeCAD lays out the workbench's toolbars AFTER
    Activated() returns. The Show filter catches every later re-show."""
    _ACTIVE[0] = True
    mw = _main_window()
    if mw is not None:
        f = _filter()
        mw.installEventFilter(f)
        for bar in mw.findChildren(QtWidgets.QToolBar):
            bar.installEventFilter(f)
    hide_now()
    for ms in (0, 150, 500):
        QtCore.QTimer.singleShot(ms, hide_now)


def active():
    return _ACTIVE[0]


def hide_now():
    """Hide whatever toolbar is visible right now; remember it for restore.
    A no-op once the chrome is inactive (a late timer after deactivate)."""
    if not _ACTIVE[0]:
        return
    mw = _main_window()
    if mw is None:
        return
    for bar in mw.findChildren(QtWidgets.QToolBar):
        if bar.isVisible():
            bar.hide()
            if bar not in _HIDDEN:
                _HIDDEN.append(bar)
            if bar.objectName():
                _NAMES.add(bar.objectName())


def restore_toolbars():
    """Show what we hid and write the snapshot back over what FreeCAD
    persisted about it. Works even when this session hid nothing (a
    profile that started inside Atech with False already persisted)."""
    _ACTIVE[0] = False
    mw = _main_window()
    if mw is not None and _FILTER:
        try:
            mw.removeEventFilter(_FILTER[0])
            for bar in mw.findChildren(QtWidgets.QToolBar):
                bar.removeEventFilter(_FILTER[0])
        except RuntimeError:
            pass
    snap = saved_snapshot() or {}
    names = set(_NAMES)
    write_back(clear=True)
    show = {n for n in names if snap.get(n, True)}
    _HIDDEN.clear()
    _NAMES.clear()
    if not show:
        return
    _restore(show)
    for ms in (0, 200, 600):
        QtCore.QTimer.singleShot(ms, lambda n=show, s=snap: _restore(n, s))


def _restore(names, snap=None):
    """Re-assert the values and re-show the bars, after FreeCAD's own
    toolbar setup for the next workbench has run."""
    if _ACTIVE[0]:
        return               # Atech was re-activated meanwhile
    try:
        import FreeCAD
        grp = FreeCAD.ParamGet(_PARAM)
        for n in names:
            grp.SetBool(n, True)
    except Exception:                                  # noqa: BLE001
        pass
    try:
        mw = _main_window()
        bars = mw.findChildren(QtWidgets.QToolBar) if mw is not None else []
    except RuntimeError:                               # window torn down
        return
    for bar in bars:
        try:
            if bar.objectName() in names and not bar.isVisible():
                bar.show()
        except RuntimeError:                           # C++ side deleted
            pass
