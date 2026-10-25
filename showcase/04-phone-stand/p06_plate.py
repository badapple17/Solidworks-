# -*- coding: utf-8 -*-
"""06 背板：96 宽圆角板（顶部 R14），3 条长圆槽 + 1 块梯形减重窗，
底部 Ø5 卷边圆棒（钩子抱箍挂在上面），上缘中间伸出 8 宽凸舌接顶部铰链。

局部坐标：原点在顶部铰链销孔中心；+Z 沿板面向上的方向，+X 板宽，
+Y 为板厚方向（板体在 Y=3..6，手机面在 Y=3 一侧）。

卷边中心 (Y=4.5, Z=10.5) 比板体下缘 (Z=14.5) 低 4 mm，
抱箍外径 3.4 -> 顶到 13.9，整周不碰板体，钩子可自由翻转。

干涉检查后的修正（装配干涉 9 处 -> 修）：
- 凸舌原到 Z=18，伸进手机下沿（手机底 Z=15.45、Y<3）151 mm³；改为止于 Z=14.5，
  与板体下缘共面相接（8×3 共用面，仍是单实体）。
- 连接筋原 ±25，与托钩抱箍（X=27±11 -> 16..38）重叠；收到 ±15，离抱箍内端 1 mm。
"""

import math

from stand_common import OUT, mm, check, color_part, C_BODY
from sw_session import SolidWorksSession
from sw_part import (
    sketch, sketch_line, sketch_arc, sketch_circle, sketch_slot,
    sketch_corner_rectangle, extrude_cut, extrude_midplane, insert_offset_plane,
)

W = 96.0
X_HALF = W / 2
Z_BOT = 14.5
Z_TOP = 124.0
R_TOP = 14.0
T = 3.0
Y_MID = 4.5
BEAD_R = 2.5
BEAD_Z = 10.5
BEAD_LEN = 96.0
WEB_X = 15.0   # 托钩占 |X|=16..38，筋必须停在 16 以内
WEB_Z0, WEB_Z1 = 8.0, 16.0
TAB_W = 8.0  # 与立柱叉口 2*4 零间隙配合
TAB_Y0, TAB_Y1 = -5.0, 6.0
TAB_Z0, TAB_Z1 = -10.0, 14.5   # 顶面 = 板体下缘，不进手机区
SLOT_W = 6.0
SLOTS = ((0.0, 38.0, 92.0), (-27.0, 44.0, 86.0), (27.0, 44.0, 86.0))
TRAP_Z0, TRAP_Z1 = 20.0, 28.0
TRAP_X0, TRAP_X1 = 7.0, 12.0
R_HOLE = 2.1


def rounded_top_area():
    return W * (Z_TOP - Z_BOT) - 2 * (R_TOP**2 - math.pi * R_TOP**2 / 4)


def circle_band_area(r, y0, y1, cy):
    """圆 r（圆心在 cy）与条带 y∈[y0,y1] 的相交面积。

    面积 = ∫ 2√(r²-(y-cy)²) dy，用解析原函数，避免数值积分误差。
    """
    def F(t):
        t = max(-r, min(r, t))
        return 0.5 * (t * math.sqrt(max(0.0, r * r - t * t)) + r * r * math.asin(t / r))
    a = max(-r, min(r, y0 - cy))
    b = max(-r, min(r, y1 - cy))
    if b <= a:
        return 0.0
    return 2.0 * (F(b) - F(a))


def expected_volume():
    body = rounded_top_area() * T
    bead = math.pi * BEAD_R**2 * BEAD_LEN
    web = 2 * WEB_X * (WEB_Z1 - WEB_Z0) * T
    tab = TAB_W * (TAB_Y1 - TAB_Y0) * (TAB_Z1 - TAB_Z0)
    band = circle_band_area(BEAD_R, 3.0, 6.0, Y_MID)                 # 卷边 ∩ 板厚条带
    band_tab = circle_band_area(BEAD_R, TAB_Y0, TAB_Y1, Y_MID)       # 卷边 ∩ 凸舌 Y 范围

    # 容斥：板体 Z>=14.5，凸舌/卷边都在 14.5 以下 -> 板体只和筋相交
    overlap_body_web = 2 * WEB_X * T * (WEB_Z1 - Z_BOT)
    overlap_bead_web = band * 2 * WEB_X
    overlap_bead_tab = band_tab * TAB_W                # 卷边 Z 8..13 全在凸舌 Z 内
    overlap_web_tab = TAB_W * T * (min(WEB_Z1, TAB_Z1) - WEB_Z0)
    triple = band * TAB_W                              # 卷边∩筋∩凸舌
    union = (body + bead + web + tab
             - (overlap_body_web + overlap_bead_web + overlap_bead_tab + overlap_web_tab)
             + triple)

    slots = sum((SLOT_W * (z1 - z0) + math.pi * (SLOT_W / 2)**2) * T for _, z0, z1 in SLOTS)
    trap = (2 * TRAP_X0 + 2 * TRAP_X1) / 2 * (TRAP_Z1 - TRAP_Z0) * T
    hole = math.pi * R_HOLE**2 * TAB_W
    return union - slots - trap - hole


