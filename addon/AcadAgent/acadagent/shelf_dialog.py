"""shelf_dialog - "Off-the-shelf parts..." on the Modules page.

Browse the curated off-the-shelf parts (Arduino, Raspberry Pi, servos,
batteries, switches, sensors... from the FreeCAD Parts Library, CC BY 3.0),
see one's picture, measured size, wiring and authors, and install it into
the user's own parts. projects/shelf.py does the work: download, blob-id
check, STEP meshed in a child freecadcmd, user_parts.import_part.

As simready_dialog: downloads run on a worker thread held in _RUNNING, and
nothing is fetched until the user selects (a picture) or installs.
"""
from . import export_tools
from .simready_dialog import _RUNNING, _log, _thumb_dir, size_text


def row_text(entry, installed):
    t = "%s   ·   %s" % (entry.get("display_name"), size_text(entry.get("size_mm")))
    return t + ("   ·   installed" if installed else "")


def wiring_text(elec):
    """{'interface': 'pwm', 'voltage_v': 5, 'wiring': '...'} -> 'PWM · 5 V · ...'."""
    e = elec or {}
    bits = []
    if e.get("interface") and e["interface"] not in ("none", "other"):
        bits.append(e["interface"].upper() if len(e["interface"]) <= 4
                    else e["interface"])
    if e.get("voltage_v") is not None:
        bits.append("%g V" % e["voltage_v"])
    bits += [str(e[k]) for k in ("wiring", "connectors") if e.get(k)]
    return " · ".join(bits)


def _freecadcmd():
    try:
        from . import sandbox
        return sandbox.find_freecadcmd()
    except Exception:                                  # noqa: BLE001
        return None


def ShelfDialog(parent=None, on_done=None, shelf=None, freecadcmd=None):
    """The dialog. on_done(part_name) runs after an install. shelf: the
    projects/shelf module (imported from the library folder when None)."""
    from PySide6 import QtCore, QtGui, QtWidgets

    if shelf is None:
        import shelf                                   # projects/ is on sys.path
    fc = freecadcmd if freecadcmd is not None else _freecadcmd()

    class Worker(QtCore.QThread):
        progress = QtCore.Signal(str, float)
        finished_ok = QtCore.Signal(str)
        failed = QtCore.Signal(str)

        def __init__(self, fn):
            super().__init__(None)
            self.fn = fn

        def run(self):
            try:
                self.finished_ok.emit(str(self.fn(self._say) or ""))
            except Exception as exc:                   # noqa: BLE001
                _log("shelf worker: %r" % (exc,))
                self.failed.emit(str(exc))

        def _say(self, text, frac):
            self.progress.emit(text, -1.0 if frac is None else float(frac))

    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Off-the-shelf parts")
    d.resize(760, 540)
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(8)
    t = QtWidgets.QLabel("Off-the-shelf parts", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel(
        "Boards, sensors, motors, batteries, buttons, displays and connectors you "
        "can buy, as real 3D models. An installed part joins your parts; the agent "
        "designs around it.", d)
    sub.setObjectName("ToolMuted")
    sub.setWordWrap(True)
    lay.addWidget(sub)

    row = QtWidgets.QHBoxLayout()
    d.query = QtWidgets.QLineEdit(d)
    d.query.setPlaceholderText("Search: arduino, servo, battery, button…")
    d.query.setClearButtonEnabled(True)
    d.query.setAccessibleName("Search off-the-shelf parts")
    row.addWidget(d.query, 1)
    d.group = QtWidgets.QComboBox(d)
    d.group.setAccessibleName("Kind of part")
    d.group.addItem("All kinds", "")
    for key, text in shelf.GROUPS:
        d.group.addItem(text, key)
    row.addWidget(d.group)
    lay.addLayout(row)

    body = QtWidgets.QHBoxLayout()
    d.list = QtWidgets.QListWidget(d)
    d.list.setAccessibleName("Off-the-shelf parts")
    body.addWidget(d.list, 3)
    side = QtWidgets.QVBoxLayout()
    d.thumb = QtWidgets.QLabel(d)
    d.thumb.setFixedSize(220, 180)
    d.thumb.setAlignment(QtCore.Qt.AlignCenter)
    d.thumb.setAccessibleName("Picture of the selected part")
    side.addWidget(d.thumb)
    d.info = QtWidgets.QLabel("", d)
    d.info.setObjectName("ToolMuted")
    d.info.setWordWrap(True)
    d.info.setTextFormat(QtCore.Qt.PlainText)
    d.info.setFixedWidth(240)
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
    credit = QtWidgets.QLabel("Models from the FreeCAD Parts Library, CC BY 3.0", d)
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
            have = shelf.installed()
        except Exception:                              # noqa: BLE001
            have = {}
        rows = shelf.search(d.query.text(), group=d.group.currentData() or None)
        d.list.clear()
        for key, e in rows:
            it = QtWidgets.QListWidgetItem(row_text(e, key in have))
            it.setData(QtCore.Qt.UserRole, key)
            d.list.addItem(it)
        d.count.setText("%d of %d parts" % (len(rows), len(shelf.index()["parts"])))
        if rows:
            d.list.setCurrentRow(0)
        else:
            d.btn_install.setEnabled(False)
            d.info.setText("Nothing matches. Pick another kind or try another word.")
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
        key = current()
        d.btn_install.setEnabled(key is not None and not d.bar.isVisible())
        if key is None:
            return
        e = shelf.index()["parts"].get(key) or {}
        bits = [e.get("display_name", key), e.get("description", ""),
                "Measured: %s" % size_text(e.get("size_mm"))]
        wiring = wiring_text(e.get("electrical"))
        if wiring:
            bits.append("Wiring: %s" % wiring)
        bits.append("download %.1f MB" % (e.get("bytes", 0) / 1e6))
        if e.get("authors"):
            bits.append("By %s · CC BY 3.0" % ", ".join(e["authors"]))
        d.info.setText("\n".join(b for b in bits if b))
        has = getattr(shelf, "has_picture", lambda x: bool(x.get("thumb")))(e)
        d.thumb.setText("…" if has else "No picture")
        d._thumb_for = key
        if not has:
            return

        def fetch(_say, k=key):
            return shelf.thumbnail(k, _thumb_dir()) or ""

        def shown(path, k=key):
            if d._thumb_for != k:
                return
            pm = QtGui.QPixmap(path) if path else QtGui.QPixmap()
            if pm.isNull():
                d.thumb.setText("No picture")
            else:
                d.thumb.setPixmap(pm.scaled(220, 180, QtCore.Qt.KeepAspectRatio,
                                            QtCore.Qt.SmoothTransformation))
        w = run(fetch, shown, "")
        w.failed.disconnect()
        w.failed.connect(lambda _m, k=key: d.thumb.setText("No picture")
                         if d._thumb_for == k else None)

    def install():
        key = current()
        if key is None:
            return
        d.btn_install.setEnabled(False)
        d.list.setEnabled(False)
        progress("Starting…", -1)

        def work(say, k=key):
            part, _sp = shelf.install(k, progress=say, freecadcmd=fc)
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
    d.group.currentIndexChanged.connect(lambda _i: refill())
    d.list.currentRowChanged.connect(lambda _r: selected())
    d.list.itemDoubleClicked.connect(lambda _it: install())
    d.btn_install.clicked.connect(install)
    d.refill = refill
    d.install = install
    refill()
    return d
