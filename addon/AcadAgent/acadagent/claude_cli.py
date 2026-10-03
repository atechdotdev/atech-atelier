"""claude_cli — drive the local `claude` CLI directly, no HTTP backend.

WHY THIS EXISTS
    client.py speaks opencode's HTTP API, which needs a separate `opencode
    serve` process on :4096 to be running, adopted or spawned (backend.py).
    Claude Code needs none of that: it is a local binary that streams NDJSON
    on stdout. No port, no supervisor, no adoption logic, no parser bound to
    someone else's OpenAPI schema.

MEASURED WIRE FORMAT (claude 2.1.232, read off a live run 2026-09-24)
    claude -p "<prompt>" --output-format stream-json --verbose
    emits one JSON object per line:
      {"type":"system","subtype":"init", "session_id":..., "tools":[...]}
      {"type":"assistant","message":{"content":[{"type":"text","text":...},
                                                {"type":"tool_use","name":...}]}}
      {"type":"user", ...}                       tool results come back here
      {"type":"result","subtype":"success","result":"...","is_error":false,
       "total_cost_usd":..., "duration_ms":...}
    --resume <session_id> continues a session, which is how the panel keeps
    one conversation across turns.

    THE PROMPT GOES ON STDIN, NOT ARGV (R35). MEASURED 2026-09-25 on
    2.1.232 and 2.0.25: `claude -p` with no positional reads the prompt from
    stdin. On argv it was readable by every local user in
    /proc/<pid>/cmdline, and a prompt starting with "-" ("-5 mm thinner")
    was parsed as an option and failed every time. The system prompt goes
    in a 0600 file (--append-system-prompt-file) when the CLI has it.

    LEAN, ISOLATED AGENT LAUNCH (S16, R78) - agent_argv(). MEASURED
    2026-09-25, "Reply with exactly: OK", same workspace and system prompt:
                        init    first text   input+cache tokens   cost
      old argv (n=3)    2.16 s  3.49 s       42 606               $0.187
      agent_argv (n=5)  0.84 s  2.05 s        8 913               $0.019
    and with agent_argv the child no longer inherits the user's MCP servers
    (Gmail, Drive, ... were connected before), slash commands (71 -> 0) or
    their global additionalDirectories: a Glob of one of those folders
    succeeded before and is a permission denial now.

    IMAGES: claude reads an image when the prompt names its path. Verified —
    handed it a viewport PNG and it identified the crane unprompted. So the
    existing capture.py round trip works with no new protocol.

THREADING
    Same rule as runner.py: FreeCAD's GUI is not thread-safe. This class runs
    the subprocess on a QThread and emits Qt signals; the panel does all
    widget work on the main thread.

WHAT THIS DOES NOT DO
    It does not decide whether Claude may write geometry. Permission is the
    CLI's own concern (--permission-mode), surfaced here as an explicit
    argument rather than a default, because an unreviewed write into a
    document whose whole value is traceability is the failure this project
    cares most about (ADR / PRD bet 5).
"""
import json
import os
import shutil
import subprocess

from PySide6 import QtCore


DEFAULT_BIN = os.path.expanduser("~/.local/bin/claude")

#: Where the official installers and the common Node managers put `claude`.
#: A desktop launch (the AppImage from a file manager or a .desktop entry)
#: gets the session's PATH, not the one the user's shell builds, so a binary
#: that `claude` finds in a terminal is often invisible here. (R22)
#: Home-relative entries are expanded at call time, so a test (or a user
#: with a moved HOME) sees its own tree.
#: DEFAULT_BIN (the official native installer's ~/.local/bin/claude) is
#: always probed first, ahead of these.
KNOWN_LOCATIONS = (
    "~/.claude/local/claude",              # `claude migrate-installer`
    "~/.npm-global/bin/claude",            # npm prefix=~/.npm-global
    "~/.bun/bin/claude",
    "~/.volta/bin/claude",
    "~/.local/share/pnpm/claude",
    "~/.yarn/bin/claude",
    "/usr/local/bin/claude",
    "/opt/homebrew/bin/claude",
    "/usr/bin/claude",
)
#: nvm keeps one tree per Node version; the newest one wins.
NVM_GLOB = "~/.nvm/versions/node/*/bin/claude"

#: What the "not found" notice tells the user to do. MEASURED 2026-09-25:
#: docs.anthropic.com/en/docs/claude-code/setup answers 301 to this URL, and
#: https://claude.ai/install.sh answers 302 to the release bootstrap script.
INSTALL_URL = "https://code.claude.com/docs/en/setup"
INSTALL_COMMAND = "curl -fsSL https://claude.ai/install.sh | bash"
#: What the "sign in" notice tells the user to run. MEASURED 2026-10-04 on
#: claude 2.1.232: `claude auth --help` lists "login  Sign in to your
#: Anthropic account". Older CLIs only have /login inside `claude`, so the
#: notice names both.
LOGIN_COMMAND = "claude auth login"

# The login-shell probe runs at most once per process (it can take a second
# on a heavy shell rc). None = not probed yet; "" = probed, nothing found.
_SHELL_FOUND = None


def _home():
    return os.environ.get("HOME") or os.path.expanduser("~")


def _expand(path):
    if path.startswith("~/"):
        return os.path.join(_home(), path[2:])
    return path


