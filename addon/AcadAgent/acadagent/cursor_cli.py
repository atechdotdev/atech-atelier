"""cursor_cli — drive the local Cursor CLI (`cursor-agent`) as the chat engine.

The same job as claude_cli for Claude Code, through the same signals
(CursorRun is a ClaudeRun), so the panel drives either one unchanged. (R870)

STATUS: PREVIEW. Written from Cursor's documentation (cursor.com/docs/cli,
read 2026-11-07), NOT measured against a running CLI: none was installed
or signed in on the development machine. Every place below that relies on
an undocumented detail says so and fails safe (a turn that fails with
the CLI's own words, never one that silently does something else).

DOCUMENTED WIRE FORMAT (docs/cli/reference/output-format)
    cursor-agent --print --output-format stream-json
                 [--stream-partial-output] "<prompt>"
    one JSON object per line:
      {"type":"system","subtype":"init","session_id":..,"model":..,
       "cwd":..,"permissionMode":..,"apiKeySource":..}
      {"type":"user","message":{...}}                   the prompt, echoed
      {"type":"assistant","message":{"content":[{"type":"text",
       "text":..}]}}  with --stream-partial-output, three kinds:
          timestamp_ms present, model_call_id absent  a text delta
          both present                                the message so far,
                                                      flushed before a tool
          both absent                                 the final message
      {"type":"tool_call","subtype":"started"|"completed","call_id":..,
       "tool_call":{"readToolCall":{"args":{"path":..},
                    "result":{"success":{..}}}}}       (also writeToolCall;
                    other tools may be {"function":{"name","arguments"}})
      {"type":"result","subtype":"success","is_error":false,
       "duration_ms":..,"result":"<final text>","session_id":..}
    On failure "the stream may end early without a terminal event"; the
    error is on stderr.

THE PROMPT IS AN ARGUMENT
    The docs show no stdin prompt, so it is the last argv entry. It is
    readable in the process list (claude_cli R35 avoids that with stdin;
    no documented way exists here) and it never starts with "-" (it would
    be read as an option). Cursor has no system-prompt flag: Atelier's
    instructions go in front of the request. Past agent_cli.ARG_LIMIT the
    whole text goes in a private file in the chat folder that the prompt
    points the agent to.

PERMISSIONS AND SANDBOX
    No --force: Cursor's run modes document "Run Everything" (every call
    runs automatically) with the sandbox OFF. Instead:
      --sandbox enabled    shell commands run in Cursor's sandbox (macOS
                           Seatbelt; workspace read/write, no network,
                           `.cursor/*.json` protected). The docs say the
                           sandbox setting persists across sessions, so
                           this may also turn it on for the user's own
                           Cursor CLI sessions.
      <ws>/.cursor/cli.json  project permissions, rewritten every turn:
                           Read(**) and Write(**) (paths are scoped to the
                           chat folder) for a chat turn; Read(**) only for
                           a view question, which also runs --mode ask.
      --trust              the chat folder is trusted without a prompt
                           (headless only).
    ./check runs through check_broker (Cursor's sandbox is Seatbelt too,
    and Seatbelt does not nest).
    NOT isolated: the Cursor CLI loads the user's own MCP servers
    (~/.cursor/mcp.json) and rules; no flag turns that off. Atelier does
    not pass --approve-mcps.
"""
import json
import os

from . import agent_cli
from . import claude_cli
from .claude_cli import ClaudeRun, _summarise

PRODUCT = "Cursor"
VENDOR = "Cursor"
PATH_KEY = "cursor_path"
MODEL_KEY = "cursor_model"
HAS_EFFORT = False
HAS_BUDGET = False
LOGIN_ARGS = ("login",)
LOGIN_COMMAND = "cursor-agent login"
INSTALL_COMMAND = "curl https://cursor.com/install -fsS | bash"
INSTALL_URL = "https://cursor.com/docs/cli/installation"

