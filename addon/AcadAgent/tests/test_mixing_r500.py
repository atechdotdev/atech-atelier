"""R510-R517: mixing Atech hardware and CAD end to end (see fc_mixing_r500.py
for what each id covers). Headless only: freecadcmd + offscreen Qt, a
scratch HOME, never the GUI app.

    QT_QPA_PLATFORM=offscreen <bundled python> -m unittest -v test_mixing_r500

Runs fc_mixing_r500.py under freecadcmd (ATECH_FREECADCMD or the dist
build) once clean and once per sabotage, in parallel; skips without
freecadcmd or the module library.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(ADDON))


def _freecadcmd():
    env = os.environ.get("ATECH_FREECADCMD")
    if env and os.path.isfile(env):
        return env
    for arch in ("arm64", "x86_64"):
        p = os.path.join(REPO, "dist", "build-macos-%s" % arch, "Atech Atelier.app",
                         "Contents", "Resources", "bin", "freecadcmd")
        if os.path.isfile(p):
            return p
    return shutil.which("freecadcmd")


FC = _freecadcmd()
MODELS = os.environ.get("ATECH_ARTIFACTS") or os.path.join(REPO, "models")
LIB = os.path.isfile(os.path.join(REPO, "projects", "atech_ports.py")) and \
    os.path.isfile(os.path.join(MODELS, "presets.yaml"))

#: sabotage: (flows to run, checks it must fail)
SABOTAGES = {
    "boardfirst": ("f1", {"f1.board_first"}),
    "fitted": ("f1,f3", {"f3.page_fitted", "f3.check_all_fitted"}),
    "owner": ("f1,f3", {"f3.cable_owned", "f3.rebuild_one_cable"}),
    "cable_parts": ("f1,f6", {"f6.fit_no_cable"}),
    "observer": ("f7", {"f7.no_dead_doc"}),
    "tick": ("f7", {"f7.tick_quiet"}),
}
_RUNS = {}


def _launch(sabotage="", only=""):
    tmp = tempfile.mkdtemp(prefix="atech-r500-")
    home = os.path.join(tmp, "home")
    os.makedirs(home)
    env = dict(os.environ)
    for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "PYTHONPATH",
              "PYTHONHOME"):
        env.pop(k, None)
    env.update(HOME=home, ATECH_R500_DIR=tmp, ATECH_ARTIFACTS=MODELS,
               QT_QPA_PLATFORM="offscreen", PYTHONUNBUFFERED="1",
               ATECH_R500_SABOTAGE=sabotage, ATECH_R500_ONLY=only)
    p = subprocess.Popen([FC, os.path.join(HERE, "fc_mixing_r500.py")], env=env,
                         cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    p._tmp = tmp
    return p


def _parse(out):
    # not anchored: FreeCAD's "Recompute... (100 %)" progress has no newline
    checks = dict(re.findall(r"CHECK (f\d\.\S+) (PASS|FAIL|SKIP)", out))
    m = re.search(r"R500_TESTS=(\d+)", out)
    return checks, (int(m.group(1)) if m else None)


@unittest.skipIf(FC is None, "freecadcmd not found (set ATECH_FREECADCMD)")
@unittest.skipUnless(LIB, "the Atech module library is not in this checkout")
class TestMixing(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if _RUNS:
            return
        procs = {"": _launch()}
        procs.update({k: _launch(k, only) for k, (only, _m) in SABOTAGES.items()})
        for k, p in procs.items():
            out, _ = p.communicate(timeout=1500)
            _RUNS[k] = out.decode("utf-8", "replace")
            shutil.rmtree(p._tmp, True)

    def out(self):
        return _RUNS[""][-4000:]

    def assert_flow(self, prefix, minimum):
        checks, _ = _parse(_RUNS[""])
        mine = {k: v for k, v in checks.items() if k.startswith(prefix)}
        self.assertGreaterEqual(len([v for v in mine.values() if v == "PASS"]),
                                minimum, self.out())
        self.assertEqual([k for k, v in mine.items() if v == "FAIL"], [], self.out())

    def test_clean_run(self):
        checks, n = _parse(_RUNS[""])
        self.assertEqual(n, 0, self.out())
        self.assertGreater(len(checks), 45)

    def test_r510_board_first_then_build(self):
        self.assert_flow("f1.", 12)

    def test_r511_user_modules_first(self):
        # the case-fits half needs the kit change reported for check.py and
        # build.py (R511); until then the refusal is pinned instead
        self.assert_flow("f2.", 4)

    def test_r512_r517_cables_and_fitted_after(self):
        self.assert_flow("f3.", 11)

    def test_r513_save_and_reopen(self):
        self.assert_flow("f4.", 8)

    def test_r514_only_cad(self):
        self.assert_flow("f5.", 4)

    def test_r515_measure_export_bom(self):
        self.assert_flow("f6.", 10)

    def test_r516_close_many_documents(self):
        self.assert_flow("f7.", 6)

    def test_sabotage_each_fix_is_caught(self):
        for name, (_only, must_fail) in sorted(SABOTAGES.items()):
            checks, n = _parse(_RUNS[name])
            failed = {k for k, v in checks.items() if v == "FAIL"}
            self.assertTrue(n, "sabotage %r went unnoticed:\n%s" % (name, _RUNS[name][-2000:]))
            self.assertTrue(must_fail <= failed, "sabotage %r: expected %s to fail, failed: %s"
                            % (name, sorted(must_fail), sorted(failed)))


if __name__ == "__main__":
    unittest.main()
