"""codex_cli — drive the local `codex` CLI (OpenAI Codex) as the chat engine.

The same job as claude_cli for Claude Code, through the same signals
(CodexRun is a ClaudeRun: process group, Stop, reaping and the parent-death
tie are shared), so the panel drives either one unchanged. (R870)

MEASURED WIRE FORMAT (codex-cli 0.162.1, 2026-11-07; the success paths
against a local stand-in for the Responses API, the signed-out path live)
    codex exec --json [options] -          the prompt is read from stdin
    codex exec --json [options] resume <thread_id> -
        every option goes BEFORE `resume` (measured: --sandbox read-only
        given there held on the resumed turn)
    emits one JSON object per line:
      {"type":"thread.started","thread_id":"<uuid>"}   the session id
      {"type":"turn.started"}
      {"type":"item.started"|"item.completed","item":{"id":..,"type":..}}
        agent_message {text}; reasoning {text};
        command_execution {command:"/bin/zsh -lc ./check",
            aggregated_output, exit_code, status: in_progress|completed|
            failed|declined};
        file_change {changes:[{path, kind: add|update|delete}], status};
        mcp_tool_call, web_search, todo_list; error {message} (a warning:
        "Model metadata for `x` not found ...")
      {"type":"error","message":"Reconnecting... 2/5 (...)"}   a retry
      {"type":"turn.completed","usage":{input_tokens, cached_input_tokens,
                                        output_tokens, ...}}
      {"type":"turn.failed","error":{"message":"unexpected status 401
                                     Unauthorized: ..."}}     (exit 1)

ISOLATION (the R78 promise, as far as Codex can keep it)
    --ignore-user-config     none of ~/.codex/config.toml (the user's MCP
                             servers, profiles, providers); auth still works
    --ignore-rules           none of the user's execpolicy .rules
    --disable <feature>      apps, plugins, hooks, multi_agent, browser and
                             computer use, image generation, goals - only
                             those `codex features list` names: an unknown
                             name fails the run ("Unknown feature flag")
    -c web_search="disabled", -c skills.include_instructions=false
    With these the model is offered exec_command, write_stdin,
    request_user_input, apply_patch and view_image only (measured).

    --sandbox workspace-write for a chat turn: Codex's own sandbox. Writes
    only in the chat folder (and the temp folders); no network; `.codex`
    in it is read-only. Reads are NOT confined to the chat folder -
    measured: `cat ~/.zshrc` worked - which Claude Code's --add-dir does
    confine. --sandbox read-only for a view question (measured: a write
    is refused). approval_policy="never": nothing ever asks, and an
    escalation request is refused.

    ./check runs through check_broker (see there for why it cannot run
    inside Codex's sandbox).

THE SYSTEM PROMPT
    -c developer_instructions="<TOML string>" (measured: it arrives as a
    developer message after Codex's own). An argument, so it is readable in
    the process list like any argv; it holds Atelier's instructions, never
    what the user typed (that goes on stdin, R35). Longer than
    agent_cli.ARG_LIMIT, it is put in front of the prompt on stdin instead.
"""
import json
import os
import re
import shlex
import subprocess

from . import agent_cli
from . import claude_cli
from .claude_cli import ClaudeRun, _summarise

PRODUCT = "Codex"
VENDOR = "OpenAI"
PATH_KEY = "codex_path"
MODEL_KEY = "codex_model"
HAS_EFFORT = True
HAS_BUDGET = False
#: `codex login` signs in from a terminal (browser or device code).
LOGIN_ARGS = ("login",)
LOGIN_COMMAND = "codex login"
INSTALL_COMMAND = "npm install -g @openai/codex"
INSTALL_URL = "https://github.com/openai/codex"

LOCATOR = agent_cli.Locator(
    ("codex",), PATH_KEY,
    known=("~/.local/bin/codex", "~/.npm-global/bin/codex",
           "~/.bun/bin/codex", "~/.volta/bin/codex",
           "~/.local/share/pnpm/codex", "~/Library/pnpm/codex",
           "~/.yarn/bin/codex", "/opt/homebrew/bin/codex",
           "/usr/local/bin/codex", "/usr/bin/codex"),
    nvm="~/.nvm/versions/node/*/bin/codex")

#: Features turned off for the chat agent, when this Codex has them.
DISABLE_FEATURES = ("apps", "plugins", "hooks", "multi_agent",
                    "image_generation", "browser_use", "computer_use",
                    "in_app_browser", "goals")
