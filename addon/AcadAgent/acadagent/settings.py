"""settings — API key entry and backend configuration.

The key is handed to the agent backend, never stored by this addon in
plaintext of its own. opencode owns credential storage; we POST the key to
its auth endpoint and keep only the provider choice locally.

Backend is opencode FOR NOW. The harness we intend to own replaces the
client in client.py without touching this pane - see docs/prd/agent_harness.md.
"""
import json
import os
import urllib.error
import urllib.request

from PySide6 import QtCore, QtWidgets

CONFIG_DIR = os.path.join(
    os.path.expanduser("~"), ".config", "acadagent")
CONFIG_PATH = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS = {
    "backend_url": "http://127.0.0.1:4096",
    "provider": "anthropic",
    "model": "",
    # Explicit path to the `claude` binary. Empty = look in the usual places
    # (claude_cli.find_claude). For installs a desktop launch cannot see.
    "claude_path": "",
    # Per-turn cost is shown only on request: on a Claude subscription the
    # CLI still reports an API-equivalent dollar figure nobody is billed.
    "show_cost": False,
    # Which version of the data notice (PRIVACY_NOTICE_VERSION) the user has
    # acknowledged. None = never shown / never acknowledged.
    "privacy_ack": None,
    # The chat agent (Claude Code), passed through claude_cli.agent_argv
    # (S16/S26). "" = the CLI's own default: MEASURED 2026-09-25 with the
    # isolated launch, that is Opus (init reports claude-opus-5). Sonnet
    # becomes the default only if a full eval earns it (release PRD S26).
    "agent_model": "",
    "agent_effort": "",
    # --max-budget-usd per turn; 0 = no limit.
    "agent_budget_usd": 3.00,
}

#: Model choices offered for Claude Code (aliases the CLI resolves itself).
AGENT_MODELS = [
    ("", "Claude Code default (Opus)"),
    ("opus", "Opus"),
    ("sonnet", "Sonnet"),
    ("haiku", "Haiku"),
]

PROVIDERS = [
    ("anthropic", "Anthropic"),
    ("openai", "OpenAI"),
    ("openrouter", "OpenRouter"),
    ("opencode", "OpenCode Zen"),
]

#: Placeholder shown in the key field for each provider: the key's visible
#: prefix where the vendor has one, never another vendor's.
KEY_PLACEHOLDERS = {
    "anthropic": "sk-ant-…",
    "openai": "sk-…",
    "openrouter": "sk-or-…",
    "opencode": "API key",
}


def load():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            cfg.update(data)
    except (OSError, ValueError):
        pass
    return cfg


