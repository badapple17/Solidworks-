# -*- coding: utf-8 -*-
"""08 手机参考件（OPPO Reno 14，157.9 × 74.73 × 7.42 mm）。

只是装配里的占位参考件，不做外观细节；四角 R10 圆角就是真机的实际轮廓。
局部坐标：背面在 Y=0，机身沿 -Y 长出 7.42 厚；X 为宽（±37.365），
Z 为高（0=底边，+157.9=顶边）。这样装配时直接放在背板正面 Y=3、
底边 Z=9.1（托钩硅胶垫顶面），不需要任何旋转。

尺寸来源：`estimated`——用户告知机型，按厂商标称三围取值。
"""

import math

from stand_common import OUT, mm, check, color_part
from sw_session import SolidWorksSession
from sw_part import sketch, sketch_line, sketch_arc, extrude_boss

W = 74.73
H = 157.9
T = 7.42
R = 10.0
C_PHONE = (196, 199, 204)


def rounded_area():
    return W * H - (4 - math.pi) * R**2


def expected_volume():
    return rounded_area() * T


session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
path = OUT / "08_phone_reno14.SLDPRT"
try:
    # 圆角矩形画在 Top Plane（u=X, v=-Z），沿 -Y 拉伸
    with sketch(part, "Top Plane", exact=True) as sk:
        x0, x1 = -W / 2, W / 2
        z0, z1 = 0.0, -H
        sketch_line(part, mm(x0 + R), mm(z0), mm(x1 - R), mm(z0))
        sketch_arc(part, mm(x1 - R), mm(z0 - R), mm(x1 - R), mm(z0),
                   mm(x1), mm(z0 - R), direction=-1)
        sketch_line(part, mm(x1), mm(z0 - R), mm(x1), mm(z1 + R))
        sketch_arc(part, mm(x1 - R), mm(z1 + R), mm(x1), mm(z1 + R),
                   mm(x1 - R), mm(z1), direction=-1)
        sketch_line(part, mm(x1 - R), mm(z1), mm(x0 + R), mm(z1))
        sketch_arc(part, mm(x0 + R), mm(z1 + R), mm(x0 + R), mm(z1),
                   mm(x0), mm(z1 + R), direction=-1)
        sketch_line(part, mm(x0), mm(z1 + R), mm(x0), mm(z0 - R))
        sketch_arc(part, mm(x0 + R), mm(z0 - R), mm(x0), mm(z0 - R),
                   mm(x0 + R), mm(z0), direction=-1)
    f = extrude_boss(part, sk, mm(T), direction=True, name="01_PHONE_BODY")
    assert f is not None, "手机拉伸失败"

    part.ForceRebuild3(False)
    color_part(part, C_PHONE, "手机参考件")
    session.save(part, str(path))
    check(part, "08_phone_reno14",
          exp_bbox=(W, T, H),
          exp_volume=expected_volume(), exp_bodies=1)
    print(f"\n已保存: {path}")
finally:
    session.close(part)
