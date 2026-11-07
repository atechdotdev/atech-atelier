"""makerworld - bring models in from MakerWorld and publish to it (R900).

MakerWorld (Bambu Lab's model site) has no public API: no sign-in for
other apps, no upload, and downloads only from a signed-in browser. So
Atelier works with files and the browser, never with MakerWorld's private
endpoints or the user's cookies:

  From MakerWorld...   paste a model's link; Open its page downloads it in
                       the browser; Use my newest download (or Choose
                       file...) adds it to the design (design_import) with
                       the link, the maker and the licence the page shows,
                       so the credit and the licence go with the design.
                       A Bambu Studio 3MF (objects in 3D/Objects/*.model)
                       is read here when FreeCAD's reader finds nothing.
  Publish to MakerWorld...
                       checks every imported part's licence first (the
                       Standard Digital File License forbids sharing, a
                       no-derivatives one forbids changes, share-alike and
                       non-commercial terms carry over), then makes the
                       upload in a folder: the model as 3MF and STEP, a
                       cover picture and description.txt (title,
                       description, "Remix of" credits, licence). Open in
                       Bambu Studio saves the print profile MakerWorld asks
                       for; Open MakerWorld is where the folder goes up.

parse_link, read_3mf, publish_plan and write_bundle are headless.
"""
import os
import re
import time
import xml.etree.ElementTree as ET
import zipfile

SITE = "https://makerworld.com"
#: MakerWorld's own upload button is on every page; no deep link to the
#: upload form is documented, so its home page opens.
UPLOAD_URL = SITE + "/en"
HELP_URL = "https://wiki.bambulab.com/en/makerworld/tutorials/how-to-upload-models"
MADE_WITH = "Made with Atech Atelier: https://atech.dev/atelier"
_LINK = re.compile(r"https?://(?:www\.)?makerworld\.com(\.cn)?/(?:[a-z]{2}(?:-[a-z]{2,4})?/)?"
                   r"models/(\d+)(?:-([A-Za-z0-9_-]+))?", re.I)
DOWNLOAD_EXT = (".3mf", ".stl", ".step", ".stp", ".obj")
MAX_3MF_TRIANGLES = 3000000


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[makerworld] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


# ------------------------------------------------------------------ links
def parse_link(text):
    """{"id", "slug", "title", "url"} for a MakerWorld model link, else None."""
    m = _LINK.search(text or "")
    if not m:
        return None
    cn, mid, slug = m.group(1), m.group(2), m.group(3) or ""
    base = SITE + (".cn" if cn else "")
    title = slug.replace("-", " ").replace("_", " ").strip()
    return {"id": mid, "slug": slug, "title": title[:1].upper() + title[1:],
            "url": "%s/en/models/%s%s" % (base, mid, ("-" + slug) if slug else "")}


def downloads_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads")


def newest_download(since=0.0, folder=None, exts=DOWNLOAD_EXT):
    """The newest model file in Downloads changed after `since` (a time),
    or None. A browser's half-written .crdownload / .part is not one."""
    folder = folder or downloads_dir()
    best = None
    try:
        names = os.listdir(folder)
    except OSError:
        return None
    for n in names:
        if not n.lower().endswith(exts):
            continue
        p = os.path.join(folder, n)
        try:
            t = os.path.getmtime(p)
        except OSError:
            continue
        if t >= since and os.path.isfile(p) and (best is None or t > best[0]):
            best = (t, p)
    return best[1] if best else None


# ------------------------------------------------------------------ 3MF
_CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
_PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"


def _matrix(text):
    """A 3MF transform ("m00 m01 m02 m10 ... m32") as a function on points."""
    if not text:
        return None
    v = [float(a) for a in text.split()]
    if len(v) != 12:
        return None

    def f(p):
        x, y, z = p
        return (x * v[0] + y * v[3] + z * v[6] + v[9],
                x * v[1] + y * v[4] + z * v[7] + v[10],
                x * v[2] + y * v[5] + z * v[8] + v[11])
    return f


