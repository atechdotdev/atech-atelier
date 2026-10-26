"""macOS support: the Seatbelt sandbox, the data folder, the orphan guard,
the bundle's PATH, and the bundle identity the macOS build stamps.

Pure parts run everywhere (CI on Linux and macOS, plain Python, no FreeCAD,
no Qt). The real-world parts run only on macOS:

  - TestOrphanGuardLive: a process group really is killed when its parent
    is SIGKILLed, and the guard really exits when the group ends first;
  - TestSeatbeltLive: with ATECH_FREECADCMD pointing at a FreeCAD (or Atech
    Atelier) bundle's freecadcmd, a model.py that tries to list the home
    folder, reach the network and rewrite ./check is stopped, and the model
    still builds - through sandbox.run() AND through the generated ./check.

    ATECH_FREECADCMD=".../Atech Atelier.app/Contents/Resources/bin/freecadcmd" \\
        python -m unittest -v test_macos
"""
import importlib
import os
import plistlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))
BRANDING = os.path.join(REPO, "branding")
if ADDON not in sys.path:
    sys.path.insert(0, ADDON)

import acadagent                                          # noqa: E402
from acadagent import sandbox                             # noqa: E402

DARWIN = sys.platform == "darwin"


def _claude_cli():
    """claude_cli under a minimal PySide6 stub when Qt is not installed."""
    try:
        import PySide6.QtCore                             # noqa: F401
        return importlib.import_module("acadagent.claude_cli")
    except ImportError:
        pass
    core = types.ModuleType("PySide6.QtCore")
    core.QObject = object
    core.QThread = object
    core.Signal = lambda *a, **k: None
    root = types.ModuleType("PySide6")
    root.QtCore = core
    with mock.patch.dict(sys.modules, {"PySide6": root, "PySide6.QtCore": core}):
        sys.modules.pop("acadagent.claude_cli", None)
        mod = importlib.import_module("acadagent.claude_cli")
    return mod


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------ pure parts
class TestDataRoot(unittest.TestCase):
    def test_per_platform(self):
        with mock.patch.dict(os.environ, {"HOME": "/h"}):
            with mock.patch.object(sys, "platform", "darwin"):
                self.assertEqual(acadagent.fallback_data_root(),
                                 "/h/Library/Application Support/Atech Atelier")
            with mock.patch.object(sys, "platform", "linux"):
                self.assertEqual(acadagent.fallback_data_root(),
                                 "/h/.local/share/Atech Atelier")


class TestStripBundlePaths(unittest.TestCase):
    def test_only_bundle_entries_go(self):
        top = "/Applications/Atech Atelier.app"
        env = {"PATH": "%s/Contents/Resources/bin:%s/Contents/Resources/Mod/Draft:"
                       "/Users/u/.local/bin:/usr/bin" % (top, top),
               "OTHER": top + "/Contents/Resources/lib",
               "KEEP": "/Applications/Atech Atelier.apple/x"}
        out = acadagent.strip_bundle_paths(dict(env), top)
        self.assertEqual(out["PATH"], "/Users/u/.local/bin:/usr/bin")
        self.assertNotIn("OTHER", out)          # nothing left: removed
        self.assertEqual(out["KEEP"], env["KEEP"])   # a prefix, not inside

    def test_no_bundle_no_change(self):
        env = {"PATH": "/a:/b"}
        with mock.patch.object(acadagent, "macos_bundle", return_value=None):
            self.assertEqual(acadagent.strip_bundle_paths(dict(env)), env)


