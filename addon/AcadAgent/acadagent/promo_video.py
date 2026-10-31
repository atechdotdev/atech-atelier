"""Assembly / promo video of a design (R730).

After each final build that lands cleanly (Settings: "Make an assembly
video after each build", on by default), and from the Atech menu, the
design becomes a ~25 s video: a hero shot of the finished product, then it
assembles from nothing - the Atech board, each module into its port, each
cable, every printed part, the screws - powers on, and turns on a
turntable with its title. A short Claude reply styles it (title, tagline,
an environment that suits the product, accent, captions, what spins and
glows) when the "style it with Claude" setting is on; without Claude a
keyword pick does.

The work runs outside Studio: collect() writes the job folder (each
visible part's triangles, colour, Atech metadata) on the GUI thread, then
promo/job.py runs in the bundled Python with numpy + PIL - a master and
one worker process per spare core - and writes the movie to
~/Movies/Atech Atelier/. Nothing here changes the document.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
JOB_SCRIPT = os.path.join(HERE, "promo", "job.py")
VIDEO_FOLDER_MAC = "~/Movies/Atech Atelier"
VIDEO_FOLDER = "~/Videos/Atech Atelier"
VIDEO_DIR_ENV = "ATECH_VIDEO_DIR"
SETTING = "assembly_video"                # make one after each build (default True)
STYLE_SETTING = "assembly_video_claude"   # let Claude style it (default True)
SIZE = (1280, 720)


def _log(msg):
    try:
        import FreeCAD
        FreeCAD.Console.PrintLog("AcadAgent video: %s\n" % msg)
    except Exception:                                     # noqa: BLE001
        pass


def enabled(cfg=None):
    if cfg is None:
        from . import settings
        cfg = settings.load()
    return bool(cfg.get(SETTING, True))


def styled_by_claude(cfg=None):
    if cfg is None:
        from . import settings
        cfg = settings.load()
    return bool(cfg.get(STYLE_SETTING, True))


def video_dir():
    d = os.environ.get(VIDEO_DIR_ENV) or os.path.expanduser(
        VIDEO_FOLDER_MAC if sys.platform == "darwin" else VIDEO_FOLDER)
    os.makedirs(d, exist_ok=True)
    return d


def out_base(label):
    safe = "".join(c if (c.isalnum() or c in " ._-") else "_" for c in (label or "")).strip(" .")
    stamp = time.strftime("%Y-%m-%d at %H.%M.%S")
    base = os.path.join(video_dir(), "%s assembly %s" % (safe or "Design", stamp))
    k = 2
    out = base
    while any(os.path.exists(out + ext) for ext in (".mp4", ".mov")):
        out, k = "%s (%d)" % (base, k), k + 1
    return out


def interpreter():
    """[python] with numpy and PIL for the job: the bundle's own Python
    (next to freecadcmd), else None."""
    cands = []
    try:
        import FreeCAD
        home = FreeCAD.getHomePath()
        cands += [os.path.join(home, "bin", n) for n in ("python", "python3")]
    except Exception:                                     # noqa: BLE001
        pass
    try:
        from . import sandbox
        fc = sandbox.find_freecadcmd()
        if fc:
            cands += [os.path.join(os.path.dirname(fc), n) for n in ("python", "python3")]
    except Exception:                                     # noqa: BLE001
        pass
    exe = os.path.basename(sys.executable or "")
    if exe.startswith("python"):
        cands.append(sys.executable)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return [c]
    return None


def director_argv(cfg=None):
    """A `claude -p` argv (prompt on stdin) for the style reply, or None:
    no tools, no MCP, none of the user's settings, one turn."""
    try:
        from . import claude_cli
        exe = claude_cli.find_claude()
        if not exe:
            return None
        have = claude_cli.supported_flags(exe)
    except Exception as exc:                              # noqa: BLE001
        _log("director: %r" % (exc,))
        return None
    argv = [exe, "-p", "--output-format", "json"]
    for flag, vals in (("--max-turns", ("1",)), ("--strict-mcp-config", ()),
                       ("--tools", ("",)), ("--setting-sources", ("",)),
                       ("--disable-slash-commands", ())):
        if flag in have:
            argv += [flag] + list(vals)
    if cfg is None:
        from . import settings
        cfg = settings.load()
    model = (cfg.get("agent_model") or "").strip()
    if model and "--model" in have:
        argv += ["--model", model]
    return argv


# ---------------------------------------------------------------- collect
def _kit():
    kit = os.path.join(HERE, "agent_kit")
    if kit not in sys.path:
        sys.path.append(kit)


def _kind(o):
    if getattr(o, "AtechCableModule", None):
        return "cable"
    role = getattr(o, "AtechRole", None)
    if role:
        return "board" if role == "board" else "module"
    return "body"


def scene_objects(doc):
    """The visible, top-level parts a video shows (as the share image)."""
    from . import export_tools as et
    out = []
    for o in doc.Objects:
        if not et._visible(o) or not et._top_level(o):
            continue
        if et.PREVIOUS in (getattr(o, "Label", "") or ""):
            continue
        if et._is_mesh(o) or et._has_solid(o):
            out.append(o)
    return out


