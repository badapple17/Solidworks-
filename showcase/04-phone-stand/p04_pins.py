# -*- coding: utf-8 -*-
"""04/05 铰链销轴（两个独立零件，Ø4 轴在 Ø4.2 孔内有 0.1 间隙，不会与其它件融合）。

04_pin_bottom：Ø4 × 18.5，两端 Ø7 × 1.2 头，总宽 20.9。原点在轴中心。
05_pin_top   ：Ø4 × 26，平头，贯穿立柱臂两叉耳与背板凸舌。原点在轴中心。
"""

import math

from stand_common import OUT, mm, check, color_part, C_METAL
from sw_session import SolidWorksSession
from sw_part import sketch, sketch_circle, extrude_boss, extrude_midplane, insert_offset_plane

R_SHAFT = 2.0
R_HEAD = 3.5
T_HEAD = 1.2

BOT_LEN = 18.5
BOT_HEAD_X = BOT_LEN / 2          # 9.25，正好贴住转盘耳片外侧面

TOP_LEN = 26.0

session = SolidWorksSession(visible=True, wait_seconds=20)

# ---------- 04 下销轴 ----------
part = session.new_part()
path = OUT / "04_pin_bottom.SLDPRT"
try:
    with sketch(part, "Right Plane", exact=True) as sk:
        sketch_circle(part, 0, 0, mm(R_SHAFT))
    f = extrude_midplane(part, sk, mm(BOT_LEN))
    assert f is not None, "下销轴轴身失败"
    f.Name = "01_SHAFT_D4"

    for sign, tag in ((1, "R"), (-1, "L")):
        plane_name = f"Plane_HEAD_{tag}"
        insert_offset_plane(part, "Right Plane", mm(sign * BOT_HEAD_X), plane_name)
        with sketch(part, plane_name, exact=True) as sk:
            sketch_circle(part, 0, 0, mm(R_HEAD))
        f = extrude_boss(part, sk, mm(T_HEAD), direction=(sign < 0),
                         name=f"02_HEAD_D7_{tag}")
        assert f is not None, f"下销轴头 {tag} 失败"

    part.ForceRebuild3(False)
    color_part(part, C_METAL, "下销轴")
    session.save(part, str(path))
    check(part, "04_pin_bottom",
          exp_bbox=(BOT_LEN + 2 * T_HEAD, 2 * R_HEAD, 2 * R_HEAD),
          exp_volume=math.pi * R_SHAFT**2 * BOT_LEN
          + 2 * math.pi * R_HEAD**2 * T_HEAD,
          exp_bodies=1)
    print(f"已保存: {path}")
finally:
    session.close(part)

# ---------- 05 上销轴 ----------
part = session.new_part()
path = OUT / "05_pin_top.SLDPRT"
try:
    with sketch(part, "Right Plane", exact=True) as sk:
        sketch_circle(part, 0, 0, mm(R_SHAFT))
    f = extrude_midplane(part, sk, mm(TOP_LEN))
    assert f is not None, "上销轴失败"
    f.Name = "01_SHAFT_D4_L26"

    part.ForceRebuild3(False)
    color_part(part, C_METAL, "上销轴")
    session.save(part, str(path))
    check(part, "05_pin_top",
          exp_bbox=(TOP_LEN, 2 * R_SHAFT, 2 * R_SHAFT),
          exp_volume=math.pi * R_SHAFT**2 * TOP_LEN,
          exp_bodies=1)
    print(f"已保存: {path}")
finally:
    session.close(part)
