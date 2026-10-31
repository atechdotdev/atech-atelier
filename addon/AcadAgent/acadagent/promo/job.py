"""Promo video job: one folder in, one movie out.

    <python> job.py <job folder>             the master
    <python> job.py <job folder> <k> <n>     worker k of n (the master starts them)

The folder holds scene.npz (every part's triangles, assembled), parts.json
and context.json (written by acadagent/promo_video.py in the app). The
master asks the director for the style (spec.json), starts the workers,
which each draw every n-th frame into frames/, encodes the movie and
writes result.json. progress.json says how far it got, all along.

No FreeCAD, no Qt: the bundled Python with numpy and PIL.
"""
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(os.path.dirname(HERE), "agent_kit")
for p in (HERE, KIT):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import director  # noqa: E402
import mux  # noqa: E402
import overlay  # noqa: E402
import render  # noqa: E402
import stage  # noqa: E402
import timeline  # noqa: E402

THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS")


def _read(job, name, default=None):
    try:
        with open(os.path.join(job, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write(job, name, data):
    tmp = os.path.join(job, name + ".part")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, os.path.join(job, name))


def _log(job, msg):
    try:
        with open(os.path.join(job, "job.log"), "a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except OSError:
        pass


def load(job):
    """(Scene, parts, context) of a job folder."""
    parts = _read(job, "parts.json", [])
    ctx = _read(job, "context.json", {})
    z = np.load(os.path.join(job, "scene.npz"))
    starts = list(z["starts"])
    for k, p in enumerate(parts):            # sizes for the director
        T = z["T"][starts[k]:starts[k + 1]].reshape(-1, 3)
        if len(T):
            p.setdefault("size", [float(v) for v in (T.max(0) - T.min(0))])
    return render.Scene(parts, z["T"], z["N"], starts), parts, ctx


def plan_for(job, scene, ctx):
    spec = _read(job, "spec.json") or director.defaults(ctx, scene.parts)
    return timeline.Plan(scene, spec, ctx, fps=int(ctx.get("fps") or timeline.FPS)), spec


def frame_path(job, f):
    return os.path.join(job, "frames", "%05d.jpg" % f)


def render_frames(job, frames, scene=None, ctx=None):
    """Draw `frames` (indices) into frames/. Skips ones already drawn."""
    if scene is None:
        scene, _parts, ctx = load(job)
    plan, spec = plan_for(job, scene, ctx)
    env = stage.environment(spec.get("environment"), timeline.hexrgb(spec.get("accent")))
    W, H = [int(v) for v in (ctx.get("size") or (1280, 720))]
    ss = int(ctx.get("supersample") or 2)
    key = np.asarray(env["key"], float)
    key = key / np.linalg.norm(key)
    shadows = {}
    from PIL import Image
    for f in frames:
        out = frame_path(job, f)
        if os.path.isfile(out):
            continue
        st = plan.state(f)
        sk = st.get("shadow_key")
        shadow = None
        if sk is not None:
            shadow = shadows.get(sk)
            if shadow is None:
                xf = {k: {"hidden": True} for k in range(len(scene.parts))} if sk == "empty" else {}
                T, _N, O = scene.pose(xf)
                shadow = shadows[sk] = render.Shadow(scene, T, O, key)
        img = render.render(scene, st["xf"], st["cam"], env, W, H, ss, t=st["t"],
                            glow=st["glow"], shadow=shadow)
        im = overlay.draw((np.clip(img, 0, 1) * 255).astype(np.uint8), plan, st, env, spec, W, H)
        tmp = out + ".part"
        im.save(tmp, "JPEG", quality=93, subsampling=0)
        os.replace(tmp, out)


def _interpreter(ctx):
    return list(ctx.get("interpreter") or [sys.executable])


def worker_count(ctx):
    n = ctx.get("workers")
    if n:
        return max(1, int(n))
    return max(1, min(8, (os.cpu_count() or 4) - 2))


def master(job):
    t0 = time.time()
    _write(job, "progress.json", {"stage": "styling", "done": 0, "total": 0})
    scene, parts, ctx = load(job)
    if not os.path.isfile(os.path.join(job, "spec.json")):
        spec = director.direct(ctx, parts, log=lambda m: _log(job, m))
        _write(job, "spec.json", spec)
        _log(job, "spec (%s): %s" % (spec.get("source"), json.dumps(spec)[:600]))
    plan, spec = plan_for(job, scene, ctx)
    total = plan.frames
    os.makedirs(os.path.join(job, "frames"), exist_ok=True)
    n = min(worker_count(ctx), total)
    env = dict(os.environ)
    for v in THREAD_VARS:
        env[v] = "1"
    procs = []
    me = os.path.abspath(__file__)
    for k in range(n):
        with open(os.path.join(job, "worker%d.log" % k), "w") as err:
            procs.append(subprocess.Popen(_interpreter(ctx) + [me, job, str(k), str(n)], env=env,
                                          stdout=subprocess.DEVNULL, stderr=err))
    _log(job, "%d frames, %d workers, %s, %s" % (total, n, spec.get("environment"),
                                                  spec.get("title")))
    while True:
        done = len([f for f in os.listdir(os.path.join(job, "frames")) if f.endswith(".jpg")])
        _write(job, "progress.json", {"stage": "drawing", "done": done, "total": total,
                                      "title": spec.get("title"),
                                      "environment": spec.get("environment")})
        if all(p.poll() is not None for p in procs):
            break
        time.sleep(0.5)
    bad = [k for k, p in enumerate(procs) if p.returncode != 0]
    missing = [f for f in range(total) if not os.path.isfile(frame_path(job, f))]
    if missing:
        raise RuntimeError("%d frames were not drawn (workers %s failed); see worker logs"
                           % (len(missing), bad))
    _write(job, "progress.json", {"stage": "encoding", "done": total, "total": total,
                                  "title": spec.get("title")})
    W, H = [int(v) for v in (ctx.get("size") or (1280, 720))]
    out_base = ctx.get("out_base") or os.path.join(job, "assembly")
    path = mux.encode(os.path.join(job, "frames"), plan.fps, out_base, W, H)
    poster = out_base + ".jpg"
    pf = min(total - 1, int(plan.t_hero * 0.75 * plan.fps))
    try:
        import shutil
        shutil.copyfile(frame_path(job, pf), poster)
    except OSError:
        poster = None
    res = {"ok": True, "path": path, "poster": poster, "seconds": round(time.time() - t0, 1),
           "frames": total, "duration": round(total / float(plan.fps), 1),
           "title": spec.get("title"), "environment": spec.get("environment"),
           "styled_by": spec.get("source")}
    _write(job, "result.json", res)
    _log(job, "done %s" % json.dumps(res))
    if not ctx.get("keep_frames"):
        import shutil
        shutil.rmtree(os.path.join(job, "frames"), ignore_errors=True)
    return res


def main(argv):
    job = os.path.abspath(argv[1])
    if len(argv) >= 4:
        k, n = int(argv[2]), int(argv[3])
        scene, _parts, ctx = load(job)
        plan, _spec = plan_for(job, scene, ctx)
        # interleaved, so every worker shares the slow and the fast stretches
        render_frames(job, list(range(k, plan.frames, n)), scene, ctx)
        return 0
    try:
        master(job)
        return 0
    except Exception:                                   # noqa: BLE001
        err = traceback.format_exc()
        _log(job, err)
        _write(job, "result.json", {"ok": False, "error": err[-3000:]})
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
