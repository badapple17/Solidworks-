# -*- coding: utf-8 -*-
"""运动轨迹检查：py -3.12 a04_motion_check.py

验证三件事：
1) 底座是固定件（IComponent2.IsFixed 为 True）。
2) 除底座外，每个零件在 X/Y/Z 三个方向都不能平移：用 SetTransformAndSolve2
   强推 10 mm，重建后看求解器是否把它拉回原位。底座本身可以被这个 API 推动
   （SW2023 实测），所以底座只看 IsFixed，不做平移探针。
3) 用临时角度配合把立柱臂从 98° 转到 88°，整条链沿铰链圆弧走：
   X 向漂移 ≤ 0.01 mm；臂的实际转角 ≈ 10°；删除临时配合后姿态保留。
4) 铰链转轴探针：给上/下两个铰链各加一个临时角度配合驱动 +5°，从位姿变化里
   反解旋转轴——必须是世界 X（前后俯仰），且被驱动零件的原点位移 ≤ 0.01 mm
   （原点在销轴上，绕 X 转时原点不动；如果关节能左右摆，轴会是 Z 或原点会沿 X 漂）。
   注意：不能靠「推变换」测转动自由度。SW2023 里推移旋转会被求解器整块退回，
   实测 plate/turntable/hook 全部读成 0°，而它们其实能转——只有角度配合驱动的
   结果才可信。

脚本只读不改：结束时不保存，交付装配的展开姿态保持 98°。
结果写入 evidence/motion_check.json。
"""

import json
import math
from pathlib import Path

import pythoncom
import win32com.client

from asm_common import (
    SW_ALIGN_ALIGNED, comp_pose, find_planar_face, mate,
)
from stand_common import OUT
from sw_assembly import (
    SW_MATE_ANGLE, collect_mate_feature_summary, delete_mates,
    get_interference_detection,
)
from sw_connect import open_document
from sw_session import SolidWorksSession

RAD = math.radians
EVIDENCE = Path(__file__).parent / "evidence"
EVIDENCE.mkdir(exist_ok=True)
CHAIN = ("turntable", "pin_b", "arm", "pin_t", "plate", "hook_R", "hook_L", "phone")


def component_label(name):
    return (name or "").rsplit("-", 1)[0]


def load_components(asm):
    found = {}
    for comp in (asm.GetComponents(False) or []):
        found[comp.Name2] = comp
    base = next(c for n, c in found.items() if n.startswith("01_base"))
    by_prefix = {}
    for prefix, label in (("02_turntable", "turntable"), ("03_arm", "arm"),
                          ("04_pin", "pin_b"), ("05_pin", "pin_t"),
                          ("06_plate", "plate"), ("08_phone", "phone")):
        by_prefix[label] = next(c for n, c in found.items() if n.startswith(prefix))
    hooks = [c for n, c in found.items() if n.startswith("07_hook")]
    by_prefix["hook_R"] = next(c for c in hooks if (c.Name2 or "").endswith("-1"))
    by_prefix["hook_L"] = next(c for c in hooks if c is not by_prefix["hook_R"])
    return base, by_prefix


def positions(comps):
    return {label: comp_pose(comp)[0] for label, comp in comps.items()}


def axis_angle(rot, index):
    """旋转矩阵第 index 列（局部轴在世界系的方向）。"""
    return tuple(rot[r][index] for r in range(3))


def angle_between(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return math.degrees(math.acos(max(-1.0, min(1.0, dot))))


def variant(values):
    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, list(values))


def rot_matrix(t):
    """ArrayData 的列主序旋转 -> 行主序 3x3。"""
    return [[t[0], t[3], t[6]],
            [t[1], t[4], t[7]],
            [t[2], t[5], t[8]]]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def rot_delta(r0, r1):
    """返回 (转角 deg, 世界系转轴单位向量)。ΔR = R1 · R0ᵀ。"""
    d = mat_mul(r1, [[r0[j][i] for j in range(3)] for i in range(3)])
    tr = d[0][0] + d[1][1] + d[2][2]
    theta = math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1.0) / 2.0))))
    axis = [d[2][1] - d[1][2], d[0][2] - d[2][0], d[1][0] - d[0][1]]
    norm = math.sqrt(sum(v * v for v in axis))
    if norm < 1e-9:
        return theta, [0.0, 0.0, 0.0]
    axis = [v / norm for v in axis]
    if max(axis, key=abs) < 0:          # 统一符号：最大分量为正
        axis = [-v for v in axis]
    return theta, [round(v, 4) for v in axis]


