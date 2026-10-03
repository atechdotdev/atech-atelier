#!/usr/bin/env python3
"""run_eval - build-quality benchmark for the Atech Atelier agent.

Answers ONE question with numbers: when a user types a request into the
Studio chat, how often does real, valid, correctly-sized geometry come out,
how many fix rounds does it take, and how long does it take?

WHAT IS PRODUCTION AND WHAT IS NOT
    Production (read from the shipped code, not copied by hand):
      - system prompt: acadagent.build.system_prompt(ws), computed inside
        freecadcmd so its Atech section resolves exactly as in Studio.
      - first-turn message: "<request>\\n\\n---\\n<build.document_brief(doc)>"
      - claude argv (S15): computed by PRODUCTION code inside freecadcmd
        (fc_build.py mode "argv"), never a hand-copied list:
        claude_cli.agent_argv when it exists (S16), else
        claude_cli.ClaudeRun._argv() + panel.AgentPanel._turn_args(ws) - the
        two calls panel._send_claude makes. Computed once per prompt for that
        prompt's workspace with the message and session as placeholders;
        recorded per prompt as `argv_flags` (free text replaced by its
        length) with `argv_source`. _turn_args gets the prompt's request
        text and its (seeded) document, as panel._send_claude passes them
        (R111), so plain and Atech prompts get the system prompt and the
        ATECH_ASSEMBLY.md copy production gives them; recorded per prompt
        as `system_prompt_chars` and `atech_reference`.
        cwd = workspace; PYTHONHOME/PYTHONPATH/LD_LIBRARY_PATH stripped.
      - build: acadagent.build.apply() on a fresh document (fc_build.py).
      - fix loop (panel._on_claude_done/_run_build/_send_fix): after a turn,
        if model.py changed, build it; a failed build sends
        "The script failed when Atech Atelier ran it:\\n<err[-3000:]>" and a
        build whose build.failures() is non-empty sends "Atech Atelier built it,
        but the measurement check failed: <bad>. Each body must be one valid
        solid." - each + "\\nFix model.py and write it again." - on the same
        session (--resume), at most MAX_FIX_ATTEMPTS = 2 times. A turn that
        writes nothing is "nothing to build" and ends the request.
      - edit turn (R173): an item with "edit": {"prompt", "expect"} sends
        that prompt as the user's NEXT message on the same session once the
        first request built ("<edit>\\n\\n---\\n<document brief of that
        build>", as panel._send_claude appends the brief), with its own fix
        loop and expectations. The final score is the edit's; the first
        request's own score is `first_request`; its model.py is saved as
        model_request1.py, the edit's attempts as edit_attempt<n>.py, and
        outcomes of the edit phase carry an "edit_" prefix. The resume argv
        is the one computed for the first request (_turn_args is not re-run
        with the edit's text).
      - live preview (S46): while a turn runs, model.py is watched the way
        panel._watch_workspace / _on_ws_changed / _preview_files do: a
        change settles for PREVIEW_DEBOUNCE_S (panel.PREVIEW_DEBOUNCE_MS),
        then it is built only when its CONTENT changed (sha1) and it
        compiles (build.compiles' check), one build at a time; a change
        during a build is looked at when it ends; no preview starts after
        the turn ends (one in flight finishes). Any writer counts - Write,
        Edit or a Bash `sed -i` - since the file is watched, not the tool
        calls. Each preview builds a COPY of the workspace (fc_build's
        headless patch rewrites model.py; the agent's file is never
        touched) with production's build.apply + build.failures (job
        "preview": no expectation/fitness checks, no render).
    Not production:
      - The live preview's RESULT is not sent back to the agent: the panel
        sends a preview failure only when the agent never rewrote the file,
        which is the same file the end-of-turn build builds and reports.
        The end-of-turn build always runs (it carries the scoring checks
        and the render), even when a preview already built the same bytes.
      - A preview here is a freecadcmd child (startup + the one-at-a-time
        lock); in Studio it builds in-process. So each preview records both
        the harness time and a production estimate (see Timing).
      - Headless: GUI-only statements (ViewObject colours) are wrapped in
        try/except and re-run once; flagged headless_patched in the results.
      - The expectation checks, fitness checks and the render are the
        benchmark's own.

USAGE (system python 3; freecadcmd is found in dist/build)
    run_eval.py                       all prompts, 2 claude calls at a time
    run_eval.py --only l_bracket,mug  a subset
    run_eval.py --jobs 1              sequential claude calls
    run_eval.py --set extra           the EXTRA prompt set (prompts_extra.json);
                                      output <tag>_extra_<n>.*, so the 12-prompt
                                      core score stays comparable
    run_eval.py --rescore baseline_1  re-build the saved model_attempt1.py and
                                      final model.py of that run (no claude
                                      calls) against the CURRENT prompt files;
                                      writes baseline_1_rescore.json/.md and
                                      leaves the original run untouched.
                                      (`--rescore 1` = <tag>_1, as before.)
    run_eval.py --rescore round_2 --addon-rev 3afafe0
                                      ... built against that addon revision
                                      (S41). Default `run`: the revision the
                                      run recorded (commit + its addon.diff +
                                      untracked files); `current`: this tree.
                                      The report states the run's revision and
                                      the one rescored against.
    run_eval.py --tag round --n 1     write round_1.* instead of baseline_<n>.*

Addon revision (S41): every run records meta.addon = {commit, dirty,
sha256 of the addon's files, untracked} and, when the addon differs from
the commit, <run>/addon.diff (git diff HEAD) and <run>/addon_untracked/,
so --rescore can rebuild the saved model.py files against the addon that
wrote them: saved scripts call the kit API of their day (round_2 unpacks
the pre-S28 `fillet_safe` tuple). R150: the rebuilt tree also carries
<repo>/projects/ (atech_ports.py, atech_modules.py) at that revision -
without it every Atech prompt failed with ModuleNotFoundError - and the
build is pointed at the live atech-artifacts meshes (ATECH_ARTIFACTS, not
revisioned; the report says so). Runs from R150 on record projects/'s
uncommitted changes in addon.diff / addon_untracked too.

Output: docs/verification/eval/<tag>_<n>.md, <tag>_<n>.json and
<tag>_<n>/<id>/{model.py, render.png, transcript.txt}  (tag defaults to "baseline").

Recorded per prompt (S15): first_apply_pass (the first model.py built with
no measurement failure), check_calls (in-turn `./check` Bash calls), init_s
and first_text_s of the first turn (seconds from spawn to the stream's
init record / first assistant text), wall_s, cost_usd, input_tokens
(input + cache creation + cache read, all turns), output_tokens (all turns;
S32 - older runs: summed from each turn's saved usage), permission_denials,
fitness checks (fc_build.py) and fit_pass, and `atech` (S35: the prompt runs
atech_check). The report gives plain and Atech pass rates separately.
S46: `previews` (every live preview: turn, sha1, settled/start/done seconds
from the request, build.apply seconds, ok, failures, error tail) and
`denials` (every permission denial: tool, command or file, and whether the
denied command runs `./check` - then that check never ran), reported per
command. S57: each turn's `timeline` (init, API retries with backoff,
message start/stop with output tokens, silences inside a stream, tool calls
and results, result - seconds from spawn) and `stalls`: every gap of
STALL_GAP_S s or more with no tool activity, split into retries / slow first
event / stream stall / model / tool / startup / unattributed seconds (see
stall_segments); reported as a section, a headline row and a per-prompt
column. Runs saved before S57 say "not measured".

transcript.txt (S32) holds, per turn, the message sent, every tool call AND
its result in stream order (`-> [id] Tool arg` / `<- [id] result`, results
clipped to TOOL_RESULT_CHARS), the assistant text and the final answer.

Timing (per request, seconds from the request being sent):
    first_write_s     the first Write/Edit tool call on model.py in the stream.
                      Studio's live preview builds at that moment, so this is
                      the LOWER bound of production time-to-first-preview.
    first_ok_build_s  end of the first END-OF-TURN build that succeeded with no
                      measurement failure (the upper bound of time-to-preview).
    first_preview_s   end of the first live preview (S46) that built with no
                      measurement failure, as the harness ran it (freecadcmd
                      startup and lock wait included).
    first_preview_prod_s  the same preview as production would show it: the
                      moment its model.py content settled + the debounce +
                      build.apply's own seconds (no process startup, no lock).
                      None when no live preview built cleanly.
    wall_s            request -> final answer (all fix rounds included).

freecadcmd runs at most ONE at a time (a lock), per the repo rule.
"""
import argparse
import ast
import concurrent.futures as cf
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.normpath(os.path.join(HERE, "..", ".."))
REPO = os.path.normpath(os.path.join(ADDON, "..", ".."))
FREECADCMD = os.environ.get(
    "FREECADCMD", os.path.join(REPO, "dist", "build", "squashfs-root", "usr", "bin", "freecadcmd"))
FC_BUILD = os.path.join(HERE, "fc_build.py")
PROMPT_SETS = {"core": "prompts.json", "extra": "prompts_extra.json"}
OUT_DIR = os.path.join(REPO, "docs", "verification", "eval")
# R150: the Atech builders (atech_ports.py, atech_modules.py) live in
# <repo>/projects, found by acadagent.projects from the addon at ../../projects;
# a materialized addon tree carries them at the same revision.
PROJECTS_REL = "projects"
# The meshes they measure live in the atech-artifacts checkout (not in this
# repo, so not revisioned); a materialized tree is pointed at the live one.
LIBRARY_ENV = "ATECH_ARTIFACTS"
LIBRARY_MARKER = "presets.yaml"

MAX_FIX_ATTEMPTS = 2           # panel.AcadPanel.MAX_FIX_ATTEMPTS
TURN_TIMEOUT_S = 900
FC_TIMEOUT_S = 300
PREVIEW_DEBOUNCE_S = 0.4      # panel.AgentPanel.PREVIEW_DEBOUNCE_MS / 1000
PREVIEW_POLL_S = 0.05
_FC_LOCK = threading.Lock()
_PRINT = threading.Lock()
PLACEHOLDER = "/__EVAL_WORKSPACE_PLACEHOLDER__"
MSG_PH = "__EVAL_MESSAGE_PLACEHOLDER__"
SID_PH = "__EVAL_SESSION_PLACEHOLDER__"


def log(*a):
    with _PRINT:
        print(time.strftime("%H:%M:%S"), *a, flush=True)


