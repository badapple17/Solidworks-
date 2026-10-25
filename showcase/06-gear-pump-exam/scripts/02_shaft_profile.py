"""Dump cylindrical-face profile (radius vs axial position) for the two shafts."""
from __future__ import annotations

import json
import sys

from common import PARTS, WORK

from sw_connect import get_com_member, open_document
from sw_session import SolidWorksSession


def cylinder_profile(model):
    rows = []
    for body in (model.GetBodies2(0, False) or []):
        for face in (body.GetFaces() or []):
            surf = get_com_member(face, 'GetSurface')
            if surf is None:
                continue
            try:
                if not get_com_member(surf, 'IsCylinder'):
                    continue
            except Exception:
                continue
            try:
                params = get_com_member(surf, 'CylinderParams')
                ox, oy, oz, ax, ay, az, radius = [float(v) for v in params]
            except Exception:
                continue
            box = get_com_member(face, 'GetBox')
            if not box:
                continue
            z0, z1 = box[2], box[5]
            rows.append(
                {
                    "r": round(radius * 1000, 3),
                    "axis": [round(ax, 4), round(ay, 4), round(az, 4)],
                    "origin": [round(ox * 1000, 2), round(oy * 1000, 2), round(oz * 1000, 2)],
                    "z": [round(z0 * 1000, 2), round(z1 * 1000, 2)],
                    "area": round(float(get_com_member(face, "GetArea") or 0) * 1e6, 1),
                }
            )
    rows.sort(key=lambda r: (r["z"][0], -r["r"]))
    return rows


def planar_profile(model):
    """Axis-normal planar faces: position + normal, to find shoulders/ends."""
    rows = []
    for body in (model.GetBodies2(0, False) or []):
        for face in (body.GetFaces() or []):
            surf = get_com_member(face, 'GetSurface')
            if surf is None or not get_com_member(surf, 'IsPlane'):
                continue
            try:
                p = [float(v) for v in get_com_member(surf, 'PlaneParams')]
            except Exception:
                continue
            nx, ny, nz = p[0], p[1], p[2]
            if abs(nz) < 0.99:
                continue
            z = p[3] * 1000 if abs(nz) > 0 else None
            box = get_com_member(face, 'GetBox')
            area = round(float(get_com_member(face, "GetArea") or 0) * 1e6, 1)
            if area < 1.0:
                continue
            rows.append({"z": round(box[5] * 1000, 2) if nz < 0 else round(box[2] * 1000, 2),
                         "nz": round(nz, 3), "area": area})
    rows.sort(key=lambda r: r["z"])
    return rows


def main() -> int:
    session = SolidWorksSession(visible=True)
    sw = session.sw
    out = {}
    for name in ["06_gear_shaft", "08_drive_gear_shaft"]:
        model = open_document(sw, str(PARTS / f"{name}.SLDPRT"), raise_on_error=True)
        model.ForceRebuild3(False)
        cyl = cylinder_profile(model)
        plan = planar_profile(model)
        out[name] = {"cylinders": cyl, "planes": plan}
        print(f"\n=== {name} ===")
        for r in cyl:
            print(f"  R{r['r']:8.2f}  z={r['z'][0]:8.2f}..{r['z'][1]:8.2f}  area={r['area']:10.1f}")
        print("  -- axis-normal planes --")
        for p in plan:
            print(f"     z={p['z']:8.2f}  nz={p['nz']:+.2f} area={p['area']:.1f}")
    (WORK / "shaft_profiles.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