def drive_hinge(asm, comp, get_a, get_b, settle_deg, test_deg, name):
    """先跳到 settle_deg 定位，再驱动到 test_deg，量这一段的转角/转轴/原点漂移。

    两步是为了只量一个已知的 5°：装配里没有能直接读出「当前夹角」的接口，
    用 settle 摆到已知角，再 +5° 驱动，测量才不依赖上游步骤把姿态改到哪。
    每次加配合前都要重新取面——重建会让之前取到的 IFace2 失效
    （实测报「被调用的对象已与其客户端断开连接」）。
    """
    first = mate(asm, SW_MATE_ANGLE, get_a(), get_b(),
                 angle=math.radians(settle_deg), name=f"{name}_SETTLE")
    asm.ForceRebuild3(False)
    delete_mates(asm, [first])          # 删配合后姿态保留在 settle_deg

    t0 = list(comp.Transform2.ArrayData)
    p0 = comp_pose(comp)[0]
    r0 = rot_matrix(t0)
    temp = mate(asm, SW_MATE_ANGLE, get_a(), get_b(),
                angle=math.radians(test_deg), name=name)
    asm.ForceRebuild3(False)
    p1 = comp_pose(comp)[0]
    theta, axis = rot_delta(r0, rot_matrix(comp.Transform2.ArrayData))
    drift = max(abs(p1[i] - p0[i]) for i in range(3))
    return temp, round(theta, 3), axis, round(drift, 3)


def nudge_and_read(asm, comp, t0, dx, dy, dz):
    data = list(t0)
    data[9] += dx / 1000.0
    data[10] += dy / 1000.0
    data[11] += dz / 1000.0
    xf = comp.Transform2
    xf.ArrayData = variant(data)
    comp.SetTransformAndSolve2(xf)
    asm.ForceRebuild3(False)
    p1 = comp_pose(comp)[0]
    # 还原：同样必须用 VARIANT，普通 list/tuple 会被静默丢弃
    xf2 = comp.Transform2
    xf2.ArrayData = variant(t0)
    comp.SetTransformAndSolve2(xf2)
    asm.ForceRebuild3(False)
    return p1