#: The installer links ~/.local/bin/cursor-agent (and ~/.local/bin/agent,
#: a name too generic to trust on PATH) to its versioned copy.
LOCATOR = agent_cli.Locator(
    ("cursor-agent",), PATH_KEY,
    known=("~/.local/bin/cursor-agent", "/opt/homebrew/bin/cursor-agent",
           "/usr/local/bin/cursor-agent", "/usr/bin/cursor-agent"))

PERMISSIONS_DIR = ".cursor"
PERMISSIONS_FILE = "cli.json"
PROMPT_FILE = ".atech-prompt.md"


def configured_path():
    return LOCATOR.configured_path()


def find(explicit=None):
    return LOCATOR.find(explicit)


def locate(timeout=8):
    return LOCATOR.locate(timeout)


def available():
    return find() is not None


def version(timeout=10):
    return agent_cli.version(find(), timeout)


def help_flags(exe=None, timeout=10):
    """The long options `cursor-agent --help` lists (cached)."""
    return agent_cli.help_flags(exe or find(), ("--help",), timeout)


def warm(exe):
    help_flags(exe)


#: `cursor-agent status` wording is not documented: only these clear
#: phrases are read; anything else is "could not tell" (None).
_SIGNED_OUT = ("not logged in", "not authenticated", "logged out",
               "not signed in")
_SIGNED_IN = ("logged in as", "authenticated as", "signed in as")


def auth_status(timeout=15):
    """(logged_in, detail) from `cursor-agent status`, or (None, reason).
    Starts a process: call from a worker."""
    import subprocess
    exe = find()
    if exe is None:
        return None, "not found"
    try:
        out = subprocess.run([exe, "status"], capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             env=agent_cli.child_env())
    except Exception as exc:                           # noqa: BLE001
        return None, "%s" % (exc,)
    text = ("%s\n%s" % (out.stdout or "", out.stderr or "")).strip()
    low = text.lower()
    if any(m in low for m in _SIGNED_OUT):
        if os.environ.get("CURSOR_API_KEY"):
            return None, "an API key is set in the environment"
        return False, text[:300]
    if any(m in low for m in _SIGNED_IN):
        return True, text.splitlines()[0][:120]
    return None, "unrecognised status"


def agent_settings(cfg=None):
    if cfg is None:
        try:
            from . import settings
            cfg = settings.load()
        except Exception:                              # noqa: BLE001
            cfg = {}
    model = cfg.get(MODEL_KEY)
    return {"model": model.strip() if isinstance(model, str) and
            model.strip() else None, "effort": None, "budget": None}


def agent_kwargs(ws, view=False, cfg=None):
    return dict(agent_settings(cfg), ws=ws)


def permissions(writes):
    """The project permissions of a turn (<ws>/.cursor/cli.json)."""
    allow = ["Read(**)"] + (["Write(**)"] if writes else [])
    return {"permissions": {"allow": allow,
                            "deny": ["Write(.cursor/**)"]}}


#: Tool-call keys -> the names the card shows (only readToolCall and
#: writeToolCall are documented; the rest follow the same pattern).
_TOOL_NAMES = {"read": "Read", "write": "Write", "edit": "Edit",
               "delete": "Delete", "shell": "Shell", "grep": "Grep",
               "glob": "Glob", "ls": "List", "todo": "Todo"}

WRITE_MODES = ("acceptEdits", "auto", "dontAsk", "bypassPermissions")


def tool_of(tool_call):
    """(name, args dict, result) of a tool_call object. Never raises."""
    if not isinstance(tool_call, dict) or not tool_call:
        return "tool", {}, None
    key = next(iter(tool_call))
    body = tool_call.get(key)
    body = body if isinstance(body, dict) else {}
    if key == "function":
        name = str(body.get("name") or "tool")
        args = body.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {"arguments": args}
        return name, args if isinstance(args, dict) else {}, \
            body.get("result")
    base = key[:-len("ToolCall")] if key.endswith("ToolCall") else key
    name = _TOOL_NAMES.get(base, base[:1].upper() + base[1:])
    args = body.get("args")
    return name, args if isinstance(args, dict) else {}, body.get("result")


