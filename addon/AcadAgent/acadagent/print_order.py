"""print_order - get a design made by Atech: its modules and its prints (R850).

The design's printed parts (every visible solid that is not Atech hardware
or a library part, as Export for print takes them) are measured laid flat
on the bed, their filament estimated (shop.print_grams) and packed into 3D
print vouchers (shop.plan_prints). order() puts that next to the modules on
the board (shop.bill), and save_prints() writes one 3MF per voucher print
plus a short order sheet, ready to send to Atech.

The logic runs headless (freecadcmd); OrderDialog (Qt) is the window the
Modules page's "Get it made" and the Atech menu open.
"""
import datetime
import os

from . import export_tools, shop

#: where the prints for Atech are saved (one folder per design)
PRINTS_DIR = os.path.join(os.path.expanduser("~"), "Documents", "Atech Prints")


def _log(msg):
    export_tools._log("print order: %s" % msg)


def printed_parts(doc):
    """The objects Atech would print: visible top-level solids that are not
    the board, a module, a cable or a library part."""
    objs, _left = export_tools.export_targets(doc, "product")
    return [o for o in objs if not export_tools._is_mesh(o)]


def measure(doc):
    """[{"label", "size" (w, d, h) mm laid flat, "grams", "solid_g"}]."""
    out = []
    for o in printed_parts(doc):
        try:
            s, _info = export_tools.orient_for_print(o.Shape)
            bb = s.BoundBox
            vol, area = float(s.Volume), float(s.Area)
        except Exception as exc:                          # noqa: BLE001
            _log("%s: %r" % (getattr(o, "Label", "?"), exc))
            continue
        out.append({"label": o.Label,
                    "size": (round(bb.XLength, 1), round(bb.YLength, 1), round(bb.ZLength, 1)),
                    "grams": round(shop.print_grams(vol, area), 1),
                    "solid_g": round(vol / 1000.0 * shop.PLA_DENSITY, 1)})
    return out


def board_modules(doc):
    """(module names on the board, one per module, {name: count} of library
    parts Atech does not sell). The board itself is counted by shop.bill."""
    names, extra, seen = [], {}, set()
    if doc is None:
        return names, extra
    for o in doc.Objects:
        if export_tools.PREVIOUS in (getattr(o, "Label", "") or ""):
            continue
        role = getattr(o, "AtechRole", None)
        key = getattr(o, "AtechModule", "") or ""
        if role == "module" and key and o.Name not in seen:
            seen.add(o.Name)
            names.append(key)
        elif role == "part":
            n = export_tools.module_name(key or o.Label)
            extra[n] = extra.get(n, 0) + 1
    return names, extra


def has_board(doc):
    return doc is not None and any(getattr(o, "AtechRole", None) == "board" for o in doc.Objects)


def order(doc):
    """Everything to get this design made: {"modules" Counter {slug: n},
    "unsold" [module names], "parts" (library parts, not sold by Atech),
    "plan" (shop.plan_prints), "names" (module names)}."""
    names, extra = board_modules(doc)
    want, unsold = shop.bill(names, board=has_board(doc))
    return {"names": names, "modules": want, "unsold": unsold, "parts": extra,
            "plan": shop.plan_prints(measure(doc))}


def cart_url(o, prints=True):
    """The atech.dev cart with the order's modules, and its vouchers when
    `prints`."""
    n = o["plan"]["vouchers"] if prints else 0
    return shop.cart_url(o["names"], board=bool(o["modules"].get(shop.SHOP_SLUGS[shop.BOARD])),
                         prints=n)


def hardware_text(o):
    """"1 x 14-Port Motherboard, 2 x DC Motor": the order's Atech hardware
    by the shop's names."""
    return ", ".join("%d x %s" % (c, shop.SHOP_NAMES.get(s, s)) for s, c in o["modules"].items()
                     if s != shop.VOUCHER)


def _design_name(doc):
    return export_tools.safe_name(getattr(doc, "Label", "") or "design")


