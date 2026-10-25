"""Build a reference bearing housing as a native SolidWorks part.

The dimensions are intentionally grouped below so the model can be regenerated
with different proportions. SolidWorks API length values are in meters.
"""

from __future__ import annotations

import math
import os
import traceback
from pathlib import Path
from typing import Any, Callable

import pythoncom
import win32com.client


SW_END_BLIND = 0
SW_END_MIDPLANE = 6
SW_SAVE_CURRENT = 0
SW_SAVE_SILENT = 1
SW_BODY_SOLID = 0
SW_VIEW_ISOMETRIC = 7
SW_DEFAULT_TEMPLATE_PART = 8

# Reference dimensions from the two supplied images.
BASE_LENGTH = 0.174
BASE_WIDTH = 0.090
BASE_THICKNESS = 0.015
BASE_CORNER_R = 0.015
MOUNT_HOLE_DIA = 0.016
MOUNT_HALF_X = 0.072
MOUNT_HALF_Z = 0.030

SHAFT_AXIS_Y = 0.0345
BODY_OUTER_R = 0.040
BODY_DEPTH = 0.060
SHAFT_BORE_DIA = 0.028
COLLAR_DIA = 0.060
COLLAR_DEPTH = 0.080
RIB_DEPTH = 0.016

TOP_BOSS_DIA = 0.054
TOP_BORE_DIA = 0.034
MODEL_TOP_Y = 0.0845


class BuildError(RuntimeError):
    pass


def connect_solidworks() -> Any:
    try:
        app = win32com.client.GetActiveObject("SldWorks.Application")
        print("Connected to the running SolidWorks instance.")
    except Exception:
        app = win32com.client.Dispatch("SldWorks.Application")
        print("Started a SolidWorks instance.")
    app.Visible = True
    return app


