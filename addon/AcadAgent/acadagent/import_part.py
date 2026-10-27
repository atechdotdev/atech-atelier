"""import_part - the "Import part..." dialog of the Modules page.

Brings a part that is not an Atech module (an Arduino, a Raspberry Pi, a
battery holder, a servo, a sensor board from another maker) into the user's
own parts library (projects/user_parts.py). The geometry is measured; what
the user types about its wiring is kept as their declaration and handed to
the agent as one.

The dialog only collects answers; user_parts.import_part does the work, so
the same import is scriptable and testable without Qt.
"""
import os

from . import export_tools


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("AcadAgent import part: %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


#: Units offered for a file: (label, scale to mm).
UNITS = (("Millimetres", 1.0), ("Inches", 25.4), ("Centimetres", 10.0),
         ("Metres", 1000.0))

CATEGORY_LABELS = (
    ("electronics", "Electronics (board, sensor, display)"),
    ("power", "Power (battery, holder, regulator)"),
    ("motor", "Motor or servo"),
    ("wheel", "Wheel"),
    ("mechanical", "Mechanical (bearing, screw, magnet)"),
    ("module", "Module with an Atech 6-pin header"),
)

INTERFACE_LABELS = (
    ("", "Not stated"), ("none", "No wiring"), ("power", "Power only"),
    ("gpio", "Digital pin (GPIO)"), ("analog", "Analog"), ("pwm", "PWM"),
    ("i2c", "I2C"), ("spi", "SPI"), ("uart", "Serial (UART)"),
    ("usb", "USB"), ("other", "Other"),
)

FILE_FILTER = ("3D files (*.step *.stp *.iges *.igs *.brep *.stl *.obj *.ply "
               "*.3mf *.amf *.off);;All files (*)")


def answers_to_kwargs(a):
    """The import_part() keyword arguments for the dialog's answers `a`
    (a plain dict: display_name, category, interface, voltage, current,
    connectors, wiring, notes, licence, url, units_scale, recentre).
    Raises ValueError for a voltage or current that is not a number."""
    elec = {}
    if a.get("interface"):
        elec["interface"] = a["interface"]
    for key, field in (("voltage", "voltage_v"), ("current", "current_ma")):
        txt = (a.get(key) or "").strip().replace(",", ".")
        if txt:
            try:
                v = float(txt)
            except ValueError:
                raise ValueError("%s %r is not a number" % (key, txt))
            elec[field] = int(v) if v.is_integer() else v
    for key in ("connectors", "wiring"):
        txt = (a.get(key) or "").strip()
        if txt:
            elec[key] = txt
    return {
        "display_name": (a.get("display_name") or "").strip(),
        "category": a.get("category") or "electronics",
        "electrical": elec or None,
        "agent_notes": (a.get("notes") or "").strip(),
        "licence": (a.get("licence") or "").strip(),
        "source_url": (a.get("url") or "").strip(),
        "scale": float(a.get("units_scale") or 1.0),
        "recentre": bool(a.get("recentre", True)),
    }


def ImportPartDialog(parent=None, path=None, on_done=None, user_parts=None):
    """The dialog, for the file at `path` (asked for when None). on_done(name)
    runs after a successful import. user_parts: the projects/user_parts
    module (imported from the library folder when None)."""
    from PySide6 import QtCore, QtWidgets

    if user_parts is None:
        import user_parts                             # projects/ is on sys.path
    if path is None:
        path, _f = QtWidgets.QFileDialog.getOpenFileName(
            parent, "Import a part", os.path.expanduser("~"), FILE_FILTER)
        if not path:
            return None

    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Import part")
    d.path = path
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(8)
    t = QtWidgets.QLabel("Import part", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel(
        "Add a part that is not an Atech module to your own library: a board, "
        "a battery, a motor. Its size is measured from the file. What you say "
        "about its wiring helps the agent design around it.", d)
    sub.setObjectName("ToolMuted")
    sub.setWordWrap(True)
    lay.addWidget(sub)
    f = QtWidgets.QLabel(os.path.basename(path), d)
    f.setObjectName("ToolMuted")
    f.setTextFormat(QtCore.Qt.PlainText)
    lay.addWidget(f)

    form = QtWidgets.QFormLayout()
    form.setSpacing(6)
    d.name = QtWidgets.QLineEdit(os.path.splitext(os.path.basename(path))[0], d)
    d.name.setAccessibleName("Part name")
    form.addRow("Name", d.name)
    d.category = QtWidgets.QComboBox(d)
    for key, label in CATEGORY_LABELS:
        d.category.addItem(label, key)
    d.category.setAccessibleName("Kind of part")
    form.addRow("Kind", d.category)
    d.units = QtWidgets.QComboBox(d)
    for label, sc in UNITS:
        d.units.addItem(label, sc)
    d.units.setAccessibleName("Units of the file")
    form.addRow("File units", d.units)
    d.interface = QtWidgets.QComboBox(d)
    for key, label in INTERFACE_LABELS:
        d.interface.addItem(label, key)
    d.interface.setAccessibleName("How it connects")
    form.addRow("Connects by", d.interface)
    d.voltage = QtWidgets.QLineEdit(d)
    d.voltage.setPlaceholderText("e.g. 5")
    d.voltage.setAccessibleName("Supply voltage in volts")
    form.addRow("Voltage (V)", d.voltage)
    d.current = QtWidgets.QLineEdit(d)
    d.current.setPlaceholderText("optional")
    d.current.setAccessibleName("Current in milliamps")
    form.addRow("Current (mA)", d.current)
    d.connectors = QtWidgets.QLineEdit(d)
    d.connectors.setPlaceholderText("e.g. micro-USB on the -X end, 2x15 pin headers")
    d.connectors.setAccessibleName("Connectors and where they are")
    form.addRow("Connectors", d.connectors)
    d.wiring = QtWidgets.QLineEdit(d)
    d.wiring.setPlaceholderText("e.g. I2C to the Atech board by Qwiic cable")
    d.wiring.setAccessibleName("How it is wired")
    form.addRow("Wiring", d.wiring)
    d.notes = QtWidgets.QPlainTextEdit(d)
    d.notes.setPlaceholderText("Anything the design must respect: keep the "
                               "antenna clear, the LED must show, M2.5 holes "
                               "at the corners...")
    d.notes.setFixedHeight(70)
    d.notes.setAccessibleName("Notes for the design")
    form.addRow("Design notes", d.notes)
    d.licence = QtWidgets.QLineEdit(d)
    d.licence.setPlaceholderText("optional, e.g. CC BY-SA 4.0")
    form.addRow("File licence", d.licence)
    d.url = QtWidgets.QLineEdit(d)
    d.url.setPlaceholderText("optional: where the file came from")
    form.addRow("Source", d.url)
    d.recentre = QtWidgets.QCheckBox("Centre it like the Atech modules", d)
    d.recentre.setChecked(True)
    d.recentre.setToolTip("Move the part so it stands on y = 0, centred in x "
                          "and z. Off keeps the file's own origin.")
    form.addRow("", d.recentre)
    lay.addLayout(form)

    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    d.status.setTextFormat(QtCore.Qt.PlainText)
    lay.addWidget(d.status)
    row = QtWidgets.QHBoxLayout()
    row.addStretch(1)
    d.btn_cancel = QtWidgets.QPushButton("Cancel", d)
    d.btn_cancel.setAutoDefault(False)
    d.btn_cancel.clicked.connect(d.reject)
    row.addWidget(d.btn_cancel)
    d.btn_ok = QtWidgets.QPushButton("Import", d)
    d.btn_ok.setObjectName("ToolPrimary")
    d.btn_ok.setDefault(True)
    row.addWidget(d.btn_ok)
    lay.addLayout(row)

    def answers():
        return {
            "display_name": d.name.text(),
            "category": d.category.currentData(),
            "interface": d.interface.currentData(),
            "voltage": d.voltage.text(), "current": d.current.text(),
            "connectors": d.connectors.text(), "wiring": d.wiring.text(),
            "notes": d.notes.toPlainText(), "licence": d.licence.text(),
            "url": d.url.text(), "units_scale": d.units.currentData(),
            "recentre": d.recentre.isChecked(),
        }

    def run():
        try:
            kw = answers_to_kwargs(answers())
        except ValueError as exc:
            d.status.setText(str(exc))
            return
        if not kw["display_name"]:
            d.status.setText("Give the part a name.")
            return
        d.status.setText("Reading %s..." % os.path.basename(path))
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        QtWidgets.QApplication.processEvents()
        try:
            entry = user_parts.import_part(path, **kw)
        except Exception as exc:                       # noqa: BLE001
            _log("import %s: %r" % (path, exc))
            d.status.setText(str(exc))
            return
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        name = os.path.splitext(entry["file"])[0]
        d.imported = name
        d.accept()
        if on_done is not None:
            on_done(name)

    d.imported = None
    d.run = run
    d.answers = answers
    d.btn_ok.clicked.connect(run)
    return d