def order_sheet(doc, o, files=()):
    """The plain-text sheet that goes with the prints (and in the email)."""
    plan = o["plan"]
    lines = ["Design: %s" % (getattr(doc, "Label", "") or "design"),
             "Prints: %d (one 3D print voucher each)" % plan["vouchers"], ""]
    how = {r["label"]: r["fit"] for r in plan["parts"]}
    for i, pr in enumerate(plan["prints"], 1):
        lines.append("Print %d, about %.0f g: %s" % (i, pr["grams"], ", ".join(
            l if how.get(l) == "ok" else "%s (%s)" % (l, FIT_TEXT[how[l]].lower())
            for l in pr["labels"])))
    if plan["split"]:
        lines += ["", "Too big for one voucher (split before printing): %s"
                  % ", ".join(plan["split"])]
    if files:
        lines += ["", "Files: %s" % ", ".join(os.path.basename(f) for f in files)]
    lines += ["", "Atech hardware: %s" % (hardware_text(o) or "none")]
    lines += ["", "Colour, material or other wishes:", "", "My order number or order email:", ""]
    return "\n".join(lines)


def _plate_shapes(objs, quality):
    """One voucher print as it goes on the bed: each part laid flat, turned
    and placed where shop.plate() puts it (on a 340 x 320 bed, corner at
    the origin). Returns [(label, mesh, colour, transparency)]."""
    import FreeCAD
    flat = []
    for o in objs:
        sh, _info = export_tools.orient_for_print(o.Shape)
        flat.append((o, sh))
    sizes = [(sh.BoundBox.XLength, sh.BoundBox.YLength, sh.BoundBox.ZLength) for _o, sh in flat]
    spots = shop.plate(sizes)
    if spots is None and len(flat) == 1:
        # a long part on its own, corner to corner
        w, d = sizes[0][:2]
        ang = shop.diagonal_angle(w, d) or 0.0
        spots = [(shop.VOUCHER_MM[0] / 2, shop.VOUCHER_MM[1] / 2, ang)]
    out = []
    for i, (o, sh) in enumerate(flat):
        cx, cy, turn = spots[i] if spots else (shop.VOUCHER_MM[0] / 2, shop.VOUCHER_MM[1] / 2, False)
        deg = 90.0 if turn is True else (float(turn) if turn else 0.0)
        c = sh.copy()
        if deg:
            c.rotate(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), deg)
        bb = c.BoundBox
        c.translate(FreeCAD.Vector(cx - (bb.XMin + bb.XMax) / 2, cy - (bb.YMin + bb.YMax) / 2,
                                   -bb.ZMin))
        col, tr = export_tools.object_colour(o)
        out.append((o.Label, export_tools.shape_mesh(c, quality), col, tr))
    return out


