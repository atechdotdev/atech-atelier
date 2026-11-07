"""R861 Post to atech.dev: share a design on the community page
(atech.dev/community, the same Showcase post the site's "Post Build" makes)
from Atelier, as the signed-in Atech account (account.py, R860).

What it sends is the site's own API: POST /api/community/posts {title,
body, category} and then each picture or clip to
/api/community/posts/<id>/media (PNG/JPEG/WebP or MP4/MOV/WebM, 25 MB each,
12 a post; a bigger video needs the site's direct upload, not done here).
The body carries "Built by:" the way the site's form writes it
(frontend/src/lib/hub/details.ts). No atech.dev project is linked: an
Atelier design is a file on this computer, not a project on the site.
"""
import glob
import os
import threading
import urllib.request

from . import account, export_tools, shop

#: The site's SHOWCASE_CATEGORIES (frontend/src/lib/hub/format.ts), label -> value.
CATEGORIES = (("Robotics", "Robotics"), ("Gadgets", "Gadgets"), ("Smart home", "SmartHome"),
              ("Game", "Game"))
MAX_MEDIA = 12
MAX_FILE_BYTES = 25 * 1024 * 1024
MEDIA_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".webp": "image/webp", ".mp4": "video/mp4", ".mov": "video/quicktime",
             ".webm": "video/webm"}
COMMUNITY_URL = shop.SITE + "/community"


def _log(msg):
    export_tools._log("post: %s" % msg)


def compose_body(text, by=""):
    """The post's body as the site's form composes it: the words, then a
    "Built by:" line."""
    parts = [text.strip()]
    if by.strip():
        parts.append("Built by: %s" % by.strip())
    return "\n\n".join(p for p in parts if p)


def latest_video(label):
    """The newest assembly video of this design (promo_video's
    "<label> assembly <date>.mp4" in Movies/Atech Atelier), or None."""
    try:
        from . import promo_video
        folder = promo_video.video_dir()
    except Exception:                                     # noqa: BLE001
        return None
    safe = "".join(c if (c.isalnum() or c in " ._-") else "_" for c in (label or "")).strip(" .")
    found = [p for p in glob.glob(os.path.join(glob.escape(folder), glob.escape(safe or "Design")
                                               + " assembly *")) if p.lower().endswith((".mp4", ".mov"))]
    return max(found, key=os.path.getmtime) if found else None


