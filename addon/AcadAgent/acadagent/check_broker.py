"""check_broker — ./check for agents that run inside their own sandbox (R870).

WHY THIS EXISTS
    The agent's ./check builds model.py headless under Atelier's own
    isolation (sandbox.wrapper_script: Seatbelt on macOS, bwrap on Linux).
    Claude Code runs ./check directly: its shell is not sandboxed, and the
    allowlist lets it run nothing else. Codex and the Cursor CLI run EVERY
    command of the agent inside their own sandbox instead, and that breaks
    ./check. MEASURED 2026-11-07, codex-cli 0.162.1 on macOS, workspace-write:
      - the nested `sandbox-exec` fails: "sandbox_apply: Operation not
        permitted" (exit 71) - Seatbelt does not nest;
      - FreeCAD without the inner Seatbelt aborts at start: "Incompatible
        processor. This Qt build requires the following features: neon" -
        Codex's profile denies the sysctl reads Qt's CPU check needs.
    Letting ./check out of the agent's sandbox (a Codex execpolicy "allow"
    rule does that, measured) is no fix: ./check lives in the folder the
    agent may write, so the agent could rewrite it and run anything
    unsandboxed.

THE BROKER
    For those engines ./check is a small client (client_script): it drops
    a request file in <ws>/.atech-check/ and waits. Atelier, outside the
    agent's sandbox, runs the REAL check - the script text it generated
    and keeps in memory (register), never a file the agent could have
    changed - and writes the output back. The agent stays entirely inside
    its own sandbox; model.py is built under Atelier's isolation exactly as
    for Claude Code.

    Files are written through a descriptor of .atech-check opened with
    O_NOFOLLOW|O_DIRECTORY, as temp files renamed into place: a symlink the
    agent plants there is replaced, never followed, so the broker cannot be
    made to write outside the chat folder.
"""
import os
import re
import stat
import subprocess
import tempfile
import threading
import time

DIR = ".atech-check"
#: The broker's presence marker: the client fails at once without it, and
#: gives up when it disappears (the turn ended).
ALIVE = "broker"
_REQ = re.compile(r"^req-([0-9]{1,12}-[0-9]{1,10})$")

_SCRIPTS = {}
_LOCK = threading.Lock()


def _key(ws):
    return os.path.realpath(ws)


def register(ws, text):
    """Keep the real ./check text of workspace `ws` (sandbox.wrapper_script)
    for the broker. In memory only: a file in the workspace is the agent's
    to change."""
    with _LOCK:
        _SCRIPTS[_key(ws)] = text


def registered(ws):
    with _LOCK:
        return _SCRIPTS.get(_key(ws))


def client_script(ws, wait_s):
    """The ./check an agent in its own sandbox runs: ask Atelier for a
    check and print its answer. `wait_s`: how long to wait for it."""
    import shlex
    d = os.path.join(os.path.realpath(ws), DIR)
    return """#!/bin/sh
# Atech Atelier self-check - written by Atelier, rewritten every turn.
# Asks Atelier to build model.py headless in its sandbox; prints what it
# measured and writes check.png. The last line is CHECK PASS or
# CHECK FAIL: <reasons>.
d=%(d)s
if [ ! -f "$d/%(alive)s" ]; then
  echo "CHECK FAIL: Atech Atelier is not taking checks for this chat right now (no reply is running)."
  exit 1
fi
id="$(date +%%s)-$$"
if ! { : > "$d/req-$id.tmp" && mv -f "$d/req-$id.tmp" "$d/req-$id"; }; then
  echo "CHECK FAIL: could not ask Atech Atelier for a check (cannot write $d)."
  exit 1
fi
n=0
while [ ! -f "$d/done-$id" ]; do
  if [ ! -f "$d/%(alive)s" ]; then
    echo "CHECK FAIL: Atech Atelier stopped the check (the reply ended)."
    exit 1
  fi
  n=$((n + 1))
  if [ "$n" -gt %(wait)d ]; then
    echo "CHECK FAIL: no answer from Atech Atelier after %(wait)d s."
    exit 1
  fi
  sleep 1
done
cat "$d/out-$id" 2>/dev/null
rc=$(cat "$d/done-$id" 2>/dev/null)
rm -f "$d/out-$id" "$d/done-$id"
case $rc in ''|*[!0-9]*) rc=1 ;; esac
exit "$rc"
""" % {"d": shlex.quote(d), "alive": ALIVE, "wait": int(wait_s)}


def client_wait(timeout):
    """Seconds a client waits: the real script's lock wait and hard stop
    (sandbox.wrapper_script) plus a margin."""
    t = int(float(timeout))
    return max(120, t + 60) + (t + 30) + 60


