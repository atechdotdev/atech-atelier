"""backend — the agent backend supervisor.

Owns one question: *is there an agent process listening on 127.0.0.1:4096, and
if not, should we start one?* Nothing here talks the opencode protocol; that is
client.py's job. This module only decides ADOPT / SPAWN / OFFLINE and reports
the answer to the panel.

Three rules, each learned the hard way and each load-bearing:

1.  PROBE BY SOCKET, NEVER BY `ss | grep 4096`.
    In `ss` output 4096 is also a common value in the Send-Q column, so a grep
    matches unrelated rows and reports a free port as busy. `connect_ex` asks
    the kernel the actual question: 0 means something accepted, 111
    (ECONNREFUSED) means nothing is listening.

2.  ADOPT AN INCUMBENT, NEVER DOUBLE-START AND NEVER KILL.
    The user may already be running `opencode serve` for their own work. A
    second bind would fail; killing theirs would be theft. If the port answers,
    we use it and we do not own it — so we must not reap it on exit either.
    `spawned_pid` is None in that case, which is how AppRun's trap knows.

2b. KNOW WHAT YOU ADOPT (R105, dogfood D6).
    "Something accepted a connection" is not "our agent backend": every test
    instance adopted an orphaned `opencode serve` (parent systemd --user)
    left by an earlier run, without a word. Before adopting, the listener is
    (a) asked the backend's own question (GET /api/health must answer JSON)
    and (b) traced to its process through /proc/net/tcp and /proc/*/fd.
    A listener this Studio's launcher started (our child, or our sibling
    under AppRun) is adopted quietly. One started by anything else is still
    usable - it may be the user's own `opencode serve` - but it is adopted
    OUT LOUD (`foreign` is set and the panel says so), and never at all when
    ATECH_AGENT_ADOPT=0, when another account owns it, or when it does not
    answer the handshake.

3.  AUTOSTART IS OFF UNTIL THE PARSER IS PROVEN.
    client.py's message parser reads the wrong API schema (see
    docs/verification/2026-09-24_opencode_api_contract.md). Against a *running*
    backend that bug turns an immediate, honest "not reachable" into a ~180 s
    silent stall that then blames a missing API key while the credentials are
    fine. Starting the backend before the parser is fixed would therefore make
    the product look MORE broken and misdirect the fix. So autostart is gated
    behind ATECH_AGENT_AUTOSTART=1 and the default flips only once the parser
    lands. `autostart_enabled()` is the single switch.
"""
import os
import socket
import subprocess
import sys
import time

HOST = "127.0.0.1"
PORT = 4096
OPENCODE_BIN = os.path.expanduser("~/.npm-global/bin/opencode")

# States the panel renders. 'working' is set by the panel itself while a
# request is in flight; this module only ever reports 'offline' or 'idle'.
OFFLINE = "offline"
IDLE = "idle"
WORKING = "working"

# Exact copy, from docs/verification/ui-review/DESIGN_FINDINGS.md.
NOTICE_TITLE = "Agent backend not reachable"
NOTICE_BODY = ("Atech Atelier talks to a local agent process on %s:%d. "
               "Nothing is listening there right now." % (HOST, PORT))
NOTICE_BODY2 = "Start it with:  opencode serve --port %d" % PORT
NOTICE_ACTIONS = ("Retry connection", "Change backend address…")


def _log(msg):
    """Write to FreeCAD's report view when we have one, stderr otherwise.

    A desktop-launched app has no terminal, so a bare print() goes nowhere.
    """
    line = "[agent] %s\n" % msg
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog(line)
    except Exception:                                        # noqa: BLE001
        sys.stderr.write(line)


