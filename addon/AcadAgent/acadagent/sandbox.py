"""sandbox - build model.py in a child freecadcmd, never on the GUI thread.

WHY
    runner.apply_code exec()s agent-written code inside Studio: on the main
    thread, with the user's files, network and FreeCAD's GUI in reach, and no
    timeout. A `while True:` or a runaway fillet freezes the app; a prompt
    injection runs as the user. (Release PRD R12.)

WHAT THIS DOES
    run(workspace) starts  <freecadcmd> agent_kit/check.py  as a child
    process that:
      - builds model.py in a FRESH document (the same names it gets in
        Studio: doc, App, FreeCAD) - check.py is the one child-side runner,
        shared with the agent's own self-check (PRD S09);
      - has a scratch HOME (a fresh temp dir), and - where the kernel allows -
        no network and no view of the user's home: `bwrap` (read-only root,
        tmpfs over $HOME, /tmp and /run, only the workspace writable), else
        `unshare -rn` (no network, scratch HOME), else neither (reported as
        isolation="none", never silently; isolation_caveat() is the sentence
        Studio tells the user once - PRD R115);
      - is killed, with its whole process group, after `timeout` seconds;
      - writes one <Name>.brep per end result plus result.json into
        <workspace>/.atech_sandbox/ (a sub-folder: build.snapshot only scans
        the top level, so these never look like agent output).
    import_result(doc, result) then adds those BREPs to a document - the only
    step that touches FreeCAD's document, and the only one for the main thread.

    Job(...).start() / .poll() is the non-blocking form for the GUI (drive it
    from a QTimer); run() is start + wait.

    context=<json path> seeds the child's fresh document with the user's
    objects (exported as BREPs by build.py), so a script that builds around
    them sees what it would see in Studio.

    wrapper_script(ws) is the text of the agent's ./check: the same child,
    under the same isolation, printing check.py's report (PRD S09) - and,
    given context=, the same user objects Studio's build sees (R128).

    font_path() is the one TrueType font a model.py can read inside the
    sandbox (R140): the host's DejaVuSans (a path that survives a relaunch),
    else the FreeCAD tree's own copy; its folder is bound read-only and the
    prompt names it.

WHAT IS LOST vs the in-process path
    Headless there is no ViewObject: check.py records direct
    `X.ViewObject.attr = v` assignments and build.py applies them, but any
    other GUI use is skipped. Parametric features arrive as plain
    Part::Feature solids (the script, not the feature tree, is the source of
    truth). Atech modules are seated in the child with the library and
    reported as data (module, ports, board placement); Studio seats the same
    ones in the document (PRD R92) - no script needs the live document for
    that any more. Scripts that genuinely need the GUI use the in-process
    path: the IN_PROCESS_SETTING user parameter (build.build_mode says which
    and why).

This module imports nothing from FreeCAD at module level: the parent side runs
under system Python (the eval harness) or inside Studio alike.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.realpath(__file__))
KIT_DIR = os.path.join(HERE, "agent_kit")
CHECK = os.path.join(KIT_DIR, "check.py")
OUT_SUBDIR = ".atech_sandbox"
DEFAULT_TIMEOUT = 60.0
MARK = "ATECH_CHECK="
# User parameter (BaseApp/Preferences/Mod/AcadAgent) that keeps the old
# in-process exec for GUI-only scripts. Read by the caller, not here.
IN_PROCESS_SETTING = "BuildInProcess"
# Files Studio writes into the workspace for the agent (build.prepare_
# workspace). Bound read-only into the child under bwrap.
PROTECTED = ("check", "atech_cad.py", "TRAPS.md", "examples")
# R140: fonts for Part.makeWireString. The usual host locations first (a
# stable path - model.py keeps it), then the bundled tree's own copy under
# _fc_root, which every mode can read (bwrap binds it). MEASURED 2026-09-25 inside the bwrap argv
# below: the tree's usr/fonts holds 31 TTFs (DejaVuSans.ttf among them) and
# /usr/share/fonts 2090 - fonts were visible all along; the agent (whose
# shell allows only ./check) never had a path to one (D56).
FONT_NAME = "DejaVuSans.ttf"
HOST_FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/TTF/DejaVuSans.ttf")


# ------------------------------------------------------------- freecadcmd
def find_freecadcmd():
    """The bundled freecadcmd: $ATECH_FREECADCMD, then next to the running
    FreeCAD, then the repo's dist build, then PATH. None if none exists."""
    cands = [os.environ.get("ATECH_FREECADCMD")]
    try:
        import FreeCAD
        cands.append(os.path.join(FreeCAD.getHomePath(), "bin", "freecadcmd"))
    except Exception:                                   # noqa: BLE001
        pass
    exe_dir = os.path.dirname(os.path.realpath(sys.executable or ""))
    cands.append(os.path.join(exe_dir, "freecadcmd"))
    repo = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
    cands.append(os.path.join(repo, "dist", "build", "squashfs-root", "usr",
                              "bin", "freecadcmd"))
    cands.append(shutil.which("freecadcmd"))
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return os.path.realpath(c)
    return None


