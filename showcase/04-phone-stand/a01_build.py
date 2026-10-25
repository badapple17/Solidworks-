# -*- coding: utf-8 -*-
"""按姿态生成可动装配体：py -3.12 a01_build.py deployed|folded

配合链：底座(固定) → 转盘(Z 转) → 下销 → 立柱臂(X 转) → 上销 → 背板(X 转)
        → 两个托钩(绕卷边 X 转) → 手机(参考件，仅展开位)
U 座偏置：转盘上的销轴在 (0,-22,18) 局部坐标，所以转盘以上所有零件整体偏 -22 mm
（实物照片：U 座骑在转盘边缘，不在圆心）。
每个转动件只留一条绕 X 的转动自由度，其余自由度必须用定位配合消掉：
- 底座：`FixComponent()` 固定（AddComponent5 插入的第一个件默认不是固定件，
  不固定时拖动任何零件都会把整台支架带着平移）。
- 下销/上销：销头内侧面或销端面与座耳/臂外侧面重合，防止销轴轴向窜出。
- 背板：凸舌侧面与臂叉口内侧重合，防止背板沿上销滑出。
- 托钩：侧面到背板侧面 10 mm 距离配合，防止抱箍沿卷边滑出；两钩胶垫顶面重合，
  保证左右钩同步翻转。
- 手机：背面贴背板 + 底面贴右钩胶垫 + 手机右视基准面与背板右视基准面重合，
  消掉最后一个 X 向平移自由度。
姿态用临时角度配合驱动，随后删除配合（本机 SW2023 的 SetTransformAndSolve2
加不上旋转，这是已验证的替代路线；删配合后姿态保留）。
托钩同步后，摆姿态只能给一个钩加临时角度（另一个由同步配合跟随），否则 error 5。

角度基准（都用与转轴平行的平面）：
  T_ARM   臂背面(+Y) ↔ 转盘座顶面(+Z)：初始 90°，后仰 α → 90+α
  T_PLATE 展开：背板背面(+Y) ↔ 臂顶面(+Z) = 90+β
          收拢：背板背面(+Y) ↔ 臂背面(+Y) = 0°
  T_HOOK  展开：抱箍端面 ↔ 背板底面(-Z) = 120°
          收拢：托钩胶垫顶面(+Z) ↔ 背板背面(+Y) = 0°
角度配合只约束夹角的绝对值：相对转角 ψ 与 -ψ（或 180-ψ）给出同一个夹角。
「垂直参考面 + 90°」恰好是 ψ=0 与 ψ=180 的分界，收拢位用它时求解器把背板
折回压到臂上（干涉 11 处）。目标夹角为 0° 的「平行参考面」只有一个解，收拢位改用它。
"""

import math
import sys

from stand_common import OUT
from sw_session import SolidWorksSession
from sw_assembly import (
    add_component, collect_mate_feature_summary, delete_mates,
    get_assembly_entity, get_component_feature,
    SW_MATE_COINCIDENT, SW_MATE_CONCENTRIC, SW_MATE_DISTANCE,
)
from asm_common import (
    SW_MATE_ANGLE, SW_ALIGN_ALIGNED, SW_ALIGN_CLOSEST, SW_ALIGN_ANTI,
    mate, find_planar_face, find_face_by_normal, cyl, comp_pose, comp_bbox,
)

FAILS = []


def try_mate(label, fn):
    """fn 是零参可调用：选面/加配合都在 fn 里求值，任一步失败都只记一笔。"""
    try:
        m = fn()
        print(f"  {label} OK")
        return m
    except Exception as exc:
        FAILS.append(f"{label}: {exc}")
        print(f"  {label} 失败: {exc}")
        return None


DEPLOYED = {
    "file": "a01_deployed.SLDASM",
    "arm_deg": 8.0,        # 立柱臂后仰
    "plate": ("arm_top", 90.0 + 17.0),   # 背板相对臂再后仰 17°；总后仰 25°
    "hook": ("clip_end", 120.0),         # 抱箍端面 与 背板底面 夹角
    "phone": True,
}
FOLDED = {
    "file": "a02_folded.SLDASM",
    "arm_deg": -90.0,      # 90-90=0，臂前倒平放
    "plate": ("arm_back", 0.0),          # 背板与臂共线
    "hook": ("pad_top", 0.0),            # 托板翻 90° 贴到背板背面
    "phone": False,
}
POSE = DEPLOYED if (len(sys.argv) < 2 or sys.argv[1] != "folded") else FOLDED
RAD = math.radians

