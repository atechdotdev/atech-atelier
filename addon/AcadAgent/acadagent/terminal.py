"""terminal — a real shell in a FreeCAD dock, on a stdlib pty.

WHY A PTY AND NOT AN EMBEDDED TERMINAL EMULATOR
    Reparenting a real terminal (`xterm -into <winid>` + QWindow.fromWinId +
    createWindowContainer) gives perfect fidelity, and both Qt calls exist
    here — but MEASURED 2026-09-24: no terminal emulator is installed on this
    machine (no xterm, urxvt, alacritty or kitty), so that route would add a
    hard external dependency to a product whose point is that it works out of
    the box.

    `pty` is in the Python standard library and is already present inside the
    AppImage. ptyprocess and pyte are NOT (measured), so this file uses
    neither.

WHAT THIS IS AND IS NOT
    It IS a real pty: `claude`, `bin/cad`, git and an interactive shell all
    run in it and see a tty, so they stream and colour normally.

    It is NOT a full VT100 emulator. We render a useful subset — newlines,
    carriage returns, backspace, and SGR colour — and STRIP the cursor
    addressing and screen-clearing sequences a full-screen TUI needs. So
    `vim` or `htop` will look wrong. That limit is stated in the UI rather
    than discovered, because a terminal that silently garbles a TUI is worse
    than one that says what it cannot do.

THREADING
    The reader runs on a QThread and emits text; the widget appends on the
    GUI thread. FreeCAD's GUI is not thread-safe (see runner.py). The reader
    has NO Qt parent and is held in _LIVE until it finishes: a QThread
    deleted with its parent widget while running aborts the whole app (R20).
    close_session() stops and joins it, closes the fd, SIGHUPs the shell and
    reaps it; the dock calls that at quit.
"""
import os
import re
import pty
import select
import signal
import tempfile
import time

from PySide6 import QtCore, QtGui, QtWidgets

from . import style


# Sequences we deliberately drop rather than half-render. Cursor movement and
# erase-display are exactly what a full-screen TUI uses; leaving them in makes
# the transcript nonsense.
_CSI = re.compile(r"\x1b\[[0-9;?]*[A-HJKSTfhlmnsu]")
_OSC = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
_OTHER = re.compile(r"\x1b[()#][0-9A-Za-z]|\x1b[=>]|\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(s):
    """Remove escape sequences, keeping printable text."""
    s = _OSC.sub("", s)
    s = _CSI.sub("", s)
    s = _OTHER.sub("", s)
    return s.replace("\x07", "")


# Variables the AppImage's AppRun (and the AppImage runtime) export for the
# bundled FreeCAD. Inherited by a user's shell they break unrelated tools:
# PYTHONHOME/PYTHONPATH point every python at the bundled stdlib, SSL_CERT_FILE
# at the bundle's CA file, QT_QPA_PLATFORM=xcb forces X11 on Wayland apps.
# MEASURED from dist/build/squashfs-root/AppRun.
APPRUN_ONLY = ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH",
               "PATH_TO_FREECAD_LIBDIR", "QT_QPA_PLATFORM", "SSL_CERT_FILE",
               "GIT_SSL_CAINFO", "FONTCONFIG_FILE", "FONTCONFIG_PATH")
APPIMAGE_RUNTIME = ("APPDIR", "APPIMAGE", "ARGV0", "OWD")
_INTERPRETER = ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH")

# The pre-AppRun snapshot the build inserts at the top of AppRun (R61,
# branding/apprun_env.py): ATECH_APPRUN_SET lists the names AppRun is about to
# export; ATECH_PRE_APPRUN_<NAME> holds the caller's value, only for names the
# caller had set. branding/ is not shipped inside the addon, so its
# restore() is mirrored here; test_shell_round3 checks the two agree.
SNAP_PREFIX = "ATECH_PRE_APPRUN_"
SNAP_LIST = "ATECH_APPRUN_SET"