# ------------------------------------------------------------- freecadcmd
def fc_job(job):
    """Run fc_build.py once, serialised. Returns (payload | None, crash text)."""
    fd, jpath = tempfile.mkstemp(suffix=".json", prefix="evaljob-")
    os.close(fd)
    job = dict(job)
    job["out"] = jpath + ".out"
    with open(jpath, "w", encoding="utf-8") as fh:
        json.dump(job, fh)
    env = dict(os.environ, EVAL_JOB=jpath)
    if job.get("addon"):
        env["EVAL_ADDON"] = job["addon"]          # S41: an earlier addon tree
        # R150: projects/atech_ports.py in a temp tree cannot find the meshes
        # by its checkout rule (../../../atech-artifacts); an explicit
        # ATECH_ARTIFACTS the user set still wins.
        lib = live_library()
        if lib and not (os.environ.get(LIBRARY_ENV) or "").strip():
            env[LIBRARY_ENV] = lib
    with _FC_LOCK:
        try:
            p = subprocess.run([FREECADCMD, FC_BUILD], env=env, capture_output=True,
                               text=True, timeout=FC_TIMEOUT_S)
            out = p.stdout + p.stderr
        except subprocess.TimeoutExpired as exc:
            out = "TIMEOUT after %ss: %s" % (FC_TIMEOUT_S, (exc.stdout or "")[-500:])
    try:
        if "FC_BUILD_DONE=" in out and os.path.isfile(job["out"]):
            with open(job["out"], encoding="utf-8") as fh:
                return json.load(fh), ""
        m = re.search(r"FC_BUILD_CRASH=(.*)", out)
        return None, (m.group(1) if m else out[-2000:])
    finally:
        for f in (jpath, job["out"]):
            try:
                os.remove(f)
            except OSError:
                pass


# ------------------------------------------------------------ live preview
def _read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _sha1(data):
    return None if data is None else hashlib.sha1(data).hexdigest()


def source_compiles(data):
    """build.compiles on bytes: complete, syntactically valid Python
    (utf-8-sig, only parsed, never run)."""
    try:
        compile(data.decode("utf-8-sig"), "model.py", "exec", dont_inherit=True)
        return True
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return False


class LivePreview(object):
    """The panel's live preview, replayed for one turn (S46).

    Polls <ws>/model.py every `poll` s. A content change that then stays
    put for `debounce` s is built when its sha1 differs from the last one
    built (or the one the turn started with) and it compiles - else it is
    counted in `skipped`. One build at a time: the poll loop itself runs
    the build, so a change made meanwhile is seen when it ends. stop() lets
    a build in flight finish and starts no other. Times are seconds from
    `t_ref` (the request being sent)."""

    def __init__(self, ws, job, t_ref, turn=1, build_fn=None,
                 debounce=PREVIEW_DEBOUNCE_S, poll=PREVIEW_POLL_S, clock=time.time):
        self.ws, self.job, self.t_ref, self.turn = ws, dict(job), t_ref, turn
        self.build_fn = build_fn or fc_job
        self.debounce, self.poll, self.clock = debounce, poll, clock
        self.script = os.path.join(ws, "model.py")
        self.records, self.skipped = [], 0
        self._stop = threading.Event()
        self._thread = None
        self.stop_wait_s = 0.0      # stop() blocked on a preview in flight
        self._built = _sha1(_read_bytes(self.script))   # the turn's starting file

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        """End the turn's watch. A build in flight finishes first; the
        seconds that took are `stop_wait_s` - they delay the end-of-turn
        build, so they are in first_ok_build_s and wall_s too."""
        t0 = self.clock()
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.stop_wait_s = round(max(0.0, self.clock() - t0), 2)
        return self.records

    def _loop(self):
        seen, changed_at = self._built, None
        while not self._stop.is_set():
            data = _read_bytes(self.script)
            h = _sha1(data)
            now = self.clock()
            if h != seen:
                seen, changed_at = h, now
            elif changed_at is not None and now - changed_at >= self.debounce:
                settled, changed_at = changed_at, None
                if h is None or h == self._built or not source_compiles(data):
                    self.skipped += 1
                else:
                    self._built = h
                    self._build(data, h, settled)
                    continue                # look at the file again at once
            self._stop.wait(self.poll)

    def _build(self, data, h, settled):
        t_start = self.clock()
        tmp = tempfile.mkdtemp(prefix="atech-preview-")
        ws = os.path.join(tmp, "ws")
        try:
            shutil.copytree(self.ws, ws, symlinks=True,
                            ignore=shutil.ignore_patterns("__pycache__"))
            with open(os.path.join(ws, "model.py"), "wb") as fh:
                fh.write(data)
            b, crash = self.build_fn(dict(self.job, workspace=ws, preview=True, render=None))
        except (OSError, shutil.Error) as exc:
            b, crash = None, "preview copy failed: %s" % exc
        except Exception as exc:        # noqa: BLE001 - a dead watch thread would
            b, crash = None, "preview build raised: %r" % exc   # drop every later preview
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        t_done = self.clock()
        b = b or {"ok": False, "error": "HARNESS CRASH: %s" % crash, "harness_crash": True}
        secs = b.get("build_seconds")
        self.records.append({
            "turn": self.turn, "sha1": h,
            "settled_s": round(settled - self.t_ref, 2),
            "start_s": round(t_start - self.t_ref, 2),
            "done_s": round(t_done - self.t_ref, 2),
            "build_seconds": secs,
            "prod_s": (round(settled - self.t_ref + self.debounce + secs, 2)
                       if secs is not None else None),
            "ok": bool(b.get("ok")), "failures": b.get("failures") or "",
            "error": preview_error_tail(b.get("error")),
            # S49: failures that are intent.json misses only (Studio: "in
            # progress"); None = not classified (older fc_build or error).
            "intent_only": b.get("intent_only"),
            "harness_crash": bool(b.get("harness_crash"))})


def preview_error_tail(err, n=300):
    """A preview's error, clipped for the record. Production's error text
    starts with the exception line and ends with the model.py excerpt; a bare
    tail clip dropped the exception (round 6: 3 of 5 failed previews recorded
    only source lines), so the first line is always kept."""
    err = (err or "").strip()
    if len(err) <= n:
        return err
    head = err.splitlines()[0][:200]
    return head + "\n...\n" + err[-n:]


def first_good_preview(previews):
    """The first live preview that built with no measurement failure."""
    for p in previews or []:
        if p.get("ok") and not p.get("failures"):
            return p
    return None


# ------------------------------------------------------------------ claude
def _is_model_write(name, inp):
    fp = str((inp or {}).get("file_path") or "")
    return name in ("Write", "Edit", "MultiEdit") and os.path.basename(fp) == "model.py"


def production_argv(root, seed=None, request=None):
    """A chat workspace made by production's build.new_workspace() under
    `root`, and the claude command templates production builds for it
    (fc_build.py mode "argv"). `request` is the user's request text, given
    to _turn_args with the document as production does (R111); the argv
    still carries MSG_PH. Returns the payload: workspace, first, resume,
    stdin_first, stdin_resume, source, document_brief, private_dirs,
    workspace_files."""
    payload, crash = fc_job({"mode": "argv", "workspace_root": root, "message": MSG_PH,
                             "session": SID_PH, "seed": seed, "request": request})
    if payload is None:
        raise RuntimeError("could not compute the production claude argv: %s" % crash)
    for key in ("first", "resume"):
        n = payload[key].count(MSG_PH) + (payload.get("stdin_" + key) or "").count(MSG_PH)
        if n != 1:
            raise RuntimeError("production command (%s) does not carry the message "
                               "exactly once (argv + stdin): %s" % (key, flags_of(payload[key])))
    if SID_PH not in payload["resume"]:
        raise RuntimeError("production resume argv has no session: %s"
                           % flags_of(payload["resume"]))
    return payload


def render_stdin(template, message):
    """Fill the message placeholder of a production stdin template (None:
    the prompt is on argv, nothing is written to stdin)."""
    return None if template is None else template.replace(MSG_PH, message)


def render_argv(template, message, session=None):
    """Fill the placeholders of a production argv template."""
    out = []
    for a in template:
        if a == MSG_PH:
            out.append(message)
        elif a == SID_PH:
            if session is None:
                raise ValueError("resume template needs a session id")
            out.append(session)
        else:
            out.append(a)
    return out


def flags_of(argv):
    """argv with the free-text values (prompt, system prompt) replaced by
    their length - what claude_cli.ClaudeRun.flags() logs."""
    out, skip = [], False
    for a in argv:
        if skip:
            out.append("<%d chars>" % len(a))
            skip = False
            continue
        out.append(a)
        skip = a == "--append-system-prompt"
    # the prompt itself (on argv before R35) shows as <message>
    return [x if x != MSG_PH else "<message>" for x in out]


def system_prompt_of(argv):
    """The appended system prompt in a production argv (inline or -file)."""
    if "--append-system-prompt" in argv:
        return argv[argv.index("--append-system-prompt") + 1]
    if "--append-system-prompt-file" in argv:
        with open(argv[argv.index("--append-system-prompt-file") + 1], encoding="utf-8") as fh:
            return fh.read()
    return None


def input_tokens(usage):
    """input + cache-creation + cache-read tokens of a result's usage, or None."""
    if not isinstance(usage, dict):
        return None
    keys = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    vals = [usage.get(k) for k in keys]
    if all(v is None for v in vals):
        return None
    return sum(int(v or 0) for v in vals)


def output_tokens(usage):
    """Output tokens of a result's usage, or None when not reported (S32)."""
    if not isinstance(usage, dict) or usage.get("output_tokens") is None:
        return None
    return int(usage["output_tokens"])


def turns_output_tokens(turns):
    """Sum of output tokens over a prompt's turns, from each turn's own
    `output_tokens` or, for runs saved before S32, its recorded `usage`.
    None when any turn did not report it (missing stays missing)."""
    vals = []
    for t in turns or []:
        v = t.get("output_tokens")
        if v is None:
            v = output_tokens(t.get("usage"))
        vals.append(v)
    return sum(vals) if vals and all(v is not None for v in vals) else None


TOOL_RESULT_CHARS = 2000        # per tool result in transcript.txt


def tool_result_text(content):
    """The text of a tool_result block's content (str or list of blocks);
    non-text blocks (images) are named, not dropped silently."""
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(str(b.get("text") or ""))
        elif isinstance(b, dict):
            parts.append("<%s block>" % b.get("type"))
    return "\n".join(parts)


def _clip(text, n=TOOL_RESULT_CHARS):
    text = text or ""
    if len(text) <= n:
        return text
    return "%s\n... [%d more chars]" % (text[:n], len(text) - n)


def _is_check_call(name, inp):
    cmd = str((inp or {}).get("command") or "").strip()
    return name == "Bash" and (cmd == "./check" or cmd.startswith("./check "))


def denial_records(result, calls):
    """Each permission denial of a result record (S46): tool, the command
    or file it was asked for, and whether the denied command runs `./check`
    (a denied `sed -i ... && ./check` never ran its check: an allowlist
    miss, not an agent error). `calls` maps a
    tool_use id to its input, from the stream, for denials that carry only
    the id."""
    out = []
    for d in (result or {}).get("permission_denials") or []:
        d = d if isinstance(d, dict) else {}
        inp = d.get("tool_input") or calls.get(d.get("tool_use_id")) or {}
        what = str(inp.get("command") or inp.get("file_path") or inp.get("pattern") or "")
        out.append({"tool": d.get("tool_name"), "command": what[:300] or None,
                    "runs_check": bool(re.search(r"(^|[;&|]\s*)\./check\b", what))})
    return out


