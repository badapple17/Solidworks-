"""Probe: what does sketching on Right/Top/Front plane and extruding +Z give?"""
from __future__ import annotations

import sys

from common import bbox_mm

from sw_connect import mm
from sw_part import extrude_boss, sketch, sketch_circle
from sw_session import SolidWorksSession


def main() -> int:
    session = SolidWorksSession(visible=True)
    for plane in ["Right Plane", "Top Plane", "Front Plane"]:
        part = session.new_part()
        try:
            with sketch(part, plane, exact=True) as sk:
                sketch_circle(part, mm(10), 0, mm(5))
            feat = extrude_boss(part, sk, mm(20), direction=True, name="PROBE")
            part.ForceRebuild3(False)
            print(f"{plane}: feature={'ok' if feat else 'NONE'} bbox={bbox_mm(part)}")
        finally:
            session.close(part)
    return 0


if __name__ == "__main__":
    sys.exit(main())
