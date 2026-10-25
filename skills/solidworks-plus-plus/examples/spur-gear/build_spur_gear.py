"""Build and review a native SolidWorks involute spur gear through COM."""

from __future__ import annotations

import json
import math
import os
import sys
import traceback
from pathlib import Path
from typing import Any


# Edit this compact block to regenerate a different gear.
MM = 0.001
TEETH = 24
MODULE_MM = 2.5
PRESSURE_ANGLE_DEG = 20.0
FACE_WIDTH_MM = 12.0
HUB_DIAMETER_MM = 36.0
HUB_WIDTH_MM = 20.0
BORE_DIAMETER_MM = 20.0

MODULE = MODULE_MM * MM
PRESSURE_ANGLE = math.radians(PRESSURE_ANGLE_DEG)
PITCH_RADIUS = MODULE * TEETH / 2.0
BASE_RADIUS = PITCH_RADIUS * math.cos(PRESSURE_ANGLE)
OUTER_RADIUS = MODULE * (TEETH + 2) / 2.0
ROOT_RADIUS = MODULE * (TEETH - 2.5) / 2.0
WORK_DIR = Path.cwd().resolve()


class GearBuildError(RuntimeError):
    pass


def resolve_modeling_skill() -> Path:
    override = (
        os.environ.get("SOLIDWORKS_PLUS_PLUS_SKILL_DIR")
        or os.environ.get("SOLIDWORKS_MODELING_SKILL_DIR")
    )
    installed_skills = Path(__file__).resolve().parents[3]
    candidates = [
        Path(override).expanduser() if override else None,
        installed_skills / "solidworks-plus-plus",
        Path.home() / ".claude" / "skills" / "solidworks-plus-plus",
        Path.home() / ".codex" / "skills" / "solidworks-plus-plus",
        Path.home() / ".agents" / "skills" / "solidworks-plus-plus",
        # 旧名回退：升级前安装的目录仍可用
        installed_skills / "solidworks-modeling",
        Path.home() / ".claude" / "skills" / "solidworks-modeling",
        Path.home() / ".codex" / "skills" / "solidworks-modeling",
        Path.home() / ".agents" / "skills" / "solidworks-modeling",
    ]
    for candidate in candidates:
        if candidate and (candidate / "scripts" / "sw_session.py").is_file():
            return candidate.resolve()
    raise GearBuildError(
        "Could not locate solidworks-plus-plus. Set "
        "SOLIDWORKS_PLUS_PLUS_SKILL_DIR (or legacy "
        "SOLIDWORKS_MODELING_SKILL_DIR) to its installed directory."
    )


def validate_parameters() -> None:
    if TEETH < 6:
        raise GearBuildError("TEETH must be at least 6 for this sampled profile.")
    if MODULE_MM <= 0.0 or FACE_WIDTH_MM <= 0.0 or HUB_WIDTH_MM <= 0.0:
        raise GearBuildError("Module and widths must be positive.")
    if BORE_DIAMETER_MM <= 0.0 or HUB_DIAMETER_MM <= BORE_DIAMETER_MM:
        raise GearBuildError("Hub diameter must exceed bore diameter.")
    if ROOT_RADIUS <= 0.0 or BASE_RADIUS >= OUTER_RADIUS:
        raise GearBuildError("The selected tooth parameters produce invalid radii.")


def polar(radius: float, angle: float) -> tuple[float, float]:
    return radius * math.cos(angle), radius * math.sin(angle)


def involute_angle(radius: float) -> float:
    t = math.sqrt((radius / BASE_RADIUS) ** 2 - 1.0)
    return t - math.atan(t)