def apprun_restore(env):
    """(env, restored_names): `env` as it was before AppRun ran, per the
    snapshot. A name AppRun set gets the caller's value back, or is removed
    when the caller had none (removed, not emptied); the snapshot variables
    themselves go. Without a snapshot nothing but the (absent) snapshot
    variables changes and restored_names is empty."""
    env = dict(env)
    names = env.pop(SNAP_LIST, "").split()
    restored = set()
    for n in names:
        key = SNAP_PREFIX + n
        if key in env:
            env[n] = env[key]
            restored.add(n)
        else:
            env.pop(n, None)
    for k in [k for k in env if k.startswith(SNAP_PREFIX)]:
        env.pop(k)
    return env, restored


def clean_env(env=None):
    """The environment for a child the user will type into.

    First the pre-AppRun snapshot is applied (R96): a value the user had
    before Studio started (QT_QPA_PLATFORM=wayland, a corporate
    SSL_CERT_FILE, their own PYTHONPATH) comes back instead of being lost.
    Then, for names the snapshot did not give back: the interpreter
    variables always go; inside an AppImage (APPDIR set) so do the rest of
    the AppRun list and the runtime's own variables. Finally every path
    that points into the mounted image (PREFIX=<APPDIR>/usr and the like) -
    a path that vanishes when Studio quits - is dropped, restored values
    included (a value leaked from an outer Studio is still the image's). In
    a list variable (PATH=<APPDIR>/usr/bin:/usr/bin) only the image's
    entries go; dropping the whole variable would lose the user's own PATH
    and with it `claude` in ~/.local/bin."""
    env = dict(os.environ if env is None else env)
    appdir = env.get("APPDIR") or ""
    env, restored = apprun_restore(env)
    for k in _INTERPRETER:
        if k not in restored:
            env.pop(k, None)
    if appdir:
        for k in APPRUN_ONLY + APPIMAGE_RUNTIME:
            if k not in restored:
                env.pop(k, None)
        top = appdir.rstrip("/")
        root = top + "/"

        def inside(part):
            return part == top or part.startswith(root)

        for k, v in list(env.items()):
            parts = v.split(os.pathsep)
            keep = [p for p in parts if not inside(p)]
            if len(keep) == len(parts):
                continue
            if any(keep):
                env[k] = os.pathsep.join(keep)
            else:
                env.pop(k)
    env["TERM"] = "dumb"          # we are not a full VT100; say so
    return env


# zsh's startup files, in the directory zsh reads them from ($ZDOTDIR, else
# $HOME). With none of them zsh runs zsh-newuser-install - a full-screen
# first-run menu - in every new interactive shell (R106, reproduced with zsh
# 5.9 and an empty HOME: "This is the Z Shell configuration function for new
# users"). The dock renders no TUI, so the user saw a menu they could not
# drive while the header said the terminal was ready.
ZSH_STARTUP = (".zshenv", ".zprofile", ".zshrc", ".zlogin")
ZSH_FALLBACK_RC = (
    "# Written by Atech Atelier for its Terminal dock: you have no zsh\n"
    "# startup files, and zsh would otherwise open its first-run menu\n"
    "# (zsh-newuser-install), which the dock cannot draw. Your own ~/.zshrc,\n"
    "# once it exists, is used instead of this file.\n"
    "PS1='%~ %# '\n")


def _zsh_fallback_dir():
    """A private directory holding the fallback .zshrc (0700, per user, in
    the temp dir - never the user's home). None when it cannot be made."""
    d = os.path.join(tempfile.gettempdir(),
                     "atech-atelier-zsh-%d" % os.getuid())
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        st = os.lstat(d)
        if st.st_uid != os.getuid() or not os.path.isdir(d) \
                or os.path.islink(d):
            return None                  # someone else's directory
        rc = os.path.join(d, ".zshrc")
        cur = None
        if os.path.isfile(rc):
            with open(rc, encoding="utf-8") as f:
                cur = f.read()
        if cur != ZSH_FALLBACK_RC:
            with open(rc, "w", encoding="utf-8") as f:
                f.write(ZSH_FALLBACK_RC)
        return d
    except OSError:
        return None


