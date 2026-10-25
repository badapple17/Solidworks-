"""CAD 建模与复核 CLI：开放格式写入、DXF 预览、DFM、Routing、FEA 与 OCP 曲面。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cad-studio", description="CAD 建模与复核 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    write_open = sub.add_parser("write-open-format")
    write_open.add_argument("--input", type=Path, required=True, help="NeutralCadDocument .cadstudio.json")
    write_open.add_argument("--out-dir", type=Path, required=True)
    write_open.add_argument("--formats", nargs="+", default=["cadstudio", "step", "iges", "brep", "stl", "obj", "glb", "dxf", "svg", "pdf", "png"])
    preview_dxf = sub.add_parser("preview-dxf")
    preview_dxf.add_argument("--input", type=Path, required=True, help="只读 DXF 输入")
    preview_dxf.add_argument("--output", type=Path, required=True, help="不覆盖的 .scene.json 输出")
    dfm = sub.add_parser("check-dfm")
    dfm.add_argument("--input", type=Path, required=True, help="NeutralCadDocument .cadstudio.json")
    dfm.add_argument("--output", type=Path, required=True, help="不覆盖旧文件的 DFM report JSON 输出")
    dfm.add_argument("--process", default="auto", help="machining/sheet_metal/laser_cutting/3d_printing；auto 时读取文档 metadata")
    dfm.add_argument("--profile", action="append", default=[], help="可重复指定 DFM Profile JSON，按供应商能力交集合并")
    dfm.add_argument("--brep-evidence", type=Path, help="可选 SolidWorks/OCCT B-Rep 证据 JSON")
    routing = sub.add_parser("check-routing")
    routing.add_argument("--input", type=Path, required=True, help="Routing 中性 JSON 输入")
    routing.add_argument("--output", type=Path, required=True, help="不覆盖旧文件的 Routing report JSON 输出")
    sub.add_parser("routing-preflight")
    fea_preflight = sub.add_parser("fea-preflight")
    fea_preflight.add_argument("--solver", choices=("auto", "calculix", "elmer"), default="auto")
    fea_prepare = sub.add_parser("prepare-fea")
    fea_prepare.add_argument("--input", type=Path, required=True, help="FEA 1.0 请求 JSON")
    fea_prepare.add_argument("--out-dir", type=Path, required=True, help="CalculiX 输入文件输出目录")
    fea_prepare.add_argument("--solver", choices=("auto", "calculix", "elmer"), default="auto")
    fea_run = sub.add_parser("run-fea")
    fea_run.add_argument("--input", type=Path, required=True, help="FEA 1.0 请求 JSON")
    fea_run.add_argument("--out-dir", type=Path, required=True, help="版本化求解目录")
    fea_run.add_argument("--timeout", type=int, default=600, help="求解超时秒数，范围 1-86400")
    fea_convergence = sub.add_parser("run-fea-convergence")
    fea_convergence.add_argument("--input", type=Path, required=True, help="FEA 网格收敛 1.0 请求 JSON")
    fea_convergence.add_argument("--out-dir", type=Path, required=True, help="版本化收敛序列目录")
    fea_convergence.add_argument("--timeout-per-case", type=int, default=600, help="每档网格求解超时秒数，范围 1-86400")
    advanced = sub.add_parser("review-advanced-geometry")
    advanced.add_argument("--input", type=Path, required=True, help="复杂曲面/模具中性计划 JSON")
    advanced.add_argument("--output", type=Path, required=True, help="不覆盖旧文件的前置报告 JSON 输出")
    loft = sub.add_parser("create-ocp-loft")
    loft.add_argument("--input", type=Path, required=True, help="OCP Loft 1.0 参数 JSON")
    loft.add_argument("--out-dir", type=Path, required=True, help="STEP/BREP/STL 版本化输出目录")
    surface = sub.add_parser("create-ocp-surface")
    surface.add_argument("--input", type=Path, required=True, help="OCP 高级曲面 1.0 参数 JSON")
    surface.add_argument("--out-dir", type=Path, required=True, help="STEP/BREP/STL 版本化输出目录")
    args = parser.parse_args(argv)

    if args.command == "write-open-format":
        from headless_cad_writer import export_headless

        result = export_headless(args.input, args.out_dir, args.formats)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") in {"pass", "pilot"} else 1
    if args.command == "preview-dxf":
        from dxf_preview_scene import dxf_to_preview_scene

        scene = dxf_to_preview_scene(args.input, args.output)
        print(json.dumps({
            "status": "pass",
            "backend": "ezdxf-preview-scene",
            "input": args.input.name,
            "output": str(args.output.resolve()),
            "entityCount": len(scene["entities"]),
            "layerCount": len(scene["layers"]),
            "limitations": scene["limitations"],
        }, ensure_ascii=False, indent=2))
        return 0
    if args.command == "check-dfm":
        from dfm_review import write_dfm_report

        result = write_dfm_report(args.input, args.output, process=args.process, profiles=args.profile, brep_evidence=args.brep_evidence)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    if args.command == "check-routing":
        from routing_review import review_routing_file

        result = review_routing_file(args.input, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    if args.command == "routing-preflight":
        from routing_review import probe_solidworks_routing

        result = probe_solidworks_routing()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    if args.command == "fea-preflight":
        from fea_analysis import discover_solver

        result = discover_solver(args.solver)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    if args.command == "prepare-fea":
        from fea_analysis import build_calculix_input, validate_analysis

        request = validate_analysis(args.input)
        if args.solver != "auto":
            request["solver"] = args.solver
        if request["solver"] == "elmer":
            result = {
                "schemaVersion": "1.0",
                "status": "blocked",
                "stage": "generate_input",
                "checks": [],
                "artifacts": [],
                "manual_review_required": True,
                "retryable": False,
                "error_code": "fea_elmer_adapter_not_implemented",
                "message": "Elmer 安全输入适配器尚未实现；当前 prepare-fea 只生成 CalculiX .inp。",
            }
        else:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            result = build_calculix_input(request, args.out_dir / f"{request['analysisId']}.inp")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    if args.command == "run-fea":
        from fea_analysis import run_analysis

        result = run_analysis(args.input, args.out_dir, timeout_seconds=args.timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    if args.command == "run-fea-convergence":
        from fea_convergence import run_convergence_study

        result = run_convergence_study(args.input, args.out_dir, timeout_seconds_per_case=max(1, min(args.timeout_per_case, 86400)))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    if args.command == "review-advanced-geometry":
        from advanced_geometry import write_preflight_report

        result = write_preflight_report(args.input, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    if args.command == "create-ocp-loft":
        from advanced_geometry_ocp import execute_ocp_loft

        result = execute_ocp_loft(args.input, args.out_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    if args.command == "create-ocp-surface":
        from advanced_surface_ocp import execute_advanced_surface

        result = execute_advanced_surface(args.input, args.out_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("status") in {"blocked", "failed"} else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
