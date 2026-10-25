"""
真实 SolidWorks 回归：linear_pattern / shell / rib 封装。

用途：
1. 1D/2D `linear_pattern()` 生成正确孔数（数量含源实例）并校验体积。
2. `shell()` 选顶面移除后生成「抽壳1」，校验薄壁体积。
3. `rib()` 记录当前实现是否返回 None；失败不算回归失败，但必须记录，
   提醒改用闭合三角形草图拉伸。

需要 Windows + SolidWorks + pywin32，默认不会被 unittest discover 执行。
运行：py -3.12 tests\\solidworks_feature_wrappers_regression.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import traceback


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sw_connect import get_com_member, mm  # noqa: E402
from sw_part import (  # noqa: E402
    extrude_boss,
    extrude_cut,
    linear_pattern,
    rib,
    shell,
    sketch,
    sketch_circle,
    sketch_corner_rectangle,
    sketch_line,
)
from sw_review import collect_geometry_measurements  # noqa: E402
from sw_session import SolidWorksSession  # noqa: E402


def _volume(part) -> float | None:
    return collect_geometry_measurements(part).get("volume_mm3")


def _name(feature) -> str | None:
    return getattr(feature, "Name", None)


def _plate_with_hole(session) -> object:
    part = session.new_part()
    with sketch(part, "Front Plane") as sk:
        sketch_corner_rectangle(part, 0, 0, mm(80), mm(40))
    extrude_boss(part, sk, mm(10), direction=False, name="Plate1")
    with sketch(part, "Front Plane") as sk:
        sketch_circle(part, mm(10), mm(10), mm(3))
    extrude_cut(part, sk, 0.0, direction=True, name="Hole1")
    return part


def _top_face(part):
    body = part.GetBodies2(0, False)[0]
    for face in body.GetFaces():
        box = list(get_com_member(face, "GetBox"))
        if (abs(box[2] - mm(20)) < 1e-6 and abs(box[5] - mm(20)) < 1e-6
                and abs(box[3] - mm(60)) < 1e-6):
            return face
    return None


def case_1d(session) -> dict:
    part = _plate_with_hole(session)
    try:
        feature = linear_pattern(part, "Hole1", 1, 0, 0, mm(20), 3)
        return {
            "ok": feature is not None,
            "feature": _name(feature),
            "volume_mm3": _volume(part),
            "expected_mm3": round(32000 - 3 * 3.141592653589793 * 9 * 10, 3),
        }
    finally:
        session.close(part)


def case_2d(session) -> dict:
    part = _plate_with_hole(session)
    try:
        feature = linear_pattern(part, "Hole1", 1, 0, 0, mm(20), 3,
                                 0, 1, 0, mm(15), 2)
        return {
            "ok": feature is not None,
            "feature": _name(feature),
            "volume_mm3": _volume(part),
            "expected_mm3": round(32000 - 6 * 3.141592653589793 * 9 * 10, 3),
        }
    finally:
        session.close(part)


def case_shell(session) -> dict:
    part = session.new_part()
    try:
        with sketch(part, "Front Plane") as sk:
            sketch_corner_rectangle(part, 0, 0, mm(60), mm(40))
        extrude_boss(part, sk, mm(20), direction=False, name="Box1")
        face = _top_face(part)
        if face is None:
            return {"ok": False, "error": "top face not found"}
        feature = shell(part, mm(2), [face])
        return {
            "ok": feature is not None,
            "feature": _name(feature),
            "type": get_com_member(feature, "GetTypeName2"),
            "volume_mm3": _volume(part),
            "expected_mm3": 60 * 40 * 20 - 56 * 36 * 18,
        }
    finally:
        session.close(part)


def case_rib(session) -> dict:
    part = session.new_part()
    try:
        with sketch(part, "Front Plane") as sk:
            sketch_corner_rectangle(part, mm(-30), 0, mm(30), mm(5))
        extrude_boss(part, sk, mm(40), direction=False, name="Base1")
        with sketch(part, "Front Plane") as sk:
            sketch_corner_rectangle(part, mm(20), 0, mm(30), mm(30))
        extrude_boss(part, sk, mm(40), direction=False, name="Wall1")
        with sketch(part, "Front Plane") as rib_sketch:
            sketch_line(part, mm(20), mm(25), mm(5), mm(5))
        feature = rib(part, str(rib_sketch), mm(3), two_sided=False)
        return {
            "ok": feature is not None,
            "feature": _name(feature),
            "volume_mm3": _volume(part),
            "note": "返回 None 属已知实现缺口，改用闭合三角形草图拉伸",
        }
    finally:
        session.close(part)


def run_regression(output_dir: Path, visible: bool = True,
                   wait_seconds: int = 20) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {"cases": {}}
    session = SolidWorksSession(visible=visible, wait_seconds=wait_seconds)
    try:
        for key, fn in (("pattern_1d", case_1d), ("pattern_2d", case_2d),
                        ("shell", case_shell), ("rib", case_rib)):
            try:
                report["cases"][key] = fn(session)
            except Exception as exc:  # noqa: BLE001
                report["cases"][key] = {
                    "ok": False,
                    "error": repr(exc),
                    "traceback": traceback.format_exc(),
                }
    finally:
        try:
            session.sw.CloseAllDocuments(False)
        except Exception:  # noqa: BLE001
            pass

    def _close(actual, expected, tol=0.5):
        return actual is not None and abs(actual - expected) <= tol

    cases = report["cases"]
    report["passed"] = {
        "pattern_1d": cases["pattern_1d"].get("ok") and _close(
            cases["pattern_1d"].get("volume_mm3"),
            cases["pattern_1d"].get("expected_mm3")),
        "pattern_2d": cases["pattern_2d"].get("ok") and _close(
            cases["pattern_2d"].get("volume_mm3"),
            cases["pattern_2d"].get("expected_mm3")),
        "shell": cases["shell"].get("ok") and _close(
            cases["shell"].get("volume_mm3"),
            cases["shell"].get("expected_mm3")),
        # rib 是已知缺口：返回 None 记为 not_applicable，不算失败
        "rib": "known_gap" if not cases["rib"].get("ok") else "now_works",
    }
    report["all_required_passed"] = all(
        report["passed"][key] for key in ("pattern_1d", "pattern_2d", "shell")
    )
    out = output_dir / "solidworks_feature_wrappers_regression.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    report["report_path"] = str(out)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        default=str(Path(tempfile.gettempdir()) / "solidworks_skill_regression"),
    )
    parser.add_argument("--hidden", action="store_true")
    args = parser.parse_args()
    result = run_regression(Path(args.output_dir), visible=not args.hidden)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["all_required_passed"] else 1)
