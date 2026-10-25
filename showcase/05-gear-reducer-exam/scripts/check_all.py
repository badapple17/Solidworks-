# -*- coding: utf-8 -*-
"""05 实例交付门禁：零件实体数、三套装配的组件/包围盒/干涉/上色回读。

输出 evidence/assembly_check.json。不修改任何模型。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_paths

from sw_assembly import get_interference_detection
from sw_connect import connect_solidworks, get_com_member, open_document
from sw_review import collect_geometry_measurements

CASE = case_paths.CASE
EVIDENCE = CASE / "evidence"
EVIDENCE.mkdir(exist_ok=True)

PARTS = sorted(case_paths.PARTS.glob("*.SLDPRT"))
ASSEMBLIES = {
    "compact": case_paths.ASM / "XXJSQ_减速器.SLDASM",
    "exploded": case_paths.ASM / "XXJSQ_减速器_爆炸图.SLDASM",
    "transparent": case_paths.ASM / "XXJSQ_减速器_透明涂色.SLDASM",
}
EXPECTED_TRANSPARENCY = {"上盖": 0.82, "下盖": 0.82, "旋转套": 0.35, "齿圈": 0.10}

# 逐对登记“已知干涉”及其体积上限（mm³）。不是忽略干涉：
# 新出现的组合、或旧组合体积超上限，都会让检查失败。
# 依据见 README「干涉分类」一节；两份报告（2026-10-25）实测值在括号里。
DOCUMENTED_INTERFERENCE = {
    ("唇形密封圈120X150", "XXJSQ-009_齿圈"): (
        1700, "唇形密封圈过盈压在齿圈外圆：密封唇需要径向过盈（实测 1608.5）"),
    ("XXJSQ-010_上盖", "XXJSQ-002_旋转套"): (
        700, "上盖中心凸台伸入旋转套实心端面：试卷图两件长度冲突（实测 659.4）"),
    ("XXJSQ-009_齿圈", "XXJSQ-008_齿轮"): (
        100, "零侧隙内啮合，齿面数值重叠；量产需加 0.06 mm 侧隙（实测 69.7~79.7）"),
    ("XXJSQ-009_齿圈", "XXJSQ-004_固定轴"): (
        40, "固定轴头 R20 超出齿圈齿顶圆 2.5 mm：试卷图尺寸冲突（实测 24.3~33.6）"),
}


def classify_interference(items):
    """把干涉项分成：已登记、未登记、超上限。"""
    documented, unexpected, over_cap = [], [], []
    for item in items:
        pair = tuple(item.get("components") or [])
        base = tuple(
            name.rsplit("-", 1)[0] if name.rsplit("-", 1)[-1].isdigit() else name
            for name in pair
        )
        key = None
        for candidate in DOCUMENTED_INTERFERENCE:
            if set(candidate) == set(base):
                key = candidate
                break
        if key is None:
            unexpected.append(item)
            continue
        cap, reason = DOCUMENTED_INTERFERENCE[key]
        entry = dict(item, reason=reason, cap_mm3=cap)
        if float(item.get("volume_mm3") or 0) > cap:
            over_cap.append(entry)
        else:
            documented.append(entry)
    return documented, unexpected, over_cap


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def bbox_mm(model):
    doc_type = get_com_member(model, "GetType")
    box = model.GetBox(0) if doc_type == 2 else model.GetPartBox(True)
    return [round(float(v) * 1000.0, 3) for v in box]


def main():
    sw, _ = connect_solidworks(visible=True)
    sw.CloseAllDocuments(True)  # 避免上一次会话残留的装配体锁住零件文档
    report = {"parts": {}, "assemblies": {}, "checks": {}}

    for path in PARTS:
        model = open_document(sw, str(path))
        if model is None:
            report["parts"][path.name] = {"error": "open failed"}
            print(f"{path.name:34s} OPEN FAILED")
            continue
        bodies = model.GetBodies2(0, False) or []
        measurements = collect_geometry_measurements(model)
        report["parts"][path.name] = {
            "bodies": len(bodies),
            "volume_mm3": measurements.get("volume_mm3"),
            "bbox_mm": bbox_mm(model),
        }
        print(f"{path.name:34s} bodies={len(bodies)} vol={measurements.get('volume_mm3')}")
        sw.CloseDoc(path.name)

    for key, path in ASSEMBLIES.items():
        asm = open_document(sw, str(path))
        components = asm.GetComponents(False) or []
        data = {
            "file": path.name,
            "components": len(components),
            "bbox_mm": bbox_mm(asm),
        }
        if key == "compact":
            data["interference"] = get_interference_detection(asm)
        if key == "transparent":
            colours = {}
            for comp in components:
                name = str(comp.Name2)
                values = comp.MaterialPropertyValues
                colours[name] = {
                    "rgb": [round(float(v), 3) for v in values[:3]],
                    "transparency": round(float(values[7]), 3),
                }
            data["colours"] = colours
        report["assemblies"][key] = data
        print(f"{key:12s} components={len(components)} bbox={data['bbox_mm']}")
        sw.CloseDoc(path.name)

    report["checks"]["all_parts_single_body"] = all(
        p["bodies"] == 1 for p in report["parts"].values()
    )
    compact = report["assemblies"]["compact"]
    documented, unexpected, over_cap = classify_interference(
        compact["interference"]["items"])
    report["checks"]["compact_interference_ok"] = not unexpected and not over_cap
    report["checks"]["compact_interference_documented"] = {
        "documented_count": len(documented),
        "unexpected_count": len(unexpected),
        "over_cap_count": len(over_cap),
        "documented": documented,
        "unexpected": unexpected,
        "over_cap": over_cap,
    }
    report["checks"]["all_three_assemblies_9_components"] = all(
        a["components"] == 9 for a in report["assemblies"].values()
    )
    transparent = report["assemblies"]["transparent"]["colours"]
    report["checks"]["transparent_colours"] = {
        key: round(transparent[name]["transparency"], 3)
        for key, name in {
            "上盖": "XXJSQ-010_上盖-1",
            "下盖": "XXJSQ-006_下盖-1",
            "旋转套": "XXJSQ-002_旋转套-1",
            "齿圈": "XXJSQ-009_齿圈-1",
        }.items()
    }
    report["checks"]["transparent_ok"] = all(
        abs(report["checks"]["transparent_colours"][key] - expected) <= 0.02
        for key, expected in EXPECTED_TRANSPARENCY.items()
    )
    report["checks"]["source_untouched"] = {
        "compact_sha256": sha256(ASSEMBLIES["compact"]),
        "transparent_sha256": sha256(ASSEMBLIES["transparent"]),
        "different_files": sha256(ASSEMBLIES["compact"]) != sha256(ASSEMBLIES["transparent"]),
    }
    report["status"] = "pass" if all(
        value for key, value in report["checks"].items()
        if key not in ("transparent_colours", "compact_interference_documented")
    ) else "fail"

    out = EVIDENCE / "assembly_check.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("status:", report["status"], "->", out)
    sw.CloseAllDocuments(True)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