def _is_exe(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def _version_key(path):
    """'.../node/v22.3.1/bin/claude' -> (22, 3, 1) for a newest-first sort."""
    part = path.split(os.sep + "node" + os.sep, 1)[-1].split(os.sep, 1)[0]
    nums = []
    for bit in part.lstrip("v").split("."):
        try:
            nums.append(int(bit))
        except ValueError:
            nums.append(-1)
    return tuple(nums)


def known_locations():
    """Every candidate path, in probe order. Pure: no process is started."""
    import glob
    out = [DEFAULT_BIN] + [_expand(p) for p in KNOWN_LOCATIONS]
    out += sorted(glob.glob(_expand(NVM_GLOB)), key=_version_key, reverse=True)
    return out


def configured_path():
    """The explicit path from Agent Settings, or "" when none is set."""
    try:
        from . import settings
        return (settings.load().get("claude_path") or "").strip()
    except Exception:                                  # noqa: BLE001
        return ""


def find_claude(explicit=None):
    """Absolute path to the claude binary, or None. Never guesses a name.

    `explicit`: None reads the path from Agent Settings; a string (even "")
    is used instead of the stored one - the dialog checks a typed path
    before it is saved.

    Order: the path set in Agent Settings; the official installer's
    ~/.local/bin/claude; the process PATH; the other known install
    locations; the login-shell answer if probe_login_shell() has run.
    Nothing here starts a process, so it is safe on the GUI thread.

    NOTE: on this machine `claude` is a *shell function* wrapping the real
    binary, so `which claude` inside a shell lies about it being on PATH.
    A subprocess does not get shell functions, so we resolve a real file.
    """
    if explicit is None:
        explicit = configured_path()
    explicit = (explicit or "").strip()
    if explicit:
        explicit = _expand(explicit)
        # An explicit path that is wrong is reported, not silently replaced
        # by some other claude the user did not choose.
        return explicit if _is_exe(explicit) else None
    cands = known_locations()
    if _is_exe(cands[0]):
        return cands[0]
    found = shutil.which("claude")
    if found:
        return found
    for cand in cands[1:]:
        if _is_exe(cand):
            return cand
    if _SHELL_FOUND and _is_exe(_SHELL_FOUND):
        return _SHELL_FOUND
    return None


def probe_login_shell(timeout=8):
    """Ask the user's login shell where `claude` is. ONCE, and never on the
    GUI thread: a login shell reads the user's profile, which can be slow.

    Only an absolute path to an executable file counts. `command -v` answers
    with a bare name for a shell function or alias (this machine wraps
    claude in one), and that is not something a subprocess can run.
    """
    global _SHELL_FOUND
    if _SHELL_FOUND is not None:
        return _SHELL_FOUND or None
    shell = os.environ.get("SHELL") or "/bin/sh"
    found = ""
    try:
        out = subprocess.run([shell, "-lc", "command -v claude"],
                             capture_output=True, text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL, env=_child_env())
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if os.path.isabs(line) and _is_exe(line):
                found = line
                break
    except Exception:                                  # noqa: BLE001
        found = ""
    _SHELL_FOUND = found
    return found or None


def locate(timeout=8):
    """find_claude(), falling back to the login-shell probe. Worker only."""
    return find_claude() or (None if configured_path() else
                             probe_login_shell(timeout))


def available():
    return find_claude() is not None


_VERSIONS = {}


def version(timeout=10):
    """The CLI's own version string, or None when it cannot be asked.
    Cached per binary: the answer does not change while Studio runs."""
    exe = find_claude()
    if exe is None:
        return None
    if exe in _VERSIONS:
        return _VERSIONS[exe]
    try:
        out = subprocess.run([exe, "--version"], capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL, env=_child_env())
        v = out.stdout.strip() or None
    except Exception:
        v = None
    _VERSIONS[exe] = v
    return v


def auth_status(timeout=15):
    """(logged_in, detail) from `claude auth status`, or (None, reason).

    MEASURED 2026-09-25 (claude 2.1.232): prints JSON with "loggedIn"; with
    an empty HOME it prints {"loggedIn": false, "authMethod": "none", ...}
    and exits 1. None means we could not tell - never read as "logged in".
    Starts a process: call from a worker.
    """
    exe = find_claude()
    if exe is None:
        return None, "not found"
    try:
        out = subprocess.run([exe, "auth", "status"], capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL, env=_child_env())
    except Exception as exc:                           # noqa: BLE001
        return None, "%s" % (exc,)
    try:
        data = json.loads(out.stdout or "null")
    except ValueError:
        data = None
    if not isinstance(data, dict) or "loggedIn" not in data:
        # MEASURED 2026-09-25: claude 2.0.25 (an npm install in
        # /usr/local/bin) has no JSON auth status; signed out it prints
        # "Invalid API key · Please run /login" and exits 1. Read that as
        # signed out; anything else stays "could not tell".
        text = ("%s\n%s" % (out.stdout or "", out.stderr or "")).strip()
        if text and classify_failure(text) == AUTH:
            return False, text[:300]
        return None, "unrecognised auth status"
    return bool(data.get("loggedIn")), str(data.get("authMethod") or "")


# --------------------------------------------------------- flag support
_HELP = {}


def supported_flags(exe=None, timeout=10):
    """The long options the installed CLI's `--help` lists, as a frozenset.

    Cached per binary. MEASURED: this machine has claude 2.1.232 in
    ~/.local/bin and 2.0.25 in /usr/local/bin, and 2.0.25 lacks --tools,
    --effort, --max-budget-usd, ... ; an unknown option fails the whole run
    ("error: unknown option"), so a flag is only passed when --help names
    it. "--append-system-prompt[-file]" in the help text counts as both
    spellings (2.1.232 documents the -file variant only that way; measured:
    it accepts --append-system-prompt-file). Starts a process (about
    0.2-0.6 s): call from a worker. Empty when --help cannot be read.
    """
    import re
    exe = exe or find_claude()
    if not exe:
        return frozenset()
    if exe in _HELP:
        return _HELP[exe]
    try:
        out = subprocess.run([exe, "--help"], capture_output=True, text=True,
                             timeout=timeout, stdin=subprocess.DEVNULL,
                             env=_child_env())
        text = "%s\n%s" % (out.stdout or "", out.stderr or "")
    except Exception:                                  # noqa: BLE001
        text = ""
    flags = set(re.findall(r"(?<![\w-])(--[a-zA-Z][a-zA-Z0-9-]*)", text))
    for base in re.findall(r"(--[a-zA-Z][a-zA-Z0-9-]*)\[-file\]", text):
        flags.update((base, base + "-file"))
    if not flags:
        # A --help that timed out or failed once (a cold start, a CLI
        # mid-update) must not pin EVERY later turn to the un-isolated
        # launch (R78): only a readable answer is cached.
        return frozenset()
    _HELP[exe] = frozenset(flags)
    return _HELP[exe]


#: The only tools the chat agent gets. Only ever passed together with
#: --strict-mcp-config: MEASURED, --tools alone still loaded the user's MCP
#: servers (97k tokens for "OK").
AGENT_TOOLS = "Read,Write,Edit,Bash,Glob,Grep"
#: Exactly the self-check command (S09/S10), never bare Bash. MEASURED
#: 2026-09-25: with these, `./check` ran; `./check 2>&1; echo` and `ls ~`
#: came back as permission_denials.
CHECK_ALLOW = ("Bash(./check)", "Bash(./check *)")
#: --effort choices, from `claude --help` (2.1.232).
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_BUDGET_USD = 3.00


def agent_settings(cfg=None):
    """agent_argv() keyword arguments from Agent Settings (S16, S26)."""
    if cfg is None:
        try:
            from . import settings
            cfg = settings.load()
        except Exception:                              # noqa: BLE001
            cfg = {}
    model = cfg.get("agent_model")
    effort = cfg.get("agent_effort")
    budget = cfg.get("agent_budget_usd", DEFAULT_BUDGET_USD)
    try:
        budget = float(budget) if budget not in (None, "") else None
    except (TypeError, ValueError):
        budget = DEFAULT_BUDGET_USD
    return {"model": model.strip() if isinstance(model, str) else None,
            "effort": effort.strip() if isinstance(effort, str) else None,
            "budget": budget}


def agent_argv(ws, model=None, effort=None, allowed=CHECK_ALLOW,
               budget=DEFAULT_BUDGET_USD, exe=None, flags=None, dropped=None):
    """The flags of one chat-agent turn: the ONE place they are assembled
    (S16). The eval harness takes its argv from here too (S15).

    Isolation (R78): no MCP servers but none, only AGENT_TOOLS, none of the
    user's settings files (their permissions and additionalDirectories),
    no slash commands/skills. Exactly one --add-dir: `ws`, the chat's own
    workspace (R14). `allowed` is the exact Bash allowlist (S10).

    A flag the installed CLI does not list in --help is dropped, never
    passed (it would fail the run); its name is appended to `dropped` when
    a list is given. `flags` overrides the probe (tests).
    """
    have = supported_flags(exe) if flags is None else frozenset(flags)
    out = []

    def want(flag, *values):
        if flag in have:
            out.extend((flag,) + values)
            return True
        if dropped is not None:
            dropped.append(flag)
        return False

    if "--strict-mcp-config" in have and "--tools" in have:
        out += ["--strict-mcp-config", "--tools", AGENT_TOOLS]
    else:
        want("--strict-mcp-config")
        if dropped is not None and "--tools" not in have:
            dropped.append("--tools")
    want("--setting-sources", "")
    want("--disable-slash-commands")
    want("--exclude-dynamic-system-prompt-sections")
    if budget:
        want("--max-budget-usd", "%.2f" % float(budget))
    if model:
        want("--model", str(model))
    if effort:
        if effort in EFFORTS:
            want("--effort", effort)
        elif dropped is not None:
            dropped.append("--effort %s" % effort)
    allowed = [a for a in (allowed or ()) if a]
    if allowed:
        flag = "--allowedTools" if "--allowedTools" in have else \
            "--allowed-tools"
        want(flag, *allowed)
    # --add-dir predates every CLI this addon supports; it is never dropped.
    out += ["--add-dir", ws]
    return out


# ------------------------------------------------ parent death (R215)
#: PR_SET_PDEATHSIG, from <linux/prctl.h>.
_PR_SET_PDEATHSIG = 1


def _pdeathsig_fn(sig=15):
    """A Popen preexec_fn that ties the child's life to Studio's (R215),
    or None where it cannot (not Linux, no libc).

    MEASURED (S7 cycle 2): after Studio was SIGKILLed, `claude -p ...
    --permission-mode acceptEdits` kept running in the chat folder,
    re-parented to the session manager. start_new_session=True takes the
    CLI out of Studio's process group (so Stop can signal the whole
    group), which is also why nothing reached it when Studio died.

    prctl(PR_SET_PDEATHSIG) fires when the THREAD that forked exits, not
    the process. The fork happens on the run's QThread, and that thread
    does not leave run() before _reap() has seen the CLI exit, so the
    signal can only fire while Studio is going away. The libc function is
    resolved here, in the parent: the forked child only calls it and
    getppid() (no import, no allocation). If Studio died between fork and
    prctl the child sees another parent and exits at once."""
    import sys
    if not sys.platform.startswith("linux"):
        return None
    try:
        import ctypes
        prctl = ctypes.CDLL(None, use_errno=True).prctl
        prctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                          ctypes.c_ulong, ctypes.c_ulong)
        prctl.restype = ctypes.c_int
    except Exception:                                  # noqa: BLE001
        return None
    parent = os.getpid()

    def tie():
        prctl(_PR_SET_PDEATHSIG, sig, 0, 0, 0)
        if os.getppid() != parent:
            os._exit(1)
    return tie