def save(cfg):
    """Write the settings. Raises OSError when the folder is not writable;
    callers show "Could not save settings" rather than a traceback."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, CONFIG_PATH)     # never a half-written settings.json
    return CONFIG_PATH


def update(**changes):
    """Merge `changes` into the stored settings. Returns True when saved.

    Every writer goes through a merge: a dialog that rebuilt the whole dict
    used to drop keys it did not know about (the privacy acknowledgement
    would have been forgotten on the next Save)."""
    cfg = load()
    cfg.update(changes)
    try:
        save(cfg)
        return True
    except OSError:
        return False


# ------------------------------------------------------------ data notice
#: Bump when the notice text changes materially; the user is asked again.
#: 2 = the final wording (2026-10-03); 1 was the draft shown during testing.
PRIVACY_NOTICE_VERSION = 2

#: Every statement below was read off the code, and must stay true of it:
#:   what you type + build.document_brief (document name; each solid's name,
#:   volume and size; Atech board/module names, ports and size; the 3D-view
#:   selection with picked points) -> panel._send_claude;
#:   "Add view" / "Ask about this view" PNGs -> panel._turn_images, vision;
#:   files the agent reads -> claude_cli.agent_argv (tools Read, Write, Edit,
#:   Glob, Grep and only `./check` for Bash; one --add-dir: the chat folder),
#:   including check.png, the picture ./check renders of its own build;
#:   chat folders -> build.new_workspace; the script on the objects ->
#:   build.apply (AtechAgentScript); ~/.claude -> Claude Code itself.
#: Claude Code's own default prompt is kept (--append-system-prompt), so
#: what it adds to any session goes too. The notice makes no claim about
#: what Anthropic keeps or for how long: that is Anthropic's terms for the
#: user's own Claude account, not restated here.
PRIVACY_NOTICE_TITLE = "Before your first message"
PRIVACY_NOTICE_BODY = (
    "The chat runs Claude Code on this computer, signed in to your own "
    "Claude account. Each message you send goes to Anthropic through that "
    "account, together with:\n"
    "  - a summary of the open document: its name, each solid's name, "
    "volume and size, the Atech board and modules on it, and what you have "
    "selected in the 3D view;\n"
    "  - any picture of the 3D view you attach with \"Add view\" or "
    "\"Ask about this view\";\n"
    "  - the files the agent reads in this chat's folder while it works: "
    "its design script, the pictures it renders of its own build to check "
    "it, the Atech reference files copied there, and what its build "
    "check (./check) prints.\n"
    "Claude Code also adds what it includes in any session, such as the "
    "chat folder's path and the name of your operating system. What "
    "Anthropic does with all of this is set by the terms of your Claude "
    "account.\n"
    "Kept on this computer:\n"
    "  - one folder per chat, with the design script and pictures, in %s "
    "(Agent Settings can delete old ones);\n"
    "  - the design script inside every document the agent builds into, so "
    "it is saved with your .FCStd file;\n"
    "  - Claude Code's own conversation history, under ~/.claude;\n"
    "  - these settings, in %s."
)


def privacy_acknowledged(cfg=None):
    cfg = cfg if cfg is not None else load()
    try:
        return int(cfg.get("privacy_ack") or 0) >= PRIVACY_NOTICE_VERSION
    except (TypeError, ValueError):
        return False


def acknowledge_privacy():
    """Persist the acknowledgement. False when it could not be written."""
    return update(privacy_ack=PRIVACY_NOTICE_VERSION)


def privacy_notice_body():
    return PRIVACY_NOTICE_BODY % (chat_workspace_root(), CONFIG_PATH)


# ------------------------------------------------------ chat workspaces
def chat_workspace_root():
    """The folder build.new_workspace() creates chat-* folders in.

    Same derivation as build.new_workspace (FreeCAD's user data dir, else
    ~/.local/share/Atech Atelier) - kept in step by
    tests/test_chat_robustness.py, which compares the two."""
    try:
        import FreeCAD
        root = FreeCAD.getUserAppDataDir()
    except Exception:                                  # noqa: BLE001
        root = os.path.expanduser("~/.local/share/Atech Atelier")
    return os.path.join(root, "agent")


def old_workspaces(keep=(), root=None):
    """chat-* folders under the workspace root, except those in `keep`.
    Returns [(path, bytes)]. Only folders named chat-* are ever listed."""
    root = root or chat_workspace_root()
    keep = {os.path.realpath(k) for k in keep if k}
    out = []
    try:
        names = sorted(os.listdir(root))
    except OSError:
        return out
    for name in names:
        path = os.path.join(root, name)
        if not name.startswith("chat-") or os.path.islink(path) or \
                not os.path.isdir(path) or os.path.realpath(path) in keep:
            continue
        size = 0
        for dp, _dn, fn in os.walk(path):
            for f in fn:
                try:
                    size += os.path.getsize(os.path.join(dp, f))
                except OSError:
                    pass
        out.append((path, size))
    return out


def clear_workspaces(keep=(), root=None):
    """Delete old chat folders (never those in `keep`, never anything not
    named chat-*). Returns (removed_count, failed_count)."""
    import shutil
    import stat
    removed = failed = 0

    def _writable(fn, p, _exc):
        # Reference copies are made read-only on purpose (R14).
        try:
            os.chmod(p, stat.S_IWUSR | stat.S_IRUSR)
            fn(p)
        except OSError:
            pass
    for path, _size in old_workspaces(keep, root):
        try:
            shutil.rmtree(path, onerror=_writable)
        except OSError:
            pass
        if os.path.exists(path):
            failed += 1
        else:
            removed += 1
    return removed, failed


def _human(n):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "bytes" else \
                ("%.1f %s" % (n, unit))
        n /= 1024.0


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("[AcadAgent settings] %s\n" % msg)
    except Exception:                                  # noqa: BLE001
        pass


def _hostport(url):
    return url.split("//")[-1].split("/")[0] or url


def key_url_ok(base_url):
    """(ok, reason) - may an API key be sent to this backend URL? (R24)

    Only over https, or plain http to this computer (127.0.0.1, ::1,
    localhost). A key typed into a free-text URL field must never cross the
    network in clear text."""
    try:
        from urllib.parse import urlsplit
        parts = urlsplit((base_url or "").strip())
        host = (parts.hostname or "").lower()
    except ValueError:
        return False, "That backend address is not a valid URL."
    if parts.scheme == "https" and host:
        return True, ""
    if parts.scheme == "http" and host in ("127.0.0.1", "::1", "localhost"):
        return True, ""
    return False, ("The key was not sent: the backend address must be "
                   "https, or http on this computer (127.0.0.1).")


def set_api_key(base_url, provider, key, timeout=20):
    """PUT the key to the backend. Returns (ok, message).

    Never reports success it did not observe. The message is plain words for
    the dialog; the raw cause goes to the Report view.
    """
    ok, why = key_url_ok(base_url)
    if not ok:
        _log("key PUT refused for %r" % (base_url,))
        return False, why
    url = "%s/auth/%s" % (base_url.rstrip("/"), provider)
    body = json.dumps({"type": "api", "key": key}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="PUT",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if 200 <= code < 300:
                return True, "Key saved."
            _log("key PUT returned HTTP %d" % code)
            return False, "The agent server did not accept the key."
    except urllib.error.HTTPError as exc:
        _log("key PUT HTTP %d: %s" % (exc.code, exc.read()[:200].decode(
            "utf-8", "replace")))
        return False, "The agent server did not accept the key."
    except (urllib.error.URLError, OSError) as exc:
        _log("key PUT failed: %r" % (exc,))
        return False, ("Could not reach the agent server at %s."
                       % _hostport(base_url))


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, keep_workspaces=()):
        super().__init__(parent)
        self.setWindowTitle("Agent Settings")
        self.setMinimumWidth(430)
        cfg = load()
        self._keep = tuple(keep_workspaces or ())

        form = QtWidgets.QFormLayout(self)

        # ENGINE first: it decides whether anything below it even applies.
        # Claude Code uses your existing Claude Code login and needs no key;
        # OpenCode and the direct API need a provider and a token.
        from . import engine as _engine
        self._engine_mod = _engine
        self.engine = QtWidgets.QComboBox()
        # R24: the public build offers Claude Code only; the dev engines
        # need ATECH_DEV_ENGINES=1.
        self._dev = _engine.dev_engines()
        for eid, title, desc in _engine.offered():
            self.engine.addItem(title, eid)
            self.engine.setItemData(self.engine.count() - 1, desc,
                                    QtCore.Qt.ToolTipRole)
        eidx = self.engine.findData(_engine.current())
        if eidx >= 0:
            self.engine.setCurrentIndex(eidx)
        self.engine.currentIndexChanged.connect(self._on_engine_changed)
        form.addRow("Agent engine", self.engine)

        self.engine_note = QtWidgets.QLabel("")
        self.engine_note.setWordWrap(True)
        self.engine_note.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse)
        self.engine_note.setStyleSheet("color: #9BA4BE; font-size: 11px;")
        form.addRow("", self.engine_note)

        # Where claude lives, for installs a desktop launch cannot see (R22).
        prow = QtWidgets.QHBoxLayout()
        self.claude_path = QtWidgets.QLineEdit(cfg.get("claude_path") or "")
        self.claude_path.setPlaceholderText("found automatically")
        self.claude_path.editingFinished.connect(self._on_engine_changed)
        browse = QtWidgets.QPushButton("Browse…")
        browse.clicked.connect(self._on_browse)
        prow.addWidget(self.claude_path, 1)
        prow.addWidget(browse)
        self._claude_row = QtWidgets.QWidget()
        self._claude_row.setLayout(prow)
        prow.setContentsMargins(0, 0, 0, 0)
        form.addRow("Claude Code", self._claude_row)

        # The chat agent's model, effort and per-turn budget (S16/S26).
        self.agent_model = QtWidgets.QComboBox()
        self.agent_model.setEditable(True)
        for mid, label in AGENT_MODELS:
            self.agent_model.addItem(label, mid)
        cur = (cfg.get("agent_model") or "").strip()
        midx = self.agent_model.findData(cur)
        if midx >= 0:
            self.agent_model.setCurrentIndex(midx)
        else:
            self.agent_model.setEditText(cur)
        form.addRow("Claude model", self.agent_model)
        self.agent_effort = QtWidgets.QComboBox()
        self.agent_effort.addItem("Claude Code default", "")
        from . import claude_cli as _cc
        for lvl in _cc.EFFORTS:
            self.agent_effort.addItem(lvl, lvl)
        eidx2 = self.agent_effort.findData(cfg.get("agent_effort") or "")
        self.agent_effort.setCurrentIndex(max(0, eidx2))
        form.addRow("Effort", self.agent_effort)
        self.agent_budget = QtWidgets.QDoubleSpinBox()
        self.agent_budget.setRange(0.0, 100.0)
        self.agent_budget.setSingleStep(0.5)
        self.agent_budget.setDecimals(2)
        self.agent_budget.setPrefix("$ ")
        self.agent_budget.setSpecialValueText("no limit")
        try:
            self.agent_budget.setValue(float(cfg.get("agent_budget_usd")
                                             or 0.0))
        except (TypeError, ValueError):
            self.agent_budget.setValue(_cc.DEFAULT_BUDGET_USD)
        self.agent_budget.setToolTip(
            "Claude Code stops a reply that would cost more than this "
            "(API-equivalent figure).")
        form.addRow("Budget per reply", self.agent_budget)

        self.backend = QtWidgets.QLineEdit(cfg["backend_url"])
        form.addRow("Backend URL", self.backend)

        self.provider = QtWidgets.QComboBox()
        for pid, label in PROVIDERS:
            self.provider.addItem(label, pid)
        idx = self.provider.findData(cfg.get("provider", "anthropic"))
        if idx >= 0:
            self.provider.setCurrentIndex(idx)
        self.provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider", self.provider)

        self.key = QtWidgets.QLineEdit()
        self.key.setEchoMode(QtWidgets.QLineEdit.Password)
        form.addRow("API key", self.key)

        self.model = QtWidgets.QLineEdit(cfg.get("model", ""))
        self.model.setPlaceholderText("leave blank for the default model")
        form.addRow("Model", self.model)

        self.show_cost = QtWidgets.QCheckBox(
            "Show the reported cost of each reply")
        self.show_cost.setChecked(bool(cfg.get("show_cost")))
        self.show_cost.setToolTip(
            "On a Claude subscription this is an API-equivalent figure, not "
            "what you are billed.")
        form.addRow("", self.show_cost)
        self._form = form
        if not self._dev:
            # R24: fields that only the dev engines use are not shown at all
            # (a key field that does nothing invites a pasted secret).
            for w in (self.backend, self.provider, self.key, self.model):
                self._hide_row(w)

        # Chat folders persist; the user can clear them here (R02).
        wrow = QtWidgets.QHBoxLayout()
        wrow.setContentsMargins(0, 0, 0, 0)
        self.ws_info = QtWidgets.QLabel("")
        self.ws_info.setWordWrap(True)
        self.ws_btn = QtWidgets.QPushButton("Clear old chat workspaces")
        self.ws_btn.clicked.connect(self._on_clear_ws)
        self.ws_confirm = QtWidgets.QPushButton("")
        self.ws_confirm.hide()
        self.ws_confirm.clicked.connect(self._on_clear_ws_confirmed)
        wrow.addWidget(self.ws_btn)
        wrow.addWidget(self.ws_confirm)
        wrow.addStretch(1)
        ww = QtWidgets.QWidget()
        ww.setLayout(wrow)
        form.addRow("Chat data", ww)
        form.addRow("", self.ws_info)

        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        # The install command shows here: it must be copyable.
        self.status.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        form.addRow(self.status)

        btns = QtWidgets.QDialogButtonBox()
        self.test_btn = btns.addButton("Test connection",
                                       QtWidgets.QDialogButtonBox.ActionRole)
        btns.addButton(QtWidgets.QDialogButtonBox.Save)
        btns.addButton(QtWidgets.QDialogButtonBox.Cancel)
        self.test_btn.clicked.connect(self._on_test)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

        self._on_provider_changed()
        self._on_engine_changed()

    def _hide_row(self, widget):
        try:
            self._form.setRowVisible(widget, False)
        except AttributeError:          # Qt < 6.4
            widget.hide()
            lbl = self._form.labelForField(widget)
            if lbl is not None:
                lbl.hide()

    def _on_provider_changed(self, *_):
        self.key.setPlaceholderText(
            KEY_PLACEHOLDERS.get(self.provider.currentData(), "API key"))

    def _on_browse(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Find the claude program", os.path.expanduser("~"))
        if path:
            self.claude_path.setText(path)
            self._on_engine_changed()

    def _claude_ready(self):
        """(ok, text) for the path in the field, without saving it."""
        from . import claude_cli
        typed = self.claude_path.text().strip()
        exe = claude_cli.find_claude(explicit=typed)
        if typed and exe is None:
            return False, ("There is no program at that path. Leave it "
                           "empty to search the usual places.")
        if exe:
            return True, "Claude Code: %s" % exe
        return False, ("Claude Code was not found. Install it by running "
                       "this in a terminal:\n    %s\nthen run `%s`. "
                       "Instructions: %s. Or set its path above."
                       % (claude_cli.INSTALL_COMMAND, claude_cli.LOGIN_COMMAND,
                          claude_cli.INSTALL_URL))

    def _on_engine_changed(self, *_):
        """Only show credential fields for engines that actually use them.

        A key field that does nothing is worse than an absent one: it invites
        the user to paste a secret that will never be read.
        """
        eid = self.engine.currentData()
        uses = self._engine_mod.uses_provider(eid)
        for w in (self.provider, self.key, self.model):
            w.setEnabled(uses)
        self.backend.setEnabled(eid == self._engine_mod.OPENCODE)
        self.test_btn.setEnabled(eid == self._engine_mod.OPENCODE)
        self.test_btn.setVisible(self._dev)
        self._claude_row.setEnabled(eid == self._engine_mod.CLAUDE)
        for w in (self.agent_model, self.agent_effort, self.agent_budget):
            w.setEnabled(eid == self._engine_mod.CLAUDE)
        desc = next((d for i, t, d in self._engine_mod.ENGINES if i == eid), "")
        if eid == self._engine_mod.CLAUDE:
            ok, text = self._claude_ready()
            self.engine_note.setText(desc)
            self._set_status(text, ok)
            return
        ok, why = self._engine_mod.available(eid)
        self.engine_note.setText(desc if ok else "%s\n%s" % (desc, why))
        self._set_status("Ready." if ok else "Not available right now.", ok)

    def _set_status(self, text, ok=None):
        colour = {True: "#6bbd85", False: "#e0705f", None: "#a8a49c"}[ok]
        self.status.setText(text)
        self.status.setStyleSheet("color: %s;" % colour)

    def _on_test(self):
        base = self.backend.text().strip().rstrip("/")
        url = base + "/api/health"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                ok = 200 <= resp.getcode() < 300
                self._set_status("The agent server answered." if ok else
                                 "The agent server answered with an error.",
                                 ok)
        except Exception as exc:                  # noqa: BLE001
            _log("health test failed: %r" % (exc,))
            self._set_status("Could not reach the agent server at %s."
                             % _hostport(base), False)

    def _agent_model_value(self):
        """The model alias: the chosen item's data, or typed text."""
        text = self.agent_model.currentText().strip()
        idx = self.agent_model.findText(text)
        if idx >= 0:
            return self.agent_model.itemData(idx) or ""
        return text

    def _on_clear_ws(self):
        old = old_workspaces(self._keep)
        if not old:
            self.ws_info.setText("No old chat workspaces to clear.")
            self.ws_confirm.hide()
            return
        total = sum(n for _p, n in old)
        self.ws_info.setText(
            "%d folder%s, %s, in %s. The chat that is open now is kept."
            % (len(old), "" if len(old) == 1 else "s", _human(total),
               chat_workspace_root()))
        self.ws_confirm.setText("Delete %d folder%s"
                                % (len(old), "" if len(old) == 1 else "s"))
        self.ws_confirm.show()

    def _on_clear_ws_confirmed(self):
        removed, failed = clear_workspaces(self._keep)
        self.ws_confirm.hide()
        if failed:
            self.ws_info.setText("Deleted %d; %d could not be deleted."
                                 % (removed, failed))
        else:
            self.ws_info.setText("Deleted %d old chat workspace%s."
                                 % (removed, "" if removed == 1 else "s"))

    def _on_save(self):
        eid = self.engine.currentData()
        changes = {
            "backend_url": self.backend.text().strip(),
            "provider": self.provider.currentData(),
            "model": self.model.text().strip(),
            "engine": eid,
            "claude_path": self.claude_path.text().strip(),
            "show_cost": bool(self.show_cost.isChecked()),
            "agent_model": self._agent_model_value(),
            "agent_effort": self.agent_effort.currentData() or "",
            "agent_budget_usd": round(float(self.agent_budget.value()), 2),
        }
        if not self._dev:
            # Hidden fields keep their stored values.
            for k in ("backend_url", "provider", "model"):
                changes.pop(k)
        key = self.key.text().strip()
        # A key is only sent to a backend that will store it. Claude Code has
        # its own auth and no endpoint to PUT a key to.
        if key and not self._engine_mod.uses_provider(eid):
            self._set_status("Claude Code uses its own sign-in; the API key "
                             "was not used.", None)
            key = ""
        if key:
            ok, msg = set_api_key(self.backend.text().strip(),
                                  self.provider.currentData(),
                                  key)
            if not ok:
                self._set_status(msg, False)
                return
            self._set_status(msg, True)
        if key and eid == "api":
            changes["api_key_set"] = True
        cfg = load()                 # merge: keep keys this dialog not owns
        cfg.update(changes)
        try:
            save(cfg)
        except OSError as exc:
            _log("save failed: %r" % (exc,))
            self._set_status("Could not save settings. Check that %s is "
                             "writable." % CONFIG_DIR, False)
            return
        self._set_status("Saved", True)
        QtCore.QTimer.singleShot(500, self.accept)


def open_dialog(parent=None, keep_workspaces=()):
    """Show the dialog. True when the user saved (the caller re-probes)."""
    dlg = SettingsDialog(parent, keep_workspaces=keep_workspaces)
    return bool(dlg.exec())      # QDialog.Accepted == 1
