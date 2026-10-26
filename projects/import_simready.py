"""import_simready - bring the modules of the atech-module-simready dataset
into the library: models/stl/<module>.stl and models/glb/<slug>.glb.

    SIMREADY_DIR=<dataset snapshot> RENDERS_DIR=<renders glb_plain dir> \\
        freecadcmd projects/import_simready.py        # from the repository root

SOURCES
    SIMREADY_DIR is a snapshot of huggingface.co/datasets/atechdev/
    atech-module-simready (CC BY 4.0) at REVISION; only its mjcf/ folders are
    read. RENDERS_DIR is glb_plain/ of atech-module-renders RELEASE
    (atech_module_glb.zip). Every file is checked before it is used: each
    STL against the dataset's bill of materials (.metadata, sha256 per file),
    each GLB against the sha256 the dataset's MJCF records as its visual
    source. A mismatch stops the import; nothing is guessed.

WHAT IS WRITTEN
    STL: the dataset's per-material STLs of one module merged into one mesh,
    in the library frame (mm, +y up, outer face toward -z). The dataset frame
    is the renders' GLB frame turned z-up (metres, connector at the origin,
    PCB underside on z = 0, outer face toward +y), so
        library = 1000 * (x, z, -y) + (10 * cells + 0.15, -2.54, 10.0)
    which is board_look's offset rule exactly: the GLB origin lands at
    x = 10 mm per port + 0.15, y = -2.54, z = 10.0 for every module.
    GLB: the release file, copied unchanged, for a module with Atech CAD. A
    DERIVED module (no Atech CAD; the dataset builds it from a module shell
    plus placeholder parts) has no GLB anywhere, so one is written here from
    the same STLs: plain float32, GLB frame, one mesh per material, the
    shell's materials taken from the shell's own GLB by name and the
    placeholder parts coloured with the MJCF's rgba.
"""
import glob
import hashlib
import json
import os
import re
import struct

import numpy as np

REVISION = "020ea47813ef1f965718c71e0d7ef73cf42d1c4e"
RELEASE = "v1.7"

#: library name -> (dataset asset, GLB slug, port cells, derived shell GLB).
#: Ids are the library's (temp_humidity, not aht20); the four modules new
#: here keep the Atech SDK catalog id the dataset uses.
MODULES = {
    "button": ("atech_button", "button", 1, None),
    "light": ("atech_neopixel", "led-grid", 1, None),
    "temp_humidity": ("atech_aht20", "temp-sensor", 1, None),
    "orientation": ("atech_icm40608", "orientation-sensor", 1, None),
    "distance_sensor": ("atech_distance_sensor", "distance-sensor", 1, None),
    "dc_motor": ("atech_dc_motor", "dc-motor", 1, None),
    "screen": ("atech_st7735_tft", "screen", 2, None),
    "speaker": ("atech_speaker", "speaker", 2, None),
    "knob": ("atech_rotary_encoder", "knob", 2, None),
    "microphone": ("atech_microphone", "microphone", 2, None),
    "pir": ("atech_pir", "pir", 1, "button"),
    "scd40_air_quality": ("atech_scd40_air_quality", "scd40-air-quality", 1, "button"),
    "robot_arm": ("atech_robot_arm_integrator", "robot-arm", 2, "screen"),
    "stepper_motor": ("atech_stepper_motor", "stepper-motor", 2, "screen"),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_stl(path):
    """(n, 3, 3) float64 triangles of a binary STL."""
    with open(path, "rb") as fh:
        b = fh.read()
    n = struct.unpack("<I", b[80:84])[0]
    if len(b) != 84 + 50 * n:
        raise SystemExit("%s: not a binary STL" % path)
    rec = np.frombuffer(b, dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]),
                        count=n, offset=84)
    return rec["v"].reshape(n, 3, 3).astype(np.float64)