def _child_env():
    env = dict(os.environ)
    # FreeCAD's AppImage sets PYTHONHOME/PYTHONPATH for its own bundled
    # interpreter. Inherited by a child, they make unrelated Python tools
    # import the wrong stdlib. Strip them for the child only.
    for k in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"):
        env.pop(k, None)
    return env


# ------------------------------------------------------ failure classes
AUTH, OFFLINE, CANCELLED, OTHER = "auth", "offline", "cancelled", "other"
#: The turn hit --max-budget-usd (R101). MEASURED in dogfood D45: the
#: failed message read "Reached maximum budget ($3)". The Agent SDK names
#: the result subtype error_max_budget_usd (documented, not measured here);
#: _judge() appends it when the text does not already say "budget".
BUDGET = "budget"

_AUTH_MARKS = ("not logged in", "/login", "invalid api key",
               "authentication_error", "authentication failed",
               "oauth token", "token has expired", "unauthorized",
               "please log in")
_OFFLINE_MARKS = ("could not reach the claude api", "network_error",
                  "enotfound", "econnrefused", "econnreset", "etimedout",
                  "eai_again", "getaddrinfo", "fetch failed",
                  "connection error", "unable to connect",
                  "network is unreachable", "no internet")
_BUDGET_MARKS = ("maximum budget", "error_max_budget", "max_budget_usd",
                 "budget exceeded", "exceeded the budget")