def shell_command(env, command=None, fallback_dir=None):
    """(argv, env, shell_name) for the dock's session.

    `command` runs as given. Otherwise the user's $SHELL, interactive. A zsh
    whose startup directory holds none of ZSH_STARTUP gets ZDOTDIR pointed at
    a private directory with a minimal .zshrc, so it starts at a prompt, not
    in zsh-newuser-install (R106). A user who has any zsh startup file keeps
    exactly their own setup: nothing is changed for them."""
    env = dict(env)
    if command:
        argv = list(command)
    else:
        argv = [env.get("SHELL") or "/bin/bash", "-i"]
    name = os.path.basename(argv[0]) or argv[0]
    if name == "zsh" or name.startswith("zsh-") or name.startswith("zsh5"):
        home = env.get("ZDOTDIR") or env.get("HOME") \
            or os.path.expanduser("~")
        if not any(os.path.exists(os.path.join(home, f))
                   for f in ZSH_STARTUP):
            d = fallback_dir if fallback_dir is not None \
                else _zsh_fallback_dir()
            if d:
                env["ZDOTDIR"] = d
        name = "zsh"
    return argv, env, name


_LIVE = set()     # running readers, held until finished (no Qt parent)


class PtyReader(QtCore.QThread):
    """Reads a pty master fd and emits decoded chunks. On EOF (the shell
    exited by itself) it reaps the child and emits `ended`; when stopped by
    close_session() it emits nothing and leaves the reaping to it."""

    chunk = QtCore.Signal(str)
    ended = QtCore.Signal(int)

    def __init__(self, fd, pid, parent=None):
        super().__init__(parent)
        self._fd = fd
        self._pid = pid
        self._stop = False
        _LIVE.add(self)
        self.finished.connect(lambda: _LIVE.discard(self))

    def run(self):
        buf = b""
        while not self._stop:
            try:
                r, _, _ = select.select([self._fd], [], [], 0.2)
            except Exception:
                break
            if not r:
                continue
            try:
                data = os.read(self._fd, 8192)
            except OSError:
                break
            if not data:
                break
            buf += data
            # Decode on a boundary we can trust; a split UTF-8 sequence would
            # otherwise render as a replacement character forever.
            try:
                text = buf.decode("utf-8")
                buf = b""
            except UnicodeDecodeError:
                try:
                    text = buf[:-1].decode("utf-8")
                    buf = buf[-1:]
                except Exception:
                    continue
            if text:
                self.chunk.emit(text)
        if self._stop:
            return
        self.ended.emit(reap(self._pid, 1.0))

    def stop(self):
        self._stop = True


def reap(pid, timeout):
    """waitpid without hanging: poll for `timeout` s. The exit code, -1 for
    a signal or a child already reaped elsewhere, None while it still runs."""
    end = time.monotonic() + timeout
    while True:
        try:
            got, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return -1
        if got == pid:
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            return -1
        if time.monotonic() >= end:
            return None
        time.sleep(0.02)


