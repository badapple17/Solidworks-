"""Build the small turned parts: 01 调节螺钉, 02 弹簧, 03 锁紧螺母M20,
04 钢球, 12 填料, 19 螺母M12."""
from __future__ import annotations

import math
import sys

from build_lib import (
    boss_cyl_x,
    cut_cyl_x,
    extrude_hex,
    plane_at_x,
    revolve_profile,
    rect_in_yz,
    save_part,
)
from common import record

from sw_connect import mm
from sw_part import extrude_boss, extrude_cut, sketch
from sw_session import SolidWorksSession


def part_01(session):
    """调节螺钉: hex A/F30 x8, Ø17 x5, M20 x14, Ø13 x7  => 34 total."""
    p = session.new_part()
    extrude_hex(p, 0, 17.3205, 8, name="01_HEX_AF30")
    revolve_profile(
        p,
        [(8, 0), (8, 8.5), (13, 8.5), (13, 10), (27, 10), (27, 6.5), (34, 6.5), (34, 0)],
        name="02_BODY",
    )
    return save_part(session, p, "01_adjust_screw", expect=[34, 34.64, 34.64], tol=0.6)


def part_02(session):
    """弹簧: OD14, wire Ø2, free length 20, 4.5 coils -> 5 rings."""
    p = session.new_part()
    n = 5
    pitch = 20.0 / 4.5
    for i in range(n):
        xc = 1.0 + i * pitch
        pts = []
        seg = 14
        for k in range(seg + 1):
            a = 2 * math.pi * k / seg
            pts.append((xc + 1.0 * math.sin(a), 6.0 + 1.0 * math.cos(a)))
        # close the circle back onto itself (no axis segment)
        closed = pts + [pts[0]]
        with sketch(p, "Front Plane", exact=True) as sk:
            p.SketchManager.CreateCenterLine(mm(-2), 0, 0, mm(22), 0, 0)
            for (x1, r1), (x2, r2) in zip(closed, closed[1:]):
                p.SketchManager.CreateLine(mm(x1), mm(r1), 0, mm(x2), mm(r2), 0)
        p.ClearSelection2(True)
        from sw_connect import create_empty_dispatch_variant
        p.Extension.SelectByID2(sk, "SKETCH", 0, 0, 0, False, 0,
                                create_empty_dispatch_variant(), 0)
        feat = p.FeatureManager.FeatureRevolve2(
            True, True, False, False, False, False,
            0, 0, 2 * math.pi, 0, False, False, 0.0, 0.0, 0, 0, 0, True, True, True)
        p.ClearSelection2(True)
        if feat is None:
            raise RuntimeError(f"spring ring {i} revolve failed")
    return save_part(session, p, "02_spring", expect=[20, 14, 14], tol=0.6)


def _locknut(session, name, od, bore_r, thick, slot_w, slot_outer_r,
             slot_inner_r, chamfer, expect):
    p = session.new_part()
    c = chamfer
    revolve_profile(
        p,
        [(0, bore_r), (0, od / 2 - c), (c, od / 2), (thick - c, od / 2),
         (thick, od / 2 - c), (thick, bore_r)],
        name="01_RING",
    )
    pl = plane_at_x(p, -0.5, name="P_SLOTS")
    with sketch(p, pl.Name, exact=True) as sk:
        u = slot_outer_r
        v = slot_w / 2
        for (u1, u2, v1, v2) in [
            (slot_inner_r, u, -v, v), (-u, -slot_inner_r, -v, v),
            (-v, v, slot_inner_r, u), (-v, v, -u, -slot_inner_r),
        ]:
            rect_in_yz(p, pl.Name, u1, u2, v1, v2)
    extrude_cut(p, sk, mm(thick + 1), direction=False, name="02_SLOTS")
    return save_part(session, p, name, expect=expect)


def part_03(session):
    return _locknut(session, "03_locknut_M20", 30, 10, 7, 5, 17, 13, 0.5,
                    [7, 30, 30])


def part_13(session):
    return _locknut(session, "13_locknut_M36", 48, 17.5, 7, 6, 26, 21, 1.0,
                    [7, 48, 48])


def part_04(session):
    """钢球 Ø10."""
    p = session.new_part()
    pts = []
    seg = 16
    for k in range(seg + 1):
        a = -math.pi / 2 + math.pi * k / seg
        pts.append((5 * math.sin(a), 5 * math.cos(a)))
    revolve_profile(p, pts, name="01_BALL")
    return save_part(session, p, "04_steel_ball", expect=[10, 10, 10], tol=0.1)


def part_12(session):
    """填料: OD26 / ID18 / length 10."""
    p = session.new_part()
    revolve_profile(p, [(0, 9), (0, 13), (10, 13), (10, 9)], name="01_PACKING")
    return save_part(session, p, "12_packing", expect=[10, 26, 26], tol=0.2)


def part_19(session):
    """螺母 M12: hex A/F20 (across corners 23.1), h=10, bore Ø10.2."""
    p = session.new_part()
    extrude_hex(p, 0, 20 / math.cos(math.radians(30)) / 2, 10,
                bore_dia=10.2, name="01_HEX_M12")
    return save_part(session, p, "19_nut_M12", expect=[10, 23.09, 23.09], tol=0.4)


def main() -> int:
    session = SolidWorksSession(visible=True)
    out = {}
    for fn in [part_01, part_02, part_03, part_04, part_12, part_13, part_19]:
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
    record("parts_small", out)
    fails = [k for k, v in out.items() if "error" in v or not v.get("saved")]
    print("FAILED:", fails if fails else "none")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