def classify_failure(msg):
    """AUTH | OFFLINE | BUDGET | CANCELLED | OTHER for a ClaudeRun.failed
    message.

    Pattern-matched on text the CLI actually printed (MEASURED 2026-09-24:
    logged out -> "Not logged in · Please run /login"; offline -> api_retry
    records then an error_during_execution result, which run() reports as
    "could not reach the Claude API"). OTHER is the honest answer for
    anything else - it is never rounded to one of the named causes.
    """
    low = (msg or "").lower()
    if low == "cancelled":
        return CANCELLED
    if any(m in low for m in _AUTH_MARKS):
        return AUTH
    if any(m in low for m in _BUDGET_MARKS):
        return BUDGET
    if any(m in low for m in _OFFLINE_MARKS):
        return OFFLINE
    return OTHER


class ClaudeRun(QtCore.QThread):
    """One `claude -p` turn, streamed.

    Signals carry already-decoded content so the panel never parses JSON.
    """

    started_session = QtCore.Signal(str)      # session_id
    text = QtCore.Signal(str)                 # assistant prose, incremental
    tool = QtCore.Signal(str, str)            # tool name, one-line argument summary
    # S19, only with --include-partial-messages: the text of the assistant
    # block being streamed so far, and "writing model.py: N lines" while a
    # Write/Edit tool call's input is still arriving.
    delta = QtCore.Signal(str)
    progress = QtCore.Signal(str)
    finished_ok = QtCore.Signal(str, dict)    # final text, result record
    failed = QtCore.Signal(str)               # human-readable reason
    # R184: a stream event arrived - (what the turn waits on next, detail):
    # "model" (the model is streaming, or a tool result went back to it),
    # "tool" (a tool call is running; detail = name + argument summary),
    # "retry" (the CLI is retrying the API; detail = attempt). Every event
    # counts, the ones no other signal carries included; repeats of the
    # same state are sent at most once per ACTIVITY_EVERY seconds.
    activity = QtCore.Signal(str, str)
    # R198: the model has an assistant message open (stream_event
    # message_start, --include-partial-messages) - True - or it closed
    # (message_stop, the tool results going back, an API retry, the
    # result) - False. Sent on change only. A quiet OPEN message is the
    # model still producing it (thinking before a long Write); a Retry
    # there throws that reasoning away.
    message_open = QtCore.Signal(bool)
    # R201 (D76): a tool call the CLI answered with is_error (an
    # InputValidationError, a refused command): tool name, the one-line
    # argument summary the `tool` signal carried for it, a short reason.
    # `activity` then says ("failed", "<name> <args>").
    tool_failed = QtCore.Signal(str, str, str)

    # R216: a tool call the CLI refused for want of a permission (a Read
    # outside the chat's one --add-dir, a command off the allowlist): tool
    # name, argument summary, a short reason. Sent INSTEAD of tool_failed
    # for such a call; `activity` says ("failed", "<name> <args>") too.
    tool_refused = QtCore.Signal(str, str, str)

    #: R215: tie the CLI's life to Studio's (PR_SET_PDEATHSIG). A class
    #: switch so a test can take the fix out.
    TIE_TO_PARENT = True

    #: R184: minimum seconds between two identical activity signals (a
    #: streamed reply is hundreds of events a minute).
    ACTIVITY_EVERY = 1.0

    # MEASURED from `claude --help` (2.1.232): the valid choices are
    # acceptEdits, auto, bypassPermissions, manual, dontAsk, plan.
    # "default" is NOT among them — passing it fails every run. We default to
    # "manual" so the assistant cannot write unreviewed changes into a
    # document whose whole value is that every number is traceable.
    PERMISSION_MODES = ("manual", "plan", "acceptEdits", "auto",
                        "dontAsk", "bypassPermissions")
    DEFAULT_PERMISSION_MODE = "manual"

    # A QThread destroyed while still running aborts the whole process —
    # MEASURED 2026-09-24: FreeCAD core-dumped with "QThread: Destroyed while
    # thread is still running" when the only reference to a run was a local
    # that went out of scope. Qt parenting makes it WORSE: a parent widget's
    # deleteLater destroys a running child thread (R18/R19). So runs are
    # created with parent=None and every live run holds a hard reference
    # here until its thread has finished.
    _LIVE = set()

    #: Seconds between SIGTERM to the CLI's process group and SIGKILL.
    KILL_AFTER = 2.0
    #: After the `result` record the turn is over for the user (S19); the
    #: CLI then takes ~0.5 s to exit (MEASURED 0.53-0.69 s). It is left to
    #: exit on its own - it may still be writing the session --resume needs
    #: - and only signalled if it has not after this many seconds.
    EXIT_GRACE = 10.0

    def __init__(self, prompt, cwd=None, session_id=None, images=None,
                 permission_mode=None, model=None, extra_args=None,
                 parent=None, system_prompt=None, agent=None):
        super().__init__(parent)
        ClaudeRun._LIVE.add(self)
        self.finished.connect(self._release)
        self._prompt = prompt
        self._cwd = cwd or os.getcwd()
        self._session = session_id
        self._images = list(images or [])
        mode = permission_mode or self.DEFAULT_PERMISSION_MODE
        if mode not in self.PERMISSION_MODES:
            ClaudeRun._LIVE.discard(self)
            raise ValueError("unknown permission mode %r (choices: %s)"
                             % (mode, ", ".join(self.PERMISSION_MODES)))
        self._permission_mode = mode
        self._model = model
        # Caller-owned flags, passed through verbatim after the ones this
        # class manages.
        self._extra = list(extra_args or [])
        # Appended to Claude Code's system prompt: through a 0600 file when
        # the CLI supports it, never readable in the process list (R35).
        self._system_prompt = system_prompt
        # agent_argv() keyword arguments (ws, model, effort, ...). Built in
        # the worker, because it asks the CLI's --help (S16).
        self._agent = dict(agent) if agent else None
        self._private = None        # temp dir for the system prompt file
        self.dropped = []           # flags this CLI does not support
        self._proc = None
        self._errf = None
        self._cancelled = False
        self._killer = None
        self._emitted = False
        self._act = (None, 0.0)     # R184: (last activity sent, when)
        self._open = False          # R198: an assistant message is open
        self._tool_ids = {}         # R201: tool_use id -> (name, summary)
        self.argv = None            # what was actually run, for the log
        self.timings = {}           # seconds from Popen: init, result, exit

    def _release(self):
        # Only a finished thread may lose its last reference. `finished` is
        # emitted from the thread just BEFORE it stops, and the queued slot
        # can run while isRunning() is still True; the thread is past run()
        # by then, so a short wait closes that window instead of leaking the
        # run in _LIVE for the rest of the session.
        if self.isRunning():
            self.wait(1000)
        if not self.isRunning():
            ClaudeRun._LIVE.discard(self)

    # -------------------------------------------------------------- command
    def _argv(self):
        exe = find_claude()
        if exe is None:
            raise RuntimeError("the `claude` CLI was not found on this system")
        # The prompt is NOT here: it goes on stdin (R35).
        argv = [exe, "-p", "--output-format", "stream-json", "--verbose"]
        have = None
        if self._agent is not None or self._system_prompt:
            have = supported_flags(exe)
        if have is not None and "--include-partial-messages" in have:
            argv.append("--include-partial-messages")      # S19
        if self._session:
            argv += ["--resume", self._session]
        if self._model:
            argv += ["--model", self._model]
        if self._permission_mode:
            argv += ["--permission-mode", self._permission_mode]
        if self._agent is not None:
            kw = dict(self._agent)
            kw.setdefault("ws", self._cwd)
            if self._model:
                kw["model"] = None          # already passed above
            argv += agent_argv(exe=exe, flags=have, dropped=self.dropped,
                               **kw)
        if self._system_prompt:
            argv += self._system_prompt_args(have)
        return argv + self._extra

    def _system_prompt_args(self, have):
        """--append-system-prompt-file <0600 file in a private 0700 dir>,
        removed when the turn ends; the inline flag only for a CLI without
        the -file variant."""
        if "--append-system-prompt-file" in (have or ()):
            import tempfile
            self._private = tempfile.mkdtemp(prefix="atech-claude-")
            path = os.path.join(self._private, "system-prompt.txt")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(self._system_prompt)
            return ["--append-system-prompt-file", path]
        self.dropped.append("--append-system-prompt-file")
        return ["--append-system-prompt", self._system_prompt]

    def flags(self):
        """The argv that was run, with free-text values elided, for a log
        line; None before the worker has built it (building it asks the
        CLI's --help, which must not happen on the GUI thread)."""
        if self.argv is None:
            return None
        out, skip = [], False
        for a in self.argv:
            if skip:
                out.append("<%d chars>" % len(a))
                skip = False
                continue
            out.append(a)
            skip = a in ("--append-system-prompt",)
        return out

    def prompt_text(self):
        """What is written to the CLI's stdin."""
        return self._compose_prompt()

    def _compose_prompt(self):
        """Name image paths in the prompt — that is how the CLI takes them.

        Only paths that actually exist are named. A path to a missing file
        would make Claude report it cannot read the image, which reads as a
        model failure rather than as our bug.
        """
        real = [p for p in self._images if p and os.path.isfile(p)]
        if not real:
            return self._prompt
        lines = [self._prompt, "", "Attached image(s) from the CAD viewport:"]
        lines += ["  %s" % p for p in real]
        return "\n".join(lines)

    # ----------------------------------------------------------------- run
    def run(self):
        """Every path out of here emits exactly one of finished_ok / failed,
        and leaves no child process behind. MEASURED (R19): a non-dict JSON
        line used to raise here, leaving the UI on "Working…" forever and
        the CLI orphaned."""
        outcome = None
        try:
            outcome = self._run()
        except Exception as exc:                       # noqa: BLE001
            outcome = ("failed", "the Claude Code run broke: %s: %s"
                       % (type(exc).__name__, exc))
        finally:
            self._reap()
        if outcome is None:
            outcome = ("failed", "the Claude Code run ended without a result")
        self._emit(outcome)

    def _emit(self, outcome):
        """Emit finished_ok/failed exactly once per run."""
        if self._emitted:
            return
        self._emitted = True
        if outcome[0] == "ok":
            self.finished_ok.emit(outcome[1], outcome[2])
        else:
            self.failed.emit(outcome[1])

    @staticmethod
    def _judge(record, saw_result, retries, retry_err, code, err):
        """The outcome of a turn from its result record (or its absence)."""
        if record.get("is_error") or (
                saw_result and record.get("subtype") not in (None, "success")):
            text = record.get("result") if isinstance(
                record.get("result"), str) else ""
            errors = record.get("errors")
            if not text and isinstance(errors, list):
                text = "; ".join(str(e) for e in errors)
            sub = str(record.get("subtype") or "")
            if sub.startswith("error_max_budget") and \
                    "budget" not in (text or "").lower():
                # R101: the panel names a budget stop from this message.
                text = "%s%s" % (sub, (": " + text) if text else "")
            if retries and (record.get("fast_mode_disabled_reason")
                            == "network_error" or not record.get("result")):
                return ("failed", "could not reach the Claude API (retried "
                        "%d times, last error: %s)%s"
                        % (retries, retry_err or "unknown",
                           (": " + text) if text else ""))
            return ("failed", text or err or "claude reported an error")
        if not saw_result:
            # Exit 0 with no result record is NOT success. Say so rather than
            # emitting an empty answer that looks like a reply.
            if retries:
                return ("failed", "could not reach the Claude API (retried "
                        "%d times, last error: %s)" % (retries,
                                                      retry_err or "unknown"))
            return ("failed", "claude exited %s without a result%s"
                    % (code, (": " + err) if err else ""))
        res = record.get("result")
        return ("ok", res if isinstance(res, str) else "", record)

    def _activity(self, kind, detail=""):
        """R184: emit `activity`, throttled for repeats of the same state."""
        import time
        now = time.monotonic()
        last, t = self._act
        if (kind, detail) == last and now - t < self.ACTIVITY_EVERY:
            return
        self._act = ((kind, detail), now)
        self.activity.emit(kind, detail)

    def _set_open(self, on):
        """R198: message_open, on change only."""
        on = bool(on)
        if on != self._open:
            self._open = on
            self.message_open.emit(on)

    def _tool_results(self, content, meta=None):
        """R201: the tool results of a `user` record. A result with
        is_error emits tool_failed (name and arguments of the call it
        answers, by tool_use_id) and returns ("failed", "<name> <args>");
        otherwise ("model", "") - the model has the turn again.

        R216: a result that is a permission refusal emits tool_refused
        instead (see is_refusal; `meta` is the record's tool_result_meta)."""
        failed = None
        rejected = set()
        for m in meta if isinstance(meta, list) else []:
            if isinstance(m, dict) and \
                    m.get("non_execution_kind") == "user-rejected":
                rejected.add(m.get("id"))
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or \
                    block.get("type") != "tool_result" or \
                    not block.get("is_error"):
                continue
            tid = block.get("tool_use_id")
            name, arg = self._tool_ids.get(tid, ("tool", ""))
            if tid in rejected or is_refusal(block.get("content")):
                self.tool_refused.emit(name, arg,
                                       short_refusal(block.get("content")))
            else:
                self.tool_failed.emit(name, arg,
                                      short_error(block.get("content")))
            failed = ("failed", ("%s %s" % (name, arg)).strip())
        return failed or ("model", "")

    @staticmethod
    def _waits_on(content):
        """("tool", "Bash ./check") when an assistant message ends in a
        tool call - the turn now waits on that tool - else ("model", "")."""
        blocks = [b for b in content if isinstance(b, dict)] \
            if isinstance(content, list) else []
        if blocks and blocks[-1].get("type") == "tool_use":
            b = blocks[-1]
            return "tool", ("%s %s" % (b.get("name") or "tool",
                                       _summarise(b.get("input")))).strip()
        return "model", ""

    def _partial(self, event, state):
        """One --include-partial-messages stream_event (S19). Shapes
        MEASURED on 2.1.232 (a Write of model.py): content_block_start
        {type: tool_use, name}, content_block_delta {type: input_json_delta,
        partial_json} / {type: text_delta, text}, content_block_stop."""
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        if kind == "message_start":
            self._set_open(True)            # R198
        elif kind == "message_stop":
            self._set_open(False)
        elif kind == "content_block_start":
            block = event.get("content_block")
            block = block if isinstance(block, dict) else {}
            state["kind"] = block.get("type")
            state["tool"] = str(block.get("name") or "")
            state["buf"] = ""
            state["lines"] = -1
        elif kind == "content_block_delta":
            d = event.get("delta")
            d = d if isinstance(d, dict) else {}
            if d.get("type") == "text_delta" and isinstance(d.get("text"),
                                                            str):
                state["buf"] = state.get("buf", "") + d["text"]
                self.delta.emit(state["buf"])
            elif d.get("type") == "input_json_delta" and state.get(
                    "tool") in ("Write", "Edit", "MultiEdit") and isinstance(
                        d.get("partial_json"), str):
                state["buf"] = state.get("buf", "") + d["partial_json"]
                import re
                m = re.search(r'"file_path"\s*:\s*"((?:[^"\\]|\\.)*)"',
                              state["buf"])
                if not m:
                    return
                # A JSON-escaped newline in the partial input = one line.
                n = state["buf"].count("\\n", m.end())
                if n != state.get("lines"):
                    state["lines"] = n
                    self.progress.emit("writing %s: %d line%s" % (
                        os.path.basename(m.group(1)) or "a file", n,
                        "" if n == 1 else "s"))
        elif kind == "content_block_stop":
            state.clear()

    def _run(self):
        try:
            argv = self._argv()
        except RuntimeError as exc:
            return ("failed", str(exc))
        except OSError as exc:
            return ("failed", "could not prepare the Claude Code run: %s"
                    % exc)
        self.argv = argv
        if self._cancelled:
            return ("failed", "cancelled")

        # stderr goes to a file, not a pipe: nothing drains a pipe while
        # stdout is being read, so >64 KB of stderr (MCP/server logs) would
        # block the child and hang the turn.
        import tempfile
        import time
        self._errf = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        t0 = time.monotonic()
        try:
            # Own process group, so Stop reaches whatever the CLI spawned
            # (tool shells, MCP servers) and not only the CLI itself.
            # R215: and dies with Studio (PR_SET_PDEATHSIG), because that
            # own session also keeps Studio's death from reaching it.
            self._proc = subprocess.Popen(
                argv, cwd=self._cwd, env=_child_env(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self._errf,
                text=True, bufsize=1, start_new_session=True,
                preexec_fn=_pdeathsig_fn() if self.TIE_TO_PARENT else None,
            )
        except Exception as exc:                       # noqa: BLE001
            return ("failed", "could not start claude: %s" % exc)
        if self._cancelled:             # Stop landed between check and spawn
            self.cancel()
        # The prompt on stdin, then EOF (R35). The CLI reads all of stdin
        # before it starts, so this cannot deadlock against stdout.
        try:
            self._proc.stdin.write(self._compose_prompt())
        except (BrokenPipeError, OSError):
            pass                        # it died at once; stderr says why
        finally:
            try:
                self._proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        record, saw_result = {}, False
        retries, retry_err = 0, ""
        partial = {}
        for line in self._proc.stdout:
            if self._cancelled:
                break
            if self._emitted:
                continue                # drain until the CLI exits (S19)
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                # Not every line is ours to understand; skip rather than
                # inventing meaning for it.
                continue
            if not isinstance(msg, dict):
                continue            # `null`, a bare string, a list
            kind = msg.get("type")
            if kind == "stream_event":
                self._activity("model")
                self._partial(msg.get("event"), partial)
                continue
            if kind == "system" and msg.get("subtype") == "api_retry":
                # R198: the request is being made again; a message it had
                # opened is abandoned.
                self._set_open(False)
                self._activity("retry", str(msg.get("attempt") or ""))
            elif kind == "user":
                # Tool results going back to the model (the message that
                # asked for them is over). R201: a failed one is said so.
                self._set_open(False)
                message = msg.get("message")
                self._activity(*self._tool_results(
                    message.get("content") if isinstance(message, dict)
                    else None, msg.get("tool_result_meta")))
            elif kind == "assistant":
                message = msg.get("message")
                self._activity(*self._waits_on(
                    message.get("content") if isinstance(message, dict)
                    else None))
            elif kind != "result":
                # init, a tool result going back to the model, anything
                # else the CLI streams: the model has the turn again.
                self._activity("model")
            if kind == "system" and msg.get("subtype") == "init":
                self.timings.setdefault("init", time.monotonic() - t0)
                sid = msg.get("session_id")
                if sid and isinstance(sid, str):
                    self._session = sid
                    self.started_session.emit(sid)
            elif kind == "system" and msg.get("subtype") == "api_retry":
                # MEASURED offline: the CLI retries ~10 times, then ends
                # with an error_during_execution result that has no text.
                retries += 1
                retry_err = str(msg.get("error") or retry_err)
            elif kind == "assistant":
                message = msg.get("message")
                content = message.get("content") if isinstance(
                    message, dict) else None
                if isinstance(content, str) and content:
                    self.text.emit(content)
                    continue
                for block in content if isinstance(content, list) else []:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text" and isinstance(
                            block.get("text"), str) and block["text"]:
                        self.text.emit(block["text"])
                    elif block.get("type") == "tool_use":
                        name = str(block.get("name") or "tool")
                        arg = _summarise(block.get("input"))
                        if block.get("id"):
                            self._tool_ids[block["id"]] = (name, arg)
                        self.tool.emit(name, arg)
            elif kind == "result":
                self._set_open(False)
                saw_result = True
                record = msg
                self.timings["result"] = time.monotonic() - t0
                if not record.get("is_error") and record.get("subtype") in (
                        None, "success") and not self._cancelled:
                    # S19: the turn is over the moment its result is read,
                    # not when the CLI gets round to exiting (~0.5 s
                    # later). Keep draining; a CLI that does not exit is
                    # signalled after EXIT_GRACE.
                    self._emit(self._judge(record, True, retries, retry_err,
                                           0, ""))
                    self._arm_exit_watchdog()

        code = self._proc.wait()
        self.timings["exit"] = time.monotonic() - t0
        err = self._stderr_tail()

        if self._emitted:
            return None
        if self._cancelled:
            return ("failed", "cancelled")
        return self._judge(record, saw_result, retries, retry_err, code, err)

    def _arm_exit_watchdog(self):
        if self._killer is None and self._proc is not None:
            import threading
            self._killer = threading.Timer(self.EXIT_GRACE, self._escalate)
            self._killer.daemon = True
            self._killer.start()

    def _escalate(self):
        """SIGTERM the group; SIGKILL it KILL_AFTER seconds later."""
        self._signal_group(15)
        import threading
        t = threading.Timer(self.KILL_AFTER, self._signal_group, args=(9,))
        t.daemon = True
        t.start()

    def _stderr_tail(self):
        try:
            self._errf.seek(0)
            return (self._errf.read() or "").strip()[-4000:]
        except Exception:                              # noqa: BLE001
            return ""

    def _signal_group(self, sig):
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, sig)     # pid == pgid: start_new_session
        except (ProcessLookupError, PermissionError):
            pass
        except OSError:
            try:
                proc.send_signal(sig)
            except Exception:                          # noqa: BLE001
                pass

    def _reap(self):
        """No orphan: SIGTERM the group, SIGKILL it if it lingers, wait."""
        proc = self._proc
        try:
            if proc is not None and proc.poll() is None:
                self._signal_group(15)
                try:
                    proc.wait(self.KILL_AFTER)
                except subprocess.TimeoutExpired:
                    self._signal_group(9)
                    proc.wait(5)
        except Exception:                              # noqa: BLE001
            pass
        for f in (getattr(proc, "stdout", None), self._errf):
            try:
                if f is not None:
                    f.close()
            except Exception:                          # noqa: BLE001
                pass
        if self._killer is not None:
            self._killer.cancel()
        if self._private:
            shutil.rmtree(self._private, ignore_errors=True)
            self._private = None

    def cancel(self):
        """Stop the turn. Never blocks the caller: SIGTERM now, SIGKILL
        KILL_AFTER seconds later if the group is still alive."""
        self._cancelled = True
        self._signal_group(15)
        if self._killer is None and self._proc is not None:
            import threading
            self._killer = threading.Timer(self.KILL_AFTER,
                                           self._signal_group, args=(9,))
            self._killer.daemon = True
            self._killer.start()

    @classmethod
    def shutdown_all(cls, timeout_ms=3000):
        """Stop every live run and WAIT. Call before the app tears down.

        Qt aborts the process if a QThread is destroyed while running, so a
        clean exit must join them rather than hope. A run that ignores
        SIGTERM gets SIGKILL; a reference is dropped only for a thread that
        has actually finished. Returns True when none is left running.
        """
        runs = list(cls._LIVE)
        for run in runs:
            try:
                run.cancel()
            except Exception:                          # noqa: BLE001
                pass
        for run in runs:
            try:
                if not run.wait(timeout_ms):
                    run._signal_group(9)
                    run.wait(timeout_ms)
            except Exception:                          # noqa: BLE001
                pass
        for run in runs:
            try:
                if not run.isRunning():
                    cls._LIVE.discard(run)
            except RuntimeError:        # wrapper already deleted
                cls._LIVE.discard(run)
        return not any(r.isRunning() for r in cls._LIVE)

    @property
    def session_id(self):
        return self._session