def save_prints(doc, o=None, out_dir=None, quality=export_tools.DEFAULT_DEVIATION):
    """One 3MF per voucher print, each a ready plate: the parts laid flat
    and placed as they fit on the 340 x 320 mm bed, in PRINTS_DIR/<design>/,
    with order.txt. Returns {"dir", "files", "sheet"}."""
    o = o or order(doc)
    plan = o["plan"]
    if not plan["prints"]:
        raise ValueError("Nothing to print: the design has no printed parts that fit a voucher.")
    export_tools.restore_exploded(doc)
    name = _design_name(doc)
    out_dir = out_dir or os.path.join(PRINTS_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    by_label = {}
    for x in printed_parts(doc):
        by_label.setdefault(x.Label, x)
    files = []
    for i, pr in enumerate(plan["prints"], 1):
        objs = [by_label[l] for l in pr["labels"] if l in by_label]
        path = os.path.join(out_dir, "%s print %d of %d.3mf" % (name, i, len(plan["prints"])))
        export_tools.write_3mf(_plate_shapes(objs, quality), path)
        files.append(path)
    sheet = order_sheet(doc, o, files)
    with open(os.path.join(out_dir, "order.txt"), "w", encoding="utf-8") as fh:
        fh.write(sheet + "\n")
    return {"dir": out_dir, "files": files, "sheet": sheet}


def email_url(doc, o, files=()):
    """A mailto: to Atech with the order sheet; the files are attached by
    hand (mailto cannot carry them)."""
    subject = "3D print voucher: %s (%d print%s)" % (
        getattr(doc, "Label", "") or "my design", o["plan"]["vouchers"],
        "" if o["plan"]["vouchers"] == 1 else "s")
    body = ("Hi Atech,\n\nPlease print my design with my 3D print voucher%s. The 3MF "
            "file%s from Atech Atelier %s attached.\n\n%s\n\nSent from Atech Atelier, %s\n" % (
                "" if o["plan"]["vouchers"] == 1 else "s",
                "" if len(files) == 1 else "s", "is" if len(files) == 1 else "are",
                order_sheet(doc, o, files), datetime.date.today().isoformat()))
    return shop.mailto_url(subject, body)


def reveal(path):
    """Show `path` selected in Finder (the folder opens elsewhere)."""
    import subprocess
    import sys
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            shop.open_url("file://" + os.path.dirname(path))
        return True
    except Exception as exc:                              # noqa: BLE001
        _log("reveal: %r" % (exc,))
        return False


# ===================================================================
# R850 the window
# ===================================================================
FIT_TEXT = {"ok": "Fits", "on its side": "Fits on its side", "diagonal": "Fits corner to corner",
            "too big": "Too big: split it", "too heavy": "Over %g g: split it" % shop.VOUCHER_GRAMS}


def split_prompt(labels):
    """What the agent is asked when parts are too big for one voucher."""
    return ("Split %s into pieces that each fit one Atech 3D print voucher (a %g x %g x %g mm "
            "print, under %g g), joined with pegs or screws, and keep the outside look."
            % (", ".join(labels), shop.VOUCHER_MM[0], shop.VOUCHER_MM[1], shop.VOUCHER_MM[2],
               shop.VOUCHER_GRAMS))


def _stored_email():
    """The email last used to send prints, else the signed-in account's
    (R860)."""
    try:
        from . import settings
        cfg = settings.load()
        return cfg.get("shop_email") or ((cfg.get("account_user") or {}).get("email") or "")
    except Exception:                                     # noqa: BLE001
        return ""


def _store_email(email):
    try:
        from . import settings
        settings.update(shop_email=email)
    except Exception as exc:                              # noqa: BLE001
        _log("store email: %r" % (exc,))


def fewer_prompt(plan):
    """What the agent is asked when the last print holds only a few light
    parts."""
    n = plan["vouchers"]
    return ("The printed parts take %d Atech 3D print vouchers (each a %g x %g mm bed), but the "
            "last print holds only %s. Make them fit on %d: slimmer or flatter parts, or "
            "pieces that nest, keeping the look." % (
                n, shop.VOUCHER_MM[0], shop.VOUCHER_MM[1], ", ".join(plan["light"]), n - 1))


def OrderDialog(parent=None, doc_fn=export_tools._active_doc, opener=None, revealer=None,
                panel_fn=None, sender=None, background=True, quoter=None):
    """R850 "Get it made by Atech": the board and modules, the prints and
    the vouchers they take; Add to cart on atech.dev (modules and, ticked,
    the vouchers); Send my prints (3MFs saved and posted to Atech with the
    buyer's email, order number and wishes; an email draft to Atech when
    the site cannot take them); Ask the agent to split what is too big.
    opener(url) / revealer(path) default to the browser and Finder,
    sender(**request) to shop.send_print_request and quoter(cart) to
    shop.quote (the price line), in a thread unless `background` is
    False."""
    from PySide6 import QtCore, QtWidgets

    opener = opener or shop.open_url
    revealer = revealer or reveal
    doc = doc_fn()
    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Get it made by Atech")
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(8)
    t = QtWidgets.QLabel("Get it made by Atech", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    sub = QtWidgets.QLabel(getattr(doc, "Label", "") or "No design open", d)
    sub.setObjectName("ToolMuted")
    lay.addWidget(sub)
    # measuring the parts takes up to ~3 s on a big design (32 saved
    # designs MEASURED 5 Nov 2026: 0.2-2.9 s)
    QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
    try:
        o = order(doc) if doc is not None else {
            "names": [], "modules": {}, "unsold": [], "parts": {},
            "plan": shop.plan_prints([])}
    finally:
        QtWidgets.QApplication.restoreOverrideCursor()
    d.order = o
    plan = o["plan"]

    def section(text):
        lab = QtWidgets.QLabel(text, d)
        lab.setObjectName("ToolMuted")
        lab.setStyleSheet("font-weight: 600; margin-top: 8px;")
        lay.addWidget(lab)
        return lab

    def text(s, muted=False):
        lab = QtWidgets.QLabel(s, d)
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        if muted:
            lab.setObjectName("ToolMuted")
        lay.addWidget(lab)
        return lab

    section("ATECH HARDWARE")
    hw = hardware_text(o)
    d.hardware = text(hw.replace(", ", "\n").replace(" x ", " \u00d7 ") if hw
                      else "No board or modules in this design.")
    if o["unsold"] or o["parts"]:
        bits = [export_tools.module_name(n) for n in o["unsold"]]
        bits += ["%d \u00d7 %s" % (c, n) for n, c in sorted(o["parts"].items())]
        text("Not sold by Atech: %s." % ", ".join(bits), muted=True)

    section("3D PRINTS")
    rows = plan["parts"]
    where = {}
    for i, pr in enumerate(plan["prints"], 1):
        for lab in pr["labels"]:
            where[lab] = i
    d.table = QtWidgets.QTableWidget(len(rows), 4, d)
    d.table.setHorizontalHeaderLabels(["Part", "Size (mm)", "About", "Voucher"])
    d.table.setAccessibleName("3D prints")
    d.table.verticalHeader().setVisible(False)
    d.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    d.table.horizontalHeader().setStretchLastSection(True)
    for i, r in enumerate(rows):
        fit_s = FIT_TEXT.get(r["fit"], r["fit"])
        if r["label"] in where:
            fit_s = "Print %d" % where[r["label"]] + ("" if r["fit"] == "ok" else " (%s)"
                                                     % fit_s.lower().replace("fits ", ""))
        vals = [r["label"], "%g \u00d7 %g \u00d7 %g" % tuple(r["size"]), "%.0f g" % r["grams"], fit_s]
        for j, v in enumerate(vals):
            d.table.setItem(i, j, QtWidgets.QTableWidgetItem(v))
    d.table.resizeColumnsToContents()
    d.table.resizeRowsToContents()
    # room for up to 7 rows as they are drawn (resized to their text)
    shown = sum(d.table.rowHeight(i) for i in range(min(len(rows), 7))) or \
        d.table.verticalHeader().defaultSectionSize()
    d.table.setMinimumHeight(d.table.horizontalHeader().sizeHint().height() + shown
                             + 2 * d.table.frameWidth() + 2)
    d.table.setVisible(bool(rows))
    lay.addWidget(d.table, 1)
    d.note = text(shop.kit_note(plan["vouchers"]) + (
        " Each voucher is one print up to 34 \u00d7 32 \u00d7 34 cm and %g g; grams are "
        "estimated at 15 %% infill." % shop.VOUCHER_GRAMS if plan["vouchers"] else ""), muted=True)
    d.voucher_link = QtWidgets.QLabel('<a href="%s">What a 3D print voucher covers</a>'
                                      % shop.VOUCHER_URL, d)
    d.voucher_link.setAccessibleName("What a 3D print voucher covers, on atech.dev")
    d.voucher_link.linkActivated.connect(lambda url: opener(url))
    lay.addWidget(d.voucher_link)
    d.split = None
    d.fewer = None
    if plan["split"]:
        row = QtWidgets.QHBoxLayout()
        lab = QtWidgets.QLabel("%s %s too big for one voucher." % (
            ", ".join(plan["split"]), "is" if len(plan["split"]) == 1 else "are"), d)
        lab.setWordWrap(True)
        row.addWidget(lab, 1)
        d.split = QtWidgets.QPushButton("Ask the agent to split it", d)
        d.split.setAccessibleName("Ask the agent to split the parts that are too big")
        row.addWidget(d.split)
        lay.addLayout(row)
    elif plan.get("light"):
        row = QtWidgets.QHBoxLayout()
        last = plan["prints"][-1]
        lab = QtWidgets.QLabel("Print %d holds only %d small part%s (%.0f g)." % (
            plan["vouchers"], len(last["labels"]), "" if len(last["labels"]) == 1 else "s",
            last["grams"]), d)
        lab.setWordWrap(True)
        row.addWidget(lab, 1)
        d.fewer = QtWidgets.QPushButton("Ask the agent to fit it on %d" % (plan["vouchers"] - 1), d)
        d.fewer.setAccessibleName("Ask the agent to fit the prints on fewer vouchers")
        row.addWidget(d.fewer)
        lay.addLayout(row)

    # Buy: the modules, and the vouchers ticked
    buy = QtWidgets.QHBoxLayout()
    d.with_prints = QtWidgets.QCheckBox(
        "With %d 3D print voucher%s" % (plan["vouchers"], "" if plan["vouchers"] == 1 else "s"), d)
    d.with_prints.setAccessibleName("Add the 3D print vouchers to the cart")
    d.with_prints.setChecked(plan["vouchers"] > 0)
    d.with_prints.setVisible(plan["vouchers"] > 0)
    buy.addWidget(d.with_prints)
    buy.addStretch(1)
    d.cart = QtWidgets.QPushButton("Add to cart on atech.dev", d)
    d.cart.setObjectName("ToolPrimary")
    d.cart.setAccessibleName("Add to cart on atech.dev")
    d.cart.setDefault(True)
    buy.addWidget(d.cart)
    lay.addLayout(buy)
    # what it costs, from the site (its prices, the visitor's currency)
    d.price = QtWidgets.QLabel("", d)
    d.price.setObjectName("ToolMuted")
    d.price.setWordWrap(True)
    d.price.setVisible(False)
    lay.addWidget(d.price)

    # Send my prints: who they are from (Atech replies there), the order
    # that paid for the vouchers, and wishes
    d.send_title = section("SEND YOUR PRINTS")
    d.send_box = QtWidgets.QWidget(d)
    form = QtWidgets.QFormLayout(d.send_box)
    form.setContentsMargins(0, 0, 0, 0)
    d.email = QtWidgets.QLineEdit(_stored_email(), d.send_box)
    d.email.setPlaceholderText("the email you ordered with")
    d.email.setAccessibleName("Your email")
    d.order_no = QtWidgets.QLineEdit(d.send_box)
    d.order_no.setPlaceholderText("optional")
    d.order_no.setAccessibleName("Order number")
    d.wishes = QtWidgets.QLineEdit(d.send_box)
    d.wishes.setPlaceholderText("colour, material, anything we should know (optional)")
    d.wishes.setAccessibleName("Wishes")
    form.addRow("Your email", d.email)
    form.addRow("Order number", d.order_no)
    form.addRow("Wishes", d.wishes)
    lay.addWidget(d.send_box)
    send_row = QtWidgets.QHBoxLayout()
    hint = QtWidgets.QLabel("Have your vouchers? Send us the files and we print them.", d)
    hint.setObjectName("ToolMuted")
    hint.setWordWrap(True)
    send_row.addWidget(hint, 1)
    d.send = QtWidgets.QPushButton("Send my prints to Atech", d)
    d.send.setAccessibleName("Send my prints to Atech")
    d.send.setToolTip("Saves one 3MF per voucher in Documents/Atech Prints and sends them to "
                      "Atech with your email; Atech replies there.")
    send_row.addWidget(d.send)
    lay.addLayout(send_row)
    for w in (d.send_title, d.send_box, hint, d.send):
        w.setVisible(plan["vouchers"] > 0)
    d.send.setEnabled(plan["vouchers"] > 0)

    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    lay.addWidget(d.status)

    quotes = {}

    def fit_height():
        """Tall enough for the wrapped text at this width (the price line
        comes in after the window opens), so nothing overlaps."""
        lay.activate()
        need = lay.totalHeightForWidth(d.width()) if lay.hasHeightForWidth() \
            else d.sizeHint().height()
        if d.height() < need:
            d.resize(d.width(), min(900, need))

    def show_price(url):
        if url != cart_url(o, d.with_prints.isChecked()):
            return                                        # ticked again since
        line = shop.price_line(quotes.get(url))
        d.price.setText(line)
        d.price.setVisible(bool(line))
        fit_height()

    def fetch_price(url):
        if url in quotes:
            return show_price(url)
        ask = quoter or shop.quote
        if not background:
            quotes[url] = ask(url)
            return show_price(url)
        import threading

        class PriceRelay(QtCore.QObject):
            done = QtCore.Signal(object)
        relay = PriceRelay(d)
        relay.done.connect(lambda q: (quotes.__setitem__(url, q), show_price(url)))
        def run():
            q = ask(url)
            try:
                relay.done.emit(q)
            except RuntimeError:                          # the window closed first
                pass
        threading.Thread(target=run, daemon=True).start()

    def sync_cart():
        url = cart_url(o, d.with_prints.isChecked())
        d.cart.setToolTip(url)
        d.cart.setEnabled(url != shop.SHOP or plan["vouchers"] > 0)
        if url == shop.SHOP:
            d.price.setVisible(False)
        else:
            fetch_price(url)
        return url

    def add_to_cart():
        url = sync_cart()
        opener(url)
        then = (" Once you have paid, come back here and press Send my prints to Atech, "
                "with the email you paid with." if d.with_prints.isChecked() else "")
        d.status.setText("The cart on atech.dev is open in your browser. Anything already in "
                         "it stays; opening it again adds nothing twice." + then)
        return url

    def by_email(res, why=""):
        """The site could not take them: an email draft to Atech, the files
        shown in Finder to drag in."""
        opener(email_url(doc_fn(), o, res["files"]))
        revealer(res["files"][0])
        d.status.setText("%sSaved %d file%s in %s. An email to %s is open: drag the file%s "
                         "from Finder into it and send." % (
                             why, len(res["files"]), "" if len(res["files"]) == 1 else "s",
                             res["dir"].replace(os.path.expanduser("~"), "~"),
                             shop.VOUCHER_EMAIL, "" if len(res["files"]) == 1 else "s"))

    def sent(res, answer):
        d.send.setEnabled(True)
        d.sent_answer = answer
        if answer["ok"]:
            # sent: one press is one voucher each, so a second send is on purpose
            d.send.setText("Send again")
            d.status.setText("Sent to Atech: %d print%s. We reply to %s; the files are also in %s." % (
                len(res["files"]), "" if len(res["files"]) == 1 else "s", d.email.text().strip(),
                res["dir"].replace(os.path.expanduser("~"), "~")))
        elif answer["status"] in (0, 404, 500, 502, 503):
            by_email(res, "Could not reach Atech just now. " if answer["status"] else
                     "You look offline. ")
        else:
            d.status.setText("Atech could not take them: %s" % answer["message"])

    def send_prints():
        email = d.email.text().strip()
        if not shop.valid_email(email):
            d.status.setText("Type the email you ordered with: Atech replies there.")
            d.email.setFocus()
            return None
        _store_email(email)
        try:
            res = save_prints(doc_fn(), o)
        except Exception as exc:                          # noqa: BLE001
            d.status.setText("Could not save the prints: %s" % exc)
            return None
        d.sent = res
        req = dict(email=email, files=res["files"], design=getattr(doc_fn(), "Label", "") or "",
                   sheet=res["sheet"], note=d.wishes.text().strip(), order=d.order_no.text().strip())
        send = sender or shop.send_print_request
        if not background:
            sent(res, send(**req))
            return res
        d.send.setEnabled(False)
        d.status.setText("Sending %d print%s to Atech..." % (
            len(res["files"]), "" if len(res["files"]) == 1 else "s"))
        import threading

        class Relay(QtCore.QObject):
            done = QtCore.Signal(object)
        d._relay = Relay()
        d._relay.done.connect(lambda answer: sent(res, answer))
        threading.Thread(target=lambda: d._relay.done.emit(send(**req)), daemon=True).start()
        return res

    def ask_agent(prompt):
        if panel_fn is not None:
            p = panel_fn()
        else:
            from . import panel
            p = panel.get_panel()
        ok = p is not None and p.ask(prompt)
        d.status.setText("Asked the agent in the chat. Open this window again when it is done."
                         if ok else "The chat is busy or closed: ask it there: \u201c%s\u201d"
                         % prompt)
        return ok

    def split():
        return ask_agent(split_prompt(plan["split"]))

    def fewer():
        return ask_agent(fewer_prompt(plan))

    d.with_prints.toggled.connect(lambda _=False: sync_cart())
    d.cart.clicked.connect(lambda _=False: export_tools._guard(add_to_cart))
    d.send.clicked.connect(lambda _=False: export_tools._guard(send_prints))
    if d.split is not None:
        d.split.clicked.connect(lambda _=False: export_tools._guard(split))
    if d.fewer is not None:
        d.fewer.clicked.connect(lambda _=False: export_tools._guard(fewer))
    sync_cart()
    d.add_to_cart, d.send_prints, d.ask_split, d.ask_fewer = add_to_cart, send_prints, split, fewer
    d.resize(620, 640)
    fit_height()
    return d