def read_3mf(path):
    """[(name, [triangle, ...])] of a 3MF's build items, with components in
    other model parts (Bambu Studio's 3D/Objects/*.model) resolved and
    every transform applied. Each triangle is three (x, y, z) in mm."""
    with zipfile.ZipFile(path) as z:
        parts = {}

        def model(name):
            name = name.lstrip("/")
            if name not in parts:
                try:
                    root = ET.fromstring(z.read(name))
                except KeyError:
                    raise ValueError("%s is missing from the 3MF" % name)
                unit = root.get("unit", "millimeter")
                scale = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0,
                         "inch": 25.4, "foot": 304.8, "meter": 1000.0}.get(unit, 1.0)
                objs = {}
                for o in root.iter("{%s}object" % _CORE):
                    objs[o.get("id")] = o
                parts[name] = (root, objs, scale)
            return parts[name]

        count = [0]

        def tris(name, oid, xf, depth=0):
            if depth > 8:
                raise ValueError("components nest too deep")
            root, objs, scale = model(name)
            o = objs.get(oid)
            if o is None:
                raise ValueError("object %s is missing from %s" % (oid, name))
            out = []
            mesh = o.find("{%s}mesh" % _CORE)
            if mesh is not None:
                vs = [(float(v.get("x")) * scale, float(v.get("y")) * scale,
                       float(v.get("z")) * scale)
                      for v in mesh.iter("{%s}vertex" % _CORE)]
                for t in mesh.iter("{%s}triangle" % _CORE):
                    tri = [vs[int(t.get(k))] for k in ("v1", "v2", "v3")]
                    out.append([xf(p) for p in tri] if xf else tri)
                    count[0] += 1
                    if count[0] > MAX_3MF_TRIANGLES:
                        raise ValueError("more than %d triangles" % MAX_3MF_TRIANGLES)
            comps = o.find("{%s}components" % _CORE)
            if comps is not None:
                for c in comps.findall("{%s}component" % _CORE):
                    sub = c.get("{%s}path" % _PROD) or name
                    cf = _matrix(c.get("transform"))
                    if cf and xf:
                        f = (lambda a, b: lambda p: a(b(p)))(xf, cf)
                    else:
                        f = cf or xf
                    out += tris(sub, c.get("objectid"), f, depth + 1)
            return out

        main = "3D/3dmodel.model"
        if main not in z.namelist():
            rels = [n for n in z.namelist() if n.lower().endswith(".model")]
            if not rels:
                raise ValueError("no 3D model in the 3MF")
            main = rels[0]
        root, objs, _s = model(main)
        result = []
        build = root.find("{%s}build" % _CORE)
        items = build.findall("{%s}item" % _CORE) if build is not None else []
        for it in items:
            oid = it.get("objectid")
            o = objs.get(oid)
            name = (o.get("name") if o is not None else None) or "object %s" % oid
            t = tris(main, oid, _matrix(it.get("transform")))
            if t:
                result.append((name, t))
        return result


def mesh_from_3mf(path):
    """One Mesh.Mesh of every build item of a 3MF (read_3mf)."""
    import Mesh
    tris = []
    for _name, t in read_3mf(path):
        tris += t
    if not tris:
        raise ValueError("the 3MF holds no triangles")
    return Mesh.Mesh(tris)


# ------------------------------------------------------------------ publish
def publish_plan(doc, licence=None):
    """What publishing the design needs to know: {"problems" (blocking,
    words for the user), "remix" (credits of imported parts), "licence"
    (the one to use: the user's, or the strictest the parts ask for),
    "licence_note"}."""
    from . import design_import as di
    objs = list(getattr(doc, "Objects", []))
    problems = [p for p in (di.licence_problem(o) for o in objs) if p]
    need = di.strictest_licence(objs)
    note = ""
    lic = licence or need or "cc-by"
    if need and licence and not _at_least(licence, need):
        problems.append("The parts you brought in ask for at least %s; %s "
                        "drops their terms." % (di.LICENCES[need][0],
                                                di.LICENCES.get(licence, ("that",))[0]))
    if need:
        note = "Remixed parts need %s or stricter." % di.LICENCES[need][0]
    return {"problems": problems, "remix": di.credits(doc), "licence": lic,
            "licence_note": note}


def _at_least(chosen, need):
    """True when licence `chosen` keeps every term of `need` (BY, NC, SA)."""
    if chosen in ("sdfl", "unknown", "own", "cc0"):
        return False
    return all(t in chosen for t in need.split("-") if t not in ("cc",))


