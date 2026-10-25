"""Final gate: reopen the three assemblies and verify what is on disk.

- CLYBZP: 26 components, compact bbox
- CLYBZP_EXPLODED: bbox spread along X by the explode offsets
- CLYBZP_TRANSPARENT: same bbox as compact, 11_body still translucent
"""
from __future__ import annotations

import sys

from common import ASM, bbox_mm, record, size_mm
from sw_appearance import get_material_property_values
from sw_connect import open_document
from sw_session import SolidWorksSession

EXPECT = {
    "CLYBZP.SLDASM": [-93.0, -52.5, 0.0, 110.1, 52.5, 156.5],
    "CLYBZP_EXPLODED.SLDASM": [-458.0, -52.5, 0.0, 430.1, 52.5, 156.5],
    "CLYBZP_TRANSPARENT.SLDASM": [-93.0, -52.5, 0.0, 110.1, 52.5, 156.5],
}


def main() -> int:
    session = SolidWorksSession(visible=True)
    report = {}
    try:
        for name, expect in EXPECT.items():
            path = ASM / name
            doc = open_document(session.sw, str(path), raise_on_error=True)
            doc.ForceRebuild3(False)
            comps = doc.GetComponents(False) or []
            box = bbox_mm(doc)
            ok = all(abs(a - b) <= 0.3 for a, b in zip(box, expect))
            row = {"components": len(comps), "bbox": box, "expected": expect,
                   "match": ok}
            if name == "CLYBZP_TRANSPARENT.SLDASM":
                body = next((c for c in comps
                             if (c.Name2 or "").startswith("11_body")), None)
                vals = get_material_property_values(body) if body else None
                row["body_appearance"] = [round(v, 3) for v in vals[:9]] if vals else None
                row["body_translucent"] = bool(vals and vals[7] > 0.5)
                ok = ok and row["body_translucent"]
            report[name] = row
            print(f"{name}: comps={len(comps)} bbox={box} match={ok}")
            if "body_appearance" in row:
                print("   11_body appearance:", row["body_appearance"],
                      "translucent:", row["body_translucent"])
            session.close(doc)
        record("verify_final", report)
        print("ALL PASS:", all(r["match"] for r in report.values()))
        return 0 if all(r["match"] for r in report.values()) else 1
    finally:
        # finish() 关掉本次打开的全部文档并退出本进程启动的实例：
        # 装配体的依赖零件不会因为 CloseDoc(装配体) 而卸载，会继续占文件锁。
        try:
            session.finish()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