def gear_outline() -> list[tuple[float, float]]:
    """Return a closed sampled involute outline in meters."""
    tooth_pitch = 2.0 * math.pi / TEETH
    half_tooth_at_pitch = math.pi / (2.0 * TEETH)
    base_half_angle = half_tooth_at_pitch + involute_angle(PITCH_RADIUS)
    outer_t = math.sqrt((OUTER_RADIUS / BASE_RADIUS) ** 2 - 1.0)
    outer_half_angle = base_half_angle - involute_angle(OUTER_RADIUS)
    points: list[tuple[float, float]] = []

    for tooth in range(TEETH):
        center = tooth * tooth_pitch
        lower_base_angle = center - base_half_angle
        upper_base_angle = center + base_half_angle

        points.append(polar(ROOT_RADIUS, lower_base_angle))
        points.append(polar(BASE_RADIUS, lower_base_angle))

        for sample in range(1, 6):
            t = outer_t * sample / 5.0
            radius = BASE_RADIUS * math.sqrt(1.0 + t * t)
            inv = t - math.atan(t)
            points.append(polar(radius, center - base_half_angle + inv))

        points.append(polar(OUTER_RADIUS, center))
        points.append(polar(OUTER_RADIUS, center + outer_half_angle))

        for sample in range(4, -1, -1):
            t = outer_t * sample / 5.0
            radius = BASE_RADIUS * math.sqrt(1.0 + t * t)
            inv = t - math.atan(t)
            points.append(polar(radius, center + base_half_angle - inv))

        points.append(polar(ROOT_RADIUS, upper_base_angle))
        next_lower_angle = center + tooth_pitch - base_half_angle
        for sample in range(1, 4):
            angle = upper_base_angle + (
                next_lower_angle - upper_base_angle
            ) * sample / 4.0
            points.append(polar(ROOT_RADIUS, angle))

    return points


def draw_gear_profile(model: Any) -> None:
    points = gear_outline()
    sketch_manager = model.SketchManager
    sketch_manager.AddToDB = True
    try:
        for start, end in zip(points, points[1:] + points[:1]):
            segment = sketch_manager.CreateLine(
                start[0], start[1], 0.0, end[0], end[1], 0.0
            )
            if segment is None:
                raise GearBuildError("SolidWorks rejected a gear outline segment.")

        bore = sketch_manager.CreateCircleByRadius(
            0.0, 0.0, 0.0, BORE_DIAMETER_MM * MM / 2.0
        )
        if bore is None:
            raise GearBuildError("SolidWorks rejected the center bore circle.")
    finally:
        sketch_manager.AddToDB = False


def draw_hub_annulus(model: Any) -> None:
    sketch_manager = model.SketchManager
    outer = sketch_manager.CreateCircleByRadius(
        0.0, 0.0, 0.0, HUB_DIAMETER_MM * MM / 2.0
    )
    inner = sketch_manager.CreateCircleByRadius(
        0.0, 0.0, 0.0, BORE_DIAMETER_MM * MM / 2.0
    )
    if outer is None or inner is None:
        raise GearBuildError("SolidWorks rejected the hub annulus sketch.")


def require_feature(model: Any, feature: Any, name: str) -> Any:
    if feature is None:
        raise GearBuildError(f"Feature creation failed: {name}")
    feature.Name = name
    model.ForceRebuild3(False)
    if model.FeatureByName(name) is None:
        raise GearBuildError(f"Feature missing after rebuild: {name}")
    print(f"Created: {name}")
    return feature


def combined_body_box(model: Any) -> tuple[int, tuple[float, ...], tuple[Any, ...]]:
    bodies = tuple(model.GetBodies2(0, False) or ())
    if not bodies:
        raise GearBuildError("SolidWorks returned no solid bodies.")
    boxes = [tuple(float(value) for value in body.GetBodyBox()) for body in bodies]
    combined = (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        min(box[2] for box in boxes),
        max(box[3] for box in boxes),
        max(box[4] for box in boxes),
        max(box[5] for box in boxes),
    )
    return len(bodies), combined, bodies


def cylindrical_radii_mm(bodies: tuple[Any, ...]) -> list[float]:
    from sw_connect import get_com_member

    radii: list[float] = []
    for body in bodies:
        for face in tuple(get_com_member(body, "GetFaces") or ()):
            surface = get_com_member(face, "GetSurface")
            if not surface or not bool(get_com_member(surface, "IsCylinder")):
                continue
            params = tuple(
                float(value)
                for value in (get_com_member(surface, "CylinderParams") or ())
            )
            if len(params) >= 7:
                radii.append(abs(params[6]) / MM)
    return sorted(radii)


def validate_geometry(model: Any) -> dict[str, Any]:
    body_count, box, bodies = combined_body_box(model)
    size_mm = tuple((box[index + 3] - box[index]) / MM for index in range(3))
    planar_sizes = sorted(size_mm[:2], reverse=True)
    radii_mm = cylindrical_radii_mm(bodies)
    expected_outside_diameter_mm = 2.0 * OUTER_RADIUS / MM

    if body_count != 1:
        raise GearBuildError(f"Expected one solid body, got {body_count}.")
    if not all(
        abs(value - expected_outside_diameter_mm) <= 0.5 for value in planar_sizes
    ):
        raise GearBuildError(f"Outside diameter validation failed: {size_mm}")
    if abs(size_mm[2] - HUB_WIDTH_MM) > 0.5:
        raise GearBuildError(f"Hub width validation failed: {size_mm}")
    if not any(abs(radius - BORE_DIAMETER_MM / 2.0) <= 0.05 for radius in radii_mm):
        raise GearBuildError(f"Center bore radius was not found: {radii_mm}")

    return {
        "body_count": body_count,
        "size_mm": [round(value, 4) for value in size_mm],
        "cylindrical_radii_mm": [round(value, 4) for value in radii_mm],
    }


