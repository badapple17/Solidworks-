"""@brief 工程图 PDF 离线检查：尺寸文字悬空、文字互相重叠、文字压在视图轮廓上、越出图框。

思路借鉴 earthtojake/text-to-cad 的 engineering-drawing 技能：出图脚本应该把
“尺寸量在空白纸上（measures blank paper）”“标注互相压字（annotation overlaps）”
“视图跑出图框”这类问题当场报出来，而不是等人看 PDF。SolidWorks 的
IDisplayDimension 拿不到可靠的文字包围盒（_drawing_report.json 里多为 estimated），
所以这里直接读 SolidWorks 导出的矢量 PDF：文字 span 是真实渲染位置，视图轮廓是
线宽最粗的那组线段。

只依赖 PyMuPDF，不连接 SolidWorks：

    py -3.12 <skill>/scripts/check_drawing_pdf.py <workdir>/drawing/part.pdf
    py -3.12 <skill>/scripts/check_drawing_pdf.py part.pdf --report part_drawing_report.json --out check.json

返回码：0 = pass，1 = warn（仅 --strict），2 = fail，3 = PDF 不可读。

判据（单位 pt，1 pt = 0.3528 mm）：
- DIM_FLOATING：尺寸文字离最近的尺寸线/箭头/视图线段超过 --float-gap（默认 6 mm）。
  SolidWorks 把 φ 符号、箭头画成细线小块，所以“附近的细线”也算锚点；一个尺寸
  周围一根线都没有，几乎一定是标注跑到了空白处（齿轮图顶部的 φ36 / φ20 就是这种）。
- TEXT_OVERLAP：两个文字 span 交叠面积 > 0.5 pt²。
- TEXT_ON_VIEW：尺寸文字中心落在视图轮廓包围盒内部且压到粗实线。
- OUT_OF_FRAME：文字或视图越出图框内边界（默认四周 10 mm 边距）。
- 标题栏区域（默认右下 180×56 mm）里的文字不参与尺寸检查。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

PT_PER_MM = 72.0 / 25.4
DIMENSION_TEXT = re.compile(r"^[\s∅ØφΦR±+\-xX×°.,:0-9()（）]*\d[\s∅ØφΦR±+\-xX×°.,:0-9()（）]*$")
GRID_LABEL = re.compile(r"^\s*([1-9]|1[0-9]|[A-H])\s*$")
SCALE_RATIO = re.compile(r"^\s*(\d+)\s*[:：]\s*(\d+)\s*$")


def _box(values) -> list[float]:
    x0, y0, x1, y1 = (float(v) for v in values)
    return [min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)]


def _overlap_area(a: list[float], b: list[float]) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _point_segment_distance(px: float, py: float, seg: tuple[float, float, float, float]) -> float:
    x0, y0, x1, y1 = seg
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / length2))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def _box_segment_distance(box: list[float], seg: tuple[float, float, float, float]) -> float:
    """文字框到线段的最近距离（框内相交时为 0）。"""
    x0, y0, x1, y1 = box
    sx0, sy0, sx1, sy1 = seg
    if (x0 <= sx0 <= x1 and y0 <= sy0 <= y1) or (x0 <= sx1 <= x1 and y0 <= sy1 <= y1):
        return 0.0
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    best = min(_point_segment_distance(cx, cy, seg) for cx, cy in corners)
    for i in range(4):
        ex0, ey0 = corners[i]
        ex1, ey1 = corners[(i + 1) % 4]
        best = min(best, _point_segment_distance(sx0, sy0, (ex0, ey0, ex1, ey1)),
                   _point_segment_distance(sx1, sy1, (ex0, ey0, ex1, ey1)))
    return best


def _path_segments(path: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    segments = []
    for item in path.get("items", []):
        kind = item[0]
        if kind == "l":
            segments.append((item[1].x, item[1].y, item[2].x, item[2].y))
        elif kind == "c":  # 贝塞尔曲线：用控制多边形近似
            pts = [item[1], item[2], item[3], item[4]]
            segments.extend((a.x, a.y, b.x, b.y) for a, b in zip(pts, pts[1:]))
        elif kind == "re":
            r = item[1]
            segments.extend([(r.x0, r.y0, r.x1, r.y0), (r.x1, r.y0, r.x1, r.y1),
                             (r.x1, r.y1, r.x0, r.y1), (r.x0, r.y1, r.x0, r.y0)])
        elif kind == "qu":
            q = item[1]
            pts = [q.ul, q.ur, q.lr, q.ll, q.ul]
            segments.extend((a.x, a.y, b.x, b.y) for a, b in zip(pts, pts[1:]))
    return segments


def _mostly_inside(box: list[float], region: list[float], threshold: float = 0.5) -> bool:
    """@brief 判断路径是否主要落在指定区域内（用于排除标题栏图框线）。"""
    area = (box[2] - box[0]) * (box[3] - box[1])
    if area <= 0:
        return False
    return _overlap_area(box, region) >= threshold * area


def _merge_boxes(boxes: list[list[float]], gap: float) -> list[list[float]]:
    merged = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        for i in range(len(merged)):
            for j in range(i + 1, len(merged)):
                a, b = merged[i], merged[j]
                if a[0] - gap <= b[2] and b[0] - gap <= a[2] and a[1] - gap <= b[3] and b[1] - gap <= a[3]:
                    merged[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    merged.pop(j)
                    changed = True
                    break
            if changed:
                break
    return merged


def classify_page(page, *, symbol_max_mm: float = 4.0,
                  title_block: list[float] | None = None) -> dict[str, Any]:
    """把 PDF 页面的矢量路径分成：视图轮廓（粗线）、标注线（细线）、符号小块、图框。

    视图轮廓取**最粗**线宽（SW 可见轮廓线），不能取“最粗线的 60%”：
    尺寸线/尺寸界线通常是次粗线，按 60% 会被误判成视图轮廓，导致
    DIM_NO_LEADER 假阳性、视图框被尺寸线撑大。
    标题栏内的模板线也不属于模型视图，单独排除。
    """
    width, height = float(page.rect.width), float(page.rect.height)
    paths = page.get_drawings()
    max_width = max((float(p.get("width") or 0) for p in paths), default=0.0)
    symbol_max = symbol_max_mm * PT_PER_MM
    view_paths, line_paths, symbol_paths, frame_boxes = [], [], [], []
    for p in paths:
        rect = p.get("rect")
        box = _box((rect.x0, rect.y0, rect.x1, rect.y1))
        w, h = box[2] - box[0], box[3] - box[1]
        if w >= 0.8 * width or h >= 0.8 * height:
            frame_boxes.append(box)
            continue
        if w <= symbol_max and h <= symbol_max:
            symbol_paths.append({"box": box, "segments": _path_segments(p)})
            continue
        stroke = float(p.get("width") or 0)
        record = {"box": box, "width": stroke, "segments": _path_segments(p)}
        is_view_stroke = max_width > 0 and stroke >= 0.95 * max_width
        in_title_block = bool(title_block and _mostly_inside(box, title_block))
        if is_view_stroke and not in_title_block and (w > 10 * PT_PER_MM or h > 10 * PT_PER_MM):
            view_paths.append(record)
        else:
            line_paths.append(record)
    views = _merge_boxes([p["box"] for p in view_paths], gap=1.0)
    return {
        "width": width, "height": height,
        "views": views, "view_paths": view_paths, "line_paths": line_paths,
        "symbol_paths": symbol_paths, "frame_boxes": frame_boxes,
    }


def extract_text(page) -> list[dict[str, Any]]:
    spans = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = str(span.get("text") or "").strip()
                if text:
                    spans.append({"text": text, "box": _box(span["bbox"]), "dir": list(line.get("dir") or (1, 0))})
    return spans


def _normalise_ratio(value: Any) -> tuple[int, int] | None:
    """@brief 把 [2, 1]、"2:1" 等比例统一成既约整数比。"""
    try:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            numerator, denominator = float(value[0]), float(value[1])
        elif isinstance(value, str):
            match = SCALE_RATIO.match(value)
            if not match:
                return None
            numerator, denominator = float(match.group(1)), float(match.group(2))
        else:
            return None
    except (TypeError, ValueError):
        return None
    if numerator <= 0 or denominator <= 0:
        return None
    ratio = (Fraction(numerator) / Fraction(denominator)).limit_denominator(1000)
    return ratio.numerator, ratio.denominator


def _distance_to_box(box: list[float], other: list[float]) -> float:
    dx = max(other[0] - box[2], box[0] - other[2], 0.0)
    dy = max(other[1] - box[3], box[1] - other[3], 0.0)
    return math.hypot(dx, dy)


def check_page(page, *, margin_mm: float, title_block_mm: tuple[float, float],
               leader_gap_mm: float, view_gap_mm: float) -> dict[str, Any]:
    width, height = float(page.rect.width), float(page.rect.height)
    margin = margin_mm * PT_PER_MM
    inner = [margin, margin, width - margin, height - margin]
    tb_w, tb_h = (v * PT_PER_MM for v in title_block_mm)
    title_block = [width - margin - tb_w, height - margin - tb_h, width - margin, height - margin]
    layout = classify_page(page, title_block=title_block)
    spans = extract_text(page)
    findings: list[dict[str, Any]] = []
    title_block_ratios = []

    def in_margin(box: list[float]) -> bool:
        return box[0] < inner[0] or box[1] < inner[1] or box[2] > inner[2] or box[3] > inner[3]

    dims = []
    for span in spans:
        box = span["box"]
        if GRID_LABEL.match(span["text"]) and in_margin(box):
            continue  # 图框分区编号
        if _overlap_area(box, title_block) > 0.5 * (box[2] - box[0]) * (box[3] - box[1]):
            match = SCALE_RATIO.match(span["text"])
            if match:
                title_block_ratios.append({
                    "text": span["text"],
                    "numerator": int(match.group(1)),
                    "denominator": int(match.group(2)),
                })
            continue  # 标题栏内容
        if DIMENSION_TEXT.match(span["text"]):
            dims.append(span)

    # 尺寸线、尺寸界线和箭头都算“引出线”证据；箭头是 ≤4 mm 的符号块，
    # 漏掉它会把正常标注误判成 DIM_NO_LEADER。
    anchor_segments = [seg for p in layout["line_paths"] + layout["symbol_paths"]
                       for seg in p["segments"]]
    view_segments = [seg for p in layout["view_paths"] for seg in p["segments"]]
    for span in dims:
        box, text = span["box"], span["text"]
        nearest_leader = min((_box_segment_distance(box, s) for s in anchor_segments), default=math.inf)
        nearest_view = min((_distance_to_box(box, v) for v in layout["views"]), default=math.inf)
        record = {
            "text": text, "box_pt": [round(v, 1) for v in box],
            "nearest_leader_mm": None if math.isinf(nearest_leader) else round(nearest_leader / PT_PER_MM, 2),
            "nearest_view_mm": None if math.isinf(nearest_view) else round(nearest_view / PT_PER_MM, 2),
        }
        if nearest_leader > leader_gap_mm * PT_PER_MM:
            findings.append({"severity": "fail", "code": "DIM_NO_LEADER", **record,
                             "message": f"尺寸文字 {text!r} 周围 {leader_gap_mm} mm 内没有尺寸线/引线/箭头，读者无法判断它标的是哪个要素。"})
        if nearest_view > view_gap_mm * PT_PER_MM:
            findings.append({"severity": "fail", "code": "DIM_FLOATING", **record,
                             "message": f"尺寸文字 {text!r} 离最近视图 {record['nearest_view_mm']} mm（阈值 {view_gap_mm} mm），量在空白纸上。"})
        if in_margin(box):
            findings.append({"severity": "fail", "code": "OUT_OF_FRAME", **record,
                             "message": f"尺寸文字 {text!r} 落在图框边距 {margin_mm} mm 以内或纸外。"})
        crossing = [s for s in view_segments if _box_segment_distance(box, s) == 0.0]
        if crossing:
            findings.append({"severity": "warn", "code": "TEXT_ON_VIEW", **record,
                             "message": f"尺寸文字 {text!r} 压在视图轮廓线上（{len(crossing)} 段）。"})
    # 只查“至少一方是尺寸文字”的压字；图框分区号、标题栏格子文字的重叠属于模板本身，不归本图负责。
    dim_ids = {id(span) for span in dims}
    for i, a in enumerate(spans):
        for b in spans[i + 1:]:
            if id(a) not in dim_ids and id(b) not in dim_ids:
                continue
            area = _overlap_area(a["box"], b["box"])
            if area > 0.5:
                findings.append({"severity": "fail", "code": "TEXT_OVERLAP", "text": f"{a['text']} | {b['text']}",
                                 "intersection_pt2": round(area, 2), "message": "两段文字互相压字。"})
    for view in layout["views"]:
        if in_margin(view):
            findings.append({"severity": "fail", "code": "VIEW_OUT_OF_FRAME", "box_pt": [round(v, 1) for v in view],
                             "message": "视图越出图框边距。"})
    for i, a in enumerate(layout["views"]):
        for b in layout["views"][i + 1:]:
            if _overlap_area(a, b) > 1.0:
                findings.append({"severity": "fail", "code": "VIEW_OVERLAP", "box_pt": [round(v, 1) for v in a],
                                 "message": "两个视图的轮廓包围盒重叠。"})
    return {
        "page_size_mm": [round(width / PT_PER_MM, 1), round(height / PT_PER_MM, 1)],
        "view_count": len(layout["views"]),
        "dimension_text_count": len(dims),
        "leader_path_count": len(layout["line_paths"]),
        "title_block_ratios": title_block_ratios,
        "findings": findings,
    }


def cross_check_report(result: dict[str, Any], report_path: Path) -> list[dict[str, Any]]:
    """与 sw_three_view.py 的 _drawing_report.json 交叉核对视图数和尺寸数。"""
    findings = []
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [{"severity": "warn", "code": "REPORT_UNREADABLE", "message": f"无法读取出图报告：{exc}"}]
    structure = report.get("structure") or {}
    expected_dims = int(structure.get("dimension_count") or 0)
    pdf_dims = sum(page["dimension_text_count"] for page in result["pages"])
    if expected_dims and pdf_dims < expected_dims:
        findings.append({"severity": "fail", "code": "DIM_COUNT_MISMATCH",
                         "message": f"出图报告有 {expected_dims} 个尺寸，PDF 只识别到 {pdf_dims} 个尺寸文字；有尺寸没有画出来或被盖住。"})
    review_findings = (report.get("review") or {}).get("findings") or []
    for item in review_findings:
        if item.get("severity") == "fail" and item.get("evidence_source") == "native":
            findings.append({"severity": "fail", "code": f"REPORT_{item.get('code')}",
                             "message": f"出图报告已有原生证据的失败项：{item.get('code')} {item.get('first')} / {item.get('second')}"})
    sheet = report.get("sheet_setup") or {}
    if sheet and not sheet.get("sheet_size_verified"):
        findings.append({"severity": "fail", "code": "SHEET_SIZE_UNVERIFIED", "message": "出图报告未回读确认图幅。"})

    # 图面比例三方核对：图面设置（标题栏“比例”格的来源）↔ 视图比例 ↔ PDF 标题栏文字。
    # 只设视图比例、不设图面比例，正是 v1.1 齿轮图“视图 2:1、标题栏 1:1”的根因。
    expected = _normalise_ratio((report.get("layout") or {}).get("scale_ratio"))
    if expected:
        if sheet:
            actual_sheet = _normalise_ratio(sheet.get("actual_scale"))
            if actual_sheet is None:
                findings.append({"severity": "fail", "code": "SHEET_SCALE_UNVERIFIED",
                                 "message": "出图报告没有回读图面比例，无法证明标题栏比例与视图一致。"})
            elif actual_sheet != expected:
                findings.append({"severity": "fail", "code": "SHEET_SCALE_MISMATCH",
                                 "message": f"图面比例 {actual_sheet[0]}:{actual_sheet[1]} 与布局比例 "
                                            f"{expected[0]}:{expected[1]} 不一致；标题栏会写错比例。"})
        # 主视图比例取众数：轴测图/局部放大图允许与图面比例不同。
        view_scales = [
            scale for scale in (_normalise_ratio(view.get("scale"))
                                for view in structure.get("views") or [])
            if scale
        ]
        if view_scales:
            common = max(dict.fromkeys(view_scales), key=view_scales.count)
            if common != expected:
                findings.append({"severity": "fail", "code": "VIEW_SCALE_MISMATCH",
                                 "message": f"主视图比例 {common[0]}:{common[1]} 与图面比例 "
                                            f"{expected[0]}:{expected[1]} 不一致。"})
        ratios = [ratio for page in result["pages"] for ratio in page.get("title_block_ratios") or []]
        if not any(_normalise_ratio(ratio.get("text")) == expected for ratio in ratios):
            if ratios:
                shown = "、".join(str(ratio.get("text")) for ratio in ratios)
                findings.append({"severity": "fail", "code": "TITLE_SCALE_MISMATCH",
                                 "message": f"PDF 标题栏比例写的是 {shown}，视图实际是 "
                                            f"{expected[0]}:{expected[1]}。"})
            else:
                findings.append({"severity": "warn", "code": "TITLE_SCALE_UNVERIFIED",
                                 "message": "PDF 标题栏内未识别到比例文字，请人工确认比例格。"})
    return findings


def check_pdf(path: Path, *, margin_mm: float = 10.0, title_block_mm: tuple[float, float] = (180.0, 56.0),
              leader_gap_mm: float = 3.0, view_gap_mm: float = 25.0, report_path: Path | None = None) -> dict[str, Any]:
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # 旧版 PyMuPDF
    result: dict[str, Any] = {"pdf": str(path), "pages": [], "findings": []}
    with pymupdf.open(path) as document:
        for index, page in enumerate(document):
            page_result = check_page(page, margin_mm=margin_mm, title_block_mm=title_block_mm,
                                     leader_gap_mm=leader_gap_mm, view_gap_mm=view_gap_mm)
            page_result["page"] = index + 1
            result["pages"].append(page_result)
            result["findings"].extend({**f, "page": index + 1} for f in page_result["findings"])
    if not any(page["view_count"] for page in result["pages"]):
        result["findings"].append({"severity": "fail", "code": "NO_VIEWS", "message": "PDF 里没有识别到视图轮廓（空白图或被轮廓化）。"})
    if report_path:
        result["findings"].extend(cross_check_report(result, report_path))
    severities = {f["severity"] for f in result["findings"]}
    result["status"] = "fail" if "fail" in severities else ("warn" if "warn" in severities else "pass")
    result["thresholds"] = {"margin_mm": margin_mm, "title_block_mm": list(title_block_mm),
                            "leader_gap_mm": leader_gap_mm, "view_gap_mm": view_gap_mm}
    result["limitations"] = [
        "只检查 SolidWorks 导出的矢量 PDF；扫描件或文字被轮廓化时无法识别尺寸文字。",
        "视图按最粗线宽识别；模板若用同等粗线画表格，需要人工复核 view_count。",
        "不判断尺寸链是否完整、基准是否合理；那部分按 drawing-standards.md §8 人工自检。",
    ]
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检查工程图 PDF 的悬空尺寸、压字、越框")
    parser.add_argument("pdf")
    parser.add_argument("--report", help="sw_three_view.py 输出的 _drawing_report.json，用于交叉核对")
    parser.add_argument("--out", help="把结果写到 JSON 文件（不会覆盖已存在的文件）")
    parser.add_argument("--margin-mm", type=float, default=10.0)
    parser.add_argument("--leader-gap-mm", type=float, default=3.0)
    parser.add_argument("--view-gap-mm", type=float, default=25.0)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    pdf = Path(args.pdf)
    if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
        print(f"[error] 不是可读的 PDF: {pdf}", file=sys.stderr)
        return 3
    result = check_pdf(pdf, margin_mm=args.margin_mm, leader_gap_mm=args.leader_gap_mm,
                       view_gap_mm=args.view_gap_mm, report_path=Path(args.report) if args.report else None)
    if args.out:
        out = Path(args.out)
        if out.exists():
            print(f"[error] 输出文件已存在，不覆盖: {out}", file=sys.stderr)
            return 3
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{result['status']}] {pdf.name}: views={sum(p['view_count'] for p in result['pages'])} "
          f"dim_texts={sum(p['dimension_text_count'] for p in result['pages'])} findings={len(result['findings'])}")
    for f in result["findings"]:
        print(f"  {f['severity']:4} {f['code']:22} {f.get('text', '')!s:14} {f['message']}")
    if result["status"] == "fail":
        return 2
    return 1 if result["status"] == "warn" and args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