def short_error(content, limit=90):
    """R201: one short line for a failed tool result's content - a string
    or a list of text blocks. The CLI wraps it in <tool_use_error> and puts
    the error type on a line of its own ("InputValidationError: Write failed
    due to the following issue:" / "The required parameter `file_path` is
    missing"): that becomes "InputValidationError: The required parameter
    `file_path` is missing". Never raises."""
    import re
    try:
        if isinstance(content, list):
            content = "\n".join(
                b.get("text") for b in content
                if isinstance(b, dict) and isinstance(b.get("text"), str))
        text = re.sub(r"</?tool_use_error>", "", str(content or ""))
        lines = [" ".join(ln.split()) for ln in text.splitlines()]
        lines = [ln for ln in lines if ln]
        if not lines:
            return "error"
        head = lines[0]
        if head.endswith(":") and len(lines) > 1:
            m = re.match(r"([A-Za-z_]\w*(?:Error|Exception))\b", head)
            head = ("%s: %s" % (m.group(1), lines[1])) if m else lines[1]
    except Exception:                                  # noqa: BLE001
        return "error"
    return head if len(head) <= limit else head[:limit - 1] + "…"


#: R216: the text of a permission refusal. MEASURED 2026-09-25 (claude
#: 2.1.232, the agent argv, a Read outside the one --add-dir): the tool
#: result is is_error with "Claude requested permissions to read from
#: <path>, but you haven't granted it yet.", and the `user` record carries
#: tool_result_meta [{"id": <tool_use_id>, "non_execution_kind":
#: "user-rejected"}]; the result record lists it in permission_denials.
_REFUSAL_MARKS = ("requested permissions", "haven't granted",
                  "have not granted")