# ------------------------------------------------------ S57 stall attribution
# A "gap" is a stretch of a turn with no tool activity: between consecutive
# marks {turn start, every tool_use, every tool_result, turn end}. Every gap
# of STALL_GAP_S or more is split, second by second of the stream timeline
# claude_turn records, into what the turn was doing:
#   retries       a failed API attempt that ended in a system/api_retry
#                 record, and the retry's backoff (retry_delay_ms)
#   first_event   an API request sent (turn start, or all tool results in)
#                 and no streamed event yet: the slow first event
#   stream_stall  inside a streamed message, a silence of STREAM_QUIET_S or
#                 more between two stream events (the API stopped mid-reply)
#   model         a message streaming (message_start .. message_stop), minus
#                 its stream stalls: the model generating
#   tool          a tool_use without its tool_result yet
#   startup       spawn -> the init record
# `cause` is the largest share. A turn recorded with no message_start events
# (no --include-partial-messages, or an older run) cannot tell API waiting
# from generation: that time is `unattributed`, never guessed (P1).
STALL_GAP_S = 120.0
STREAM_QUIET_S = 5.0
STALL_CATEGORIES = ("retries", "first_event", "stream_stall", "model", "tool", "startup",
                    "unattributed")


def stall_segments(timeline, end_s):
    """[(t0, t1, category)] covering 0 .. end_s from a turn's timeline
    ([[t, kind, info], ...]; kinds init, msg_start, msg_stop, tool_use,
    tool_result, retry (info = backoff s), quiet (info = silence start),
    result). Pure."""
    evs = sorted((list(e) for e in timeline or [] if e and e[0] is not None),
                 key=lambda e: e[0])
    streamed = any(e[1] == "msg_start" for e in evs)
    wait = "first_event" if streamed else "unattributed"
    # a retry's backoff ends at t + delay unless something happens first
    for e in list(evs):
        if e[1] == "retry" and e[2]:
            evs.append([e[0] + float(e[2]), "backoff_end", None])
    evs.sort(key=lambda e: (e[0], e[1] == "backoff_end"))
    segs, state, t, pending = [], "startup", 0.0, set()
    has_init = any(e[1] == "init" for e in evs)
    if not has_init:
        state = wait

    def push(t1, cat):
        if t1 > t:
            segs.append([t, t1, cat])
    for tt, kind, info in evs:
        tt = min(max(tt, t), end_s)
        if kind == "retry":
            # the attempt that just failed was waiting on the API: retries
            for s in reversed(segs):
                if s[2] != wait:
                    break
                s[2] = "retries"
            push(tt, "retries" if state == wait else state)
            t, state = tt, "retries"
            continue
        push(tt, state)
        t = tt
        if kind == "init" and state == "startup":
            state = wait
        elif kind == "backoff_end" and state == "retries":
            state = wait
        elif kind == "msg_start":
            state = "model"
        elif kind == "msg_stop":
            state = "tool" if pending else wait
        elif kind == "tool_use":
            pending.add(info)
            if state != "model":
                state = "tool"
        elif kind == "tool_result":
            pending.discard(info)
            if not pending and state == "tool":
                state = wait
        elif kind == "result":
            state = "unattributed"             # the CLI wrapping up; tiny
    push(end_s, state)
    # stream stalls: quiet stretches inside a streamed message
    quiet = [(float(e[2]), e[0]) for e in evs if e[1] == "quiet" and e[2] is not None]
    out = []
    for a, b, cat in segs:
        if cat != "model" or not quiet:
            out.append((a, b, cat))
            continue
        cur = a
        for q0, q1 in sorted(quiet):
            lo, hi = max(q0, cur), min(q1, b)
            if hi <= lo:
                continue
            if lo > cur:
                out.append((cur, lo, "model"))
            out.append((lo, hi, "stream_stall"))
            cur = hi
        if cur < b:
            out.append((cur, b, "model"))
    return out


def turn_gaps(turn, threshold=STALL_GAP_S):
    """S57: every gap of `threshold` s or more in one recorded turn, each
    attributed (see STALL_CATEGORIES). None when the turn has no timeline
    (recorded before round 9): not measured, not "no gaps"."""
    tl = turn.get("timeline")
    if tl is None:
        return None
    end = turn.get("wall_s")
    if end is None:
        return None
    # wall_s is rounded to 0.1 s; the timeline to 0.01 s
    end = max([end] + [e[0] for e in tl if e and e[0] is not None])
    marks = [(0.0, "request")]
    for t, kind, info in tl:
        if kind in ("tool_use", "tool_result") and t is not None:
            marks.append((min(t, end), "%s %s" % (kind, info)))
    marks.append((end, "timeout" if turn.get("timed_out") else "end"))
    marks.sort(key=lambda m: m[0])
    segs = stall_segments(tl, end)
    gaps = []
    for (a, what), (b, until) in zip(marks, marks[1:]):
        if b - a < threshold:
            continue
        g = {"from_s": round(a, 1), "to_s": round(b, 1), "gap_s": round(b - a, 1),
             "after": what, "until": until}
        for c in STALL_CATEGORIES:
            g[c + "_s"] = round(sum(max(0.0, min(s1, b) - max(s0, a))
                                    for s0, s1, cat in segs if cat == c), 1)
        g["requests"] = sum(1 for t, k, _i in tl if k == "msg_start" and a < t <= b)
        g["retries"] = sum(1 for t, k, _i in tl if k == "retry" and a < t <= b)
        toks = [i for t, k, i in tl if k == "msg_stop" and a < t <= b]
        g["output_tokens"] = sum(toks) if toks and all(x is not None for x in toks) else None
        g["cause"] = max(STALL_CATEGORIES, key=lambda c: g[c + "_s"])
        gaps.append(g)
    return gaps


def request_stalls(res, threshold=STALL_GAP_S):
    """Every attributed gap of a request, turn by turn, with the turn's
    start from the request (`turn_start_s`). None when no turn carries a
    timeline (a run saved before S57)."""
    out, measured = [], False
    for i, t in enumerate(res.get("turns") or []):
        gaps = turn_gaps(t, threshold)
        if gaps is None:
            continue
        measured = True
        for g in gaps:
            g = dict(g, turn=i + 1)
            if t.get("started_s") is not None:
                g["turn_start_s"] = t["started_s"]
            out.append(g)
    return out if measured else None


def claude_turn(argv, ws, stdin_text=None):
    """One `claude -p` turn with the production argv (and the prompt on
    stdin when production puts it there). Returns a dict."""
    env = dict(os.environ)
    for k in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"):
        env.pop(k, None)
    t0 = time.time()
    errf = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
    proc = subprocess.Popen(argv, cwd=ws, env=env, stdout=subprocess.PIPE,
                            stderr=errf, text=True, bufsize=1,
                            stdin=subprocess.PIPE if stdin_text is not None
                            else subprocess.DEVNULL)
    timer = threading.Timer(TURN_TIMEOUT_S, proc.terminate)   # our own child only
    timer.start()
    if stdin_text is not None:
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except OSError:
            pass                                    # the child died; its stream says why
    rec = {"session": None, "tools": [], "texts": [], "result": None,
           "model": None, "timed_out": False, "first_write_s": None,
           "init_s": None, "first_text_s": None, "check_calls": 0,
           "first_event_s": None, "api_retries": [],
           "timeline": [],     # S57: [t, kind, info] - see stall_segments
           "log": []}          # S32: tool calls AND their results, in stream order
    calls = {}                 # tool_use id -> input (S46 denials)
    tl = rec["timeline"]
    last_stream = [None]       # time of the previous stream_event (S57 quiet)
    msg_tokens = [None]        # output tokens of the message streaming now
    msg_open = [False]         # a message_start with no message_stop yet
    n_tool = [0]

    def now():
        return round(time.time() - t0, 2)
    try:
        for line in proc.stdout:
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
                rec["session"] = msg.get("session_id") or rec["session"]
                rec["model"] = msg.get("model")
                if rec["init_s"] is None:
                    rec["init_s"] = round(time.time() - t0, 2)
                    tl.append([rec["init_s"], "init", None])
            elif kind == "system" and msg.get("subtype") == "api_retry":
                d_ms = msg.get("retry_delay_ms")
                tl.append([now(), "retry", round(d_ms / 1000.0, 3)
                           if isinstance(d_ms, (int, float)) else None])
                # R8: an API retry is latency the model never saw; without it
                # a slow first write cannot be told from a slow model
                rec["api_retries"].append({
                    "at_s": round(time.time() - t0, 2),
                    "attempt": msg.get("attempt"),
                    "error_status": msg.get("error_status"),
                    "error": str(msg.get("error") or "")[:200],
                    "retry_delay_ms": msg.get("retry_delay_ms")})
                rec["log"].append("!! api_retry attempt %s status %s delay %s ms" % (
                    msg.get("attempt"), msg.get("error_status"), msg.get("retry_delay_ms")))
            elif kind == "assistant":
                for b in (msg.get("message") or {}).get("content") or []:
                    if b.get("type") == "text" and b.get("text"):
                        rec["texts"].append(b["text"])
                        if rec["first_text_s"] is None:
                            rec["first_text_s"] = round(time.time() - t0, 2)
                    elif b.get("type") == "tool_use":
                        inp = b.get("input") or {}
                        if b.get("id"):
                            calls[b["id"]] = inp
                        n_tool[0] += 1
                        tl.append([now(), "tool_use", b.get("id") or "#%d" % n_tool[0]])
                        arg = inp.get("file_path") or inp.get("command") or inp.get("pattern") or ""
                        rec["tools"].append("%s %s" % (b.get("name"), str(arg)[:160]))
                        rec["log"].append("-> [%s] %s %s" % (
                            b.get("id") or "?", b.get("name"), str(arg)[:400]))
                        if rec["first_write_s"] is None and _is_model_write(b.get("name"), inp):
                            rec["first_write_s"] = round(time.time() - t0, 1)
                        if _is_check_call(b.get("name"), inp):
                            rec["check_calls"] += 1
            elif kind == "user":
                # the CLI echoes each tool's result back as a user message
                content = (msg.get("message") or {}).get("content")
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        tl.append([now(), "tool_result", b.get("tool_use_id")])
                        rec["log"].append("<- [%s]%s %s" % (
                            b.get("tool_use_id") or "?",
                            " ERROR" if b.get("is_error") else "",
                            _clip(tool_result_text(b.get("content")))))
            elif kind == "stream_event":
                # --include-partial-messages (S19): text deltas arrive before
                # the assembled assistant message; the first one is first text
                ev = msg.get("event") or {}
                t_ev = now()
                if rec["first_event_s"] is None:
                    # R8: the first streamed API event = the API answered
                    rec["first_event_s"] = t_ev
                if last_stream[0] is not None and t_ev - last_stream[0] >= STREAM_QUIET_S:
                    tl.append([t_ev, "quiet", last_stream[0]])      # S57
                last_stream[0] = t_ev
                et = ev.get("type")
                if et == "message_start":
                    msg_tokens[0] = None
                    msg_open[0] = True
                    tl.append([t_ev, "msg_start", None])
                elif et == "message_delta":
                    u = ev.get("usage") or {}
                    if isinstance(u.get("output_tokens"), int):
                        msg_tokens[0] = u["output_tokens"]
                elif et == "message_stop":
                    tl.append([t_ev, "msg_stop", msg_tokens[0]])
                    msg_tokens[0] = None
                    msg_open[0] = False
                d = ev.get("delta") or {}
                if rec["first_text_s"] is None and d.get("type") == "text_delta" \
                        and d.get("text"):
                    rec["first_text_s"] = round(time.time() - t0, 2)
            elif kind == "result":
                rec["result"] = msg
                tl.append([now(), "result", None])
    finally:
        # S57: a stream that goes silent mid-message and never speaks again
        # (the turn is killed at TURN_TIMEOUT_S, or the CLI dies) has no
        # later stream event to mark the silence - close it here, or the
        # whole trailing silence would read as `model`
        t_end = now()
        if msg_open[0] and last_stream[0] is not None \
                and t_end - last_stream[0] >= STREAM_QUIET_S:
            tl.append([t_end, "quiet", last_stream[0]])
        code = proc.wait()
        proc.stdout.close()
        if not timer.is_alive():
            rec["timed_out"] = True
        timer.cancel()
    errf.seek(0)
    rec["stderr_tail"] = errf.read()[-1500:]
    errf.close()
    rec["exit"] = code
    rec["wall_s"] = round(time.time() - t0, 1)
    r = rec["result"] or {}
    rec["ok"] = bool(rec["result"]) and not r.get("is_error")
    rec["final"] = r.get("result") or ""
    rec["cost_usd"] = r.get("total_cost_usd")
    rec["duration_api_ms"] = r.get("duration_api_ms")
    rec["num_turns"] = r.get("num_turns")
    rec["usage"] = r.get("usage")
    rec["input_tokens"] = input_tokens(r.get("usage"))
    rec["output_tokens"] = output_tokens(r.get("usage"))
    rec["permission_denials"] = len(r.get("permission_denials") or [])
    rec["denials"] = denial_records(r, calls)
    rec["stalls"] = turn_gaps(rec)                  # S57
    return rec


