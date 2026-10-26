#!/usr/bin/env python3
"""Drive the REAL Atech app (Cocoa) through one scenario and collect results.

    python3 app_driver.py scn_smoke.py [--app ".../Atech Atelier.app"]
                          [--out DIR] [--timeout 180] [--profile DIR]
                          [--keep-open]

* Launches <app>/Contents/MacOS/FreeCAD with an ISOLATED profile: HOME and
  FREECAD_USER_HOME both point at a fresh folder (FreeCAD on macOS takes its
  user folders from the account unless FREECAD_USER_HOME is set; MEASURED by
  branding/build_macos.sh). On that first run FreeCAD seeds user.cfg from
  branding.xml's UserParameterTemplate (bin/atech_user_template.cfg), so the
  Atech workbench (StartWorkbench) activates and installs the shell exactly
  as on a user's first launch.
* The scenario file is passed on the command line; FreeCAD runs it as a macro
  once the GUI is up. It talks back through $ATECH_GUI_OUT (result.json, PNGs)
  and the "ATECH_GUI_RESULT <path>" marker on stdout.
* Hard timeout: the process group is killed (SIGTERM, then SIGKILL).

The app's windows appear on screen for the scenario's duration (Cocoa needs a
real window server for the macOS style); nothing outside the app is touched
and no screenshot of the desktop is taken (pixels come from QWidget.grab()).

Prints one JSON summary line ("ATECH_GUI_SUMMARY {...}") and exits 0 when the
scenario reported ok, 1 otherwise, 2 on harness failure (no result).
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRATCH_DEFAULT = os.environ.get("ATECH_GUI_SCRATCH", "/tmp/atech-gui")


def default_app():
    env = os.environ.get("ATECH_GUI_APP")
    if env:
        return env
    return os.path.join(SCRATCH_DEFAULT, "app-build", "AtechTest.stage")


def run(scenario, app=None, out=None, timeout=180.0, profile=None, keep_open=False,
        extra_env=None, quiet=False):
    app = os.path.abspath(app or default_app())
    exe = os.path.join(app, "Contents", "MacOS", "FreeCAD")
    if not os.path.isfile(exe):
        raise SystemExit("no app binary at %s (run make_test_app.sh first)" % exe)
    scenario = os.path.abspath(scenario)
    name = os.path.splitext(os.path.basename(scenario))[0]
    out = os.path.abspath(out or os.path.join(SCRATCH_DEFAULT, "runs",
                                              "%s-%s" % (name, time.strftime("%Y%m%d-%H%M%S"))))
    os.makedirs(out, exist_ok=True)
    profile = os.path.abspath(profile or tempfile.mkdtemp(prefix="profile-", dir=out))
    os.makedirs(profile, exist_ok=True)
    profile = os.path.realpath(profile)

    env = {
        "HOME": profile,
        "FREECAD_USER_HOME": profile,
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "en_US.UTF-8",
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "ATECH_GUI_OUT": out,
        "ATECH_GUI_HARNESS": HERE,
        "ATECH_GUI_TIMEOUT": str(max(10.0, timeout - 15.0)),
        "ATECH_GUI_KEEP_OPEN": "1" if keep_open else "0",
    }
    env.update(extra_env or {})
    log_file = os.path.join(out, "freecad.log")
    cmd = [exe, "--log-file", log_file, scenario]
    t0 = time.time()
    env["ATECH_GUI_T0"] = repr(t0)
    stdout_path = os.path.join(out, "stdout.txt")
    proc = subprocess.Popen(cmd, env=env, cwd=profile, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=True)
    marker = {}
    lines = []

    def reader():
        with open(stdout_path, "w", encoding="utf-8") as f:
            for raw in iter(proc.stdout.readline, b""):
                ln = raw.decode("utf-8", "replace")
                f.write(ln)
                f.flush()
                lines.append(ln)
                if ln.startswith("ATECH_GUI_RESULT "):
                    marker["path"] = ln.split(" ", 1)[1].strip()
                    marker["t"] = time.time() - t0
                if not quiet and ln.startswith(("ATECH_GUI_LOG", "ATECH_GUI_RESULT")):
                    sys.stderr.write(ln)
    th = threading.Thread(target=reader, daemon=True)
    th.start()

    killed = False
    try:
        proc.wait(timeout=timeout if not keep_open else None)
    except subprocess.TimeoutExpired:
        killed = True
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                break
            try:
                proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                continue
    th.join(timeout=5)
    wall = time.time() - t0
    res_path = marker.get("path") or os.path.join(out, "result.json")
    result = None
    if os.path.isfile(res_path):
        with open(res_path, encoding="utf-8") as f:
            result = json.load(f)
    summary = {
        "scenario": name, "out": out, "profile": profile, "app": app,
        "rc": proc.returncode, "killed_on_timeout": killed,
        "wall_s": round(wall, 2),
        "t_result_s": round(marker["t"], 2) if "t" in marker else None,
        "ok": bool(result and result.get("ok")),
        "result": res_path if result else None,
        "steps_failed": [s["name"] for s in (result or {}).get("steps", []) if not s.get("ok")],
        "exceptions": len((result or {}).get("exceptions", [])),
        "pngs": [g["path"] for g in (result or {}).get("grabs", [])],
    }
    return summary, result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scenario")
    ap.add_argument("--app", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--timeout", type=float, default=180.0)
    ap.add_argument("--profile", default=None,
                    help="reuse a profile folder (default: a fresh one per run)")
    ap.add_argument("--keep-open", action="store_true",
                    help="leave the app running after the scenario (debugging)")
    ap.add_argument("--env", action="append", default=[],
                    help="extra KEY=VALUE for the app's environment (repeatable)")
    a = ap.parse_args(argv)
    extra = dict(kv.split("=", 1) for kv in a.env)
    summary, result = run(a.scenario, a.app, a.out, a.timeout, a.profile, a.keep_open, extra)
    print("ATECH_GUI_SUMMARY " + json.dumps(summary))
    if result is None:
        return 2
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
