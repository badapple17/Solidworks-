# -*- coding: utf-8 -*-
"""
汽车轮毂（单件）示意模型 v3 — 前后对称双面 5 辐

模式：A 示意模式（尺寸不追问，按常规比例取值，来源标 assumed）
坐标：X=宽度方向、Y=高度方向、Z=车轮轴向；Front Plane (XY) 为前轮辐正面，
Back Plane 一侧为对称的后轮辐正面。
主体：Right Plane 半剖轮廓 + 中心线，绕 Z 轴旋转 360°，轮廓同时包含
前后两套轮毂/轮辐板；辐窗、中心孔、螺栓孔贯穿切除时自然同时切穿两面。
"""
import json
import math
import os
import sys
from pathlib import Path

def _find_skill_dir() -> Path:
    override = (
        os.environ.get("SOLIDWORKS_PLUS_PLUS_SKILL_DIR")
        or os.environ.get("SOLIDWORKS_MODELING_SKILL_DIR")
    )
    here = Path(__file__).resolve()
    candidates = [
        Path(override).expanduser() if override else None,
        here.parents[2] / "skills" / "solidworks-plus-plus",  # 仓库布局 <repo>/showcase/<case>/
        here.parents[2] / "solidworks-plus-plus",  # 发布包布局 <release>/showcase/<case>/
        Path.home() / ".claude" / "skills" / "solidworks-plus-plus",
        Path.home() / ".codex" / "skills" / "solidworks-plus-plus",
        Path.home() / ".agents" / "skills" / "solidworks-plus-plus",
        # 旧名回退：升级前安装的目录仍可用
        here.parents[2] / "solidworks-modeling",
        Path.home() / ".claude" / "skills" / "solidworks-modeling",
        Path.home() / ".codex" / "skills" / "solidworks-modeling",
        Path.home() / ".agents" / "skills" / "solidworks-modeling",
    ]
    for candidate in candidates:
        if candidate and (candidate / "scripts" / "sw_session.py").is_file():
            return candidate.resolve()
    raise SystemExit(
        "找不到 solidworks-plus-plus 技能目录；"
        "请设置 SOLIDWORKS_PLUS_PLUS_SKILL_DIR（或旧名 "
        "SOLIDWORKS_MODELING_SKILL_DIR）指向技能根目录。"
    )


SKILL = _find_skill_dir()
sys.path.insert(0, str(SKILL / "scripts"))

from sw_connect import (  # noqa: E402
    create_empty_dispatch_variant, get_com_member, mm,
)
from sw_part import extrude_cut, insert_offset_plane, sketch, sketch_line  # noqa: E402
from sw_hole_features import (  # noqa: E402
    create_blind_hole, create_hole_pattern, create_through_hole,
)
from sw_session import SolidWorksSession  # noqa: E402
from sw_review import (  # noqa: E402
    collect_geometry_measurements, collect_model_summary,
    group_coaxial_hole_segments, run_review,
)
from PIL import Image  # noqa: E402

WORK = Path(__file__).resolve().parent
REVIEW_DIR = WORK / "previews"
PART_PATH = WORK / "car_wheel_v3.SLDPRT"
STEP_PATH = WORK / "car_wheel_v3.STEP"
PARAM_PATH = WORK / "car_wheel_v3_parameters.json"
DELIVERY_PATH = WORK / "car_wheel_v3_delivery.md"

# ---------------- 参数表（A 模式：assumed，按常规乘用车轮毂比例） ----------------
P = {
    "rim_flange_od_mm": 470.0,      # 轮辋法兰外径
    "rim_barrel_od_mm": 450.0,      # 轮辋筒身外径
    "rim_width_mm": 200.0,          # 轮辋总宽
    "flange_width_mm": 12.0,        # 两端法兰轴向宽度
    "rim_wall_mm": 10.0,            # 轮辋壁厚
    "front_lip_mm": 20.0,           # 两端轮辋唇口伸出轮辐正面的长度（前后对称）
    "web_thickness_mm": 20.0,       # 轮辐板厚
    "hub_od_mm": 160.0,             # 轮毂外径
    "hub_length_mm": 60.0,          # 轮毂轴向长度
    "bore_d_mm": 70.5,              # 中心孔
    "bolt_pcd_mm": 114.3,           # 5×114.3 螺栓节圆
    "bolt_d_mm": 14.0,              # 螺栓孔
    "bolt_n": 5,
    "spoke_n": 5,
    "window_inner_r_mm": 95.0,      # 辐窗内半径
    "window_outer_r_mm": 195.0,     # 辐窗外半径
    "window_half_angle_deg": 24.0,  # 单个辐窗半角（5 窗 → 辐条角宽 24°）
    "valve_d_mm": 11.5,             # 气门嘴孔
    "valve_z_mm": -80.0,            # 气门嘴孔轴向位置
}

