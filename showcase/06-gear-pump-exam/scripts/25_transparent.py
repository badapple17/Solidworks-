"""CLYBZP — transparent colour-coded assembly.

Copies the finished compact assembly to CLYBZP_TRANSPARENT.SLDASM and colours
each component: the housing parts become translucent so the gear pair, shafts
and stuffing box read through them; every internal part gets a solid colour.

The original CLYBZP.SLDASM is never modified.
"""
from __future__ import annotations

import shutil
import sys

from common import ASM, bbox_mm, record
from sw_appearance import (
    SW_THIS_CONFIGURATION,
    get_material_property_values,
    material_values,
    material_variant,
    rgb01,
)
from sw_connect import open_document
from sw_session import SolidWorksSession

SRC = ASM / "CLYBZP.SLDASM"
DST = ASM / "CLYBZP_TRANSPARENT.SLDASM"

# part -> (colour, transparency 0..1).  Transparency applies to the housing
# only; everything inside stays opaque so it reads through the glass.
STYLE = {
    "11_body": ("#C8CDD2", 0.80),
    "07_cover": ("#D98CA8", 0.75),
    "10_gasket": ("#4F86C6", 0.45),
    "08_drive_gear_shaft": ("#2E5FA8", 0.0),
    "06_gear_shaft": ("#2E5FA8", 0.0),
    "16_pulley": ("#3FA34D", 0.0),
    "17_key_5x5x18": ("#F2C200", 0.0),
    "09_washer_12": ("#BFC4C8", 0.0),
    "19_nut_M12": ("#4A4F55", 0.0),
    "01_adjust_screw": ("#BFC4C8", 0.0),
    "03_locknut_M20": ("#D99A22", 0.0),
    "02_spring": ("#C62828", 0.0),
    "04_steel_ball": ("#BFC4C8", 0.0),
    "12_packing": ("#D84315", 0.0),
    "15_packing_gland": ("#D99A22", 0.0),
    "14_gland_nut": ("#C98A1E", 0.0),
    "13_locknut_M36": ("#B8860B", 0.0),
    "18_bolt_M6x18": ("#C9CDD1", 0.0),
    "05_pin_5x20": ("#C9CDD1", 0.0),
}


def part_name(comp):
    try:
        name = comp.Name2 or ""
    except Exception:
        name = ""
    return name.rsplit("-", 1)[0] if "-" in name else name


def apply(comp, color, transparency):
    """Set colour + transparency at component level; returns (ok, readback)."""
    values = material_values(color, transparency=transparency)
    packed = material_variant(values)
    wrote = False
    try:
        wrote = bool(comp.SetMaterialPropertyValues2(packed, SW_THIS_CONFIGURATION, None))
    except Exception:
        wrote = False
    if not wrote:
        try:
            comp.MaterialPropertyValues = packed
            wrote = True
        except Exception:
            wrote = False
    readback = get_material_property_values(comp)
    rgb_ok = readback is not None and all(
        abs(a - b) <= 0.02 for a, b in zip(readback[:3], rgb01(color))
    )
    alpha_ok = readback is not None and abs(readback[7] - transparency) <= 0.02
    return wrote and rgb_ok, readback, rgb_ok, alpha_ok


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
            raise RuntimeError("could not open the transparent copy")
        asm.ForceRebuild3(False)

        done, failed = [], []
        for comp in (asm.GetComponents(False) or []):
            name = part_name(comp)
            style = STYLE.get(name)
            if style is None:
                print(f"  WARN no colour rule for {name!r} - left default")
                continue
            ok, readback, rgb_ok, alpha_ok = apply(comp, *style)
            done.append((name, style, ok))
            print(f"  {name:22s} {style[0]} a={style[1]:.2f} "
                  f"rgb_ok={rgb_ok} alpha_ok={alpha_ok} read={readback}")
            if not ok:
                failed.append(name)

        asm.ForceRebuild3(False)
        print(f"coloured: {len(done)}   failed: {failed if failed else 'none'}")
        print("bbox:", bbox_mm(asm))
        ok = session.save(asm)
        print("saved:", ok, DST)

        from sw_review import save_preview
        preview_dir = ASM.parent / "preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        previews = []
        for view in ("isometric", "bottom", "right"):
            bmp = save_preview(asm, preview_dir / f"transparent_{view}.bmp",
                               view_name=view)
            previews.append(bmp)
            print("preview:", bmp)

        record("transparent", {"path": str(DST), "saved": bool(ok),
                               "count": len(done), "failed": failed,
                               "bbox": bbox_mm(asm), "previews": previews})
    finally:
        try:
            session.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