def _open_dir(ws):
    """A descriptor of <ws>/.atech-check, created 0700 when missing.
    Raises OSError when it is not a real directory inside `ws`."""
    ws = os.path.realpath(ws)
    wfd = os.open(ws, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            os.mkdir(DIR, 0o700, dir_fd=wfd)
        except FileExistsError:
            pass
        st = os.stat(DIR, dir_fd=wfd, follow_symlinks=False)
        if not stat.S_ISDIR(st.st_mode):
            raise OSError("%s is not a folder" % DIR)
        return os.open(DIR, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                       dir_fd=wfd)
    finally:
        os.close(wfd)


def _put(dfd, name, data):
    """Write `data` (bytes) as `name` in the directory `dfd`: a fresh file
    renamed into place, so a planted link is replaced, never followed."""
    tmp = ".%s.%d.%d.tmp" % (name, os.getpid(), threading.get_ident())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o644, dir_fd=dfd)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except BaseException:
        try:
            os.unlink(tmp, dir_fd=dfd)
        except OSError:
            pass
        raise
    os.replace(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)


def _unlink(dfd, name):
    try:
        os.unlink(name, dir_fd=dfd)
    except OSError:
        pass


def _log(msg):
    line = "[agent] check broker: %s\n" % msg
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog(line)
    except Exception:                                  # noqa: BLE001
        import sys
        sys.stderr.write(line)


class Broker(object):
    """Answers the ./check requests of one workspace while a turn runs.

    start() creates the alive marker and a polling thread; stop() removes
    the marker, kills a check in flight and joins the thread. `env`: the
    environment the real check runs in (the turn's, with ATECH_TURN_T0)."""

    POLL_S = 0.25

    def __init__(self, ws, env=None):
        self.ws = os.path.realpath(ws)
        self.env = dict(env) if env is not None else None
        self._stop = threading.Event()
        self._thread = None
        self._dfd = None
        self._proc = None
        self.answered = 0

    def start(self):
        """True when the broker runs; False (logged) when the workspace has
        no usable .atech-check folder."""
        try:
            self._dfd = _open_dir(self.ws)
            for name in os.listdir(self._dfd):
                # Leftovers of an earlier turn: never answered now.
                if name != ALIVE:
                    _unlink(self._dfd, name)
            _put(self._dfd, ALIVE, ("%d\n" % os.getpid()).encode("ascii"))
        except OSError as exc:
            _log("not started in %s: %r" % (self.ws, exc))
            self._close()
            return False
        self._thread = threading.Thread(target=self._loop,
                                        name="atech-check-broker",
                                        daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout=5.0):
        self._stop.set()
        self._kill()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout)
        if self._dfd is not None:
            _unlink(self._dfd, ALIVE)
        self._close()

    def _close(self):
        if self._dfd is not None:
            try:
                os.close(self._dfd)
            except OSError:
                pass
            self._dfd = None

    def _kill(self):
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        for sig in (15, 9):
            try:
                os.killpg(proc.pid, sig)
            except OSError:
                pass
            try:
                proc.wait(2.0)
                return
            except subprocess.TimeoutExpired:
                continue

    def _loop(self):
        while not self._stop.is_set():
            try:
                names = sorted(os.listdir(self._dfd))
            except OSError as exc:
                _log("cannot list %s: %r" % (DIR, exc))
                return
            for name in names:
                if self._stop.is_set():
                    return
                m = _REQ.match(name)
                if m:
                    _unlink(self._dfd, name)
                    self._answer(m.group(1))
            self._stop.wait(self.POLL_S)

    def _answer(self, rid):
        text = registered(self.ws)
        if text is None:
            out = (b"CHECK FAIL: Atech Atelier has no check for this chat "
                   b"folder yet (it is written when a reply starts).\n")
            rc = 1
        else:
            out, rc = self._run(text)
        if self._stop.is_set():
            return                  # the client gives up on the marker
        try:
            _put(self._dfd, "out-" + rid, out)
            _put(self._dfd, "done-" + rid, ("%d\n" % rc).encode("ascii"))
            self.answered += 1
        except OSError as exc:
            _log("could not answer %s: %r" % (rid, exc))

    def _run(self, text):
        """Run the real ./check text; (output bytes, exit status)."""
        with tempfile.TemporaryFile() as fh:
            try:
                self._proc = subprocess.Popen(
                    ["/bin/sh", "-c", text, "check"], cwd=self.ws,
                    env=self.env, stdin=subprocess.DEVNULL, stdout=fh,
                    stderr=subprocess.STDOUT, start_new_session=True)
            except OSError as exc:
                return (("CHECK FAIL: Atech Atelier could not run the "
                         "check: %s\n" % exc).encode("utf-8"), 1)
            while self._proc.poll() is None:
                if self._stop.wait(0.2):
                    self._kill()
                    break
            rc = self._proc.returncode
            self._proc = None
            fh.seek(0)
            out = fh.read()
        if rc is None or rc < 0:
            rc = 1
        return out, rc
