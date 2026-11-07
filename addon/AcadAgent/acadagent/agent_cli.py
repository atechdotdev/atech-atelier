"""agent_cli — what the Codex and Cursor CLI engines share (R870).

claude_cli.py finds, probes and runs `claude`. codex_cli.py and cursor_cli.py
do the same for `codex` and `cursor-agent`; the parts that do not depend on
the CLI live here: finding the program the way a desktop launch must (R22),
reading the long options its --help lists, and asking its version.

Every rule claude_cli states for the same job holds here too: an explicit
path from Agent Settings that is wrong is reported, never replaced by some
other program; a login-shell probe runs at most once and never on the GUI
thread; nothing that starts a process is called from the GUI thread.
"""
import glob
import os
import re
import shutil
import subprocess

from . import claude_cli


def _home():
    return os.environ.get("HOME") or os.path.expanduser("~")


def expand(path):
    if path.startswith("~/"):
        return os.path.join(_home(), path[2:])
    return path


def is_exe(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def child_env():
    """The CLI child's environment: claude_cli._child_env (FreeCAD's own
    PYTHONHOME/PYTHONPATH and bundle paths stripped)."""
    return claude_cli._child_env()


class Locator(object):
    """Find one CLI program. `names`: the program names searched on PATH,
    in order; `known`: candidate paths (home-relative allowed) probed
    after PATH; `nvm`: the per-Node-version glob, newest first."""

    def __init__(self, names, path_key, known=(), nvm=None):
        self.names = tuple(names)
        self.path_key = path_key
        self.known = tuple(known)
        self.nvm = nvm
        # None = not probed yet; "" = probed, nothing found.
        self._shell_found = None

    def configured_path(self):
        """The explicit path from Agent Settings, or ""."""
        try:
            from . import settings
            val = settings.load().get(self.path_key)
            return val.strip() if isinstance(val, str) else ""
        except Exception:                              # noqa: BLE001
            return ""

    def known_locations(self):
        """Every candidate path, in probe order. Pure."""
        out = [expand(p) for p in self.known]
        if self.nvm:
            out += sorted(glob.glob(expand(self.nvm)),
                          key=claude_cli._version_key, reverse=True)
        return out

    def find(self, explicit=None):
        """Absolute path to the program, or None. `explicit`: None reads
        Agent Settings; a string (even "") is used instead. Order: the
        explicit path; PATH; the known locations; the login-shell answer
        when probe_login_shell() has run. Starts no process."""
        if explicit is None:
            explicit = self.configured_path()
        explicit = (explicit or "").strip()
        if explicit:
            explicit = expand(explicit)
            return explicit if is_exe(explicit) else None
        for name in self.names:
            found = shutil.which(name)
            if found:
                return found
        for cand in self.known_locations():
            if is_exe(cand):
                return cand
        if self._shell_found and is_exe(self._shell_found):
            return self._shell_found
        return None

    def probe_login_shell(self, timeout=8):
        """Ask the user's login shell where the program is. ONCE, and never
        on the GUI thread. Only an absolute path to an executable counts."""
        if self._shell_found is not None:
            return self._shell_found or None
        shell = os.environ.get("SHELL") or "/bin/sh"
        found = ""
        for name in self.names:
            try:
                out = subprocess.run([shell, "-lc", "command -v %s" % name],
                                     capture_output=True, text=True,
                                     timeout=timeout,
                                     stdin=subprocess.DEVNULL,
                                     env=child_env())
            except Exception:                          # noqa: BLE001
                continue
            for line in (out.stdout or "").splitlines():
                line = line.strip()
                if os.path.isabs(line) and is_exe(line):
                    found = line
                    break
            if found:
                break
        self._shell_found = found
        return found or None

    def locate(self, timeout=8):
        """find(), falling back to the login-shell probe. Worker only."""
        return self.find() or (None if self.configured_path() else
                               self.probe_login_shell(timeout))


_HELP = {}


def help_flags(exe, args=("--help",), timeout=10):
    """The long options `exe *args` lists, as a frozenset; cached per
    (exe, args); empty (and not cached) when the help cannot be read.
    Starts a process: call from a worker."""
    key = (exe, tuple(args))
    if not exe:
        return frozenset()
    if key in _HELP:
        return _HELP[key]
    try:
        out = subprocess.run([exe] + list(args), capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL, env=child_env())
        text = "%s\n%s" % (out.stdout or "", out.stderr or "")
    except Exception:                                  # noqa: BLE001
        text = ""
    flags = frozenset(re.findall(r"(?<![\w-])(--[a-zA-Z][a-zA-Z0-9-]*)",
                                 text))
    if flags:
        _HELP[key] = flags
    return flags


_VERSIONS = {}


def version(exe, timeout=10):
    """`exe --version`'s first line, or None. Cached per program."""
    if not exe:
        return None
    if exe in _VERSIONS:
        return _VERSIONS[exe]
    try:
        out = subprocess.run([exe, "--version"], capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL, env=child_env())
        lines = (out.stdout or "").strip().splitlines()
        v = lines[0].strip() if lines else None
    except Exception:                                  # noqa: BLE001
        v = None
    _VERSIONS[exe] = v
    return v


#: Linux caps ONE argv string at 128 KiB (MAX_ARG_STRLEN); macOS caps the
#: whole argv + environment at 1 MiB. A text passed as an argument stays
#: under this, or goes another way (stdin, a private file).
ARG_LIMIT = 96 * 1024


def fits_argv(text):
    return len((text or "").encode("utf-8")) <= ARG_LIMIT