def _first_text(obj):
    """A short message out of an error/rejection value."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for k in ("message", "error", "reason", "stderr", "output"):
            v = obj.get(k)
            if isinstance(v, str) and v.strip():
                return v
    return ""


def judge_result(result):
    """("ok"|"refused"|"failed", reason) for a completed tool's result.
    Only "success" is documented; a missing result counts as ok."""
    if not isinstance(result, dict):
        return "ok", ""
    succ = result.get("success")
    if "success" in result and not isinstance(succ, dict):
        return "ok", ""
    if isinstance(succ, dict):
        code = succ.get("exitCode", succ.get("exit_code"))
        if isinstance(code, int) and code != 0:
            out = "%s\n%s" % (succ.get("stdout") or "",
                              succ.get("stderr") or "")
            last = [ln.strip() for ln in out.splitlines() if ln.strip()]
            return "failed", ("exit code %d%s" % (
                code, (": " + last[-1]) if last else ""))
        return "ok", ""
    for k in ("rejected", "permissionDenied", "denied"):
        if k in result:
            return "refused", (_first_text(result[k]) or "not permitted")
    for k in ("error", "failure", "failed"):
        if k in result:
            return "failed", (_first_text(result[k]) or "failed")
    return "ok", ""


def _short(text, limit=90):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


class CursorRun(ClaudeRun):
    """One `cursor-agent --print` turn, streamed, with ClaudeRun's
    signals."""

    PRODUCT = PRODUCT
    EXE_NAME = "cursor-agent"
    ISOLATION_FLAGS = ("--sandbox",)

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._broker = None
        self._prompt_file = None

    def _writes(self):
        return self._permission_mode in WRITE_MODES

    def _argv(self):
        exe = find()
        if exe is None:
            raise RuntimeError("the Cursor CLI (`cursor-agent`) was not "
                               "found on this system")
        have = help_flags(exe)
        if "--output-format" not in have:
            raise RuntimeError("this Cursor CLI does not list "
                               "--output-format; update it with "
                               "`cursor-agent update`.")
        if not self._writes() and "--mode" not in have:
            raise RuntimeError("this Cursor CLI has no --mode, so a "
                               "read-only question cannot be asked; update "
                               "it with `cursor-agent update`.")
        out = [exe, "--print", "--output-format", "stream-json"]

        def want(flag, *values):
            if flag in have:
                out.extend((flag,) + values)
                return True
            self.dropped.append(flag)
            return False

        want("--stream-partial-output")
        want("--trust")
        out += ["--workspace", self._cwd]
        want("--sandbox", "enabled")
        if not self._writes():
            out += ["--mode", "ask"]
        agent = self._agent or {}
        model = self._model or agent.get("model")
        if model:
            out += ["--model", str(model)]
        if self._session:
            # The = form: --resume takes an OPTIONAL value, so a separate
            # word could be read as the prompt.
            out.append("--resume=%s" % self._session)
        out += self._extra
        out.append(self._prompt_arg())
        return out

    def _prompt_arg(self):
        """The prompt argument: Atelier's instructions, then the request.
        Never starts with "-"; past ARG_LIMIT it lives in a 0600 file in
        the chat folder (removed when the turn ends)."""
        text = self._compose_prompt()
        if self._system_prompt:
            text = ("<atelier_instructions>\n%s\n</atelier_instructions>"
                    "\n\n%s" % (self._system_prompt, text))
        if agent_cli.fits_argv(text):
            return ("Request:\n" + text) if text.startswith("-") else text
        path = os.path.join(self._cwd, PROMPT_FILE)
        try:
            os.unlink(path)
        except OSError:
            pass
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self._prompt_file = path
        return ("Your instructions and the request are in the file %s in "
                "this folder. Read all of it first, then do what it says."
                % PROMPT_FILE)

    def flags(self):
        """The argv with the prompt elided, for a log line."""
        if self.argv is None:
            return None
        return self.argv[:-1] + ["<prompt: %d chars>" % len(self.argv[-1])]

    def prompt_text(self):
        return self.argv[-1] if self.argv else self._compose_prompt()

    def _write_permissions(self):
        d = os.path.join(self._cwd, PERMISSIONS_DIR)
        if os.path.islink(d):
            os.unlink(d)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, PERMISSIONS_FILE)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(permissions(self._writes()), fh, indent=2)
        os.replace(tmp, path)

    def _reap(self):
        broker, self._broker = self._broker, None
        if broker is not None:
            broker.stop()
        super()._reap()
        if self._prompt_file:
            try:
                os.unlink(self._prompt_file)
            except OSError:
                pass
            self._prompt_file = None

    def _run(self):
        try:
            self._write_permissions()
            argv = self._argv()
        except RuntimeError as exc:
            return ("failed", str(exc))
        except OSError as exc:
            return ("failed", "could not prepare the Cursor run: %s" % exc)
        self.argv = argv
        if self._cancelled:
            return ("failed", "cancelled")
        import time
        t0 = time.monotonic()
        env = claude_cli.turn_env()
        if self._writes():
            from . import check_broker
            broker = check_broker.Broker(self._cwd, env)
            if broker.start():
                self._broker = broker
        failed = self._spawn(argv, "", env)
        if failed is not None:
            return failed

        record, saw_result = {}, False
        buf = ""
        calls = {}
        for line in self._proc.stdout:
            if self._cancelled:
                break
            if self._emitted:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            if kind == "system" and msg.get("subtype") == "init":
                self.timings.setdefault("init", time.monotonic() - t0)
                sid = msg.get("session_id")
                if sid and isinstance(sid, str):
                    self._session = sid
                    self.started_session.emit(sid)
                self._activity("model")
            elif kind == "assistant":
                text = _message_text(msg.get("message"))
                if "timestamp_ms" in msg and "model_call_id" not in msg:
                    buf += text                 # a streamed delta
                    self._set_open(True)
                    if buf:
                        self.delta.emit(buf)
                else:
                    # A whole message: flushed before a tool call, the
                    # final flush, or (no partial output) the message.
                    buf = ""
                    if text:
                        self.text.emit(text)
                self._activity("model")
            elif kind == "tool_call":
                self._tool_event(msg, calls)
            elif kind == "result":
                self._set_open(False)
                saw_result = True
                record = msg
                self.timings["result"] = time.monotonic() - t0
                if not record.get("is_error") and record.get("subtype") in (
                        None, "success") and not self._cancelled:
                    self._emit(self._judge(record, True, 0, "", 0, ""))
                    self._arm_exit_watchdog()
            else:
                self._activity("model")

        code = self._proc.wait()
        self.timings["exit"] = time.monotonic() - t0
        err = self._stderr_tail()
        if self._emitted:
            return None
        if self._cancelled:
            return ("failed", "cancelled")
        if saw_result:
            return self._judge(record, True, 0, "", code, err)
        return ("failed", "cursor-agent exited %s without a result%s"
                % (code, (": " + err) if err else ""))

    def _tool_event(self, msg, calls):
        name, args, result = tool_of(msg.get("tool_call"))
        cid = msg.get("call_id")
        if msg.get("subtype") == "started":
            arg = _summarise(args)
            calls[cid] = (name, arg)
            self._set_open(False)
            self.tool.emit(name, arg)
            self._activity("tool", ("%s %s" % (name, arg)).strip())
            return
        if msg.get("subtype") != "completed":
            self._activity("model")
            return
        if cid not in calls:
            calls[cid] = (name, _summarise(args))
            self.tool.emit(*calls[cid])
        name, arg = calls[cid]
        verdict, why = judge_result(result)
        if verdict == "refused":
            self.tool_refused.emit(name, arg, _short(why))
            self._activity("failed", ("%s %s" % (name, arg)).strip())
        elif verdict == "failed":
            self.tool_failed.emit(name, arg, _short(why))
            self._activity("failed", ("%s %s" % (name, arg)).strip())
        else:
            self._activity("model")
        self._set_open(True)


def _message_text(message):
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "".join(b.get("text") for b in content or ()
                   if isinstance(b, dict) and b.get("type") == "text" and
                   isinstance(b.get("text"), str))


Run = CursorRun
