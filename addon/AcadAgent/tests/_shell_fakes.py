"""Stand-ins for FreeCAD, FreeCADGui and the chat panel, for headless shell tests.

The shell (shell.py, chrome.py, viewport.py) only talks to FreeCAD through a
handful of calls: ParamGet groups, getMainWindow, runCommand,
Control.activeDialog, getUserCachePath, Console. These fakes implement exactly
those, with the same method names and GetContents() type strings MEASURED on
the bundled FreeCAD 1.1.3 (Boolean, Integer, Unsigned Long, Float, String),
so the shell code under test is the code that ships.

The fake AgentPanel owns a QThread parented to itself and RUNNING - the exact
shape that aborted FreeCAD on a workbench switch (R18): a parent deleted
under a running QThread prints "QThread: Destroyed while thread is still
running" and calls abort().

Run under the AppImage's bundled interpreter (Python 3.11 + PySide6 6.8.3):
    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python -m unittest ...
"""
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.abspath(os.path.join(HERE, ".."))
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets  # noqa: E402

_TYPES = {"Bool": "Boolean", "Int": "Integer", "Unsigned": "Unsigned Long",
          "Float": "Float", "String": "String"}
_DEFAULTS = {"Bool": False, "Int": 0, "Unsigned": 0, "Float": 0.0, "String": ""}


class Group:
    def __init__(self):
        self.v = {}          # (kind, name) -> value

    def GetContents(self):                             # noqa: N802
        if not self.v:
            return None      # measured: an empty group returns None, not []
        return [(_TYPES[k], n, val) for (k, n), val in self.v.items()]

    def __getattr__(self, attr):
        for verb in ("Get", "Set", "Rem"):
            if attr.startswith(verb) and attr[3:] in _TYPES:
                kind = attr[3:]
                if verb == "Get":
                    return lambda n, d=None, k=kind: self.v.get(
                        (k, n), _DEFAULTS[k] if d is None else d)
                if verb == "Set":
                    return lambda n, val, k=kind: self.v.__setitem__((k, n), val)
                return lambda n, k=kind: self.v.pop((k, n), None)
        raise AttributeError(attr)


class Params:
    def __init__(self):
        self.groups = {}

    def __call__(self, path):
        return self.groups.setdefault(path, Group())


class _Console:
    def __init__(self):
        self.lines = []

    def _p(self, s):
        self.lines.append(s)

    PrintLog = PrintMessage = PrintWarning = PrintError = _p


def install_fakes(mw):
    """Register fake FreeCAD / FreeCADGui modules bound to main window `mw`."""
    cache = tempfile.mkdtemp(prefix="atech-test-cache-")
    fc = types.ModuleType("FreeCAD")
    fc.ParamGet = Params()
    fc.Console = _Console()
    fc.getUserCachePath = lambda: cache + os.sep
    fc.listDocuments = lambda: {}
    fc.ActiveDocument = None
    fc.getHomePath = lambda: cache
    fc.newDocument = lambda *a: None

    gui = types.ModuleType("FreeCADGui")
    gui.getMainWindow = lambda: mw
    gui.commands = []
    gui.runCommand = lambda name, *a: gui.commands.append(name)
    gui.dialog = [False]

    class _Control:
        @staticmethod
        def activeDialog():                            # noqa: N802
            return gui.dialog[0]

    gui.Control = _Control
    gui.getDocument = lambda name: None
    gui.ActiveDocument = None
    sys.modules["FreeCAD"] = fc
    sys.modules["FreeCADGui"] = gui
    sys.modules.setdefault("Part", types.ModuleType("Part"))
    # modules that bound FreeCAD at import time must see this fake
    vp = sys.modules.get("acadagent.viewport")
    if vp is not None:
        vp.FreeCAD, vp.FreeCADGui = fc, gui
    return fc, gui


class _Spinner(QtCore.QThread):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.stop = False

    def run(self):
        # Cooperative like ChatWorker/HealthWorker: honours interruption.
        # Set .deaf = True to model a worker that will not stop.
        while not self.stop and (getattr(self, "deaf", False)
                                 or not self.isInterruptionRequested()):
            self.msleep(10)


class FakePanel(QtWidgets.QWidget):
    """AgentPanel's public surface, with a live worker parented to it."""
    instances = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.notices = []
        self.worker = _Spinner(self)       # the R18 shape: parent=self
        self.worker.start()
        FakePanel.instances.append(self)

    def restyle(self):
        pass

    def show_notice(self, title, body, actions=None, detail=None):
        self.notices.append((title, body, detail))

    def _on_capture(self):
        pass


class FakeModulesPage(QtWidgets.QWidget):
    def restyle(self):
        pass


def install_panel_stubs():
    panel = types.ModuleType("acadagent.panel")
    panel.AgentPanel = FakePanel
    mp = types.ModuleType("acadagent.modules_page")
    mp.ModulesPage = FakeModulesPage
    sys.modules["acadagent.panel"] = panel
    sys.modules["acadagent.modules_page"] = mp


def build_main_window(n_toolbars=40, n_status_labels=6):
    """A QMainWindow shaped like FreeCAD's: many toolbars, a Model dock with a
    tree, a Tasks dock, an MDI area with one subwindow, a status bar with a
    pixmap mark among plain labels, and a workbench selector in the menubar
    corner."""
    from PySide6 import QtGui
    mw = QtWidgets.QMainWindow()
    mdi = QtWidgets.QMdiArea()
    mw.setCentralWidget(mdi)
    for i in range(n_toolbars):
        tb = QtWidgets.QToolBar("tb%d" % i)
        tb.setObjectName(["File", "Edit", "View", "Workbench", "Macro"][i]
                         if i < 5 else "Toolbar%d" % i)
        tb.addAction("a%d" % i)
        mw.addToolBar(tb)
    model = QtWidgets.QDockWidget("Model", mw)
    model.setObjectName("Model")
    tree = QtWidgets.QTreeWidget()
    tree.setObjectName("ModelTree")
    model.setWidget(tree)
    mw.addDockWidget(QtCore.Qt.LeftDockWidgetArea, model)
    tasks = QtWidgets.QDockWidget("Tasks", mw)
    tasks.setObjectName("Tasks")
    tasks.setWidget(QtWidgets.QWidget())
    mw.addDockWidget(QtCore.Qt.RightDockWidgetArea, tasks)
    sb = mw.statusBar()
    for i in range(n_status_labels):
        lbl = QtWidgets.QLabel("status %d" % i)
        if i == 0:
            pm = QtGui.QPixmap(64, 20)
            pm.fill(QtCore.Qt.black)
            lbl.setPixmap(pm)
            lbl.setFixedWidth(64)
        sb.addPermanentWidget(lbl)
    selector = QtWidgets.QComboBox(mw.menuBar())   # parented: kept alive
    selector.setObjectName("WorkbenchSelector")
    selector.addItem("Part")
    mw.menuBar().addMenu("File")
    mw.menuBar().setCornerWidget(selector, QtCore.Qt.TopRightCorner)
    mw.resize(1400, 900)
    mw.show()
    sub = mdi.addSubWindow(QtWidgets.QWidget())
    sub.show()
    return mw


def pump(ms=50):
    """Run the event loop for `ms` milliseconds (deferred timers, deleteLater)."""
    app = QtWidgets.QApplication.instance()
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()
    app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    app.processEvents()