def probe(host=HOST, port=PORT, timeout=1.0):
    """Return the errno from connect_ex: 0 = in use, 111 = free.

    This is the only correct way to ask. See rule 1 in the module docstring.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        return sock.connect_ex((host, port))
    finally:
        sock.close()


def is_listening(host=HOST, port=PORT, timeout=1.0):
    return probe(host, port, timeout) == 0


# ---------------------------------------------------- listener identity (R105)
_LOOPBACK4 = ("0100007F", "00000000")                 # 127.0.0.1, 0.0.0.0
_LOOPBACK6 = ("00000000000000000000000001000000",     # ::1
              "00000000000000000000000000000000",     # ::
              "0000000000000000FFFF00000100007F")     # ::ffff:127.0.0.1
TCP_LISTEN = "0A"


def _listen_rows(port, proc="/proc"):
    """(inode, uid) of each LISTEN socket on `port` at a loopback or
    wildcard address, read from the kernel's own tables."""
    out = []
    for name, addrs in (("tcp", _LOOPBACK4), ("tcp6", _LOOPBACK6)):
        try:
            with open(os.path.join(proc, "net", name), encoding="ascii") as fh:
                rows = fh.read().splitlines()[1:]
        except OSError:
            continue
        for row in rows:
            f = row.split()
            if len(f) < 10 or f[3] != TCP_LISTEN:
                continue
            addr, _sep, hexport = f[1].partition(":")
            try:
                if int(hexport, 16) != int(port):
                    continue
            except ValueError:
                continue
            if addr.upper() not in addrs:
                continue
            try:
                out.append((int(f[9]), int(f[7])))
            except ValueError:
                continue
    return out