class TestSeatbeltProfile(unittest.TestCase):
    def test_profile_shape(self):
        p = sandbox.seatbelt_profile(2, 3, 1)
        self.assertTrue(p.startswith("(version 1)"))
        self.assertIn("(deny network*)", p)
        for name in ("HOME0", "HOME1", "RO0", "RO2", "P0", "FC", "WS", "SCRATCH"):
            self.assertIn('(param "%s")' % name, p)
        self.assertNotIn('"HOME2"', p)
        # SBPL: the last matching rule wins, so the allows follow the denies
        self.assertLess(p.index("(deny file-read-data"), p.index("(allow file-read-data"))
        self.assertLess(p.index("(deny file-write*)"), p.index("(allow file-write*"))
        self.assertGreater(p.rindex('(literal (param "P0"))'), p.index("(allow file-write*"))
        # metadata stays readable: denying it stops freecadcmd (MEASURED)
        self.assertNotIn("(deny file-read*", p)

    def test_argv_passes_paths_as_parameters(self):
        ws = tempfile.mkdtemp(prefix="atech-ws-")
        self.addCleanup(shutil.rmtree, ws, True)
        with open(os.path.join(ws, "check"), "w") as fh:
            fh.write("#!/bin/sh\n")
        fc = "/Apps/Odd 'name\".app/Contents/Resources/bin/freecadcmd"
        a = sandbox._argv("seatbelt", fc, ws, "/scratch", [])
        self.assertEqual(a[0], sandbox.SANDBOX_EXEC)
        profile = a[2]
        self.assertNotIn(ws, profile)           # paths never spliced in
        self.assertNotIn("Odd", profile)
        params = dict(a[i + 1].split("=", 1) for i, x in enumerate(a) if x == "-D")
        self.assertEqual(params["WS"], ws)
        self.assertEqual(params["SCRATCH"], "/scratch")
        self.assertEqual(params["FC"], "/Apps/Odd 'name\".app/Contents/Resources")
        self.assertEqual(params["P0"], os.path.join(ws, "check"))
        self.assertEqual(a[-2:], [fc, sandbox.CHECK])

    def test_wrapper_substitutes_the_scratch_home(self):
        ws = tempfile.mkdtemp(prefix="atech-ws-")
        self.addCleanup(shutil.rmtree, ws, True)
        text = sandbox.wrapper_script(ws, freecadcmd="/fc/bin/freecadcmd",
                                      mode="seatbelt")
        self.assertIn("SCRATCH=\"$h\"", text)
        self.assertNotIn("@ATECH_HOME@", text)
        self.assertIn('h=$(cd "$h" && pwd -P)', text)   # Seatbelt matches real paths
        # macOS has no flock; R250: the lock wait follows the mode's timeout
        # (120 s in fast mode, 240 s in quality mode, the default)
        wait = max(120, int(sandbox.default_timeout()) + 60)
        self.assertIn("lockf -t %d .check.lock" % wait, text)
        self.assertIn("perl -e alarm(shift);exec(@ARGV)||exit(127)", text)

    def test_bwrap_wrapper_unchanged_shape(self):
        ws = tempfile.mkdtemp(prefix="atech-ws-")
        self.addCleanup(shutil.rmtree, ws, True)
        text = sandbox.wrapper_script(ws, freecadcmd="/fc/bin/freecadcmd",
                                      mode="bwrap")
        self.assertIn('--bind "$h" "$h"', text)

    def test_caveats(self):
        self.assertIsNone(sandbox.isolation_caveat("seatbelt"))
        self.assertIsNone(sandbox.isolation_caveat("bwrap"))
        with mock.patch.object(sys, "platform", "darwin"):
            none = sandbox.isolation_caveat("none")
            self.assertIn("macOS sandbox", none)
            self.assertNotIn("bubblewrap", none)    # cannot be installed there
        self.assertIn("full path", sandbox.isolation_caveat("unshare"))

    def test_isolation_override(self):
        with mock.patch.object(sandbox, "_ISOLATION", None), \
                mock.patch.dict(os.environ, {"ATECH_SANDBOX_ISOLATION": "seatbelt"}):
            self.assertEqual(sandbox.isolation(), "seatbelt")


class TestOrphanGuardPure(unittest.TestCase):
    def test_not_on_linux(self):
        cli = _claude_cli()
        with mock.patch.object(sys, "platform", "linux"):
            self.assertIsNone(cli._orphan_guard(12345))

    def test_macos_install_locations(self):
        cli = _claude_cli()
        self.assertIn("~/Library/pnpm/claude", cli.KNOWN_LOCATIONS)
        self.assertIn("/opt/homebrew/bin/claude", cli.KNOWN_LOCATIONS)


