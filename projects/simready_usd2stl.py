"""simready_usd2stl — one USD stage -> one binary STL in millimetres, Y up.

    python -I simready_usd2stl.py <root.usd> <out.stl> <dir with usd-core>

Run by simready.convert() in a child Python, so Pixar's pxr never loads into
Atelier. Prints one line SIMREADY_STL={json}: triangles, meshes, the stage's
units and up axis, size_mm; or {"error": ...}.

Which geometry: every UsdGeom.Mesh the stage DRAWS - instance proxies
included (SimReady instances its meshes), invisible prims and the guide and
proxy purposes (collision shapes, helpers) left out. Points go through the
prim's local-to-world transform, polygons are fan-triangulated, left-handed
meshes have their winding flipped. Frame: metersPerUnit -> mm; a Z-up stage
is turned Y up as (x, z, -y), the turn the Atech library import uses.
"""
import json
import struct
import sys


def main(root, out, usd_dir):
    sys.path.insert(0, usd_dir)
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(root, Usd.Stage.LoadAll)
    if stage is None:
        return {"error": "USD could not open %s" % root}
    mpu = UsdGeom.GetStageMetersPerUnit(stage) or 0.01
    up = str(UsdGeom.GetStageUpAxis(stage))
    s = float(mpu) * 1000.0
    keep = {UsdGeom.Tokens.default_, UsdGeom.Tokens.render}
    xc = UsdGeom.XformCache(Usd.TimeCode.Default())
    pred = Usd.TraverseInstanceProxies(Usd.PrimDefaultPredicate)
    tris, meshes, skipped = [], 0, 0
    for prim in Usd.PrimRange(stage.GetPseudoRoot(), pred):
        if not prim.IsA(UsdGeom.Mesh):
            continue
        img = UsdGeom.Imageable(prim)
        if (img.ComputeVisibility() == UsdGeom.Tokens.invisible
                or img.ComputePurpose() not in keep):
            skipped += 1
            continue
        mesh = UsdGeom.Mesh(prim)
        pts = mesh.GetPointsAttr().Get()
        counts = mesh.GetFaceVertexCountsAttr().Get()
        idx = mesh.GetFaceVertexIndicesAttr().Get()
        if not pts or not counts or not idx:
            continue
        m = xc.GetLocalToWorldTransform(prim)
        w = [m.Transform(p) for p in pts]
        if up.upper() == "Z":
            w = [(p[0] * s, p[2] * s, -p[1] * s) for p in w]
        else:
            w = [(p[0] * s, p[1] * s, p[2] * s) for p in w]
        flip = mesh.GetOrientationAttr().Get() == UsdGeom.Tokens.leftHanded
        if m.GetDeterminant3() < 0:
            flip = not flip
        k = 0
        for c in counts:
            face = idx[k:k + c]
            k += c
            for j in range(1, c - 1):
                a, b, d = w[face[0]], w[face[j]], w[face[j + 1]]
                tris.append((a, d, b) if flip else (a, b, d))
        meshes += 1
    if not tris:
        return {"error": "no drawn mesh in %s (%d skipped)" % (root, skipped)}
    lo = [min(t[i][a] for t in tris for i in range(3)) for a in range(3)]
    hi = [max(t[i][a] for t in tris for i in range(3)) for a in range(3)]
    with open(out, "wb") as fh:
        fh.write(b"NVIDIA SimReady asset via Atech Atelier".ljust(80, b" "))
        fh.write(struct.pack("<I", len(tris)))
        pack = struct.Struct("<12fH").pack
        for a, b, c in tris:
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            n = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
            fh.write(pack(nx / n, ny / n, nz / n, *a, *b, *c, 0))
    return {"triangles": len(tris), "meshes": meshes, "skipped": skipped,
            "meters_per_unit": mpu, "up_axis": up,
            "size_mm": [round(h - l, 2) for l, h in zip(lo, hi)]}


if __name__ == "__main__":
    try:
        rep = main(*sys.argv[1:4])
    except Exception as exc:                           # noqa: BLE001
        rep = {"error": "%s: %s" % (type(exc).__name__, exc)}
    print("SIMREADY_STL=" + json.dumps(rep))
    sys.stdout.flush()