def description(title, text, plan):
    """description.txt: what goes in MakerWorld's form, ready to paste."""
    from . import design_import as di
    lines = [title.strip() or "Untitled", ""]
    if text.strip():
        lines += [text.strip(), ""]
    if plan["remix"]:
        lines.append("Remix of:")
        lines += ["- %s" % c for c in plan["remix"]]
        lines.append("")
    lines.append("Licence: %s" % di.LICENCES.get(plan["licence"], ("?",))[0])
    lines.append(MADE_WITH)
    return "\n".join(lines) + "\n"


def bundle_dir(doc, root=None):
    root = root or os.path.join(os.path.expanduser("~"), "Documents",
                                "Atech Atelier", "MakerWorld")
    name = re.sub(r"[^\w .-]", "_", getattr(doc, "Label", "") or "design").strip() or "design"
    return os.path.join(root, name)


def write_bundle(doc, folder, title, text, licence=None, picture=True):
    """Make the upload in `folder`: model.3mf, model.step (solids only),
    cover.png and description.txt. Refuses (ValueError) while a licence
    forbids publishing. Returns {"folder", "files", "plan", "notes"}."""
    from . import export_tools
    plan = publish_plan(doc, licence)
    if plan["problems"]:
        raise ValueError(" ".join(plan["problems"]))
    os.makedirs(folder, exist_ok=True)
    files, notes = [], []
    stem = re.sub(r"[^\w-]+", "_", title.strip() or "model").strip("_") or "model"
    p3 = os.path.join(folder, stem + ".3mf")
    r = export_tools.export_for_print(doc, p3, fmt="3MF", scope="product")
    files += r.get("files") or [p3]
    if r.get("left_out"):
        notes.append("Atech board and modules are left out of the files (their "
                     "models are not yours to share); say in the description "
                     "which ones the design uses.")
    try:
        ps = os.path.join(folder, stem + ".step")
        r = export_tools.export_for_print(doc, ps, fmt="STEP", scope="product")
        files += r.get("files") or [ps]
        if r.get("skipped"):
            notes.append("STL / 3MF parts are not in the STEP file (meshes).")
    except ValueError as exc:
        notes.append("No STEP file: %s" % exc)
    if picture:
        try:
            from . import capture
            img = capture.share_image(doc, out_dir=folder, clipboard=False)
            cover = os.path.join(folder, "cover" + os.path.splitext(img)[1])
            os.replace(img, cover)
            files.append(cover)
        except Exception as exc:                       # noqa: BLE001
            _log("cover: %r" % (exc,))
            notes.append("No cover picture: %s" % exc)
    dp = os.path.join(folder, "description.txt")
    with open(dp, "w", encoding="utf-8") as fh:
        fh.write(description(title, text, plan))
    files.append(dp)
    return {"folder": folder, "files": files, "plan": plan, "notes": notes}


# ------------------------------------------------------------------ windows
def _open_url(url):
    from PySide6 import QtCore, QtGui
    QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))


