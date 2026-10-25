"""16 皮带轮 — V-belt pulley.

Local frame: X = axis (0 at the hub's outer face), Y/Z radial.
OD 105, rim 18 wide, V-groove 30deg included, top width 10 at OD, bottom Ø85,
web Ø74 x 7, hub Ø30 x 23, bore Ø16H7, keyway 5 wide x 2.3 deep,
5 x Ø18 lightening holes on a Ø52 circle.
"""
from __future__ import annotations

import math
import sys

from build_lib import (
    cut_cyl_x,
    plane_at_x,
    reset_sw,
    revolve_profile,
    save_part,
)
from common import record

from sw_connect import mm
from sw_part import extrude_cut, sketch, sketch_line
from sw_session import SolidWorksSession

OD_R = 52.5
GROOVE_R = 42.5          # Ø85 groove bottom
GROOVE_HALF = 5.0        # 10 wide at the OD
GROOVE_CX = 9.0
WEB_R = 37.0
HUB_R = 15.0
LEN = 23.0
RIM_X = (0.0, 18.0)
WEB_X = (5.0, 12.0)


def profile():
    half_bottom = GROOVE_HALF - (OD_R - GROOVE_R) * math.tan(math.radians(15.0))
    return [
        (0.0, 0.0), (LEN, 0.0), (LEN, HUB_R), (WEB_X[1], HUB_R),
        (WEB_X[1], WEB_R), (RIM_X[1], WEB_R), (RIM_X[1], OD_R),
        (GROOVE_CX + GROOVE_HALF, OD_R),
        (GROOVE_CX + half_bottom, GROOVE_R),
        (GROOVE_CX - half_bottom, GROOVE_R),
        (GROOVE_CX - GROOVE_HALF, OD_R),
        (0.0, OD_R), (0.0, WEB_R), (WEB_X[0], WEB_R), (WEB_X[0], HUB_R),
        (0.0, HUB_R),
    ]


def build(session):
    p = session.new_part()
    feat = revolve_profile(p, profile(), name="01_BODY")
    if feat is None:
        raise RuntimeError("pulley revolve failed")

    # bore Ø16H7 through
    cut_cyl_x(p, -1.0, 0, 0, 16, LEN + 2, name="02_BORE", direction=True)
    # keyway 5 wide x 2.3 deep at the top of the bore, axial: cutting along the
    # axis (rectangle in the YZ plane) is the natural construction and keeps the
    # slot on +Y; a Front-plane slab cut landed on the hub's underside instead.
    pl = plane_at_x(p, -1.0, name="P_KEY")
    with sketch(p, pl.Name, exact=True) as sk:
        # start 1 mm inside the bore: a profile edge exactly on the bore wall is
        # tangent to it (zero-thickness) and SolidWorks drops the whole cut
        pts = [(-2.5, 7.0), (2.5, 7.0), (2.5, 10.3), (-2.5, 10.3)]
        for (a, b), (c, d) in zip(pts, pts[1:] + pts[:1]):
            sketch_line(p, mm(a), mm(b), mm(c), mm(d))
    extrude_cut(p, sk, mm(LEN + 2), direction=True, name="03_KEYWAY")
    # 5 x Ø18 lightening holes through the web
    for i in range(5):
        a = math.radians(90.0 + 72.0 * i)
        cut_cyl_x(p, WEB_X[0] - 1.0, 26 * math.cos(a), 26 * math.sin(a), 18, 9,
                  name=f"04_HOLE_{i}", direction=True)
    return p


def main() -> int:
    session = SolidWorksSession(visible=True)
    reset_sw(session.sw, delete_names=["16_pulley"])
    try:
        p = build(session)
        p.ForceRebuild3(False)
        print("bbox:", __import__("common").bbox_mm(p),
              "bodies:", len(p.GetBodies2(0, False) or []))
        info = save_part(session, p, "16_pulley", expect=[23, 105, 105], tol=0.4)
        record("part_pulley", info)
    finally:
        try:
            session.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
