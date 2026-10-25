"""Import the 7 supplied STEP standard parts, save as SLDPRT, record measurements."""
from __future__ import annotations

import json
import sys

from common import ASM, OUT, PARTS, STD, bbox_mm, body_count, record, size_mm

from sw_connect import open_document, save_document
from sw_session import SolidWorksSession
from sw_review import collect_geometry_measurements

FILES = [
    ("06_gear_shaft", "6-齿轮轴.STEP"),
    ("08_drive_gear_shaft", "8-传动齿轮轴.STEP"),
    ("17_key_5x5x18", "GB／T1096-2003普通平键A型5x5×18.STEP"),
    ("05_pin_5x20", "GB／T119.1-2000圆柱销A型5×20.STEP"),
    ("18_bolt_M6x18", "GB／T5782-2000六角头螺栓 M6×18.STEP"),
    ("09_washer_12_asm", "GB／T93-1987标准型弹性垫圈(装配)12×6．21.STEP"),
    ("09_washer_12", "GB／T93-1987标准型弹性垫圈(零件)12×6．21.STEP"),
]


def main() -> int:
    session = SolidWorksSession(visible=True)
    sw = session.sw
    results = {}
    for name, fname in FILES:
        src = STD / fname
        model = open_document(sw, str(src), silent=True, raise_on_error=True)
        if model is None:
            print(f"[FAIL] {name}: could not open {fname}")
            return 1
        try:
            model.ForceRebuild3(False)
        except Exception:
            pass
        dest = PARTS / f"{name}.SLDPRT"
        save_document(model, str(dest))
        info = {
            "src": fname,
            "file": str(dest),
            "size_mm": size_mm(model),
            "bbox_mm": bbox_mm(model),
            "bodies": body_count(model),
        }
        try:
            m = collect_geometry_measurements(model)
            info["volume_mm3"] = m.get("volume_mm3")
        except Exception as exc:
            info["volume_error"] = str(exc)
        results[name] = info
        print(f"[OK] {name}: {info['size_mm']} bodies={info['bodies']} vol={info.get('volume_mm3')}")
        title = model.GetTitle
        sw.CloseDoc(title)
    (OUT / "import_measurements.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    record("import_std", results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
