"""Off-centre probe: sketch circle at (u=+10, v=+20) on each base plane."""
from __future__ import annotations

import sys

from common import bbox_mm

from sw_connect import mm
from sw_part import extrude_boss, insert_offset_plane, sketch, sketch_circle
from sw_session import SolidWorksSession


def run(session, plane, tag):
    p = session.new_part()
    try:
        with sketch(p, plane, exact=True) as sk:
            sketch_circle(p, mm(10), mm(20), mm(5))
        extrude_boss(p, sk, mm(10), direction=False, name="P")
        p.ForceRebuild3(False)
        b = bbox_mm(p)
        print(f"[{tag}] {plane}: bbox={b}  centre=({(b[0]+b[3])/2:.1f},"
              f"{(b[1]+b[4])/2:.1f},{(b[2]+b[5])/2:.1f})")
    finally:
        session.close(p)


def main() -> int:
    session = SolidWorksSession(visible=True)
    run(session, "Front Plane", "front")
    run(session, "Top Plane", "top")
    run(session, "Right Plane", "right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
