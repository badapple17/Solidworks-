# -*- coding: utf-8 -*-
"""07 折叠托钩（左右同一零件，装配时用两件）：托板 + 前挡边 + 硅胶垫 + C 形抱箍。

局部坐标：原点在抱箍轴线（= 背板底部卷边轴线）；断面画在 Right Plane
（u=-Z, v=Y），沿 X 拉伸。抱箍包角 240°（YZ 角 60°..300°），开口朝 +Y。

几何约束（决定托板只能这么短）：
- 内孔 r=2.55 必须整周让给 Ø5 卷边，托板底面抬到 z=+2.60（孔顶 2.55 之上），
  抱箍外径 3.4，所以托板顶面 3.75、硅胶垫顶面 4.95 —— 手机底边因此落在
  抱箍最高点(+3.4) 之上，不会被抱箍顶住；
- 本件原点在卷边轴心 = 背板局部 (Y=4.5, Z=10.5)。手机背面贴背板 Y=3 -> 本件
  y=-1.5；手机厚 7.42 -> 屏面 y=-8.92。前挡边内侧面 y=-9.5，与屏面留 0.58。
- 胶垫 +y 端停在 y=-1.7（手机背面前 0.2），否则伸进背板板体（板体 Y 3..6, Z>=14.5）；
  托板顶面只到 z=3.75（背板 Z=14.25 < 14.5），可以一直伸到 y=+0.5 加厚与抱箍的连接。
- 首版把背板坐标里的屏面 Y=-4.42 直接当成本件坐标，挡边整块切进手机 150 mm³，
  装配干涉检查才查出来——零件自身的体积/包围盒校验发现不了这类坐标系错误。

展开位：零旋转；收拢位：绕 X 轴翻 90°（托板贴到背板背面）。
特征顺序：先画全部矩形，最后画圆弧——本机 SW2023 在 Right Plane 上
画过圆弧后 CreateCornerRectangle 会静默返回 None。
"""

import math

from stand_common import (
    OUT, mm, check, color, color_part, measure, annulus_sector, draw_annulus_sector,
    C_BODY, C_RUBBER,
)
from sw_session import SolidWorksSession
from sw_part import (
    sketch, sketch_line, sketch_corner_rectangle, extrude_midplane,
)


def rect_lines(part, u0, v0, u1, v1):
    """四条线画矩形（毫米输入）。CreateCornerRectangle 在角点靠近草图轴时会
    静默吸附到轴上（实测 0.5 mm 被吸到 0），此时改用逐条线。"""
    sketch_line(part, mm(u0), mm(v0), mm(u1), mm(v0))
    sketch_line(part, mm(u1), mm(v0), mm(u1), mm(v1))
    sketch_line(part, mm(u1), mm(v1), mm(u0), mm(v1))
    sketch_line(part, mm(u0), mm(v1), mm(u0), mm(v0))

R_OUT, R_IN = 3.4, 2.55
THETA0, THETA1 = 60.0, 300.0          # YZ 角（自 +Y 转向 +Z）
W_HOOK = 22.0
PAD_W = 15.0

Y_PHONE_BACK = -1.5                    # 手机背面（= 背板 Y=3）在本件局部的 y
PADDLE_Y0, PADDLE_Y1 = -11.2, 0.5
PADDLE_Z0, PADDLE_Z1 = 2.60, 3.75     # 底面 0.05 高于内孔顶，不侵入抱箍内孔
LIP_Y0, LIP_Y1 = -11.2, -9.5          # 挡边内侧面 y=-9.5，与手机屏面 -8.92 留 0.58
LIP_Z1 = 10.0
PAD_Y0, PAD_Y1 = -9.5, -1.7            # +y 端不进背板板体
PAD_Z0, PAD_Z1 = 3.75, 4.95           # 手机底面落在这个高度