class TestBundleIdentity(unittest.TestCase):
    def setUp(self):
        self.mb = _load(os.path.join(BRANDING, "macos_bundle.py"), "macos_bundle")

    def test_stamp(self):
        pl = {"CFBundleIdentifier": "org.freecad.FreeCAD", "CFBundleName": "FreeCAD_1.1.3",
              "CFBundleExecutable": "FreeCAD", "CFBundleIconFile": "freecad.icns",
              "CFBundleDocumentTypes": [{"CFBundleTypeExtensions": ["FCStd"],
                                         "LSIsAppleDefaultForType": True,
                                         "CFBundleTypeRole": "Editor"}],
              "UTExportedTypeDeclarations": [{"UTTypeIdentifier": "org.freecad.fcstd"}]}
        out = self.mb.stamp_plist(pl, "1.2.3", "atech.icns")
        self.assertEqual(out["CFBundleIdentifier"], "dev.atech.Atelier")
        self.assertEqual(out["CFBundleName"], "Atech Atelier")
        self.assertEqual(out["CFBundleDisplayName"], "Atech Atelier")
        self.assertEqual(out["CFBundleExecutable"], "FreeCAD")   # untouched
        self.assertEqual(out["CFBundleShortVersionString"], "1.2.3")
        self.assertEqual(out["CFBundleIconFile"], "atech.icns")
        self.assertIn("FreeCAD contributors", out["NSHumanReadableCopyright"])
        d = out["CFBundleDocumentTypes"][0]
        self.assertEqual(d["LSHandlerRank"], "Alternate")
        self.assertNotIn("LSIsAppleDefaultForType", d)
        self.assertNotIn("UTExportedTypeDeclarations", out)
        self.assertEqual(out["UTImportedTypeDeclarations"][0]["UTTypeIdentifier"],
                         "org.freecad.fcstd")
        plistlib.dumps(out)                     # still a valid plist

    def test_identity_agrees_with_the_gate_and_branding(self):
        with open(os.path.join(BRANDING, "verify_tree.py"), encoding="utf-8") as fh:
            gate = fh.read()
        self.assertIn('PRODUCT = "%s"' % self.mb.PRODUCT, gate)
        self.assertIn('APP_ID = "%s"' % self.mb.APP_ID, gate)
        with open(os.path.join(BRANDING, "build_macos.sh"), encoding="utf-8") as fh:
            build = fh.read()
        self.assertIn('PRODUCT="%s"' % self.mb.PRODUCT, build)
        self.assertIn('APP_ID="%s"' % self.mb.APP_ID, build)
        self.assertEqual(acadagent.PRODUCT, self.mb.PRODUCT)

    def test_release_names(self):
        rm = _load(os.path.join(BRANDING, "release_meta.py"), "release_meta")
        self.assertEqual(rm.dmg_name("1.2.3", "arm64"), "AtechAtelier-1.2.3-macOS-arm64.dmg")
        self.assertEqual(rm.dmg_name("1.2.3", "x86_64"), "AtechAtelier-1.2.3-macOS-x86_64.dmg")
        with self.assertRaises(ValueError):
            rm.dmg_name("1.2.3", "ppc")