# -------------------------------------------------------------- isolation
_ISOLATION = None


def _works(argv):
    try:
        return subprocess.run(argv, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def isolation():
    """'bwrap', 'unshare' or 'none' - probed once, by actually running it."""
    global _ISOLATION
    if _ISOLATION is None:
        mode = os.environ.get("ATECH_SANDBOX_ISOLATION")
        if mode in ("bwrap", "unshare", "none"):
            _ISOLATION = mode
        elif shutil.which("bwrap") and _works(
                ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                 "--unshare-net", "--die-with-parent", "true"]):
            _ISOLATION = "bwrap"
        elif shutil.which("unshare") and _works(["unshare", "-rn", "true"]):
            _ISOLATION = "unshare"
        else:
            _ISOLATION = "none"
    return _ISOLATION


def isolation_caveat(mode=None):
    """None when builds hide the user's home (bwrap); otherwise one plain
    sentence for the USER saying what the build can still reach (R115:
    without bwrap the scratch HOME hides nothing from an absolute path)."""
    mode = mode or isolation()
    if mode == "bwrap":
        return None
    if mode == "unshare":
        return ("Designs are built without bubblewrap (bwrap) here: the design "
                "script has no network and a scratch home folder, but it can "
                "still read your files by their full path. Install bubblewrap "
                "to hide them.")
    return ("Designs are built without isolation here (neither bubblewrap nor "
            "unshare works): the design script can read your files and use the "
            "network. Install bubblewrap to isolate it.")


def _homes():
    """Every home folder the child must not see: $HOME AND the account's
    home from the password database - Studio started with another HOME
    (a test rig, a wrapper script) must not expose the real one."""
    out = [os.path.realpath(os.path.expanduser("~")), "/root"]
    try:
        import pwd
        out.append(os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir))
    except (ImportError, KeyError, OSError):
        pass
    return sorted({h for h in out if h and h != "/" and os.path.isdir(h)})


def _fc_root(fc):
    """The install tree freecadcmd needs to see (…/usr of the AppImage)."""
    return os.path.dirname(os.path.dirname(fc))


def font_path(fc=None):
    """The TrueType font model.py should use for text (R140): absolute,
    readable inside the sandbox in every isolation mode (bwrap binds its
    folder read-only - _argv). None when no candidate exists."""
    fc = fc or find_freecadcmd()
    # A host font first: the path is written into model.py, and the
    # AppImage's tree is mounted at a new random /tmp/.mount_* on every
    # launch, so a tree path in a saved model.py breaks the next session's
    # rebuild (round-5 review). The tree's copy is the fallback for a host
    # without DejaVu.
    cands = list(HOST_FONTS)
    if fc:
        cands.append(os.path.join(_fc_root(fc), "fonts", FONT_NAME))
    for c in cands:
        if os.path.isfile(c) and os.access(c, os.R_OK):
            return os.path.realpath(c)
    return None


