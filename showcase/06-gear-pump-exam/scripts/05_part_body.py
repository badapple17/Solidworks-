"""11 泵体 — 立式42型齿轮油泵 body.

Global frame: X = gear axis, cover face at X=-30, back face X=+32,
Y = port axis, Z = up (base bottom Z=0, gear axes Z=104 / Z=62).

Cut direction semantics (probed on SW2023): extrude_cut direction=True -> +normal,
False -> -normal; extrude_boss is the reverse.  Callers pass the raw flag;
auto_flip still rescues any cut that lands in air.
"""
from __future__ import annotations

import math
import sys

from build_lib import (
    boss_cyl_y,
    capsule_sketch,
    cut_cyl_x,
    cut_cyl_y,
    cut_cyl_z,
    plane_at_x,
    plane_at_z,
    reset_sw,
    save_part,
)
from common import bbox_mm, record

from sw_connect import mm
from sw_part import extrude_boss, extrude_cut, sketch, sketch_circle, sketch_line
from sw_session import SolidWorksSession

Z_UP, Z_LO = 104.0, 62.0
X_FRONT, X_BACK = -30.0, 32.0
BASE_X0, BASE_X1 = -46.0, 32.0
SBOX_X0, SBOX_X1 = 32.0, 67.0
PORT_Z = 83.0
PORT_X = -14.0
BOLTS = [(-104, 32), (-104, -32), (-62, 32), (-62, -32), (-136, 0), (-30, 0)]
DOWELS = [(-126.6, 22.6), (-39.4, -22.6)]
BASE_HOLES_X = [-38.0, -18.0, 4.0, 24.0]
BASE_HOLES_Y = [40.0, -40.0]


def polyline(part, pts):
    for (u1, v1), (u2, v2) in zip(pts, pts[1:] + pts[:1]):
        sketch_line(part, mm(u1), mm(v1), mm(u2), mm(v2))


def rounded_rect(part, u0, u1, v0, v1, r=6.0, seg=6):
    """Closed rounded-rectangle polyline, walked counter-clockwise.

    Each corner arc must run in the direction of travel; emitting them in any
    other order leaves the closing segment cutting across the interior and the
    profile self-intersects (extrude then fails silently).
    """
    corners = [
        (u1 - r, v0 + r, -90.0),   # bottom-right: -90 -> 0
        (u1 - r, v1 - r, 0.0),     # top-right:     0 -> 90
        (u0 + r, v1 - r, 90.0),    # top-left:     90 -> 180
        (u0 + r, v0 + r, 180.0),   # bottom-left: 180 -> 270
    ]
    pts = []
    for (cu, cv, a0) in corners:
        for k in range(seg + 1):
            a = math.radians(a0 + 90.0 * k / seg)
            pts.append((cu + r * math.cos(a), cv + r * math.sin(a)))
    polyline(part, pts)


