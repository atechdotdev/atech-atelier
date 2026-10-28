"""Build projects/simready_index.json: what is in NVIDIA's SimReady dataset
(huggingface.co/datasets/nvidia/simready-assets, CC BY 4.0), so Atelier
can search and size its assets without downloading them.

    PYTHONPATH=<dir with usd-core> python projects/build_simready_index.py [--workers 16]

For every asset folder at one pinned dataset revision it reads ONLY the root
layer (about 20 KB; payloads are not composed) for its SimReady_Metadata:
extents, mass, type, Wikidata id, licence. The extents are converted to
millimetres in Atelier's frame (Y up, see simready.to_library_extents) and
are the dataset's own numbers; the installed part is measured again from its
mesh. Re-run to pick up a newer dataset revision.
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import simready  # noqa: E402


def _root_meta(name, rev, tmp):
    from pxr import Sdf, UsdGeom  # noqa: F401
    files = simready.asset_files(name, rev)
    roots = [f for f in files if simready.is_root_usd(name, f["path"])]
    if not roots:
        return name, {"error": "no root USD"}
    root = roots[0]
    p = os.path.join(tmp, name + ".usd")
    with simready._retrying(simready.file_url(root["path"], rev), timeout=60) as r:
        data = r.read()
    with open(p, "wb") as fh:
        fh.write(data)
    layer = Sdf.Layer.FindOrOpen(p)
    md = dict(layer.customLayerData.get("SimReady_Metadata", {}) or {})
    # USD's documented fallback when a layer does not say: centimetres.
    mpu = float(layer.pseudoRoot.GetInfo("metersPerUnit")) \
        if layer.pseudoRoot.HasInfo("metersPerUnit") else 0.01
    up = str(layer.pseudoRoot.GetInfo("upAxis")) \
        if layer.pseudoRoot.HasInfo("upAxis") else "Y"
    ext = md.get("asset_extents")
    entry = {
        "root": root["path"][len(name) + 1:],
        "type": str(md.get("asset_type") or md.get("category") or ""),
        "mass_kg": round(float(md["mass"]), 4) if md.get("mass") else None,
        "qcode": str(md.get("qcode") or "") or None,
        "licence": str(md.get("asset_license") or ""),
        "thumb": next((f["path"][len(name) + 1:] for f in files
                       if f["path"].endswith("_thumbnail.png")), None),
        "bytes": sum(f["size"] for f in files if simready.needed(name, f["path"])),
    }
    if ext is not None and mpu:
        entry["size_mm"] = simready.to_library_extents(
            [float(v) for v in ext], mpu, up)
    try:
        os.remove(p)
    except OSError:
        pass
    return name, entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fresh", action="store_true",
                    help="ignore the existing index (default: keep its entries "
                         "when it is at the same revision)")
    a = ap.parse_args()
    rev = simready.latest_revision()
    names = simready.list_remote(rev)
    if a.limit:
        names = names[:a.limit]
    out, errors = {}, {}
    if not a.fresh and os.path.isfile(simready.INDEX):
        with open(simready.INDEX, encoding="utf-8") as fh:
            old = json.load(fh)
        if old.get("revision") == rev:
            out = {n: e for n, e in old["assets"].items() if n in names}
            print("resuming: %d already indexed" % len(out), flush=True)
    names = [n for n in names if n not in out]
    tmp = tempfile.mkdtemp(prefix="simready_index_")
    with cf.ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(_root_meta, n, rev, tmp): n for n in names}
        for i, f in enumerate(cf.as_completed(futs), 1):
            n = futs[f]
            try:
                name, e = f.result()
                (errors if "error" in e else out)[name] = e
            except Exception as exc:                   # noqa: BLE001
                errors[n] = {"error": repr(exc)}
            if i % 100 == 0:
                print("%d/%d" % (i, len(names)), flush=True)
    index = {
        "dataset": simready.DATASET,
        "revision": rev,
        "licence": "CC-BY-4.0",
        "count": len(out),
        "assets": dict(sorted(out.items())),
    }
    with open(simready.INDEX, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=0, sort_keys=False)
        fh.write("\n")
    print("wrote %s: %d assets, %d errors" % (simready.INDEX, len(out), len(errors)))
    for n, e in sorted(errors.items())[:20]:
        print("  %s: %s" % (n, e["error"]))


if __name__ == "__main__":
    main()