#: Model reasoning effort levels (`codex debug models`, 0.162.1: low ..
#: max; not every model has every level).
EFFORTS = ("low", "medium", "high", "xhigh", "max")


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


def auth_status(timeout=15):
    """(logged_in, detail) from `codex login status`, or (None, reason).

    MEASURED (0.162.1): signed out it prints "Not logged in" and exits 1.
    Signed in it prints "Logged in using ..." (ChatGPT or an API key).
    A key in the environment ($CODEX_API_KEY, $OPENAI_API_KEY) may sign
    `codex exec` in without a stored login, so "Not logged in" then means
    could-not-tell. Starts a process: call from a worker."""
    exe = find()
    if exe is None:
        return None, "not found"
    try:
        out = subprocess.run([exe, "login", "status"], capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             env=agent_cli.child_env())
    except Exception as exc:                           # noqa: BLE001
        return None, "%s" % (exc,)
    text = ("%s\n%s" % (out.stdout or "", out.stderr or "")).strip()
    low = text.lower()
    if "not logged in" in low:
        if os.environ.get("CODEX_API_KEY") or os.environ.get("OPENAI_API_KEY"):
            return None, "an API key is set in the environment"
        return False, text[:300]
    if low.startswith("logged in"):
        return True, text.splitlines()[0][:120]
    return None, "unrecognised login status"


def exec_flags(exe=None, timeout=10):
    """The long options `codex exec --help` lists (cached)."""
    return agent_cli.help_flags(exe or find(), ("exec", "--help"), timeout)


_FEATURES = {}


def features(exe=None, timeout=10):
    """The feature names `codex features list` prints (first column),
    cached per program; empty when it cannot be read."""
    exe = exe or find()
    if not exe:
        return frozenset()
    if exe in _FEATURES:
        return _FEATURES[exe]
    try:
        out = subprocess.run([exe, "features", "list"], capture_output=True,
                             text=True, timeout=timeout,
                             stdin=subprocess.DEVNULL,
                             env=agent_cli.child_env())
        names = frozenset(
            ln.split()[0] for ln in (out.stdout or "").splitlines()
            if ln.strip() and re.match(r"^[a-z][a-z0-9_]*\s", ln))
    except Exception:                                  # noqa: BLE001
        names = frozenset()
    if names:
        _FEATURES[exe] = names
    return names


def warm(exe):
    """Off the GUI thread at mount: cache what the first turn asks."""
    exec_flags(exe)
    features(exe)


def agent_settings(cfg=None):
    """The model and effort of a turn: Agent Settings' Codex model, and
    the shared effort (the user's own, else the mode's default)."""
    if cfg is None:
        try:
            from . import settings
            cfg = settings.load()
        except Exception:                              # noqa: BLE001
            cfg = {}
    model = cfg.get(MODEL_KEY)
    effort = cfg.get("agent_effort")
    effort = effort.strip() if isinstance(effort, str) else ""
    if not effort and claude_cli._quality(cfg):
        effort = claude_cli._mode_effort()
    return {"model": model.strip() if isinstance(model, str) and
            model.strip() else None,
            "effort": effort or None, "budget": None}


def agent_kwargs(ws, view=False, cfg=None):
    """The `agent` argument of a turn. A view question differs only in
    its permission mode ("plan" = --sandbox read-only)."""
    return dict(agent_settings(cfg), ws=ws)


def toml_string(text):
    """`text` as a TOML basic string (JSON's escapes are a subset)."""
    return json.dumps(text, ensure_ascii=False)


def command_of(cmd):
    """'/bin/zsh -lc ./check' -> './check': the command the model asked
    for, without the shell Codex wraps it in. Never raises."""
    try:
        parts = shlex.split(cmd or "")
    except ValueError:
        return cmd or ""
    if len(parts) == 3 and parts[1] in ("-lc", "-c") and \
            os.path.basename(parts[0]) in ("sh", "bash", "zsh", "dash"):
        return parts[2]
    return cmd or ""


#: Permission modes that may write (ClaudeRun.PERMISSION_MODES); every
#: other one runs read-only.
WRITE_MODES = ("acceptEdits", "auto", "dontAsk", "bypassPermissions")