session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
path = OUT / "06_plate.SLDPRT"
try:
    plane_body = insert_offset_plane(part, "Top Plane", mm(Y_MID), "Plane_Plate_Mid")
    plane_tab = insert_offset_plane(part, "Top Plane", mm((TAB_Y0 + TAB_Y1) / 2), "Plane_Tab_Mid")

    # 1) 板体：顶部两角 R14，底部直角（底部两角被钩子挡住）
    with sketch(part, "Plane_Plate_Mid", exact=True) as sk:
        sketch_line(part, mm(-X_HALF), mm(-Z_BOT), mm(X_HALF), mm(-Z_BOT))
        sketch_line(part, mm(X_HALF), mm(-Z_BOT), mm(X_HALF), mm(-(Z_TOP - R_TOP)))
        sketch_arc(part, mm(X_HALF - R_TOP), mm(-(Z_TOP - R_TOP)),
                   mm(X_HALF), mm(-(Z_TOP - R_TOP)),
                   mm(X_HALF - R_TOP), mm(-Z_TOP), direction=-1)
        sketch_line(part, mm(X_HALF - R_TOP), mm(-Z_TOP), mm(-(X_HALF - R_TOP)), mm(-Z_TOP))
        sketch_arc(part, mm(-(X_HALF - R_TOP)), mm(-(Z_TOP - R_TOP)),
                   mm(-(X_HALF - R_TOP)), mm(-Z_TOP),
                   mm(-X_HALF), mm(-(Z_TOP - R_TOP)), direction=-1)
        sketch_line(part, mm(-X_HALF), mm(-(Z_TOP - R_TOP)), mm(-X_HALF), mm(-Z_BOT))
    f = extrude_midplane(part, sk, mm(T))
    assert f is not None, "板体拉伸失败"
    f.Name = "01_PLATE_BODY"

    # 2) 底部卷边 Ø5
    with sketch(part, "Right Plane", exact=True) as sk:
        # Right Plane: u=-Z, v=Y
        sketch_circle(part, mm(-BEAD_Z), mm(Y_MID), mm(BEAD_R))
    f = extrude_midplane(part, sk, mm(BEAD_LEN))
    assert f is not None, "卷边失败"
    f.Name = "02_EDGE_BEAD_D5"

    # 3) 中部连接筋（把卷边与板体连起来；两端留空给钩子抱箍）
    with sketch(part, "Plane_Plate_Mid", exact=True) as sk:
        sketch_corner_rectangle(part, mm(-WEB_X), mm(-WEB_Z1), mm(WEB_X), mm(-WEB_Z0))
    f = extrude_midplane(part, sk, mm(T))
    assert f is not None, "连接筋失败"
    f.Name = "03_WEB"

    # 4) 顶部铰链凸舌
    with sketch(part, "Plane_Tab_Mid", exact=True) as sk:
        sketch_corner_rectangle(part, mm(-TAB_W / 2), mm(-TAB_Z1), mm(TAB_W / 2), mm(-TAB_Z0))
    f = extrude_midplane(part, sk, mm(TAB_Y1 - TAB_Y0))
    assert f is not None, "凸舌失败"
    f.Name = "04_TAB"

    # 5) 3 条长圆槽（双向贯穿 3 厚板体）
    for idx, (cx, z0, z1) in enumerate(SLOTS, start=1):
        for direction, side in ((True, "F"), (False, "B")):
            with sketch(part, "Plane_Plate_Mid", exact=True) as sk:
                sketch_slot(part, mm(cx), mm(-z0), mm(cx), mm(-z1), mm(SLOT_W))
            f = extrude_cut(part, sk, 0.0, direction=direction,
                            name=f"05_SLOT_{idx}_{side}")
            assert f is not None, f"长圆槽 {idx}-{side} 失败"

    # 6) 梯形减重窗（下窄上宽）
    for direction, side in ((True, "F"), (False, "B")):
        with sketch(part, "Plane_Plate_Mid", exact=True) as sk:
            sketch_line(part, mm(-TRAP_X0), mm(-TRAP_Z0), mm(TRAP_X0), mm(-TRAP_Z0))
            sketch_line(part, mm(TRAP_X0), mm(-TRAP_Z0), mm(TRAP_X1), mm(-TRAP_Z1))
            sketch_line(part, mm(TRAP_X1), mm(-TRAP_Z1), mm(-TRAP_X1), mm(-TRAP_Z1))
            sketch_line(part, mm(-TRAP_X1), mm(-TRAP_Z1), mm(-TRAP_X0), mm(-TRAP_Z0))
        f = extrude_cut(part, sk, 0.0, direction=direction, name=f"06_WINDOW_{side}")
        assert f is not None, f"减重窗 {side} 失败"

    # 7) 顶部销孔 Ø4.2
    for direction, side in ((True, "R"), (False, "L")):
        with sketch(part, "Right Plane", exact=True) as sk:
            sketch_circle(part, 0, 0, mm(R_HOLE))
        f = extrude_cut(part, sk, 0.0, direction=direction, name=f"07_PINHOLE_{side}")
        assert f is not None, f"销孔 {side} 失败"

    part.ForceRebuild3(False)
    color_part(part, C_BODY, "背板")
    assert session.save(part, str(path)), "保存失败（检查是否有残留打开文档）"
    check(part, "06_plate",
          exp_bbox=(W, max(TAB_Y1, Y_MID + BEAD_R) - TAB_Y0, Z_TOP - TAB_Z0),
          exp_volume=expected_volume(), exp_bodies=1)
    print(f"\n已保存: {path}")
finally:
    session.close(part)