def transcript_turn(message, turn):
    """One turn of transcript.txt: the message sent, every tool call with
    its result (S32; tool results clipped to TOOL_RESULT_CHARS), the text
    and the final answer."""
    return ("=== USER ===\n%s\n=== TOOLS (call -> result) ===\n%s\n=== TEXT ===\n%s\n"
            "=== FINAL ===\n%s\n" % (message, "\n".join(turn.get("log") or turn["tools"]),
                                      "\n---\n".join(turn["texts"]), turn["final"]))


# ----------------------------------------------------------- code quality
def code_quality(code):
    """Static signals about model.py. Descriptive, not a verdict."""
    out = {"lines": len([l for l in code.splitlines() if l.strip()])}
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        out["syntax_error"] = str(exc)
        return out
    params = 0
    for node in tree.body:                                   # module-level constants
        if isinstance(node, ast.Assign) and all(isinstance(t, ast.Name) for t in node.targets):
            if isinstance(node.value, (ast.Constant, ast.BinOp, ast.UnaryOp, ast.Tuple)):
                params += 1
    call_literals = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, (int, float)) \
                        and a.value not in (0, 1, -1, 2):
                    call_literals += 1
    src = code
    out.update({
        "named_params": params,
        "magic_numbers_in_calls": call_literals,
        "functions": sum(isinstance(n, ast.FunctionDef) for n in ast.walk(tree)),
        "fuse": src.count(".fuse("), "cut": src.count(".cut("),
        "checks_solids": "len(" in src and ".Solids" in src,
        "removeSplitter": "removeSplitter" in src,
        "fillet_or_chamfer": ("makeFillet" in src) or ("makeChamfer" in src),
        "objects_added": src.count("addObject("),
        "sets_color": "ShapeColor" in src or "ViewObject" in src,
        "uses_sketcher": "Sketcher" in src,
        "uses_partdesign": "PartDesign" in src,
    })
    return out


# ------------------------------------------------------------- one prompt
def first_apply_pass(build):
    """The first model.py the agent wrote built, with no measurement failure."""
    return bool(build and build.get("ok") and not build.get("failures"))


def score_final(res, last):
    """Expectation score + fitness score from the final build."""
    res["final_build"] = last
    checks = last.get("checks") or []
    res["checks_passed"] = sum(c["pass"] for c in checks)
    res["checks_total"] = len(checks)
    res["pass"] = bool(res["built"] and checks and all(c["pass"] for c in checks))
    fit = last.get("fitness") or []
    res["fitness_passed"] = sum(c["pass"] for c in fit)
    res["fitness_total"] = len(fit)
    res["fit_pass"] = bool(res["built"] and fit and all(c["pass"] for c in fit))


def _seed_path(item):
    seed = item.get("seed")
    return os.path.join(HERE, seed) if seed else None


def is_atech_item(item):
    """An Atech prompt (S35): its expectations run atech_ports.check."""
    return bool(((item or {}).get("expect") or {}).get("atech_check"))


PHASE_PREFIX = ("", "edit_")                 # outcome prefix per request phase
ATTEMPT_FILE = ("model_attempt%d.py", "edit_attempt%d.py")
REQUEST1_FILE = "model_request1.py"         # the first request's built model.py


def request_record(res, build):
    """R173: the first request of an item with an edit turn, scored on its
    own expectations before the edit is sent (or when it never built)."""
    checks = build.get("checks") or []
    fit = build.get("fitness") or []
    ok = bool(build.get("ok") and not build.get("failures"))
    return {"built": ok, "builds": (len(res["builds"]) if res.get("builds") is not None
                                    else None),
            "fix_rounds": res.get("fix_rounds", 0),
            "first_ok_build_s": res.get("first_ok_build_s"),
            "whole_dims_sorted_mm": build.get("whole_dims_sorted_mm"),
            "checks_passed": sum(c["pass"] for c in checks), "checks_total": len(checks),
            "pass": bool(ok and checks and all(c["pass"] for c in checks)),
            "fit_pass": bool(ok and fit and all(c["pass"] for c in fit)),
            "failed_checks": [c["check"] for c in checks + fit if not c["pass"]]}


