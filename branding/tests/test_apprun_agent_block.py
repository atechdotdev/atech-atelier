#!/usr/bin/env python3
"""R134: AppRun's agent block never announces an adoption.

Whether a listener already on the agent port is adopted is the addon's call,
made after its ownership check (R105, acadagent/backend.py _adopt). AppRun
runs before that check, so the most it may say is that the port is in use.
Runs branding/apprun_agent_block.sh under real bash against a real listener
on a free port (never 4096: the owner's own backend may hold it) and checks:

  - a busy port: no "adopt" wording, no backend spawned (even with
    ATECH_AGENT_AUTOSTART=1), ATECH_AGENT_PID empty, and the listener is
    still alive after the script's EXIT trap ran;
  - a free port with autostart: the stub backend is spawned and reaped by
    pid on exit (the lifecycle the block exists for is unchanged);
  - sabotage: the round-4 line put back into a copy makes the check fail.

    python3 branding/tests/test_apprun_agent_block.py -> APPRUN_AGENT_BLOCK_TESTS_OK
"""
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK = os.path.join(os.path.dirname(HERE), "apprun_agent_block.sh")
ROUND4_LINE = ('    echo "[atech] agent backend already listening on '
               '${ATECH_AGENT_HOST}:${ATECH_AGENT_PORT} — adopting it" >&2\n')

LISTENER = r'''
import socket, sys, time
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(sys.argv[1]))); s.listen(8)
if len(sys.argv) > 2:
    open(sys.argv[2], "w").write("spawned\n")
print("LISTENING", flush=True)
while True:
    c, _ = s.accept(); c.close()
'''


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def port_open(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        return True
    except OSError:
        return False


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # A zombie still answers kill(0); read its state.
    try:
        with open("/proc/%d/stat" % pid) as fh:
            return fh.read().split(")")[-1].split()[0] != "Z"
    except OSError:
        return False


def adoption_claims(stderr):
    """Lines in which AppRun claims an adoption it has not verified."""
    return [ln for ln in stderr.splitlines() if re.search(r"adopt", ln, re.I)]


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="apprun_block_")
        self.port = free_port()
        self.procs = []

    def tearDown(self):
        for p in self.procs:                # only processes this test started
            if p.poll() is None:
                p.kill()
                p.wait(5)
            p.stdout.close()

    def listen(self):
        p = subprocess.Popen([sys.executable, "-c", LISTENER, str(self.port)],
                             stdout=subprocess.PIPE)
        self.procs.append(p)
        self.assertEqual(p.stdout.readline().strip(), b"LISTENING")
        return p

    def stub(self, marker):
        """A stand-in `opencode`: listens on --port and leaves a marker."""
        path = os.path.join(self.tmp, "opencode")
        with open(path, "w") as fh:
            fh.write("#!/bin/bash\n"
                     "port=\"\"\n"
                     "while [ $# -gt 0 ]; do [ \"$1\" = --port ] && port=$2; "
                     "shift; done\n"
                     "unset PYTHONHOME\n"
                     "exec %s -c '%s' \"$port\" %s\n"
                     % (sys.executable, LISTENER.replace("'", "'\\''"),
                        marker))
        os.chmod(path, 0o755)
        return path

    def run_block(self, block=None, **env):
        block = block or BLOCK
        script = os.path.join(self.tmp, "run.sh")
        with open(script, "w") as fh:
            fh.write("#!/bin/bash\nsource %s\n"
                     "echo \"PID=[${ATECH_AGENT_PID}]\"\n" % block)
        e = dict(os.environ, ATECH_AGENT_PORT=str(self.port),
                 ATECH_AGENT_HOST="127.0.0.1",
                 XDG_DATA_HOME=os.path.join(self.tmp, "data"))
        e.pop("ATECH_AGENT_AUTOSTART", None)
        e.update(env)
        r = subprocess.run(["bash", script], env=e, capture_output=True,
                           text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        pid = re.search(r"PID=\[(\d*)\]", r.stdout).group(1)
        return r.stderr, pid


class TestBusyPort(Case):
    def test_says_in_use_never_adopting(self):
        lst = self.listen()
        err, pid = self.run_block()
        print("\nR134 AppRun stderr: %s" % err.strip())
        self.assertEqual(adoption_claims(err), [])
        self.assertIn("already in use", err)
        self.assertEqual(pid, "", "AppRun took ownership of a listener")
        self.assertIsNone(lst.poll(), "the EXIT trap killed the listener")
        self.assertTrue(port_open(self.port))

    def test_autostart_spawns_nothing_on_a_busy_port(self):
        lst = self.listen()
        marker = os.path.join(self.tmp, "spawned")
        err, pid = self.run_block(ATECH_AGENT_AUTOSTART="1",
                                  ATECH_AGENT_BIN=self.stub(marker))
        self.assertEqual(adoption_claims(err), [])
        self.assertEqual(pid, "")
        self.assertFalse(os.path.exists(marker), "a second backend started")
        self.assertIsNone(lst.poll())

    def test_sabotage_round4_line_is_caught(self):
        with open(BLOCK, encoding="utf-8") as fh:
            src = fh.read()
        m = re.search(r'^if atech_port_open; then\n(?:    #.*\n)*'
                      r'    echo .*\n', src, re.M)
        self.assertIsNotNone(m, "busy-port branch not found")
        head = re.match(r'^if atech_port_open; then\n(?:    #.*\n)*',
                        m.group(0)).group(0)
        bad = src.replace(m.group(0), head + ROUND4_LINE, 1)
        path = os.path.join(self.tmp, "block_round4.sh")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(bad)
        self.listen()
        err, _pid = self.run_block(block=path)
        self.assertNotEqual(adoption_claims(err), [],
                            "the check cannot see the round-4 line")


class TestFreePort(Case):
    def test_autostart_spawns_and_reaps_its_own(self):
        self.assertFalse(port_open(self.port), "precondition")
        marker = os.path.join(self.tmp, "spawned")
        err, pid = self.run_block(ATECH_AGENT_AUTOSTART="1",
                                  ATECH_AGENT_BIN=self.stub(marker))
        self.assertTrue(pid, err)
        self.assertTrue(os.path.exists(marker), err)
        for _ in range(20):
            if not pid_alive(int(pid)):
                break
            time.sleep(0.1)
        alive = pid_alive(int(pid))
        if alive:                           # never leave our stub behind
            os.kill(int(pid), signal.SIGKILL)
        self.assertFalse(alive, "the spawned backend was not reaped")
        self.assertEqual(adoption_claims(err), [])

    def test_autostart_off_says_nothing(self):
        err, pid = self.run_block()
        self.assertEqual(err.strip(), "")
        self.assertEqual(pid, "")


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    if r.wasSuccessful():
        print("APPRUN_AGENT_BLOCK_TESTS_OK")
    sys.exit(0 if r.wasSuccessful() else 1)