def _argv(mode, fc, workspace, home, extra_ro):
    base = [fc, CHECK]
    if mode == "bwrap":
        a = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
             "--tmpfs", "/tmp", "--tmpfs", "/run"]
        for hidden in _homes():
            if os.path.isdir(hidden):
                a += ["--tmpfs", hidden]
        font = font_path(fc)
        # The font's folder is bound after the tmpfs mounts, so a font found
        # under /tmp or a home folder stays readable (R140); under the
        # FreeCAD tree it is already covered, and a second bind is harmless.
        for ro in [_fc_root(fc), KIT_DIR, font and os.path.dirname(font)] + list(extra_ro):
            if ro and os.path.exists(ro):
                ro = os.path.realpath(ro)
                a += ["--ro-bind", ro, ro]
        a += ["--bind", workspace, workspace]
        # Studio's own files in the workspace stay read-only to the child:
        # a model.py that rewrote ./check would have the agent run arbitrary
        # shell OUTSIDE the sandbox on its next ./check (MEASURED before this
        # change). A read-only bind is also a mount point, so the child can
        # neither unlink nor rename over it.
        for name in PROTECTED:
            p = os.path.join(workspace, name)
            if os.path.lexists(p) and not os.path.islink(p):
                a += ["--ro-bind", p, p]
        a += ["--bind", home, home, "--chdir", workspace, "--unshare-net", "--unshare-ipc",
              "--unshare-pid", "--die-with-parent", "--new-session"]
        return a + base
    if mode == "unshare":
        return ["unshare", "-rn"] + base
    return base


def _passthrough_env():
    """Variables the child must inherit to find what the parent found: the
    Atech module library's location (atech_ports reads ATECH_ARTIFACTS; the
    folder itself is bound read-only through extra_path - PRD R92)."""
    out = {}
    lib = (os.environ.get("ATECH_ARTIFACTS") or "").strip()
    if lib:
        out["ATECH_ARTIFACTS"] = os.path.abspath(os.path.expanduser(lib))
    return out


# -------------------------------------------------------------------- job
class Result(object):
    """What the child built. ok is False on any failure; error says why."""

    def __init__(self, ok, error="", objects=(), timed_out=False, seconds=None,
                 isolation="none", report=None, stdout="", returncode=None,
                 out_dir=None):
        self.ok = ok
        self.error = error
        self.objects = list(objects)      # check.py's per-object facts (+ "brep")
        self.timed_out = timed_out
        self.seconds = seconds
        self.isolation = isolation
        self.report = report or {}        # check.py's full JSON line
        self.stdout = stdout
        self.returncode = returncode
        self.out_dir = out_dir

    def __repr__(self):
        return "<sandbox.Result ok=%s objects=%d timed_out=%s %.2fs %s>" % (
            self.ok, len(self.objects), self.timed_out, self.seconds or 0,
            self.isolation)