# 派生量
R_FLANGE = P["rim_flange_od_mm"] / 2.0
R_BARREL = P["rim_barrel_od_mm"] / 2.0
R_RIM_IN = R_BARREL - P["rim_wall_mm"]
R_HUB = P["hub_od_mm"] / 2.0
R_BORE = P["bore_d_mm"] / 2.0
R_BOLT_PCD = P["bolt_pcd_mm"] / 2.0
R_BOLT = P["bolt_d_mm"] / 2.0
R_VALVE = P["valve_d_mm"] / 2.0

Z_BACK = P["front_lip_mm"] - P["rim_width_mm"]          # -180
Z_BACK_FLANGE_END = Z_BACK + P["flange_width_mm"]       # -168
Z_FRONT_FLANGE_START = P["front_lip_mm"] - P["flange_width_mm"]  # 8
Z_FRONT = P["front_lip_mm"]                             # 20
Z_WEB_BACK = -P["web_thickness_mm"]                     # -20
Z_HUB_BACK = -P["hub_length_mm"]                        # -60

# 后侧与前端关于 Z=-80 镜像对称
Z_BACK_FACE = Z_BACK + P["front_lip_mm"]                # -160（后轮辐正面）
Z_BACK_WEB_FACE = Z_BACK_FACE + P["web_thickness_mm"]   # -140（后轮辐背面）
Z_BACK_HUB_END = Z_BACK_FACE + P["hub_length_mm"]       # -100（后轮毂内端）

# 期望体积（解析法：前后两套轮毂/轮辐 + 轮辋 − 贯穿切除体积）
V_BASE = (
    2 * math.pi * R_HUB ** 2 * P["hub_length_mm"]
    + 2 * math.pi * (R_RIM_IN ** 2 - R_HUB ** 2) * P["web_thickness_mm"]
    + math.pi * (R_BARREL ** 2 - R_RIM_IN ** 2) * P["rim_width_mm"]
    + 2 * math.pi * (R_FLANGE ** 2 - R_BARREL ** 2) * P["flange_width_mm"]
)
V_WINDOW_EACH = (
    0.5 * (P["window_outer_r_mm"] ** 2 - P["window_inner_r_mm"] ** 2)
    * math.sin(math.radians(2 * P["window_half_angle_deg"]))
) * P["web_thickness_mm"]
# 中心孔与螺栓孔贯穿前后两个轮毂
V_BORE = 2 * math.pi * R_BORE ** 2 * P["hub_length_mm"]
V_BOLTS = 2 * P["bolt_n"] * math.pi * R_BOLT ** 2 * P["hub_length_mm"]
# 同一组贯穿窗同时切穿前后两块轮辐板
V_WINDOWS = 2 * P["spoke_n"] * V_WINDOW_EACH
V_VALVE = math.pi * R_VALVE ** 2 * P["rim_wall_mm"]
V_EXPECTED = V_BASE - V_BORE - V_BOLTS - V_WINDOWS - V_VALVE


def check(name, flag):
    if not flag:
        raise RuntimeError(f"{name} 失败")
    print(f"[OK] {name}")


def volume(part, label, expected, tolerance=0.001):
    m = collect_geometry_measurements(part)
    actual = m.get("volume_mm3")
    if actual is None:
        raise RuntimeError(f"{label}: 无法读取体积")
    error = abs(actual - expected) / expected
    print(f"[VOL] {label}: actual={actual:.3f} expected={expected:.3f} err={error*100:.4f}%")
    if error > tolerance:
        raise RuntimeError(f"{label}: 体积偏差 {error*100:.4f}% > {tolerance*100:.1f}%")
    return actual