def build(session):
    p = session.new_part()

    # ---- 01 housing: capsule of the two R40 lobes, X -30..+32
    pl = plane_at_x(p, X_FRONT, name="P_HOUSING")
    with sketch(p, pl.Name, exact=True) as sk:
        capsule_sketch(p, -Z_UP, -Z_LO, 40.0)
    extrude_boss(p, sk, mm(X_BACK - X_FRONT), direction=False, name="01_HOUSING")

    # ---- 02 column Y+-12 from the base up to the lower lobe
    pl2 = plane_at_x(p, X_FRONT, name="P_COLUMN")
    with sketch(p, pl2.Name, exact=True) as sk2:
        polyline(p, [(-12, -12), (-12, 12), (-62, 12), (-62, -12)])
    extrude_boss(p, sk2, mm(X_BACK - X_FRONT), direction=False, name="02_COLUMN")

    # ---- 03 base 78 x 88 x 12, R6 vertical corners.
    # Drawn in XY (Front plane) and extruded +Z: rounding 6 in the ZY section
    # would degenerate (the section is only 12 wide) and self-intersect.
    pl3 = plane_at_z(p, 0.0, name="P_BASE")
    with sketch(p, pl3.Name, exact=True) as sk3:
        rounded_rect(p, BASE_X0, BASE_X1, -44.0, 44.0, r=6.0)
    extrude_boss(p, sk3, mm(12), direction=False, name="03_BASE")

    # ---- 04 stuffing-box collar Ø64, X 32..67
    pl4 = plane_at_x(p, SBOX_X0, name="P_SBOX")
    with sketch(p, pl4.Name, exact=True) as sk4:
        sketch_circle(p, mm(-Z_UP), 0, mm(32))
    extrude_boss(p, sk4, mm(SBOX_X1 - SBOX_X0), direction=False, name="04_SBOX")

    # ---- 05 upper bore stack (cut +X from the cover face)
    cut_cyl_x(p, -30, 0, Z_UP, 48, 30, name="05_CAV_UP", direction=True)
    cut_cyl_x(p, 0, 0, Z_UP, 18, 20, name="06_BRG_UP", direction=True)
    cut_cyl_x(p, 20, 0, Z_UP, 26, 22, name="07_PACK_UP", direction=True)
    cut_cyl_x(p, 42, 0, Z_UP, 34.5, 25, name="08_M36_UP", direction=True)
    # ---- 06 lower bore stack
    cut_cyl_x(p, -30, 0, Z_LO, 48, 30, name="09_CAV_LO", direction=True)
    cut_cyl_x(p, 0, 0, Z_LO, 18, 20, name="10_BRG_LO", direction=True)
    cut_cyl_x(p, 20, 0, Z_LO, 30, 12, name="11_RECESS_LO", direction=True)

    # ---- 07 port bosses Ø30 on both sides, passages Ø20 + G1/4 tap
    for sign, tag in ((1, "P"), (-1, "N")):
        boss_cyl_y(p, 30.0 * sign, PORT_X, PORT_Z, 30, 17,
                   name=f"12_PORTBOSS_{tag}", direction=(sign < 0))
        # gallery Ø20 from Y=33 inward; G1/4 (Ø11.8) only in the outer 14 mm.
        # Order matters: cutting Ø20 to the mouth first leaves the Ø11.8 no
        # material, and SolidWorks silently drops the feature.
        cut_cyl_y(p, 33.0 * sign, PORT_X, PORT_Z, 20, 25,
                  name=f"13_PASS_{tag}", direction=(sign < 0))
        cut_cyl_y(p, 47.0 * sign, PORT_X, PORT_Z, 11.8, 14,
                  name=f"14_G14_{tag}", direction=(sign < 0))

    # ---- 08 front-face bolt holes (M6 tap drill) and dowel holes
    for i, (u, v) in enumerate(BOLTS):
        cut_cyl_x(p, -30, v, -u, 5.0, 10, name=f"15_M6_{i}", direction=True)
    for i, (u, v) in enumerate(DOWELS):
        cut_cyl_x(p, -30, v, -u, 5.0, 12, name=f"16_DOWEL_{i}", direction=True)

    # ---- 09 base fixing holes Ø9 vertical
    for i, x in enumerate(BASE_HOLES_X):
        for j, y in enumerate(BASE_HOLES_Y):
            cut_cyl_z(p, -1.0, x, y, 9.0, 14, name=f"17_BH_{i}{j}", direction=True)

    # ---- 10 bottom relief groove 42 wide x 3 deep
    plb = plane_at_z(p, -1.0, name="P_RELIEF")
    with sketch(p, plb.Name, exact=True) as skb:
        polyline(p, [(-46, -21), (32, -21), (32, 21), (-46, 21)])
    extrude_cut(p, skb, mm(4), direction=True, name="18_RELIEF")
    return p


def main() -> int:
    session = SolidWorksSession(visible=True)
    reset_sw(session.sw, delete_names=["11_body"])
    try:
        p = build(session)
        p.ForceRebuild3(False)
        print("bbox:", bbox_mm(p), "bodies:", len(p.GetBodies2(0, False) or []))
        info = save_part(session, p, "11_body", expect=[113, 94, 144], tol=0.6)
        record("part_body", info)
    finally:
        try:
            session.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
