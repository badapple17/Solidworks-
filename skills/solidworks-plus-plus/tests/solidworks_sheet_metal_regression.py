#!/usr/bin/env python
"""SolidWorks 钣金基体法兰 + 平板型式真机回归。

需要 Windows + SolidWorks + pywin32/comtypes；不会被普通 pytest 收集。
对应黄金用例 sm_base_flange_flat：100×50×0.5 平板，体积 2500.0 mm³。
"""

from __future__ import annotations

import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from sw_connect import get_com_member, mm
from sw_part import sketch_corner_rectangle, current_sketch_name, end_sketch, start_sketch
from sw_review import collect_geometry_measurements
from sw_session import SolidWorksSession
from sw_sheetmetal import assert_sheet_metal, insert_base_flange


def assert_close(actual, expected, label, tolerance):
    if actual is None or abs(float(actual) - float(expected)) > tolerance:
        raise AssertionError(f"{label}: 实际 {actual!r}，预期 {expected} ± {tolerance}")


def main() -> int:
    session = SolidWorksSession(visible=True)
    model = session.new_part()
    try:
        start_sketch(model, "Front Plane")
        sketch_corner_rectangle(model, mm(-50), mm(-25), mm(50), mm(25))
        sketch_name = current_sketch_name(model)
        end_sketch(model)

        feature = insert_base_flange(model, sketch_name, mm(0.5), mm(0.5), 0.0)
        if feature is None:
            raise AssertionError("基体法兰返回 None")
        model.ForceRebuild3(False)

        box = [round(float(value) * 1000.0, 3) for value in model.GetPartBox(True)]
        expected_box = [-50.0, -25.0, -0.5, 50.0, 25.0, 0.0]
        for index, (actual, expected) in enumerate(zip(box, expected_box)):
            assert_close(actual, expected, f"bbox[{index}]", 0.1)

        bodies = model.GetBodies2(0, False) or []
        if len(bodies) != 1:
            raise AssertionError(f"实体数应为 1，实际 {len(bodies)}")
        measurements = collect_geometry_measurements(model)
        volume = measurements.get("volume_mm3")
        assert_close(volume, 2500.0, "volume_mm3", 1.0)

        audit = assert_sheet_metal(model)
        if not audit["has_flat_pattern"]:
            raise AssertionError("平板型式未自动生成")

        print("sheet_metal_base_flange_ok")
        print("sheet_metal_flat_pattern_ok", audit["flat_pattern_name"])
        return 0
    finally:
        try:
            title = str(get_com_member(model, "GetTitle"))
        except Exception:
            title = ""
        if title:
            session.sw.CloseDoc(title)


if __name__ == "__main__":
    raise SystemExit(main())
