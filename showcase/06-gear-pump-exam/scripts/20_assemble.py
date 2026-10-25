"""CLYBZP — 立式42型齿轮油泵 assembly.

Components are positioned by explicit transforms (no mates): every part was
modelled in the same world frame, so the placement table below is the whole
assembly definition.

World frame: X = shaft axis (cover side negative, drive side positive),
Y = port axis, Z = up (base bottom Z=0, gear axes Z=104 upper / Z=62 lower).

Layout (from the section drawing):
  cover -65..-31 | gasket -31..-30 | body -30..+32 | gland collar 32..67
  upper axis Z=104: drive shaft 08, gear in the cavity, shaft leaves through
      the stuffing box at the back -> pulley/key/washer/nut outside
  lower axis Z=62: gear shaft 06, ends inside the body's rear bearing bore
"""
from __future__ import annotations

import math
import sys

import pythoncom
from win32com.client import VARIANT

from common import ASM, PARTS, bbox_mm, record

from sw_assembly import add_component
from sw_session import SolidWorksSession

I = ((1, 0, 0), (0, 1, 0), (0, 0, 1))

# 08 drive shaft (local z = axis, +z toward the cover): flip so the long end
# leaves through the back.  local x -> world +Y keeps the keyway on +Y.
R_DRIVE = ((0, 0, -1), (1, 0, 0), (0, -1, 0))

# 06 gear shaft: local z (axis) -> world X, local x -> world Y, local y -> world Z
PHASE = math.radians(360.0 / 14.0 / 2.0)     # half a tooth pitch
C, S = math.cos(PHASE), math.sin(PHASE)
R_GEAR = ((0, 0, 1), (C, -S, 0), (S, C, 0))  # rotated half a pitch to mesh

# key: length -> X, height -> Y, width -> -Z
R_KEY = ((1, 0, 0), (0, 0, 1), (0, -1, 0))
# spring washer: local z (axis) -> world X
R_WASHER = ((0, 0, 1), (1, 0, 0), (0, 1, 0))

Z_UP, Z_LO = 104.0, 62.0
BOLTS = [(32, 104), (-32, 104), (32, 62), (-32, 62), (0, 136), (0, 30)]
DOWELS = [(22.6, 126.6), (-22.6, 39.4)]


def components():
    """(part name, rotation, translation mm) in assembly order."""
    out = [
        ("11_body", I, (0, 0, 0)),
        ("10_gasket", I, (0, 0, 0)),
        ("07_cover", I, (-1, 0, 0)),
        ("08_drive_gear_shaft", R_DRIVE, (0, 0, Z_UP)),
        ("06_gear_shaft", R_GEAR, (-30, 0, Z_LO)),
        ("16_pulley", I, (71, 0, Z_UP)),
        ("17_key_5x5x18", R_KEY, (82, 5.3, Z_UP)),
        ("09_washer_12", R_WASHER, (96.9, 0, Z_UP)),
        ("19_nut_M12", I, (100.1, 0, Z_UP)),
        # relief valve in the cover's lower boss (lower axis)
        ("01_adjust_screw", I, (-93, 0, Z_LO)),
        ("03_locknut_M20", I, (-72, 0, Z_LO)),
        ("02_spring", I, (-59, 0, Z_LO)),
        ("04_steel_ball", I, (-40, 0, Z_LO)),
        # stuffing box on the upper axis
        ("12_packing", I, (20, 0, Z_UP)),
        ("12_packing", I, (30, 0, Z_UP)),
        ("15_packing_gland", I, (40, 0, Z_UP)),
        ("14_gland_nut", I, (56, 0, Z_UP)),
        ("13_locknut_M36", I, (67, 0, Z_UP)),
    ]
    for (y, z) in BOLTS:
        out.append(("18_bolt_M6x18", I, (-47, y, z)))
    for (y, z) in DOWELS:
        out.append(("05_pin_5x20", I, (-43.2, y, z)))
    return out


def transform_data(R, t_mm):
    """16-element ArrayData for `world = R * local + t`.

    R is written here as rows x local columns for readability, but SolidWorks
    reads the first nine elements column-major (probed on SW2023 with a 90 deg
    bolt: a row-major array rotates the opposite way), so transpose on write.
    """
    data = []
    for c in range(3):
        for r in range(3):
            data.append(float(R[r][c]))
    data.extend(float(v) / 1000.0 for v in t_mm)
    data.extend([1.0, 0.0, 0.0, 0.0])
    return data


def set_pose(component, R, t_mm):
    """Apply an assembly pose.

    ArrayData only accepts a SAFEARRAY of doubles; a plain Python list/tuple is
    silently discarded (the setter still returns, the pose stays identity).
    """
    data = transform_data(R, t_mm)
    val = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, data)
    xform = component.Transform2
    if xform is None:
        raise RuntimeError("component has no Transform2")
    xform.ArrayData = val
    try:
        if component.SetTransformAndSolve2(xform):
            return True
    except Exception:
        pass
    component.Transform2 = xform
    return True


def build(session):
    asm = session.new_assembly()
    if asm is None:
        raise RuntimeError("could not create assembly")
    placed = []
    for name, R, t in components():
        comp = add_component(asm, str(PARTS / f"{name}.SLDPRT"), 0, 0, 0,
                             sw=session.sw)
        if comp is None:
            raise RuntimeError(f"add_component failed: {name}")
        try:
            comp.Name2 = f"{name}-{len(placed) + 1}"
        except Exception:
            pass
        set_pose(comp, R, t)
        placed.append((name, t))
    asm.ForceRebuild3(False)
    return asm, placed


def report_pose(asm):
    rows = []
    for comp in (asm.GetComponents(False) or []):
        try:
            t = comp.Transform2
            d = [float(v) for v in t.ArrayData]
            rows.append((comp.Name2, [round(v * 1000, 2) for v in d[9:12]]))
        except Exception:
            rows.append(("?", None))
    return rows


def main() -> int:
    session = SolidWorksSession(visible=True)
    try:
        try:
            session.sw.CloseAllDocuments(True)
        except Exception:
            pass
        asm, placed = build(session)
        comps = asm.GetComponents(False) or []
        print(f"components: {len(comps)} (expected {len(placed)})")
        for name, t in report_pose(asm):
            print(f"   {name:34s} t={t}")
        print("bbox:", bbox_mm(asm))
        ASM.mkdir(parents=True, exist_ok=True)
        ok = session.save(asm, str(ASM / "CLYBZP.SLDASM"))
        print("saved:", ok)
        record("assembly", {"count": len(comps), "bbox": bbox_mm(asm),
                            "saved": bool(ok), "path": str(ASM / "CLYBZP.SLDASM")})
    finally:
        try:
            session.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