def run_prompt(item, out_root, render=True):
    pid = item["id"]
    root = tempfile.mkdtemp(prefix="atech-eval-%s-" % pid)
    seed = _seed_path(item)
    prod = production_argv(root, seed, item["prompt"])
    ws = prod["workspace"]
    brief = prod["document_brief"]
    sp_first = system_prompt_of(prod["first"])
    dest = os.path.join(out_root, pid)
    os.makedirs(dest, exist_ok=True)
    script = os.path.join(ws, "model.py")
    t_start = time.time()
    res = {"id": pid, "prompt": item["prompt"], "workspace": ws, "turns": [],
           "builds": [], "built": False, "fix_rounds": 0, "outcome": None,
           "first_write_s": None, "first_ok_build_s": None,
           "previews": [], "preview_skipped": 0, "preview_wait_s": 0.0, "denials": [],
           "argv_source": prod["source"], "argv_flags": flags_of(prod["first"]),
           "argv_dropped": prod.get("dropped_first") or [],
           "prompt_on_stdin": prod.get("stdin_first") is not None,
           "seed": item.get("seed"), "atech": is_atech_item(item),
           "system_prompt_chars": len(sp_first) if sp_first is not None else None,
           "atech_reference": "ATECH_ASSEMBLY.md" in (prod.get("workspace_files") or [])}
    message = "%s\n\n---\n%s" % (item["prompt"], brief)
    session, attempt, last_mtime = None, 0, None
    transcript = []
    # R173: an item's "edit" is a SECOND user request on the same session,
    # sent once the first one built; it gets its own fix loop and its own
    # expectations (the final score). `phase` 0 = the request, 1 = the edit.
    edit, phase, base_fixes = item.get("edit"), 0, 0
    expect, request = item.get("expect"), item["prompt"]
    if edit:
        res["edit_prompt"] = edit["prompt"]
    while True:
        log("[%s] claude turn %d" % (pid, len(res["turns"]) + 1))
        t_turn = time.time()
        key = "resume" if session else "first"
        argv = render_argv(prod[key], message, session)
        live = LivePreview(ws, {"mode": "build", "expect": expect,
                                "prompt": request, "seed": seed},
                           t_start, turn=len(res["turns"]) + 1).start()
        try:
            turn = claude_turn(argv, ws, render_stdin(prod.get("stdin_" + key), message))
        finally:
            res["previews"] += live.stop()          # S46: a build in flight finishes
            res["preview_skipped"] += live.skipped
            res["preview_wait_s"] = round(res["preview_wait_s"] + live.stop_wait_s, 2)
        res["denials"] += turn["denials"]
        if res["first_write_s"] is None and turn["first_write_s"] is not None:
            res["first_write_s"] = round(t_turn - t_start + turn["first_write_s"], 1)
        session = turn["session"] or session
        rec_turn = {k: turn[k] for k in (
            "wall_s", "ok", "cost_usd", "num_turns", "model", "tools", "timed_out", "exit",
            "first_write_s", "init_s", "first_text_s", "check_calls", "input_tokens",
            "output_tokens", "permission_denials", "denials", "usage")}
        # Stall diagnostics (round 8): absent from turns recorded by an older
        # run_claude or a test double, so missing stays missing (None).
        for k in ("first_event_s", "api_retries", "duration_api_ms", "timeline", "stalls"):
            rec_turn[k] = turn.get(k)
        rec_turn["started_s"] = round(t_turn - t_start, 1)      # S57
        res["turns"].append(rec_turn)
        transcript.append(transcript_turn(message, turn))
        if not turn["ok"]:
            res["outcome"] = PHASE_PREFIX[phase] + "claude_failed: %s" % (
                (turn["final"] or turn["stderr_tail"] or "no result")[:300])
            break
        mtime = os.path.getmtime(script) if os.path.isfile(script) else None
        if mtime is None or mtime == last_mtime:
            res["outcome"] = PHASE_PREFIX[phase] + (
                "nothing_to_build" if mtime is None else "not_rewritten")
            break
        last_mtime = mtime
        with open(script, encoding="utf-8") as fh:
            code = fh.read()
        shutil.copy(script, os.path.join(dest, ATTEMPT_FILE[phase] % (attempt + 1)))
        log("[%s] %sbuild attempt %d" % (pid, PHASE_PREFIX[phase], attempt + 1))
        b, crash = fc_job({"mode": "build", "workspace": ws, "expect": expect,
                           "prompt": request, "seed": seed,
                           "render": os.path.join(dest, "render.png") if render else None})
        if b is None:
            b = {"ok": False, "error": "HARNESS CRASH: %s" % crash, "harness_crash": True}
        b["code_quality"] = code_quality(code)
        res["builds"].append(b)
        if b.get("harness_crash"):
            res["outcome"] = PHASE_PREFIX[phase] + "harness_crash"
            break
        if not b["ok"]:
            fix = "The script failed when Atech Atelier ran it:\n%s" % (b.get("error") or "")[-3000:]
        elif b.get("failures"):
            fix = ("Atech Atelier built it, but the measurement check failed: %s. Each body "
                   "must be one valid solid." % b["failures"])
        else:
            if res["first_ok_build_s"] is None:
                res["first_ok_build_s"] = round(time.time() - t_start, 1)
            if phase == 0 and edit:
                # the request is done: score it, keep its model.py, then
                # send the edit as the user's next message (panel._send_claude
                # appends the document brief to every message)
                res["first_request"] = request_record(res, b)
                shutil.copy(script, os.path.join(dest, REQUEST1_FILE))
                phase, attempt, base_fixes = 1, 0, res["fix_rounds"]
                expect = edit.get("expect") or expect
                request = "%s\n%s" % (item["prompt"], edit["prompt"])
                message = "%s\n\n---\n%s" % (edit["prompt"], b.get("document_brief") or brief)
                log("[%s] request built; sending the edit turn" % pid)
                continue
            res["built"] = True
            res["outcome"] = PHASE_PREFIX[phase] + "built"
            break
        attempt += 1
        if attempt > MAX_FIX_ATTEMPTS:
            res["outcome"] = PHASE_PREFIX[phase] + "still_fails_after_%d_fixes" % MAX_FIX_ATTEMPTS
            break
        res["fix_rounds"] = base_fixes + attempt
        message = "%s\nFix model.py and write it again.\n\n---\n%s" % (
            fix, b.get("document_brief") or brief)
        # panel._send_fix -> _send_claude(message) -> message + brief
    res["wall_s"] = round(time.time() - t_start, 1)
    res["cost_usd"] = round(sum(t["cost_usd"] or 0 for t in res["turns"]), 4)
    t1 = res["turns"][0] if res["turns"] else {}
    res["init_s"] = t1.get("init_s")
    res["first_text_s"] = t1.get("first_text_s")
    res["check_calls"] = sum(t.get("check_calls") or 0 for t in res["turns"])
    res["permission_denials"] = sum(t.get("permission_denials") or 0 for t in res["turns"])
    toks = [t.get("input_tokens") for t in res["turns"]]
    res["input_tokens"] = sum(toks) if toks and all(x is not None for x in toks) else None
    res["output_tokens"] = turns_output_tokens(res["turns"])
    res["stalls"] = request_stalls(res)                  # S57
    if edit and phase == 0:
        res["first_request"] = request_record(res, res["builds"][-1] if res["builds"] else {})
    good = first_good_preview(res["previews"])
    res["first_preview_s"] = good["done_s"] if good else None
    res["first_preview_prod_s"] = good["prod_s"] if good else None
    res["first_apply_pass"] = first_apply_pass(res["builds"][0] if res["builds"] else None)
    score_final(res, res["builds"][-1] if res["builds"] else {})
    if os.path.isfile(script):
        shutil.copy(script, os.path.join(dest, "model.py"))
    intent = os.path.join(ws, "intent.json")
    if os.path.isfile(intent) and not os.path.islink(intent):
        # the final build read it (fitted_after); --rescore needs it too
        shutil.copy(intent, os.path.join(dest, "intent.json"))
    for d in prod.get("private_dirs") or []:
        shutil.rmtree(d, ignore_errors=True)            # ClaudeRun's system-prompt files
    with open(os.path.join(dest, "transcript.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(transcript))
    log("[%s] %s  built=%s pass=%s checks=%d/%d attempts=%d previews=%d %.0fs $%.2f" % (
        pid, res["outcome"], res["built"], res["pass"], res["checks_passed"],
        res["checks_total"], len(res["builds"]), len(res["previews"]), res["wall_s"],
        res["cost_usd"]))
    return res


# ------------------------------------------------------------------ report
def _next_n(tag="baseline"):
    os.makedirs(OUT_DIR, exist_ok=True)
    ns = [int(m.group(1)) for f in os.listdir(OUT_DIR)
          for m in [re.match(r"%s_(\d+)\.json$" % re.escape(tag), f)] if m]
    return (max(ns) + 1) if ns else 1


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else 0.5 * (xs[m - 1] + xs[m])


def is_atech_result(r, items=None):
    """A result's group: recorded `atech` (S35), else looked up by id in
    the current prompt files (runs saved before S35)."""
    if r.get("atech") is not None:
        return bool(r["atech"])
    items = load_expectations() if items is None else items
    return is_atech_item(items.get(r.get("id")))


def all_checks_pass(r):
    """Built, every expectation check AND every fitness check passed. For an
    Atech prompt the fitness checks carry the Atech verdicts (S35)."""
    return bool(r.get("built") and r.get("pass") and
                (r.get("fit_pass") or not r.get("fitness_total")))


def group_rows(results, items=None):
    """Plain vs Atech pass rates (S35), reported separately so an Atech
    regression cannot hide inside the plain score or the other way round.
    -> [(group, n, built, first, expectations, fitness, all)]."""
    rows = []
    for name, want in (("plain", False), ("Atech", True)):
        rs = [r for r in results if is_atech_result(r, items) == want]
        rows.append((name, len(rs),
                     sum(bool(r.get("built")) for r in rs),
                     sum(1 for r in rs if r.get("built") and (
                         r["first_apply_pass"] if r.get("first_apply_pass") is not None
                         else len(r.get("builds") or []) == 1)),
                     sum(bool(r.get("pass")) for r in rs),
                     sum(bool(r.get("fit_pass")) for r in rs),
                     sum(all_checks_pass(r) for r in rs)))
    return rows


def edit_rows(results):
    """R173: the report's edit-turn section - the first request's own score
    next to the edit's (the final score). [] when no prompt had an edit."""
    rs = [r for r in results if r.get("edit_prompt") or r.get("first_request")]
    if not rs:
        return []
    L = ["", "## Edit turns (R173)", "",
         "A second user request sent on the same session once the first one "
         "built. The row's final score (pass / fitness above) is the edit's; "
         "the first request is scored on its own expectations before the edit.", "",
         "| id | edit | 1st request built | 1st request checks | 1st request pass | "
         "edit outcome | edit pass | edit fitness |", "|---|---|---|---|---|---|---|---|"]
    for r in rs:
        f = r.get("first_request") or {}
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], (r.get("edit_prompt") or "-").replace("|", "\\|"),
            "yes" if f.get("built") else "no",
            "%d/%d" % (f.get("checks_passed", 0), f.get("checks_total", 0)) if f else "-",
            "PASS" if f.get("pass") else "FAIL",
            r.get("outcome") if f.get("built") else "not sent (the request did not build)",
            ("PASS" if r.get("pass") else "FAIL") if f.get("built") else "-",
            ("%d/%d" % (r.get("fitness_passed", 0), r["fitness_total"])
             if f.get("built") and r.get("fitness_total") else "-")))
    return L


def _stalls_of(r):
    """A result's attributed gaps (S57): recorded, else from its turns'
    timelines; None = not measured (the run predates S57)."""
    if r.get("stalls") is not None:
        return r["stalls"]
    return request_stalls(r)


def stall_headline(results):
    """`n gaps in k prompts, x s total; by cause: ...` or not measured."""
    measured = [r for r in results if _stalls_of(r) is not None]
    if not measured:
        return "not measured (run predates S57)"
    gs = [g for r in measured for g in _stalls_of(r)]
    if not gs:
        return "none (n=%d prompts)" % len(measured)
    by = {}
    for g in gs:
        by[g["cause"]] = by.get(g["cause"], 0) + 1
    return "%d in %d of %d prompts, %.0f s total; cause: %s" % (
        len(gs), sum(1 for r in measured if _stalls_of(r)), len(measured),
        sum(g["gap_s"] for g in gs),
        ", ".join("%s %d" % (c, by[c]) for c in STALL_CATEGORIES if c in by))


def stall_cell(r):
    """Per-prompt column: gaps >= STALL_GAP_S as `n (longest s cause)`."""
    st = _stalls_of(r)
    if st is None:
        return "not measured"
    if not st:
        return "0"
    g = max(st, key=lambda x: x["gap_s"])
    return "%d (%.0f s %s)" % (len(st), g["gap_s"], g["cause"])


