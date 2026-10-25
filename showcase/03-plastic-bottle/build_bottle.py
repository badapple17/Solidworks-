# -*- coding: utf-8 -*-
"""
百岁山风格塑料矿泉水瓶（示意模式 A，单件，不含瓶盖）

建模思路（按 skill 路线 A / R15 决策链）：
- 剖面有回转中心线、主体绕轴 → 旋转首特征（expert-thinking.md R1/R12）
- 瓶是闭合薄壁回转体（套筒类）→ 外轮廓 + 内腔一次旋成，不用抽壳
  （stepped-shaft.md 轮廓判断：空心件轮廓留壁厚）
- 肩部两段相切圆弧：凸弧与直筒竖直相切、凹弧与颈部竖直相切、拐点外切 G1 连续
  （避免折线密采样在模型上留下几十道棱边；几何精确、体积可解析验证）
- 颈环/螺纹棱/标签槽全部并入主轮廓（R3 特征粒度对齐形状：整件一次旋成，特征数 1）
- 瓶口螺纹按示意简化成 3 道环形棱（不做真实螺旋牙）

预期：包围盒 66 × 235 × 66 mm，实体 1，体积 = 2π·x̄·A（Pappus）解析值。
"""

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


SKILL_SCRIPTS = _find_skill_dir() / "scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
sys.path.insert(0, str(Path(__file__).parent))

from sw_connect import mm
from sw_part import sketch, sketch_line, sketch_arc, revolve_boss
from sw_session import SolidWorksSession
from sw_review import collect_geometry_measurements, run_review

import bottle_geom as geo

OUT_DIR = Path(__file__).parent
PART_PATH = OUT_DIR / "bottle_baishuishan_style_v2.SLDPRT"

print(f"[design] 剖面实体: 直线+2×2 圆弧  绘制指令: {len(geo.ops)}  特征规划: 1×旋转")
print(f"[design] 期望材料体积: {geo.EXPECTED_VOLUME_ML:.3f} ml  满口容量: {geo.CAPACITY_ML:.1f} ml")
print(f"[design] 期望包围盒: 66 × 235 × 66 mm, 实体数 1")

if "--dry" in sys.argv:
    raise SystemExit(0)

OUT_DIR.mkdir(parents=True, exist_ok=True)
session = SolidWorksSession(visible=True, wait_seconds=20)
part = session.new_part()
try:
    # 几十段轮廓仍用 exact=True：默认推理会把相邻点吸附/打断，
    # 实测密集折线轮廓 contours=28、旋转返回 None（probe_dense.py）；
    # exact=True（AddToDB）绕过推理，轮廓数 1、旋转成功。
    with sketch(part, "Front Plane", exact=True) as sk:
        part.SketchManager.CreateCenterLine(0, mm(-10), 0, 0, mm(geo.H + 10), 0)
        last = None
        for op in geo.ops:
            if op[0] == "line":
                # 折线串的每个点是顶点，相邻顶点即线段；首点必须保留——
                # 它与上一段终点重合，正是本串第一段的起点（去重会丢第一段）
                pts = [(mm(x), mm(y)) for x, y in op[1]]
                for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                    sketch_line(part, x1, y1, x2, y2)
                last = pts[-1]
            else:
                _, center, start, end, ccw = op
                sketch_arc(part, mm(center[0]), mm(center[1]),
                           mm(start[0]), mm(start[1]),
                           mm(end[0]), mm(end[1]),
                           direction=1 if ccw else -1)
                last = (mm(end[0]), mm(end[1]))
        sketch_line(part, last[0], last[1], mm(geo.CLOSE_TO[0]), mm(geo.CLOSE_TO[1]))

    feature = revolve_boss(part, sk, 2.0 * math.pi)
    if feature is None:
        raise RuntimeError("旋转失败：检查剖面是否闭合、是否跨过中心线")

    part.ForceRebuild3(False)
    m = collect_geometry_measurements(part)
    print("[measure] envelope_mm:", m["envelope_mm"])
    print("[measure] volume_mm3:", m["volume_mm3"])
    print("[measure] bodies:", len(part.GetBodies2(0, False) or []))
    print("[measure] cylindrical_faces:", len(m.get("cylindrical_faces") or []))

    env = m["envelope_mm"]
    # envelope_mm 按模型 XYZ 命名：X=length、Y=width、Z=height；
    # 瓶子竖放（轴=Y）→ 高记在 width，两个直径分列 length/height
    expect = {"length": 66.0, "width": geo.H, "height": 66.0}
    for key, value in expect.items():
        actual = env[key]
        if abs(actual - value) > max(0.1, value * 0.002):
            raise RuntimeError(f"包围盒 {key} 不符: {actual} != {value}")
    if len(part.GetBodies2(0, False) or []) != 1:
        raise RuntimeError("实体数不为 1")
    actual_ml = m["volume_mm3"] / 1000.0
    err = abs(actual_ml - geo.EXPECTED_VOLUME_ML) / geo.EXPECTED_VOLUME_ML
    print(f"[gate] 体积 {actual_ml:.3f} ml vs 解析 {geo.EXPECTED_VOLUME_ML:.3f} ml, 误差 {err * 100:.3f}%")
    if err > 0.002:
        raise RuntimeError(f"体积与解析值偏差 {err * 100:.2f}% > 0.2%")

    # 关键回转直径证据：瓶身 Ø66、颈外 Ø26、颈内 Ø21.8、身内 Ø64.4、防盗环 Ø30.8
    diameters = sorted({round(f["diameter_mm"], 1) for f in (m.get("cylindrical_faces") or [])})
    print("[gate] 圆柱面直径:", diameters)
    for required in (66.0, 26.0, 21.8, 64.4, 30.8):
        if not any(abs(d - required) < 0.05 for d in diameters):
            raise RuntimeError(f"缺少关键圆柱面 Ø{required}")

    if PART_PATH.exists():
        PART_PATH.unlink()
    saved = session.save(part, str(PART_PATH))
    if not PART_PATH.is_file() or PART_PATH.stat().st_size == 0:
        raise RuntimeError(f"保存失败: {PART_PATH} (save={saved})")

    report, report_path = run_review(
        part, str(OUT_DIR / "previews"), basename="bottle_v2",
        expected_outputs=[str(PART_PATH)],
    )
    print("[review]", report["evaluation"])
    print("[review] report:", report_path)
finally:
    session.close(part)
