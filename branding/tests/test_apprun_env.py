#!/usr/bin/env python3
"""R61: AppRun keeps the caller's environment so children can get it back.

Runs a patched copy of an upstream-shaped AppRun under real bash, launching
a stub "application" that dumps its environment, and checks that restore()
turns that environment back into the one AppRun was started with -- values
the caller had come back, values the caller did not have go away.

When a built tree exists (dist/build/squashfs-root/AppRun) the same check
runs against the real upstream AppRun too, so the measured export list is
the one that ships.

    python3 branding/tests/test_apprun_env.py   -> APPRUN_ENV_TESTS_OK
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BRANDING = os.path.dirname(HERE)
REPO = os.path.dirname(BRANDING)
sys.path.insert(0, BRANDING)

import apprun_env  # noqa: E402

REAL_APPRUN = os.path.join(REPO, "dist", "build", "squashfs-root", "AppRun")

# The upstream FreeCAD 1.1.3 AppRun, reduced to its environment lines and its
# launch logic (verbatim shapes, including the commented-out export).
FIXTURE = r'''#!/bin/bash
HERE="$(dirname "$(readlink -f "${0}")")"
export PREFIX=${HERE}/usr
# export LD_LIBRARY_PATH=${HERE}/usr/lib${LD_LIBRARY_PATH:+':'}$LD_LIBRARY_PATH
export PYTHONHOME=${HERE}/usr
export PATH_TO_FREECAD_LIBDIR=${HERE}/usr/lib
export FONTCONFIG_FILE=/etc/fonts/fonts.conf
export FONTCONFIG_PATH=/etc/fonts
export QT_QPA_PLATFORM=xcb
export SSL_CERT_FILE=$PREFIX/ssl/cacert.pem
export GIT_SSL_CAINFO=$HERE/usr/ssl/cacert.pem
if [ ! -z "$1" ] && [ -e "$HERE/usr/bin/$1" ] ; then
    MAIN="$HERE/usr/bin/$1" ; shift
else
    MAIN="$HERE/usr/bin/freecad"
fi
"${MAIN}" "$@"
'''

DUMP = "#!/bin/sh\nexec env -0 > \"$1\"\n"


def _run(apprun_src, caller_env, patch=True):
    """Patch `apprun_src`, run it with `caller_env`, return the child env."""
    tmp = tempfile.mkdtemp(prefix="apprun_env_")
    try:
        os.makedirs(os.path.join(tmp, "usr", "bin"))
        app = os.path.join(tmp, "AppRun")
        with open(app, "w", encoding="utf-8") as fh:
            fh.write(apprun_env.insert_snapshot(apprun_src) if patch
                     else apprun_src)
        os.chmod(app, 0o755)
        dump = os.path.join(tmp, "usr", "bin", "atech-envdump")
        with open(dump, "w", encoding="utf-8") as fh:
            fh.write(DUMP)
        os.chmod(dump, 0o755)
        out = os.path.join(tmp, "env.bin")
        subprocess.run([app, "atech-envdump", out], env=caller_env,
                       check=True, capture_output=True, timeout=30)
        with open(out, "rb") as fh:
            raw = fh.read().decode("utf-8", "surrogateescape")
        child = dict(kv.split("=", 1) for kv in raw.split("\0") if "=" in kv)
        return child
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _caller():
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": "/home/someone",
        "QT_QPA_PLATFORM": "wayland",          # the user's own value
        "SSL_CERT_FILE": "/etc/corp/ca.pem",   # the user's own value
        "WITH_SPACES": "a b  c",
        "WITH_NEWLINE": "line1\nline2",
    }


class AppRunEnv(unittest.TestCase):
    def test_names_measured_from_exports(self):
        self.assertEqual(apprun_env.exported_names(FIXTURE), [
            "PREFIX", "PYTHONHOME", "PATH_TO_FREECAD_LIBDIR",
            "FONTCONFIG_FILE", "FONTCONFIG_PATH", "QT_QPA_PLATFORM",
            "SSL_CERT_FILE", "GIT_SSL_CAINFO"])

    def test_child_sees_apprun_values(self):
        child = _run(FIXTURE, _caller())
        self.assertEqual(child["QT_QPA_PLATFORM"], "xcb")
        self.assertTrue(child["PYTHONHOME"].endswith("/usr"))
        self.assertEqual(child["ATECH_PRE_APPRUN_QT_QPA_PLATFORM"], "wayland")
        self.assertNotIn("ATECH_PRE_APPRUN_PYTHONHOME", child)

    def test_restore_gives_back_the_caller_env(self):
        caller = _caller()
        got = apprun_env.restore(_run(FIXTURE, caller))
        # bash itself adds PWD/SHLVL/_ ; those are not AppRun's doing.
        for k in ("PWD", "SHLVL", "_", "OLDPWD"):
            got.pop(k, None)
        self.assertEqual(got, caller)

    def test_inherited_stale_snapshot_is_dropped(self):
        # Atech Atelier started from a shell that already carries an outer one's
        # snapshot: a name this caller never set must not be "restored" to
        # the outer caller's value.
        caller = _caller()
        del caller["QT_QPA_PLATFORM"]
        caller["ATECH_PRE_APPRUN_QT_QPA_PLATFORM"] = "wayland"
        child = _run(FIXTURE, caller)
        self.assertNotIn("ATECH_PRE_APPRUN_QT_QPA_PLATFORM", child)
        self.assertNotIn("QT_QPA_PLATFORM", apprun_env.restore(child))

    def test_without_snapshot_restore_cannot(self):
        # Control: the unpatched AppRun loses the user's value for good.
        child = _run(FIXTURE, _caller(), patch=False)
        self.assertEqual(child["QT_QPA_PLATFORM"], "xcb")
        self.assertNotEqual(apprun_env.restore(child).get("QT_QPA_PLATFORM"),
                            "wayland")

    def test_idempotent(self):
        once = apprun_env.insert_snapshot(FIXTURE)
        self.assertEqual(apprun_env.insert_snapshot(once), once)
        self.assertEqual(once.count(apprun_env.MARK), 1)

    def test_shape_change_fails_loudly(self):
        with self.assertRaises(ValueError):
            apprun_env.insert_snapshot("#!/bin/sh\nexport A=1\n")
        with self.assertRaises(ValueError):
            apprun_env.insert_snapshot("#!/bin/bash\necho no exports\n")

    @unittest.skipUnless(os.path.isfile(REAL_APPRUN), "no built tree")
    def test_real_apprun(self):
        with open(REAL_APPRUN, encoding="utf-8") as fh:
            src = fh.read()
        # A rebuilt tree already carries the block: cut it out (mark through
        # its end line), keeping the upstream text on both sides of it.
        if apprun_env.MARK in src:
            head, rest = src.split(apprun_env.MARK, 1)
            src = head + rest.split("# --- end snapshot ---\n", 1)[1]
        names = apprun_env.exported_names(src)
        self.assertIn("QT_QPA_PLATFORM", names)
        self.assertIn("PYTHONHOME", names)
        patched = apprun_env.insert_snapshot(src)
        r = subprocess.run(["bash", "-n"], input=patched.encode(),
                           capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    r = unittest.main(exit=False, verbosity=2).result
    if r.wasSuccessful():
        print("APPRUN_ENV_TESTS_OK")
    sys.exit(0 if r.wasSuccessful() else 1)
