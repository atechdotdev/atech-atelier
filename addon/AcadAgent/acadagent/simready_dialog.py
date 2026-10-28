"""simready_dialog - "Install from NVIDIA SimReady..." on the Modules page.

Search NVIDIA's SimReady assets (CC BY 4.0) from the index shipped with
Atelier, see one's picture, size and licence, and install it into the
user's own parts (projects/simready.py does the work: download, hash check,
USD -> STL in a child process, user_parts.import_part).

Downloads run on a worker thread; the dialog stays responsive and says what
it is doing. Nothing is fetched until the user selects (a thumbnail) or
installs (the geometry).
"""
import os

from . import export_tools

#: "Fits on a desk": the largest side, mm. Atech products are hand-sized.
DESK_MM = 300.0

#: Workers still running. A QThread destroyed while it runs aborts the app,
#: so they are held here, not by the dialog, until they finish (closing the
#: dialog mid-install lets the install finish in the background).
_RUNNING = []


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("AcadAgent SimReady: %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def size_text(size):
    """[x, y, z] mm -> '17.5 × 53.4 × 27 mm' (x × height × depth)."""
    if not size:
        return "size unknown"
    return "%s mm" % " × ".join("%g" % round(v, 1) for v in size)


def row_text(name, entry, installed, label):
    t = "%s   ·   %s" % (label(name), size_text(entry.get("size_mm")))
    return t + ("   ·   installed" if installed else "")


def _thumb_dir():
    try:
        import FreeCAD
        return os.path.join(FreeCAD.getUserAppDataDir(), "cache", "simready")
    except Exception:                                  # noqa: BLE001
        import tempfile
        return os.path.join(tempfile.gettempdir(), "atelier_simready")


def SimReadyDialog(parent=None, on_done=None, sr=None):
    """The dialog. on_done(part_name) runs after an install. sr: the
    projects/simready module (imported from the library folder when None)."""
    from PySide6 import QtCore, QtGui, QtWidgets

    if sr is None:
        import simready as sr                         # projects/ is on sys.path

    class Worker(QtCore.QThread):
        progress = QtCore.Signal(str, float)
        finished_ok = QtCore.Signal(str)
        failed = QtCore.Signal(str)

        def __init__(self, fn, parent=None):
            super().__init__(parent)
            self.fn = fn

        def run(self):
            try:
                self.finished_ok.emit(str(self.fn(self._say) or ""))
            except Exception as exc:                   # noqa: BLE001
                _log("worker: %r" % (exc,))
                self.failed.emit(str(exc))

        def _say(self, text, frac):
            self.progress.emit(text, -1.0 if frac is None else float(frac))

    d = export_tools._tool_dialog(QtWidgets.QDialog, parent,
                                  "Install from NVIDIA SimReady")
    d.resize(720, 520)
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(8)
    t = QtWidgets.QLabel("Install from NVIDIA SimReady", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel(
        "Real-object models from NVIDIA's SimReady library (CC BY 4.0): "
        "batteries, fuses, bulbs, sensors, bolts and more. An installed part "
        "joins your parts; the agent designs around it.", d)
    sub.setObjectName("ToolMuted")
    sub.setWordWrap(True)
    lay.addWidget(sub)

    row = QtWidgets.QHBoxLayout()
    d.query = QtWidgets.QLineEdit(d)
    d.query.setPlaceholderText("Search: battery, fuse, camera, bolt m4…")
    d.query.setClearButtonEnabled(True)
    d.query.setAccessibleName("Search SimReady assets")
    row.addWidget(d.query, 1)
    d.only_elec = QtWidgets.QCheckBox("Electrical only", d)
    d.only_elec.setChecked(True)
    row.addWidget(d.only_elec)
    d.only_desk = QtWidgets.QCheckBox("Fits on a desk", d)
    d.only_desk.setChecked(True)
    d.only_desk.setToolTip("Largest side %g mm or less" % DESK_MM)
    row.addWidget(d.only_desk)
    lay.addLayout(row)

    body = QtWidgets.QHBoxLayout()
    d.list = QtWidgets.QListWidget(d)
    d.list.setAccessibleName("SimReady assets")
    body.addWidget(d.list, 3)
    side = QtWidgets.QVBoxLayout()
    d.thumb = QtWidgets.QLabel(d)
    d.thumb.setFixedSize(220, 220)
    d.thumb.setAlignment(QtCore.Qt.AlignCenter)
    d.thumb.setAccessibleName("Picture of the selected asset")
    side.addWidget(d.thumb)
    d.info = QtWidgets.QLabel("", d)
    d.info.setObjectName("ToolMuted")
    d.info.setWordWrap(True)
    d.info.setTextFormat(QtCore.Qt.PlainText)
    d.info.setFixedWidth(220)
    side.addWidget(d.info)
    side.addStretch(1)
    body.addLayout(side)
    lay.addLayout(body, 1)

    d.count = QtWidgets.QLabel("", d)
    d.count.setObjectName("ToolMuted")
    lay.addWidget(d.count)
    d.bar = QtWidgets.QProgressBar(d)
    d.bar.setTextVisible(False)
    d.bar.setFixedHeight(6)
    d.bar.hide()
    lay.addWidget(d.bar)
    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    d.status.setTextFormat(QtCore.Qt.PlainText)
    lay.addWidget(d.status)
    btns = QtWidgets.QHBoxLayout()
    credit = QtWidgets.QLabel("Models © NVIDIA, CC BY 4.0", d)
    credit.setObjectName("ToolMuted")
    btns.addWidget(credit)
    btns.addStretch(1)
    d.btn_close = QtWidgets.QPushButton("Close", d)
    d.btn_close.setAutoDefault(False)
    d.btn_close.clicked.connect(d.reject)
    btns.addWidget(d.btn_close)
    d.btn_install = QtWidgets.QPushButton("Install", d)
    d.btn_install.setObjectName("ToolPrimary")
    d.btn_install.setEnabled(False)
    btns.addWidget(d.btn_install)
    lay.addLayout(btns)

    d.workers = []
    d.installed_name = None
    d._thumb_for = None

    def current():
        it = d.list.currentItem()
        return it.data(QtCore.Qt.UserRole) if it is not None else None

    def refill():
        try:
            have = sr.installed()
        except Exception:                              # noqa: BLE001
            have = {}
        rows = sr.search(d.query.text(), electrical=d.only_elec.isChecked(),
                         max_mm=DESK_MM if d.only_desk.isChecked() else None)
        d.list.clear()
        for name, e in rows:
            it = QtWidgets.QListWidgetItem(row_text(name, e, name in have, sr.label))
            it.setData(QtCore.Qt.UserRole, name)
            d.list.addItem(it)
        total = sr.index().get("count") or len(sr.index()["assets"])
        d.count.setText("%d of %d assets%s" % (
            len(rows), total, " (first 200 shown)" if len(rows) >= 200 else ""))
        if rows:
            d.list.setCurrentRow(0)
        else:
            d.btn_install.setEnabled(False)
            d.info.setText("Nothing matches. Clear a filter or try another word.")
            d.thumb.clear()

    def run(fn, ok, busy_text):
        w = Worker(fn)
        w.progress.connect(lambda text, frac: progress(text, frac))
        w.finished_ok.connect(ok)
        w.failed.connect(failed)
        w.finished.connect(lambda: _RUNNING.remove(w) if w in _RUNNING else None)
        _RUNNING.append(w)
        d.workers.append(w)
        if busy_text:
            d.status.setText(busy_text)
        w.start()
        return w

    def progress(text, frac):
        d.status.setText(text)
        d.bar.show()
        if frac < 0:
            d.bar.setRange(0, 0)
        else:
            d.bar.setRange(0, 1000)
            d.bar.setValue(int(frac * 1000))

    def failed(msg):
        d.bar.hide()
        d.status.setText(msg)
        d.btn_install.setEnabled(current() is not None)
        d.list.setEnabled(True)

    def selected():
        name = current()
        d.btn_install.setEnabled(name is not None and not d.bar.isVisible())
        if name is None:
            return
        e = sr.index()["assets"].get(name) or {}
        # Size and mass are NVIDIA's figures for its simulation model, said
        # as such: some are far from the real part (a car battery at 897 g).
        bits = [sr.label(name), "NVIDIA's model: %s" % size_text(e.get("size_mm"))]
        if e.get("mass_kg"):
            bits.append("NVIDIA's mass: %s" % ("%g g" % round(e["mass_kg"] * 1000, 1)
                                               if e["mass_kg"] < 1
                                               else "%g kg" % e["mass_kg"]))
        if e.get("bytes"):
            bits.append("download %.1f MB" % (e["bytes"] / 1e6))
        bits.append("NVIDIA SimReady · CC BY 4.0")
        bits.append(name)
        d.info.setText("\n".join(bits))
        d.thumb.setText("…")
        d._thumb_for = name

        def fetch(_say, n=name):
            return sr.thumbnail(n, _thumb_dir()) or ""

        def shown(path, n=name):
            if d._thumb_for != n:
                return
            pm = QtGui.QPixmap(path) if path else QtGui.QPixmap()
            if pm.isNull():
                d.thumb.setText("No picture")
            else:
                d.thumb.setPixmap(pm.scaled(220, 220, QtCore.Qt.KeepAspectRatio,
                                            QtCore.Qt.SmoothTransformation))
        w = run(fetch, shown, "")
        w.failed.disconnect()
        w.failed.connect(lambda _m, n=name: d.thumb.setText("No picture")
                         if d._thumb_for == n else None)

    def install():
        name = current()
        if name is None:
            return
        d.btn_install.setEnabled(False)
        d.list.setEnabled(False)
        progress("Starting…", -1)

        def work(say, n=name):
            part, _sp = sr.install(n, progress=say)
            return part

        def done(part):
            d.bar.hide()
            d.list.setEnabled(True)
            d.installed_name = part
            d.status.setText("Installed. It is in your parts on the Modules page.")
            refill()
            if on_done is not None:
                on_done(part)
        run(work, done, "Starting…")

    d.query.textChanged.connect(lambda _t: refill())
    d.only_elec.toggled.connect(lambda _b: refill())
    d.only_desk.toggled.connect(lambda _b: refill())
    d.list.currentRowChanged.connect(lambda _r: selected())
    d.list.itemDoubleClicked.connect(lambda _it: install())
    d.btn_install.clicked.connect(install)
    d.refill = refill
    d.install = install
    refill()
    return d
