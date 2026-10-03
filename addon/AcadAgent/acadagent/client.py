"""client — talk to the agent backend (opencode, for now).

This is the ONLY module that knows the backend's wire format. When we replace
opencode with our own harness, this file changes and nothing else does.

THREADING
    Every network call happens on a worker thread. Results reach the GUI as Qt
    signals. Nothing here touches a widget.

MEASURED WIRE FORMAT (opencode 1.18.18, read off its live OpenAPI spec at
/doc and confirmed against a live reply on 2026-09-24)
    POST /api/session                    -> {"data":{"id":"ses_..."}}
    POST /api/session/{id}/prompt        <- {"prompt":{"text":"..."}}
                                         -> {"data":{"admittedSeq":N}}  (async)
    GET  /api/session/{id}/message       -> {"data":[SessionMessage, ...]}
    PUT  /auth/{providerID}              <- {"type":"api","key":"..."}

    A SessionMessage has NO "info" wrapper, NO "parts" key and NO "role" key -
    an earlier docstring here claimed all three and the parser built on it
    matched nothing, ever. The real shape (SessionMessageAssistant):
        {"id":"msg_...", "type":"assistant", "agent":..., "model":...,
         "time":{"created":N,"completed":N}, "finish":"...",
         "error":{"type":"unknown","message":"..."},      (only on failure)
         "content":[ {"type":"text","id":..,"text":".."}
                   | {"type":"reasoning",...}
                   | {"type":"tool","id":..,"name":"..","state":{...}} ]}
    Role is type=="assistant". Tool parts carry "name" and "state", and a
    completed state's output is state["content"], a list of
    {"type":"text","text":".."} - not a plain "output" string.

    The prompt body accepts exactly {id, prompt, delivery, resume}
    (additionalProperties:false). A top-level "model" key is NOT part of it
    and was silently dropped, which is why the Settings model field never
    took effect. Model selection needs POST /api/session/{id}/model - see Q4.

    The prompt is ADMITTED, not answered: the reply arrives later. We poll
    /message rather than hold an SSE stream open, because polling is trivially
    cancellable and this panel is not latency-critical.
"""
import json
import urllib.error
import urllib.request

from PySide6 import QtCore


