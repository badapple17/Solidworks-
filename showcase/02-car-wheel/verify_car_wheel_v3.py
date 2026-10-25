# -*- coding: utf-8 -*-
"""重新打开 v3，校验包围盒、体积、实体数、前后双面与孔位。"""
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

from sw_connect import get_com_member  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402
from sw_review import (  # noqa: E402
    collect_geometry_measurements, group_coaxial_hole_segments,
    validate_hole_positions,
)

WORK = Path(__file__).resolve().parent
PART = WORK / "car_wheel_v3.SLDPRT"
PARAM = WORK / "car_wheel_v3_parameters.json"
VERIFY_JSON = WORK / "previews" / "car_wheel_v3_verify.json"
EXPECTED_VOLUME = 7811777.086
EXPECTED_ENVELOPE = {"length": 470.0, "width": 470.0, "height": 200.0}


def planar_faces_at_z(part, z_mm, outward_sign):
    """返回外法向沿 Z、平面点 Z=z_mm 的平面面积（mm²）列表。"""
    areas = []
    for body in get_com_member(part, "GetBodies2", 0, False) or []:
        for face in get_com_member(body, "GetFaces") or []:
            surface = get_com_member(face, "GetSurface")
            if not surface or not get_com_member(surface, "IsPlane"):
                continue
            params = list(get_com_member(surface, "PlaneParams") or [])
            if len(params) < 6:
                continue
            normal = get_com_member(face, "Normal") or params[:3]
            if abs(abs(float(normal[2])) - 1.0) > 1e-4:
                continue
            sign = 1 if float(normal[2]) > 0 else -1
            if sign != outward_sign:
                continue
            if abs(float(params[5]) * 1000.0 - z_mm) > 0.01:
                continue
            area_mm2 = float(get_com_member(face, "GetArea") or 0.0) * 1_000_000.0
            areas.append(round(area_mm2, 3))
    return sorted(areas, reverse=True)


session = SolidWorksSession(visible=True, wait_seconds=20)
active = session.sw.ActiveDoc
if active is not None:
    title = str(get_com_member(active, "GetTitle"))
    print("[CLOSE_ACTIVE]", title)
    session.close(active)

part = session.open(str(PART), silent=False, raise_on_error=True)
if part is None:
    raise RuntimeError("v3 重新打开失败")

m = collect_geometry_measurements(part)
print("[REOPEN_OK]", get_com_member(part, "GetTitle"))
print("[ENVELOPE]", m["envelope_mm"])
print("[VOLUME]", m["volume_mm3"])
print("[BODY_COUNT]", len(part.GetBodies2(0, False) or []))
print("[INTERNAL_CYL_FACES]", m["hole_count"])

for key, expected in EXPECTED_ENVELOPE.items():
    actual = m["envelope_mm"][key]
    if abs(actual - expected) > 0.1:
        raise RuntimeError(f"envelope {key}: {actual} != {expected}")
volume_error = abs(m["volume_mm3"] - EXPECTED_VOLUME) / EXPECTED_VOLUME
print(f"[VOLUME_ERROR] {volume_error * 100:.5f}%")
if volume_error > 0.001:
    raise RuntimeError("体积偏差超过 0.1%")

# 前后两面：z=0 外法向 +Z；z=-160 外法向 -Z；大面积平面证明两面都存在
front_faces = planar_faces_at_z(part, 0.0, +1)
back_faces = planar_faces_at_z(part, -160.0, -1)
print("[FRONT_FACE_AREAS_MM2]", front_faces[:5])
print("[BACK_FACE_AREAS_MM2]", back_faces[:5])
if not front_faces or front_faces[0] < 50_000.0:
    raise RuntimeError("未找到前辐板正面（z=0，面积>50000 mm²）")
if not back_faces or back_faces[0] < 50_000.0:
    raise RuntimeError("未找到后辐板正面（z=-160，面积>50000 mm²）")

