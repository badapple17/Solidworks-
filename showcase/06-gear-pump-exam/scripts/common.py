"""Shared paths + helpers for the 立式42型齿轮油泵 build.

路径全部由 case_paths.py 推导，不含本机绝对路径；换机器只需保证
inputs/ 与 deliverables/ 跟着实例目录走。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_paths
from case_paths import CASE, EVIDENCE, PARTS, PREVIEWS, SKILL, STD, WORK

ROOT = CASE
OUT = case_paths.OUT
ASM = case_paths.ASM


def status_path():
    return WORK / "build_status.json"


def record(key, value):
    p = status_path()
    data = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data[key] = value
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def bbox_mm(model):
    """Bounding box of the solid bodies.

    GetPartBox also counts unconsumed sketches, so a failed extrusion can still
    report a plausible box; the body boxes are the real geometry.
    """
    from sw_connect import get_com_member

    doc_type = get_com_member(model, "GetType")
    if doc_type == 2:
        box = model.GetBox(0)
        return [round(float(v) * 1000.0, 3) for v in box]
    bodies = model.GetBodies2(0, False) or []
    boxes = []
    for b in bodies:
        try:
            boxes.append([float(v) for v in b.GetBodyBox()])
        except Exception:
            pass
    if not boxes:
        return [round(float(v) * 1000.0, 3) for v in model.GetPartBox(True)]
    lo = [min(b[i] for b in boxes) for i in range(3)]
    hi = [max(b[i + 3] for b in boxes) for i in range(3)]
    return [round(v * 1000.0, 3) for v in lo + hi]


def size_mm(model):
    b = bbox_mm(model)
    return [round(b[i + 3] - b[i], 3) for i in range(3)]


def body_count(model):
    bodies = model.GetBodies2(0, False) or []
    return len(bodies)


def volume_mm3(model):
    try:
        mp = model.Extension.CreateMassProperty()
        return round(float(mp.Mass) / 1000.0, 1) if mp else None
    except Exception:
        return None


def mass_props(model):
    """Return (volume_mm3, mass_g) using density-independent volume."""
    from sw_review import collect_geometry_measurements

    m = collect_geometry_measurements(model)
    return m.get("volume_mm3"), m.get("mass_g")


def summary(model):
    return {
        "size_mm": size_mm(model),
        "bbox_mm": bbox_mm(model),
        "bodies": body_count(model),
        "volume_mm3": mass_props(model)[0],
    }