def _req(url, method="GET", payload=None, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else {}


class Backend:
    """Stateless helper around the HTTP surface."""

    def __init__(self, base_url):
        self.base = base_url.rstrip("/")

    def health(self, timeout=8):
        _req("%s/api/health" % self.base, timeout=timeout)
        return True

    def models(self, timeout=20):
        """Return [(providerID, modelID)] the backend actually offers."""
        out = []
        data = _req("%s/api/provider" % self.base, timeout=timeout)
        for prov in data.get("data", []):
            pid = prov.get("id")
            models = prov.get("models")
            if isinstance(models, dict):
                names = list(models.keys())
            elif isinstance(models, list):
                names = [m.get("id") if isinstance(m, dict) else m
                         for m in models]
            else:
                names = []
            for name in names:
                if pid and name:
                    out.append((pid, name))
        return out

    def new_session(self, timeout=30):
        d = _req("%s/api/session" % self.base, "POST", {}, timeout)
        sid = (d.get("data") or {}).get("id")
        if not sid:
            raise RuntimeError("backend returned no session id: %s" % d)
        return sid

    def send(self, sid, text, provider=None, model=None, timeout=60,
             images=None):
        """Admit a prompt, optionally with viewport captures attached.

        provider/model are accepted but NOT sent. The prompt schema is
        additionalProperties:false over {id, prompt, delivery, resume}; a
        top-level "model" key was accepted with HTTP 200 and silently
        ignored. Sending it looked like model selection worked. The
        signature keeps both arguments so panel.py and the swap-the-backend
        seam stay unchanged - see Q4.

        images: a list of PNG paths. Each becomes a prompt.files[] entry
        carrying a data: URI - see attachment() for why that is the only
        form that works.
        """
        prompt = {"text": text}
        if images:
            prompt["files"] = [attachment(p) for p in images]
        return _req("%s/api/session/%s/prompt" % (self.base, sid),
                    "POST", {"prompt": prompt}, timeout)

    def messages(self, sid, timeout=30):
        d = _req("%s/api/session/%s/message" % (self.base, sid),
                 timeout=timeout)
        return d.get("data", d) if isinstance(d, dict) else d


#: Extension -> MIME. The backend requires an explicit mime; guessing is not
#: an option and a wrong guess fails ASYNCHRONOUSLY (see attachment()).
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp"}


def attachment(path, name=None):
    """Build a prompt.files[] entry for an image, as a data: URI.

    MEASURED 2026-09-24 against live opencode 1.18.18. THREE URI forms were
    tried with the same 64x64 PNG and the same question. All three were
    ADMITTED with HTTP 200 - the difference only showed up later, in the
    assistant record:

        {"uri": "file:///tmp/shot.png"} -> finish="error",
             error="OpenAI Chat media must contain valid base64"
        {"uri": "/tmp/shot.png"}        -> finish="error", same message
        {"uri": "data:image/png;base64,<b64>"} -> finish="stop", and the
             model correctly named the colour of a bar drawn in the image,
             so it genuinely received the pixels.

    Two things worth keeping in mind:

    1. The server does NOT read the file for you. It never opens a path. The
       bytes must travel inline. "file://" is a perfectly well-formed URI and
       is silently useless here.
    2. The failure is ASYNCHRONOUS and its text mentions base64, not URIs -
       so a path-based attachment looks like it worked (HTTP 200, prompt
       admitted) and only fails ~10s later with a message pointing somewhere
       else entirely. This is the T5 shape: the wrong call looks right.

    Raises:
        ValueError: unreadable file, or a type we have no MIME for. We do
            not invent a MIME - a wrong one fails async and confusingly.
    """
    import base64
    import os

    ext = os.path.splitext(path)[1].lower()
    mime = _MIME.get(ext)
    if mime is None:
        raise ValueError(
            "no known MIME type for %r; supported: %s"
            % (ext or path, ", ".join(sorted(_MIME))))

    with open(path, "rb") as fh:
        raw = fh.read()
    if not raw:
        raise ValueError("refusing to attach an empty file: %s" % path)

    b64 = base64.b64encode(raw).decode("ascii")
    return {"uri": "data:%s;base64,%s" % (mime, b64),
            "mime": mime,
            "name": name or os.path.basename(path)}


def _is_assistant(msg):
    """Role is carried by "type", not by a "role" key under "info"."""
    return msg.get("type") == "assistant"


def _error_of(msg):
    """The backend's OWN account of what went wrong, or None.

    SessionErrorUnknown is {"type":"unknown","message":"..."}. When this is
    present the backend has already named the cause, so guessing one after a
    timeout is strictly worse information.
    """
    err = msg.get("error")
    if isinstance(err, dict):
        return (err.get("message") or "").strip() or None
    return None


def _texts(msg):
    """Pull assistant text out of a message record."""
    out = []
    for p in msg.get("content", []) or []:
        if p.get("type") == "text":
            t = (p.get("text") or "").strip()
            if t:
                out.append(t)
    return out


def _tool_output(state):
    """Flatten a completed tool state's content[] into readable text."""
    chunks = []
    for c in state.get("content", []) or []:
        if isinstance(c, dict) and c.get("type") == "text":
            t = (c.get("text") or "").strip()
            if t:
                chunks.append(t)
    return "\n".join(chunks)


def _tools(msg):
    """Pull tool invocations out of a message record."""
    out = []
    for p in msg.get("content", []) or []:
        if p.get("type") != "tool":
            continue
        state = p.get("state") or {}
        out.append({
            "name": p.get("name") or "tool",
            "status": state.get("status") or "",
            "input": state.get("input") or {},
            "output": _tool_output(state),
        })
    return out


class ChatWorker(QtCore.QThread):
    """Send a prompt, then poll until the assistant replies.

    Emits:
        chunk(str)         - assistant text as it appears
        tool(dict)         - a tool invocation seen in the reply
        finished_ok(str)   - the final assistant text ("" if none)
        failed(str)        - a NAMED failure. Never a silent stall.
    """

    chunk = QtCore.Signal(str)
    tool = QtCore.Signal(dict)
    finished_ok = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, base_url, sid, text, provider=None, model=None,
                 poll_seconds=180, parent=None, images=None):
        super().__init__(parent)
        self._api = Backend(base_url)
        self._sid = sid
        self._text = text
        self._provider = provider
        self._model = model
        self._deadline = poll_seconds
        self._cancelled = False
        # Optional viewport captures. Appended LAST so existing positional
        # callers in panel.py keep working unchanged.
        self._images = list(images or [])

    def cancel(self):
        self._cancelled = True

    def run(self):
        import time

        try:
            before = len(self._api.messages(self._sid))
        except urllib.error.URLError as exc:
            self.failed.emit("cancelled" if self._cancelled else
                             "cannot reach backend: %s" % exc.reason)
            return
        except Exception as exc:                          # noqa: BLE001
            self.failed.emit("cancelled" if self._cancelled else
                             "%s: %s" % (type(exc).__name__, exc))
            return
        # R24: Stop pressed while the first request was in flight - never
        # send the prompt after the user cancelled it.
        if self._cancelled:
            self.failed.emit("cancelled")
            return

        try:
            self._api.send(self._sid, self._text, self._provider, self._model,
                           images=self._images)
        except ValueError as exc:
            # A bad attachment. Say so HERE, where the cause is known -
            # sending it anyway produces an async "valid base64" error ~10s
            # later that points at the wrong thing entirely.
            self.failed.emit("cannot attach the capture: %s" % exc)
            return
        except urllib.error.HTTPError as exc:
            body = exc.read()[:300].decode("utf-8", "replace")
            self.failed.emit("backend rejected the prompt (HTTP %d): %s"
                             % (exc.code, body))
            return
        except Exception as exc:                          # noqa: BLE001
            self.failed.emit("cancelled" if self._cancelled else
                             "%s: %s" % (type(exc).__name__, exc))
            return

        seen_text = []
        seen_tools = set()
        waited = 0.0
        step = 1.0
        while waited < self._deadline and not self._cancelled:
            time.sleep(step)
            waited += step
            try:
                msgs = self._api.messages(self._sid)
            except Exception:                             # noqa: BLE001
                continue
            fresh = msgs[before:]
            done = False
            for m in fresh:
                if not _is_assistant(m):
                    continue
                for t in _tools(m):
                    key = (t["name"], json.dumps(t["input"], sort_keys=True)[:200])
                    if key not in seen_tools:
                        seen_tools.add(key)
                        self.tool.emit(t)
                for t in _texts(m):
                    if t not in seen_text:
                        seen_text.append(t)
                        self.chunk.emit(t)
                # The backend named the failure. Report it and stop - do not
                # poll on to a timeout and then guess at a cause.
                named = _error_of(m)
                if named:
                    self.failed.emit(named)
                    return
                if m.get("finish") or (m.get("time") or {}).get("completed"):
                    done = True
            if done and seen_text:
                break

        if self._cancelled:
            self.failed.emit("cancelled")
            return
        if not seen_text:
            self.failed.emit(
                "no reply after %.0fs. The prompt was accepted but the model "
                "produced nothing - usually a missing API key or an "
                "unconfigured model. Check Settings." % waited)
            return
        self.finished_ok.emit("\n\n".join(seen_text))