expected_holes = [{
    "id": "center_bore_D70.5",
    "position_mm": [0.0, 0.0, -30.0],
    "diameter_mm": 70.5,
}]
for i in range(5):
    angle = math.radians(90.0 + i * 72.0)
    expected_holes.append({
        "id": f"bolt_hole_{i + 1}_D14",
        "position_mm": [57.15 * math.cos(angle), 57.15 * math.sin(angle), -30.0],
        "diameter_mm": 14.0,
    })
expected_holes.append({
    "id": "valve_hole_D11.5",
    "position_mm": [0.0, 220.0, -80.0],
    "diameter_mm": 11.5,
})

result = validate_hole_positions(m, expected_holes)
print("[HOLE_VALIDATION]", result["status"])
for check in result["checks"]:
    print(" ", check["id"], check["passed"],
          "d_err=", check["diameter_error_mm"], "pos_err=", check["position_error_mm"])
if result["status"] != "pass":
    raise RuntimeError("孔位校验失败")

real_segments = [
    hole for hole in m["holes"] if float(hole["diameter_mm"]) < 400.0
]
real_groups = group_coaxial_hole_segments(real_segments)
print("[REAL_HOLE_GROUPS]", len(real_groups))
for group in real_groups:
    print(" ", group["diameters_mm"], "segments=", group["segment_count"],
          "pos=", group["position_mm"])
if len(real_groups) != 7:
    raise RuntimeError(f"唯一孔组数 {len(real_groups)} != 7")
for group in real_groups:
    if group["diameters_mm"] == [70.5] and group["segment_count"] != 2:
        raise RuntimeError("中心孔未贯穿前后两个轮毂")
    if group["diameters_mm"] == [14.0] and group["segment_count"] != 2:
        raise RuntimeError("螺栓孔未贯穿前后两个轮毂")

max_diameter_error = max(check["diameter_error_mm"] or 0.0 for check in result["checks"])
max_position_error = max(check["position_error_mm"] or 0.0 for check in result["checks"])

evidence = {
    "reopen_verified": True,
    "reopen_envelope_mm": m["envelope_mm"],
    "reopen_volume_mm3": m["volume_mm3"],
    "reopen_body_count": len(part.GetBodies2(0, False) or []),
    "version": "v3",
    "hole_validation_status": result["status"],
    "hole_validation_errors_mm": {
        "diameter": max_diameter_error,
        "position": max_position_error,
    },
    "real_hole_group_count": len(real_groups),
    "real_hole_groups": [
        {
            "diameters_mm": group["diameters_mm"],
            "segment_count": group["segment_count"],
            "position_mm": group["position_mm"],
        }
        for group in real_groups
    ],
    "planar_face_evidence": {
        "front_z0_areas_mm2": front_faces,
        "back_z160_areas_mm2": back_faces,
        "criterion": "z=0 外法向 +Z 与 z=-160 外法向 -Z 各存在面积 > 50000 mm² 的平面",
    },
}
VERIFY_JSON.parent.mkdir(parents=True, exist_ok=True)
VERIFY_JSON.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

if PARAM.exists():
    doc = json.loads(PARAM.read_text(encoding="utf-8"))
    doc.update({
        "reopen_verified": True,
        "reopen_envelope_mm": {
            "length": m["envelope_mm"]["length"],
            "width": m["envelope_mm"]["width"],
            "height": m["envelope_mm"]["height"],
        },
        "reopen_volume_mm3": m["volume_mm3"],
        "reopen_body_count": evidence["reopen_body_count"],
        "hole_validation_status": result["status"],
        "hole_validation_errors_mm": evidence["hole_validation_errors_mm"],
        "real_hole_group_count": len(real_groups),
        "planar_face_evidence": evidence["planar_face_evidence"],
    })
    PARAM.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[PARAM_UPDATED]", PARAM)

print("[VERIFY_JSON]", VERIFY_JSON)
print("[VERIFY_DONE] pass")
