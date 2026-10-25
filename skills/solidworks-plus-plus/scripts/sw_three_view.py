"""从已有零件生成 GB 风格三视图工程图。

默认第一角投影（GB/T）：主视图 + 俯视图（下方）+ 左视图（右方），
可选等轴测图；可插入模型尺寸并导出 PDF/PNG 预览和结构报告。

运行：
    py -3.12 scripts/sw_three_view.py --part C:\\path\\part.sldprt --out-dir C:\\path\\out

输出：
    <out-dir>/<part>.slddrw
    <out-dir>/<part>.pdf
    <out-dir>/<part>_drawing_preview.png
    <out-dir>/<part>_drawing_report.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from fractions import Fraction
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from sw_connect import get_com_member  # noqa: E402
from sw_drawing import (  # noqa: E402
    PAPER_SIZES,
    _apply_view_layout,
    export_sheet_to_pdf,
    inspect_drawing_structure,
    insert_dimensions,
    plan_standard_view_layout,
)
from sw_review import (  # noqa: E402
    collect_geometry_measurements,
    review_drawing_layout,
)
from sw_session import SolidWorksSession  # noqa: E402


def find_drawing_template(paper: str) -> dict:
    """@brief 在本机模板目录中查找 GB 图幅模板和图框。"""
    program_data = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    roots = [program_data / "SOLIDWORKS"]
    templates, formats = [], []
    for root in roots:
        if not root.is_dir():
            continue
        templates.extend(root.glob(f"*/templates/gb_{paper.lower()}.drwdot"))
        templates.extend(root.glob("*/templates/gb.drwdot"))
        formats.extend(root.glob(f"*/lang/*/sheetformat/{paper.lower()} - gb.slddrt"))
    fallback = Path(r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\data\templates\gb.drwdot")
    if fallback.is_file():
        templates.append(fallback)
    chosen_template = next((p for p in templates if paper.lower() in p.name.lower()), None)
    if chosen_template is None:
        chosen_template = templates[0] if templates else None
    return {
        "template": str(chosen_template) if chosen_template else None,
        "sheet_format": str(formats[0]) if formats else None,
        "template_candidates": [str(p) for p in templates],
        "sheet_format_candidates": [str(p) for p in formats],
    }


def setup_sheet(drawing, paper: str, sheet_format: str | None) -> dict:
    """@brief 用 SetupSheet6 将当前图纸设为指定图幅和 GB 图框（第一角）。"""
    spec = PAPER_SIZES[paper]
    try:
        sheet = get_com_member(drawing, "GetCurrentSheet")
        sheet_name = str(get_com_member(sheet, "GetName") or "")
        configured = bool(get_com_member(
            drawing,
            "SetupSheet6",
            sheet_name,
            spec["code"],
            spec["code"],
            1.0,
            1.0,
            True,
            sheet_format or "",
            0.0,
            0.0,
            "",
            False,
            0.0,
            0.0,
            0.0,
            0.0,
            0,
            0,
        ))
        if not configured:
            return {"configured": False, "sheet_name": sheet_name,
                    "error_code": "DRAWING_SHEET_SETUP_FAILED"}
        # GetProperties 返回 (paper_size, template_in, scale1, scale2, first_angle,
        #                      width_m, height_m)；必须回读，不能只信 SetupSheet6 的 True。
        properties = list(get_com_member(sheet, "GetProperties") or [])
        actual = properties[-2:] if len(properties) >= 2 else []
        size_ok = (
            len(actual) == 2
            and abs(float(actual[0]) - spec["width_m"]) < 0.002
            and abs(float(actual[1]) - spec["height_m"]) < 0.002
        )
        return {
            "configured": True,
            "sheet_size_verified": size_ok,
            "sheet_name": sheet_name,
            "paper_properties": properties,
            "actual_size_m": actual,
            "expected_size_m": [spec["width_m"], spec["height_m"]],
            "error_code": None if size_ok else "DRAWING_SHEET_SIZE_MISMATCH",
        }
    except Exception as exc:
        return {"configured": False, "error_code": "DRAWING_SHEET_SETUP_FAILED", "error": str(exc)}


def resolve_model_view_names(model) -> dict:
    """@brief 读取本机语言的模型视图名（中文 SolidWorks 不认 *Front）。"""
    names = [str(item) for item in (get_com_member(model, "GetModelViewNames") or [])]

    def pick(chinese: str, english: str) -> str:
        for keyword in (chinese, english):
            for name in names:
                if keyword.lower() in name.lower():
                    return name
        return f"*{english.capitalize()}"

    return {
        "*Front": pick("前视", "front"),
        "*Top": pick("上视", "top"),
        "*Left": pick("左视", "left"),
        "*Right": pick("右视", "right"),
        "*Isometric": pick("等轴测", "isometric"),
    }


def create_views(drawing, part_path: str, layout: dict, view_names: dict | None = None) -> dict:
    """@brief 按布局创建视图并逐项校验位置与比例。"""
    numerator, denominator = layout["scale_ratio"]
    mapping = view_names or {}
    created, failures = [], []
    for item in layout["views"]:
        center = item["center"]
        attempt = mapping.get(item["name"], item["name"])
        view = drawing.CreateDrawViewFromModelView3(part_path, attempt, center[0], center[1], 0)
        if view is None:
            failures.append({"name": item["name"], "attempted": attempt,
                             "reason": "CreateDrawViewFromModelView3 returned None"})
            continue
        try:
            created.append(_apply_view_layout(view, item, numerator, denominator))
        except Exception as exc:
            failures.append({"name": item["name"], "attempted": attempt,
                             "reason": f"layout failed: {exc}"})
    return {"views": created, "failures": failures, "view_count": len(created)}


def add_isometric_view(drawing, part_path: str, layout: dict, view_names: dict | None = None) -> dict | None:
    """@brief 在工作区右上角尝试放置等轴测图；位置冲突时返回失败记录。"""
    try:
        working = layout["working_area"]
        scale = layout["scale"] * 0.75
        ratio = Fraction(float(scale)).limit_denominator(1000)
        width = max(0.02, (working["right"] - working["left"]) * 0.28)
        center = [working["right"] - width / 2.0, working["top"] - width * 0.35]
        attempt = (view_names or {}).get("*Isometric", "*Isometric")
        view = drawing.CreateDrawViewFromModelView3(part_path, attempt, center[0], center[1], 0)
        if view is None:
            return None
        import pythoncom
        from win32com.client import VARIANT

        view.ScaleRatio = VARIANT(
            pythoncom.VT_ARRAY | pythoncom.VT_R8,
            [float(ratio.numerator), float(ratio.denominator)],
        )
        return {"name": "*Isometric", "attempted": attempt, "center": center,
                "actual_name": str(get_com_member(view, "Name") or "")}
    except Exception as exc:
        return {"error": str(exc)}


def render_pdf_preview(pdf_path: Path, png_path: Path, dpi: int = 150) -> dict:
    """@brief 用 PyMuPDF 把 PDF 第一页渲染为 PNG，并检查非空白。"""
    try:
        import pymupdf as fitz
    except ImportError:
        try:
            import fitz  # type: ignore
        except ImportError:
            return {"rendered": False, "error_code": "PYMUPDF_MISSING"}
    try:
        document = fitz.open(str(pdf_path))
        page = document[0]
        pixmap = page.get_pixmap(dpi=dpi)
        pixmap.save(str(png_path))
        document.close()
        evidence = {"rendered": True, "path": str(png_path)}
        try:
            from PIL import Image

            image = Image.open(png_path).convert("L")
            histogram = image.histogram()
            total = sum(histogram)
            dark_ratio = sum(histogram[:240]) / float(total or 1)
            evidence["dark_pixel_ratio"] = round(dark_ratio, 6)
            evidence["not_blank"] = bool(dark_ratio > 0.0005)
        except Exception as exc:
            evidence["blank_check_error"] = str(exc)
        return evidence
    except Exception as exc:
        return {"rendered": False, "error_code": "PDF_PREVIEW_FAILED", "error": str(exc)}


def run(args) -> dict:
    paper = args.paper.upper()
    if paper not in PAPER_SIZES:
        raise SystemExit(f"不支持的图幅: {paper}")
    part_path = str(Path(args.part).resolve())
    if not Path(part_path).is_file():
        raise SystemExit(f"零件不存在: {part_path}")
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(part_path).stem
    drawing_path = out_dir / f"{stem}.SLDDRW"
    pdf_path = out_dir / f"{stem}.pdf"
    png_path = out_dir / f"{stem}_drawing_preview.png"
    report_path = out_dir / f"{stem}_drawing_report.json"
    report = {"status": "blocked", "part": part_path, "paper": paper,
              "projection": args.projection, "outputs": {}}

    templates = find_drawing_template(paper)
    if not templates["template"]:
        report.update({"error_code": "DRAWING_TEMPLATE_MISSING", "templates": templates})
        return report

    session = SolidWorksSession(visible=True, wait_seconds=20)
    drawing = None
    part = None
    try:
        part = session.open(part_path, read_only=True, silent=True)
        measurements = collect_geometry_measurements(part)
        view_names = resolve_model_view_names(part)
        report["model_view_names"] = view_names
        envelope_mm = measurements.get("envelope_mm") or {}
        if "length" not in envelope_mm:
            raise RuntimeError("无法读取零件包围盒")
        size_m = [envelope_mm["length"] / 1000.0, envelope_mm["width"] / 1000.0, envelope_mm["height"] / 1000.0]
        report["envelope_mm"] = envelope_mm

        layout = plan_standard_view_layout(size_m, paper_size=paper, projection=args.projection)
        report["layout"] = {key: layout[key] for key in ("status", "scale", "scale_ratio", "projection", "views")}

        drawing = session.new_drawing(template_path=templates["template"])
        report["sheet_setup"] = setup_sheet(drawing, paper, templates["sheet_format"])
        if not report["sheet_setup"].get("sheet_size_verified"):
            report.update({"status": "failed",
                           "error_code": report["sheet_setup"].get("error_code")})
            return report
        creation = create_views(drawing, part_path, layout, view_names)
        report["view_creation"] = creation
        if creation["view_count"] < 3:
            report.update({"status": "failed", "error_code": "DRAWING_VIEW_CREATE_FAILED"})
            return report

        if args.iso:
            report["isometric"] = add_isometric_view(drawing, part_path, layout, view_names)

        if args.dims:
            inserted = insert_dimensions(drawing)
            report["dimension_insertion"] = {"returned": inserted is not None,
                                             "type": str(type(inserted))}
            try:
                from sw_drawing import auto_arrange_drawing_dimensions

                report["dimension_arrangement"] = auto_arrange_drawing_dimensions(drawing)
            except Exception as exc:
                report["dimension_arrangement"] = {"status": "skipped", "error": str(exc)}

        drawing.ForceRebuild3(False)
        drawing.ViewZoomtofit2()
        saved = session.save(drawing, str(drawing_path))
        report["outputs"]["slddrw"] = {"path": str(drawing_path), "saved": bool(saved),
                                       "exists": drawing_path.is_file()}
        pdf_ok = export_sheet_to_pdf(drawing, str(pdf_path), sw_app=session.sw)
        report["outputs"]["pdf"] = {"path": str(pdf_path), "exported": bool(pdf_ok),
                                    "exists": pdf_path.is_file()}
        if pdf_path.is_file():
            report["preview"] = render_pdf_preview(pdf_path, png_path)

        structure = inspect_drawing_structure(drawing, paper_size_hint=paper)
        review = review_drawing_layout(structure)
        report["structure"] = {
            "view_count": len(structure.get("views", [])),
            "dimension_count": len(structure.get("dimensions", [])),
            "views": structure.get("views", []),
            "paper_size": structure.get("paper_size"),
        }
        report["review"] = review
        view_ok = len(structure.get("views", [])) >= 3
        report["status"] = "pass" if (view_ok and pdf_path.is_file()) else "warn"
        if not view_ok:
            report["error_code"] = "DRAWING_STRUCTURE_INCOMPLETE"

        # 附加：PDF 机器初筛（悬空尺寸/无引出线/越界/重叠/与报告不一致）。
        # 不改变既有 status 语义，只把结果单列，供 SKILL.md §4/§5 的门禁读取。
        if pdf_path.is_file():
            try:
                report_path.write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                from check_drawing_pdf import check_pdf

                pdf_check = check_pdf(pdf_path, report_path=report_path)
                report["pdf_check"] = {
                    "status": pdf_check.get("status"),
                    "findings": pdf_check.get("findings", []),
                    "thresholds": pdf_check.get("thresholds"),
                    "limitations": pdf_check.get("limitations"),
                    "note": "机器初筛，不替代目视；只认 SolidWorks 导出的矢量 PDF。",
                }
                if pdf_check.get("status") == "fail":
                    report.setdefault("delivery_warnings", []).append(
                        "PDF_CHECK_FAILED：按 SKILL.md §4/§5，工程图不得凭此 PDF 宣布完成。")
            except Exception as exc:  # 不影响出图主流程，但必须如实标记未执行
                report["pdf_check"] = {
                    "status": "skipped",
                    "error": str(exc),
                    "note": "PDF 检查未执行——按 not_run 处理，不算通过。",
                }
    finally:
        if part is not None:
            try:
                session.close(part)
            except Exception:
                pass
        report["report_path"] = str(report_path)
        try:
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--paper", default="A3", choices=sorted(PAPER_SIZES))
    parser.add_argument("--projection", default="first", choices=["first", "third"])
    parser.add_argument("--dims", action="store_true", help="插入模型尺寸")
    parser.add_argument("--iso", action="store_true", help="附加等轴测图")
    args = parser.parse_args()
    report = run(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
