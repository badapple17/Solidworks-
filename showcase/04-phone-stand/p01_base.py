# -*- coding: utf-8 -*-
"""01 底座：Ø104 圆盘 + 中心 Ø50 转盘沉槽 + 3 条弧形橡胶脚 + 3 颗十字螺钉。

Ø104 来自用户俯视图标尺实测（约 10.3 cm，原估 Ø110 偏大）。
螺钉：用户指定改为 3 颗绕圆心 120° 均布（落在脚垫之间），不留通孔，不再按照片。
局部坐标：原点在底面中心，+Z 向上。装配时底面贴 Z=0。
"""

import math

from stand_common import (
    OUT, mm, deg, annulus_sector, draw_annulus_sector, check, color,
    C_BODY, C_RUBBER, C_SCREW,
)
from sw_session import SolidWorksSession
from sw_part import (
    sketch, sketch_circle, sketch_line, extrude_boss, extrude_cut,
    insert_offset_plane,
)

R_BASE = 52.0
T_BASE = 10.0
R_RECESS = 25.0
T_RECESS = 2.6
FOOT_R_OUT, FOOT_R_IN, FOOT_T = 46.5, 39.0, 1.2
FOOT_ANGLES = (30.0, 150.0, 270.0)
FOOT_HALF = 23.0
SCREW_PCD_R = 12.0
SCREW_ANGLES = (90.0, 210.0, 330.0)   # 与脚垫 30/150/270 错开
SCREWS = tuple((SCREW_PCD_R * math.cos(math.radians(a)), SCREW_PCD_R * math.sin(math.radians(a)))
               for a in SCREW_ANGLES)
R_SCREW, SCREW_SEAT, SLOT_L, SLOT_W, SLOT_D = 3.25, 0.3, 6.5, 0.7, 0.45


def rect_lines(part, u0, v0, u1, v1):
    """四条线画矩形（毫米）。CreateCornerRectangle 角点离草图轴 <0.5 mm 会被吸到轴上
    （(0,12) 处竖槽角点 x=±0.35 实测失败），十字槽一律用逐条线。"""
    sketch_line(part, mm(u0), mm(v0), mm(u1), mm(v0))
    sketch_line(part, mm(u1), mm(v0), mm(u1), mm(v1))
    sketch_line(part, mm(u1), mm(v1), mm(u0), mm(v1))
    sketch_line(part, mm(u0), mm(v1), mm(u0), mm(v0))


def expected_volume():
    disc = math.pi * R_BASE**2 * T_BASE
    recess = math.pi * R_RECESS**2 * T_RECESS
    sector = 0.5 * (FOOT_R_OUT**2 - FOOT_R_IN**2) * math.radians(2 * FOOT_HALF)
    feet = 3 * sector * FOOT_T
    n = len(SCREWS)
    screw_recess = n * math.pi * R_SCREW**2 * SCREW_SEAT
    # 十字槽：两条 6.5×0.7 交叉（中心 0.7×0.7 只算一次），比座面再深 0.15；
    # 槽端角点超出 Ø6.5 座面约 0.02 mm，那一小块全深 0.45，量级 <0.01 mm³，忽略
    cross = n * (2 * SLOT_L * SLOT_W - SLOT_W**2) * (SLOT_D - SCREW_SEAT)
    return disc - recess + feet - screw_recess - cross


session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
path = OUT / "01_base.SLDPRT"
try:
    # 1) 主圆盘
    with sketch(part, "Front Plane", exact=True) as sk:
        sketch_circle(part, 0, 0, mm(R_BASE))
    f_disc = extrude_boss(part, sk, mm(T_BASE), direction=False, name="01_DISC_D104")
    assert f_disc is not None, "底盘拉伸失败"
    color(f_disc, C_BODY, "底座主体")

    # 2) 三条弧形橡胶脚（底面 −Z 方向 1.2）
    for idx, ang in enumerate(FOOT_ANGLES, start=1):
        spec = annulus_sector(0, 0, mm(FOOT_R_OUT), mm(FOOT_R_IN),
                              ang - FOOT_HALF, ang + FOOT_HALF)
        with sketch(part, "Front Plane", exact=True) as sk:
            draw_annulus_sector(part, spec)
        f = extrude_boss(part, sk, mm(FOOT_T), direction=True, merge=True,
                         name=f"02_FOOT_{idx}")
        assert f is not None, f"脚垫 {idx} 拉伸失败"
        color(f, C_RUBBER, f"脚垫{idx}")

    # 3) 中心转盘沉槽 Ø52 × 2.6，从顶面向下切
    top_plane = insert_offset_plane(part, "Front Plane", mm(T_BASE), "Plane_Top")
    with sketch(part, top_plane.Name if hasattr(top_plane, "Name") else "Plane_Top",
                exact=True) as sk:
        sketch_circle(part, 0, 0, mm(R_RECESS))
    f = extrude_cut(part, sk, mm(T_RECESS), direction=False, name="03_RECESS_D50")
    assert f is not None, "沉槽切除失败"

    # 4) 三颗十字螺钉（沉入底面 0.3，加十字槽；120° 均布）
    for idx, (cx, cy) in enumerate(SCREWS, start=1):
        with sketch(part, "Front Plane", exact=True) as sk:
            sketch_circle(part, mm(cx), mm(cy), mm(R_SCREW))
        f = extrude_cut(part, sk, mm(SCREW_SEAT), direction=True, name=f"04_SCREW_SEAT_{idx}")
        assert f is not None, f"螺钉座 {idx} 失败"
        for j, (w, h) in enumerate(((SLOT_L, SLOT_W), (SLOT_W, SLOT_L)), start=1):
            with sketch(part, "Front Plane", exact=True) as sk:
                rect_lines(part, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
            f2 = extrude_cut(part, sk, mm(SLOT_D), direction=True,
                             name=f"04_SCREW_X_{idx}_{j}")
            assert f2 is not None, f"螺钉十字槽 {idx}-{j} 失败"
            color(f2, C_SCREW, f"螺钉{idx}")

    part.ForceRebuild3(False)
    assert session.save(part, str(path)), "保存失败（检查是否有残留打开文档）"
    check(part, "01_base",
          exp_bbox=(104.0, 104.0, T_BASE + FOOT_T),
          exp_volume=expected_volume(), exp_bodies=1)
    print(f"\n已保存: {path}")
finally:
    session.close(part)
