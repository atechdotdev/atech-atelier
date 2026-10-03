"""engine — which agent drives the conversation.

TWO AXES, DELIBERATELY SEPARATE
    settings.py already has a `provider` (anthropic / openai / openrouter /
    opencode-zen). That is *which LLM vendor an API key belongs to*. It is NOT
    the same question as *what runs the agent loop*, and conflating them is how
    a settings dialog ends up offering "Anthropic" and "Claude Code" as if they
    were alternatives at the same level.

    ENGINE   how the agent runs        transport
    ------   --------------------      ---------------------------------
    claude   the local `claude` CLI    subprocess, NDJSON on stdout
    opencode a running opencode serve  HTTP on 127.0.0.1:4096
    api      a provider API directly   HTTPS with a token from settings

    PROVIDER (anthropic/openai/...) only applies to `opencode` and `api`.
    `claude` carries its own auth and ignores it — that is the point of it.

WHY THIS EXISTS
    The opencode path needs a separate server process to be running, adopted
    or spawned; when it is not, the panel reports a dropped connection. The
    claude path has no port at all. Users should be able to pick, and the
    reason each one is or is not available should be visible rather than
    inferred from an error.

HONESTY RULE
    available() answers with a measured fact, never a guess: `claude` is a
    real executable on disk; `opencode` is a socket that actually accepts.
    An engine that cannot run says why, in words a user can act on.
"""
import os
import socket

from . import settings


CLAUDE = "claude"
OPENCODE = "opencode"
API = "api"

ENGINES = (
    (CLAUDE, "Claude Code",
     "Runs the local `claude` CLI. No server, no port, no API key — it uses "
     "your existing Claude Code login."),
    (OPENCODE, "OpenCode (local server)",
     "Talks to `opencode serve` over HTTP on 127.0.0.1:4096. Needs that "
     "process running, and an API key for the chosen provider."),
    (API, "Provider API (token)",
     "Calls a provider's API directly with a token you supply. No local "
     "process."),
)

DEFAULT = CLAUDE

_KEY = "engine"

#: R24 (needs_user_decision - which engines the public build offers). The
#: API engine has no implementation of its own (it routes to the opencode
#: client) and OpenCode needs a local server the public does not have. They
#: stay in the code, offered only when Studio is started with
#: ATECH_DEV_ENGINES=1. Removing them is the owner's call.
DEV_ENV = "ATECH_DEV_ENGINES"


def dev_engines():
    """True when the developer engines are offered (ATECH_DEV_ENGINES=1)."""
    return os.environ.get(DEV_ENV, "").strip() == "1"


def offered():
    """The engines this build offers: all three with ATECH_DEV_ENGINES=1,
    else Claude Code only. Same (id, title, description) rows as ENGINES."""
    if dev_engines():
        return ENGINES
    return tuple(e for e in ENGINES if e[0] == CLAUDE)


def current():
    """The selected engine, falling back to the default for unknown values
    and for an engine this build does not offer (a settings.json written
    by a dev build keeps working, on Claude Code)."""
    name = (settings.load().get(_KEY) or DEFAULT)
    # A hand-edited settings.json can hold any JSON value; a list is
    # unhashable and would raise in the set test below.
    if not isinstance(name, str):
        return DEFAULT
    return name if name in {e[0] for e in offered()} else DEFAULT


def select(name):
    """Store the engine choice. Any known engine may be stored; current()
    reads back only one this build offers."""
    if name not in {e[0] for e in ENGINES}:
        raise ValueError("unknown engine %r (choices: %s)"
                         % (name, ", ".join(e[0] for e in ENGINES)))
    cfg = settings.load()
    cfg[_KEY] = name
    settings.save(cfg)
    return name


def label(name):
    for key, title, _ in ENGINES:
        if key == name:
            return title
    return name


def uses_provider(name=None):
    """Whether the provider/API-key settings apply to this engine."""
    return (name or current()) in (OPENCODE, API)


# ------------------------------------------------------------- availability
def _port_open(host, port, timeout=0.4):
    """Ask the kernel, never `ss | grep`.

    backend.py states the reason and it is worth repeating: in `ss` output
    4096 is also a common Send-Q value, so a grep reports a free port as busy.
    connect_ex asks the real question.
    """
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def available(name=None):
    """(ok, reason). reason is empty when ok, else actionable text."""
    name = name or current()
    if name == CLAUDE:
        from . import claude_cli
        exe = claude_cli.find_claude()
        if exe:
            return True, ""
        if claude_cli.configured_path():
            return False, ("there is no program at the Claude Code path set "
                           "in Agent Settings (%s)."
                           % claude_cli.configured_path())
        return False, ("Claude Code is not installed, or not where Atech "
                       "Atelier looks. Install it with\n    %s\nthen run "
                       "`%s` in a terminal to sign in. Instructions: "
                       "%s. If it is installed somewhere else, set its path "
                       "in Agent Settings."
                       % (claude_cli.INSTALL_COMMAND, claude_cli.LOGIN_COMMAND,
                          claude_cli.INSTALL_URL))
    if name == OPENCODE:
        cfg = settings.load()
        url = cfg.get("backend_url") or "http://127.0.0.1:4096"
        host, port = _split(url)
        if _port_open(host, port):
            return True, ""
        return False, ("nothing is listening on %s:%d — start `opencode serve` "
                       "or choose another engine." % (host, port))
    if name == API:
        # We can see whether a key was configured; we cannot see whether it
        # is valid without spending a call, so we do not claim that it is.
        cfg = settings.load()
        if cfg.get("api_key_set"):
            return True, ""
        return False, ("no API token is configured for %s — set one in Agent "
                       "Settings." % (cfg.get("provider") or "the provider"))
    return False, "unknown engine %r" % name


def _split(url):
    rest = url.split("://", 1)[-1]
    hostport = rest.split("/", 1)[0]
    if ":" in hostport:
        host, _, p = hostport.partition(":")
        try:
            return host, int(p)
        except ValueError:
            return host, 4096
    return hostport, 4096


def status_line():
    """One line for the UI: engine, and whether it can actually run."""
    name = current()
    ok, why = available(name)
    if ok:
        extra = ""
        if name == CLAUDE:
            from . import claude_cli
            v = claude_cli.version()
            if v:
                extra = " %s" % v.split()[0]
        return "%s%s — ready" % (label(name), extra)
    return "%s — unavailable: %s" % (label(name), why)