def cut_spoke_window(part, index, center_deg):
    """在轮辐板上切一个梯形辐窗；五点均布，窗间材料形成 5 根辐条。"""
    r_in = P["window_inner_r_mm"]
    r_out = P["window_outer_r_mm"]
    half = P["window_half_angle_deg"]
    pts = []
    for radius, angle_deg in (
        (r_in, center_deg - half),
        (r_out, center_deg - half),
        (r_out, center_deg + half),
        (r_in, center_deg + half),
    ):
        angle = math.radians(angle_deg)
        pts.append((mm(radius * math.cos(angle)), mm(radius * math.sin(angle))))

    with sketch(part, "Front Plane", exact=True) as sk:
        for first, second in zip(pts, pts[1:] + pts[:1]):
            segment = sketch_line(part, first[0], first[1], second[0], second[1])
            if segment is None:
                raise RuntimeError(f"辐窗 {index} 草图线段创建失败")

    # 前后轮辐板分别在 Z=-20..0 与 -160..-140，均位于 Front Plane 的 -Z 侧；
    # 贯穿切除一次同时切穿两面，形成完全对称的辐窗
    feature = extrude_cut(
        part, sk, 0.0, direction=False, auto_flip=False,
        name=f"02_WINDOW_{index}",
    )
    if feature is None:
        raise RuntimeError(f"辐窗 {index} 切除失败：检查轮廓闭合与方向")
    print(f"[OK] 辐窗 {index} center={center_deg:.1f}°")


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    session = SolidWorksSession(visible=True, wait_seconds=20)
    # 关闭上一次同系列构建留下的文档，避免同名保存冲突
    active = session.sw.ActiveDoc
    if active is not None:
        try:
            active_title = str(get_com_member(active, "GetTitle"))
        except Exception:
            active_title = ""
        if active_title.startswith("car_wheel"):
            print("[CLOSE_EXISTING]", active_title)
            session.close(active)
    part = session.new_part()
    if part is None:
        raise RuntimeError("新建零件失败")

    try:
        # 1) 前后对称半剖轮廓 + 中心线 → 旋转 360°
        profile = [
            (0.0, 0.0),                     # 前轮毂轴心
            (0.0, R_RIM_IN),                # 前辐板/轮毂正面
            (Z_FRONT, R_RIM_IN),            # 前唇内壁
            (Z_FRONT, R_FLANGE),            # 前法兰端面
            (Z_FRONT_FLANGE_START, R_FLANGE),
            (Z_FRONT_FLANGE_START, R_BARREL),
            (Z_BACK_FLANGE_END, R_BARREL),
            (Z_BACK_FLANGE_END, R_FLANGE),
            (Z_BACK, R_FLANGE),
            (Z_BACK, R_RIM_IN),
            (Z_BACK_FACE, R_RIM_IN),        # 后唇内壁到后辐板正面
            (Z_BACK_FACE, 0.0),             # 后辐板/轮毂正面
            (Z_BACK_HUB_END, 0.0),          # 后轮毂内孔底面（轴线）
            (Z_BACK_HUB_END, R_HUB),        # 后轮毂内端面
            (Z_BACK_WEB_FACE, R_HUB),       # 后轮毂外圆
            (Z_BACK_WEB_FACE, R_RIM_IN),    # 后辐板背面
            (Z_WEB_BACK, R_RIM_IN),         # 空腔轮辋内壁到前辐板背面
            (Z_WEB_BACK, R_HUB),            # 前辐板背面
            (Z_HUB_BACK, R_HUB),            # 前轮毂外圆
            (Z_HUB_BACK, 0.0),              # 前轮毂背面（轴线）
        ]
        with sketch(part, "Right Plane", exact=True) as sk:
            # Right Plane: u=-Z, v=r；Z 轴为 v=0 这条水平线
            part.SketchManager.CreateCenterLine(mm(-40), 0, 0, mm(200), 0, 0)
            for (z1, r1), (z2, r2) in zip(profile, profile[1:] + profile[:1]):
                segment = sketch_line(part, mm(-z1), mm(r1), mm(-z2), mm(r2))
                if segment is None:
                    raise RuntimeError("旋转轮廓线段创建失败")

        from sw_part import revolve_boss  # 延迟导入，保持顶部导入清晰
        feature = revolve_boss(part, sk, math.radians(360))
        if feature is None:
            raise RuntimeError("旋转凸台失败：检查轮廓是否闭合、中心线是否为旋转轴")
        try:
            feature.Name = "01_REVOLVE_WHEEL"
        except Exception:
            pass
        print("[OK] 旋转主体")
        volume(part, "旋转主体", V_BASE)

        # 2) 5 个辐窗（窗中心位于两根辐条之间：90+36+k*72）
        for index in range(1, P["spoke_n"] + 1):
            cut_spoke_window(part, index, 90.0 + 36.0 + (index - 1) * 72.0)
        volume(part, "切辐窗后", V_BASE - V_WINDOWS)

        # 3) 中心孔（Front Plane → -Z 贯穿轮毂）
        create_through_hole(
            part, (0, 0), mm(P["bore_d_mm"]),
            plane_name="Front Plane", name="03_BORE_D70.5", direction=False,
        )
        print("[OK] 中心孔")
        volume(part, "切中心孔后", V_BASE - V_WINDOWS - V_BORE)

        # 4) 5 个螺栓孔，位于辐条中心线上（90+k*72）
        positions = []
        for index in range(P["bolt_n"]):
            angle = math.radians(90.0 + index * 360.0 / P["bolt_n"])
            positions.append((
                mm(R_BOLT_PCD * math.cos(angle)),
                mm(R_BOLT_PCD * math.sin(angle)),
            ))
        create_hole_pattern(
            part, positions, create_through_hole,
            diameter=mm(P["bolt_d_mm"]), plane_name="Front Plane",
            name="04_BOLT_HOLE_D14", direction=False,
        )
        print("[OK] 5×螺栓孔")
        volume(part, "切螺栓孔后", V_BASE - V_WINDOWS - V_BORE - V_BOLTS)

        # 5) 气门嘴孔：从轮辋筒身顶部径向钻入（Top Plane 偏置到 Y=+R_BARREL）
        insert_offset_plane(part, "Top Plane", mm(R_BARREL), "Plane_Valve")
        create_blind_hole(
            part,
            (0, mm(-P["valve_z_mm"])),  # Top Plane: u=X, v=-Z
            mm(P["valve_d_mm"]),
            mm(P["rim_wall_mm"] + 10.0),
            plane_name="Plane_Valve",
            name="05_VALVE_HOLE_D11.5",
            direction=False,
        )
        print("[OK] 气门嘴孔")
        actual_volume = volume(part, "全部切除后", V_EXPECTED)

        # 隐藏气门嘴孔用的临时偏置面，避免遮挡预览
        part.ClearSelection2(True)
        selected = part.Extension.SelectByID2(
            "Plane_Valve", "PLANE", 0, 0, 0, False, 0,
            create_empty_dispatch_variant(), 0,
        )
        print("[PLANE_SELECTED]", bool(selected))
        if selected:
            part.BlankRefGeom()
        part.ClearSelection2(True)
        part.GraphicsRedraw2()

        part.ForceRebuild3(False)
        measurements = collect_geometry_measurements(part)
        envelope = measurements["envelope_mm"]
        body_count = len(part.GetBodies2(0, False) or [])
        print("[ENV]", envelope)
        print("[BODY]", body_count)
        print("[HOLES]", measurements["hole_count"], measurements["holes"])
        print("[CYL]", len(measurements["cylindrical_faces"]))

        if body_count != 1:
            raise RuntimeError(f"实体数 {body_count} != 1")
        expected_env = {
            "length": P["rim_flange_od_mm"],
            "width": P["rim_flange_od_mm"],
            "height": P["rim_width_mm"],
        }
        for key, expected in expected_env.items():
            if abs(envelope[key] - expected) > 0.1:
                raise RuntimeError(f"包围盒 {key}={envelope[key]} != {expected}")

        summary = collect_model_summary(part)
        feature_names = {item["name"] for item in summary.get("features", [])}
        required = {
            "01_REVOLVE_WHEEL",
            "02_WINDOW_1", "02_WINDOW_2", "02_WINDOW_3", "02_WINDOW_4", "02_WINDOW_5",
            "03_BORE_D70.5",
            "04_BOLT_HOLE_D14_1", "04_BOLT_HOLE_D14_2", "04_BOLT_HOLE_D14_3",
            "04_BOLT_HOLE_D14_4", "04_BOLT_HOLE_D14_5",
            "05_VALVE_HOLE_D11.5",
        }
        missing = sorted(required - feature_names)
        if missing:
            raise RuntimeError(f"缺少特征: {missing}")
        print("[OK] 特征树检查")

        session.save(part, str(PART_PATH))
        check(f"保存 {PART_PATH.name}", PART_PATH.exists() and PART_PATH.stat().st_size > 0)
        session.export(part, str(STEP_PATH))
        check(f"导出 {STEP_PATH.name}", STEP_PATH.exists() and STEP_PATH.stat().st_size > 0)

        report, report_path = run_review(
            part, str(REVIEW_DIR), basename="car_wheel_v3",
            views=("isometric", "front", "back", "top", "right"),
            expected_outputs=[str(PART_PATH), str(STEP_PATH)],
        )
        evaluation = report["evaluation"]
        print("[REVIEW]", evaluation["status"], evaluation["score"], evaluation["issues"])
        print("[REVIEW_PATH]", report_path)

        # BMP → PNG，便于直接查看（含背面）
        for view in ("isometric", "front", "back", "top", "right"):
            bmp = REVIEW_DIR / f"car_wheel_v3_{view}.bmp"
            if bmp.exists():
                Image.open(bmp).save(REVIEW_DIR / f"car_wheel_v3_{view}.png")

        # 参数与假设清单
        # φ430 轮辋内壁与中心孔同轴，必须先按直径剔除轮辋面再按轴线分组
        real_hole_segments = [
            hole for hole in measurements["holes"]
            if float(hole["diameter_mm"]) < 400.0
        ]
        real_hole_groups = group_coaxial_hole_segments(real_hole_segments)
        real_hole_count = len(real_hole_groups)
        param_doc = {
            "version": "v3",
            "mode": "A_schematic",
            "input_type": "text_brief",
            "units": "mm",
            "coordinate": "X=width, Y=height, Z=wheel_axis; Front Plane=front wheel face",
            "parameters": {key: {"value": value, "source": "assumed"} for key, value in P.items()},
            "derived": {
                "rim_inner_radius_mm": R_RIM_IN,
                "hub_radius_mm": R_HUB,
                "bore_radius_mm": R_BORE,
                "bolt_pcd_radius_mm": R_BOLT_PCD,
                "rim_back_z_mm": Z_BACK,
                "web_back_z_mm": Z_WEB_BACK,
                "hub_back_z_mm": Z_HUB_BACK,
                "back_face_z_mm": Z_BACK_FACE,
                "back_web_face_z_mm": Z_BACK_WEB_FACE,
                "back_hub_end_z_mm": Z_BACK_HUB_END,
            },
            "expected_volume_mm3": round(V_EXPECTED, 3),
            "actual_volume_mm3": actual_volume,
            "envelope_mm": envelope,
            "body_count": body_count,
            "internal_cylindrical_faces": measurements["hole_count"],
            "real_hole_count": real_hole_count,
            "hole_group_evidence": [
                {
                    "position_mm": group["position_mm"],
                    "diameters_mm": group["diameters_mm"],
                    "segment_count": group["segment_count"],
                    "feature_kind": group["feature_kind"],
                }
                for group in real_hole_groups
            ],
            "assumptions": [
                "前后对称双面 5 辐单件轮毂，不含轮胎、轮辋装饰罩、螺母。",
                "轮辋法兰外径 470、筒身 450、总宽 200，按 17–18 英寸级视觉比例取值。",
                "前后轮辐板与轮毂关于 Z=-80 镜像对称，前后各 5 根辐条。",
                "中心孔 70.5、5×114.3 PCD、φ14 螺栓孔贯穿前后两个轮毂。",
                "辐窗为前后贯通的 5 个梯形窗，未做圆角与拔模。",
                "气门嘴孔为顶部径向 φ11.5 通孔，位于轮辋中部 z=-80，仅示意。",
                "材料未指定，模型为纯几何体，不包含材料属性。",
            ],
            "hole_evidence_notes": [
                "hole_count / internal_cylindrical_faces 统计的是 B-Rep 内部圆柱面，不是孔的数量。",
                "中心孔与螺栓孔贯穿前后两个轮毂，各形成前后两段圆柱面；辐窗为贯穿切割，不产生圆柱面孔。",
                "real_hole_count 按同轴孔组统计：中心孔 φ70.5 + 5×φ14 螺栓孔 + 气门嘴孔 φ11.5 = 7 个唯一孔。",
            ],
        }
        param_doc.update({
            "part_file": str(PART_PATH),
            "step_file": str(STEP_PATH),
            "review_report": str(report_path),
        })
        PARAM_PATH.write_text(json.dumps(param_doc, ensure_ascii=False, indent=2), encoding="utf-8")

        delivery = f"""# 汽车轮毂单件模型 v3 — 交付说明（前后双面）

- 模式：A 示意模式（尺寸按常规比例，来源均为 assumed）
- 输入：文字需求“建一个车轮模型”，反馈“轮子只有一面，另一边是空的”后修正
- 模型：`{PART_PATH.name}`
- 通用格式：`{STEP_PATH.name}`
- 预览：`review_v3/car_wheel_v3_isometric.png`、`review_v3/car_wheel_v3_front.png`、`review_v3/car_wheel_v3_back.png`
- 审查报告：`review_v3/car_wheel_v3_review_report.json`
- 参数表：`{PARAM_PATH.name}`

## 本版修正

v2 的轮辐板与轮毂只在前端（Z=-60..0），后端轮辋筒身内是空的。v3 在 Z=-160..-100
增加一套镜像对称的轮毂与轮辐板，前后两面均为 5 辐造型；辐窗、中心孔、螺栓孔
采用贯穿切除，一次同时切穿前后两面，因此两面完全对称。

## 验证结果

| 项目 | 结果 |
|---|---|
| 包围盒 (X×Y×Z) | {envelope['length']} × {envelope['width']} × {envelope['height']} mm |
| 实体数 | {body_count} |
| 体积 | {actual_volume:.3f} mm³（解析期望 {V_EXPECTED:.3f} mm³，偏差 {abs(actual_volume - V_EXPECTED) / V_EXPECTED * 100:.5f}%） |
| 唯一孔 | {real_hole_count} 个：中心孔 φ{P['bore_d_mm']} + {P['bolt_n']}×φ{P['bolt_d_mm']} 螺栓孔 + φ{P['valve_d_mm']} 气门嘴孔 |
| 内部圆柱面总数 | {measurements['hole_count']}（前后贯通孔分成两段，另含 φ{R_RIM_IN * 2:.0f} 轮辋内壁） |
| 审查状态 | {evaluation['status']} / {evaluation['score']} |
| 特征数 | {summary.get('feature_count')} |

## 主要参数（全部 assumed）

| 参数 | 值 |
|---|---|
| 轮辋法兰外径 / 筒身外径 / 总宽 | {P['rim_flange_od_mm']} / {P['rim_barrel_od_mm']} / {P['rim_width_mm']} mm |
| 轮辋壁厚 / 法兰宽 | {P['rim_wall_mm']} / {P['flange_width_mm']} mm |
| 前后轮辐板厚 / 每面辐条数 | {P['web_thickness_mm']} mm / {P['spoke_n']} |
| 前后轮毂外径 / 长度 | {P['hub_od_mm']} / {P['hub_length_mm']} mm（各一端） |
| 中心孔 / PCD / 螺栓孔 | φ{P['bore_d_mm']} / {P['bolt_pcd_mm']} / {P['bolt_n']}×φ{P['bolt_d_mm']}（贯穿两面） |
| 辐窗半径范围 / 半角 | {P['window_inner_r_mm']}–{P['window_outer_r_mm']} mm / {P['window_half_angle_deg']}°（前后贯通） |
| 气门嘴孔 | φ{P['valve_d_mm']}，径向，位于轮辋中部 z={P['valve_z_mm']} |

## 建模顺序

1. Right Plane 前后对称半剖轮廓 + 中心线 → 绕 Z 轴旋转 360°（轮辋 + 前后轮辐板 + 前后轮毂）
2. 5 个梯形辐窗贯穿切除，同时切穿前后两块轮辐板，窗间材料形成前后各 5 根辐条
3. 中心孔 φ{P['bore_d_mm']} 贯穿前后两个轮毂
4. {P['bolt_n']}×φ{P['bolt_d_mm']} 螺栓孔，PCD {P['bolt_pcd_mm']}，前后贯通，与辐条中心对齐
5. 顶部径向 φ{P['valve_d_mm']} 气门嘴孔
6. 隐藏临时偏置面 `Plane_Valve`

## 假设清单

""" + "\n".join(f"- {item}" for item in param_doc["assumptions"]) + "\n"
        DELIVERY_PATH.write_text(delivery, encoding="utf-8")

        print("[DONE]")
        print(PART_PATH)
        print(STEP_PATH)
        print(DELIVERY_PATH)
        print(REVIEW_DIR)
    except Exception:
        # 失败时尽量保留现场，便于诊断
        try:
            debug_path = WORK / "car_wheel_v3_failed.SLDPRT"
            session.save(part, str(debug_path))
            print(f"[DEBUG_SAVED] {debug_path}")
        except Exception as save_error:
            print(f"[DEBUG_SAVE_FAILED] {save_error}")
        raise


if __name__ == "__main__":
    main()
