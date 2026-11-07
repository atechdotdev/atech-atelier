"""R860 Home's account button: "Sign in", "Waiting for the browser...", or
the signed-in name with its menu (account.py does the work)."""
import threading

from PySide6 import QtCore, QtGui, QtWidgets

from . import account, shop


class _Relay(QtCore.QObject):
    done = QtCore.Signal(object)
    changed = QtCore.Signal()


class AccountButton(QtWidgets.QPushButton):
    """Signed out: Sign in (opens atech.dev/connect/atelier). Waiting: a
    menu to open the page again, paste the code, or cancel. Signed in: the
    name, with the email, the account page and Sign out."""

    def __init__(self, parent=None, acct=None, opener=None, background=True):
        super().__init__(parent)
        self.setObjectName("HomeBtn")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.acct = acct or account.get()
        self.opener = opener or shop.open_url
        self.background = background
        self.flow = None
        self.last_message = ""
        self._relay = _Relay(self)
        self._relay.done.connect(self._finished)
        self._relay.changed.connect(self.sync)
        self.clicked.connect(self._click)
        self.sync()
        if self.acct.signed_in():
            # check the session is still good, and pick up a new name
            self._bg(lambda: (self.acct.refresh_profile(), self._emit_changed()))

    def _bg(self, fn):
        if self.background:
            threading.Thread(target=fn, daemon=True).start()
        else:
            fn()

    def _emit_changed(self):
        try:
            self._relay.changed.emit()
        except RuntimeError:                              # the window closed first
            pass

    # -- state -------------------------------------------------------- #
    def sync(self):
        if self.flow is not None:
            self.setText("Waiting for the browser…")
            self.setAccessibleName("Signing in: waiting for the browser")
            self.setToolTip("Connect Atech Atelier on the atech.dev page that opened. "
                            "Click for more.")
        elif self.acct.signed_in():
            u = self.acct.user
            self.setText(self.acct.label())
            self.setAccessibleName("Signed in as %s" % u.get("email", ""))
            self.setToolTip("Signed in to Atech as %s" % u.get("email", ""))
        else:
            self.setText("Sign in")
            self.setAccessibleName("Sign in with your Atech account")
            self.setToolTip("Sign in with your atech.dev account, the one your Atech board "
                            "and projects are on. Opens atech.dev in your browser.")

    def _click(self):
        if self.flow is None and not self.acct.signed_in():
            return self.sign_in()
        self.menu().popup(self.mapToGlobal(QtCore.QPoint(0, self.height())))

    def menu(self):
        m = QtWidgets.QMenu(self)
        if self.flow is not None:
            m.addAction("Open the page again", lambda: self.opener(self.flow.url))
            m.addAction("Copy the link", lambda: QtGui.QGuiApplication.clipboard().setText(
                self.flow.url))
            m.addAction("Paste a code…", self.paste_code)
            m.addSeparator()
            m.addAction("Cancel", self.cancel)
        else:
            u = self.acct.user or {}
            who = m.addAction(u.get("email", ""))
            who.setEnabled(False)
            m.addAction("Your account on atech.dev", lambda: self.opener(shop.SITE + "/account"))
            m.addSeparator()
            m.addAction("Sign out", self.sign_out)
        self._menu = m
        return m

    # -- actions ------------------------------------------------------ #
    def sign_in(self):
        self.last_message = ""
        self.flow = account.SignIn(self.acct, opener=self.opener, done=self._emit_done)
        self.sync()
        self.flow.start()
        return self.flow

    def _emit_done(self, result):
        try:
            self._relay.done.emit(result)
        except RuntimeError:
            pass

    def _finished(self, result):
        self.flow = None
        self.last_message = result.get("message", "")
        self.sync()
        if not result.get("ok") and self.last_message and not result.get("cancelled"):
            QtWidgets.QToolTip.showText(self.mapToGlobal(QtCore.QPoint(0, self.height())),
                                        self.last_message, self)

    def paste_code(self, code=None):
        if self.flow is None:
            return None
        if code is None:
            code, ok = QtWidgets.QInputDialog.getText(
                self, "Paste the code", "The code from the atech.dev page:")
            if not ok or not code.strip():
                return None
        flow = self.flow
        self._bg(lambda: flow.submit_code(code))
        return True

    def cancel(self):
        if self.flow is not None:
            self.flow.cancel()

    def sign_out(self):
        self._bg(lambda: (self.acct.sign_out(), self._emit_changed()))
