"""CLYBZP — exploded-view file.

Copies the finished compact assembly and offsets every component along its
removal direction.  The original CLYBZP.SLDASM is never modified: the copy is
opened, moved and saved as CLYBZP_EXPLODED.SLDASM.

Offsets are given in millimetres and added to the component translation
(elements 9..11 of IMathTransform.ArrayData, which are in metres).
"""
from __future__ import annotations

import shutil
import sys

import pythoncom
from win32com.client import VARIANT

from common import ASM, bbox_mm, record
from sw_connect import open_document
from sw_session import SolidWorksSession

SRC = ASM / "CLYBZP.SLDASM"
DST = ASM / "CLYBZP_EXPLODED.SLDASM"

# part name -> (dx, dy, dz) mm.  Cover side goes -X, drive side +X; the key is
# lifted radially out of its keyway.
OFFSETS = {
    # ---- cover side (-X): disassembly order, cover last among its fasteners
    "10_gasket": (-55.0, 0.0, 0.0),
    "07_cover": (-110.0, 0.0, 0.0),
    "06_gear_shaft": (-35.0, 0.0, 0.0),
    "18_bolt_M6x18": (-165.0, 0.0, 0.0),
    "05_pin_5x20": (-205.0, 0.0, 0.0),
    "04_steel_ball": (-235.0, 0.0, 0.0),
    "02_spring": (-275.0, 0.0, 0.0),
    "03_locknut_M20": (-320.0, 0.0, 0.0),
    "01_adjust_screw": (-365.0, 0.0, 0.0),
    # ---- drive side (+X): stuffing box outwards
    "15_packing_gland": (110.0, 0.0, 0.0),
    "14_gland_nut": (150.0, 0.0, 0.0),
    "13_locknut_M36": (200.0, 0.0, 0.0),
    "16_pulley": (240.0, 0.0, 0.0),
    "17_key_5x5x18": (10.0, 38.0, 0.0),
    "09_washer_12": (290.0, 0.0, 0.0),
    "19_nut_M12": (320.0, 0.0, 0.0),
}
PACKING_OFFSETS = ((-1e9, 25.0, (50.0, 0.0, 0.0)),
                   (25.0, 1e9, (80.0, 0.0, 0.0)))

# parts that stay where they are: the body anchors the view, the drive shaft
# carries the exploded parts and is the reference the eye follows
FIXED = {"11_body", "08_drive_gear_shaft"}


def part_name(comp):
    try:
        name = comp.Name2 or ""
    except Exception:
        name = ""
    return name.rsplit("-", 1)[0] if "-" in name else name


def pose_mm(comp):
    return [round(float(v) * 1000.0, 3) for v in comp.Transform2.ArrayData[9:12]]


def set_pose(comp, data):
    xform = comp.Transform2
    xform.ArrayData = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                              [float(v) for v in data])
    try:
        if comp.SetTransformAndSolve2(xform):
            return True
    except Exception:
        pass
    comp.Transform2 = xform
    return True


def offset_for(name, tx):
    for lo, hi, delta in PACKING_OFFSETS:
        if name == "12_packing" and lo <= tx < hi:
            return delta
    return OFFSETS.get(name)


def main() -> int:
    if not SRC.exists():
        raise FileNotFoundError(SRC)
    shutil.copy2(SRC, DST)
    print("copied:", SRC.name, "->", DST.name)

    session = SolidWorksSession(visible=True)
    try:
        try:
            session.sw.CloseAllDocuments(True)
        except Exception:
            pass
        asm = open_document(session.sw, str(DST), raise_on_error=True)
        if asm is None:
            raise RuntimeError("could not open the exploded-view copy")
        asm.ForceRebuild3(False)

        moved, kept = [], []
        for comp in (asm.GetComponents(False) or []):
            name = part_name(comp)
            data = [float(v) for v in comp.Transform2.ArrayData]
            tx = data[9] * 1000.0
            delta = offset_for(name, tx)
            if name in FIXED:
                kept.append(name)
                continue
            if delta is None:
                print(f"  WARN no offset rule for {name!r} - left in place")
                kept.append(name)
                continue
            before = pose_mm(comp)
            data[9] += delta[0] / 1000.0
            data[10] += delta[1] / 1000.0
            data[11] += delta[2] / 1000.0
            set_pose(comp, data)
            after = pose_mm(comp)
            moved.append((name, before, after))
            print(f"  {name:22s} {before} -> {after}")

        asm.ForceRebuild3(False)
        print(f"moved: {len(moved)}   unmoved: {len(kept)}")
        print("bbox:", bbox_mm(asm))
        ok = session.save(asm)
        print("saved:", ok, DST)

        from sw_review import save_preview
        preview_dir = ASM.parent / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        png = preview_dir / "exploded_iso.png"
        save_preview(asm, png, view_name="isometric")
        print("preview:", png)

        record("exploded", {"path": str(DST), "saved": bool(ok),
                            "count": len(moved), "bbox": bbox_mm(asm),
                            "preview": str(png)})
    finally:
        try:
            session.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