def paddle_sector_overlap():
    """托板与抱箍在 YZ 断面的重叠面积。

    托板 z∈[2.60,3.75]、y∈[-6.7,0.5]；该高度已高于内孔顶(R_IN=2.55)，
    抱箍断面只剩外圆：y ∈ [-√(R²-z²), min(√(R²-z²), z/√3)]
    （θ ∈ [60°,300°] 在 z>0 时只限制 +y 侧 y ≤ z/√3）。
    """
    def w(z):
        if z > R_OUT:
            return 0.0
        circ = math.sqrt(max(0.0, R_OUT**2 - z * z))
        lo = max(-circ, PADDLE_Y0)
        hi = min(circ, z / math.sqrt(3.0), PADDLE_Y1)   # +y 侧受 θ 角与托板端面限制
        return max(0.0, hi - lo)

    n = 20000
    a, b = PADDLE_Z0, min(PADDLE_Z1, R_OUT)
    if b <= a:
        return 0.0
    h = (b - a) / n
    s = w(a) + w(b)
    for i in range(1, n):
        s += (4 if i % 2 else 2) * w(a + i * h)
    return s * h / 3.0


def expected_volume():
    sector = math.pi * (R_OUT**2 - R_IN**2) * (THETA1 - THETA0) / 360 * W_HOOK
    paddle = (PADDLE_Y1 - PADDLE_Y0) * (PADDLE_Z1 - PADDLE_Z0) * W_HOOK
    lip = (LIP_Y1 - LIP_Y0) * (LIP_Z1 - PADDLE_Z0) * W_HOOK
    pad = (PAD_Y1 - PAD_Y0) * (PAD_Z1 - PAD_Z0) * PAD_W
    o_paddle_sector = paddle_sector_overlap() * W_HOOK
    o_paddle_lip = (LIP_Y1 - LIP_Y0) * (PADDLE_Z1 - PADDLE_Z0) * W_HOOK
    # 胶垫底面 = 托板顶面（相贴不重叠）；挡边、胶垫都够不到抱箍半径 3.4
    return sector + paddle + lip + pad - o_paddle_sector - o_paddle_lip


def expected_bbox():
    y_max = max(PADDLE_Y1, R_OUT * math.cos(math.radians(THETA0)),
                R_OUT * math.cos(math.radians(THETA1)))
    return (W_HOOK, y_max - PADDLE_Y0, LIP_Z1 - (-R_OUT))


session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
path = OUT / "07_hook.SLDPRT"
try:
    # 1) 托板
    with sketch(part, "Right Plane", exact=True) as sk:
        rect_lines(part, -PADDLE_Z1, PADDLE_Y0, -PADDLE_Z0, PADDLE_Y1)
    f = extrude_midplane(part, sk, mm(W_HOOK))
    assert f is not None, "托板失败"
    f.Name = "01_PADDLE"
    print(f"  step1 vol {measure(part)['volume_mm3']:.3f}")

    # 2) 前挡边
    with sketch(part, "Right Plane", exact=True) as sk:
        sketch_corner_rectangle(part, mm(-LIP_Z1), mm(LIP_Y0),
                                mm(-PADDLE_Z0), mm(LIP_Y1))
    f = extrude_midplane(part, sk, mm(W_HOOK))
    assert f is not None, "挡边失败"
    f.Name = "02_LIP"
    print(f"  step2 vol {measure(part)['volume_mm3']:.3f}")

    # 3) 硅胶垫（角点 v=0.5 贴近草图轴，用四条线，避免静默吸附）
    with sketch(part, "Right Plane", exact=True) as sk:
        rect_lines(part, -PAD_Z1, PAD_Y0, -PAD_Z0, PAD_Y1)
    f = extrude_midplane(part, sk, mm(PAD_W))
    assert f is not None, "硅胶垫失败"
    f.Name = "03_PAD"
    color(f, C_RUBBER, "硅胶垫")
    print(f"  step3 vol {measure(part)['volume_mm3']:.3f}")

    # 4) C 形抱箍（最后画，避免圆弧打断矩形工具）
    with sketch(part, "Right Plane", exact=True) as sk:
        draw_annulus_sector(part, annulus_sector(
            0, 0, mm(R_OUT), mm(R_IN), THETA0 + 90, THETA1 + 90))
    f = extrude_midplane(part, sk, mm(W_HOOK))
    assert f is not None, "抱箍失败"
    f.Name = "04_CLIP"
    color(f, C_BODY, "抱箍")
    print(f"  step4 vol {measure(part)['volume_mm3']:.3f}")

    part.ForceRebuild3(False)
    color_part(part, C_BODY, "托钩")
    assert session.save(part, str(path)), "保存失败（检查是否有残留打开文档）"
    check(part, "07_hook",
          exp_bbox=expected_bbox(),
          exp_volume=expected_volume(), exp_bodies=1)
    print(f"\n已保存: {path}")
finally:
    session.close(part)