# ------------------------------------------------------------ live (macOS)
@unittest.skipUnless(DARWIN, "macOS only")
class TestOrphanGuardLive(unittest.TestCase):
    def test_group_dies_with_parent(self):
        cli = _claude_cli()
        # `parent` stands in for Studio: it starts a process group (the CLI
        # and a child of it) in its own session, then is SIGKILLed.
        code = ("import subprocess, time\n"
                "p = subprocess.Popen(['/bin/sh', '-c', 'sleep 300 & sleep 300'],"
                " start_new_session=True)\n"
                "print(p.pid, flush=True)\n"
                "time.sleep(300)\n")
        parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE,
                                  text=True)
        pgid = int(parent.stdout.readline())
        # The guard _orphan_guard starts, watching `parent` instead of us.
        guard = subprocess.Popen(["/bin/sh", "-c", cli._ORPHAN_GUARD, "guard",
                                  str(parent.pid), str(pgid)], start_new_session=True)
        try:
            os.killpg(pgid, 0)                  # the group is alive
            parent.kill()
            parent.wait()
            deadline = time.time() + 10
            while time.time() < deadline:
                try:
                    os.killpg(pgid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.2)
            with self.assertRaises(ProcessLookupError):
                os.killpg(pgid, 0)
            self.assertEqual(guard.wait(10), 0)
        finally:
            parent.stdout.close()
            for fn in (lambda: os.killpg(pgid, signal.SIGKILL), guard.kill):
                try:
                    fn()
                except (OSError, ProcessLookupError):
                    pass

    def test_guard_exits_when_the_run_ends(self):
        cli = _claude_cli()
        p = subprocess.Popen(["sleep", "0.5"], start_new_session=True)
        g = cli._orphan_guard(p.pid)
        self.assertIsNotNone(g)
        p.wait()
        self.assertEqual(g.wait(5), 0)


ESCAPE = r'''
import os, socket
leak = []
for p in (%(home)r, os.path.join(%(home)r, "Documents"), "/Volumes", "/private/tmp"):
    try:
        os.listdir(p); leak.append("listed " + p)
    except OSError:
        pass
try:
    socket.create_connection(("1.1.1.1", 80), 2); leak.append("network")
except OSError:
    pass
try:
    open("check", "w").write("pwned"); leak.append("rewrote ./check")
except OSError:
    pass
try:
    open(os.path.join(%(home)r, ".atech-sandbox-escape"), "w"); leak.append("wrote home")
except OSError:
    pass
print("LEAKS=%%r" %% leak)
import Part
b = doc.addObject("Part::Feature", "Box")
b.Shape = Part.makeBox(10, 20, 30)
'''


@unittest.skipUnless(DARWIN and os.environ.get("ATECH_FREECADCMD"),
                     "macOS with ATECH_FREECADCMD only")
class TestSeatbeltLive(unittest.TestCase):
    def setUp(self):
        sandbox._ISOLATION = None
        self.assertEqual(sandbox.isolation(), "seatbelt")
        # Under the real home folder, like the app's chat folders.
        base = os.path.join(acadagent.fallback_data_root(), "test-sandbox")
        os.makedirs(base, exist_ok=True)
        self.addCleanup(lambda: os.path.isdir(base) and not os.listdir(base)
                        and os.rmdir(base))
        self.ws = os.path.realpath(tempfile.mkdtemp(prefix="ws-", dir=base))
        self.addCleanup(shutil.rmtree, self.ws, True)
        home = os.path.realpath(os.path.expanduser("~"))
        with open(os.path.join(self.ws, "model.py"), "w") as fh:
            fh.write(ESCAPE % {"home": home})
        with open(os.path.join(self.ws, "check"), "w") as fh:
            fh.write("#!/bin/sh\necho original\n")
        self.home = home

    def _assert_contained(self, text):
        self.assertIn("LEAKS=[]", text)
        self.assertFalse(os.path.exists(os.path.join(self.home, ".atech-sandbox-escape")))
        with open(os.path.join(self.ws, "check")) as fh:
            self.assertEqual(fh.read(), "#!/bin/sh\necho original\n")

    def test_run(self):
        r = sandbox.run(self.ws, timeout=120)
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.isolation, "seatbelt")
        self.assertEqual([(o["name"], o["volume_mm3"]) for o in r.objects], [("Box", 6000.0)])
        self._assert_contained(r.stdout)

    def test_check_wrapper(self):
        path = os.path.join(self.ws, "check2")
        with open(path, "w") as fh:
            fh.write(sandbox.wrapper_script(self.ws))
        os.chmod(path, 0o755)
        out = subprocess.run([path], cwd=self.ws, capture_output=True, text=True,
                             timeout=300).stdout
        self.assertIn("CHECK PASS", out)
        self._assert_contained(out)


if __name__ == "__main__":
    unittest.main()
