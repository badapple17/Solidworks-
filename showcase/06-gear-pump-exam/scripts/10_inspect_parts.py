"""Ground-truth inspection: every saved part -> bodies, volume, cylindrical faces."""
from __future__ import annotations

import json
import sys

from common import PARTS, record, bbox_mm

from sw_connect import get_com_member, open_document
from sw_session import SolidWorksSession

AX = {0: "X", 1: "Y", 2: "Z"}


def inspect(model):
    rows = []
    vol = 0.0
    for body in (model.GetBodies2(0, False) or []):
        try:
            mp = body.GetMassProperties(1.0)
            vol += float(mp[3]) * 1e9
        except Exception:
            pass
        for face in (body.GetFaces() or []):
            surf = get_com_member(face, "GetSurface")
            if surf is None:
                continue
            try:
                if not get_com_member(surf, "IsCylinder"):
                    continue
                params = [float(v) for v in get_com_member(surf, "CylinderParams")]
            except Exception:
                continue
            r = round(params[6] * 1000, 2)
            ax = max(range(3), key=lambda i: abs(params[3 + i]))
            box = [round(float(v) * 1000, 2) for v in get_com_member(face, "GetBox")]
            span = round(box[ax + 3] - box[ax], 2)
            rows.append({"d": round(r * 2, 2), "axis": AX[ax],
                         "at": [round(box[ax + 3], 1) if False else
                                round((box[ax] + box[ax + 3]) / 2, 1)],
                         "span": [box[ax], box[ax + 3]], "len": span})
    rows.sort(key=lambda x: (x["axis"], x["d"]))
    return rows, round(vol, 1)


def main() -> int:
    session = SolidWorksSession(visible=True)
    sw = session.sw
    out = {}
    names = sorted(p.stem for p in PARTS.glob("*.SLDPRT") if not p.name.startswith("~$"))
    for name in names:
        model = open_document(sw, str(PARTS / f"{name}.SLDPRT"), silent=True,
                              raise_on_error=False)
        if model is None:
            out[name] = {"error": "open failed"}
            continue
        try:
            rows, vol = inspect(model)
            bb = bbox_mm(model)
            out[name] = {"bbox": bb, "volume_mm3": vol, "cyl": rows}
            print(f"\n=== {name}  bbox={bb}  vol={vol}  cyl={len(rows)}")
            for r in rows:
                print(f"    D{r['d']:>7} {r['axis']} span={r['span']} len={r['len']}")
        finally:
            title = model.GetTitle
            sw.CloseDoc(title)
    (PARTS.parent / "inspect_parts.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    record("inspect_parts", {"count": len(out)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
