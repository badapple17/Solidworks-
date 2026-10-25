# -*- coding: utf-8 -*-
"""百岁山风格水瓶的剖面几何（纯 Python，无 SolidWorks 依赖）。

坐标：x=半径（轴向剖面内），y=高度；单位 mm。

肩部用**两段相切圆弧**做 S 形长肩：
- 圆弧 1（凸）：圆心在直筒面内 (r0-R1, y0)，与直筒竖直相切；
- 圆弧 2（凹）：圆心在颈部面内 (r1+R2, y1)，与颈部竖直相切；
- 两弧在拐点 T 处外切（G1 连续），半径满足 S=R1+R2=(Δr²+Δh²)/(2Δr)。

轮廓由直线 + 圆弧组成，体积按 Pappus 定理 2π·x̄·A 对圆弧细分离散后精确计算。
`ops` 是绘制指令（直线串/圆弧），`profile` 是同一轮廓的密采样（供体积门禁）。
"""

import math

# ---------------- 参数区（全部 mm，风格自定 = user_delegated） ----------------
H = 235.0                 # 总高（570 ml 级水瓶）
R_BODY = 33.0             # 瓶身外半径（OD 66）
T_BODY = 0.8              # 瓶身壁厚（示意；真实 PET 约 0.4~0.6）
R_BODY_IN = R_BODY - T_BODY
Y_BODY_TOP = 150.0        # 直筒段顶端
Y_SHOULDER_TOP = 210.0    # 肩部顶端（支撑环下缘）
R_SHOULDER_TOP = 14.2     # 肩顶外半径
R_NECK = 13.0             # 颈外半径（OD 26）
R_NECK_IN = 10.9          # 颈内半径（颈壁较厚，便于锁盖）
R_RING = 15.4             # 防盗环（支撑环）外半径
Y_RING_TOP = 213.6
R_LIP = 13.4              # 瓶口凸缘
LABEL_Y0, LABEL_Y1 = 48.0, 120.0
LABEL_DEPTH = 0.3         # 标签带浅槽深
R_RECESS = R_BODY - LABEL_DEPTH
R_RECESS_IN = R_BODY_IN - LABEL_DEPTH

R_SHOULDER_OUT = 55.0     # 肩部外凸弧半径（拐点位置由相切条件决定）
R_SHOULDER_IN = 50.0      # 肩部内凸弧半径


def shoulder_solution(r0, y0, r1, y1, r_big):
    """两段相切圆弧解：返回 (C1, C2, T, R1, R2)。

    C1=(r0-R1,y0) 与直筒相切于 (r0,y0)；C2=(r1+R2,y1) 与颈部相切于 (r1,y1)；
    外切条件 |C1C2| = R1+R2 → S=R1+R2=(Δr²+Δh²)/(2Δr)，拐点 T 在 C1C2 连线上。
    """
    dr = r0 - r1
    dh = y1 - y0
    if dr <= 0 or dh <= 0:
        raise ValueError("肩部要求 r0>r1 且 y1>y0")
    s = (dr * dr + dh * dh) / (2.0 * dr)
    r1_rad = r_big
    r2_rad = s - r1_rad
    if r2_rad <= 0:
        raise ValueError(f"圆弧半径过大: R1={r1_rad}, R1+R2={s:.3f}")
    c1 = (r0 - r1_rad, y0)
    c2 = (r1 + r2_rad, y1)
    t = (c1[0] + (c2[0] - c1[0]) * r1_rad / s,
         c1[1] + (c2[1] - c1[1]) * r1_rad / s)
    return c1, c2, t, r1_rad, r2_rad


def arc_points(center, start, end, ccw, n=400):
    """按圆心/起点/终点采样圆弧（含两端点）。"""
    cx, cy = center
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)
    radius = math.hypot(start[0] - cx, start[1] - cy)
    if ccw:
        while a1 <= a0:
            a1 += 2.0 * math.pi
    else:
        while a1 >= a0:
            a1 -= 2.0 * math.pi
    return [(cx + radius * math.cos(a0 + (a1 - a0) * i / n),
             cy + radius * math.sin(a0 + (a1 - a0) * i / n)) for i in range(n + 1)]


def ridge(y):
    """示意螺纹棱：梯形截面，高 0.8、宽 2.2。"""
    return [(R_NECK, y), (13.8, y + 0.5), (13.8, y + 2.2), (R_NECK, y + 2.7)]


# ---------------- 肩部两段圆弧 ----------------
C1_OUT, C2_OUT, T_OUT, R1_OUT, R2_OUT = shoulder_solution(
    R_BODY, Y_BODY_TOP, R_SHOULDER_TOP, Y_SHOULDER_TOP, R_SHOULDER_OUT)
C1_IN, C2_IN, T_IN, R1_IN, R2_IN = shoulder_solution(
    R_BODY_IN, 151.2, R_NECK_IN, 211.2, R_SHOULDER_IN)