class CodexRun(ClaudeRun):
    """One `codex exec --json` turn, streamed, with ClaudeRun's signals."""

    PRODUCT = PRODUCT
    EXE_NAME = "codex"
    ISOLATION_FLAGS = ("--ignore-user-config",)

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._sp_on_stdin = False
        self._broker = None

    def _writes(self):
        return self._permission_mode in WRITE_MODES

    def _argv(self):
        exe = find()
        if exe is None:
            raise RuntimeError("the `codex` CLI was not found on this system")
        have = exec_flags(exe)
        if "--json" not in have:
            raise RuntimeError("this Codex is too old: `codex exec` has no "
                               "--json. Update Codex.")
        out = [exe, "exec", "--json"]

        def want(flag, *values):
            if flag in have:
                out.extend((flag,) + values)
                return True
            self.dropped.append(flag)
            return False

        want("--skip-git-repo-check")
        want("--ignore-user-config")
        want("--ignore-rules")
        out += ["-c", 'approval_policy="never"',
                "-c", 'web_search="disabled"',
                "-c", "skills.include_instructions=false"]
        if "--disable" in have:
            feats = features(exe)
            for f in DISABLE_FEATURES:
                if f in feats:
                    out += ["--disable", f]
        out += ["--sandbox",
                "workspace-write" if self._writes() else "read-only",
                "--cd", self._cwd]
        agent = self._agent or {}
        model = self._model or agent.get("model")
        if model:
            out += ["--model", str(model)]
        effort = agent.get("effort")
        if effort in EFFORTS:
            out += ["-c", "model_reasoning_effort=%s" % toml_string(effort)]
        elif effort:
            self.dropped.append("model_reasoning_effort %s" % effort)
        if self._system_prompt:
            arg = "developer_instructions=%s" % toml_string(
                self._system_prompt)
            if agent_cli.fits_argv(arg):
                out += ["-c", arg]
            else:
                self._sp_on_stdin = True
        # Caller-owned flags go with the others: every option must come
        # before `resume` and the `-` that reads the prompt from stdin.
        out += self._extra
        if self._session:
            out += ["resume", self._session]
        out.append("-")
        return out

    def flags(self):
        """The argv with the system prompt elided, for a log line."""
        if self.argv is None:
            return None
        return [("developer_instructions=<%d chars>" % len(a))
                if a.startswith("developer_instructions=") else a
                for a in self.argv]

    def _compose_prompt(self):
        text = super()._compose_prompt()
        if self._sp_on_stdin and self._system_prompt:
            return ("<atelier_instructions>\n%s\n</atelier_instructions>\n\n%s"
                    % (self._system_prompt, text))
        return text

    def _start_broker(self, env):
        if not self._writes():
            return
        from . import check_broker
        broker = check_broker.Broker(self._cwd, env)
        if broker.start():
            self._broker = broker

    def _reap(self):
        broker, self._broker = self._broker, None
        if broker is not None:
            broker.stop()
        super()._reap()

    def _run(self):
        try:
            argv = self._argv()
        except RuntimeError as exc:
            return ("failed", str(exc))
        except OSError as exc:
            return ("failed", "could not prepare the Codex run: %s" % exc)
        self.argv = argv
        if self._cancelled:
            return ("failed", "cancelled")
        import time
        t0 = time.monotonic()
        env = claude_cli.turn_env()
        self._start_broker(env)
        failed = self._spawn(argv, self._compose_prompt(), env)
        if failed is not None:
            return failed

        last_text, fail_msg, last_err = "", "", ""
        retries, retry_err = 0, ""
        saw_result, usage = False, {}
        started = set()
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
            item = msg.get("item") if isinstance(msg.get("item"),
                                                 dict) else {}
            if kind == "thread.started":
                self.timings.setdefault("init", time.monotonic() - t0)
                sid = msg.get("thread_id")
                if sid and isinstance(sid, str):
                    self._session = sid
                    self.started_session.emit(sid)
                self._activity("model")
            elif kind == "turn.started":
                self._set_open(True)
                self._activity("model")
            elif kind == "item.started":
                self._item_started(item, started)
            elif kind == "item.completed":
                text = self._item_completed(item, started)
                if text is not None:
                    last_text = text
            elif kind == "item.updated":
                self._activity("model")
            elif kind == "error":
                m = str(msg.get("message") or "")
                r = re.match(r"Reconnecting\.\.\.\s*(\d+)", m)
                if r:
                    retries += 1
                    retry_err = m
                    self._set_open(False)
                    self._activity("retry", r.group(1))
                else:
                    last_err = m
            elif kind == "turn.failed":
                self._set_open(False)
                err = msg.get("error")
                fail_msg = str((err or {}).get("message") or "") \
                    if isinstance(err, dict) else str(err or "")
                fail_msg = fail_msg or last_err or "Codex reported an error"
            elif kind == "turn.completed":
                self._set_open(False)
                saw_result = True
                usage = msg.get("usage") if isinstance(
                    msg.get("usage"), dict) else {}
                self.timings["result"] = time.monotonic() - t0
                if not self._cancelled:
                    self._emit(("ok", last_text, {
                        "type": "result", "subtype": "success",
                        "is_error": False, "result": last_text,
                        "session_id": self._session, "usage": usage,
                        "duration_ms": int(self.timings["result"] * 1000)}))
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
        if fail_msg:
            if retries and claude_cli.classify_failure(fail_msg) != \
                    claude_cli.AUTH:
                return ("failed", "could not reach OpenAI (retried %d "
                        "times): %s" % (retries, fail_msg))
            return ("failed", fail_msg)
        if not saw_result:
            if retries:
                return ("failed", "could not reach OpenAI (retried %d "
                        "times, last error: %s)" % (retries, retry_err))
            return ("failed", "codex exited %s without a result%s"
                    % (code, (": " + (last_err or err))
                       if (last_err or err) else ""))
        return None

    # ------------------------------------------------------------ items
    def _describe(self, item):
        """(tool name, one-line argument) for a tool item, else None."""
        t = item.get("type")
        if t == "command_execution":
            return "Shell", _summarise(
                {"command": command_of(str(item.get("command") or ""))})
        if t == "file_change":
            names = [os.path.basename(str(c.get("path") or ""))
                     for c in item.get("changes") or ()
                     if isinstance(c, dict)]
            return "Edit", _summarise(", ".join(n for n in names if n))
        if t == "mcp_tool_call":
            return ("%s.%s" % (item.get("server") or "mcp",
                               item.get("tool") or "tool")), ""
        if t == "web_search":
            return "WebSearch", _summarise(str(item.get("query") or ""))
        return None

    def _item_started(self, item, started):
        desc = self._describe(item)
        if desc is None:
            self._activity("model")
            return
        name, arg = desc
        iid = item.get("id")
        if iid is not None:
            started.add(iid)
            self._tool_ids[iid] = (name, arg)
        self._set_open(False)
        self.tool.emit(name, arg)
        self._activity("tool", ("%s %s" % (name, arg)).strip())

    def _item_completed(self, item, started):
        """Handle a finished item; the agent's text when it is a message."""
        t = item.get("type")
        if t == "agent_message":
            text = item.get("text")
            if isinstance(text, str) and text:
                self.text.emit(text)
                self._activity("model")
                return text
            return None
        desc = self._describe(item)
        if desc is None:
            if t == "error" and item.get("message"):
                _log("codex: %s" % item.get("message"))
            self._activity("model")
            return None
        iid = item.get("id")
        name, arg = self._tool_ids.get(iid, desc)
        if iid not in started:
            self.tool.emit(name, arg)       # completed without a start
        status = item.get("status")
        code = item.get("exit_code")
        if status == "declined":
            self.tool_refused.emit(name, arg,
                                   "declined by Codex's sandbox policy")
            self._activity("failed", ("%s %s" % (name, arg)).strip())
        elif status == "failed" or (isinstance(code, int) and code != 0):
            self.tool_failed.emit(name, arg, _failure(item))
            self._activity("failed", ("%s %s" % (name, arg)).strip())
        else:
            self._activity("model")
        self._set_open(True)                # the model has the turn again
        return None


def _failure(item):
    """One short line for a failed tool item."""
    code = item.get("exit_code")
    out = str(item.get("aggregated_output") or "")
    err = item.get("error")
    if isinstance(err, dict) and err.get("message"):
        out = str(err["message"])
    last = [ln.strip() for ln in out.splitlines() if ln.strip()]
    head = ("exit code %s" % code) if isinstance(code, int) else "failed"
    text = "%s: %s" % (head, last[-1]) if last else head
    return text if len(text) <= 90 else text[:89] + "…"


def _log(msg):
    line = "[agent] %s\n" % msg
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog(line)
    except Exception:                                  # noqa: BLE001
        import sys
        sys.stderr.write(line)


Run = CodexRun