def write_stl(path, T, header):
    T = np.asarray(T, dtype=np.float64)
    nrm = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    nrm = np.divide(nrm, ln, out=np.zeros_like(nrm), where=ln > 0)
    rec = np.zeros(len(T), dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    rec["n"] = nrm
    rec["v"] = T.reshape(-1, 9)
    with open(path, "wb") as fh:
        fh.write(header.encode("ascii")[:80].ljust(80, b" "))
        fh.write(struct.pack("<I", len(T)))
        fh.write(rec.tobytes())


def bom(asset_dir):
    """{relative path: sha256} from the dataset's bill of materials."""
    with open(os.path.join(asset_dir, ".metadata",
                           "com.nvidia.simready.packaging.bom.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    out = {it["relative_path"]: it["hash"]["sha256"] for it in data.get("items", [])}
    if not out:
        raise SystemExit("%s: bill of materials lists no files" % asset_dir)
    return out


def mjcf(asset_dir, asset):
    """(text, {stl stem: rgba}) of the asset's MJCF."""
    with open(os.path.join(asset_dir, "mjcf", asset + ".xml"), encoding="utf-8") as fh:
        text = fh.read()
    rgba = {}
    for stem, c in re.findall(r'mesh="%s_(\w+?)_cad_mesh" rgba="([^"]+)"' % asset, text):
        rgba[stem] = [float(v) for v in c.split()]
    return text, rgba


def custom(text, key):
    m = re.search(r'<text name="atech:%s" data="([^"]*)"' % re.escape(key), text)
    return m.group(1) if m else None


def parts(asset_dir, asset, sums):
    """[(material stem, triangles in metres, dataset frame)], checked."""
    out = []
    for p in sorted(glob.glob(os.path.join(asset_dir, "mjcf", "meshes", asset, "*.stl"))):
        rel = os.path.relpath(p, asset_dir)
        if sums.get(rel) != sha256(p):
            raise SystemExit("%s: sha256 differs from the bill of materials" % rel)
        out.append((os.path.splitext(os.path.basename(p))[0], read_stl(p)))
    if not out:
        raise SystemExit("%s: no meshes" % asset)
    return out


def to_library(T, cells):
    """Dataset frame (m, z-up) -> library STL frame (mm, y-up)."""
    L = np.stack([T[..., 0], T[..., 2], -T[..., 1]], axis=-1) * 1000.0
    return L + np.array([10.0 * cells + 0.15, -2.54, 10.0])


def to_glb(T):
    """Dataset frame -> the renders' GLB frame (m, y-up, outer face -z)."""
    return np.stack([T[..., 0], T[..., 2], -T[..., 1]], axis=-1)


def glb_materials(path):
    with open(path, "rb") as fh:
        b = fh.read()
    cl = struct.unpack("<I", b[12:16])[0]
    js = json.loads(b[20:20 + cl].decode("utf-8"))
    return {m.get("name"): m for m in js.get("materials", [])}


def write_glb(path, mesh_parts, shell_mats, rgba):
    """Plain float32 GLB: one mesh + node per material, no transforms."""
    gl = {"asset": {"version": "2.0", "generator": "atech import_simready"},
          "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
          "materials": [], "accessors": [], "bufferViews": [], "buffers": []}
    blob = bytearray()

    def view(data, target):
        while len(blob) % 4:
            blob.append(0)
        gl["bufferViews"].append({"buffer": 0, "byteOffset": len(blob),
                                  "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(gl["bufferViews"]) - 1

    for stem, T in mesh_parts:
        P = to_glb(T).reshape(-1, 3).astype(np.float32)
        idx = np.arange(len(P), dtype=np.uint32)
        mat = dict(shell_mats.get(stem) or {})
        if not mat:
            c = rgba.get(stem)
            if c is None:
                raise SystemExit("%s: no material and no rgba for %r" % (path, stem))
            mat = {"pbrMetallicRoughness": {"baseColorFactor": c, "metallicFactor": 0.0,
                                            "roughnessFactor": 0.6}}
            if c[3] < 1.0:
                mat["alphaMode"] = "BLEND"
        mat.pop("extensions", None)
        for k in ("baseColorTexture", "metallicRoughnessTexture"):
            mat.get("pbrMetallicRoughness", {}).pop(k, None)
        for k in ("normalTexture", "occlusionTexture", "emissiveTexture"):
            mat.pop(k, None)
        mat["name"] = stem
        gl["materials"].append(mat)
        pv = view(P.tobytes(), 34962)
        iv = view(idx.tobytes(), 34963)
        gl["accessors"].append({"bufferView": pv, "componentType": 5126, "count": len(P),
                                "type": "VEC3", "min": P.min(0).tolist(),
                                "max": P.max(0).tolist()})
        gl["accessors"].append({"bufferView": iv, "componentType": 5125,
                                "count": len(idx), "type": "SCALAR"})
        gl["meshes"].append({"name": stem, "primitives": [{
            "attributes": {"POSITION": len(gl["accessors"]) - 2},
            "indices": len(gl["accessors"]) - 1,
            "material": len(gl["materials"]) - 1}]})
        gl["nodes"].append({"name": stem, "mesh": len(gl["meshes"]) - 1})
        gl["scenes"][0]["nodes"].append(len(gl["nodes"]) - 1)
    gl["buffers"].append({"byteLength": len(blob)})
    js = json.dumps(gl, separators=(",", ":")).encode("utf-8")
    js += b" " * (-len(js) % 4)
    blob += b"\0" * (-len(blob) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A))
        fh.write(js)
        fh.write(struct.pack("<II", len(blob), 0x004E4942))
        fh.write(bytes(blob))


def main():
    sim = os.environ.get("SIMREADY_DIR")
    ren = os.environ.get("RENDERS_DIR")
    if not sim or not ren:
        raise SystemExit("set SIMREADY_DIR and RENDERS_DIR (see the docstring)")
    models = os.path.join(os.getcwd(), "models")
    if not os.path.isfile(os.path.join(models, "presets.yaml")):
        raise SystemExit("run from the repository root")
    record = {"dataset": "huggingface.co/datasets/atechdev/atech-module-simready",
              "revision": REVISION, "renders": "atechdotdev/atech-module-renders@" + RELEASE,
              "modules": {}}
    for name, (asset, slug, cells, shell) in MODULES.items():
        d = os.path.join(sim, asset)
        text, rgba = mjcf(d, asset)
        mp = parts(d, asset, bom(d))
        source = custom(text, "visual:source")
        T = np.concatenate([to_library(t, cells) for _, t in mp])
        stl = os.path.join(models, "stl", name + ".stl")
        write_stl(stl, T, "atech %s from %s@%s" % (name, asset, REVISION[:12]))
        glb = os.path.join(models, "glb", slug + ".glb")
        if shell is None:
            src = os.path.join(ren, slug + ".glb")
            if sha256(src) != custom(text, "visual:sha256"):
                raise SystemExit("%s: %s differs from the dataset's visual source"
                                 % (name, src))
            with open(src, "rb") as fi, open(glb, "wb") as fo:
                fo.write(fi.read())
        else:
            if not (source or "").startswith("derived:"):
                raise SystemExit("%s: dataset does not mark it derived" % name)
            write_glb(glb, mp, glb_materials(os.path.join(ren, shell + ".glb")), rgba)
        lo, hi = T.reshape(-1, 3).min(0), T.reshape(-1, 3).max(0)
        record["modules"][name] = {
            "asset": asset, "glb": slug + ".glb", "cells": cells,
            "derived": shell is not None, "visual_source": source,
            "size_mm": [round(float(v), 3) for v in hi - lo],
            "stl_sha256": sha256(stl), "glb_sha256": sha256(glb)}
        print("%-18s %-28s %s" % (name, asset, record["modules"][name]["size_mm"]))
    with open(os.path.join(models, "SIMREADY.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, sort_keys=True)
        fh.write("\n")


main()
