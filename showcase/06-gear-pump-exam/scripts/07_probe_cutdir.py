"""Which way does a cut extrude go? Read back the cut cylinder's face box.

Block: Right plane offset X=-20, boss 40 with dir=False  => X -20..20.
Blind hole D10 depth 10 from plane X=0.  Faces tell where the hole landed.
"""
from __future__ import annotations

import sys

from build_lib import plane_at_x
from common import bbox_mm

from sw_connect import get_com_member, mm
from sw_part import extrude_boss, extrude_cut, sketch, sketch_circle
from sw_session import SolidWorksSession


def cyl_boxes(part):
    out = []
    for body in (part.GetBodies2(0, False) or []):
        for face in (body.GetFaces() or []):
            surf = get_com_member(face, "GetSurface")
            if surf is None:
                continue
            try:
                if not get_com_member(surf, "IsCylinder"):
                    continue
            except Exception:
                continue
            b = get_com_member(face, "GetBox")
            out.append([round(v * 1000, 2) for v in b])
    return out


def run(session, direction, tag):
    p = session.new_part()
    try:
        pl = plane_at_x(p, -20, name="P0")
        with sketch(p, pl.Name, exact=True) as sk:
            sketch_circle(p, 0, 0, mm(20))
        extrude_boss(p, sk, mm(40), direction=False, name="BLOCK")
        pl2 = plane_at_x(p, 0, name="P1")
        with sketch(p, pl2.Name, exact=True) as sk2:
            sketch_circle(p, 0, 0, mm(5))
        extrude_cut(p, sk2, mm(10), direction=direction, name="HOLE")
        p.ForceRebuild3(False)
        print(f"[cut dir={direction} {tag}] bbox={bbox_mm(p)} cylfaces={cyl_boxes(p)}")
    finally:
        session.close(p)


def main() -> int:
    session = SolidWorksSession(visible=True)
    run(session, False, "false=+X?")
    run(session, True, "true=-X?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