def next_output_path() -> Path:
    stem = f"spur_gear_Z{TEETH}_M{MODULE_MM:g}"
    for suffix in ("", *(f"_{index}" for index in range(2, 100))):
        candidate = WORK_DIR / f"{stem}{suffix}.SLDPRT"
        if not candidate.exists():
            return candidate
    raise GearBuildError("Could not choose a non-conflicting output filename.")


def main() -> int:
    validate_parameters()
    automation_skill = resolve_modeling_skill()
    sys.path.insert(0, str(automation_skill / "scripts"))

    # The case is deliberately non-installing. Missing packages fail clearly.
    from sw_preflight import run_preflight

    run_preflight(allow_install=False, check_solidworks=True)

    import pythoncom
    from sw_connect import get_com_member
    from sw_part import extrude_midplane, sketch
    from sw_review import run_review
    from sw_session import SolidWorksSession

    pythoncom.CoInitialize()
    session = None
    model = None
    success = False
    try:
        output_path = next_output_path()
        session = SolidWorksSession(visible=True)
        model = session.new_part()

        with sketch(model, "Front Plane") as sketch_name:
            draw_gear_profile(model)
        require_feature(
            model,
            extrude_midplane(model, sketch_name, FACE_WIDTH_MM * MM),
            f"01_GEAR_BODY_Z{TEETH}_M{MODULE_MM:g}_PA{PRESSURE_ANGLE_DEG:g}",
        )

        with sketch(model, "Front Plane") as sketch_name:
            draw_hub_annulus(model)
        require_feature(
            model,
            extrude_midplane(model, sketch_name, HUB_WIDTH_MM * MM),
            f"02_HUB_D{HUB_DIAMETER_MM:g}_BORE_D{BORE_DIAMETER_MM:g}",
        )

        model.ForceRebuild3(False)
        validation = validate_geometry(model)
        model.ShowNamedView2("*Isometric", 7)
        get_com_member(model, "ViewZoomtofit2")
        get_com_member(model, "GraphicsRedraw2")

        if not session.save(model, str(output_path)) or not output_path.exists():
            raise GearBuildError(f"Native save failed: {output_path}")

        evidence_path = output_path.with_name(f"{output_path.stem}_evidence.json")
        evidence = {
            "cad_spec": {
                "type": "external_spur_gear",
                "teeth": TEETH,
                "module_mm": MODULE_MM,
                "pressure_angle_deg": PRESSURE_ANGLE_DEG,
                "pitch_diameter_mm": 2.0 * PITCH_RADIUS / MM,
                "outside_diameter_mm": 2.0 * OUTER_RADIUS / MM,
                "root_diameter_mm": 2.0 * ROOT_RADIUS / MM,
                "face_width_mm": FACE_WIDTH_MM,
                "hub_diameter_mm": HUB_DIAMETER_MM,
                "hub_width_mm": HUB_WIDTH_MM,
                "bore_diameter_mm": BORE_DIAMETER_MM,
            },
            "measurement_source": "SolidWorks API/B-Rep",
            "units": "mm",
            "validation": validation,
        }
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=True, indent=2), encoding="utf-8"
        )

        review_dir = WORK_DIR / f"{output_path.stem}_review"
        report, report_path = run_review(
            model,
            review_dir,
            basename=output_path.stem,
            views=("isometric", "front", "top", "right"),
            expected_outputs=[str(output_path)],
        )
        if report["evaluation"]["status"] == "fail":
            raise GearBuildError(f"Review failed: {report['evaluation']['issues']}")

        print("SUCCESS")
        print(f"Saved: {output_path}")
        print(f"Evidence: {evidence_path}")
        print(f"Review: {report_path}")
        print(f"Review status: {report['evaluation']['status']}")
        print(f"Validation: {validation}")
        success = True
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        traceback.print_exc()
        return 1
    finally:
        if not success and session is not None and model is not None:
            try:
                session.close(model=model)
            except Exception:
                pass
        model = None
        session = None
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
