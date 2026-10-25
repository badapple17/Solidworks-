# -*- coding: utf-8 -*-
"""03 立柱臂：26 宽 × 6 厚扁杆，下端收窄成舌头（14 深，插进转盘双耳），
顶端开叉（夹背板凸舌），杆身开 6 mm 长圆孔。销轴另做零件（04/05）。

局部坐标：原点在下端销孔中心；+Z 沿杆身向上，+X 为杆宽方向，+Y 为杆厚方向。
上端销孔中心在 (0, 0, 92)。
"""

import math

from stand_common import OUT, mm, check, color, C_BODY
from sw_session import SolidWorksSession
from sw_part import (
    sketch, sketch_line, sketch_circle, sketch_slot, sketch_corner_rectangle,
    extrude_cut, extrude_midplane,
)

W_BODY = 26.0
T_BODY = 6.0
W_NECK = 8.5  # 与转盘双耳内距 2*4.25 零间隙配合
D_NECK = 14.0
Z_NECK_TOP = 12.0
Z_NECK_BOT = -6.0
Z_BODY_TOP = 74.0
Z_FORK_TOP = 100.0
Z_PIN_TOP = 92.0
X_FORK_GAP = 4.0
R_HOLE = 2.1          # Ø4.2 销孔
SLOT_W = 6.0          # sketch_slot 第 5 参数是槽宽，不是半径
SLOT_Z0, SLOT_Z1 = 22.0, 68.0     # 圆心距；胶囊实际到 19..71，留在杆身内

PROFILE = [
    (-W_NECK / 2, Z_NECK_BOT), (W_NECK / 2, Z_NECK_BOT),
    (W_NECK / 2, Z_NECK_TOP), (W_BODY / 2, Z_NECK_TOP),
    (W_BODY / 2, Z_BODY_TOP), (W_BODY / 2, Z_FORK_TOP),
    (X_FORK_GAP, Z_FORK_TOP), (X_FORK_GAP, Z_BODY_TOP),
    (-X_FORK_GAP, Z_BODY_TOP), (-X_FORK_GAP, Z_FORK_TOP),
    (-W_BODY / 2, Z_FORK_TOP), (-W_BODY / 2, Z_BODY_TOP),
    (-W_BODY / 2, Z_NECK_TOP), (-W_NECK / 2, Z_NECK_TOP),
]


def prong_w():
    return W_BODY / 2 - X_FORK_GAP


def expected_volume():
    neck = W_NECK * D_NECK * (Z_NECK_TOP - Z_NECK_BOT)
    body = W_BODY * T_BODY * (Z_BODY_TOP - Z_NECK_TOP)
    prongs = 2 * prong_w() * T_BODY * (Z_FORK_TOP - Z_BODY_TOP)
    r = SLOT_W / 2
    slot = (SLOT_W * (SLOT_Z1 - SLOT_Z0) + math.pi * r**2) * T_BODY
    hole_bot = math.pi * R_HOLE**2 * W_NECK
    hole_top = 2 * math.pi * R_HOLE**2 * prong_w()
    return neck + body + prongs - slot - hole_bot - hole_top


session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
path = OUT / "03_arm.SLDPRT"
try:
    # 1) 主轮廓（XZ 面 -> Top Plane；v = -Z）
    with sketch(part, "Top Plane", exact=True) as sk:
        prev = PROFILE[0]
        for (x, z) in PROFILE[1:]:
            sketch_line(part, mm(prev[0]), mm(-prev[1]), mm(x), mm(-z))
            prev = (x, z)
        sketch_line(part, mm(prev[0]), mm(-prev[1]),
                    mm(PROFILE[0][0]), mm(-PROFILE[0][1]))
    f = extrude_midplane(part, sk, mm(T_BODY))
    assert f is not None, "杆身拉伸失败"
    f.Name = "01_ARM_BODY"
    color(f, C_BODY, "立柱臂")

    # 2) 下端舌头加厚到 14（补齐两侧各 4；原 6 厚是它的子集，不重复计体积）
    with sketch(part, "Top Plane", exact=True) as sk:
        sketch_corner_rectangle(part, mm(-W_NECK / 2), mm(-Z_NECK_TOP),
                                mm(W_NECK / 2), mm(-Z_NECK_BOT))
    f = extrude_midplane(part, sk, mm(D_NECK))
    assert f is not None, "舌头加厚失败"
    f.Name = "02_NECK_BLOCK"

    # 3) 长圆孔（6 宽，双向贯穿 6 厚杆身）
    for direction, tag in ((True, "F"), (False, "B")):
        with sketch(part, "Top Plane", exact=True) as sk:
            sketch_slot(part, 0, mm(-SLOT_Z0), 0, mm(-SLOT_Z1), mm(SLOT_W))
        f = extrude_cut(part, sk, 0.0, direction=direction, name=f"03_SLOT_{tag}")
        assert f is not None, f"长圆孔 {tag} 失败"

    # 4) 上下销孔 Ø4.2（贯穿全部实体，左右各切一次）
    for z, tag in ((0.0, "BOT"), (Z_PIN_TOP, "TOP")):
        for direction, side in ((True, "R"), (False, "L")):
            with sketch(part, "Right Plane", exact=True) as sk:
                sketch_circle(part, mm(-z), 0, mm(R_HOLE))
            f = extrude_cut(part, sk, 0.0, direction=direction,
                            name=f"04_PINHOLE_{tag}_{side}")
            assert f is not None, f"销孔 {tag}-{side} 失败"

    part.ForceRebuild3(False)
    session.save(part, str(path))
    check(part, "03_arm",
          exp_bbox=(W_BODY, D_NECK, Z_FORK_TOP - Z_NECK_BOT),
          exp_volume=expected_volume(), exp_bodies=1)
    print(f"\n已保存: {path}")
finally:
    session.close(part)
