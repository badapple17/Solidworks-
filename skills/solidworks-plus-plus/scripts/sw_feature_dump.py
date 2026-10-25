"""只读导出 SolidWorks 零件/装配体的特征树、尺寸和包围盒。

用途：
    1. 分析已有模型，复现其建模顺序；
    2. 批量挖掘题库答案的建模模式；
    3. 出图前检查模型里是否存在可导入的尺寸。

运行：
    py -3.12 scripts/sw_feature_dump.py --part <workdir>\\part.SLDPRT --output <workdir>\\part.json
    py -3.12 scripts/sw_feature_dump.py --root <答案题库目录> --output <workdir>\\dump.jsonl --limit 50

单文件输出 JSON；目录输出 JSONL。全程只读，不保存、不修改源文件。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from sw_connect import (  # noqa: E402
    connect_solidworks,
    get_com_member,
    open_document,
    safe_get_com_member,
)


def _feature_dimensions(feature) -> list[dict]:
    """@brief 读取一个特征下的全部显示尺寸。"""
    dims = []
    try:
        display = safe_get_com_member(feature, "GetFirstDisplayDimension")
        guard = 0
        while display and guard < 200:
            guard += 1
            record = {}
            try:
                dim = safe_get_com_member(display, "GetDimension")
                if dim is not None:
                    record["full_name"] = safe_get_com_member(dim, "FullName")
                    try:
                        record["value_mm"] = round(
                            float(get_com_member(dim, "SystemValue")) * 1000.0, 6)
                    except Exception:
                        pass
                    record["type"] = (safe_get_com_member(dim, "GetType2")
                                      or safe_get_com_member(dim, "Type"))
            except Exception:
                pass
            text = safe_get_com_member(display, "GetText", 0)
            if text:
                record["text"] = str(text)
            if record:
                dims.append(record)
            display = (safe_get_com_member(display, "GetNext3")
                       or safe_get_com_member(display, "GetNext"))
    except Exception:
        pass
    return dims


def _feature_tree(model, limit: int = 4000) -> list[dict]:
    """@brief 顺序遍历特征树，保留类型名与尺寸。"""
    features = []
    try:
        feature = safe_get_com_member(model, "FirstFeature")
        guard = 0
        while feature and guard < limit:
            guard += 1
            record = {
                "name": safe_get_com_member(feature, "Name"),
                "type": (safe_get_com_member(feature, "GetTypeName2")
                         or safe_get_com_member(feature, "GetTypeName")),
            }
            dims = _feature_dimensions(feature)
            if dims:
                record["dimensions"] = dims
            features.append(record)
            feature = safe_get_com_member(feature, "GetNextFeature")
    except Exception as exc:
        features.append({"error": str(exc)})
    return features


def _custom_properties(model) -> dict:
    """@brief 读取文档级自定义属性。"""
    props = {}
    try:
        manager = get_com_member(model, "Extension").CustomPropertyManager("")
        for name in list(manager.GetNames() or []):
            try:
                value = manager.Get6(name, "", True)
                props[str(name)] = str(value[0] if isinstance(value, (list, tuple)) else value)
            except Exception:
                pass
    except Exception:
        pass
    return props


def dump_part(sw, path: str) -> dict:
    """@brief 打开一个文档并导出结构化记录；无论成功失败都关闭文档。"""
    record = {"path": path, "name": os.path.basename(path)}
    model = open_document(sw, path, read_only=True, silent=True)
    if model is None:
        record["error"] = "open_failed"
        return record
    try:
        record["title"] = safe_get_com_member(model, "GetTitle")
        record["doc_type"] = safe_get_com_member(model, "GetType")
        try:
            box = list(get_com_member(model, "GetPartBox", True) or [])
            if len(box) >= 6:
                record["envelope_mm"] = [
                    round(abs(float(box[i + 3]) - float(box[i])) * 1000.0, 4)
                    for i in range(3)
                ]
                record["box_min_mm"] = [round(float(box[i]) * 1000.0, 4) for i in range(3)]
                record["box_max_mm"] = [round(float(box[i + 3]) * 1000.0, 4) for i in range(3)]
        except Exception as exc:
            record["envelope_error"] = str(exc)
        try:
            bodies = get_com_member(model, "GetBodies2", 0, False) or []
            record["body_count"] = len(list(bodies))
        except Exception:
            record["body_count"] = None
        try:
            material = safe_get_com_member(model, "GetMaterialPropertyName2", "", "")
            if material:
                record["material"] = str(material)
        except Exception:
            pass
        record["features"] = _feature_tree(model)
        props = _custom_properties(model)
        if props:
            record["custom_properties"] = props
    finally:
        try:
            sw.CloseDoc(safe_get_com_member(model, "GetTitle"))
        except Exception:
            pass
    return record


def _collect_paths(root: str, include_assemblies: bool) -> list[str]:
    """@brief 递归收集 SolidWorks 文档路径。"""
    extensions = {".sldprt"}
    if include_assemblies:
        extensions.add(".sldasm")
    paths = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in sorted(filenames):
            if os.path.splitext(filename)[1].lower() in extensions:
                paths.append(os.path.join(dirpath, filename))
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--part", help="单个 SLDPRT/SLDASM")
    target.add_argument("--root", help="递归目录")
    parser.add_argument("--output", required=True, help=".json（单件）或 .jsonl（目录）")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--match", default="")
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--include-assemblies", action="store_true")
    args = parser.parse_args()

    sw, _active_model = connect_solidworks(visible=args.visible, wait_seconds=30)
    if args.part:
        source = str(Path(args.part).resolve())
        if not Path(source).is_file():
            raise SystemExit(f"文件不存在: {source}")
        record = dump_part(sw, source)
        Path(args.output).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"output": args.output, "features": len(record.get("features", [])),
                          "error": record.get("error")}, ensure_ascii=False))
        return

    paths = _collect_paths(args.root, args.include_assemblies)
    if args.match:
        paths = [p for p in paths if args.match in os.path.basename(p)]
    if args.limit:
        paths = paths[:args.limit]
    print("parts:", len(paths), flush=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        for index, path in enumerate(paths, 1):
            try:
                record = dump_part(sw, path)
            except Exception:
                record = {"path": path, "name": os.path.basename(path),
                          "error": traceback.format_exc()}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            print("[%d/%d] %s features=%s" % (
                index, len(paths), os.path.basename(path),
                len(record.get("features", []))), flush=True)
    print("done:", len(paths), flush=True)


if __name__ == "__main__":
    main()