def resolve_part_template(app: Any) -> str:
    template = ""
    try:
        template = app.GetUserPreferenceStringValue(SW_DEFAULT_TEMPLATE_PART)
    except Exception:
        pass

    candidates = [template]
    program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    for version_dir in program_data.glob("SOLIDWORKS/SOLIDWORKS *"):
        for pattern in ("templates/gb_part.prtdot", "templates/Part.prtdot"):
            candidate = version_dir / pattern
            if candidate.is_file():
                candidates.append(str(candidate))
    candidates.append(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\data\templates\Part.prtdot")
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    raise BuildError("No usable SolidWorks part template was found.")


def select_reference_plane(model: Any, ordinal: int, label: str) -> None:
    model.ClearSelection2(True)
    feature = model.FirstFeature
    plane_count = 0
    while feature is not None:
        if str(feature.GetTypeName2).lower() == "refplane":
            plane_count += 1
            if plane_count == ordinal:
                if not bool(feature.Select2(False, 0)):
                    raise BuildError(f"Could not select {label}.")
                return
        feature = feature.GetNextFeature
    raise BuildError(f"Could not find {label}.")


def create_boss(
    model: Any,
    *,
    end_condition: int,
    depth: float,
    reverse_direction: bool = False,
) -> Any:
    return model.FeatureManager.FeatureExtrusion2(
        True,
        False,
        reverse_direction,
        end_condition,
        SW_END_BLIND,
        depth,
        0.001,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
        0,
        0.0,
        False,
    )


def create_cut(model: Any, *, depth: float, reverse_direction: bool) -> Any:
    return model.FeatureManager.FeatureCut3(
        True,
        False,
        reverse_direction,
        SW_END_BLIND,
        SW_END_BLIND,
        depth,
        0.001,
        False,
        False,
        False,
        False,
        0.0,
        0.0,
        False,
        False,
        False,
        False,
        False,
        True,
        True,
        False,
        False,
        False,
        0,
        0.0,
        False,
    )


def require_feature(model: Any, feature: Any, name: str) -> Any:
    if feature is None:
        raise BuildError(f"Feature creation failed: {name}")
    feature.Name = name
    if not bool(model.EditRebuild3):
        raise BuildError(f"Rebuild failed after creating: {name}")
    print(f"Created {name}")
    return feature


def run_sketch(model: Any, plane_ordinal: int, label: str, draw: Callable[[Any], None]) -> None:
    select_reference_plane(model, plane_ordinal, label)
    sketch = model.SketchManager
    sketch.InsertSketch(True)
    sketch.AddToDB = True
    try:
        draw(sketch)
    finally:
        sketch.AddToDB = False
        sketch.InsertSketch(True)


def circle(sketch: Any, x: float, y: float, radius: float) -> None:
    if sketch.CreateCircleByRadius(x, y, 0.0, radius) is None:
        raise BuildError("Circle creation failed.")


def draw_base(sketch: Any) -> None:
    hx = BASE_LENGTH / 2.0
    hz = BASE_WIDTH / 2.0
    tx = hx - BASE_CORNER_R
    tz = hz - BASE_CORNER_R
    q = BASE_CORNER_R / math.sqrt(2.0)

    sketch.CreateLine(-tx, -hz, 0.0, tx, -hz, 0.0)
    sketch.Create3PointArc(tx, -hz, 0.0, hx, -tz, 0.0, tx + q, -tz - q, 0.0)
    sketch.CreateLine(hx, -tz, 0.0, hx, tz, 0.0)
    sketch.Create3PointArc(hx, tz, 0.0, tx, hz, 0.0, tx + q, tz + q, 0.0)
    sketch.CreateLine(tx, hz, 0.0, -tx, hz, 0.0)
    sketch.Create3PointArc(-tx, hz, 0.0, -hx, tz, 0.0, -tx - q, tz + q, 0.0)
    sketch.CreateLine(-hx, tz, 0.0, -hx, -tz, 0.0)
    sketch.Create3PointArc(-hx, -tz, 0.0, -tx, -hz, 0.0, -tx - q, -tz - q, 0.0)

    for x in (-MOUNT_HALF_X, MOUNT_HALF_X):
        for z in (-MOUNT_HALF_Z, MOUNT_HALF_Z):
            circle(sketch, x, z, MOUNT_HOLE_DIA / 2.0)


def draw_arch(sketch: Any) -> None:
    base_top = BASE_THICKNESS / 2.0
    sketch.CreateLine(-BODY_OUTER_R, base_top, 0.0, -BODY_OUTER_R, SHAFT_AXIS_Y, 0.0)
    sketch.Create3PointArc(
        -BODY_OUTER_R,
        SHAFT_AXIS_Y,
        0.0,
        BODY_OUTER_R,
        SHAFT_AXIS_Y,
        0.0,
        0.0,
        SHAFT_AXIS_Y + BODY_OUTER_R,
        0.0,
    )
    sketch.CreateLine(BODY_OUTER_R, SHAFT_AXIS_Y, 0.0, BODY_OUTER_R, base_top, 0.0)
    sketch.CreateLine(BODY_OUTER_R, base_top, 0.0, -BODY_OUTER_R, base_top, 0.0)
    circle(sketch, 0.0, SHAFT_AXIS_Y, SHAFT_BORE_DIA / 2.0)


def draw_ribs(sketch: Any) -> None:
    y0 = BASE_THICKNESS / 2.0
    y1 = SHAFT_AXIS_Y + 0.016

    sketch.CreateLine(-0.076, y0, 0.0, -BODY_OUTER_R, y0, 0.0)
    sketch.CreateLine(-BODY_OUTER_R, y0, 0.0, -BODY_OUTER_R, y1, 0.0)
    sketch.CreateLine(-BODY_OUTER_R, y1, 0.0, -0.076, y0, 0.0)

    sketch.CreateLine(BODY_OUTER_R, y0, 0.0, 0.076, y0, 0.0)
    sketch.CreateLine(0.076, y0, 0.0, BODY_OUTER_R, y1, 0.0)
    sketch.CreateLine(BODY_OUTER_R, y1, 0.0, BODY_OUTER_R, y0, 0.0)


def draw_top_boss(sketch: Any) -> None:
    circle(sketch, 0.0, 0.0, TOP_BOSS_DIA / 2.0)


def draw_top_bore(sketch: Any) -> None:
    circle(sketch, 0.0, 0.0, TOP_BORE_DIA / 2.0)


def draw_collar(sketch: Any) -> None:
    circle(sketch, 0.0, SHAFT_AXIS_Y, COLLAR_DIA / 2.0)


def draw_shaft_bore(sketch: Any) -> None:
    circle(sketch, 0.0, SHAFT_AXIS_Y, SHAFT_BORE_DIA / 2.0)


def get_solid_summary(model: Any) -> tuple[int, tuple[float, float, float, float, float, float]]:
    bodies = model.GetBodies2(SW_BODY_SOLID, False)
    if not bodies:
        raise BuildError("SolidWorks returned no solid bodies.")

    boxes = [tuple(float(v) for v in body.GetBodyBox()) for body in bodies]
    box = (
        min(item[0] for item in boxes),
        min(item[1] for item in boxes),
        min(item[2] for item in boxes),
        max(item[3] for item in boxes),
        max(item[4] for item in boxes),
        max(item[5] for item in boxes),
    )
    return len(bodies), box


def validate_summary(body_count: int, box: tuple[float, float, float, float, float, float]) -> bool:
    size_x = box[3] - box[0]
    size_y = box[4] - box[1]
    size_z = box[5] - box[2]
    valid = (
        body_count == 1
        and 0.170 <= size_x <= 0.178
        and 0.088 <= size_z <= 0.092
        and 0.089 <= size_y <= 0.096
        and box[1] >= -0.012
    )
    print(
        "Validation: "
        f"bodies={body_count}, size_mm="
        f"{size_x * 1000:.2f} x {size_z * 1000:.2f} x {size_y * 1000:.2f}, "
        f"min_y_mm={box[1] * 1000:.2f}"
    )
    return valid


def build_model(app: Any, template: str, *, reverse_top_boss: bool) -> Any:
    model = app.NewDocument(template, 0, 0.0, 0.0)
    if model is None:
        raise BuildError("SolidWorks could not create a new part document.")

    run_sketch(model, 2, "Top Plane", draw_base)
    require_feature(
        model,
        create_boss(model, end_condition=SW_END_MIDPLANE, depth=BASE_THICKNESS),
        "01_BASE_174x90x15_R15",
    )

    run_sketch(model, 1, "Front Plane", draw_arch)
    require_feature(
        model,
        create_boss(model, end_condition=SW_END_MIDPLANE, depth=BODY_DEPTH),
        "02_ARCH_BODY_R40_D60",
    )

    run_sketch(model, 1, "Front Plane", draw_ribs)
    require_feature(
        model,
        create_boss(model, end_condition=SW_END_MIDPLANE, depth=RIB_DEPTH),
        "03_SIDE_RIBS_T16",
    )

    run_sketch(model, 2, "Top Plane", draw_top_boss)
    require_feature(
        model,
        create_boss(
            model,
            end_condition=SW_END_BLIND,
            depth=MODEL_TOP_Y,
            reverse_direction=reverse_top_boss,
        ),
        "04_TOP_BOSS_D54",
    )

    run_sketch(model, 1, "Front Plane", draw_collar)
    require_feature(
        model,
        create_boss(model, end_condition=SW_END_MIDPLANE, depth=COLLAR_DEPTH),
        "05_SHAFT_COLLAR_D60",
    )

    run_sketch(model, 2, "Top Plane", draw_top_bore)
    require_feature(
        model,
        create_cut(model, depth=0.110, reverse_direction=False),
        "06_TOP_BORE_D34_UP",
    )

    run_sketch(model, 2, "Top Plane", draw_top_bore)
    require_feature(
        model,
        create_cut(model, depth=0.025, reverse_direction=True),
        "07_TOP_BORE_D34_DOWN",
    )

    run_sketch(model, 1, "Front Plane", draw_shaft_bore)
    require_feature(
        model,
        create_cut(model, depth=0.060, reverse_direction=False),
        "08_SHAFT_BORE_D28_FRONT",
    )

    run_sketch(model, 1, "Front Plane", draw_shaft_bore)
    require_feature(
        model,
        create_cut(model, depth=0.060, reverse_direction=True),
        "09_SHAFT_BORE_D28_REAR",
    )

    model.ForceRebuild3(False)
    return model


def next_output_path(folder: Path) -> Path:
    candidate = folder / "bearing_housing_reference.SLDPRT"
    if not candidate.exists():
        return candidate
    for index in range(2, 100):
        candidate = folder / f"bearing_housing_reference_{index}.SLDPRT"
        if not candidate.exists():
            return candidate
    raise BuildError("Could not choose a non-conflicting output filename.")


def close_unsaved_attempt(app: Any, model: Any) -> None:
    try:
        app.CloseDoc(model.GetTitle)
    except Exception:
        pass


def main() -> int:
    pythoncom.CoInitialize()
    app = None
    model = None
    try:
        app = connect_solidworks()
        template = resolve_part_template(app)
        print(f"Using template: {template}")

        model = build_model(app, template, reverse_top_boss=False)
        body_count, box = get_solid_summary(model)
        if not validate_summary(body_count, box):
            print("Top boss direction did not match the model axes; rebuilding once.")
            close_unsaved_attempt(app, model)
            model = build_model(app, template, reverse_top_boss=True)
            body_count, box = get_solid_summary(model)
            if not validate_summary(body_count, box):
                raise BuildError("The rebuilt model failed solid or size validation.")

        model.ShowNamedView2("*Isometric", SW_VIEW_ISOMETRIC)
        _ = model.ViewZoomtofit2
        _ = model.GraphicsRedraw2

        output_path = next_output_path(Path(__file__).resolve().parent)
        save_status = int(model.SaveAs3(str(output_path), SW_SAVE_CURRENT, SW_SAVE_SILENT))
        if save_status != 0:
            raise BuildError(f"SolidWorks could not save {output_path}")

        print("SUCCESS")
        print(f"Saved: {output_path}")
        print(f"Solid bodies: {body_count}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}")
        traceback.print_exc()
        if app is not None and model is not None:
            close_unsaved_attempt(app, model)
        return 1
    finally:
        model = None
        app = None
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
