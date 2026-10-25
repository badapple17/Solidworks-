"""Probe extrude direction off Top Plane (XZ, normal Y) and Front Plane (XY, normal Z)."""
from __future__ import annotations

import sys

from build_lib import plane_at_x
from common import bbox_mm

from sw_connect import mm
from sw_part import extrude_boss, extrude_cut, insert_offset_plane, sketch, sketch_circle
from sw_session import SolidWorksSession


def probe_boss(session, base_plane, offset, direction, tag):
    p = session.new_part()
    try:
        pl = insert_offset_plane(p, base_plane, mm(offset), name="P")
        with sketch(p, pl.Name, exact=True) as sk:
            sketch_circle(p, 0, 0, mm(5))
        feat = extrude_boss(p, sk, mm(20), direction=direction, name="PROBE")
        p.ForceRebuild3(False)
        print(f"[boss {tag}] base={base_plane} off={offset} dir={direction} "
              f"feature={'ok' if feat else 'NONE'} bbox={bbox_mm(p)}")
    finally:
        session.close(p)


def probe_cut(session, base_plane, offset, direction, tag):
    p = session.new_part()
    try:
        pl0 = insert_offset_plane(p, base_plane, mm(offset - 30), name="P0")
        with sketch(p, pl0.Name, exact=True) as sk0:
            sketch_circle(p, 0, 0, mm(20))
        extrude_boss(p, sk0, mm(60), direction=False, name="BLOCK")
        pl = insert_offset_plane(p, base_plane, mm(offset), name="P")
        with sketch(p, pl.Name, exact=True) as sk:
            sketch_circle(p, 0, 0, mm(5))
        feat = extrude_cut(p, sk, mm(20), direction=direction, name="CUTPROBE")
        p.ForceRebuild3(False)
        print(f"[cut {tag}] base={base_plane} off={offset} dir={direction} "
              f"feature={'ok' if feat else 'NONE'} bbox={bbox_mm(p)}")
    finally:
        session.close(p)


def main() -> int:
    session = SolidWorksSession(visible=True)
    probe_boss(session, "Top Plane", -10, False, "top_false")
    probe_boss(session, "Top Plane", 10, True, "top_true")
    probe_boss(session, "Front Plane", -10, False, "front_false")
    probe_boss(session, "Front Plane", 10, True, "front_true")
    probe_cut(session, "Top Plane", 6, False, "top_false")
    probe_cut(session, "Top Plane", 6, True, "top_true")
    probe_cut(session, "Front Plane", 6, False, "front_false")
    probe_cut(session, "Front Plane", 6, True, "front_true")
    return 0


if __name__ == "__main__":
    sys.exit(main())