# 外肩：圆弧1（凸，逆时针）→ 圆弧2（凹，顺时针）
OUT_ARC1 = arc_points(C1_OUT, (R_BODY, Y_BODY_TOP), T_OUT, ccw=True)
OUT_ARC2 = arc_points(C2_OUT, T_OUT, (R_SHOULDER_TOP, Y_SHOULDER_TOP), ccw=False)
# 内肩：从颈部向下（圆弧2 反向 → 圆弧1 反向）
IN_ARC2 = arc_points(C2_IN, (R_NECK_IN, 211.2), T_IN, ccw=True)
IN_ARC1 = arc_points(C1_IN, T_IN, (R_BODY_IN, 151.2), ccw=False)

# ---------------- 直线段 ----------------
OUTER_HEAD = [
    (0.0, 8.0),            # 底凹中心
    (21.0, 8.0),           # 底凹顶面
    (24.5, 7.4),
    (27.5, 5.0),
    (29.0, 1.2),
    (30.5, 0.0),           # 支撑环内缘
    (32.2, 0.0),           # 支撑环外缘
    (32.8, 0.5),
    (R_BODY, 1.5),         # 底部外圆角
    (R_BODY, LABEL_Y0),
    (R_RECESS, LABEL_Y0 + 0.6),
    (R_RECESS, LABEL_Y1),
    (R_BODY, LABEL_Y1 + 0.6),
    (R_BODY, Y_BODY_TOP),  # → 接外肩圆弧1
]
OUTER_TAIL = [
    (R_SHOULDER_TOP, Y_SHOULDER_TOP),   # ← 外肩圆弧2 终点
    (R_RING, Y_SHOULDER_TOP + 0.4),
    (R_RING, Y_RING_TOP - 0.2),
    (R_NECK, Y_RING_TOP + 0.3),
]
OUTER_TAIL += ridge(217.0)
OUTER_TAIL += ridge(221.4)
OUTER_TAIL += ridge(225.8)
OUTER_TAIL += [
    (R_NECK, 231.2),
    (R_LIP, 231.7),
    (R_LIP, 234.2),
    (13.2, H),             # 瓶口外缘倒角
]

INNER_HEAD = [(R_NECK_IN, H), (R_NECK_IN, 211.2)]   # → 接内肩圆弧2
INNER_TAIL = [
    (R_BODY_IN, 151.2),    # ← 内肩圆弧1 终点
    (R_BODY_IN, 120.0),
    (R_RECESS_IN, 119.4),
    (R_RECESS_IN, 48.6),
    (R_BODY_IN, 48.0),
    (R_BODY_IN, 12.0),
    (31.5, 10.6),
    (30.0, 9.6),
    (28.0, 9.0),
    (25.0, 8.8),
    (0.0, 8.8),            # 内底中心
]

# 瓶口顶面：外轮廓终点 → 瓶颈内径（profile 里这两点相邻，隐含有向边；
# 草图必须显式画出来才能闭合）
MOUTH_TOP = [OUTER_TAIL[-1], INNER_HEAD[0]]

# ---------------- 绘制指令（直线串 / 圆弧） ----------------
ops = [
    ("line", OUTER_HEAD),
    ("arc", C1_OUT, (R_BODY, Y_BODY_TOP), T_OUT, True),
    ("arc", C2_OUT, T_OUT, (R_SHOULDER_TOP, Y_SHOULDER_TOP), False),
    ("line", OUTER_TAIL),
    ("line", MOUTH_TOP),
    ("line", INNER_HEAD),
    ("arc", C2_IN, (R_NECK_IN, 211.2), T_IN, True),
    ("arc", C1_IN, T_IN, (R_BODY_IN, 151.2), False),
    ("line", INNER_TAIL),
]
CLOSE_FROM = INNER_TAIL[-1]      # (0,8.8)
CLOSE_TO = OUTER_HEAD[0]         # (0,8.0)

# 同一轮廓的密采样（外轮廓自下而上 + 内轮廓自上而下，沿轴线闭合）
profile = (
    OUTER_HEAD
    + OUT_ARC1[1:]
    + OUT_ARC2[1:]
    + OUTER_TAIL[1:]
    + INNER_HEAD
    + IN_ARC2[1:]
    + IN_ARC1[1:]
    + INNER_TAIL[1:]
)


def polygon_area_centroid_x(pts):
    """闭合多边形 (x=半径, y) 的有向面积与形心 x；用于 Pappus 体积。"""
    area = 0.0
    cx = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
    area *= 0.5
    if abs(area) < 1e-9:
        raise RuntimeError("剖面面积为零：轮廓自交或未闭合")
    return area, cx / (6.0 * area)


def pappus_volume_ml(pts):
    area, cx = polygon_area_centroid_x(pts)
    return 2.0 * math.pi * cx * abs(area) / 1000.0


# 材料体积（闭合剖面 = 材料截面；圆弧已 400 分细分，误差 < 1e-7）
EXPECTED_VOLUME_ML = pappus_volume_ml(profile)
# 内腔容量（内表面 + 瓶口平面 + 轴线围成的区域，到瓶口满容量）
_inner_dense = (INNER_HEAD + IN_ARC2[1:] + IN_ARC1[1:] + INNER_TAIL[1:])
_cavity = list(reversed(_inner_dense)) + [(0.0, H)]
CAPACITY_ML = pappus_volume_ml(_cavity)