def _proc_field(pid, name, proc="/proc"):
    try:
        with open(os.path.join(proc, str(pid), name), "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _ppid(pid, proc="/proc"):
    raw = _proc_field(pid, "stat", proc)
    if not raw:
        return None
    # comm may hold spaces and parentheses: the fields after the LAST ')'.
    try:
        return int(raw[raw.rindex(b")") + 2:].split()[1])
    except (ValueError, IndexError):
        return None


def _pid_of_inode(inode, proc="/proc"):
    """The pid holding socket inode `inode`, or None (another account's
    process, whose fds we cannot read, or a socket gone meanwhile)."""
    want = "socket:[%d]" % inode
    try:
        pids = [d for d in os.listdir(proc) if d.isdigit()]
    except OSError:
        return None
    for pid in pids:
        fd_dir = os.path.join(proc, pid, "fd")
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                if os.readlink(os.path.join(fd_dir, fd)) == want:
                    return int(pid)
            except OSError:
                continue
    return None


def listener(port=PORT, proc="/proc"):
    """Who listens on `port`: {'pid', 'uid', 'ppid', 'cmd', 'parent_cmd'}
    or None when no LISTEN row is found. pid is None when the socket
    belongs to a process we cannot inspect. Measured, never assumed."""
    rows = _listen_rows(port, proc)
    if not rows:
        return None
    inode, uid = rows[0]
    pid = _pid_of_inode(inode, proc)
    info = {"pid": pid, "uid": uid, "ppid": None, "cmd": "",
            "parent_cmd": ""}
    if pid is not None:
        info["ppid"] = _ppid(pid, proc)
        raw = _proc_field(pid, "cmdline", proc) or b""
        info["cmd"] = raw.replace(b"\0", b" ").decode("utf-8", "replace").strip()
        if info["ppid"]:
            raw = _proc_field(info["ppid"], "cmdline", proc) or b""
            info["parent_cmd"] = raw.replace(b"\0", b" ").decode(
                "utf-8", "replace").strip()
    return info


OWN = "own"             # started by this Studio (child, or AppRun's sibling)
USER = "user"           # this account, not started by this Studio
OTHER_USER = "other-user"
UNKNOWN = "unknown"


def classify(info, me=None, parent=None, uid=None, proc="/proc"):
    """OWN / USER / OTHER_USER / UNKNOWN for a listener() record."""
    if not info:
        return UNKNOWN
    me = os.getpid() if me is None else me
    parent = os.getppid() if parent is None else parent
    uid = os.getuid() if uid is None else uid
    if info.get("uid") is not None and info["uid"] != uid:
        return OTHER_USER
    pid = info.get("pid")
    if pid is None:
        return UNKNOWN
    # Our descendant: walk its parents up to init.
    seen, p = set(), pid
    while p and p > 1 and p not in seen:
        if p == me:
            return OWN
        seen.add(p)
        p = _ppid(p, proc)
    # AppRun starts the backend and then FreeCAD from the same bash: the
    # backend is our sibling. An orphan (re-parented to init or systemd
    # --user) is not.
    if parent and parent > 1 and info.get("ppid") == parent:
        return OWN
    return USER


def handshake(host=HOST, port=PORT, timeout=2.0):
    """True when the listener answers the agent backend's health call with
    JSON. A port held by anything else (a dev server, another app) does
    not."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen("http://%s:%d/api/health" % (host, port),
                                    timeout=timeout) as resp:
            if not 200 <= resp.status < 300:
                return False
            raw = resp.read(65536).decode("utf-8", "replace")
        json.loads(raw) if raw.strip() else {}
        return True
    except Exception:                                        # noqa: BLE001
        return False


def adopt_allowed():
    """ATECH_AGENT_ADOPT=0 refuses any backend this Studio did not start."""
    env = os.environ.get("ATECH_AGENT_ADOPT")
    return env is None or env.strip().lower() not in ("0", "false", "no")


def describe(info):
    """One line for the user: pid, command, and who started it."""
    if not info or info.get("pid") is None:
        return "a process Atech Atelier cannot inspect"
    parent = info.get("parent_cmd") or ""
    orphan = info.get("ppid") in (None, 0, 1) or "systemd" in parent
    return "pid %d (%s)%s" % (
        info["pid"], (info.get("cmd") or "?")[:80],
        ", left running by an earlier session" if orphan else "")


def log_path():
    """Where opencode's stdout/stderr lands.

    Under the user's data dir, because the app is launched from a desktop icon
    and has no terminal to print to. A failure that leaves no trace is
    indistinguishable from a failure that never happened.
    """
    try:
        import FreeCAD
        base = FreeCAD.getUserAppDataDir()
    except Exception:                                        # noqa: BLE001
        base = os.path.join(os.path.expanduser("~"), ".local", "share",
                            "Atech Atelier", "v1-1")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "agent-backend.log")


def autostart_enabled():
    """THE SEQUENCING GATE. See rule 3 in the module docstring.

    Default False. Flip DEFAULT_AUTOSTART to True only after client.py's
    parser fix is deployed and proven against a live backend — not before.
    """
    DEFAULT_AUTOSTART = False
    # R24: OpenCode is a developer engine; without ATECH_DEV_ENGINES=1 it
    # is not offered, so nothing may start its server either.
    if os.environ.get("ATECH_DEV_ENGINES", "").strip() != "1":
        return False
    env = os.environ.get("ATECH_AGENT_AUTOSTART")
    if env is not None:
        return env.strip() not in ("", "0", "false", "no")
    return DEFAULT_AUTOSTART


class Supervisor(object):
    """Decides adopt / spawn / offline, and remembers which it was.

    `spawned_pid` is the whole contract with the lifecycle: it is set only
    when WE started the process, so only then may anyone reap it.
    """

    def __init__(self, host=HOST, port=PORT, binary=OPENCODE_BIN):
        self.host = host
        self.port = port
        self.binary = binary
        self.spawned_pid = None
        self.adopted = False
        self.foreign = None     # listener() of an adopted backend not ours
        self.refused = None     # (reason, listener()) of one not adopted
        self._proc = None

    # ---------------------------------------------------------------- state
    def state(self):
        """'idle' if something answers on the port, else 'offline'.

        Measured, never asserted: this asks the socket every time rather than
        trusting a flag we set earlier. A backend that died since we spawned
        it must read as offline, not as whatever we last hoped.
        """
        return IDLE if is_listening(self.host, self.port) else OFFLINE

    # -------------------------------------------------------------- startup
    def ensure(self, wait=20.0):
        """Adopt an incumbent, or spawn one if autostart is enabled.

        Returns (state, note). Never raises: a supervisor that crashes the
        workbench is worse than one that reports offline.
        """
        code = probe(self.host, self.port)
        if code == 0:
            return self._adopt()

        if not autostart_enabled():
            _log("nothing on %s:%d and autostart is off "
                 "(set ATECH_AGENT_AUTOSTART=1 to enable)"
                 % (self.host, self.port))
            return OFFLINE, "autostart-disabled"

        if not os.path.exists(self.binary):
            _log("autostart wanted but %s does not exist" % self.binary)
            return OFFLINE, "binary-missing"

        return self._spawn(wait)

    def _adopt(self):
        """R105: verify the listener before adopting it (rule 2b)."""
        try:
            info = listener(self.port)
        except Exception as exc:                             # noqa: BLE001
            _log("listener inspection failed: %r" % (exc,))
            info = None
        kind = classify(info)
        where = "%s:%d" % (self.host, self.port)
        if kind == OTHER_USER:
            self.refused = ("other-user", info)
            _log("%s is held by another account (uid %s); not adopted"
                 % (where, info.get("uid")))
            return OFFLINE, "foreign-user"
        if not handshake(self.host, self.port):
            self.refused = ("not-a-backend", info)
            _log("%s is held by %s, which does not answer the agent "
                 "backend's health call; not adopted" % (where, describe(info)))
            return OFFLINE, "port-busy"
        if kind == OWN:
            self.adopted = True
            _log("adopted this Atelier's own backend on %s (pid %s)"
                 % (where, (info or {}).get("pid")))
            return IDLE, "adopted"
        if not adopt_allowed():
            self.refused = ("not-ours", info)
            _log("%s is served by %s, not started by this Atelier; "
                 "ATECH_AGENT_ADOPT=0, so not adopted" % (where, describe(info)))
            return OFFLINE, "foreign-refused"
        self.adopted = True
        self.foreign = info or {}
        _log("adopted a backend this Atelier did not start on %s: %s. It is "
             "never stopped on exit." % (where, describe(info)))
        return IDLE, "adopted-foreign"

    def _spawn(self, wait):
        path = log_path()
        try:
            handle = open(path, "ab", 0)
        except OSError as exc:
            _log("cannot open backend log %s: %s" % (path, exc))
            return OFFLINE, "log-unwritable"

        handle.write(("\n=== %s  spawn %s serve --port %d --hostname %s ===\n"
                      % (time.strftime("%Y-%m-%d %H:%M:%S"), self.binary,
                         self.port, self.host)).encode("utf-8"))
        try:
            self._proc = subprocess.Popen(
                [self.binary, "serve", "--port", str(self.port),
                 "--hostname", self.host],
                stdout=handle, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True)
        except OSError as exc:
            handle.close()
            _log("spawn failed: %s" % exc)
            return OFFLINE, "spawn-failed"
        finally:
            try:
                handle.close()
            except Exception:                                # noqa: BLE001
                pass

        self.spawned_pid = self._proc.pid
        _log("spawned backend pid %d, log %s" % (self.spawned_pid, path))

        # Wait for the port, not for a fixed sleep: the port answering is the
        # only evidence the process is actually serving.
        deadline = time.time() + wait
        while time.time() < deadline:
            if self._proc.poll() is not None:
                _log("backend pid %d exited early with %s; see %s"
                     % (self.spawned_pid, self._proc.returncode, path))
                self.spawned_pid = None
                return OFFLINE, "exited-early"
            if is_listening(self.host, self.port, timeout=0.5):
                return IDLE, "spawned"
            time.sleep(0.25)

        _log("backend pid %d did not answer within %.0fs; see %s"
             % (self.spawned_pid, wait, path))
        return OFFLINE, "spawn-timeout"

    # ------------------------------------------------------------- shutdown
    def shutdown(self, grace=5.0):
        """Terminate ONLY a process we spawned. Adopted ones are never touched.

        Returns True if we reaped something, False if there was nothing of
        ours to reap. AppRun's trap covers the normal desktop path; this is
        for the in-process case.
        """
        if self.adopted or self._proc is None or self.spawned_pid is None:
            return False
        if self._proc.poll() is not None:
            self.spawned_pid = None
            return False
        pid = self.spawned_pid
        try:
            self._proc.terminate()
            deadline = time.time() + grace
            while time.time() < deadline:
                if self._proc.poll() is not None:
                    break
                time.sleep(0.1)
            else:
                self._proc.kill()
                self._proc.wait(timeout=grace)
        except Exception as exc:                             # noqa: BLE001
            _log("shutdown of pid %s: %s" % (pid, exc))
        self.spawned_pid = None
        _log("reaped backend pid %d" % pid)
        return True


_SUPERVISOR = None


def supervisor():
    global _SUPERVISOR
    if _SUPERVISOR is None:
        _SUPERVISOR = Supervisor()
    return _SUPERVISOR


# ------------------------------------------------------------------- panel
# These call INTO the panel's API. panel.py is owned by another agent, and the
# two methods may not exist yet, so every call is guarded: a missing method
# must degrade to a log line, never to a traceback that takes the dock down.

def _call(panel, name, *args):
    fn = getattr(panel, name, None)
    if not callable(fn):
        _log("panel has no %s(); skipping" % name)
        return False
    try:
        fn(*args)
        return True
    except Exception as exc:                                 # noqa: BLE001
        _log("panel.%s failed: %s" % (name, exc))
        return False


def apply_to_panel(panel, state=None):
    """Push the measured state into the dock.

    On OFFLINE also raise the designed notice with DESIGN_FINDINGS' exact copy
    — never a urllib repr, which is implementation trivia the user cannot act
    on.
    """
    sup = supervisor()
    if state is None:
        state = sup.state()
    _call(panel, "set_backend_state", state)
    if state == OFFLINE and sup.refused:
        why, info = sup.refused
        body = {
            "other-user": "Another account on this computer is using "
                          "%s:%d. Atech Atelier will not send your work to "
                          "it." % (sup.host, sup.port),
            "not-a-backend": "%s:%d is taken by %s, which is not an agent "
                             "backend." % (sup.host, sup.port, describe(info)),
            "not-ours": "%s:%d is served by %s, which Atech Atelier did not "
                        "start (ATECH_AGENT_ADOPT=0)." % (
                            sup.host, sup.port, describe(info)),
        }.get(why, NOTICE_BODY)
        _call(panel, "show_notice", NOTICE_TITLE,
              "%s\n\nStop it, or change the backend address in Settings."
              % body, list(NOTICE_ACTIONS))
    elif state == OFFLINE:
        _call(panel, "show_notice", NOTICE_TITLE,
              "%s\n\n%s" % (NOTICE_BODY, NOTICE_BODY2),
              list(NOTICE_ACTIONS))
    elif sup.foreign is not None:
        _call(panel, "show_notice", FOREIGN_TITLE,
              foreign_body("%s:%d" % (sup.host, sup.port), sup.foreign))
    return state


FOREIGN_TITLE = "Using an agent backend Atech Atelier did not start"


def foreign_body(where, info, kind=USER):
    """The notice body for a backend adopted although this Studio did not
    start it. `where` is 'host:port'."""
    if kind == OTHER_USER:
        return ("%s is served by another account on this computer. Anything "
                "you send goes to that account's process. Change the "
                "backend address in Settings." % where)
    return ("%s is served by %s. Atech Atelier is using it and will not stop "
            "it when you quit. If that is not yours, stop it and retry."
            % (where, describe(info)))


def start_and_report(panel=None):
    """Called at panel mount. Adopt-or-start, then render the outcome.

    Returns (state, note) so a caller can log what actually happened rather
    than assuming it worked.
    """
    state, note = supervisor().ensure()
    if panel is not None:
        apply_to_panel(panel, state)
    return state, note


if __name__ == "__main__":
    # Standalone probe: `python3 backend.py` prints the measured truth. Used
    # by the verification runs, so the numbers in the record come from the
    # same code the app runs.
    code = probe()
    print("probe %s:%d -> connect_ex=%d (%s)"
          % (HOST, PORT, code, "IN USE" if code == 0 else
             "FREE" if code == 111 else "other"))
    print("autostart_enabled=%s  (env ATECH_AGENT_AUTOSTART=%r)"
          % (autostart_enabled(), os.environ.get("ATECH_AGENT_AUTOSTART")))
    print("opencode binary exists=%s  (%s)"
          % (os.path.exists(OPENCODE_BIN), OPENCODE_BIN))
    print("log_path=%s" % log_path())