def stall_rows(results):
    """S57: the report's stall section - every gap of STALL_GAP_S s or more
    split into retries / slow first event / stream stall / model / tool
    time, with the output tokens streamed in it."""
    measured = [r for r in results if _stalls_of(r) is not None]
    L = ["", "## Stalls over %.0f s (S57)" % STALL_GAP_S, ""]
    if not measured:
        return L + ["Not measured: the run predates S57 (no stream timeline per turn)."]
    rows = [(r["id"], g) for r in measured for g in _stalls_of(r)]
    L += ["A gap is a stretch with no tool call or tool result (from the turn's start, "
          "a tool call or its result, to the next one or the turn's end). Each second "
          "is attributed from the stream: `retries` (a failed API attempt and its "
          "backoff), `first event` (request sent, nothing streamed yet), `stream stall` "
          "(silent >= %.0f s inside a streamed message), `model` (streaming), `tool` "
          "(a tool running), `unattributed` (no stream events recorded). %d of %d "
          "prompts measured." % (STREAM_QUIET_S, len(measured), len(results)), ""]
    if not rows:
        return L + ["None."]
    L += ["| id | turn | from s | to s | gap s | after | retries s | first event s | "
          "stream stall s | model s | tool s | startup s | unattributed s | requests | "
          "retries | out tok | cause |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for pid, g in rows:
        L.append("| %s | %d | %.0f | %.0f | %.0f | %s | %.0f | %.0f | %.0f | %.0f | %.0f | "
                 "%.0f | %.0f | %d | %d | %s | **%s** |" % (
                     pid, g["turn"], g["from_s"], g["to_s"], g["gap_s"],
                     g["after"].replace("|", "\\|"), g["retries_s"], g["first_event_s"],
                     g["stream_stall_s"], g["model_s"], g["tool_s"], g["startup_s"],
                     g["unattributed_s"], g["requests"], g["retries"],
                     "-" if g["output_tokens"] is None else "%d" % g["output_tokens"],
                     g["cause"]))
    return L


def report(results, n, meta, tag="baseline"):
    N = len(results)

    def pct(k):
        return "%d/%d (%.0f%%)" % (k, N, 100.0 * k / N) if N else "0/0"

    built = sum(r["built"] for r in results)
    # first_apply_pass when recorded (S15, rescore); older runs: one build
    first = sum(1 for r in results if r["built"] and (
        r["first_apply_pass"] if r.get("first_apply_pass") is not None
        else len(r["builds"]) == 1))
    passed = sum(r["pass"] for r in results)
    fitted = sum(bool(r.get("fit_pass")) for r in results)
    fit_n = sum(1 for r in results if r.get("fitness_total"))
    inits = [r.get("init_s") for r in results if r.get("init_s") is not None]
    texts = [r.get("first_text_s") for r in results if r.get("first_text_s") is not None]
    checks_n = [r.get("check_calls") for r in results if r.get("check_calls") is not None]
    toks = [r.get("input_tokens") for r in results if r.get("input_tokens") is not None]
    for r in results:                     # runs saved before S32: from turn usage
        if r.get("output_tokens") is None:
            r["output_tokens"] = turns_output_tokens(r.get("turns"))
    otoks = [r["output_tokens"] for r in results if r.get("output_tokens") is not None]
    denials = sum(r.get("permission_denials") or 0 for r in results)
    sources = sorted({r.get("argv_source") for r in results if r.get("argv_source")})
    single = sum(1 for r in results if r["built"] and any(
        c["check"] == "single_solid_per_object" and c["pass"]
        for c in r["final_build"].get("checks", [])))
    patched = sum(1 for r in results for b in r["builds"] if b.get("headless_patched"))
    walls = sorted(r["wall_s"] for r in results)
    med = _median(walls) or 0
    fw = [r.get("first_write_s") for r in results if r.get("first_write_s") is not None]
    fok = [r.get("first_ok_build_s") for r in results if r.get("first_ok_build_s") is not None]
    fixes = [r.get("fix_rounds", 0) for r in results]
    # S46: runs saved before it have no `previews` key at all (not measured);
    # a run with the key and no clean preview measured "none"
    live = [r for r in results if "previews" in r]
    fp = [r.get("first_preview_s") for r in live if r.get("first_preview_s") is not None]
    fpp = [r.get("first_preview_prod_s") for r in live
           if r.get("first_preview_prod_s") is not None]
    pv = [p for r in live for p in r.get("previews") or []]
    pv_bad = sum(1 for p in pv if not (p.get("ok") and not p.get("failures")))
    pv_skip = sum(r.get("preview_skipped") or 0 for r in live)
    pv_err = sum(1 for p in pv if not p.get("ok"))
    pv_intent = sum(1 for p in pv if p.get("intent_only") is True)
    pv_unclass = sum(1 for p in pv if p.get("ok") and p.get("failures")
                     and p.get("intent_only") is None)
    pv_wait = sum(r.get("preview_wait_s") or 0 for r in live)

    def _s(v, fmt="%.0f s"):
        return fmt % v if v is not None else "not measured"
    cost = sum(r["cost_usd"] for r in results)
    ck_p = sum(r["checks_passed"] for r in results)
    ck_t = sum(r["checks_total"] for r in results)
    name = "%s_%d" % (tag, n)
    L = ["# Agent build-quality benchmark - %s %d" % (tag, n), "",
         *(["Re-scored from the saved model.py files of `%s` (no claude calls): "
            "`built` = the final model.py builds with no measurement failure, "
            "`built on first attempt` = model_attempt1.py does. Agent timings, "
            "cost and turns are the original run's." % meta["rescore_of"], ""]
           if meta.get("rescore_of") else []),
         "Run %s. Model: %s. Claude CLI: %s. Harness: `addon/AcadAgent/tests/eval/run_eval.py`.%s" % (
             meta["date"], meta.get("model"), meta.get("cli"),
             (" Final builds re-measured %s against the current prompts.json and the "
              "current production build.apply()/failures() (`--rescore`)."
              % meta["rescored"]) if meta.get("rescored") else ""),
         "Production system prompt (build.system_prompt), production flags, production "
         "build.apply() in freecadcmd, fix loop max %d. Raw data: `%s.json`; "
         "per-prompt model.py, render and transcript under `%s/`." % (MAX_FIX_ATTEMPTS, name, name),
         "", "## Headline", "",
         "| metric | value |", "|---|---|",
         "| built (valid geometry after <=%d fixes) | %s |" % (MAX_FIX_ATTEMPTS, pct(built)),
         "| built on first attempt | %s |" % pct(first),
         "| passed ALL expectation checks | %s |" % pct(passed),
         "| passed ALL fitness checks (overlap, below-desk, teeth, atech) | %s |" % (
             pct(fitted) if fit_n else "not measured (run predates S15)"),
         "| expectation checks passed (all prompts) | %d/%d (%.0f%%) |" % (
             ck_p, ck_t, 100.0 * ck_p / ck_t if ck_t else 0),
         "| median wall time per request (time to final) | %.0f s |" % med,
         "| median time to first model.py write (preview lower bound) | %s (n=%d) |" % (
             _s(_median(fw)), len(fw)),
         "| median time to first successful build (preview upper bound) | %s (n=%d) |" % (
             _s(_median(fok)), len(fok)),
         *(["| median time to first clean live preview (harness: freecadcmd child, lock "
             "wait) | %s (n=%d of %d) |" % (_s(_median(fp)), len(fp), len(live)),
             "| median time to first clean live preview (production estimate: settled + "
             "%.1f s debounce + build.apply) | %s (n=%d of %d) |" % (
                 PREVIEW_DEBOUNCE_S, _s(_median(fpp)), len(fpp), len(live)),
             "| live previews built / with a failure / skipped (unchanged or not compiling) "
             "| %d / %d / %d |" % (len(pv), pv_bad, pv_skip),
             "| failed previews: script error / check failed / intent.json only "
             "(S49, Studio shows \"in progress\") / not classified "
             "| %d / %d / %d / %d |" % (pv_err, pv_bad - pv_err - pv_intent - pv_unclass,
                                       pv_intent, pv_unclass),
             "| end-of-turn builds held by a live preview in flight (in 1st ok build "
             "and wall times; earlier runs had no previews) | %.1f s total |" % pv_wait]
           if live else ["| live preview (S46) | not measured (run predates S46) |"]),
         "| mean fix rounds per request | %.2f (n=%d) |" % (
             (sum(fixes) / float(len(fixes))) if fixes else 0, len(fixes)),
         "| wall time range | %.0f - %.0f s |" % (walls[0], walls[-1]) if walls else "| - | - |",
         "| total cost | $%.2f |" % cost,
         "| median init_s (spawn -> init record, turn 1) | %s (n=%d) |" % (
             _s(_median(inits), "%.2f s"), len(inits)),
         "| median first_text_s (spawn -> first text, turn 1) | %s (n=%d) |" % (
             _s(_median(texts), "%.2f s"), len(texts)),
         "| in-turn ./check calls (total, all prompts) | %s |" % (
             sum(checks_n) if checks_n else "not measured"),
         "| input tokens incl. cache (total / median per prompt) | %s |" % (
             "%d / %d" % (sum(toks), _median(toks)) if toks else "not measured"),
         "| output tokens (total / median per prompt) | %s |" % (
             "%d / %d (n=%d)" % (sum(otoks), _median(otoks), len(otoks)) if otoks
             else "not measured"),
         "| permission denials (total) | %d |" % denials,
         "| gaps >= %.0f s with no tool activity (S57; causes below) | %s |" % (
             STALL_GAP_S, stall_headline(results)),
         "| claude argv source | %s |" % (", ".join(sources) or "not recorded (run predates S15)"),
         "| addon revision of the run | %s |" % describe_addon(meta.get("addon")),
         *(["| addon rescored against (%s) | %s%s%s |" % (
             meta["rescore_addon"].get("source"), describe_addon(meta["rescore_addon"]),
             {True: "; sha256 matches the run's", False: "; sha256 DIFFERS from the run's"}
             .get(meta["rescore_addon"].get("verified"), ""),
             "; " + meta["rescore_addon"]["note"] if meta["rescore_addon"].get("note") else "")]
           if meta.get("rescore_addon") else []),
         "| builds needing the headless ViewObject patch | %d |" % patched,
         "", "## Plain vs Atech prompts", "",
         "An Atech prompt is one whose expectations run `atech_ports.check` "
         "(`atech_check`); its Atech checks are fitness checks, so `all checks` "
         "= built + all expectation checks + all fitness checks.", "",
         "| group | prompts | built | built 1st attempt | all expectations | all fitness | all checks |",
         "|---|---|---|---|---|---|---|",
         *["| %s | %d | %d/%d | %d/%d | %d/%d | %d/%d | %d/%d |" % (
             g, k, b, k, f, k, e, k, ft, k, a, k)
           for g, k, b, f, e, ft, a in group_rows(results)],
         *edit_rows(results),
         *stall_rows(results),
         "", "## Per prompt", "",
         "| id | prompt | outcome | builds | 1st apply | 1st write s | 1st preview s (prod est.) | 1st ok build s | init s | 1st text s | wall s | $ | in tok | out tok | ./check | objects/solids | whole bound mm | checks | pass | fitness | stalls >%.0f s | render |" % STALL_GAP_S,
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        b = r["final_build"]
        objs = b.get("objects") or []
        sol = sum(o.get("solids", 0) for o in objs)
        wd = b.get("whole_dims_sorted_mm")
        img = "%s/%s/render.png" % (name, r["id"])
        has_img = os.path.isfile(os.path.join(OUT_DIR, img)) and r["built"]
        def _f(k, fmt="%.0f"):
            return "-" if r.get(k) is None else fmt % r[k]
        fa = r.get("first_apply_pass")
        if fa is None and r.get("builds"):
            fa = first_apply_pass(r["builds"][0])
        if "previews" not in r:
            prev = "-"
        elif r.get("first_preview_s") is None:
            prev = "none (%d built)" % len(r.get("previews") or [])
        else:
            prev = "%.0f (%s)" % (r["first_preview_s"], _f("first_preview_prod_s"))
        L.append("| %s | %s | %s | %d | %s | %s | %s | %s | %s | %s | %.0f | %.2f | %s | %s | %s | %s | %s | %d/%d | %s | %s | %s | %s |" % (
            r["id"], r["prompt"], r["outcome"], len(r["builds"]),
            "-" if fa is None else ("yes" if fa else "no"),
            _f("first_write_s"), prev, _f("first_ok_build_s"),
            _f("init_s", "%.2f"), _f("first_text_s", "%.2f"),
            r["wall_s"], r["cost_usd"], _f("input_tokens", "%d"), _f("output_tokens", "%d"),
            _f("check_calls", "%d"),
            "%d/%d" % (len(objs), sol) if objs else "-",
            " x ".join("%g" % d for d in wd) if wd else "-",
            r["checks_passed"], r["checks_total"], "PASS" if r["pass"] else "FAIL",
            ("%d/%d" % (r.get("fitness_passed", 0), r["fitness_total"])
             if r.get("fitness_total") else "-"),
            stall_cell(r),
            "[png](%s)" % img if has_img else "-"))
    L += ["", "## Permission denials by command", ""]
    dn = [(r["id"], d) for r in results for d in r.get("denials") or []]
    if dn:
        L += ["Each denial is an allowlist miss: the agent asked, production's "
              "flags refused. `runs ./check` = the denied command ran the check, "
              "so that check never ran.", "",
              "| id | tool | command | runs ./check |", "|---|---|---|---|"]
        for pid, d in dn:
            L.append("| %s | %s | `%s` | %s |" % (
                pid, d.get("tool") or "?",
                (d.get("command") or "?").replace("|", "\\|").replace("\n", " ")[:160],
                "yes" if d.get("runs_check") else "no"))
    elif denials:
        L.append("%d denial(s); the run predates S46 and did not record the commands."
                 % denials)
    else:
        L.append("None.")
    L += ["", "## Failed checks", ""]
    for r in results:
        bad = [c for c in r["final_build"].get("checks", []) if not c["pass"]]
        if not r["built"]:
            err = (r["final_build"].get("error") or r["outcome"] or "").strip().splitlines()
            L.append("- **%s**: not built - `%s`" % (r["id"], (err[-1] if err else r["outcome"])[:200]))
        for c in bad:
            L.append("- **%s**: %s -> measured `%s`" % (r["id"], c["check"],
                                                       json.dumps(c["detail"])[:200]))
        for c in r["final_build"].get("fitness", []) or []:
            if not c["pass"]:
                L.append("- **%s**: fitness %s -> measured `%s`" % (
                    r["id"], c["check"], json.dumps(c["detail"])[:240]))
    L += ["", "## model.py code signals (final attempt)", "",
          "| id | lines | named params | magic numbers in calls | fuse | cut | checks len(Solids) | removeSplitter | fillet/chamfer | objects | sets colour |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        q = (r["final_build"] or {}).get("code_quality") or {}
        if not q:
            L.append("| %s | - |" % r["id"])
            continue
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["id"], q.get("lines"), q.get("named_params"), q.get("magic_numbers_in_calls"),
            q.get("fuse"), q.get("cut"), q.get("checks_solids"), q.get("removeSplitter"),
            q.get("fillet_or_chamfer"), q.get("objects_added"), q.get("sets_color")))
    return "\n".join(L) + "\n"


# ------------------------------------------------------ addon revision (S41)
def _git(repo, *args):
    """git -C repo <args>, stdout as bytes; raises on failure. Read-only
    commands only (rev-parse, diff, ls-files, archive)."""
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True,
                          check=True).stdout


