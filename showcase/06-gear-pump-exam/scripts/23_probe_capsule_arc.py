"""Probe: build the stadium profile from two arcs + two lines.

The current body/cover use a 36..40-segment polyline, which leaves ~80 flat
facets on the housing's curved surface (visible as stripes in every render).
This probe finds the sketch-arc direction convention and verifies that a clean
4-entity contour extrudes to the exact same envelope with smooth cylinders.
"""
from __future__ import annotations

import sys

from build_lib import plane_at_x, reset_sw
from common import bbox_mm

from sw_connect import get_com_member, mm
from sw_part import extrude_boss, sketch, sketch_arc, sketch_line
from sw_session import SolidWorksSession

U1, U2 = -104.0, -62.0      # lobe centres in u (u = -Z: upper axis 104, lower 62)
R = 40.0
LEN = 62.0


def face_kinds(model):
    kinds = {}
    for b in (model.GetBodies2(0, False) or []):
        for f in (b.GetFaces() or []):
            surf = get_com_member(f, "GetSurface")
            kind = "other"
            for name in ("IsPlane", "IsCylinder", "IsCone", "IsTorus"):
                try:
                    if get_com_member(surf, name):
                        kind = name[2:]
                        break
                except Exception:
                    pass
            kinds[kind] = kinds.get(kind, 0) + 1
    return kinds


def build(session, direction):
    p = session.new_part()
    pl = plane_at_x(p, -30.0, name="P_TEST")
    with sketch(p, pl.Name, exact=True) as sk:
        sketch_line(p, mm(U1), mm(-R), mm(U2), mm(-R))
        sketch_arc(p, mm(U2), 0, mm(U2), mm(-R), mm(U2), mm(R), direction)
        sketch_line(p, mm(U2), mm(R), mm(U1), mm(R))
        sketch_arc(p, mm(U1), 0, mm(U1), mm(R), mm(U1), mm(-R), direction)
    ok = extrude_boss(p, sk, mm(LEN), direction=False, name="01_TEST")
    p.ForceRebuild3(False)
    return p, ok


def main() -> int:
    session = SolidWorksSession(visible=True)
    reset_sw(session.sw)
    try:
        for direction in (1, -1):
            p, ok = build(session, direction)
            print(f"\n--- arc direction={direction}: extrude ok={ok is not None}")
            print("    bbox:", bbox_mm(p), "bodies:", len(p.GetBodies2(0, False) or []))
            print("    faces:", face_kinds(p))
            session.close(p)
    finally:
        try:
            session.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