def ImportDialog(parent=None, opener=None):
    """From MakerWorld...: link, page, download, licence, add."""
    from PySide6 import QtWidgets
    from . import design_import as di
    from . import export_tools

    opener = opener or _open_url
    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "From MakerWorld")
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(10)
    t = QtWidgets.QLabel("From MakerWorld", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel("1. Paste the model's link and open its page.  2. Download "
                           "it there (STEP is best for editing; 3MF and STL work).  "
                           "3. Add it here with the licence its page shows.", d)
    sub.setObjectName("ToolMuted")
    sub.setWordWrap(True)
    lay.addWidget(sub)
    d.link = QtWidgets.QLineEdit(d)
    d.link.setPlaceholderText("https://makerworld.com/en/models/…")
    d.link.setAccessibleName("MakerWorld link")
    d.btn_page = QtWidgets.QPushButton("Open its page", d)
    r = QtWidgets.QHBoxLayout()
    r.addWidget(d.link, 1)
    r.addWidget(d.btn_page)
    lay.addLayout(r)
    d.file = QtWidgets.QLineEdit(d)
    d.file.setPlaceholderText("The downloaded file")
    d.file.setAccessibleName("Downloaded file")
    d.btn_newest = QtWidgets.QPushButton("Use my newest download", d)
    d.btn_choose = QtWidgets.QPushButton("Choose…", d)
    r = QtWidgets.QHBoxLayout()
    r.addWidget(d.file, 1)
    r.addWidget(d.btn_newest)
    r.addWidget(d.btn_choose)
    lay.addLayout(r)
    form = QtWidgets.QFormLayout()
    d.author = QtWidgets.QLineEdit(d)
    d.author.setPlaceholderText("The maker's name on the page")
    form.addRow("Made by", d.author)
    d.licence = QtWidgets.QComboBox(d)
    for k in di.LICENCE_ORDER:
        if k != "own":
            d.licence.addItem(di.LICENCES[k][0], k)
    d.licence.setToolTip("The licence shown on the model's page")
    form.addRow("Licence", d.licence)
    lay.addLayout(form)
    d.editable = QtWidgets.QCheckBox("Let the design agent edit it", d)
    lay.addWidget(d.editable)
    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    lay.addWidget(d.status)
    bb = QtWidgets.QDialogButtonBox(d)
    d.ok = bb.addButton("Add to design", QtWidgets.QDialogButtonBox.AcceptRole)
    bb.addButton(QtWidgets.QDialogButtonBox.Cancel)
    bb.accepted.connect(d.accept)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    state = {"opened": time.time()}

    def check():
        info = parse_link(d.link.text())
        d.btn_page.setEnabled(info is not None)
        p = d.file.text().strip()
        okf = bool(p) and os.path.isfile(p) and p.lower().endswith(di.ADD_EXT)
        d.ok.setEnabled(okf and info is not None)
        if d.link.text().strip() and info is None:
            d.status.setText("That is not a MakerWorld model link.")
        elif info is not None and d.licence.currentData() == "sdfl":
            d.status.setText("Standard Digital File License: fine for your own "
                             "prints, but a design with it cannot be published.")
        elif info is not None and not okf:
            d.status.setText("Download it from its page, then use your newest "
                             "download.")
        else:
            d.status.setText("")

    def page():
        info = parse_link(d.link.text())
        if info:
            state["opened"] = time.time() - 5
            opener(info["url"])

    def newest():
        p = newest_download(state["opened"]) or newest_download(0)
        if p:
            d.file.setText(p)
        else:
            d.status.setText("No STEP, 3MF or STL in Downloads yet.")

    def choose():
        p, _f = QtWidgets.QFileDialog.getOpenFileName(
            d, "The downloaded model", downloads_dir(), di.FILE_FILTER)
        if p:
            d.file.setText(p)

    def values():
        info = parse_link(d.link.text()) or {}
        return {"path": d.file.text().strip(),
                "source": {"url": info.get("url", ""), "author": d.author.text(),
                           "licence": d.licence.currentData()},
                "label": info.get("title") or None,
                "agent_editable": d.editable.isChecked()}

    d.btn_page.clicked.connect(lambda _=False: page())
    d.btn_newest.clicked.connect(lambda _=False: newest())
    d.btn_choose.clicked.connect(lambda _=False: choose())
    d.link.textChanged.connect(lambda _t: check())
    d.file.textChanged.connect(lambda _t: check())
    d.licence.currentIndexChanged.connect(lambda _i: check())
    d.values = values
    check()
    d.resize(560, 0)
    return d


def import_to_active(parent=None):
    from PySide6 import QtWidgets
    import FreeCAD
    from . import design_import as di
    d = ImportDialog(parent)
    if d.exec() != QtWidgets.QDialog.Accepted:
        return []
    v = d.values()
    doc = FreeCAD.ActiveDocument or FreeCAD.newDocument("Untitled")
    try:
        made = di.add_file(doc, v["path"], source=v["source"],
                           agent_editable=v["agent_editable"], label=v["label"])
    except Exception as exc:                           # noqa: BLE001
        QtWidgets.QMessageBox.warning(parent, "Could not add the model",
                                      "%s could not be added: %s"
                                      % (os.path.basename(v["path"]), exc))
        return []
    di._show(made)
    return made


def PublishDialog(parent=None, doc=None, opener=None):
    """Publish to MakerWorld...: licence check, the files, then the browser."""
    from PySide6 import QtCore, QtWidgets
    from . import design_import as di
    from . import export_tools

    opener = opener or _open_url
    if doc is None:
        doc = export_tools._active_doc()
    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Publish to MakerWorld")
    d.setModal(False)
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 16, 20, 16)
    lay.setSpacing(10)
    t = QtWidgets.QLabel("Publish to MakerWorld", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel("Atelier makes the files and the text; you upload them on "
                           "MakerWorld (it has no way for apps to upload).", d)
    sub.setObjectName("ToolMuted")
    sub.setWordWrap(True)
    lay.addWidget(sub)
    form = QtWidgets.QFormLayout()
    d.title = QtWidgets.QLineEdit(getattr(doc, "Label", "") or "", d)
    form.addRow("Title", d.title)
    d.text = QtWidgets.QPlainTextEdit(d)
    d.text.setPlaceholderText("What it is, how to print it, what it needs")
    d.text.setFixedHeight(90)
    form.addRow("Description", d.text)
    d.licence = QtWidgets.QComboBox(d)
    for k in di.LICENCE_ORDER:
        if k not in ("unknown", "own"):
            d.licence.addItem(di.LICENCES[k][0], k)
    form.addRow("Licence", d.licence)
    lay.addLayout(form)
    d.checks = QtWidgets.QLabel("", d)
    d.checks.setWordWrap(True)
    lay.addWidget(d.checks)
    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    d.status.setTextInteractionFlags(d.status.textInteractionFlags()
                                     | QtCore.Qt.TextSelectableByMouse)
    lay.addWidget(d.status)
    row = QtWidgets.QHBoxLayout()
    d.btn_make = QtWidgets.QPushButton("Make the files", d)
    d.btn_slicer = QtWidgets.QPushButton("Open in Bambu Studio", d)
    d.btn_slicer.setToolTip("Save the project there (File > Save Project): that "
                            "3MF is the print profile MakerWorld asks for")
    d.btn_folder = QtWidgets.QPushButton("Show files", d)
    d.btn_site = QtWidgets.QPushButton("Open MakerWorld", d)
    d.btn_site.setToolTip("Press Upload there and add the files from the folder")
    for b in (d.btn_make, d.btn_slicer, d.btn_folder, d.btn_site):
        row.addWidget(b)
        b.setAutoDefault(False)
    lay.addLayout(row)
    help_ = QtWidgets.QLabel('<a href="%s">How uploading to MakerWorld works</a>'
                             % HELP_URL, d)
    help_.setOpenExternalLinks(True)
    lay.addWidget(help_)
    state = {"bundle": None}
    plan0 = publish_plan(doc) if doc is not None else {"licence": "cc-by",
                                                       "problems": ["Open a design first."],
                                                       "remix": [], "licence_note": ""}
    i = d.licence.findData(plan0["licence"])
    d.licence.setCurrentIndex(i if i >= 0 else 0)

    def refresh():
        plan = publish_plan(doc, d.licence.currentData()) if doc is not None else plan0
        bits = []
        for p in plan["problems"]:
            bits.append("✗ " + p)
        if plan["remix"]:
            bits.append("Remix of: " + "; ".join(plan["remix"]))
        if plan["licence_note"]:
            bits.append(plan["licence_note"])
        if not plan["problems"]:
            bits.append("✓ The licences allow publishing it.")
        d.checks.setText("\n".join(bits))
        d.btn_make.setEnabled(not plan["problems"])
        have = state["bundle"] is not None
        d.btn_slicer.setEnabled(have and bool(export_tools.find_slicers()))
        d.btn_folder.setEnabled(have)
        return plan

    def make():
        folder = bundle_dir(doc)
        try:
            b = write_bundle(doc, folder, d.title.text(), d.text.toPlainText(),
                             d.licence.currentData())
        except Exception as exc:                       # noqa: BLE001
            d.status.setText("Could not make the files: %s" % exc)
            return
        state["bundle"] = b
        d.status.setText("Saved in %s:\n%s%s" % (
            folder, ", ".join(os.path.basename(f) for f in b["files"]),
            ("\n" + "\n".join(b["notes"])) if b["notes"] else ""))
        refresh()

    def slicer():
        b = state["bundle"]
        sl = export_tools.find_slicers()
        bambu = [s for s in sl if "Bambu" in s["name"]] or sl
        if b and bambu:
            export_tools.open_in_slicer([f for f in b["files"] if f.endswith(".3mf")],
                                        bambu[0])

    def folder():
        b = state["bundle"]
        if b:
            from PySide6 import QtCore, QtGui
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(b["folder"]))

    d.btn_make.clicked.connect(lambda _=False: make())
    d.btn_slicer.clicked.connect(lambda _=False: slicer())
    d.btn_folder.clicked.connect(lambda _=False: folder())
    d.btn_site.clicked.connect(lambda _=False: opener(UPLOAD_URL))
    d.licence.currentIndexChanged.connect(lambda _i: refresh())
    d.refresh = refresh
    refresh()
    d.resize(560, 0)
    return d
