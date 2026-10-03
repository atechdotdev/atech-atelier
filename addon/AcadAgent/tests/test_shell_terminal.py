"""The pty terminal, headless (R20): interrupt, quit-time join, child env.

    QT_QPA_PLATFORM=offscreen dist/build/squashfs-root/usr/bin/python \
        -m unittest discover -s addon/AcadAgent/tests -p 'test_shell_*.py' -v
"""
import os
import subprocess
import sys
import textwrap
import time
import unittest

import _shell_fakes as F
from PySide6 import QtWidgets

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def wait_for(pred, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        F.pump(50)
        if pred():
            return True
    return False


class TestPty(unittest.TestCase):
    def setUp(self):
        from acadagent import terminal
        self.terminal = terminal
        self.t = terminal.TerminalWidget(cwd="/tmp", command=["/bin/sh", "-i"])
        self.assertTrue(self.t.start())
        self.pid, self.fd = self.t._pid, self.t._fd
        self.reader = self.t._reader

    def tearDown(self):
        self.t.close_session()
        self.t.deleteLater()
        F.pump(20)

    def text(self):
        return self.t.out.toPlainText()

    def test_interrupt_stops_the_foreground_job(self):
        self.t.write("sleep 100\n")
        F.pump(400)
        t0 = time.monotonic()
        self.assertTrue(self.t.interrupt())
        self.t.write("echo done-$((40+2))\n")
        self.assertTrue(wait_for(lambda: "done-42" in self.text(), 10),
                        self.text()[-300:])
        self.assertLess(time.monotonic() - t0, 10)
        self.assertTrue(self.t.running(), "the shell itself must survive ^C")

    def test_close_session_joins_closes_and_reaps(self):
        self.t.write("sleep 100\n")
        F.pump(200)
        self.assertTrue(self.t.close_session())
        self.assertFalse(self.reader.isRunning(), "reader still running")
        with self.assertRaises(OSError):
            os.fstat(self.fd)                          # fd closed
        with self.assertRaises(ChildProcessError):
            os.waitpid(self.pid, os.WNOHANG)            # reaped, no zombie
        self.assertTrue(self.t.close_session(), "second call is a no-op")

    def test_reader_has_no_widget_parent(self):
        self.assertIsNone(self.reader.parent())
        self.assertIn(self.reader, self.terminal._LIVE)

    def test_child_env_is_clean(self):
        self.t.write("echo PH=[${PYTHONHOME}] Q=[${QT_QPA_PLATFORM}] T=[$TERM]\n")
        # Qt's offscreen plugin was requested through QT_QPA_PLATFORM, but
        # only an AppImage (APPDIR) strips it; PYTHONHOME always goes.
        self.assertTrue(wait_for(lambda: "PH=[]" in self.text(), 10),
                        self.text()[-300:])
        self.assertIn("T=[dumb]", self.text())


class TestCleanEnv(unittest.TestCase):
    def test_appimage_variables_stripped(self):
        from acadagent.terminal import clean_env
        env = {"APPDIR": "/tmp/.mount_Atech1", "APPIMAGE": "/opt/a.AppImage",
               "PYTHONHOME": "/tmp/.mount_Atech1/usr",
               "PREFIX": "/tmp/.mount_Atech1/usr",
               "QT_QPA_PLATFORM": "xcb",
               "SSL_CERT_FILE": "/tmp/.mount_Atech1/usr/ssl/cacert.pem",
               "HOME": "/home/u", "PATH": "/usr/bin", "LANG": "C.UTF-8"}
        out = clean_env(env)
        self.assertEqual(out, {"HOME": "/home/u", "PATH": "/usr/bin",
                               "LANG": "C.UTF-8", "TERM": "dumb"})

    def test_path_list_loses_only_the_image_entries(self):
        from acadagent.terminal import clean_env
        m = "/tmp/.mount_Atech1"
        out = clean_env({"APPDIR": m,
                         "PATH": m + "/usr/bin:/home/u/.local/bin:/usr/bin",
                         "XDG_DATA_DIRS": m + "/usr/share",
                         "DISPLAY": ":0", "URL": "http://x:80"})
        self.assertEqual(out["PATH"], "/home/u/.local/bin:/usr/bin")
        self.assertNotIn("XDG_DATA_DIRS", out)
        self.assertEqual(out["DISPLAY"], ":0")
        self.assertEqual(out["URL"], "http://x:80")

    def test_outside_appimage_user_values_kept(self):
        from acadagent.terminal import clean_env
        out = clean_env({"QT_QPA_PLATFORM": "wayland", "PYTHONPATH": "/x",
                         "SSL_CERT_FILE": "/etc/ssl/c.pem"})
        self.assertEqual(out, {"QT_QPA_PLATFORM": "wayland",
                               "SSL_CERT_FILE": "/etc/ssl/c.pem",
                               "TERM": "dumb"})


class TestDockQuit(unittest.TestCase):
    def test_shutdown_joins_session_and_status_probe(self):
        mw = QtWidgets.QMainWindow()
        F.install_fakes(mw)
        from acadagent import engine, terminal_dock

        orig = engine.status_line

        def slow():
            time.sleep(0.3)                  # a `claude --version` stand-in
            return "Claude Code — ready"
        engine.status_line = slow
        try:
            t0 = time.monotonic()
            dock = terminal_dock.ensure_terminal()
            self.assertLess(time.monotonic() - t0, 0.25,
                            "status probe ran on the GUI thread")
            body = dock.widget()
            sh = body.term.shell_name
            # R106: the header names the shell first, the engine as such
            self.assertEqual(body.status.text(),
                             terminal_dock.header_status(sh))
            reader = body.term._reader
            self.assertTrue(terminal_dock.shutdown(3000))
            self.assertFalse(reader.isRunning())
            self.assertFalse(terminal_dock._PROBES and any(
                p.isRunning() for p in terminal_dock._PROBES))
            F.pump(50)
            self.assertEqual(body.status.text(), terminal_dock.header_status(
                sh, "Claude Code — ready"))
            self.assertIn("chat engine: Claude Code — ready",
                          body.status.text())
        finally:
            engine.status_line = orig
            terminal_dock._DOCK = None
            mw.deleteLater()
            F.pump(20)


QUIT_SCRIPT = textwrap.dedent("""
    import sys
    sys.path.insert(0, %r)
    import _shell_fakes as F
    from PySide6 import QtCore, QtWidgets
    app = QtWidgets.QApplication([])
    mw = QtWidgets.QMainWindow(); F.install_fakes(mw)
    from acadagent import terminal_dock
    if sys.argv[1] == "nohook":
        terminal_dock._QUIT_HOOKED[0] = True   # the old code: no quit hook
    dock = terminal_dock.ensure_terminal()
    dock.widget().term.write("sleep 100\\n")
    QtCore.QTimer.singleShot(300, app.quit)
    app.exec()
    del dock
    mw.deleteLater()
    app.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
    print("EXITED", flush=True)
""") % (os.path.dirname(os.path.abspath(__file__)),)


class TestQuitAfterTerminal(unittest.TestCase):
    """Quit with a terminal open: the reader thread must be joined."""

    def run_quit(self, mode):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        return subprocess.run([sys.executable, "-c", QUIT_SCRIPT, mode],
                              env=env, capture_output=True, text=True,
                              timeout=60)

    def test_quit_hook_joins_reader(self):
        r = self.run_quit("hook")
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        self.assertNotIn("Destroyed while thread", r.stderr)

    def test_without_hook_it_aborts(self):
        # The test above can fail: without the hook the same run aborts.
        r = self.run_quit("nohook")
        self.assertIn("Destroyed while thread", r.stderr)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