class TerminalWidget(QtWidgets.QWidget):
    """A shell session rendered into the dock. `ended` carries the exit code
    when the shell exits by itself (not on close_session)."""

    ended = QtCore.Signal(int)

    def __init__(self, cwd=None, command=None, parent=None):
        super().__init__(parent)
        self._cwd = cwd or os.path.expanduser("~")
        self._command = command
        self.shell_name = shell_command(os.environ, command,
                                        fallback_dir="")[2]
        self._fd = None
        self._pid = None
        self._reader = None
        self._build()

    # ------------------------------------------------------------ interface
    def _build(self):
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.out = QtWidgets.QPlainTextEdit()
        self.out.setObjectName("TermOut")
        self.out.setReadOnly(True)
        self.out.setMaximumBlockCount(5000)
        f = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)
        f.setPointSize(10)
        self.out.setFont(f)
        lay.addWidget(self.out, 1)

        row = QtWidgets.QWidget()
        row.setObjectName("TermRow")
        rl = QtWidgets.QHBoxLayout(row)
        rl.setContentsMargins(8, 6, 8, 8)
        rl.setSpacing(6)
        self.inp = QtWidgets.QLineEdit()
        self.inp.setObjectName("TermInput")
        self.inp.setPlaceholderText("Run a command…")
        self.inp.setFont(f)
        self.inp.returnPressed.connect(self._send_line)
        rl.addWidget(self.inp, 1)
        self.btn_int = QtWidgets.QPushButton("Ctrl-C")
        self.btn_int.setObjectName("TermBtn")
        self.btn_int.setToolTip("Interrupt the running command")
        self.btn_int.clicked.connect(self.interrupt)
        rl.addWidget(self.btn_int)
        lay.addWidget(row)

        self.setStyleSheet(style.qss(style.TERMINAL_QSS))

    # -------------------------------------------------------------- session
    def start(self):
        """Fork a shell on a pty. Returns True when it is running."""
        if self._pid is not None:
            return True
        # Built before the fork: the child only execs (see clean_env).
        argv, env, self.shell_name = shell_command(clean_env(), self._command)
        try:
            pid, fd = pty.fork()
        except Exception as exc:
            self._append("could not open a pty: %s\n" % exc)
            return False
        if pid == 0:
            try:
                os.chdir(self._cwd)
            except Exception:
                pass
            try:
                os.execvpe(argv[0], argv, env)
            except Exception:
                os._exit(127)
        self._pid, self._fd = pid, fd
        self._reader = PtyReader(fd, pid)
        self._reader.chunk.connect(self._on_chunk)
        self._reader.ended.connect(self._on_end)
        self._reader.start()
        return True

    def _send_line(self):
        text = self.inp.text()
        self.inp.clear()
        self.write(text + "\n")

    def write(self, data):
        if self._fd is None:
            return False
        try:
            os.write(self._fd, data.encode("utf-8"))
            return True
        except OSError:
            return False

    def interrupt(self):
        """Ctrl-C, typed: the pty's line discipline turns ^C into SIGINT for
        the terminal's FOREGROUND job - the command running, not the shell.
        Signalling the shell's own group (the old way) missed any job the
        shell had put in its own group."""
        return self.write("\x03")

    def running(self):
        return self._pid is not None

    def close_session(self, timeout=1.5):
        """End the session for good: stop and JOIN the reader, close the
        master fd, SIGHUP the shell's group, reap it (SIGKILL if it will not
        go). Safe to call twice. Returns True when nothing is left behind."""
        reader, self._reader = self._reader, None
        if reader is not None:
            try:
                reader.ended.disconnect(self._on_end)
            except (RuntimeError, TypeError):
                pass
            reader.stop()
            reader.wait(2000)        # select() wakes every 0.2 s
        fd, pid = self._fd, self._pid
        self._fd = self._pid = None
        if fd is not None:
            try:
                os.close(fd)         # the kernel HUPs the session too
            except OSError:
                pass
        clean = reader is None or not reader.isRunning()
        if pid is not None:
            for sig in (signal.SIGHUP, signal.SIGKILL):
                try:
                    os.killpg(pid, sig)   # pty.fork: the shell leads its group
                except (ProcessLookupError, PermissionError):
                    pass
                if reap(pid, timeout) is not None:
                    break
            else:
                clean = False
        return clean

    # ---------------------------------------------------------------- output
    def _on_chunk(self, text):
        self._append(strip_ansi(text))

    def _on_end(self, code):
        self._append("\n[session ended, exit %s]\n" % code)
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._pid = self._fd = self._reader = None
        self.ended.emit(-1 if code is None else int(code))

    def _append(self, text):
        """Append output, treating CR the way a terminal does.

        MEASURED 2026-09-24: the naive "split on CR and clear the block"
        version ate every line under zsh, which emits a bare CR before each
        prompt and after each echoed command. Clearing on those CRs deleted
        the text just inserted, so the widget showed a prompt and nothing
        else while the pty underneath was working perfectly.

        Correct rule: CRLF is a plain line break. Only a CR that is NOT part
        of a CRLF returns the cursor to the start of the line and overwrites
        it — which is what makes a progress bar redraw in place.
        """
        if not text:
            return
        cur = self.out.textCursor()
        cur.movePosition(QtGui.QTextCursor.End)
        text = text.replace("\r\n", "\n")
        for i, part in enumerate(text.split("\r")):
            if i:
                cur.movePosition(QtGui.QTextCursor.StartOfBlock,
                                 QtGui.QTextCursor.KeepAnchor)
                cur.removeSelectedText()
            if part:
                cur.insertText(part)
        self.out.setTextCursor(cur)
        self.out.ensureCursorVisible()