def part_record(o, doc=None):
    """parts.json entry of one object (no triangles)."""
    from . import export_tools as et
    _kit()
    import review
    kind = _kind(o)
    c, tr = et.object_colour(o)
    if c is None:
        c = {"board": review.BOARD, "module": review.MODULE,
             "cable": review.CABLE}.get(kind, review.DEFAULT)
    rec = {"label": o.Label, "kind": kind, "color": [float(x) for x in c[:3]],
           "transparency": int(tr or 0)}
    if kind == "module":
        key = getattr(o, "AtechModule", "") or ""
        rec["module"] = key
        rec["name"] = et.module_name(key) if key else et.display_name(o.Label)
        try:
            rec["ports"] = [int(p) for p in (getattr(o, "AtechPorts", None) or [])]
        except Exception:                                 # noqa: BLE001
            rec["ports"] = []
        ax = getattr(o, "AtechSlideAxis", None)
        if ax is not None:
            rec["slide_axis"] = [float(ax.x), float(ax.y), float(ax.z)]
        rec["slide_out"] = float(getattr(o, "AtechSlideOut", 0.0) or 0.0)
    elif kind == "board":
        rec["name"] = "Atech board"
    elif kind == "cable":
        doc = doc or getattr(o, "Document", None)
        mod = doc.getObject(o.AtechCableModule) if doc is not None else None
        if mod is not None:
            rec["cable_of"] = mod.Label
            key = getattr(mod, "AtechModule", "") or ""
            rec["cable_to"] = et.module_name(key) if key else mod.Label
    return rec


def write_job(job, records, tris):
    """job/scene.npz + parts.json from records and their (T, N) arrays."""
    import numpy as np
    keep = [(r, T, N) for r, (T, N) in zip(records, tris) if T is not None and len(T)]
    if not keep:
        raise ValueError("nothing to draw")
    starts = np.cumsum([0] + [len(T) for _r, T, _N in keep])
    np.savez(os.path.join(job, "scene.npz"),
             T=np.concatenate([np.asarray(T, np.float32) for _r, T, _N in keep]),
             N=np.concatenate([np.asarray(N, np.float32) for _r, _T, N in keep]),
             starts=starts)
    with open(os.path.join(job, "parts.json"), "w", encoding="utf-8") as fh:
        json.dump([r for r, _T, _N in keep], fh)
    return len(keep)


def collect(doc, job):
    """Write the job's scene from the document as it stands (assembled:
    an exploded view is put back first). Returns the number of parts."""
    from . import export_tools as et
    _kit()
    import review
    try:
        et.restore_exploded(doc)
    except Exception:                                     # noqa: BLE001
        pass
    records, tris = [], []
    for o in scene_objects(doc):
        try:
            if et._is_mesh(o):
                T, N = review._mesh_tris(o.Mesh)
            else:
                T, N = review._shape_tris(o.Shape)
        except Exception as exc:                          # noqa: BLE001
            _log("%s: %r" % (o.Label, exc))
            continue
        records.append(part_record(o, doc))
        tris.append((T, N))
    return write_job(job, records, tris)


def fitted_after(ws):
    try:
        with open(os.path.join(ws, "intent.json"), encoding="utf-8") as fh:
            v = json.load(fh).get("fitted_after") or []
        return [str(x) for x in v] if isinstance(v, list) else []
    except (OSError, ValueError, AttributeError, TypeError):
        return []


def context(doc, ws=None, request=None, cfg=None):
    from . import settings
    cfg = settings.load() if cfg is None else cfg
    ctx = {"title": getattr(doc, "Label", "") or "", "request": request or "",
           "fitted_after": fitted_after(ws) if ws else [],
           "size": list(SIZE), "supersample": 2, "fps": 24,
           "interpreter": interpreter(), "out_base": out_base(getattr(doc, "Label", ""))}
    if styled_by_claude(cfg):
        ctx["director_argv"] = director_argv(cfg)
    return ctx