def _skip_file(rel):
    parts = rel.replace(os.sep, "/").split("/")
    return "__pycache__" in parts or rel.endswith((".pyc", ".pyo"))


def addon_tree_sha256(addon_dir, files=None):
    """sha256 over the addon's files (sorted relative path + content;
    bytecode caches skipped). Two trees with the same hash import the same
    code, whatever git says about them. `files` (relative to addon_dir)
    limits it to what git carries - a live tree's ignored tool caches
    (.pytest_cache, .ruff_cache) are not part of the addon; default: every
    file under addon_dir (a materialized tree has nothing else)."""
    h = hashlib.sha256()
    if files is None:
        files = []
        for root, dirs, names in os.walk(addon_dir):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for n in names:
                rel = os.path.relpath(os.path.join(root, n), addon_dir)
                if not _skip_file(rel):
                    files.append(rel)
    files = [f for f in files if not _skip_file(f)
             and os.path.isfile(os.path.join(addon_dir, f))]
    for rel in sorted(files, key=lambda r: r.replace(os.sep, "/")):
        h.update(rel.replace(os.sep, "/").encode("utf-8") + b"\0")
        with open(os.path.join(addon_dir, rel), "rb") as fh:
            h.update(fh.read())
        h.update(b"\0")
    return h.hexdigest()


def live_library(repo=REPO):
    """The atech-artifacts models directory this checkout's projects/ finds
    (atech_ports' development rule: <repo>/../../atech-artifacts/models),
    or None when there is none (the child then says the library is missing)."""
    c = os.path.normpath(os.path.join(repo, PROJECTS_REL, "..", "..", "..",
                                      "atech-artifacts", "models"))
    return c if os.path.isfile(os.path.join(c, LIBRARY_MARKER)) else None


def _carried(repo, rel):
    return [f for f in _git(repo, "ls-files", "-z", "--cached", "--others",
                            "--exclude-standard", "--", rel).decode("utf-8").split("\0") if f]


def addon_revision(save_dir=None, repo=REPO, addon=ADDON):
    """The addon a run builds with: {path, commit, dirty, sha256, untracked,
    diff, projects_sha256}. With save_dir, a dirty addon's `git diff HEAD`
    goes to save_dir/addon.diff and its untracked files under
    save_dir/addon_untracked/, so materialize_addon() can rebuild it. A git
    failure leaves commit None and says why (never a guessed revision).
    R150: repo/projects/ (the Atech builders the addon imports) is carried
    the same way - in the diff, the untracked files and dirty - but sha256
    stays the addon's own (projects_sha256 is recorded beside it)."""
    rel = os.path.relpath(addon, repo).replace(os.sep, "/")
    info = {"path": rel, "commit": None, "dirty": None, "sha256": None,
            "untracked": [], "diff": None}
    paths = [rel] + ([PROJECTS_REL] if os.path.isdir(os.path.join(repo, PROJECTS_REL)) else [])
    try:
        info["commit"] = _git(repo, "rev-parse", "HEAD").decode().strip()
        # Pinned format: a user's diff.noprefix / diff.external / color.diff
        # would otherwise write a patch materialize_addon cannot apply.
        diff = _git(repo, "diff", "--binary", "--no-ext-diff", "--no-color",
                    "--src-prefix=a/", "--dst-prefix=b/", "HEAD", "--", *paths)
        untracked = [u for u in _git(repo, "ls-files", "--others", "--exclude-standard",
                                     "--", *paths).decode("utf-8").splitlines()
                     if u and not _skip_file(u)]
        carried = _carried(repo, rel)
        pcarried = _carried(repo, PROJECTS_REL) if len(paths) > 1 else []
    except (OSError, subprocess.CalledProcessError) as exc:
        info["error"] = "git: %s" % (getattr(exc, "stderr", None) or exc)
        info["sha256"] = addon_tree_sha256(addon)
        return info
    info["sha256"] = addon_tree_sha256(addon, [
        os.path.relpath(os.path.join(repo, f), addon) for f in carried])
    if pcarried:
        pdir = os.path.join(repo, PROJECTS_REL)
        info["projects_sha256"] = addon_tree_sha256(pdir, [
            os.path.relpath(os.path.join(repo, f), pdir) for f in pcarried])
    info["dirty"] = bool(diff or untracked)
    info["untracked"] = untracked
    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        if diff:
            with open(os.path.join(save_dir, "addon.diff"), "wb") as fh:
                fh.write(diff)
            info["diff"] = "addon.diff"
        for u in untracked:
            dst = os.path.join(save_dir, "addon_untracked", u)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(repo, u), dst)
    return info


def materialize_addon(info, dest, run_dir=None, repo=REPO):
    """Rebuild the addon `info` describes under dest: `git archive` of its
    commit (the repo is not touched), then the run's addon.diff and
    addon_untracked/ when recorded. Returns (addon dir, sha256 matches the
    recorded one: True / False / None when none was recorded).
    R150: repo/projects/ at the same commit comes too (when the commit has
    one), at dest/projects - where acadagent.projects looks from the addon."""
    rel = info.get("path") or os.path.relpath(ADDON, REPO).replace(os.sep, "/")
    paths = [rel]
    try:
        _git(repo, "cat-file", "-e", "%s:%s" % (info["commit"], PROJECTS_REL))
        paths.append(PROJECTS_REL)
    except subprocess.CalledProcessError:
        pass                                    # a commit before projects/ existed
    data = _git(repo, "archive", "--format=tar", info["commit"], "--", *paths)
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")
        else:                                           # pragma: no cover
            tf.extractall(dest)
    if info.get("diff") and run_dir:
        p = subprocess.run(["git", "apply", "--whitespace=nowarn",
                            os.path.join(run_dir, info["diff"])],
                           cwd=dest, capture_output=True, text=True)
        if p.returncode:
            raise RuntimeError("addon.diff does not apply to %s: %s" % (
                info["commit"][:12], p.stderr.strip()))
    extra = os.path.join(run_dir or "", "addon_untracked")
    if run_dir and os.path.isdir(extra):
        shutil.copytree(extra, dest, dirs_exist_ok=True)
    out = os.path.join(dest, rel)
    want = info.get("sha256")
    return out, (addon_tree_sha256(out) == want) if want else None


def resolve_addon(spec, meta, run_dir, dest):
    """--addon-rev -> (addon dir or None for this tree, record for meta).
    spec: "run" (the revision the run recorded), "current", or a git rev.
    A run that recorded nothing is rescored against this tree, and the
    record says so - it is never presented as the run's own addon."""
    recorded = (meta or {}).get("addon")
    if spec == "run" and not (recorded and recorded.get("commit")):
        cur = addon_revision()
        return None, dict(cur, requested="run", source="current tree", note=(
            "the run recorded no addon revision (predates S41): rescored against "
            "the CURRENT tree, which may not be the addon that wrote these files; "
            "pass --addon-rev <commit> to pin one"))
    if spec == "current":
        return None, dict(addon_revision(), requested="current", source="current tree")
    if spec == "run":
        info = dict(recorded)
        addon, ok = materialize_addon(info, dest, run_dir)
        return addon, dict(info, requested="run", source="run's recorded revision",
                           verified=ok, **_projects_record(dest, info))
    commit = _git(REPO, "rev-parse", "--verify", "%s^{commit}" % spec).decode().strip()
    addon, _ = materialize_addon({"commit": commit}, dest)
    return addon, dict({"requested": spec, "source": "git revision", "commit": commit,
                        "dirty": False, "sha256": addon_tree_sha256(addon)},
                       **_projects_record(dest))


def _projects_record(dest, run_info=None):
    """R150: what a materialized tree carries besides the addon - projects/
    (at the commit; plus the run's diff when the run recorded it) and the
    live mesh library it is pointed at. Stated, never implied."""
    pdir = os.path.join(dest, PROJECTS_REL)
    if not os.path.isdir(pdir):
        return {"projects": None, "note": "the commit has no projects/: Atech "
                "prompts cannot import atech_ports at this revision"}
    rec = {"projects": PROJECTS_REL, "projects_sha256_rebuilt": addon_tree_sha256(pdir)}
    notes = []
    want = (run_info or {}).get("projects_sha256")
    if want:
        rec["projects_verified"] = rec["projects_sha256_rebuilt"] == want
    elif run_info is not None:
        notes.append("projects/ taken at the commit: the run predates R150 and did "
                     "not record uncommitted projects/ changes")
    lib = (os.environ.get(LIBRARY_ENV) or "").strip() or live_library()
    rec["library"] = lib
    notes.append("Atech meshes from %s (%s; not revisioned)" % (
        lib, "$%s" % LIBRARY_ENV if (os.environ.get(LIBRARY_ENV) or "").strip()
        else "the live atech-artifacts checkout") if lib else
        "no Atech mesh library found: Atech checks will say the library is missing")
    rec["note"] = "; ".join(notes)
    return rec


