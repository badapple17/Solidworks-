"""
真实 SolidWorks 装配配合回归测试：同心对齐方式 + 角度摆姿态 + 静态干涉。

测试件：40×40×10 方块（中心 Ø6.1 通孔）+ Ø6×20 销。销已按设计位姿放进孔里。
通过标准：
1. 同心配合 align=CLOSEST(2) 后，销相对方块的位姿不变（旋转对角 (1,1,1)、平移不变）。
   ALIGNED(0)/ANTI(1) 的结果只记录不判定——会不会翻 180° 取决于两个圆柱面的轴向，
   这正是不该用它们的原因。
2. 临时角度配合能把销转到 30°，删除该配合后位姿保留、配合数回到 1。
3. 干涉检查：销在孔里 0 处；再放一个插进实体的销，必须报出 1 处、体积 ≈ π·3²·10。
4. 关闭装配体后，被引用的零件文档是否还留在会话里——记录下来（会让下次 SaveAs 报错码 1）。
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sw_assembly import (  # noqa: E402
    SW_MATE_ANGLE, SW_MATE_CONCENTRIC, SW_MATE_ALIGN_CLOSEST,
    add_component, add_mate5_checked, collect_mate_feature_summary, delete_mates,
    find_largest_cylinder_face, find_planar_face, get_component_pose,
    get_interference_detection, select_entities_for_mate,
)
from sw_connect import connect_solidworks, get_com_member, mm, new_document, save_document  # noqa: E402
from sw_part import extrude_boss, extrude_cut, sketch, sketch_circle, sketch_rectangle  # noqa: E402


def _open_titles(sw):
    docs = get_com_member(sw, "GetDocuments") or []
    return [get_com_member(d, "GetTitle") for d in docs]


def _make_part(sw, path: Path, builder):
    try:
        sw.CloseDoc(path.name)
    except Exception:
        pass
    model = new_document(sw, "part")
    builder(model)
    model.ForceRebuild3(False)
    if not save_document(model, str(path)):
        raise RuntimeError(f"测试零件保存失败: {path}")
    sw.CloseDoc(get_com_member(model, "GetTitle"))


def _block(model):
    with sketch(model, "Front Plane", exact=True) as sk:
        sketch_rectangle(model, 0, 0, mm(40), mm(40))
    if extrude_boss(model, sk, mm(10), direction=False) is None:   # Front 凸台 False = +Z
        raise RuntimeError("方块拉伸失败")
    with sketch(model, "Front Plane", exact=True) as sk:
        sketch_circle(model, 0, 0, mm(3.05))
    if extrude_cut(model, sk, 0.0, direction=True) is None:
        raise RuntimeError("通孔失败")


def _pin(model):
    with sketch(model, "Front Plane", exact=True) as sk:
        sketch_circle(model, 0, 0, mm(3.0))
    if extrude_boss(model, sk, mm(20), direction=False) is None:
        raise RuntimeError("销拉伸失败")


def _relative(pin, block):
    """销相对方块：(平移 mm, 旋转对角)。方块未固定时求解器可能移动任一方，所以比较相对量。"""
    (pp, pr), (bp, br) = get_component_pose(pin), get_component_pose(block)
    # R_rel = R_b^T · R_p（Transform2 前 9 项按行存）
    rel = [[sum(br[k][i] * pr[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    d = [pp[i] - bp[i] for i in range(3)]
    t = [sum(br[k][i] * d[k] for k in range(3)) * 1000 for i in range(3)]
    return [round(v, 3) for v in t], [round(rel[i][i], 3) for i in range(3)]


def _place(sw, asm, block_path, pin_path):
    # AddComponent5 的 x/y/z 是组件包围盒中心：方块中心 z=5，销中心 z=10
    block = add_component(asm, str(block_path), 0.0, 0.0, 0.005, sw=sw)
    pin = add_component(asm, str(pin_path), 0.0, 0.0, 0.007, sw=sw)   # 销底 z=-3，穿出方块两端
    return block, pin


def run_regression(output_dir: Path, visible=True, wait_seconds=12, run_id=None) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    block_path = output_dir / f"align_probe_block_{run_id}.SLDPRT"
    pin_path = output_dir / f"align_probe_pin_{run_id}.SLDPRT"
    result = {"output_dir": str(output_dir), "run_id": run_id, "align": {}}

    sw, _ = connect_solidworks(wait_seconds=wait_seconds, visible=visible)
    result["revision"] = get_com_member(sw, "RevisionNumber")
    _make_part(sw, block_path, _block)
    _make_part(sw, pin_path, _pin)

    for align in (0, 1, 2):
        asm = new_document(sw, "assembly")
        block, pin = _place(sw, asm, block_path, pin_path)
        before = _relative(pin, block)
        entry = {"before": before}
        try:
            select_entities_for_mate(asm, find_largest_cylinder_face(pin, 0.0029, 0.0031),
                                     find_largest_cylinder_face(block, 0.0030, 0.0031))
            add_mate5_checked(asm, SW_MATE_CONCENTRIC, align=align, name=f"C_{align}")
            entry["after"] = _relative(pin, block)
            entry["kept_pose"] = entry["after"] == before
        except Exception as exc:
            entry["error"] = str(exc)
        result["align"][align] = entry

        if align == SW_MATE_ALIGN_CLOSEST:
            if not entry.get("kept_pose"):
                raise RuntimeError(f"CLOSEST 同心没有保持位姿: {entry}")
            # 角度摆姿态：圆柱销没有平面可作参照，再挂一个方块实例（z 20..30）同心套在销上，
            # 用两个方块的 +X 侧面做角度配合——验证「临时角度配合 → 删除后位姿保留」。
            block2 = add_component(asm, str(block_path), 0.0, 0.0, 0.025, sw=sw)
            select_entities_for_mate(asm, find_largest_cylinder_face(pin, 0.0029, 0.0031),
                                     find_largest_cylinder_face(block2, 0.0030, 0.0031))
            add_mate5_checked(asm, SW_MATE_CONCENTRIC, align=SW_MATE_ALIGN_CLOSEST, name="C_B2")
            select_entities_for_mate(asm, find_planar_face(block2, "x", 0.02, sign=1),
                                     find_planar_face(block, "x", 0.02, sign=1))
            temp = add_mate5_checked(asm, SW_MATE_ANGLE, angle=math.radians(30.0), name="T_ANGLE")
            _, diag_posed = _relative(block2, block)
            removed = delete_mates(asm, [temp])
            asm.ForceRebuild3(False)
            _, diag_after = _relative(block2, block)
            mates = [m["name"] for m in collect_mate_feature_summary(asm) if m["depth"] > 0]
            result["angle"] = {"posed_diag": diag_posed, "after_delete_diag": diag_after,
                               "removed": removed, "mates_left": mates}
            if abs(sorted(diag_posed)[0] - math.cos(math.radians(30.0))) > 0.01:
                raise RuntimeError(f"角度配合没有转到 30°: {diag_posed}")
            if diag_after != diag_posed or "T_ANGLE" in mates:
                raise RuntimeError(f"删除临时角度配合后位姿没保留: {result['angle']}")

            inter_ok = get_interference_detection(asm)
            # 第二个销插进实体（偏离孔 12 mm），预期 1 处干涉，体积 = π·3²·10 = 282.74 mm³
            add_component(asm, str(pin_path), 0.012, 0.0, 0.007, sw=sw)
            inter_bad = get_interference_detection(asm)
            result["interference"] = {"pin_in_hole": inter_ok, "pin_in_solid": inter_bad}
            if inter_ok["interference_count"] != 0:
                raise RuntimeError(f"销在孔里却报干涉: {inter_ok}")
            vols = [it.get("volume_mm3", 0) for it in inter_bad["items"]]
            if inter_bad["interference_count"] != 1 or abs(vols[0] - math.pi * 90) > 1.0:
                raise RuntimeError(f"插进实体的销没被正确检出: {inter_bad}")

        title = get_com_member(asm, "GetTitle")
        sw.CloseDoc(title)
        result.setdefault("open_after_close", {})[align] = _open_titles(sw)

    # 只关本测试创建的零件（关装配体不会卸载它们）；不碰用户会话里的其他文档
    for path in (block_path, pin_path):
        sw.CloseDoc(path.name)
    result["open_after_cleanup"] = [t for t in _open_titles(sw) if "align_probe_" in str(t)]
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SolidWorks 装配对齐/角度/干涉回归测试。")
    parser.add_argument("--output-dir",
                        default=str(Path(tempfile.gettempdir()) / "solidworks_assembly_align_regression"))
    parser.add_argument("--hidden", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=12)
    parser.add_argument("--run-id", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    try:
        result = run_regression(output_dir, visible=not args.hidden,
                                wait_seconds=args.wait_seconds, run_id=args.run_id or None)
        result["status"] = "ok"
    except Exception as exc:
        result = {"status": "failed", "output_dir": str(output_dir), "error": str(exc),
                  "traceback": traceback.format_exc()}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "assembly_align_regression_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
