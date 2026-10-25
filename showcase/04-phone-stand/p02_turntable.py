# -*- coding: utf-8 -*-
"""02 旋转转盘：Ø48 车削转盘 + 顶部 U 型座（双耳，销孔 Ø4.2 沿 X）。

实物照片显示 U 型座不在转盘中心，而是骑在转盘边缘：销轴中心在 (0, -22, 18)，
U 座底板 26×18 跨到 y=-31，比转盘边缘（R24）外伸 7 mm，从底座顶面上方掠过
（底板 z=4.8 + 7.4 = 12.2，底座顶面 10.0，间隙 2.2）。
局部坐标：原点在转盘底面中心，+Z 向上，销轴偏 -Y 方向（展开时手机朝 -Y）。
装配时转盘底面落在底座沉槽底 Z=7.4。
"""

import math

from stand_common import OUT, mm, check, color, C_METAL
from sw_session import SolidWorksSession
from sw_part import (
    sketch, sketch_circle, sketch_corner_rectangle, extrude_boss, extrude_cut,
    extrude_midplane, insert_offset_plane,
)

R_DISC = 24.0
T_DISC = 4.2
R_BOSS = 20.0
T_BOSS = 0.6
Z_BOSS_TOP = T_DISC + T_BOSS          # 4.8
RADIAL = 22.0                         # 销轴到转盘轴线的径向偏置（骑在边缘）
BASE_W, BASE_D, BASE_H = 26.0, 18.0, 6.0
Z_BASE_TOP = Z_BOSS_TOP + BASE_H      # 10.8
EAR_X_IN, EAR_X_OUT = 4.25, 9.25
EAR_Y, EAR_H = 7.0, 11.2
Z_EAR_TOP = Z_BASE_TOP + EAR_H        # 22.0
Z_PIN = 18.0
R_PIN = 2.1


def expected_volume():
    disc = math.pi * R_DISC**2 * T_DISC
    boss = math.pi * R_BOSS**2 * T_BOSS
    base = BASE_W * BASE_D * BASE_H
    ears = 2 * (EAR_X_OUT - EAR_X_IN) * (2 * EAR_Y) * EAR_H
    holes = 2 * math.pi * R_PIN**2 * (EAR_X_OUT - EAR_X_IN)
    return disc + boss + base + ears - holes


session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
path = OUT / "02_turntable.SLDPRT"
try:
    with sketch(part, "Front Plane", exact=True) as sk:
        sketch_circle(part, 0, 0, mm(R_DISC))
    f = extrude_boss(part, sk, mm(T_DISC), direction=False, name="01_DISC_D48")
    assert f is not None, "转盘拉伸失败"
    color(f, C_METAL, "转盘")

    # 凸台必须画在转盘顶面上，否则会埋在转盘里（首轮体积差正好等于凸台体积）
    boss_plane = insert_offset_plane(part, "Front Plane", mm(T_DISC), "Plane_Turntable_Top")
    with sketch(part, "Plane_Turntable_Top", exact=True) as sk:
        sketch_circle(part, 0, 0, mm(R_BOSS))
    f = extrude_boss(part, sk, mm(T_BOSS), direction=False, name="02_BOSS_D42")
    assert f is not None, "转盘凸台失败"

    # U 座底板（草图面偏到 Y=-RADIAL：Top Plane 本身在 Y=0）
    cradle_plane = insert_offset_plane(part, "Top Plane", mm(-RADIAL), "Plane_Cradle_Mid")
    with sketch(part, "Plane_Cradle_Mid", exact=True) as sk:
        # Top Plane: u=X, v=-Z  ->  v = -Z
        sketch_corner_rectangle(part, mm(-BASE_W / 2), mm(-Z_BASE_TOP),
                                mm(BASE_W / 2), mm(-Z_BOSS_TOP))
    # 中面拉伸 -> 关于草图面（Y=-RADIAL）对称
    f = extrude_midplane(part, sk, mm(BASE_D))
    assert f is not None, "U 座底板失败"
    f.Name = "03_CRADLE_BASE"
    color(f, C_METAL, "转盘座")

    # 双耳
    for sign, tag in ((1, "R"), (-1, "L")):
        x0, x1 = sorted((sign * EAR_X_IN, sign * EAR_X_OUT))
        with sketch(part, "Plane_Cradle_Mid", exact=True) as sk:
            sketch_corner_rectangle(part, mm(x0), mm(-Z_EAR_TOP),
                                    mm(x1), mm(-Z_BASE_TOP))
        f = extrude_midplane(part, sk, mm(2 * EAR_Y))
        assert f is not None, f"耳片 {tag} 失败"
        f.Name = f"04_EAR_{tag}"

    # Ø4.2 销孔，两个方向贯穿
    for direction, tag in ((True, "R"), (False, "L")):
        with sketch(part, "Right Plane", exact=True) as sk:
            # Right Plane: u=-Z, v=Y
            sketch_circle(part, mm(-Z_PIN), mm(-RADIAL), mm(R_PIN))
        f = extrude_cut(part, sk, 0.0, direction=direction, name=f"05_PIN_HOLE_{tag}")
        assert f is not None, f"销孔 {tag} 失败"

    part.ForceRebuild3(False)
    session.save(part, str(path))
    check(part, "02_turntable",
          exp_bbox=(2 * R_DISC, R_DISC + (RADIAL + BASE_D / 2), Z_EAR_TOP),
          exp_volume=expected_volume(), exp_bodies=1)
    print(f"\n已保存: {path}")
finally:
    session.close(part)