def main():
    asm_path = OUT / "a01_deployed.SLDASM"
    session = SolidWorksSession(visible=True, wait_seconds=20)
    result = {"assembly": str(asm_path), "status": "fail", "checks": {}}
    try:
        session.sw.CloseAllDocuments(True)
        asm = open_document(session.sw, str(asm_path), raise_on_error=True)
        asm.ForceRebuild3(False)
        base, comps = load_components(asm)

        # ---- 1. 底座固定 ----
        result["checks"]["base_fixed"] = bool(base.IsFixed)
        print(f"底座 IsFixed: {base.IsFixed}")

        # ---- 2. 交付姿态的干涉 ----
        inter = get_interference_detection(asm)
        result["checks"]["interference"] = inter
        print(f"交付姿态干涉: {inter['status']} / {inter['interference_count']} 处")

        # ---- 3. 角度驱动：98° -> 88° ----
        before = positions(comps)
        _, rot_before = comp_pose(comps["arm"])
        e_arm_back = find_planar_face(comps["arm"], "y", 0.003, 1)
        e_tt_top = find_planar_face(comps["turntable"], "z", 0.0108, 1)
        temp = mate(asm, SW_MATE_ANGLE, e_arm_back, e_tt_top,
                    angle=RAD(88.0), name="T_MOTION_CHECK")
        asm.ForceRebuild3(False)
        after = positions(comps)
        _, rot_after = comp_pose(comps["arm"])
        swept = angle_between(axis_angle(rot_before, 2), axis_angle(rot_after, 2))
        print(f"臂转角: {swept:.4f}°（目标 10°）")

        rows = []
        max_dx = 0.0
        for label in CHAIN:
            p0, p1 = before[label], after[label]
            dx, dy, dz = (p1[i] - p0[i] for i in range(3))
            max_dx = max(max_dx, abs(dx))
            rows.append({
                "component": label,
                "before_mm": [round(v, 3) for v in p0],
                "after_mm": [round(v, 3) for v in p1],
                "delta_mm": [round(v, 3) for v in (dx, dy, dz)],
            })
            print(f"  {label:9s} Δ=({dx:+8.3f},{dy:+8.3f},{dz:+8.3f}) mm")

        # ---- 4. 删临时配合后姿态保留 ----
        removed = delete_mates(asm, [temp])
        asm.ForceRebuild3(False)
        kept = positions(comps)
        max_keep = max(abs(kept[l][i] - after[l][i]) for l in CHAIN for i in range(3))
        print(f"删除临时配合 {removed} 个；姿态最大变化 {max_keep:.4f} mm")

        mates = [m for m in collect_mate_feature_summary(asm) if m["depth"] > 0]
        result["checks"].update({
            "swept_deg": round(swept, 4),
            "max_abs_dx_mm": round(max_dx, 4),
            "pose_kept_after_delete_mm": round(max_keep, 4),
            "temporary_mates_removed": removed,
            "mate_count": len(mates),
            "mate_names": [m["name"] for m in mates],
            "rows": rows,
        })

        # ---- 5. 平移自由度探针（非底座零件） ----
        dof = {}
        for label, comp in comps.items():
            t0 = list(comp.Transform2.ArrayData)
            p0 = comp_pose(comp)[0]
            moved = []
            for dx, dy, dz in ((10, 0, 0), (0, 10, 0), (0, 0, 10)):
                p1 = nudge_and_read(asm, comp, t0, dx, dy, dz)
                moved.append(round(max(abs(p1[i] - p0[i]) for i in range(3)), 3))
            dof[label] = moved
            print(f"  自由度 {label:9s} X/Y/Z 强推后位移 {moved} mm")
        result["checks"]["dof_probe_mm"] = dof

        # ---- 6. 铰链转轴探针：上/下铰链各驱动 +5°，反解转轴 ----
        hinge = {}
        bad_axes = []
        def arm_back():
            return find_planar_face(comps["arm"], "y", 0.003, 1)

        def tt_top():
            return find_planar_face(comps["turntable"], "z", 0.0108, 1)

        def plate_back():
            return find_planar_face(comps["plate"], "y", 0.006, 1)

        def arm_top():
            return find_planar_face(comps["arm"], "z", 0.100, 1)

        cases = (
            ("arm_lower", comps["arm"], "arm", arm_back, tt_top, 105.0, 110.0),
            ("plate_upper", comps["plate"], "plate", plate_back, arm_top, 110.0, 115.0),
        )
        temps = []
        for label, comp, key, get_a, get_b, settle, test in cases:
            temp, theta, axis, drift = drive_hinge(
                asm, comp, get_a, get_b, settle, test, f"T_AXIS_{label}")
            temps.append(temp)
            hinge[key] = {"angle_deg": theta, "axis": axis, "origin_drift_mm": drift}
            ok = abs(axis[0]) >= 0.999 and drift <= 0.01 and 3.0 <= theta <= 7.0
            print(f"  铰链 {label:12s} 驱动 +5° -> 实转 {theta:.3f}°  转轴 {axis}  "
                  f"原点漂移 {drift:.3f} mm  {'OK' if ok else 'FAIL'}")
            if not ok:
                bad_axes.append(label)
        if any(t is not None for t in temps):
            result["checks"]["hinge_temps_removed"] = delete_mates(
                asm, [t for t in temps if t is not None])
        result["checks"]["hinge_axis"] = hinge
        result["checks"]["hinge_axis_ok"] = not bad_axes

        passed = (
            result["checks"]["base_fixed"]
            and inter["status"] == "pass"
            and max_dx <= 0.01
            and abs(swept - 10.0) <= 0.05
            and max_keep <= 0.01
            and all(max(m) <= 0.01 for m in dof.values())
            and not bad_axes
        )
        result["status"] = "pass" if passed else "fail"
        print(f"\n运动检查: {result['status'].upper()}")
    finally:
        # 不保存（交付姿态不变）；关文档并退出本会话启动的实例，释放文件锁。
        session.finish(save=False)

    (EVIDENCE / "motion_check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"证据: {EVIDENCE / 'motion_check.json'}")
    if result["status"] != "pass":
        raise SystemExit("运动检查未通过")


if __name__ == "__main__":
    main()