class Job(object):
    """One child build. start() returns at once; poll() never blocks."""

    def __init__(self, workspace, script="model.py", timeout=DEFAULT_TIMEOUT,
                 freecadcmd=None, extra_path=(), mode=None, render=False,
                 context=None):
        self.workspace = os.path.realpath(workspace)
        self.script = os.path.join(self.workspace, script)
        self.timeout = float(timeout)
        self.fc = freecadcmd or find_freecadcmd()
        self.extra_path = [os.path.realpath(p) for p in extra_path if p]
        self.mode = mode or isolation()
        self.render = render
        self.context = context
        self.out_dir = os.path.join(self.workspace, OUT_SUBDIR)
        self.proc = None
        self.result = None
        self._t0 = None
        self._home = None
        self._log = None

    def start(self):
        if self.fc is None:
            self.result = Result(False, "freecadcmd not found (set ATECH_FREECADCMD)")
            return self
        if not os.path.isfile(self.script):
            self.result = Result(False, "no %s in %s" % (
                os.path.basename(self.script), self.workspace))
            return self
        # The previous child could leave a symlink here (it can write the
        # workspace): remove the link itself, never what it points at.
        if os.path.islink(self.out_dir) or (os.path.lexists(self.out_dir)
                                            and not os.path.isdir(self.out_dir)):
            os.unlink(self.out_dir)
        elif os.path.isdir(self.out_dir):
            shutil.rmtree(self.out_dir, ignore_errors=True)
        os.makedirs(self.out_dir)
        self._home = tempfile.mkdtemp(prefix="atech-sandbox-home-")
        env = {
            "HOME": self._home,
            "PATH": "/usr/bin:/bin",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "TMPDIR": self._home,
            "XDG_CONFIG_HOME": os.path.join(self._home, ".config"),
            "XDG_DATA_HOME": os.path.join(self._home, ".local", "share"),
            "XDG_CACHE_HOME": os.path.join(self._home, ".cache"),
            "MPLCONFIGDIR": os.path.join(self._home, ".mpl"),
            "QT_QPA_PLATFORM": "offscreen",
            "ATECH_CHECK_SCRIPT": self.script,
            "ATECH_CHECK_OUT": self.out_dir,
            "ATECH_CHECK_PNG": (os.path.join(self.out_dir, "check.png")
                                if self.render else ""),
            "ATECH_CHECK_TIMEOUT": str(self.timeout),
            "ATECH_CHECK_PATH": os.pathsep.join(self.extra_path),
        }
        env.update(_passthrough_env())
        if self.context:
            env["ATECH_CHECK_CONTEXT"] = self.context
        argv = _argv(self.mode, self.fc, self.workspace, self._home, self.extra_path)
        self._log = open(os.path.join(self._home, "child.log"), "w+b")
        self._t0 = time.time()
        try:
            self.proc = subprocess.Popen(
                argv, cwd=self.workspace, env=env, stdin=subprocess.DEVNULL,
                stdout=self._log, stderr=subprocess.STDOUT,
                start_new_session=True)            # its own group: kill all of it
        except OSError as exc:
            self._finish(Result(False, "could not start the build process: %s" % exc,
                                isolation=self.mode))
        return self

    def elapsed(self):
        return 0.0 if self._t0 is None else time.time() - self._t0

    def poll(self):
        """The Result when finished, else None. Kills the child at timeout."""
        if self.result is not None:
            return self.result
        if self.proc is None:
            raise RuntimeError("sandbox.Job.poll() before start()")
        if self.proc.poll() is None:
            if self.elapsed() > self.timeout + 5:     # check.py stops itself at
                self._kill()                         # `timeout`; this is the backstop
                self._finish(Result(
                    False, "model.py did not finish in %g s; the build process "
                    "was stopped. Look for an endless loop or a very heavy "
                    "operation." % self.timeout, timed_out=True,
                    seconds=round(self.elapsed(), 2), isolation=self.mode))
            return self.result
        self._finish(self._collect())
        return self.result

    def wait(self, tick=0.05):
        while self.poll() is None:
            time.sleep(tick)
        return self.result

    def cancel(self):
        if self.result is None and self.proc is not None:
            self._kill()
            self._finish(Result(False, "cancelled", seconds=round(self.elapsed(), 2),
                                isolation=self.mode))

    # ------------------------------------------------------------ internals
    def _kill(self):
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except (OSError, AttributeError):
            try:
                self.proc.kill()
            except OSError:
                pass
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            pass

    def _collect(self):
        self._log.seek(0)
        text = self._log.read().decode("utf-8", "replace")
        secs = round(self.elapsed(), 2)
        report = None
        for line in reversed(text.splitlines()):
            if line.startswith(MARK):
                try:
                    report = json.loads(line[len(MARK):])
                except ValueError:
                    pass
                break
        if report is None:
            return Result(False, "the build process ended without a result "
                          "(exit code %s):\n%s" % (self.proc.returncode, text[-3000:]),
                          seconds=secs, isolation=self.mode, stdout=text,
                          returncode=self.proc.returncode)
        err = report.get("error") or ""
        timed_out = bool(report.get("timed_out"))
        ok = bool(report.get("ok"))
        if ok and not all(o.get("brep") for o in report.get("objects", [])):
            ok, err = False, "a result could not be exported: %s" % [
                o.get("brep_error") for o in report.get("objects", [])]
        return Result(ok, err, report.get("objects", []), timed_out=timed_out,
                      seconds=secs, isolation=self.mode, report=report,
                      stdout=text, returncode=self.proc.returncode,
                      out_dir=self.out_dir)

    def _finish(self, result):
        self.result = result
        if self._log is not None:
            try:
                self._log.close()
            except OSError:
                pass
        if self._home:
            shutil.rmtree(self._home, ignore_errors=True)
            self._home = None