# ---------------------------------------------------------------- job
class VideoJob(object):
    """One running video: its folder and master process. poll() reads its
    progress; cancel() stops it and its workers."""

    def __init__(self, doc, ws=None, request=None, job_root=None):
        py = interpreter()
        if not py:
            raise RuntimeError("no Python with numpy for the video job")
        self.label = getattr(doc, "Label", "") or "Design"
        self.job = tempfile.mkdtemp(prefix="atech-video-", dir=job_root)
        n = collect(doc, self.job)
        ctx = context(doc, ws, request)
        ctx["interpreter"] = py
        with open(os.path.join(self.job, "context.json"), "w", encoding="utf-8") as fh:
            json.dump(ctx, fh)
        env = _job_env()
        self.proc = subprocess.Popen(py + [JOB_SCRIPT, self.job], env=env, cwd=self.job,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
        self.t0 = time.time()
        _log("job %s: %d parts, pid %d" % (self.job, n, self.proc.pid))

    def _read(self, name):
        try:
            with open(os.path.join(self.job, name), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def poll(self):
        """(state, info): ("running", progress dict) / ("done", result) /
        ("failed", result or {})."""
        res = self._read("result.json")
        if res is not None:
            return ("done" if res.get("ok") else "failed"), res
        if self.proc.poll() is not None:
            return "failed", {"error": "the video job stopped (exit %s)" % self.proc.returncode}
        return "running", self._read("progress.json") or {"stage": "starting"}

    def cancel(self):
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    def cleanup(self):
        shutil.rmtree(self.job, ignore_errors=True)


def _job_env():
    env = dict(os.environ)
    for k in ("PYTHONHOME", "PYTHONPATH"):
        env.pop(k, None)
    return env


def progress_text(info):
    st = (info or {}).get("stage")
    if st == "styling":
        return "styling it"
    if st == "drawing":
        total = info.get("total") or 0
        done = info.get("done") or 0
        return "drawing %d%%" % (100 * done // total) if total else "drawing"
    if st == "encoding":
        return "saving the movie"
    return "starting"


def reveal(path):
    """Show the file in Finder / the file manager."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except OSError as exc:
        _log("reveal: %r" % (exc,))


def open_file(path):
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except OSError as exc:
        _log("open: %r" % (exc,))


# ---------------------------------------------------------------- chat
class Runner(object):
    """The chat panel's videos: one job per document (a newer build's
    video replaces one still running), its progress on a card in the
    transcript, and a notice with Play / Show in Finder when it is ready.

    panel: needs _add(widget), show_notice(title, body, actions) and a
    ToolCard class passed as `card_cls`."""

    POLL_MS = 1000

    def __init__(self, panel, card_cls):
        from PySide6 import QtCore
        self.panel, self.card_cls = panel, card_cls
        self.jobs = {}                     # doc key -> (VideoJob, card)
        self.timer = QtCore.QTimer()
        self.timer.setInterval(self.POLL_MS)
        self.timer.timeout.connect(self.poll)
        try:
            app = QtCore.QCoreApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(self.cancel_all)
        except Exception:                                 # noqa: BLE001
            pass

    def start(self, doc, ws=None, request=None, key=None):
        """Start a video of `doc`. Returns the VideoJob, or None (with a
        notice) when it cannot start."""
        key = key or getattr(doc, "Name", "") or id(doc)
        old = self.jobs.pop(key, None)
        if old is not None:
            old[0].cancel()
            old[0].cleanup()
            old[1].set_status("replaced by a newer build", "idle")
        try:
            job = VideoJob(doc, ws=ws, request=request)
        except Exception as exc:                          # noqa: BLE001
            _log("cannot start: %r" % (exc,))
            self.panel.show_notice(
                "No assembly video this time",
                "The video of %s could not be started: %s." % (
                    getattr(doc, "Label", "the design"),
                    "there is nothing to show yet" if "nothing to draw" in str(exc)
                    else "this installation has no Python with numpy for it"),
                detail=str(exc))
            return None
        card = self.card_cls("Assembly video", getattr(doc, "Label", ""), mono=False)
        card.set_status("starting", "run")
        self.panel._add(card)
        self.jobs[key] = (job, card)
        if not self.timer.isActive():
            self.timer.start()
        return job

    def poll(self):
        for key, (job, card) in list(self.jobs.items()):
            state, info = job.poll()
            if state == "running":
                txt = progress_text(info)
                try:
                    card.set_status(txt, "run")
                    env = (info or {}).get("environment")
                    title = (info or {}).get("title")
                    if title and not card.body.text():
                        card.append("%s%s" % (title, (" - %s stage" % env) if env else ""))
                except RuntimeError:                      # card deleted (chat cleared)
                    pass
                continue
            self.jobs.pop(key, None)
            if state == "done":
                self._done(job, card, info)
            else:
                self._failed(job, card, info)
            job.cleanup()
        if not self.jobs:
            self.timer.stop()

    def _done(self, job, card, res):
        path = res.get("path")
        try:
            card.set_status("ready", "ok")
            card.append("%s s, saved to %s" % (res.get("duration"), path))
        except RuntimeError:
            pass
        self.panel.show_notice(
            "Assembly video ready: %s" % (res.get("title") or job.label),
            "%s s, from the finished product to every part going together. "
            "Saved in %s." % (res.get("duration"), os.path.dirname(path or "")),
            actions=[("Play", lambda _=False, p=path: open_file(p)),
                     ("Show in Finder" if sys.platform == "darwin" else "Show in folder",
                      lambda _=False, p=path: reveal(p))])

    def _failed(self, job, card, res):
        try:
            card.set_status("failed", "fail")
        except RuntimeError:
            pass
        _log("job failed: %s" % (res or {}).get("error"))
        self.panel.show_notice(
            "The assembly video could not be made",
            "Your design is fine; only the video of %s failed." % job.label,
            detail=str((res or {}).get("error") or "")[-1500:])

    def cancel_all(self):
        for job, _card in self.jobs.values():
            job.cancel()
            job.cleanup()
        self.jobs = {}