def _result_text(content):
    if isinstance(content, list):
        return "\n".join(b.get("text") for b in content
                         if isinstance(b, dict) and
                         isinstance(b.get("text"), str))
    return str(content or "")


def is_refusal(content):
    """R216: True when a failed tool result is a permission refusal (the
    call never ran), not an error of the call itself. Never raises."""
    try:
        low = _result_text(content).lower()
    except Exception:                                  # noqa: BLE001
        return False
    return any(m in low for m in _REFUSAL_MARKS)


def short_refusal(content, limit=90):
    """R216: one short line for a refused call: "no permission to read
    from atech_geom.py (outside this chat's folder)", or "no permission
    to use Bash" when no path is named. A path is named by its basename
    (the full one is in the Report view). Never raises."""
    import re
    try:
        text = " ".join(_result_text(content).split())
        m = re.search(r"requested permissions? to (.+?),? but you "
                      r"(?:haven't|have not) granted", text)
        what = m.group(1) if m else ""

        paths = []

        def base(mm):
            paths.append(mm.group(0))
            return os.path.basename(mm.group(0).rstrip("/")) or mm.group(0)
        what = re.sub(r"/[^\s,]+", base, what).strip()
        # Only a refusal that names a path is about the chat's folder; a
        # tool or command off the allowlist ("to use Bash") is not, and a
        # refusal with no text says nothing about why.
        out = "no permission to %s" % what if what else "no permission"
        if paths:
            out += " (outside this chat's folder)"
    except Exception:                                  # noqa: BLE001
        return "no permission"
    return out if len(out) <= limit else out[:limit - 1] + "…"


def _summarise(obj, limit=90):
    """One short line describing a tool's input. Never raises."""
    if obj is None:
        return ""
    try:
        if isinstance(obj, dict):
            for key in ("command", "file_path", "pattern", "path", "prompt"):
                if key in obj and isinstance(obj[key], str):
                    s = obj[key]
                    # A file is named by its basename in a one-line summary;
                    # the full path (often with spaces, e.g. "Atech Atelier")
                    # truncates to noise.
                    if key in ("file_path", "path"):
                        s = os.path.basename(s.rstrip("/")) or s
                    break
            else:
                s = json.dumps(obj, sort_keys=True)
        else:
            s = str(obj)
    except Exception:
        return ""
    s = " ".join(s.split())
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"