def wrapper_script(workspace, extra_path=(), freecadcmd=None, mode=None,
                   timeout=DEFAULT_TIMEOUT, context=None):
    """The text of the agent's ./check (PRD S09): build model.py in the same
    isolated child Studio uses, print check.py's lines, write check.png.

    context: the JSON index of the user's objects (build._export_context,
    written when the turn starts) - the same seed Studio's own build gets,
    so ./check sees what model.py will see in Studio (R128). Its folder
    must be in extra_path (bound read-only).

    The agent is allowed to run exactly this file, so it must not be a way
    around the sandbox: it runs check.py under the same bwrap/unshare argv,
    with a scratch HOME, one check at a time (flock), and a hard `timeout`
    on top of check.py's own. Returns None when no freecadcmd is found."""
    import shlex
    fc = freecadcmd or find_freecadcmd()
    if fc is None:
        return None
    ws = os.path.realpath(workspace)
    mode = mode or isolation()
    extra = [os.path.realpath(p) for p in extra_path if p]
    placeholder = "/@ATECH_HOME@"
    argv = _argv(mode, fc, ws, placeholder, extra)
    cmd = " ".join('"$h"' if a == placeholder else shlex.quote(a) for a in argv)
    env = {
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "QT_QPA_PLATFORM": "offscreen",
        "ATECH_CHECK_SCRIPT": os.path.join(ws, "model.py"),
        "ATECH_CHECK_PNG": os.path.join(ws, "check.png"),
        "ATECH_CHECK_TIMEOUT": str(timeout),
        "ATECH_CHECK_PATH": os.pathsep.join(extra),
    }
    if context:
        env["ATECH_CHECK_CONTEXT"] = os.path.realpath(context)
    env.update(_passthrough_env())
    env_s = " ".join("%s=%s" % (k, shlex.quote(v)) for k, v in env.items())
    return """#!/bin/sh
# Atech Atelier self-check - written by Atelier, rewritten every turn.
# Builds model.py headless in a sandbox, prints what it measured, writes
# check.png. The last line is CHECK PASS or CHECK FAIL: <reasons>.
cd %(ws)s || exit 3
h=$(mktemp -d "${TMPDIR:-/tmp}/atech-check-home-XXXXXX") || exit 3
trap 'rm -rf "$h"' EXIT INT TERM
lock=""
if command -v flock >/dev/null 2>&1; then lock="flock -w 120 .check.lock"; fi
stop=""
if command -v timeout >/dev/null 2>&1; then stop="timeout -k 5 %(hard)d"; fi
env -i HOME="$h" TMPDIR="$h" XDG_CONFIG_HOME="$h/.config" \
    XDG_DATA_HOME="$h/.local/share" XDG_CACHE_HOME="$h/.cache" \
    MPLCONFIGDIR="$h/.mpl" %(env)s \
    $lock $stop %(cmd)s
""" % {"ws": shlex.quote(ws), "hard": int(timeout) + 30, "env": env_s, "cmd": cmd}


def run(workspace, script="model.py", timeout=DEFAULT_TIMEOUT, **kw):
    """Build model.py in a child process and wait. Returns a Result."""
    return Job(workspace, script, timeout, **kw).start().wait()


# ------------------------------------------------------------ main thread
def import_result(doc, result):
    """Add a successful Result's solids to `doc` as Part::Feature objects with
    the names and labels model.py gave them. MAIN THREAD ONLY. Returns the
    created objects; raises ValueError on a failed result."""
    import Part
    if not result.ok:
        raise ValueError("refusing to import a failed build: %s" % result.error)
    made = []
    for o in result.objects:
        shape = Part.Shape()
        shape.read(o["brep"])
        obj = doc.addObject("Part::Feature", o.get("name") or "Body")
        obj.Shape = shape
        if o.get("label"):
            obj.Label = o["label"]
        made.append(obj)
    doc.recompute()
    return made