HOOK_X = 27.0              # 托钩中心到板中心；手机平底只到 ±27.365，再外就托空


def plane(comp, axis, value, sign):
    return find_planar_face(comp, axis, value / 1000.0, sign)


def rotate_diag(comp):
    _, rot = comp_pose(comp)
    return tuple(round(rot[i][i], 3) for i in range(3))


def report(tag, items):
    for name, comp in items:
        pos = comp_pose(comp)[0]
        print(f"  {name} 平移 {tuple(round(v, 2) for v in pos)} "
              f"转置对角 {rotate_diag(comp)}")


session = SolidWorksSession(visible=True, wait_seconds=20)
asm = session.new_assembly()
path = OUT / POSE["file"]
try:
    base = add_component(asm, str(OUT / "01_base.SLDPRT"), 0, 0, 0.0044, sw=session.sw)
    # 转盘包围盒中心在局部 y=-3.5（U 座外伸到 -31），放置后转盘轴线才落在 y=0
    tt = add_component(asm, str(OUT / "02_turntable.SLDPRT"), 0, -0.0035, 0.0184, sw=session.sw)
    pin_b = add_component(asm, str(OUT / "04_pin_bottom.SLDPRT"), 0, -0.022, 0.0254, sw=session.sw)
    arm = add_component(asm, str(OUT / "03_arm.SLDPRT"), 0, -0.022, 0.0724, sw=session.sw)
    pin_t = add_component(asm, str(OUT / "05_pin_top.SLDPRT"), 0, -0.022, 0.1174, sw=session.sw)
    plate = add_component(asm, str(OUT / "06_plate.SLDPRT"), 0, -0.021, 0.1744, sw=session.sw)
    hook_r = add_component(asm, str(OUT / "07_hook.SLDPRT"),
                           0.027, -0.02225, 0.1312, sw=session.sw)
    # 托钩局部包围盒中心 (y,z)=(-4.75,3.3)；卷边轴心在世界 (-17.5,127.9)
    hook_l = add_component(asm, str(OUT / "07_hook.SLDPRT"),
                           -0.027, -0.02225, 0.1312, sw=session.sw)
    phone = None
    if POSE["phone"]:
        phone = add_component(asm, str(OUT / "08_phone_reno14.SLDPRT"),
                              0, -0.02271, 0.2118, sw=session.sw)

    print("-- 转盘 --")
    try_mate("M01_TT_D48", lambda: mate(
        asm, SW_MATE_CONCENTRIC, cyl(tt, 23.9, 24.1), cyl(base, 24.9, 25.1),
        align=SW_ALIGN_CLOSEST, name="M01_TT_D48"))
    try_mate("M02_TT_SEAT", lambda: mate(
        asm, SW_MATE_COINCIDENT, plane(tt, "z", 0.0, -1), plane(base, "z", 7.4, 1),
        align=SW_ALIGN_ANTI, name="M02_TT_SEAT"))

    print("-- 下销 --")
    try_mate("M03_PINB_HOLE", lambda: mate(
        asm, SW_MATE_CONCENTRIC, cyl(pin_b, 1.95, 2.05),
        cyl(tt, 2.05, 2.15, at=("z", 18.0)), align=SW_ALIGN_CLOSEST, name="M03_PINB_HOLE"))

    print("-- 立柱臂 --")
    try_mate("M05_ARM_HOLE", lambda: mate(
        asm, SW_MATE_CONCENTRIC, cyl(pin_b, 1.95, 2.05),
        cyl(arm, 2.05, 2.15, at=("z", 0.0)), align=SW_ALIGN_CLOSEST, name="M05_ARM_HOLE"))
    try_mate("M06_ARM_AXIAL", lambda: mate(
        asm, SW_MATE_COINCIDENT, plane(arm, "x", 4.25, 1), plane(tt, "x", 4.25, -1),
        align=SW_ALIGN_ANTI, name="M06_ARM_AXIAL"))

    print("-- 上销 --")
    try_mate("M07_PINT_FORK", lambda: mate(
        asm, SW_MATE_CONCENTRIC, cyl(pin_t, 1.95, 2.05),
        cyl(arm, 2.05, 2.15, at=("z", 92.0)), align=SW_ALIGN_CLOSEST, name="M07_PINT_FORK"))

    print("-- 背板 --")
    try_mate("M09_PLATE_TAB", lambda: mate(
        asm, SW_MATE_CONCENTRIC, cyl(plate, 2.05, 2.15), cyl(pin_t, 1.95, 2.05),
        align=SW_ALIGN_CLOSEST, name="M09_PLATE_TAB"))

    print("-- 托钩 --")
    for hook, tag in ((hook_r, "R"), (hook_l, "L")):
        try_mate(f"M11_CLIP_{tag}", (lambda h=hook, t=tag: mate(
            asm, SW_MATE_CONCENTRIC, cyl(h, 2.5, 2.6), cyl(plate, 2.45, 2.55),
            align=SW_ALIGN_CLOSEST, name=f"M11_CLIP_{t}")))

    if phone is not None:
        print("-- 手机 --")
        try_mate("M13_PHONE_BACK", lambda: mate(
            asm, SW_MATE_COINCIDENT, plane(phone, "y", 0.0, 1), plane(plate, "y", 3.0, -1),
            align=SW_ALIGN_ANTI, name="M13_PHONE_BACK"))
        try_mate("M14_PHONE_BOTTOM", lambda: mate(
            asm, SW_MATE_COINCIDENT, plane(phone, "z", 0.0, -1), plane(hook_r, "z", 4.95, 1),
            align=SW_ALIGN_ANTI, name="M14_PHONE_BOTTOM"))

    print("-- 定位：固定底座 + 消除轴向窜动 --")
    asm.ClearSelection2(True)
    if not base.Select2(False, 0):
        raise RuntimeError("无法选择底座")
    asm.FixComponent()
    if not base.IsFixed:
        raise RuntimeError("底座未固定：拖动时会带着整台支架平移")
    print("  底座 IsFixed:", base.IsFixed)
    try_mate("M04_PINB_AXIAL", lambda: mate(
        asm, SW_MATE_COINCIDENT,
        plane(pin_b, "x", 9.25, -1), plane(tt, "x", 9.25, 1),
        align=SW_ALIGN_ANTI, name="M04_PINB_AXIAL"))
    try_mate("M08_PINT_AXIAL", lambda: mate(
        asm, SW_MATE_COINCIDENT,
        plane(pin_t, "x", 13.0, 1), plane(arm, "x", 13.0, 1),
        align=SW_ALIGN_ALIGNED, name="M08_PINT_AXIAL"))
    try_mate("M10_PLATE_AXIAL", lambda: mate(
        asm, SW_MATE_COINCIDENT,
        plane(plate, "x", 4.0, 1), plane(arm, "x", 4.0, -1),
        align=SW_ALIGN_ANTI, name="M10_PLATE_AXIAL"))
    for hook, tag, sign in ((hook_r, "R", 1), (hook_l, "L", -1)):
        try_mate(f"M12_CLIP_{tag}_AXIAL", (lambda h=hook, t=tag, s=sign: mate(
            asm, SW_MATE_DISTANCE,
            plane(h, "x", s * 11.0, s), plane(plate, "x", s * 48.0, s),
            align=SW_ALIGN_ALIGNED, distance=0.010,
            name=f"M12_CLIP_{t}_AXIAL")))
    try_mate("M16_HOOK_SYNC", lambda: mate(
        asm, SW_MATE_COINCIDENT,
        plane(hook_r, "z", 4.95, 1), plane(hook_l, "z", 4.95, 1),
        align=SW_ALIGN_ALIGNED, name="M16_HOOK_SYNC"))
    if phone is not None:
        def phone_center():
            f_phone = get_component_feature(phone, ["Right Plane", "右视基准面"])
            f_plate = get_component_feature(plate, ["Right Plane", "右视基准面"])
            return mate(asm, SW_MATE_COINCIDENT,
                        get_assembly_entity(phone, f_phone),
                        get_assembly_entity(plate, f_plate),
                        align=SW_ALIGN_ALIGNED, name="M15_PHONE_AXIAL")
        try_mate("M15_PHONE_AXIAL", phone_center)

    print("-- 配合后位姿 --")
    report("配合后", (("转盘", tt), ("下销", pin_b), ("臂", arm), ("上销", pin_t),
                     ("板", plate), ("钩R", hook_r), ("钩L", hook_l)))
    if phone is not None:
        print(f"  手机 平移 {tuple(round(v, 2) for v in comp_pose(phone)[0])}")

    # ---------------- 姿态：临时角度配合 ----------------
    print("-- 摆姿态 --")
    e_tt_top = plane(tt, "z", 10.8, 1)
    e_arm_back = plane(arm, "y", 3.0, 1)
    e_arm_top = plane(arm, "z", 100.0, 1)
    e_plate_back = plane(plate, "y", 6.0, 1)
    e_plate_bot = plane(plate, "z", 14.5, -1)
    e_clip_end = {t: find_face_by_normal(h, (0.0, 0.8660254, 0.5))
                  for t, h in (("R", hook_r), ("L", hook_l))}
    e_pad_top = {t: plane(h, "z", 4.95, 1) for t, h in (("R", hook_r), ("L", hook_l))}
    plate_ref = {"arm_top": e_arm_top, "arm_back": e_arm_back}[POSE["plate"][0]]
    hook_ref, hook_other = {"clip_end": (e_clip_end, e_plate_bot),
                            "pad_top": (e_pad_top, e_plate_back)}[POSE["hook"][0]]

    temps = []
    temps.append(mate(asm, SW_MATE_ANGLE, e_arm_back, e_tt_top,
                      angle=RAD(90.0 + POSE["arm_deg"]), name="T_ARM"))
    temps.append(mate(asm, SW_MATE_ANGLE, e_plate_back, plate_ref,
                      angle=RAD(POSE["plate"][1]), name="T_PLATE"))
    # 手机在时，M14 已把右钩转角定死，M16 又把左钩同步到右钩，两个钩都不能再加角度；
    # 无手机（收拢位）时只给右钩加，左钩由 M16 跟随，否则第二个角度配合冗余 error 5。
    if phone is None:
        temps.append(mate(asm, SW_MATE_ANGLE, hook_ref["R"], hook_other,
                          angle=RAD(POSE["hook"][1]), name="T_HOOK_R"))
    print("  临时配合:", [m.Name for m in temps if m])

    print("-- 摆姿态后 --")
    report("姿态", (("臂", arm), ("板", plate), ("钩R", hook_r), ("钩L", hook_l)))
    # IAssemblyDoc.GetBox 参数个数与 IComponent2.GetBox 不同（实测 '无效的参数数目'），用组件并集
    boxes = [comp_bbox(c) for c in (base, tt, pin_b, arm, pin_t, plate, hook_r, hook_l)]
    lo = [min(b[i] for b in boxes) for i in range(3)]
    hi = [max(b[i + 3] for b in boxes) for i in range(3)]
    print("  支架包围盒 mm:", tuple(round(v, 1) for v in lo + hi),
          "尺寸", tuple(round(hi[i] - lo[i], 1) for i in range(3)))
    if phone is not None:
        print("  手机 包围盒 mm:", tuple(round(v, 1) for v in comp_bbox(phone)))

    # 删掉临时角度配合，姿态保留，铰链恢复可拖动
    print("  删除临时配合:", delete_mates(asm, temps))
    # IAssemblyDoc 没有 GetMates；配合在特征树 MateGroup 下
    mates_left = [m["name"] for m in collect_mate_feature_summary(asm) if m["depth"] > 0]
    print(f"  删除后配合 {len(mates_left)} 个:", mates_left)
    asm.ForceRebuild3(False)
    print("-- 删除临时配合 + 重建后 --")
    report("重建后", (("臂", arm), ("板", plate), ("钩R", hook_r), ("钩L", hook_l)))

    assert session.save(asm, str(path)), "保存失败（检查是否有残留打开文档）"
    print(f"\n已保存: {path}")
    if FAILS:
        print("失败配合:")
        for line in FAILS:
            print("  -", line)
finally:
    # 关掉装配体后，被引用的零件文档仍留在内存里：既会让下次重建零件时
    # SaveAs 返回错误码 1，又会占着文件锁让用户打不开交付文件。
    # finish() = 关全部文档 + 退出本会话启动的实例。
    session.finish()