def describe_addon(a):
    """One line for the report."""
    if not a or not a.get("commit"):
        return "not recorded" + (" (%s)" % a["error"] if a and a.get("error") else
                                 " (run predates S41)")
    saved = [x for x in ("addon.diff" if a.get("diff") else None,
                         "%d untracked" % len(a["untracked"]) if a.get("untracked") else None)
             if x]
    return "%s%s, addon sha256 %s" % (
        a["commit"][:12], (" + uncommitted changes" + (" (%s)" % ", ".join(saved)
                                                        if saved else ""))
        if a.get("dirty") else "", (a.get("sha256") or "?")[:12])


def resolve_run(spec, tag="baseline"):
    """'baseline_1' / 'round_1' / 'baseline_extra_1' -> (name, tag, n);
    a bare number means <tag>_<n>."""
    spec = str(spec)
    if re.match(r"^\d+$", spec):
        return "%s_%d" % (tag, int(spec)), tag, int(spec)
    m = re.match(r"^([a-z][a-z0-9]*(?:_[a-z][a-z0-9]*)?)_(\d+)$", spec)
    if not m:
        raise ValueError("--rescore wants a run name like baseline_1 (got %r)" % spec)
    return spec, m.group(1), int(m.group(2))


def load_expectations():
    """id -> prompt item, over every prompt set (ids are unique across sets)."""
    out = {}
    for fname in PROMPT_SETS.values():
        path = os.path.join(HERE, fname)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for it in json.load(fh)["prompts"]:
                out[it["id"]] = it
    return out


def rescore_result(r, run_dir, items, build_fn=None, addon=None):
    """Re-build one prompt's saved files. Mutates and returns r.

    first_apply_pass <- model_attempt1.py; built/checks/fitness <- model.py.
    A result with no saved file keeps built=False; agent timings stay.
    `addon`: an addon tree to build with (S41); None = this one.
    R173: when the run sent an edit turn (model_request1.py saved), the
    final model.py is scored against the edit's expectations and the
    first request's model.py against the item's own (`first_request`)."""
    build_fn = build_fn or fc_job
    item = items.get(r["id"]) or {}
    seed = _seed_path(item)
    d = os.path.join(run_dir, r["id"])
    edited = bool(item.get("edit")) and os.path.isfile(os.path.join(d, REQUEST1_FILE))

    def build(src, expect=None, prompt=None):
        ws = tempfile.mkdtemp(prefix="atech-rescore-%s-" % r["id"])
        try:
            shutil.copy(src, os.path.join(ws, "model.py"))
            intent = os.path.join(os.path.dirname(src), "intent.json")
            if os.path.isfile(intent):              # the run's FINAL intent.json
                shutil.copy(intent, os.path.join(ws, "intent.json"))
            job = {"mode": "build", "workspace": ws,
                   "expect": expect if expect is not None else item.get("expect"),
                   "prompt": prompt or r.get("prompt"),
                   "seed": seed, "render": None}
            if addon:
                job["addon"] = addon
            b, crash = build_fn(job)
            if b is None:
                b = {"ok": False, "error": "HARNESS CRASH: %s" % crash, "harness_crash": True}
            return b
        finally:
            shutil.rmtree(ws, ignore_errors=True)

    a1, final = os.path.join(d, "model_attempt1.py"), os.path.join(d, "model.py")
    orig = {"built": r.get("built"), "first": bool(r.get("built")) and len(r.get("builds") or []) == 1,
            "pass": r.get("pass")}
    r["original"] = orig
    b1 = build(a1) if os.path.isfile(a1) else None
    r["first_apply_pass"] = first_apply_pass(b1)
    if edited:
        r["first_request"] = request_record(
            {"builds": None, "fix_rounds": None, "first_ok_build_s": None},
            build(os.path.join(d, REQUEST1_FILE)))
        edit = item["edit"]
        # no edit_attempt1.py = the edit turn never wrote model.py (it is
        # still the request's file): the edit was not made, so it is not
        # built - the live run's edit_not_rewritten / edit_claude_failed
        edit_wrote = os.path.isfile(os.path.join(d, ATTEMPT_FILE[1] % 1))
        bf = build(final, edit.get("expect") or item.get("expect"),
                   "%s\n%s" % (r.get("prompt"), edit["prompt"])) \
            if os.path.isfile(final) and edit_wrote else {}
        if bf:
            bf["code_quality"] = (r.get("final_build") or {}).get("code_quality")
        r["built"] = first_apply_pass(bf)
    elif os.path.isfile(final):
        bf = build(final)
        bf["code_quality"] = (r.get("final_build") or {}).get("code_quality")
        r["built"] = first_apply_pass(bf)
    else:
        bf = {}
        r["built"] = False
    # builds: attempt 1 (+ the final one when it differs) so len()==1 keeps
    # meaning "built on first attempt" in report()
    builds = [b1] if b1 is not None else []
    if not (r["built"] and r["first_apply_pass"]) and bf:
        builds.append(bf)
    r["builds"] = builds
    score_final(r, bf)
    return r


def rescore(spec, tag="baseline", addon_rev="run"):
    """Re-measure a saved run without calling claude. Writes
    <name>_rescore.json/.md; the original run's files are not touched.
    addon_rev (S41): "run" | "current" | a git revision - see resolve_addon."""
    name, rtag, n = resolve_run(spec, tag)
    jpath = os.path.join(OUT_DIR, "%s.json" % name)
    with open(jpath, encoding="utf-8") as fh:
        data = json.load(fh)
    items = load_expectations()
    run_dir = os.path.join(OUT_DIR, name)
    tmp = tempfile.mkdtemp(prefix="atech-rescore-addon-")
    try:
        addon, record = resolve_addon(addon_rev, data["meta"], run_dir, tmp)
        log("rescore against %s: %s%s" % (record["source"], describe_addon(record),
                                          "; " + record["note"] if record.get("note") else ""))
        if record.get("verified") is False:
            log("WARNING: the rebuilt addon's sha256 differs from the run's record")
        if record.get("projects_verified") is False:
            log("WARNING: the rebuilt projects/ sha256 differs from the run's record")
        data["meta"]["rescore_addon"] = record
        _rescore_all(data, run_dir, items, addon)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return _write_rescore(data, name, n, rtag)


def _rescore_all(data, run_dir, items, addon):
    for r in data["results"]:
        rescore_result(r, run_dir, items, addon=addon)
        log("[%s] rescored built=%s first=%s pass=%s fit=%s (was built=%s first=%s)" % (
            r["id"], r["built"], r["first_apply_pass"], r["pass"], r.get("fit_pass"),
            r["original"]["built"], r["original"]["first"]))


def _write_rescore(data, name, n, rtag):
    data["meta"]["rescore_of"] = name
    data["meta"]["rescored"] = time.strftime("%Y-%m-%d %H:%M")
    out = "%s_rescore" % name
    with open(os.path.join(OUT_DIR, "%s.json" % out), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, default=str)
    md = report(data["results"], n, data["meta"], rtag)
    with open(os.path.join(OUT_DIR, "%s.md" % out), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescore", default=None,
                    help="re-score a saved run (baseline_1, or a number = <tag>_<n>)")
    ap.add_argument("--addon-rev", default="run",
                    help="with --rescore: run (the run's recorded addon), current, "
                         "or a git revision (S41)")
    ap.add_argument("--set", default="core", choices=sorted(PROMPT_SETS),
                    help="prompt set: core (the comparable 12) or extra")
    ap.add_argument("--only", default="")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--n", type=int, default=None, help="run number (default: next free)")
    ap.add_argument("--tag", default="baseline", help="output name prefix: baseline | round")
    args = ap.parse_args()
    if not re.match(r"^[a-z][a-z0-9]*$", args.tag):
        sys.exit("--tag must be lowercase letters/digits")
    if not os.path.isfile(FREECADCMD):
        sys.exit("freecadcmd not found at %s (set FREECADCMD)" % FREECADCMD)
    if args.rescore is not None:
        return rescore(args.rescore, args.tag, args.addon_rev)
    with open(os.path.join(HERE, PROMPT_SETS[args.set]), encoding="utf-8") as fh:
        items = json.load(fh)["prompts"]
    if args.set != "core":
        args.tag = "%s_%s" % (args.tag, args.set)
    if args.only:
        want = set(args.only.split(","))
        items = [i for i in items if i["id"] in want]
    n = args.n or _next_n(args.tag)
    name = "%s_%d" % (args.tag, n)
    out_root = os.path.join(OUT_DIR, name)
    os.makedirs(out_root, exist_ok=True)
    # S41: the addon this run builds with, before anything else can change it.
    addon = addon_revision(save_dir=out_root)
    log("addon: %s" % describe_addon(addon))
    # The system prompt as production sends it, for the record (workspace
    # path replaced by a placeholder); also the claude binary production uses.
    probe_root = tempfile.mkdtemp(prefix="atech-eval-argv-")
    try:
        prod = production_argv(probe_root)
        first = prod["first"]
        sp = system_prompt_of(first)
        if sp is not None:
            with open(os.path.join(out_root, "system_prompt.txt"), "w", encoding="utf-8") as fh:
                fh.write(sp.replace(prod["workspace"], PLACEHOLDER))
    except RuntimeError as exc:
        sys.exit(str(exc))
    finally:
        shutil.rmtree(probe_root, ignore_errors=True)
        for d in (locals().get("prod") or {}).get("private_dirs") or []:
            shutil.rmtree(d, ignore_errors=True)
    cli = subprocess.run([first[0], "--version"], capture_output=True, text=True).stdout.strip()
    log("%s: %d prompts, jobs=%d, claude %s, argv from %s: %s" % (
        name, len(items), args.jobs, cli, prod["source"],
        " ".join(flags_of(first)).replace(prod["workspace"], "<ws>")))
    results = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as ex:
        futs = {ex.submit(run_prompt, it, out_root, not args.no_render): it for it in items}
        for f in cf.as_completed(futs):
            it = futs[f]
            try:
                results[it["id"]] = f.result()
            except Exception as exc:                        # noqa: BLE001
                import traceback
                log("[%s] HARNESS ERROR %s" % (it["id"], traceback.format_exc()))
                results[it["id"]] = {"id": it["id"], "prompt": it["prompt"], "outcome":
                                     "harness_error: %s" % exc, "built": False, "pass": False,
                                     "builds": [], "turns": [], "final_build": {},
                                     "checks_passed": 0, "checks_total": 0,
                                     "wall_s": 0, "cost_usd": 0, "fix_rounds": 0}
    ordered = [results[i["id"]] for i in items]
    model = next((t.get("model") for r in ordered for t in r["turns"] if t.get("model")), None)
    meta = {"date": time.strftime("%Y-%m-%d %H:%M"), "model": model, "cli": cli,
            "prompt_set": args.set, "addon": addon,
            "argv_source": sorted({r.get("argv_source") for r in ordered if r.get("argv_source")})}
    with open(os.path.join(OUT_DIR, "%s.json" % name), "w", encoding="utf-8") as fh:
        json.dump({"meta": meta, "results": ordered}, fh, indent=1, default=str)
    md = report(ordered, n, meta, args.tag)
    with open(os.path.join(OUT_DIR, "%s.md" % name), "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md)


if __name__ == "__main__":
    main()