def media_problem(path):
    """Why `path` cannot go on a post, or ""."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in MEDIA_EXT:
        return "not a picture or video the site takes"
    try:
        size = os.path.getsize(path)
    except OSError:
        return "missing"
    if size > MAX_FILE_BYTES:
        return "%.0f MB, over the 25 MB a file can be from Atelier for now" % (size / 1e6)
    return ""


def publish(title, body, category, files, acct=None, opener=None):
    """Create the post and upload `files` in order. Returns {"ok", "id",
    "uploaded", "failed": [(path, why)], "message"}."""
    acct = acct or account.get()
    status, row = acct.request("POST", "/api/community/posts",
                               {"title": title.strip()[:140], "body": body[:4000],
                                "category": category})
    if status == 401:
        return {"ok": False, "id": None, "uploaded": 0, "failed": [],
                "message": "Sign in first: your session has ended."}
    if status != 201 or not row.get("id"):
        why = account._message(row, "The site did not take the post (HTTP %d)." % status
                               if status else "Could not reach atech.dev.")
        return {"ok": False, "id": None, "uploaded": 0, "failed": [], "message": why}
    pid, uploaded, failed = row["id"], 0, []
    for path in files[:MAX_MEDIA]:
        problem = media_problem(path)
        if problem:
            failed.append((path, problem))
            continue
        tok = acct.token()
        body_bytes, ctype = shop._multipart({}, [path], MEDIA_EXT[os.path.splitext(path)[1].lower()])
        req = urllib.request.Request(
            "%s/api/community/posts/%s/media" % (shop.SITE, pid), data=body_bytes, method="POST",
            headers={"Content-Type": ctype, "Accept": "application/json",
                     "User-Agent": "AtechAtelier", "Authorization": "Bearer " + tok})
        st, out = account._call(req, opener or acct.opener, timeout=300)
        if st == 201:
            uploaded += 1
        else:
            failed.append((path, account._message(out, "upload failed (HTTP %d)" % st)))
    return {"ok": True, "id": pid, "uploaded": uploaded, "failed": failed, "message": ""}


def PostDialog(parent=None, doc_fn=export_tools._active_doc, acct=None, opener=None,
               background=True, share_fn=None, video_fn=None, publisher=None):
    """The Post to atech.dev window. share_fn(doc) -> a fresh share image
    path (export_tools.share_now), video_fn(label) -> the latest assembly
    video; publisher(**kw) -> publish()."""
    from PySide6 import QtCore, QtWidgets

    acct = acct or account.get()
    opener = opener or shop.open_url
    doc = doc_fn()
    label = getattr(doc, "Label", "") or ""
    d = export_tools._tool_dialog(QtWidgets.QDialog, parent, "Post to atech.dev")
    lay = QtWidgets.QVBoxLayout(d)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(8)
    t = QtWidgets.QLabel("Post to atech.dev", d)
    t.setObjectName("ToolTitle")
    lay.addWidget(t)
    d.who = QtWidgets.QLabel("", d)
    d.who.setObjectName("ToolMuted")
    d.who.setWordWrap(True)
    lay.addWidget(d.who)

    form = QtWidgets.QFormLayout()
    d.title = QtWidgets.QLineEdit(label, d)
    d.title.setMaxLength(140)
    d.title.setAccessibleName("Title")
    d.category = QtWidgets.QComboBox(d)
    d.category.setAccessibleName("Category")
    for text, value in CATEGORIES:
        d.category.addItem(text, value)
    d.text = QtWidgets.QPlainTextEdit(d)
    d.text.setPlaceholderText("What it is, what it does, how you built it.")
    d.text.setAccessibleName("Description")
    d.text.setFixedHeight(110)
    d.by = QtWidgets.QLineEdit(d)
    d.by.setPlaceholderText("your name, or names (optional)")
    d.by.setAccessibleName("Built by")
    form.addRow("Title", d.title)
    form.addRow("Category", d.category)
    form.addRow("Description", d.text)
    form.addRow("Built by", d.by)
    lay.addLayout(form)

    sec = QtWidgets.QLabel("PICTURES AND VIDEO", d)
    sec.setObjectName("ToolMuted")
    sec.setStyleSheet("font-weight: 600; margin-top: 8px;")
    lay.addWidget(sec)
    d.media = QtWidgets.QListWidget(d)
    d.media.setAccessibleName("Pictures and video to post")
    d.media.setFixedHeight(96)
    lay.addWidget(d.media)

    def add_media(path, checked=True):
        if not path or any(d.media.item(i).data(QtCore.Qt.UserRole) == path
                           for i in range(d.media.count())):
            return
        problem = media_problem(path)
        it = QtWidgets.QListWidgetItem(os.path.basename(path) + (" (%s)" % problem if problem else ""))
        it.setData(QtCore.Qt.UserRole, path)
        it.setFlags(it.flags() | QtCore.Qt.ItemIsUserCheckable)
        it.setCheckState(QtCore.Qt.Checked if checked and not problem else QtCore.Qt.Unchecked)
        if problem:
            it.setFlags(it.flags() & ~QtCore.Qt.ItemIsEnabled)
        d.media.addItem(it)

    d.add_media = add_media
    row = QtWidgets.QHBoxLayout()
    d.add = QtWidgets.QPushButton("Add pictures or video…", d)
    row.addWidget(d.add)
    row.addStretch(1)
    lay.addLayout(row)

    def chosen():
        return [d.media.item(i).data(QtCore.Qt.UserRole) for i in range(d.media.count())
                if d.media.item(i).checkState() == QtCore.Qt.Checked]

    d.status = QtWidgets.QLabel("", d)
    d.status.setObjectName("ToolMuted")
    d.status.setWordWrap(True)
    lay.addWidget(d.status)
    buttons = QtWidgets.QHBoxLayout()
    buttons.addStretch(1)
    d.sign_in = QtWidgets.QPushButton("Sign in to post", d)
    d.post = QtWidgets.QPushButton("Post", d)
    d.post.setObjectName("ToolPrimary")
    d.post.setDefault(True)
    buttons.addWidget(d.sign_in)
    buttons.addWidget(d.post)
    lay.addLayout(buttons)

    class Relay(QtCore.QObject):
        done = QtCore.Signal(object)
        signed = QtCore.Signal(object)
    relay = Relay(d)

    def sync():
        signed_in = acct.signed_in()
        u = acct.user or {}
        d.who.setText("Posting on atech.dev/community as %s." % (u.get("name") or u.get("email"))
                      if signed_in else "Sign in with your Atech account to post. It opens "
                      "atech.dev in your browser.")
        d.sign_in.setVisible(not signed_in)
        d.post.setEnabled(signed_in and bool(d.title.text().strip()))
        if signed_in and not d.by.text().strip() and u.get("name"):
            d.by.setText(u["name"])

    def sign_in():
        d.status.setText("Waiting for the browser: press Connect on the atech.dev page.")
        flow = account.SignIn(acct, opener=opener, done=lambda r: _emit(relay.signed, r))
        d.flow = flow
        flow.start()
        return flow

    def signed(result):
        d.flow = None
        d.status.setText("" if result.get("ok") else result.get("message", ""))
        sync()

    def _emit(signal, value):
        try:
            signal.emit(value)
        except RuntimeError:                              # the window closed first
            pass

    def post():
        title = d.title.text().strip()
        if not title:
            d.status.setText("Give the post a title.")
            return None
        kw = dict(title=title, body=compose_body(d.text.toPlainText(), d.by.text()),
                  category=d.category.currentData(), files=chosen(), acct=acct)
        d.post.setEnabled(False)
        d.status.setText("Posting…" + (" (uploading %d file%s)" % (
            len(kw["files"]), "" if len(kw["files"]) == 1 else "s") if kw["files"] else ""))
        run = publisher or publish
        if background:
            threading.Thread(target=lambda: _emit(relay.done, run(**kw)), daemon=True).start()
        else:
            posted(run(**kw))
        return kw

    def posted(res):
        d.result = res
        sync()
        if not res["ok"]:
            d.status.setText(res["message"])
            return
        msg = "Posted on atech.dev/community"
        if res["uploaded"]:
            msg += " with %d file%s" % (res["uploaded"], "" if res["uploaded"] == 1 else "s")
        msg += "."
        if res["failed"]:
            msg += " Not uploaded: %s." % "; ".join(
                "%s (%s)" % (os.path.basename(p), why) for p, why in res["failed"])
        d.status.setText(msg + " It is open in your browser.")
        d.post.setEnabled(False)
        d.post.setText("Posted")
        opener(COMMUNITY_URL)

    def browse():
        paths, _f = QtWidgets.QFileDialog.getOpenFileNames(
            d, "Add pictures or video", os.path.expanduser("~"),
            "Pictures and video (*.png *.jpg *.jpeg *.webp *.mp4 *.mov *.webm)")
        for p in paths:
            add_media(p)

    relay.done.connect(posted)
    relay.signed.connect(signed)
    d.title.textChanged.connect(lambda _=None: sync())
    d.sign_in.clicked.connect(lambda _=False: export_tools._guard(sign_in))
    d.post.clicked.connect(lambda _=False: export_tools._guard(post))
    d.add.clicked.connect(lambda _=False: export_tools._guard(browse))
    d.do_post, d.do_sign_in, d.chosen, d.flow = post, sign_in, chosen, None

    # the pictures: a fresh share image, and the latest assembly video
    if doc is not None:
        share = share_fn or (lambda dd: export_tools.share_now(d, lambda: dd)[0])
        try:
            add_media(share(doc))
        except Exception as exc:                          # noqa: BLE001
            _log("share image: %r" % (exc,))
        add_media((video_fn or latest_video)(label))
    sync()
    d.resize(560, 560)
    return d
