"""07 泵盖, 10 垫片, 14 压盖螺母, 15 填料压盖."""
from __future__ import annotations

import math
import sys

from build_lib import (
    capsule_sketch,
    reset_sw,
    boss_cyl_x,
    circle_on_yz,
    cut_cyl_x,
    extrude_hex,
    plane_at_x,
    revolve_profile,
    save_part,
)
from common import record

from sw_connect import mm
from sw_part import extrude_boss, extrude_cut, sketch, sketch_circle, sketch_line
from sw_session import SolidWorksSession

Z_UP, Z_LO = 104.0, 62.0      # gear axes
BOLTS = [(-104, 32), (-104, -32), (-62, 32), (-62, -32), (-136, 0), (-30, 0)]
DOWELS = [(-126.6, 22.6), (-39.4, -22.6)]


def stadium(part):
    """One closed capsule profile in the (u,v) plane (u=-Z, v=Y).

    Two R40 lobes at u=-104 / u=-62 joined by tangent lines at v=+-40, drawn as
    real arcs: a polyline approximation leaves ~70 flat facets on the flange's
    curved surface and shows up as stripes in every shaded view.
    """
    capsule_sketch(part, -Z_UP, -Z_LO, 40.0)


def part_07(session):
    p = session.new_part()
    # ---- flange 12 thick: X -42..-30
    pl = plane_at_x(p, -42, name="P_FLANGE")
    with sketch(p, pl.Name, exact=True) as sk:
        stadium(p)
    extrude_boss(p, sk, mm(12), direction=False, name="01_FLANGE")
    # ---- two bearing bosses Ø32 x 10 on the outer face: X -52..-42
    boss_cyl_x(p, -52, 0, Z_UP, 32, 10, name="02_BOSS_UP")
    boss_cyl_x(p, -64, 0, Z_LO, 32, 22, name="03_BOSS_LO")
    # ---- bearing bores Ø18 x 10 from the inner face X=-30 going -X
    cut_cyl_x(p, -30, 0, Z_UP, 18, 10, name="04_BORE_UP", direction=True)
    cut_cyl_x(p, -30, 0, Z_LO, 18, 10, name="05_BORE_LO", direction=True)
    # ---- relief-valve cavity in lower boss: Ø20 to X=-38 then Ø8 seat
    cut_cyl_x(p, -64, 0, Z_LO, 20, 26, name="06_RV_CAVITY")
    cut_cyl_x(p, -38, 0, Z_LO, 8, 8, name="07_RV_SEAT")
    # ---- bolt holes Ø8 + dowel holes Ø5 through the flange
    for i, (u, v) in enumerate(BOLTS):
        cut_cyl_x(p, -43, v, -u, 8, 14, name=f"08_BOLT_{i}")
    for i, (u, v) in enumerate(DOWELS):
        cut_cyl_x(p, -43, v, -u, 5, 14, name=f"09_DOWEL_{i}")
    return save_part(session, p, "07_cover", expect=[34, 80, 122], tol=0.4)


def part_10(session):
    p = session.new_part()
    pl = plane_at_x(p, -31, name="P_GASKET")
    with sketch(p, pl.Name, exact=True) as sk:
        stadium(p)
    extrude_boss(p, sk, mm(1), direction=False, name="01_GASKET")
    cut_cyl_x(p, -32, 0, Z_UP, 48, 3, name="02_HOLE_UP")
    cut_cyl_x(p, -32, 0, Z_LO, 48, 3, name="03_HOLE_LO")
    for i, (u, v) in enumerate(BOLTS):
        cut_cyl_x(p, -32, v, -u, 8, 3, name=f"04_BOLT_{i}")
    for i, (u, v) in enumerate(DOWELS):
        cut_cyl_x(p, -32, v, -u, 5, 3, name=f"05_DOWEL_{i}")
    return save_part(session, p, "10_gasket", expect=[1, 80, 122], tol=0.3)


def part_14(session):
    """压盖螺母: Ø36.5 sleeve 23 + hex A/F32 x 6, bore Ø20, external M36."""
    p = session.new_part()
    revolve_profile(p, [(0, 10), (0, 18.25), (23, 18.25), (23, 10)], name="01_SLEEVE")
    extrude_hex(p, 23, 32 / math.cos(math.radians(30)) / 2, 6, bore_dia=20,
                name="02_HEX", direction=False)
    return save_part(session, p, "14_gland_nut", expect=[29, 36.95, 36.95], tol=0.5)


def part_15(session):
    """填料压盖: Ø26 spigot 12 + Ø30 flange 4, bore Ø20, total 16."""
    p = session.new_part()
    revolve_profile(
        p, [(0, 10), (0, 13), (12, 13), (12, 15), (16, 15), (16, 10)], name="01_GLAND"
    )
    return save_part(session, p, "15_packing_gland", expect=[16, 30, 30], tol=0.2)


def main() -> int:
    session = SolidWorksSession(visible=True)
    reset_sw(session.sw, delete_names=['07_cover','10_gasket','14_gland_nut','15_packing_gland'])
    out = {}
    for fn in [part_07, part_10, part_14, part_15]:
        try:
            out[fn.__name__] = fn(session)
        except Exception as exc:
            print(f"[FAIL] {fn.__name__}: {exc}")
            out[fn.__name__] = {"error": str(exc)}
        finally:
            try:
                session.close()
            except Exception:
                pass
    record("parts_cover", out)
    fails = [k for k, v in out.items() if "error" in v or not v.get("saved")]
    print("FAILED:", fails if fails else "none")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
